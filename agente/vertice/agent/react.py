"""Agente ReAct de investigação de margem.

Dois transportes de ferramenta:
  - modo "texto" (padrão): as ferramentas são descritas no system prompt e o
    modelo responde AÇÃO/PARÂMETROS em texto, interpretado aqui por regex. Funciona
    independentemente de o gateway suportar function calling nativo.
  - modo "nativo": usa o parâmetro `tools=` da API. Mantido como opção porque o
    comportamento do gateway EloAgents com `tools=` não é confiável (em testes o
    modelo ignorou o schema ou chamou ferramentas de plataforma inexistentes no
    nosso registro). O loop valida toda chamada contra o registro e rejeita
    ferramentas desconhecidas, então o modo nativo degrada com erro claro em vez
    de produzir número inventado.
"""
from __future__ import annotations

import difflib
import json
import re
import time
from typing import Any

from .. import config
from ..engine import REGISTRO, executar, schemas_openai
from . import prompts
from .llm import LLM, construir_llm
from .router import (INVALID_PARAMETERS, ORIGEM_LLM, ORIGEM_ROTEADOR,
                     ORIGEM_SEMENTE,
                     PERGUNTA_COMPLEXA, TOOL_CALLED_ERROR, TOOL_CALLED_SUCCESS,
                     TOOL_NOT_CALLED, TOOL_RESULT_EMPTY, rotear, validar_parametros)
from .trace import ORIGENS_CONSULTA, Trace
from .verificacao import coletar_numeros, verificar_numeros

# Aceita "AÇÃO"/"ACAO", com ou sem markdown (**AÇÃO:**), maiúsculas variadas.
# ANCORADO EM INÍCIO DE LINHA e com DOIS-PONTOS OBRIGATÓRIO: sem isso, prosa como
# "avaliar a ação dos descontos" era lida como uma chamada à ferramenta "dos".
# A classe do nome é explicitamente [A-Za-z_] porque re.IGNORECASE faz [a-z_]
# casar maiúsculas — era assim que "AÇÃO: N/A" virava a ferramenta "N".
RE_ACAO = re.compile(
    r"^[ \t>*_-]*A[ÇC][ÃA]O[ \t]*\**[ \t]*:[ \t]*\**[ \t]*[`\"']?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE | re.MULTILINE,
)

# Respostas em que o modelo declara que NÃO há ação a tomar. Sem esta lista, o
# texto após "AÇÃO:" é capturado como se fosse nome de ferramenta.
NAO_ACAO = {"n", "na", "nenhuma", "nenhum", "nao", "none", "null", "nada",
            "nenhuma_acao", "n_a", "finalizar", "responder", "concluir"}
RE_PARAMS = re.compile(r"PAR[ÂA]METROS\s*:?\s*\**\s*(\{.*?\})", re.IGNORECASE | re.DOTALL)
RE_PENSAMENTO = re.compile(r"PENSAMENTO\s*:?\s*\**\s*(.+?)(?=\n\s*A[ÇC][ÃA]O|$)",
                           re.IGNORECASE | re.DOTALL)
# Seções da resposta final. Os padrões toleram o que o modelo realmente produz:
# markdown (**FATO:**, ## FATO), acentuação ausente (INFERENCIA, FORCA DA
# EVIDENCIA) e dois-pontos omitido em estilo de cabeçalho.
SECOES_FINAIS: list[tuple[str, str]] = [
    ("FATO", r"FATO"),
    ("INFERÊNCIA", r"INFER[ÊE]NCIA"),
    ("RECOMENDAÇÃO", r"RECOMENDA[ÇC][ÃA]O"),
    ("FORÇA DA EVIDÊNCIA", r"FOR[ÇC]A[ \t]+DA[ \t]+EVID[ÊE]NCIA"),
]


def _re_secao(corpo: str) -> re.Pattern:
    """Casa um cabeçalho de seção com ou sem markdown/acento/dois-pontos."""
    return re.compile(
        r"^[ \t]*[#>\-*_]*[ \t]*\**[ \t]*(?:" + corpo
        + r")[ \t]*\**[ \t]*(?::[ \t]*\**[ \t]*|$)",
        re.IGNORECASE | re.MULTILINE,
    )


RE_SECAO = {nome: _re_secao(corpo) for nome, corpo in SECOES_FINAIS}
RE_FINAL = RE_SECAO["FATO"]

# Ferramenta pré-semeada: sem isso o modelo tende a tratar "Vértice Retail" como
# empresa desconhecida e pedir dados ao usuário em vez de investigar.
FERRAMENTA_SEMENTE = "margem_consolidada"

# Segunda semente: a ponte do pós-pedido. O retrato consolidado sozinho enquadra
# o problema como "o que se perde entre a receita e a margem", e o maior
# vazamento do caso acontece depois dela.
FERRAMENTA_SEMENTE_POS_PEDIDO = "perda_pos_pedido"

# Conjunto das sementes: o que foi entregue ANTES do primeiro turno não
# conta como investigação do modelo.
SEMENTES = frozenset({FERRAMENTA_SEMENTE, FERRAMENTA_SEMENTE_POS_PEDIDO})

LIMITE_OBS_CHARS = 6000


def extrair_acao(texto: str) -> tuple[str | None, dict, str | None]:
    """Interpreta a resposta textual do modelo -> (ferramenta, parâmetros, pensamento).

    Devolve (None, {}, pensamento) quando não há chamada de ferramenta — o que
    inclui o caso da resposta final.
    """
    if not texto:
        return None, {}, None
    pens = RE_PENSAMENTO.search(texto)
    pensamento = pens.group(1).strip() if pens else None

    # Uma resposta final começa em FATO: e não deve ser lida como ação, mesmo que
    # o modelo mencione o nome de uma ferramenta no corpo do texto.
    m_acao = RE_ACAO.search(texto)
    m_fato = RE_FINAL.search(texto)
    if m_fato and (not m_acao or m_fato.start() < m_acao.start()):
        return None, {}, pensamento
    if not m_acao:
        return None, {}, pensamento

    ferramenta = m_acao.group(1).strip()
    # "AÇÃO: N/A", "AÇÃO: Não aplicável", "AÇÃO: nenhuma" — o modelo está dizendo
    # que não há ferramenta a chamar, não pedindo uma ferramenta chamada "N".
    if ferramenta.lower() in NAO_ACAO:
        return None, {}, pensamento

    # "AÇÃO: Chamar indice_sazonalidade e tendencia_ajustada_sazonalidade" — o
    # modelo prefixou com um verbo ("Chamar"/"Usar"/"Executar a ferramenta"...)
    # e às vezes citou mais de um nome na mesma linha. A extração ingênua pega
    # a primeira palavra ("Chamar"), que não é ferramenta nenhuma. Procura,
    # nessa ordem: (1) a MESMA LINHA da AÇÃO, usando o PRIMEIRO nome que
    # aparece; (2) o bloco PENSAMENTO, usando o ÚLTIMO nome citado — é a
    # frase mais próxima da decisão ("já tenho X, agora preciso de Y");
    # (3) o resto do texto após a AÇÃO, usando o primeiro nome. Em produção
    # o modelo às vezes escreve "AÇÃO: Chamar()" vazio e só nomeia a
    # ferramenta na linha de PENSAMENTO logo acima — sem isso vira KeyError
    # ("Chamar" não existe) e desperdiça uma rodada inteira. Se um 2º nome
    # citado não for chamado, o guardrail de "ferramenta citada sem ser
    # chamada" cobra isso depois.
    if ferramenta not in REGISTRO:
        fim_linha = texto.find("\n", m_acao.end())
        fim_linha = fim_linha if fim_linha != -1 else len(texto)
        resto_linha = texto[m_acao.end():fim_linha]

        def _primeiro(trecho: str) -> str | None:
            candidatos = sorted(
                (m.start(), n) for n in REGISTRO
                if (m := re.search(rf"\b{re.escape(n)}\b", trecho))
            )
            return candidatos[0][1] if candidatos else None

        def _ultimo(trecho: str) -> str | None:
            candidatos = sorted(
                (m.start(), n) for n in REGISTRO
                if (m := re.search(rf"\b{re.escape(n)}\b", trecho))
            )
            return candidatos[-1][1] if candidatos else None

        encontrado = (_primeiro(resto_linha)
                      or (pensamento and _ultimo(pensamento))
                      or _primeiro(texto[m_acao.end():]))
        if encontrado:
            ferramenta = encontrado

    params: dict[str, Any] = {}
    m_par = RE_PARAMS.search(texto, m_acao.end() - 1)
    if m_par:
        bruto = m_par.group(1)
        try:
            params = json.loads(bruto)
        except json.JSONDecodeError:
            # Tolera aspas simples e vírgula sobrando, comuns em saída de LLM.
            tentativa = re.sub(r",\s*([}\]])", r"\1", bruto.replace("'", '"'))
            try:
                params = json.loads(tentativa)
            except json.JSONDecodeError:
                params = {}
    if not isinstance(params, dict):
        params = {}
    return ferramenta, params, pensamento


