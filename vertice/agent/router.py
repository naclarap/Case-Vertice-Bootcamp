"""Roteamento determinístico de intenção — decide ferramenta e parâmetros em
Python, antes de o modelo opinar.

Por que existe: a pergunta "O que aconteceria se eu limitasse o desconto de
Moda no Email Marketing a 17%?" não era respondida. Três causas, todas fora do
motor de cálculo:

  1. a extração de parâmetros não conhecia CATEGORIA (só percentual, canal, mês);
  2. nada distinguia "limitar a 17%" (teto) de "aplicar 17%" (desconto do
     segmento) — são operações diferentes com resultados diferentes;
  3. a pista por palavra-chave casava "Email Marketing" com *marketing* e
     sugeria `ranking_roas_canais`, empurrando o modelo para longe.

A correção é arquitetural, não de prompt: quando a intenção é estruturada, quem
escolhe a ferramenta e preenche os parâmetros é o código. O modelo continua
dono da linguagem (interpretar pergunta aberta, explicar resultado); o Python
continua dono do número. Pergunta que este módulo não resolve com segurança sai
como PERGUNTA_COMPLEXA e segue para o ReAct, que não foi removido.

Nada aqui calcula métrica: o roteador só lê texto e devolve uma decisão.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from .. import config
from ..engine.filtros import MESES_PT, _chave

# ------------------------------------------------------------------ intenções
MARGEM_CONSOLIDADA = "MARGEM_CONSOLIDADA"
MARGEM_POR_DIMENSAO = "MARGEM_POR_DIMENSAO"
COMPARACAO_PERIODOS = "COMPARACAO_PERIODOS"
TESTE_ESTATISTICO = "TESTE_ESTATISTICO"
TETO_DESCONTO = "TETO_DESCONTO"
APLICAR_DESCONTO = "APLICAR_DESCONTO"
FRETE = "FRETE"
DEVOLUCOES = "DEVOLUCOES"
SAZONALIDADE = "SAZONALIDADE"
MARKETING = "MARKETING"
AUDITORIA = "AUDITORIA"
MARGEM_NEGATIVA = "MARGEM_NEGATIVA"
RELACAO_DESCONTO_MARGEM = "RELACAO_DESCONTO_MARGEM"
POLITICA_ALCADA = "POLITICA_ALCADA"
VIOLACAO_POLITICA = "VIOLACAO_POLITICA"
VALIDACAO_MOTIVOS = "VALIDACAO_MOTIVOS"
COERENCIA_PRAZO = "COERENCIA_PRAZO"
FRETE_PANORAMA = "FRETE_PANORAMA"
CUSTO_DE_NAO_AGIR = "CUSTO_DE_NAO_AGIR"
REAJUSTE_PRECO = "REAJUSTE_PRECO"
LIMITE_DE_DADOS = "LIMITE_DE_DADOS"
PERDA_POS_PEDIDO = "PERDA_POS_PEDIDO"
PENDENCIAS = "PENDENCIAS"
FRETE_REGRA_LIMIAR = "FRETE_REGRA_LIMIAR"
KPI_DE_ACEITE = "KPI_DE_ACEITE"
CASO_BASE = "CASO_BASE"
PERGUNTA_COMPLEXA = "PERGUNTA_COMPLEXA"

# Origem da decisão — o trace precisa distinguir quem escolheu a ferramenta.
ORIGEM_ROTEADOR = "roteador_deterministico"
ORIGEM_LLM = "llm_react"
ORIGEM_SEMENTE = "pre_semeadura"   # retrato consolidado, carregado antes do 1º turno

# Estado da execução da ferramenta. "não retornou" era ambíguo demais: não dava
# para saber se a ferramenta nem foi chamada, se quebrou, ou se rodou e o
# recorte estava vazio — e a resposta final dizia a mesma coisa nos três casos.
TOOL_NOT_CALLED = "TOOL_NOT_CALLED"
TOOL_CALLED_SUCCESS = "TOOL_CALLED_SUCCESS"
TOOL_CALLED_ERROR = "TOOL_CALLED_ERROR"
TOOL_RESULT_EMPTY = "TOOL_RESULT_EMPTY"
INVALID_PARAMETERS = "INVALID_PARAMETERS"


@dataclass
class Roteamento:
    """Decisão explícita e inspecionável — não um texto para regex interpretar."""

    intencao: str
    ferramenta: str | None = None
    parametros: dict[str, Any] = field(default_factory=dict)
    origem: str = ORIGEM_ROTEADOR
    confianca: float = 0.0
    faltando: list[str] = field(default_factory=list)
    motivo: str = ""

    @property
    def determinado(self) -> bool:
        """Há ferramenta e parâmetros suficientes para executar já."""
        return bool(self.ferramenta) and not self.faltando

    def to_dict(self) -> dict:
        return {
            "intencao": self.intencao,
            "ferramenta": self.ferramenta,
            "parametros": self.parametros,
            "origem": self.origem,
            "confianca": round(self.confianca, 2),
            "faltando": self.faltando,
            "motivo": self.motivo,
        }


# --------------------------------------------------------- valores do domínio
@lru_cache(maxsize=1)
def valores_do_dominio() -> dict[str, list[str]]:
    """Canais e categorias lidos DA BASE, não de lista fixa no código: canal
    novo no Data Room passa a ser reconhecido sem editar este arquivo."""
    try:
        from ..data import carregar_vendas
        df = carregar_vendas()
        return {
            "canal": sorted(df["canal"].dropna().astype(str).unique()),
            "categoria": sorted(df["categoria"].dropna().astype(str).unique()),
        }
    except Exception:
        return {"canal": [], "categoria": []}   # extração é best-effort


def _bate(texto: str, gatilho: str) -> bool:
    """Gatilho curto casa só como palavra inteira.

    Substring pura roteou "Podemos automatizar a classificação dos tickets?"
    para o assunto CAC: "classificacao" contém "cac". Gatilho longo continua por
    substring — é o que permite "limit" pegar limitar/limitasse/limite.
    """
    if len(gatilho) <= 4 and gatilho.strip() == gatilho:
        return re.search(rf"(?<![\w]){re.escape(gatilho)}(?![\w])", texto) is not None
    return gatilho in texto


def _achar_valor(texto_norm: str, valores: list[str]) -> tuple[str | None, str | None]:
    """Procura um valor do domínio no texto já normalizado (sem acento, minúsculo).

    Casa com limite de palavra para 'moda' não acertar 'modalidade'. O mais
    LONGO vence: 'Email Marketing' antes de um eventual canal 'Email'.
    Devolve (valor canônico, trecho casado) — o trecho é removido do texto antes
    da detecção de intenção, senão 'Email Marketing' dispara a pista de
    marketing e a pergunta vira ranking de ROAS.
    """
    melhor, trecho = None, None
    for v in sorted(valores, key=len, reverse=True):
        alvo = _chave(v)
        if re.search(rf"(?<![\w]){re.escape(alvo)}(?![\w])", texto_norm):
            melhor, trecho = v, alvo
            break
    return melhor, trecho


# ------------------------------------------------------------------ intenções
# Um teto LIMITA o que passa do valor; aplicar DEFINE o valor do segmento
# inteiro. Confundir os dois dá número errado, não só ferramenta errada.
# Radicais, não formas exatas: a pessoa escreve "capasse", "travasse",
# "restringisse" — conjugar tudo à mão foi o que deixou metade dos verbos do
# enunciado fora, com a pergunta caindo em aplicação e devolvendo o número
# errado (aplicar 17% em todo o segmento ≠ limitar a 17% quem passa disso).
GATILHOS_TETO = (
    "limit", "teto", "maximo", "no maximo", "nao ultrapassar", "nao passar de",
    "nao deixar o desconto passar", "nao exceder", "capar", "capass", "capand",
    "restring", "desconto maximo", "ate o maximo", "travar", "travass", "travand",
    "limite", "passar de", "nao permit", "desconto acima de", "acima de",
)
GATILHOS_APLICAR = (
    "aplicar", "aplicasse", "aplicando", "dar ", "desse ", "oferecer",
    "oferecesse", "conceder", "concedesse", "colocar o desconto",
    "simular desconto", "simule um desconto", "campanha de", "praticar",
    "subir o desconto para", "passar a dar",
)
GATILHOS_COMPLEXA = (
    "por que", "porque", "por quais", "qual o motivo", "o que deveriamos",
    "o que fazer", "quais acoes", "que acoes", "como melhorar", "como resolver",
    "o que poderia ser feito", "o que pode ser feito", "diagnostic",
    "recomend", "plano de acao", "e o que",
)


# Perguntas cujo CAMPO existe na base mas não sustenta a resposta — o caso mais
# perigoso do case, porque o modelo encontra `clientes.ltv_acumulado` ou
# `marketing.cac` e responde com o número achado. Aqui elas saem do caminho do
# ReAct e vão para uma ferramenta que MEDE a cobertura do dado e devolve o
# veredito com a medida junto. Vem antes de qualquer outra regra, inclusive da
# detecção de pergunta aberta: "Por que não podemos afirmar as verdadeiras
# causas das devoluções?" é exatamente uma pergunta de cobertura.
GATILHOS_LIMITE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cac", ("cac", "custo de aquisicao", "custo por aquisicao")),
    ("ltv", ("ltv", "lifetime value", "valor vitalicio", "valor do tempo de vida")),
    ("churn", ("churn", "taxa de cancelamento", "evasao de clientes")),
    ("segmentos_de_clientes", ("segmento de cliente", "segmentos de cliente",
                              "melhores segmentos", "segmentacao de cliente", "rfm")),
    ("oferta_individual", ("oferta individual", "oferta personalizada",
                           "quais clientes deveriam", "que clientes deveriam",
                           "oferta por cliente")),
    ("classificacao_de_tickets", ("classificacao dos tickets", "classificar os tickets",
                                  "classificacao de tickets", "automatizar a classificacao")),
    ("causa_de_devolucao", ("verdadeiras causas", "verdadeira causa", "causas reais",
                            "causa real", "causas verdadeiras",
                            "afirmar quais sao as causas", "evidencia compativel")),
    ("previsao_de_devolucao", ("exatamente a reducao", "reducao das devolucoes depois",
                               "depois da intervencao", "meta de reducao",
                               "quanto vai cair", "quanto cairao")),
)


RE_PCT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*(?:%|por\s*cento|pontos?\s*percentuais?)")
# "limitar o desconto a 17" / "teto de 17" sem o símbolo de porcentagem
RE_PCT_SEM_SIMBOLO = re.compile(
    r"(?:a|para|de|em)\s+(\d{1,3}(?:[.,]\d+)?)\b(?!\s*(?:%|pedidos|reais|dias))")


def extrair_parametros(pergunta: str) -> dict[str, Any]:
    """Percentual, canal, categoria, mês e ano ditos LITERALMENTE na pergunta.

    Não adivinha: mês sem ano só resolve quando a base tem um único ano com
    aquele mês (a mesma regra de engine/filtros.py). Devolve também
    `_texto_sem_dominio`, usado internamente para a detecção de intenção.
    """
    texto = pergunta or ""
    norm = _chave(texto)
    achados: dict[str, Any] = {}

    dominio = valores_do_dominio()
    restante = norm
    for coluna in ("canal", "categoria"):
        valor, trecho = _achar_valor(restante, dominio[coluna])
        if valor:
            achados[coluna] = valor
            restante = restante.replace(trecho, " ")

    m = RE_PCT.search(texto)
    if m:
        achados["percentual"] = float(m.group(1).replace(",", "."))
    elif "desconto" in norm and any(g in norm for g in GATILHOS_TETO + GATILHOS_APLICAR):
        # "limitar o desconto a 17" — sem o símbolo. Só nesse contexto: fora
        # dele, "top 5" ou "últimos 7 dias" viraria percentual.
        m2 = RE_PCT_SEM_SIMBOLO.search(norm)
        if m2:
            achados["percentual"] = float(m2.group(1).replace(",", "."))

    m_mes = re.search(r"\b(" + "|".join(MESES_PT) + r")\b", restante)
    if m_mes:
        num = MESES_PT[m_mes.group(1)]
        m_ano = re.search(r"\b(20\d{2})\b", texto)
        if m_ano:
            achados["mes"] = f"{m_ano.group(1)}-{num:02d}"
            achados["ano"] = m_ano.group(1)
        else:
            try:
                from ..data import carregar_vendas
                meses = sorted(carregar_vendas()["mes"].astype(str).unique())
            except Exception:
                meses = []
            candidatos = [x for x in meses if x.endswith(f"-{num:02d}")]
            if len(candidatos) == 1:      # ambíguo (ex: janeiro) fica de fora
                achados["mes"] = candidatos[0]
    elif (m_ano := re.search(r"\b(20\d{2})\b", texto)):
        achados["ano"] = m_ano.group(1)

    achados.update(_periodos_ditos(norm, texto))
    achados.update(_recorte_dito(norm))
    achados["_texto_sem_dominio"] = restante
    return achados


# --------------------------------------------------------------- recorte dito
# "fora de novembro", "no ano todo", "com os devolvidos": o recorte é parte da
# pergunta tanto quanto o percentual. Enquanto não era extraído, "teto de 20%
# FORA DE NOVEMBRO" produzia a mesma chamada que "teto de 20%" — a resposta saía
# formatada, com número rastreável, e contradizia a pergunta sem nenhum sinal na
# tela. Número silenciosamente igual quando deveria mudar é pior que número
# errado, porque não há o que conferir.
RE_EXCLUIR_MES = re.compile(
    r"\b(?:fora|exceto|excluindo|sem|desconsiderando|tirando|descontando)\s+"
    r"(?:de\s+|o\s+mes\s+de\s+|os\s+meses\s+de\s+)?"
    r"(" + "|".join(MESES_PT) + r")\b")

GATILHOS_ANO_TODO = ("ano todo", "ano inteiro", "todos os meses",
                     "sem excluir novembro", "sem tirar novembro")

# Inclusão de um mês que o padrão exclui. O radical (`inclu`) cobre incluindo,
# incluir, incluirmos e incluíssemos: conjugar à mão deixaria metade das formas
# de fora, que foi exatamente o que aconteceu com os verbos de teto antes.
RE_INCLUIR_MES = re.compile(
    r"\b(?:inclu\w*|considerando|inclusive|contando\s+com|com)\s+"
    r"(?:o\s+|os\s+|o\s+mes\s+de\s+)?"
    r"(" + "|".join(MESES_PT) + r")\b")
GATILHOS_BASE_INTEIRA = ("base inteira", "toda a base", "base toda", "13 meses",
                         "treze meses", "periodo inteiro", "toda a janela",
                         "sem recorte", "base completa")
GATILHOS_COM_DEVOLVIDOS = ("com os devolvidos", "incluindo os devolvidos",
                           "incluindo devolvidos", "com devolvidos",
                           "inclusive os devolvidos")
GATILHOS_SO_MANTIDOS = ("pedidos mantidos", "so os mantidos", "sem os devolvidos",
                        "excluindo os devolvidos", "sem devolvidos",
                        "desconsiderando os devolvidos")


def _recorte_dito(norm: str) -> dict[str, Any]:
    """Recorte que a pergunta declara. Só o que está escrito, nada inferido."""
    achados: dict[str, Any] = {}

    if any(g in norm for g in GATILHOS_BASE_INTEIRA):
        achados["convencao"] = "diagnostico"
    excluir = [MESES_PT[m.group(1)] for m in RE_EXCLUIR_MES.finditer(norm)]
    incluir = [MESES_PT[m.group(1)] for m in RE_INCLUIR_MES.finditer(norm)]
    if excluir:
        achados["excluir_meses"] = str(sorted(set(excluir)))
    elif incluir or any(g in norm for g in GATILHOS_ANO_TODO):
        # Pedir explicitamente para INCLUIR o mês que o padrão exclui equivale a
        # não excluir nenhum. Não se inventa um recorte novo: só se desliga o
        # que a convenção padrão aplicaria.
        achados["excluir_meses"] = "[]"

    if any(g in norm for g in GATILHOS_COM_DEVOLVIDOS):
        achados["excluir_devolvidos"] = "false"
    elif any(g in norm for g in GATILHOS_SO_MANTIDOS):
        achados["excluir_devolvidos"] = "true"
    return achados


# Parâmetros de recorte que o roteador repassa à ferramenta quando, e somente
# quando, a pergunta os declara. O que a pergunta não diz fica a cargo do padrão
# DECLARADO da ferramenta, que volta no campo `recorte_aplicado` do resultado —
# nunca escondido.
PARAMS_RECORTE = ("convencao", "ano", "excluir_meses", "excluir_devolvidos")


def _com_recorte(params: dict[str, Any], achados: dict[str, Any],
                 ferramenta: str) -> dict[str, Any]:
    """Acrescenta a params o recorte dito na pergunta, se a ferramenta o aceita."""
    from ..engine.registry import REGISTRO

    aceitos = REGISTRO[ferramenta].parametros if ferramenta in REGISTRO else {}
    for chave in PARAMS_RECORTE:
        if chave in achados and chave in aceitos:
            params[chave] = achados[chave]
    return params


# "primeiro semestre de 2023" é um período dito literalmente, tanto quanto
# "2023-01:2023-06" — só que escrito como a pessoa fala. Sem isto, "compare o
# segundo semestre com o primeiro" chegava em comparar_periodos sem nenhum
# parâmetro e a ferramenta nem era chamada.
_ORDINAIS = {"primeiro": 1, "1o": 1, "1º": 1, "segundo": 2, "2o": 2, "2º": 2,
             "terceiro": 3, "3o": 3, "3º": 3, "quarto": 4, "4o": 4, "4º": 4}
RE_INTERVALO = re.compile(r"(20\d{2}-\d{2})\s*(?:a|ate|:|vs|versus|x)\s*(20\d{2}-\d{2})")


def _anos_da_base() -> list[str]:
    try:
        from ..data import carregar_vendas
        return sorted(carregar_vendas()["ano"].astype(str).unique())
    except Exception:
        return []


def _periodos_ditos(norm: str, original: str) -> dict:
    """periodo_a/periodo_b a partir de semestre, trimestre ou AAAA-MM explícito.

    Devolve sempre o mais ANTIGO como periodo_a: a ferramenta decompõe a
    variação de A para B, e ler o passado como base é o que torna o sinal da
    variação interpretável.
    """
    anos = _anos_da_base()
    ano_padrao = anos[0] if len(anos) == 1 else (anos[-1] if anos else None)
    faixas: list[str] = []

    # A unidade aparece uma vez e vale para todos os ordinais da frase: em
    # "o segundo semestre de 2023 com o primeiro", o segundo ordinal está
    # elíptico — exigir a palavra "semestre" grudada nele achava um período só,
    # e com um período só a comparação não acontece.
    unidade = "semestre" if "semestre" in norm else ("trimestre" if "trimestre" in norm else None)
    if unidade:
        m_ano = re.search(r"\b(20\d{2})\b", norm)
        ano = m_ano.group(1) if m_ano else ano_padrao
        vistos: list[int] = []
        for m in re.finditer(r"\b(" + "|".join(_ORDINAIS) + r")\b", norm):
            n = _ORDINAIS[m.group(1)]
            if ano and n not in vistos:
                vistos.append(n)
                if unidade == "semestre" and n <= 2:
                    ini, fim = (1, 6) if n == 1 else (7, 12)
                elif unidade == "trimestre" and n <= 4:
                    ini, fim = 3 * n - 2, 3 * n
                else:
                    continue
                faixas.append(f"{ano}-{ini:02d}:{ano}-{fim:02d}")

    if len(faixas) < 2:
        m = RE_INTERVALO.search(norm)
        if m:
            faixas = [m.group(1), m.group(2)]
        else:
            soltos = re.findall(r"\b(20\d{2}-\d{2})\b", original)
            if len(soltos) >= 2:
                faixas = soltos[:2]

    if len(faixas) < 2:
        return {}
    a, b = sorted(faixas[:2])
    return {"periodo_a": a, "periodo_b": b}


# (intenção, gatilhos, ferramenta). Ordem = precedência; o mais específico antes.
REGRAS: tuple[tuple[str, tuple[str, ...], str | None], ...] = (
    (AUDITORIA, ("auditoria", "qualidade dos dados", "qualidade do dado",
                 "integridade", "duplicat", "valores nulos", "campos vazios",
                 "completude"), "relatorio_auditoria_dados"),
    # Governança vem antes do simulador: "Quantos pedidos estão acima do teto?"
    # tem a palavra "teto" e ia parar em simular_teto_desconto, que responde
    # outra coisa (o efeito de impor um teto, não a contagem de quem o excede).
    (POLITICA_ALCADA, ("dentro da politica", "fora da politica", "quem precisa aprovar",
                       "quem aprova", "quem deve aprovar", "alcada", "aprovacao do gerente",
                       "aprovacao do cmo", "aprovacao do diretor", "cmo e cfo", "cmo e do cfo",
                       "exige justificativa", "justificativa de excecao",
                       "quando e necessaria aprovacao", "esta dentro da"),
     "consultar_politica_desconto"),
    (VIOLACAO_POLITICA, ("acima do teto", "acima do limite", "acima do maximo",
                         "limite permitido", "excecoes a politica", "excecao a politica",
                         "exceções a politica", "contornar a politica", "burlar",
                         "violacao da politica", "desrespeit"),
     "pedidos_acima_do_teto"),
    (REAJUSTE_PRECO, ("reajuste", "aumento de preco", "aumentar o preco",
                      "subir o preco", "repasse de preco", "aumento no preco"),
     "simular_reajuste_preco"),
    # O caso-base vem antes do simulador: "quanto vale o plano?" não é a
    # simulação de uma alavanca, é a soma das duas com a separação entre o que
    # é interno e o que depende do parceiro.
    (CASO_BASE, ("caso-base", "caso base", "quanto vale o plano", "valor do plano",
                 "total do plano", "se o parceiro recusar", "sob controle interno",
                 "depende de terceiros", "quanto sobra se"), "caso_base_do_plano"),
    # KPI de aceite antes do simulador, porque a pergunta cita o teto mas pede
    # outra coisa: a régua de acompanhamento e a regra de parada do piloto.
    (KPI_DE_ACEITE, ("kpi de aceite", "kpi do teto", "regra de parada", "quando parar",
                     "quando interromper", "ponto de equilibrio", "ponto de equilibrio",
                     "quantos pedidos podemos perder", "quanto podemos perder",
                     "antes de o ganho zerar", "antes do ganho zerar",
                     "como medir o teto", "meta do teto"), "kpis_do_teto"),
    (TETO_DESCONTO, GATILHOS_TETO, "simular_teto_desconto"),
    (APLICAR_DESCONTO, GATILHOS_APLICAR, "simular_desconto_em_segmento"),
    # "Quanto gastamos com frete?" é panorama (gasto e média por canal);
    # custo_assimetria_frete responde outra pergunta — quanto do frete do
    # Marketplace seria evitável — e devolveria o número de um canal só.
    # A REGRA vem antes do panorama e do contrafactual. "Quanto ganhamos se o
    # Marketplace seguir a mesma regra dos demais?" pede a regra objetiva
    # (frete só abaixo de R$ 250), que é a alavanca negociável com o parceiro.
    # Os gatilhos "mesma regra dos demais/outros" apontavam para
    # custo_assimetria_frete, que responde outra pergunta — quanto do frete
    # seria evitável por contrafactual estatístico — e devolve outro número.
    (FRETE_REGRA_LIMIAR, ("mesma regra dos demais", "mesma regra dos outros",
                          "mesma regra de frete", "seguir a regra", "seguisse a regra",
                          "adotar a regra", "adotasse a regra", "regra dos demais canais",
                          "regra de r$ 250", "regra de 250", "frete so abaixo de",
                          "frete apenas abaixo de", "equalizar a politica de frete",
                          "equalizar o frete"), "regra_frete_por_limiar"),
    (FRETE_PANORAMA, ("quanto gastamos com frete", "gasto com frete", "gastamos com frete",
                      "custo total de frete", "total de frete", "frete medio",
                      "frete por pedido", "custo de frete", "custo do frete",
                      "politica de frete", "frete por canal"),
     "politica_frete_por_canal"),
    (FRETE, ("frete", "economizariamos"), "custo_assimetria_frete"),
    # Validação do motivo declarado vem antes de impacto_devolucoes: "os motivos
    # são confiáveis?" não se responde com taxa de devolução.
    (COERENCIA_PRAZO, ("atraso", "dentro do prazo", "prazo de entrega",
                       "tempo de entrega"), "coerencia_motivo_entrega"),
    (VALIDACAO_MOTIVOS, ("motivo", "motivos", "tamanho errado", "sao confiaveis",
                         "e confiavel", "inconsistencia", "inconsistencias",
                         "coerentes com a categoria", "podem ser validad",
                         "precisam ser revisad", "podem ser considerados confiaveis"),
     "verificar_consistencia_categorica"),
    (DEVOLUCOES, ("devoluc", "devolvid", "devolucao"), "impacto_devolucoes"),
    # Pendência antes da ponte: "quantos pedidos estão Aguardando há mais de 30
    # dias?" pede o estoque a sanear, não a ponte do ano inteiro.
    (PENDENCIAS, ("aguardando ha", "pendentes ha", "pendencia antiga",
                  "pendencias antigas", "sanear", "saneamento", "ha mais de 30 dias",
                  "parados ha"), "pendencias_antigas"),
    # Ponte do pós-pedido: o vazamento que acontece DEPOIS de a margem ser
    # calculada. Vem antes de MARGEM_CONSOLIDADA porque "qual é a margem que se
    # realiza?" caía lá e devolvia a margem CALCULADA — conceito trocado sem
    # nenhum sinal na resposta, que é a pior classe de erro deste sistema.
    (PERDA_POS_PEDIDO, ("depois do pedido", "apos o pedido", "pos-pedido", "pos pedido",
                        "margem que se realiza", "margem realizada", "se realiza",
                        "nao se realiza", "margem calculada", "cancelamento",
                        "cancelados", "cancelamentos", "pendencia", "pendencias",
                        "ponte da margem", "perda depois"), "perda_pos_pedido"),
    (SAZONALIDADE, ("sazonal", "sazonalidade", "black friday", "pico de venda",
                    "melhor mes", "pior mes", "melhores meses", "piores meses",
                    "quais meses", "que meses", "meses apresentam"),
     "indice_sazonalidade"),
    (CUSTO_DE_NAO_AGIR, ("custo de nao agir", "nao agir", "nao fizermos nada",
                         "nao fazer nada", "manter como esta", "cenarios de reducao"),
     "cenarios_reducao_desconto"),
    (MARGEM_NEGATIVA, ("margem negativa", "abaixo do piso", "piso de margem",
                       "prejuizo"), "pedidos_margem_negativa"),
    (MARKETING, ("roas", "retorno sobre investimento", "investimento em midia",
                 "verba de marketing"), "ranking_roas_canais"),
    # Antes do teste estatístico: "houve mudança significativa entre os
    # períodos?" tem "significativ" e ia para a ANOVA por canal, que compara
    # canais e não períodos.
    (COMPARACAO_PERIODOS, ("comparar", "comparacao entre", "versus", " vs ",
                           "em relacao ao mesmo", "entre os periodos",
                           "entre dois periodos", "entre os dois periodos"),
     "comparar_periodos"),
    # "O Marketplace é estatisticamente pior?" não casava com
    # "estatisticamente significativ" e ia parar no ReAct, que respondeu só com
    # a semente e disse que não havia dado por canal — havia, em duas ferramentas.
    (TESTE_ESTATISTICO, ("estatisticamente", "teste estatistico", "significancia",
                         "p-valor", "p valor", "significativ"), "anova_um_fator"),
    (MARGEM_POR_DIMENSAO, ("qual canal", "que canal", "quais canais", "que canais",
                           "pior canal", "melhor canal", "por canal", "por categoria",
                           "qual categoria", "que categoria", "quais categorias",
                           "que categorias", "ranking de canais", "ranking de categoria",
                           "menor margem", "maior margem", "quais produtos",
                           "que produtos", "quais skus", "por produto", "por sku",
                           "evolui", "evoluc", "ao longo do", "ao longo dos",
                           "mes a mes", "por mes"), "margem_por_dimensao"),
    # A relação desconto×margem vem DEPOIS do corte por dimensão: "qual
    # categoria sofre mais impacto do desconto?" pede a abertura por categoria,
    # não a tabela de faixas — que responde a versão sem dimensão da pergunta.
    # "Existe relação entre desconto e margem?" caía em PERGUNTA_COMPLEXA e o
    # modelo INVENTOU a tabela inteira de faixas — seis linhas de margem por
    # faixa, com valores que somados passavam da receita da base.
    (RELACAO_DESCONTO_MARGEM,
     ("relacao entre desconto", "desconto e a margem", "desconto e margem",
      "faixa de desconto", "faixas de desconto", "desconto afeta a margem",
      "desconto impacta a margem", "desconto compra volume",
      "desconto esta comprando", "impacto dos descontos", "impacto do desconto",
      "descontos sobre a margem", "desconto sobre a margem",
      "descontos na margem", "desconto na margem"), "tabela_faixas_desconto"),
    (MARGEM_CONSOLIDADA, ("margem consolidada", "margem total", "qual a margem",
                          "qual e a margem", "margem da operacao",
                          "margem de contribuicao", "desconto medio",
                          "desconto media", "media de desconto"), "margem_consolidada"),
)


def _dimensao_pedida(texto: str) -> str:
    for palavra, dim in (("categoria", "categoria"), ("canal", "canal"),
                         ("mes", "mes"), ("sku", "sku"), ("produto", "sku"),
                         ("pagamento", "metodo_pagamento")):
        if palavra in texto:
            return dim
    return "canal"


def rotear(pergunta: str) -> Roteamento:
    """Decide intenção, ferramenta e parâmetros a partir da pergunta.

    Devolve PERGUNTA_COMPLEXA (sem ferramenta) quando a pergunta pede
    investigação — aí quem conduz é o ReAct, que continua no lugar.
    """
    achados = extrair_parametros(pergunta)
    texto = achados.pop("_texto_sem_dominio", _chave(pergunta))
    pct = achados.get("percentual")
    canal, categoria = achados.get("canal"), achados.get("categoria")

    def _conta(gatilhos):
        return sum(1 for g in gatilhos if _bate(texto, g))

    # Cobertura de dado vem primeiro, inclusive na frente de "por que...": a
    # pergunta que o case planta ("qual é o LTV?", "quais as verdadeiras causas
    # das devoluções?") tem campo com o nome certo na base e resposta errada.
    # Deixá-la no ReAct é justamente o caminho em que o modelo acha o campo.
    for assunto, gatilhos in GATILHOS_LIMITE:
        if any(_bate(texto, g) for g in gatilhos):
            return Roteamento(
                intencao=LIMITE_DE_DADOS, ferramenta="cobertura_de_dados",
                parametros={"assunto": assunto}, confianca=0.9,
                motivo=f"pergunta depende de dado cuja cobertura precisa ser medida "
                       f"antes de responder ({assunto})")

    complexa = _conta(GATILHOS_COMPLEXA) > 0

    # Simulação com percentual explícito é estruturada mesmo dentro de uma
    # pergunta que começa com "o que aconteceria": há um número e uma operação.
    tem_teto, tem_aplicar = _conta(GATILHOS_TETO), _conta(GATILHOS_APLICAR)
    # "Quem precisa aprovar um desconto acima de 25%?" tem percentual e verbo de
    # limite, e ainda assim não é simulação: é consulta de alçada. A pergunta de
    # governança tem precedência sobre o simulador, e as regras abaixo a pegam.
    gatilhos_politica = next(g for i, g, _ in REGRAS if i == POLITICA_ALCADA)
    # KPI de aceite e caso-base citam o teto e o percentual, mas não pedem a
    # simulação: pedem a régua de acompanhamento e a soma das alavancas. Sem
    # esta checagem o atalho abaixo os capturaria antes de as REGRAS rodarem.
    gatilhos_kpi = next(g for i, g, _ in REGRAS if i == KPI_DE_ACEITE)
    gatilhos_caso = next(g for i, g, _ in REGRAS if i == CASO_BASE)
    pede_kpi = any(_bate(texto, g) for g in gatilhos_kpi)
    pede_caso = any(_bate(texto, g) for g in gatilhos_caso)

    if pct is not None and (tem_teto or tem_aplicar) and not pede_kpi and not pede_caso \
            and not any(_bate(texto, g) for g in gatilhos_politica):
        if tem_teto >= tem_aplicar:
            params = {"teto_pct": pct}
            if canal:
                params["canal"] = canal
            if categoria:
                params["categoria"] = categoria
            # O recorte DITO na pergunta vira parâmetro; o que ela não diz fica
            # com o padrão declarado da ferramenta, que volta em
            # `recorte_aplicado`. Nunca em silêncio, nos dois casos.
            params = _com_recorte(params, achados, "simular_teto_desconto")
            return Roteamento(
                intencao=TETO_DESCONTO, ferramenta="simular_teto_desconto",
                parametros=params, confianca=0.95,
                motivo=(f"verbo de limite ({tem_teto} gatilho(s)) + percentual explícito"
                        + (f"; recorte dito na pergunta: "
                           f"{ {k: v for k, v in params.items() if k in PARAMS_RECORTE} }"
                           if any(k in params for k in PARAMS_RECORTE) else
                           "; sem recorte na pergunta: vale o padrão declarado da ferramenta")))
        params = {"desconto_pct": pct}
        for k, v in (("canal", canal), ("categoria", categoria), ("mes", achados.get("mes"))):
            if v:
                params[k] = v
        return Roteamento(
            intencao=APLICAR_DESCONTO, ferramenta="simular_desconto_em_segmento",
            parametros=params, confianca=0.95,
            motivo=f"verbo de aplicação ({tem_aplicar} gatilho(s)) + percentual explícito")

    # Dois períodos ditos na pergunta ("o segundo semestre com o primeiro")
    # decidem sozinhos a comparação — sem eles, "semestre" é só o recorte de uma
    # pergunta de evolução, que se responde por mês e não por comparação.
    if achados.get("periodo_a") and achados.get("periodo_b"):
        return Roteamento(
            intencao=COMPARACAO_PERIODOS, ferramenta="comparar_periodos",
            parametros={"periodo_a": achados["periodo_a"], "periodo_b": achados["periodo_b"]},
            confianca=0.9, motivo="dois períodos explícitos na pergunta")

    # Pergunta aberta ("por que...", "o que fazer...") vai para investigação.
    if complexa:
        return Roteamento(intencao=PERGUNTA_COMPLEXA, confianca=0.9,
                          origem=ORIGEM_LLM,
                          motivo="pergunta pede investigação, não uma consulta única")

    for intencao, gatilhos, ferramenta in REGRAS:
        if not any(_bate(texto, g) for g in gatilhos):
            continue
        if ferramenta is None:          # intenção reconhecida, ferramenta depende do caso
            return Roteamento(intencao=intencao, origem=ORIGEM_LLM, confianca=0.5,
                              motivo="intenção reconhecida, mas a ferramenta depende "
                                     "das variáveis da pergunta")
        params: dict[str, Any] = {}
        faltando: list[str] = []
        if ferramenta == "margem_por_dimensao":
            params["dimensao"] = _dimensao_pedida(texto)
        elif ferramenta == "custo_assimetria_frete" and canal:
            params["canal"] = canal
        elif ferramenta in ("consultar_politica_desconto", "pedidos_acima_do_teto"):
            chave = "desconto_pct" if ferramenta == "consultar_politica_desconto" else "teto_pct"
            if pct is not None:
                params[chave] = pct
            if canal:
                params["canal"] = canal
            if categoria:
                params["categoria"] = categoria
        elif ferramenta == "simular_reajuste_preco":
            if pct is None:
                faltando.append("reajuste_pct")
            else:
                params["reajuste_pct"] = pct
            for nome, valor in (("canal", canal), ("categoria", categoria)):
                if valor:
                    params[nome] = valor
        elif ferramenta == "verificar_consistencia_categorica":
            params.update({"tabela": "vendas", "coluna_a": "motivo_devolucao",
                           "coluna_b": "categoria"})
        elif ferramenta == "comparar_periodos":
            for chave in ("periodo_a", "periodo_b"):
                if achados.get(chave):
                    params[chave] = achados[chave]
                else:
                    faltando.append(chave)
        elif ferramenta in ("simular_teto_desconto", "simular_desconto_em_segmento"):
            # Sem percentual na pergunta, o simulador só roda se houver política
            # vigente para servir de padrão. Antes disso o roteador marcava a
            # decisão como determinada, a ferramenta levantava TypeError e a
            # pergunta morria ali — pior que dizer o que está faltando.
            chave = ("teto_pct" if ferramenta == "simular_teto_desconto"
                     else "desconto_pct")
            if pct is not None:
                params[chave] = pct
            else:
                from ..politica import teto_vigente_pct
                if teto_vigente_pct(canal, categoria) is None:
                    faltando.append(chave)
            for nome, valor in (("canal", canal), ("categoria", categoria)):
                if valor:
                    params[nome] = valor
        elif ferramenta == "kpis_do_teto":
            # Sem percentual na pergunta, o KPI vale para o teto recomendado —
            # que é o padrão da própria ferramenta, declarado no retorno.
            if pct is not None:
                params["teto_pct"] = pct
            else:
                from ..politica import teto_vigente_pct
                if teto_vigente_pct(canal, categoria) is None:
                    params["teto_pct"] = config.LIMIAR_DESCONTO_ALTO * 100
            for nome, valor in (("canal", canal), ("categoria", categoria)):
                if valor:
                    params[nome] = valor
        elif ferramenta == "regra_frete_por_limiar":
            if canal:
                params["canal"] = canal
        elif ferramenta == "perda_pos_pedido":
            if achados.get("ano"):
                params["ano"] = achados["ano"]
        elif ferramenta == "impacto_devolucoes":
            params["por"] = "categoria" if "categoria" in texto else "canal"
        elif ferramenta == "anova_um_fator":
            # A métrica padrão é margem porque é o assunto do case; o fator vem
            # do que a pergunta cita (um canal citado => comparação entre canais).
            params["metrica"] = "margem_contribuicao"
            params["coluna_grupo"] = ("categoria" if (categoria and not canal)
                                      or "categoria" in texto else "canal")
        params = _com_recorte(params, achados, ferramenta)
        return Roteamento(intencao=intencao, ferramenta=ferramenta, parametros=params,
                          confianca=0.8, faltando=faltando,
                          motivo=f"gatilho de {intencao.lower()}")

    # Último recurso antes do ReAct: percentual + segmento + a palavra desconto,
    # sem verbo nenhum ("o impacto na margem do segmento de um desconto de 17%
    # em Moda"). Só vale com segmento explícito — sem ele, "um desconto de 22%
    # está dentro da política?" viraria simulação em vez de consulta de alçada,
    # e as regras de política já rodaram acima.
    if pct is not None and "desconto" in texto and (canal or categoria or achados.get("mes")):
        params = {"desconto_pct": pct}
        for chave, valor in (("canal", canal), ("categoria", categoria),
                             ("mes", achados.get("mes"))):
            if valor:
                params[chave] = valor
        return Roteamento(
            intencao=APLICAR_DESCONTO, ferramenta="simular_desconto_em_segmento",
            parametros=params, confianca=0.7,
            motivo="percentual e segmento explícitos, sem verbo de limite: aplicação")

    return Roteamento(intencao=PERGUNTA_COMPLEXA, origem=ORIGEM_LLM, confianca=0.3,
                      motivo="nenhuma intenção estruturada reconhecida")


# ------------------------------------------------------------------ validação
def validar_parametros(ferramenta: str, parametros: dict) -> tuple[dict, list[str]]:
    """Normaliza e valida ANTES de executar. Devolve (parâmetros, problemas).

    Canal/categoria são conferidos contra a base (via engine/filtros), percentual
    contra a faixa 0–100. Parâmetro ausente é reportado, NUNCA inventado: sem
    canal na pergunta, o teto vale para o escopo que a ferramenta aceitar.
    """
    from ..engine.filtros import normalizar_categorico
    from ..engine.registry import REGISTRO

    problemas: list[str] = []
    if ferramenta not in REGISTRO:
        return parametros, [f"ferramenta '{ferramenta}' não existe no registro"]

    saida = dict(parametros)
    dominio = valores_do_dominio()
    for coluna in ("canal", "categoria"):
        if coluna in saida and dominio[coluna]:
            try:
                saida[coluna] = normalizar_categorico(coluna, saida[coluna], dominio[coluna])
            except ValueError as e:
                problemas.append(str(e))

    for chave, valor in list(saida.items()):
        if chave.endswith("_pct") and valor is not None:
            try:
                v = float(valor)
            except (TypeError, ValueError):
                problemas.append(f"{chave} não é número: {valor!r}")
                continue
            if not 0 <= v <= 100:
                problemas.append(f"{chave} fora da faixa 0–100: {v}")

    faltando = [p for p in REGISTRO[ferramenta].obrigatorios if p not in saida]
    problemas += [f"parâmetro obrigatório ausente: {p}" for p in faltando]
    return saida, problemas