def _sugestao(nome: str) -> str:
    """Sugere ferramentas parecidas em vez de repetir as 19 a cada erro.

    Despejar o catálogo inteiro a cada falha gasta contexto e, na prática, não
    ajudou o modelo a se corrigir — ele repetia a mesma chamada inválida.
    """
    if nome in REGISTRO:
        return ""
    perto = difflib.get_close_matches(nome.lower(), list(REGISTRO), n=3, cutoff=0.4)
    if perto:
        return f"\nVocê quis dizer: {', '.join(perto)}?"
    return ("\nEssa ferramenta não existe. Se NENHUMA ferramenta da lista responde à "
            "pergunta, não invente uma: responda agora no formato final dizendo, em "
            "INFERÊNCIA, o que não é possível apurar com as ferramentas disponíveis.")


def _serializar(obj: Any) -> str:
    txt = json.dumps(obj, ensure_ascii=False, indent=1, default=str)
    if len(txt) > LIMITE_OBS_CHARS:
        txt = txt[:LIMITE_OBS_CHARS] + f"\n... [truncado em {LIMITE_OBS_CHARS} caracteres]"
    return txt


MARCAS_TAMANHO = ("too large", "context_length", "maximum context",
                  "request_too_large", "413", "tokens per request")


# O gpt-oss emite, de vez em quando, uma chamada de função mesmo com tools=None
# no modo texto — e o provedor recusa a geração com 400 "Tool choice is none, but
# model called a tool". O nosso protocolo ReAct vai dentro do campo `arguments`,
# ou seja: o modelo entendeu a pergunta, só embrulhou a resposta no canal errado.
# É falha de forma, não de conteúdo, e costuma passar numa segunda tentativa.
MARCAS_FERRAMENTA_INDEVIDA = ("tool choice is none", "model called a tool",
                              "tool_choice", "called a tool")


def _nome_de_ferramenta(bruto: str) -> str:
    """Nome como o registro conhece.

    A Groq devolveu "tool_margem_por_dimensao" — alguns provedores prefixam o
    nome da função. Sem tirar o prefixo, a chamada certa morreria como
    "ferramenta não existe".
    """
    nome = (bruto or "").strip()
    if nome in REGISTRO:
        return nome
    for prefixo in ("tool_", "functions.", "function_"):
        if nome.startswith(prefixo) and nome[len(prefixo):] in REGISTRO:
            return nome[len(prefixo):]
    return nome


def _erro_de_ferramenta_indevida(e: Exception) -> bool:
    msg = f"{type(e).__name__}: {e}".lower()
    return any(m in msg for m in MARCAS_FERRAMENTA_INDEVIDA)


# Cota esgotada é diferente de pedido grande demais, embora a Groq use o mesmo
# "Request too large" nos dois: aqui vem 'rate_limit_exceeded' / 'tokens per
# minute'. Encolher não resolve — só o tempo resolve —, então a resposta precisa
# dizer isso em vez de mandar "tente quando o gateway voltar".
MARCAS_COTA = ("rate_limit", "rate limit", "tokens per minute", "tokens per day",
               "quota", "tpm", "tpd", "try again in")
RE_ESPERA = re.compile(r"try again in ([\d.]+)\s*(s|ms|m\b|seconds?|minutes?)",
                       re.IGNORECASE)


def _erro_de_cota(e: Exception) -> bool:
    return any(m in f"{type(e).__name__}: {e}".lower() for m in MARCAS_COTA)


def _espera_sugerida(msg: str) -> str:
    """O provedor costuma dizer em quanto tempo tentar de novo; sem isso a
    pessoa fica adivinhando se espera dez segundos ou um dia."""
    m = RE_ESPERA.search(msg)
    return f"{m.group(1)}{m.group(2)}" if m else ""


def _erro_de_tamanho(e: Exception) -> bool:
    """O provedor recusou por tamanho do pedido, não por conteúdo."""
    msg = f"{type(e).__name__}: {e}".lower()
    return any(m in msg for m in MARCAS_TAMANHO)


def _reduzir_pedido(msgs: list[dict], modo: str, limite_msg: int = 1500) -> list[dict]:
    """Refaz a conversa em versão enxuta para uma segunda tentativa.

    Camada gratuita de provedor costuma ter teto BAIXO de tokens por
    requisição, e o teto varia por conta — não dá para calibrar isso por
    variável de ambiente sem a pessoa adivinhar o número. Em vez disso: se o
    pedido foi recusado por tamanho, encolhe e tenta de novo, uma vez.

    O que encolhe, nesta ordem: catálogo de ferramentas (o maior bloco), depois
    o histórico (some inteiro — é contexto de conversa, não da pergunta), depois
    o corpo das mensagens restantes. O que NUNCA some é o resultado de
    ferramenta da pergunta atual: é dele que sai o número da resposta.
    """
    sistema = {"role": "system",
               "content": prompts.system_prompt(modo, compacto=True)}
    corpo = [m for m in msgs[1:] if m.get("role") != "assistant"]
    mantidas = corpo[-3:] if len(corpo) > 3 else corpo
    enxutas = []
    for m in mantidas:
        texto = m["content"]
        if len(texto) > limite_msg:
            texto = texto[:limite_msg] + "\n... [encurtado para caber no limite do provedor]"
        enxutas.append({"role": m["role"], "content": texto})
    return [sistema] + enxutas


def _linha_curta(item: dict, max_campos: int = 4) -> str:
    """Uma linha de tabela em texto, só com o que responde a pergunta.

    Despejar as treze colunas de margem_por_dimensao por canal deixa a resposta
    ilegível; o identificador e as métricas de margem bastam para dizer qual
    canal é o pior.
    """
    chaves = list(item)
    prioritarias = [k for k in chaves[1:]
                    if any(t in k for t in ("margem", "pct", "pedidos"))]
    escolhidas = chaves[:1] + prioritarias[:max_campos - 1]
    return " ".join(f"{k}={item[k]}" for k in escolhidas
                    if not isinstance(item.get(k), (list, dict)))


def _erro_curto(msg: str, limite: int = 300) -> str:
    """Mensagem de erro do provedor sem cortar o que interessa.

    Cortar em 160 caracteres escondia justamente o fim — que é onde vem
    "Limit 6000, Requested 9000", o número que diz o que precisa encolher.
    """
    if len(msg) <= limite:
        return msg
    return f"{msg[:limite // 2]} … {msg[-(limite // 2):]}"


def _resumir_para_leitura(resultado: Any, limite: int = 12) -> str:
    """Campos escalares de um retorno de ferramenta, em texto corrido pt-BR.

    Serve à resposta sem modelo (`_resposta_sem_modelo`): sem o redator, alguém
    precisa transformar o dicionário em frase. Só formata — não escolhe o que é
    relevante nem recalcula nada.
    """
    if not isinstance(resultado, dict):
        return _serializar(resultado)

    partes = []
    linhas_uteis = ""
    for chave, valor in resultado.items():
        # Listas eram descartadas inteiras, e é nelas que mora a resposta de
        # margem_por_dimensao: sem isso, "qual canal tem menor margem?" saía
        # como "dimensao = canal; n grupos = 7" — verdadeiro e inútil.
        if isinstance(valor, list) and valor and isinstance(valor[0], dict) and not linhas_uteis:
            linhas_uteis = "; ".join(_linha_curta(item) for item in valor[:8])
            continue
        if chave in ("premissa", "nota", "base_do_ganho_pp") or isinstance(valor, (list, dict)):
            continue
        if isinstance(valor, bool) or valor is None:
            continue
        if isinstance(valor, (int, float)):
            # Não arredonda: 0,076 p.p. arredondado para 0,08 seria alterar um
            # número apurado pelo motor só para caber no texto.
            # Inteiro sai sem casas; o resto mantém as casas do próprio valor,
            # com o mínimo de 2 para dinheiro não sair como "21.162,4".
            casas = 0 if float(valor).is_integer() else max(
                2, len(str(valor).partition(".")[2].rstrip("0")))
            texto = f"{valor:,.{casas}f}".replace(
                ",", "\x00").replace(".", ",").replace("\x00", ".")
        else:
            texto = str(valor)
        partes.append(f"{chave.replace('_', ' ')} = {texto}")
        if len(partes) >= limite:
            break

    recorte = resultado.get("recorte") or resultado.get("segmento")
    if isinstance(recorte, dict) and recorte:
        alvo = ", ".join(f"{k}={v}" for k, v in recorte.items())
        partes.insert(0, f"recorte {alvo}")
    texto = "; ".join(partes) if partes else ""
    if linhas_uteis:
        texto = f"{texto} | {linhas_uteis}" if texto else linhas_uteis
    return texto or _serializar(resultado)


class AgenteMargem:
    """Agente ReAct. Decide sozinho quais ferramentas chamar e em que ordem."""

    def __init__(self, llm: LLM | None = None, modelo: str | None = None,
                 modelo_sintese: str | None = None, modo: str | None = None,
                 max_iteracoes: int | None = None, mock: bool = False,
                 roteiro_mock: list[str] | None = None, verbose: bool = True):
        self.llm = llm or construir_llm(mock=mock, roteiro=roteiro_mock)
        self.modelo = modelo or config.MODELO_INVESTIGACAO
        self.modelo_sintese = modelo_sintese or config.MODELO_SINTESE
        self.modo = modo or config.MODO_FERRAMENTAS
        self.max_iteracoes = max_iteracoes or config.MAX_ITERACOES
        self.verbose = verbose
        self.historico: list[dict] = []  # persiste entre perguntas na sessão

    # -- utilidades de saída ------------------------------------------------
    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    def _chamar_ferramenta(self, nome: str, params: dict, trace: Trace, iteracao: int,
                           falhas: dict[str, int] | None = None, pergunta: str = "",
                           origem: str = ORIGEM_LLM) -> str:
        t0 = time.perf_counter()
        trace.add("acao", None, ferramenta=nome, parametros=params, iteracao=iteracao,
                  origem=origem)
        self._log(f"  🔧 {nome}({json.dumps(params, ensure_ascii=False)})")
        try:
            resultado = executar(nome, params)
            dur = (time.perf_counter() - t0) * 1000
            # Rodou e veio vazio é diferente de rodou e trouxe dado: sem essa
            # distinção a resposta final dizia "não retornou" nos dois casos.
            vazio = resultado in (None, {}, [], ()) or (
                isinstance(resultado, dict) and resultado.get("linhas") == [])
            trace.add("observacao", resultado, ferramenta=nome, duracao_ms=round(dur, 1),
                      iteracao=iteracao, origem=origem, parametros=params,
                      status=TOOL_RESULT_EMPTY if vazio else TOOL_CALLED_SUCCESS)
            return f"{prompts.ROTULO_RESULTADO}\nFerramenta: {nome}\n{_serializar(resultado)}"
        except Exception as e:  # erro vira observação: o agente se corrige sozinho
            dur = (time.perf_counter() - t0) * 1000
            msg = f"{type(e).__name__}: {e}"
            trace.add("erro", msg, ferramenta=nome, duracao_ms=round(dur, 1),
                      iteracao=iteracao, origem=origem, status=TOOL_CALLED_ERROR)
            self._log(f"  ⚠️  {msg}")

            # TypeError = a ferramenta existe, mas a chamada está malformada
            # (parâmetro obrigatório ausente ou desconhecido). Nomear o que falta
            # não bastou em produção: o modelo chamou a ferramenta certa com
            # PARÂMETROS: {} duas vezes seguidas. Mostrar o exemplo pronto, já na
            # primeira falha — não só depois de repetir.
            if isinstance(e, TypeError) and nome in REGISTRO:
                orientacao = f"\n\n{prompts.cobrar_parametros(nome, pergunta)}"
            else:
                orientacao = _sugestao(nome)  # ferramenta inexistente: sugestão fuzzy

            aviso = ""
            if falhas is not None:
                chave = f"{nome}|{json.dumps(params, sort_keys=True, default=str)}"
                falhas[chave] = falhas.get(chave, 0) + 1
                if falhas[chave] >= 2:
                    aviso = ("\n\nATENÇÃO: você já tentou exatamente esta chamada e ela falhou "
                             "antes. NÃO repita. Escolha outra ferramenta da lista, ou responda "
                             "agora no formato final (FATO/INFERÊNCIA/RECOMENDAÇÃO/FORÇA DA "
                             "EVIDÊNCIA) com o que já foi apurado.")
            return f"{prompts.ROTULO_ERRO}\nFerramenta: {nome}\n{msg}{orientacao}{aviso}"

    # -- roteamento determinístico -------------------------------------------
    def _rotear_e_executar(self, pergunta: str, trace: Trace, msgs: list[dict]) -> None:
        """Roteia, valida e (se der) executa a ferramenta antes do 1º turno do
        modelo, injetando o resultado real na conversa.

        Só isso já resolve o caso que motivou o roteador: com o resultado de
        `simular_teto_desconto` na mão, o modelo não tem como dizer que a
        ferramenta não retornou. Falha de roteamento nunca derruba a
        investigação — no pior caso o ReAct assume, como antes."""
        try:
            r = rotear(pergunta)
        except Exception as e:                       # roteador é auxiliar, não crítico
            trace.add("roteamento", {"erro": f"{type(e).__name__}: {e}"})
            return

        registro = r.to_dict()
        if not r.ferramenta:
            registro["status_ferramenta"] = TOOL_NOT_CALLED
            trace.roteamento = registro
            trace.add("roteamento", registro)
            self._log(f"  🧭 {r.intencao} — sem rota determinística, seguindo por investigação")
            return

        params, problemas = validar_parametros(r.ferramenta, r.parametros)
        registro["parametros"] = params
        if problemas:
            # Parâmetro ausente ou inválido NÃO vira palpite: o modelo recebe o
            # que falta e decide como prosseguir.
            registro.update({"status_ferramenta": INVALID_PARAMETERS, "problemas": problemas})
            trace.roteamento = registro
            trace.add("roteamento", registro, status=INVALID_PARAMETERS)
            self._log(f"  🧭 {r.intencao} — parâmetros insuficientes: {problemas}")
            msgs.append({"role": "user", "content":
                         f"{prompts.ROTULO_SISTEMA} A leitura determinística da pergunta "
                         f"apontou {r.ferramenta}, mas os parâmetros não fecharam: "
                         f"{'; '.join(problemas)}. Peça o que falta ou escolha outro "
                         f"caminho — não preencha por conta própria."})
            return

        # A semente já executa margem_consolidada: repetir a mesma chamada com os
        # mesmos parâmetros só duplicaria trabalho e poluiria o trace.
        ja_feita = any(p.tipo == "acao" and p.ferramenta == r.ferramenta
                       and (p.parametros or {}) == params for p in trace.passos)
        if ja_feita:
            registro["status_ferramenta"] = TOOL_CALLED_SUCCESS
            registro["nota"] = "resultado já obtido nesta investigação; não repetida"
            trace.roteamento = registro
            trace.add("roteamento", registro, status=TOOL_CALLED_SUCCESS)
            self._log(f"  🧭 {r.intencao} -> {r.ferramenta} (já executado; não repetido)")
            return

        trace.roteamento = registro
        trace.add("roteamento", registro)
        self._log(f"  🧭 {r.intencao} -> {r.ferramenta}"
                  f"({json.dumps(params, ensure_ascii=False)}) [determinístico]")

        obs = self._chamar_ferramenta(r.ferramenta, params, trace, iteracao=0,
                                      pergunta=pergunta, origem=ORIGEM_ROTEADOR)
        ultimo = trace.passos[-1]
        trace.roteamento["status_ferramenta"] = ultimo.status or TOOL_CALLED_ERROR
        msgs.append({"role": "user", "content":
                     f"{obs}\n\n{prompts.ROTULO_SISTEMA} Esta chamada foi decidida e "
                     f"executada pelo sistema a partir da leitura da pergunta "
                     f"(intenção {r.intencao}). O resultado acima é real e já está "
                     f"apurado — use estes números. Chame mais ferramentas se precisar "
                     f"complementar."})

    # -- loop principal -----------------------------------------------------
    def investigar(self, pergunta: str, origem_consulta: str = "ad_hoc") -> Trace:
        """origem_consulta: "ad_hoc" (pergunta pontual, padrão) ou
        "revisao_periodica" (disparada por agendamento). Fica registrado no
        trace para o consumidor conseguir separar os dois casos depois."""
        if origem_consulta not in ORIGENS_CONSULTA:
            raise ValueError(
                f"origem_consulta inválida: '{origem_consulta}'. "
                f"Use uma de: {list(ORIGENS_CONSULTA)}"
            )
        trace = Trace(pergunta=pergunta, modelo=self.modelo, modo_ferramentas=self.modo,
                      origem_consulta=origem_consulta)
        trace.add("pergunta", pergunta)
        self._log(f"\n❓ {pergunta}")

        msgs = [{"role": "system", "content": prompts.system_prompt(self.modo)}]
        # Só as últimas trocas: sem corte, a conversa inteira ia junto de cada
        # pergunta e o pedido crescia até o provedor recusar por tamanho.
        limite_hist = config.max_mensagens_historico()
        msgs += self.historico[-limite_hist:] if limite_hist else []
        msgs.append({"role": "user", "content": f"{prompts.ROTULO_PERGUNTA} {pergunta}"})

        # Pré-semeadura: entrega o retrato consolidado antes do 1º turno do modelo.
        semente = self._chamar_ferramenta(FERRAMENTA_SEMENTE, {}, trace, iteracao=0,
                                          origem=ORIGEM_SEMENTE)
        msgs.append({"role": "user", "content":
                     f"{semente}\n\n{prompts.ROTULO_SISTEMA} Este é o retrato consolidado "
                     f"da base, já carregado para você. Ele é o PONTO DE PARTIDA, não a "
                     f"resposta. Continue a investigação da pergunta acima chamando as "
                     f"ferramentas que julgar necessárias."
                     f"{prompts.bloco_sugestoes(pergunta)}"})

        # Segunda semente: a ponte do pós-pedido, SÓ em pergunta aberta.
        #
        # A margem consolidada sozinha enquadra o problema como "o que se perde
        # ENTRE a receita e a margem", e o maior vazamento do caso acontece
        # DEPOIS dela. Numa pergunta aberta ("por que a margem caiu?", "qual a
        # prioridade nº 1?") é o modelo que escolhe por onde investigar, e sem
        # este retrato ele parte de um enquadramento que ignora 26,7% da margem
        # calculada — sem ter como saber que a ferramenta existe.
        #
        # Em pergunta estruturada o roteador já executa a ferramenta certa, e um
        # segundo retrato seria só ruído e custo de token. Por isso a semente é
        # condicional. Vem com a trava de dupla contagem colada, porque é aqui
        # que ela é necessária: os dois retratos chegam juntos e não se somam.
        # O roteador é auxiliar: se quebrar, a investigação segue sem a segunda
        # semente, exatamente como seguia antes de ela existir.
        try:
            aberta = rotear(pergunta).intencao == PERGUNTA_COMPLEXA
        except Exception:           # noqa: BLE001
            aberta = False
        if aberta:
            try:
                ponte = self._chamar_ferramenta(FERRAMENTA_SEMENTE_POS_PEDIDO, {}, trace,
                                                iteracao=0, origem=ORIGEM_SEMENTE)
                msgs.append({"role": "user", "content":
                             f"{ponte}\n\n{prompts.ROTULO_SISTEMA} Esta é a ponte entre a "
                             f"margem CALCULADA e a margem que se REALIZA, no ano-base. "
                             f"ATENÇÃO: estes valores NÃO se somam ao retrato consolidado "
                             f"acima — aquele mede o que se perde entre a receita bruta e "
                             f"a margem; este mede o que se perde depois dela. E "
                             f"cancelamento e pendência são margem que nunca se realizou, "
                             f"NÃO economia capturável: não entram em caso-base nem em "
                             f"business case."})
            except Exception as e:  # noqa: BLE001 — semente é apoio, nunca bloqueia
                self._log(f"  ⚠️  semente do pós-pedido indisponível ({e}); seguindo sem ela")

        # Roteamento determinístico: quando a pergunta é estruturada, quem escolhe
        # a ferramenta e preenche os parâmetros é o Python — o modelo recebe o
        # resultado já calculado e cuida só da redação. Isso existe porque
        # "limitar o desconto de Moda no Email Marketing a 17%" não era
        # respondida: a pista por palavra-chave casava "Email Marketing" com
        # marketing e sugeria ranking de ROAS, e a extração nem conhecia
        # categoria. Pergunta aberta continua no ReAct, logo abaixo.
        self._rotear_e_executar(pergunta, trace, msgs)

        resposta = None
        falhas: dict[str, int] = {}   # (ferramenta+params) -> nº de falhas idênticas
        cobrou_investigacao = False   # a cobrança por investigar é feita uma única vez
        reprovas_numericas = 0        # quantas vezes a resposta trouxe número sem ferramenta
        reprovas_vocabulario = 0      # quantas vezes FORÇA DA EVIDÊNCIA usou palavra errada
        reprovas_sem_teste = 0        # quantas vezes FORTE/MODERADA veio sem teste estatístico
        reprovas_periodo = 0          # quantas vezes a RECOMENDAÇÃO citou R$ sem período
        cobrou_ferramenta = False     # o modelo citou a ferramenta certa sem executá-la
        reduziu_pedido = False        # já encolhemos o pedido após recusa por tamanho
        ligou_ferramentas_nativas = False  # o modelo exigiu function calling e cedemos
        for it in range(1, self.max_iteracoes + 1):
            try:
                usar_nativo = self.modo == "nativo" or ligou_ferramentas_nativas
                msg = self.llm.completar(
                    msgs, self.modelo, tools=schemas_openai() if usar_nativo else None)
            except Exception as e:
                # Recusado por TAMANHO: encolhe o pedido e tenta uma vez mais,
                # em vez de exigir que a pessoa descubra o teto do provedor.
                if _erro_de_tamanho(e) and not reduziu_pedido:
                    reduziu_pedido = True
                    antes = sum(len(m["content"]) for m in msgs)
                    msgs = _reduzir_pedido(msgs, self.modo)
                    depois = sum(len(m["content"]) for m in msgs)
                    trace.add("pensamento",
                              {"pedido_reduzido": f"{antes} -> {depois} caracteres",
                               "motivo": f"{type(e).__name__}: {e}"[:200]}, iteracao=it)
                    self._log(f"  ✂️  pedido grande demais ({antes} chars) — "
                              f"reenviando com {depois}")
                    continue
                # O modelo tentou chamar ferramenta pelo canal nativo e o
                # provedor recusou porque mandamos tools=None. A chamada em si
                # vinha CORRETA (nome e parâmetros válidos): o modelo é treinado
                # para function calling e insistir em texto é remar contra. Então
                # a resposta é LIGAR as ferramentas e deixá-lo trabalhar como sabe.
                if _erro_de_ferramenta_indevida(e) and not ligou_ferramentas_nativas:
                    ligou_ferramentas_nativas = True
                    trace.add("pensamento",
                              {"ferramentas_nativas_ligadas": f"{type(e).__name__}: {e}"[:200]},
                              iteracao=it)
                    self._log("  🔧 modelo pediu function calling — ligando ferramentas "
                              "nativas e repetindo")
                    continue
                # Gateway fora do ar, orçamento estourado, timeout: o número já
                # foi apurado em Python antes do modelo entrar. Jogar isso fora e
                # devolver um erro 500 seria perder a única parte que não depende
                # de terceiro. Ver _resposta_sem_modelo.
                resposta = self._resposta_sem_modelo(pergunta, trace, e)
                break
            texto = (getattr(msg, "content", None) or "").strip()
            chamadas = getattr(msg, "tool_calls", None)

            # -- function calling da API ---------------------------------------
            # Aceita a chamada nativa sempre que ela vier, não só com
            # modo="nativo": um modelo que insiste nesse canal (gpt-oss) tem a
            # chamada executada em vez de descartada.
            if chamadas:
                msgs.append({"role": "assistant", "content": texto or "(chamada de ferramenta)"})
                for tc in chamadas:
                    nome = _nome_de_ferramenta(tc.function.name)
                    try:
                        params = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        params = {}
                    obs = self._chamar_ferramenta(nome, params, trace, it, falhas, pergunta)
                    msgs.append({"role": "user", "content": obs})
                continue

            ferramenta, params, pensamento = extrair_acao(texto)
            if pensamento:
                trace.add("pensamento", pensamento, iteracao=it)
                self._log(f"  🧠 {pensamento[:160]}")

            if ferramenta:
                msgs.append({"role": "assistant", "content": texto})
                obs = self._chamar_ferramenta(ferramenta, params, trace, it, falhas, pergunta)
                msgs.append({"role": "user", "content": obs})
                # Três falhas idênticas: o modelo não vai se corrigir sozinho.
                if max(falhas.values(), default=0) >= 3:
                    trace.add("pensamento", "loop de falha detectado; interrompendo investigação",
                              iteracao=it)
                    self._log("  ⛔ mesma chamada falhou 3x — forçando síntese")
                    break
                continue

            # Sem chamada de ferramenta: ou é a resposta final, ou o modelo se perdeu.
            if RE_FINAL.search(texto):
                # Responder só com a semente não é investigar: a semente é o retrato
                # consolidado, não a resposta de uma pergunta específica. Cobra uma vez.
                # Conta ferramentas que NÃO são semente: com duas sementes em
                # pergunta aberta, um teto fixo de 1 deixaria de cobrar quem
                # respondeu sem investigar nada.
                usadas_de_verdade = [f for f in trace.ferramentas_usadas
                                     if f not in SEMENTES]
                if not usadas_de_verdade and not cobrou_investigacao:
                    cobrou_investigacao = True
                    trace.add("pensamento",
                              "resposta final sem nenhuma ferramenta específica; cobrando investigação",
                              iteracao=it)
                    self._log("  ↩️  respondeu só com a semente — cobrando investigação")
                    msgs.append({"role": "assistant", "content": texto})
                    msgs.append({"role": "user", "content": prompts.cobrar_investigacao()})
                    continue
                # O modelo às vezes identifica a ferramenta certa, escreve o nome dela
                # na resposta ("sem o resultado de X não dá") e mesmo assim desiste.
                citadas = self._ferramentas_citadas_nao_chamadas(texto, trace)
                if citadas and not cobrou_ferramenta:
                    cobrou_ferramenta = True
                    trace.add("pensamento",
                              {"ferramentas_citadas_nao_chamadas": citadas}, iteracao=it)
                    self._log(f"  📎 citou sem chamar: {', '.join(citadas)} — cobrando execução")
                    msgs.append({"role": "assistant", "content": texto})
                    msgs.append({"role": "user",
                                 "content": prompts.cobrar_ferramenta_citada(citadas, pergunta)})
                    continue

                # GUARDA CENTRAL: todo número da resposta tem de ter vindo de uma
                # ferramenta. O modelo já apresentou multiplicação própria como se
                # fosse dado apurado; pedir no prompt não basta, é preciso conferir.
                ver = self._verificar(texto, trace, pergunta)
                if not ver["ok"] and reprovas_numericas < 2:
                    reprovas_numericas += 1
                    trace.add("erro", {"motivo": "números não rastreáveis a ferramenta",
                                       "verificacao": ver}, iteracao=it)
                    self._log(f"  🚫 números sem ferramenta: {', '.join(ver['suspeitos'][:5])}")
                    msgs.append({"role": "assistant", "content": texto})
                    msgs.append({"role": "user",
                                 "content": prompts.cobrar_numeros(ver["suspeitos"])})
                    continue
                trace.add("pensamento", {"verificacao_numerica": ver}, iteracao=it)
                if not ver["ok"]:
                    resposta = self._fallback_numeros(pergunta, trace, ver)
                    break

                # FORÇA DA EVIDÊNCIA fora do vocabulário fechado (ex.: "Alta" em
                # vez de FORTE/MODERADA/FRACA). Uma cobrança primeiro; se
                # persistir, NÃO aceita como estava — força FRACA
                # deterministicamente (ver _forcar_vocabulario_fechado).
                # Antes disso "Alta"/"NULA"/"ALTA" passavam direto como
                # resposta final via API web, porque nada reescrevia o texto
                # quando a cobrança única não resolvia.
                vfmt = validar_formato_final(texto)
                if not vfmt["vocabulario_evidencia_ok"]:
                    if reprovas_vocabulario < 1:
                        reprovas_vocabulario += 1
                        trace.add("erro", {"motivo": "FORÇA DA EVIDÊNCIA fora do vocabulário "
                                           "FORTE/MODERADA/FRACA"}, iteracao=it)
                        self._log("  📐 vocabulário de evidência errado — cobrando correção")
                        msgs.append({"role": "assistant", "content": texto})
                        msgs.append({"role": "user",
                                     "content": prompts.cobrar_vocabulario_evidencia()})
                        continue
                    palavra_errada = _palavra_alegada_fora_do_vocabulario(texto)
                    texto = _forcar_vocabulario_fechado(texto, palavra_errada or "?")
                    trace.add("pensamento",
                              {"vocabulario_forcado": f"'{palavra_errada}' -> FRACA "
                                                       "(fora do padrão mesmo após cobrança)"},
                              iteracao=it)
                    self._log(f"  ⬇️  '{palavra_errada}' fora do vocabulário mesmo após "
                              "cobrança — forçado para FRACA")

                # FORTE/MODERADA sem nenhum teste estatístico chamado na
                # investigação: confiança tão infundada quanto número
                # inventado. Regressão real: "FORTE" numa conclusão de mudança
                # estrutural usando só indice_sazonalidade (descritivo) —
                # tendencia_ajustada_sazonalidade nunca foi chamada, e chamada
                # de verdade dá p=0,17 (FRACA). 1 cobrança; se persistir,
                # rebaixa para FRACA deterministicamente (fato auditável no
                # trace, não palpite) em vez de publicar confiança sem lastro.
                # Valor em R$ na RECOMENDAÇÃO sem dizer período nem recorte. A
                # verificação numérica não pega isto: o dígito veio de
                # ferramenta e está certo — o qualificador ao lado dele é que
                # não. Um acumulado de 13 meses lido como anual superestima
                # 8,3%; lido como mensal, treze vezes. Uma cobrança; se
                # persistir, segue com nota auditável no trace, porque o número
                # em si continua correto e bloquear custaria a investigação
                # inteira.
                if not prompts.recomendacao_declara_periodo(texto):
                    if reprovas_periodo < 1:
                        reprovas_periodo += 1
                        trace.add("erro", {"motivo": "valor em R$ na RECOMENDAÇÃO sem "
                                           "período nem recorte declarado"}, iteracao=it)
                        self._log("  🗓️  valor sem período na recomendação — cobrando")
                        msgs.append({"role": "assistant", "content": texto})
                        msgs.append({"role": "user",
                                     "content": prompts.cobrar_periodo_na_recomendacao()})
                        continue
                    trace.add("pensamento",
                              {"periodo_nao_declarado": "a RECOMENDAÇÃO cita valor em R$ "
                               "sem período/recorte mesmo após cobrança; o valor é "
                               "rastreável, o qualificador temporal não foi declarado"},
                              iteracao=it)
                    self._log("  ⚠️  período não declarado mesmo após cobrança — "
                              "registrado no trace")

                palavra = _forca_alegada(texto)
                tem_teste = bool(FERRAMENTAS_ESTATISTICAS & set(trace.ferramentas_usadas))
                if palavra in ("FORTE", "MODERADA") and not tem_teste:
                    if reprovas_sem_teste < 1:
                        reprovas_sem_teste += 1
                        trace.add("erro", {"motivo": f"FORÇA DA EVIDÊNCIA={palavra} sem "
                                           "teste estatístico chamado"}, iteracao=it)
                        self._log(f"  🧪 {palavra} sem teste estatístico — cobrando correção")
                        msgs.append({"role": "assistant", "content": texto})
                        msgs.append({"role": "user",
                                     "content": prompts.cobrar_teste_estatistico(palavra)})
                        continue
                    texto = _rebaixar_forca_para_fraca(texto, palavra)
                    trace.add("pensamento",
                              {"forca_rebaixada": f"{palavra} -> FRACA (sem teste estatístico)"},
                              iteracao=it)
                    self._log(f"  ⬇️  {palavra} rebaixado para FRACA (sem teste estatístico)")

                resposta = texto
                break
            # texto pode vir vazio/só espaço aqui — nem AÇÃO nem FATO casaram.
            # Ecoar content="" de volta ao gateway quebrou em produção: a
            # EloAgents/Bedrock rejeita com 400 "Value null at
            # messages.N.member.content" (o gateway normaliza string vazia
            # para null antes de repassar ao Bedrock). Nunca mandar content
            # vazio de volta — mesmo padrão já usado no modo nativo.
            msgs.append({"role": "assistant", "content": texto or "(resposta vazia)"})
            msgs.append({"role": "user", "content": prompts.prompt_sintese(pergunta)})
            trace.add("pensamento", "resposta sem ação nem formato final; forçando síntese",
                      iteracao=it)

        if resposta is None:
            # Limite de iterações atingido: força a síntese com o que já foi coletado.
            try:
                resposta = self._forcar_sintese(msgs, pergunta, trace)
            except Exception as e:
                resposta = self._resposta_sem_modelo(pergunta, trace, e)

        resposta = self._sanear_final(resposta)

        # A guarda numérica rodava SÓ dentro do loop. Quando as iterações se
        # esgotavam, _forcar_sintese entregava o texto direto para publicação —
        # e um número inventado ali saía sem checagem nenhuma. Buraco real,
        # alcançável com VERTICE_MAX_ITER baixo ou investigação longa: a guarda
        # mais importante do projeto tinha uma saída pelos fundos. Aqui é a
        # última porta antes de publicar, então vale para qualquer caminho.
        if not self._veio_do_fallback(resposta):
            ver_final = self._verificar(resposta, trace, pergunta)
            if not ver_final["ok"]:
                trace.add("erro", {"motivo": "números não rastreáveis na síntese final",
                                   "verificacao": ver_final})
                self._log("  🚫 síntese final com número sem ferramenta: "
                          f"{', '.join(ver_final['suspeitos'][:5])}")
                resposta = self._fallback_numeros(pergunta, trace, ver_final)

        if not validar_formato_final(resposta)["valido"]:
            # O modelo pode ignorar a ordem de sintetizar e devolver outra AÇÃO.
            # Nunca devolvemos isso como resposta: cai no fallback auditável.
            resposta = self._fallback_formato(pergunta, trace, resposta)
        trace.add("resposta_final", resposta)
        trace.encerrar(resposta)

        # Mantém a conversa entre perguntas, com os papéis etiquetados.
        self.historico += [
            {"role": "user", "content": f"{prompts.ROTULO_PERGUNTA} {pergunta}"},
            {"role": "assistant", "content": resposta},
        ]
        return trace

    # -- degradação sem modelo -------------------------------------------------
    def _resposta_sem_modelo(self, pergunta: str, trace: Trace, erro: Exception) -> str:
        """Resposta montada só com o que o motor já apurou, quando o modelo não
        está disponível.

        A arquitetura separa quem calcula de quem redige: o Python calcula, o
        modelo redige. Quando só o redator cai, os números continuam corretos e
        completos — devolvê-los sem prosa é melhor do que devolver um erro de
        gateway para quem perguntou. Todo valor aqui vem de resultado de
        ferramenta; nada é recalculado nem interpretado.
        """
        msg_erro = f"{type(erro).__name__}: {erro}"
        trace.add("erro", {"motivo": "modelo de linguagem indisponível",
                           "detalhe": msg_erro,
                           "acao": "resposta montada com os resultados determinísticos"},
                  status=TOOL_CALLED_ERROR)
        self._log(f"  ⚠️  modelo indisponível ({msg_erro[:90]}) — respondendo só com o motor")

        observacoes = [p for p in trace.passos
                       if p.tipo == "observacao" and p.origem != ORIGEM_SEMENTE]
        alvo = observacoes[-1] if observacoes else next(
            (p for p in trace.passos if p.tipo == "observacao"), None)

        if alvo is None:
            fato = "nenhuma ferramenta chegou a ser executada nesta consulta."
        else:
            # Os parâmetros ficam no passo "acao"; a observação guarda o resultado.
            acao = next((p for p in reversed(trace.passos)
                         if p.tipo == "acao" and p.ferramenta == alvo.ferramenta
                         and p.indice < alvo.indice), None)
            params = (acao.parametros if acao else None) or {}
            fato = (f"{alvo.ferramenta}"
                    f"({json.dumps(params, ensure_ascii=False)}) devolveu: "
                    f"{_resumir_para_leitura(alvo.conteudo)}")

        if _erro_de_cota(erro):
            espera = _espera_sugerida(msg_erro)
            quando = f"Aguarde {espera} e repita" if espera else "Espere um minuto e repita"
            inferencia = (f"a leitura interpretativa não pôde ser redigida porque a COTA DE "
                          f"TOKENS da chave se esgotou, não porque o serviço caiu "
                          f"({_erro_curto(msg_erro)}). Os números acima são do motor "
                          f"determinístico e não dependem de cota nenhuma.")
            recomendacao = (f"{quando} a mesma pergunta — o texto muda, os números não. Se "
                            f"repetir, a cota é por minuto na camada gratuita: espaçar as "
                            f"perguntas resolve, e uma chave de plano pago ou de outro "
                            f"provedor elimina o limite.")
        else:
            inferencia = (f"a leitura interpretativa não pôde ser redigida — o modelo de "
                          f"linguagem não respondeu ({_erro_curto(msg_erro)}). Os números "
                          f"acima são do motor determinístico e não dependem dele.")
            recomendacao = ("refaça a pergunta quando o gateway voltar para obter a leitura "
                            "executiva; os números não vão mudar. As telas de relatório, "
                            "auditoria e política seguem funcionando normalmente.")

        return (f"FATO: {fato}\n"
                f"INFERÊNCIA: {inferencia}\n"
                f"RECOMENDAÇÃO: {recomendacao}\n"
                f"FORÇA DA EVIDÊNCIA: FRACA")

    def _forcar_sintese(self, msgs: list[dict], pergunta: str, trace: Trace) -> str:
        """Pede a síntese final. Tenta duas vezes: a segunda com instrução dura."""
        tentativas = [
            prompts.prompt_sintese(pergunta),
            (f"{prompts.ROTULO_SISTEMA} Sua última resposta NÃO estava no formato exigido. "
             f"Responda AGORA apenas com as quatro linhas FATO:, INFERÊNCIA:, RECOMENDAÇÃO: "
             f"e FORÇA DA EVIDÊNCIA:. Não escreva AÇÃO, não chame ferramentas, não escreva "
             f"mais nada."),
        ]
        resposta = ""
        for i, instrucao in enumerate(tentativas):
            msgs.append({"role": "user", "content": instrucao})
            trace.add("pensamento", f"forçando síntese final (tentativa {i + 1})")
            msg = self.llm.completar(msgs, self.modelo_sintese)
            resposta = (getattr(msg, "content", None) or "").strip()
            if validar_formato_final(self._sanear_final(resposta))["valido"]:
                return resposta
            msgs.append({"role": "assistant", "content": resposta or "(resposta vazia)"})
        return resposta

    @staticmethod
    def _ferramentas_citadas_nao_chamadas(texto: str, trace: Trace) -> list[str]:
        """Nomes de ferramentas do registro mencionados no texto e nunca executados."""
        usadas = set(trace.ferramentas_usadas)
        achadas = []
        for nome in REGISTRO:
            if nome in usadas:
                continue
            if re.search(rf"\b{re.escape(nome)}\b", texto or ""):
                achadas.append(nome)
        return achadas

    def _verificar(self, texto: str, trace: Trace, pergunta: str) -> dict:
        """Confronta os números da resposta com os das observações de ferramenta.

        Número que o modelo DIGITOU como parâmetro não vira número apurado só
        porque a ferramenta o devolveu de volta. `classificar_evidencia` ecoa
        p_valor e n no resultado, e foi por aí que um p-valor inventado virou
        evidência rastreável duas vezes: o modelo chamou
        classificar_evidencia(p_valor=0,0001) sem nenhum teste ter produzido
        esse valor, a ferramenta devolveu {"forca": "FORTE", "p_valor": 0,0001},
        e a verificação aprovou — o número existia numa observação.

        Por isso a subtração é por chamada: o que entrou como argumento daquela
        chamada sai do conjunto DELA. Se outra ferramenta calculou o mesmo valor
        de verdade, ele continua rastreável pela observação dessa outra.
        """
        conhecidos: set[float] = set()
        for p in trace.passos:
            if p.tipo != "observacao":
                continue
            do_resultado = coletar_numeros(p.conteudo)
            conhecidos |= do_resultado - coletar_numeros(p.parametros or {})
        return verificar_numeros(texto, conhecidos, pergunta)

    @staticmethod
    def _veio_do_fallback(resposta: str) -> bool:
        """Textos que o próprio sistema montou já são rastreáveis por construção
        (vêm do trace) e não devem ser reverificados — reverificar levaria o
        fallback a acusar a si mesmo."""
        marcas = ("bloqueada por falha de rastreabilidade",
                  "não foi possível sintetizar",
                  "a leitura interpretativa não pôde ser redigida")
        return any(m in (resposta or "") for m in marcas)

    def _fallback_numeros(self, pergunta: str, trace: Trace, ver: dict) -> str:
        """Resposta quando o modelo insiste em números que não vieram de ferramenta.

        Não publicamos os números suspeitos como se fossem apuração: o valor do
        projeto está justamente em não fazer isso.
        """
        usadas = ", ".join(dict.fromkeys(trace.ferramentas_usadas)) or "nenhuma"
        trace.add("erro", {"motivo": "resposta bloqueada: números não rastreáveis",
                           "verificacao": ver})
        return (
            f"FATO: a investigação chamou as ferramentas ({usadas}), mas a resposta "
            f"produzida pelo modelo continha números que NÃO apareceram em nenhum "
            f"resultado de ferramenta: {', '.join(ver['suspeitos'][:8])}.\n"
            f"INFERÊNCIA: esses valores foram calculados pelo próprio modelo, o que este "
            f"sistema não aceita — todo número precisa vir do motor determinístico. "
            f"Nenhuma conclusão é apresentada, para não publicar número não apurado.\n"
            f"RECOMENDAÇÃO: reformule a pergunta de forma mais específica ou consulte o "
            f"trace {trace.id}, que contém os resultados reais das ferramentas já "
            f"executadas. Se a pergunta exige um cálculo que nenhuma ferramenta faz, "
            f"a ferramenta precisa ser implementada no motor — não estimada pelo modelo.\n"
            f"FORÇA DA EVIDÊNCIA: FRACA — resposta bloqueada por falha de rastreabilidade "
            f"numérica, não por falta de dado."
        )

    def _fallback_formato(self, pergunta: str, trace: Trace,
                          rejeitada: str = "") -> str:
        """Resposta de último recurso quando o modelo não produz o formato final.

        Não inventa conclusão: declara o que foi apurado e que a síntese falhou.
        Mantém as quatro seções para não quebrar quem consome a saída.
        """
        usadas = ", ".join(dict.fromkeys(trace.ferramentas_usadas)) or "nenhuma"
        trace.add("erro", {
            "motivo": "modelo não produziu o formato final; usando fallback auditável",
            "resposta_rejeitada": rejeitada,
            "validacao": validar_formato_final(rejeitada or ""),
        })
        return (
            f"FATO: a investigação executou {len(trace.ferramentas_usadas)} chamada(s) de "
            f"ferramenta ({usadas}); os números apurados estão no trace {trace.id}.\n"
            f"INFERÊNCIA: não foi possível sintetizar uma conclusão — o modelo não devolveu "
            f"o formato exigido dentro do limite de iterações. Nenhuma conclusão é afirmada "
            f"aqui para não inventar resultado.\n"
            f"RECOMENDAÇÃO: reexecutar a pergunta \"{pergunta}\" de forma mais específica, "
            f"ou inspecionar o trace {trace.id} para ler diretamente os resultados das "
            f"ferramentas já executadas.\n"
            f"FORÇA DA EVIDÊNCIA: FRACA — falha de síntese do modelo, não de dado. "
            f"Os resultados de ferramenta no trace permanecem válidos."
        )

    @staticmethod
    def _sanear_final(texto: str) -> str:
        """Corta o preâmbulo antes de FATO e normaliza os cabeçalhos das seções."""
        if not texto:
            return texto
        m = RE_FINAL.search(texto)
        corpo = texto[m.start():] if m else texto
        return normalizar_formato_final(corpo)


# O prompt exige exatamente uma destas três palavras em FORÇA DA EVIDÊNCIA — não
# "Alta"/"Baixa"/"Confiável" etc. Em produção o modelo escreveu "Alta" mesmo
# sem ter rodado nenhum teste estatístico que sustentasse essa palavra.
RE_VOCAB_EVIDENCIA = re.compile(r"\b(FORTE|MODERADA|FRACA)\b", re.IGNORECASE)

# Ferramentas que produzem um critério objetivo de força (p-valor/R²/n). FORTE
# ou MODERADA só fazem sentido apoiadas em uma delas — indice_sazonalidade,
# por exemplo, é descritivo (um índice), não um teste de significância, e não
# entra aqui. Em produção o modelo rotulou "FORTE" uma conclusão de mudança
# estrutural usando só indice_sazonalidade, sem nunca chamar
# tendencia_ajustada_sazonalidade — que, chamada de verdade, dá p=0,17 (FRACA).
FERRAMENTAS_ESTATISTICAS = frozenset({
    "teste_t_welch", "anova_um_fator", "regressao_linear_multipla",
    "qui_quadrado_independencia", "classificar_evidencia",
    "tendencia_ajustada_sazonalidade",
})


def _corpo_da_secao(resposta: str, nome: str, pos: dict[str, int | None]) -> str:
    """Texto de uma seção: do fim do cabeçalho até a próxima seção (ou o fim)."""
    if pos.get(nome) is None:
        return ""
    inicio = RE_SECAO[nome].search(resposta).end()
    fim = len(resposta)
    for outro in RE_SECAO:
        m = RE_SECAO[outro].search(resposta, inicio)
        if m and m.start() < fim:
            fim = m.start()
    return resposta[inicio:fim]


def _forca_alegada(texto: str) -> str | None:
    """Primeira palavra do vocabulário fechado (FORTE/MODERADA/FRACA) dentro da
    seção FORÇA DA EVIDÊNCIA, em maiúsculas — ou None se a seção não existe ou
    não usa o vocabulário certo (esse 2º caso já é pego por outro guardrail)."""
    pos = {nome: (m.start() if (m := RE_SECAO[nome].search(texto)) else None)
           for nome in RE_SECAO}
    corpo = _corpo_da_secao(texto, "FORÇA DA EVIDÊNCIA", pos)
    m = RE_VOCAB_EVIDENCIA.search(corpo)
    return m.group(1).upper() if m else None


def _rebaixar_forca_para_fraca(texto: str, palavra_original: str) -> str:
    """Corrige FORTE/MODERADA -> FRACA quando nenhum teste estatístico foi
    chamado. Não é palpite: "nenhuma ferramenta estatística no trace" é fato
    objetivo, então a correção é segura de aplicar sem mais um turno do
    modelo — só anexa uma nota, auditável, do porquê."""
    pos = {nome: (m.start() if (m := RE_SECAO[nome].search(texto)) else None)
           for nome in RE_SECAO}
    corpo = _corpo_da_secao(texto, "FORÇA DA EVIDÊNCIA", pos)
    m = RE_VOCAB_EVIDENCIA.search(corpo)
    if pos.get("FORÇA DA EVIDÊNCIA") is None or not m:
        return texto
    inicio_corpo = RE_SECAO["FORÇA DA EVIDÊNCIA"].search(texto).end()
    nota = (f" [rebaixado automaticamente de {palavra_original} para FRACA: "
            f"nenhum teste estatístico foi executado nesta investigação — a "
            f"classificação exige um teste real (p-valor/R²/n), não leitura "
            f"qualitativa de tabela ou índice descritivo.]")
    novo_corpo = corpo[:m.start()] + "FRACA" + corpo[m.end():] + nota
    return texto[:inicio_corpo] + novo_corpo + texto[inicio_corpo + len(corpo):]


RE_PALAVRA_INICIAL = re.compile(r"^[\s*_`]*([^\s.,;:!?()]+)")


def _palavra_alegada_fora_do_vocabulario(texto: str) -> str | None:
    """Primeira palavra da seção FORÇA DA EVIDÊNCIA, qualquer que seja —
    usado só para a nota auditável quando ela está fora do vocabulário
    fechado (senão _forca_alegada já cobriria o caso)."""
    pos = {nome: (m.start() if (m := RE_SECAO[nome].search(texto)) else None)
           for nome in RE_SECAO}
    if pos.get("FORÇA DA EVIDÊNCIA") is None:
        return None
    corpo = _corpo_da_secao(texto, "FORÇA DA EVIDÊNCIA", pos)
    m = RE_PALAVRA_INICIAL.match(corpo)
    return m.group(1) if m else None


INTENSIFICADORES = {"muito", "bem", "bastante", "pouco", "extremamente",
                    "razoavelmente", "relativamente", "super"}
RE_PROXIMA_PALAVRA = re.compile(r"^\s*[^\s.,;:!?()]+")


def _chave_simples(palavra: str) -> str:
    import unicodedata
    sem = unicodedata.normalize("NFKD", str(palavra))
    return "".join(c for c in sem if not unicodedata.combining(c)).strip().lower()


def _forcar_vocabulario_fechado(texto: str, palavra_original: str) -> str:
    """Quando FORÇA DA EVIDÊNCIA insiste fora do vocabulário FORTE/MODERADA/
    FRACA mesmo depois da cobrança (ex.: "Alta", "NULA", "ALTA" — nenhuma das
    três palavras aparece em lugar nenhum da seção), substitui a palavra
    alegada por FRACA deterministicamente, com nota auditável.

    Regressão real observada em produção via API web: "Alta" e "ALTA"
    passaram direto como resposta final porque o guardrail de vocabulário só
    cobrava 1x e tolerava se persistisse — sem reescrever nada. Diferente de
    _rebaixar_forca_para_fraca (que só age quando a palavra JÁ é um
    substring de FORTE/MODERADA/FRACA, ex. "MUITO FORTE"), esta função lida
    com qualquer palavra fora do vocabulário inteiro. FRACA é o destino
    seguro por padrão: uma resposta que não seguiu o contrato de formato
    mesmo depois de avisada não tem lastro para reivindicar confiança alta,
    e a maioria dos casos reais (ex.: custo_assimetria_frete, que não é
    ferramenta estatística) já cairia em FRACA pela outra regra se tivesse
    usado a palavra certa."""
    pos = {nome: (m.start() if (m := RE_SECAO[nome].search(texto)) else None)
           for nome in RE_SECAO}
    if pos.get("FORÇA DA EVIDÊNCIA") is None:
        return texto
    corpo = _corpo_da_secao(texto, "FORÇA DA EVIDÊNCIA", pos)
    m_palavra = RE_PALAVRA_INICIAL.match(corpo)
    if not m_palavra:
        return texto
    inicio_corpo = RE_SECAO["FORÇA DA EVIDÊNCIA"].search(texto).end()
    nota = (f" [normalizado automaticamente de '{palavra_original}' para FRACA: "
            f"vocabulário fora do padrão FORTE/MODERADA/FRACA, mesmo após "
            f"cobrança de correção.]")
    resto = corpo[m_palavra.end(1):]
    # "Muito Baixa" -> substituir só "Muito" deixaria "FRACA Baixa". Quando a
    # palavra recusada é um intensificador, o grau vem na palavra seguinte e
    # as duas saem juntas.
    if _chave_simples(palavra_original) in INTENSIFICADORES:
        resto = RE_PROXIMA_PALAVRA.sub("", resto, count=1)
    novo_corpo = (corpo[:m_palavra.start(1)] + "FRACA" + resto + nota)
    return texto[:inicio_corpo] + novo_corpo + texto[inicio_corpo + len(corpo):]


def validar_formato_final(resposta: str) -> dict:
    """Verifica se a resposta traz as 4 seções obrigatórias, na ordem certa.

    Tolera markdown (**FATO:**, ## FATO) e acentuação ausente: o conteúdo é o que
    importa, e rejeitar por causa de asteriscos descartava respostas boas.

    `vocabulario_evidencia_ok` (FORÇA DA EVIDÊNCIA usa FORTE/MODERADA/FRACA) é
    informativo, NÃO entra em `valido`. Isso é proposital: vocabulário errado é
    cosmético — o loop dá UMA cobrança (ver `investigar()`) e aceita a resposta
    mesmo se persistir. Se contasse para `valido`, a checagem pós-loop rejeitaria
    de novo a mesma resposta que o loop acabou de decidir tolerar, empurrando
    tudo para o fallback "não foi possível sintetizar" sem necessidade — travar
    aqui por causa de uma palavra, quando o conteúdo está correto, é
    desproporcional ao problema.
    """
    resposta = resposta or ""
    pos: dict[str, int | None] = {}
    for nome in RE_SECAO:
        m = RE_SECAO[nome].search(resposta)
        pos[nome] = m.start() if m else None
    faltando = [n for n, p in pos.items() if p is None]
    ordenado = (not faltando) and list(pos.values()) == sorted(pos.values())
    # Só avalia vocabulário quando a seção existe de fato — senão "faltando" já
    # cobre o problema, e não há corpo de seção pra checar.
    vocab_ok = True
    if not faltando:
        corpo = _corpo_da_secao(resposta, "FORÇA DA EVIDÊNCIA", pos)
        vocab_ok = bool(RE_VOCAB_EVIDENCIA.search(corpo))
    return {"valido": not faltando and ordenado, "faltando": faltando,
            "na_ordem": ordenado, "posicoes": pos, "vocabulario_evidencia_ok": vocab_ok}


def normalizar_formato_final(resposta: str) -> str:
    """Reescreve os cabeçalhos na forma canônica 'SEÇÃO: ', tirando o markdown.

    A saída do agente é um contrato — quem consome (painel, apresentação) não
    deve ter de lidar com quatro grafias diferentes do mesmo cabeçalho.
    """
    if not resposta:
        return resposta
    texto = resposta
    for nome in RE_SECAO:
        texto = RE_SECAO[nome].sub(f"{nome}: ", texto)
        # Cabeçalho em linha própria (estilo markdown ## FATO) reencontra seu texto.
        texto = re.sub(rf"^{re.escape(nome)}:[ \t]*\n+(?=\S)", f"{nome}: ", texto,
                       flags=re.MULTILINE)
    # Espaços duplicados criados pela substituição, sem tocar em quebras de linha.
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    return _cortar_apos_secoes_completas(texto.strip())


def _cortar_apos_secoes_completas(texto: str) -> str:
    """Corta qualquer texto depois da 1ª passagem completa pelas 4 seções.

    Regressão observada: a síntese às vezes escreve uma seção extra (ex.: um
    2º "RECOMENDAÇÃO:") depois de "FORÇA DA EVIDÊNCIA:" — o contrato do agente
    é "sem seção extra, sem texto após a última". validar_formato_final() só
    olha a 1ª ocorrência de cada cabeçalho e não pega essa duplicata; aqui ela
    é removida antes de a resposta sair do agente.
    """
    m_forca = RE_SECAO["FORÇA DA EVIDÊNCIA"].search(texto)
    if not m_forca:
        return texto  # formato incompleto: não é este código que resolve isso
    prox = min(
        (m.start() for nome in RE_SECAO
         if (m := RE_SECAO[nome].search(texto, m_forca.end()))),
        default=None,
    )
    return texto[:prox].rstrip() if prox is not None else texto
