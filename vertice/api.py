"""API HTTP do agente de margem — liga o front-end MarginGuard ao motor + ReAct.

    uvicorn vertice.api:app --reload --port 8000
    # ou: python -m vertice.api

Contrato consumido por frontend/script.js::sendToBackend() (a Pessoa 3 já
deixou o exemplo comentado no arquivo dela — este endpoint bate exatamente
com ele, não precisou mudar mais nada do lado do front):

    POST /api/chat   {"message": str, "history": [{"role","content"}, ...]}
                  -> {"reply": str, "trace_id": str}

Servidor stateless por design: nenhuma sessão fica guardada em memória no
processo. Cada requisição reconstrói o histórico da conversa a partir do que
o próprio front-end manda de volta (ele já guarda localmente os pares
pergunta/resposta), em vez de manter um AgenteMargem vivo por usuário — mais
simples e não vaza estado entre abas/pessoas diferentes usando o mesmo
servidor.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .agent.prompts import ROTULO_PERGUNTA
from .agent.react import AgenteMargem
from .engine import executar
from .engine.auditoria import linhas_que_falharam
from .politica import (aguardando_aprovacao, ESTADOS, ROTULOS_ESTADO,
                       TRANSICOES, avancar_estado, etapas_futuras,
                       etapas_habilitadas,
                       caminho_arquivo, criar_proposta, definir_politica,
                       historico, propostas, proposta_em_teste,
                       politica_vigente)
from .experimento import (atribuicao_de, avaliar_regra_de_parada, criar_experimento,
                          desenho, encerrar_experimento, experimento_corrente,
                          experimentos, iniciar_experimento, resultado,
                          validacao_aa)
from .relatorio import (_int, _margem_exibida, _pct, _variacao_exibida,
                        gerar_relatorio_semanal, gerar_relatorio_semanal_dados)
# ROTULOS_CHECAGEM: o rótulo de negócio de cada checagem vive no módulo de
# apresentação, para a tela, o relatório e o arquivo exportado mostrarem o
# mesmo nome. O nome técnico continua sendo o do motor.
from .render_html import (ROTULOS_CHECAGEM, render_auditoria_html,
                          render_relatorio_html)

_TRACES_DIR = Path(os.getenv("VERTICE_TRACES_DIR", "traces"))

app = FastAPI(title="Vértice Retail — MarginGuard API")

# Front-end pode ser aberto de outra origem (ex.: extensão "Live Server" do
# editor) durante o desenvolvimento — CORS liberado não tem custo aqui
# porque não há autenticação/cookie nenhum neste protótipo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Mensagem(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Mensagem] = []


class ChatResponse(BaseModel):
    reply: str
    trace_id: str


def _modo_mock() -> bool:
    """Lido a cada chamada (não uma constante de módulo) para que os testes
    consigam ligar/desligar via variável de ambiente sem reimportar o app."""
    return os.getenv("VERTICE_API_MOCK", "").lower() in ("1", "true", "yes")


def _historico_do_frontend(history: list[Mensagem]) -> list[dict]:
    """Reconstrói o histórico no formato que o agente espera internamente
    (com a mesma etiqueta de papel do CLI), a partir do que o front-end
    devolveu. O front-end só guarda pares pergunta/resposta finais — nunca os
    passos intermediários de ferramenta — então não há nada para vazar aqui
    além do que o próprio usuário já viu na tela."""
    reconstruido = []
    for m in history:
        if m.role == "user":
            reconstruido.append({"role": "user", "content": f"{ROTULO_PERGUNTA} {m.content}"})
        elif m.role == "assistant":
            reconstruido.append({"role": "assistant", "content": m.content})
    return reconstruido


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(400, "message vazia")
    try:
        agente = AgenteMargem(mock=_modo_mock(), verbose=False)
    except RuntimeError as e:
        # Tipicamente ELOAGENTS_API_KEY ausente — mesma checagem do CLI.
        raise HTTPException(500, str(e))
    agente.historico = _historico_do_frontend(req.history)
    try:
        trace = agente.investigar(req.message)
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {e}")
    # Sem isso o trace morre com a requisição — via CLI dá pra rodar /trace
    # na hora, mas pela web a única forma de auditar depois é ter salvo.
    trace.salvar(_TRACES_DIR)
    return ChatResponse(reply=trace.resposta_final, trace_id=trace.id)


@app.get("/api/trace/{trace_id}")
def obter_trace(trace_id: str) -> dict:
    caminho = _TRACES_DIR / f"trace_{trace_id}.json"
    if not caminho.is_file():
        raise HTTPException(404, f"trace {trace_id} não encontrado")
    import json
    return json.loads(caminho.read_text(encoding="utf-8"))


# Data de fim da janela do relatório. Validar aqui é o que transforma
# "?ate=ontem" num 400 explicativo em vez de um 500 vindo do pandas.
RE_DATA = re.compile(r"\d{4}-\d{2}-\d{2}")

# Tudo que não pode entrar num nome de arquivo sugerido por Content-Disposition.
_NOME_SEGURO = re.compile(r"[^A-Za-z0-9_.-]+")


# ------------------------------------------------- relatório semanal / auditoria
def _resposta_html(conteudo: str, nome_arquivo: str, baixar: bool) -> Response:
    """Mesmo HTML serve para ver na aba e para baixar — só muda o cabeçalho."""
    headers = ({"Content-Disposition": f'attachment; filename="{nome_arquivo}"'}
               if baixar else {})
    return Response(content=conteudo, media_type="text/html; charset=utf-8",
                    headers=headers)


@app.get("/api/relatorio")
def relatorio_semanal(com_resumo: bool = False, canal_foco: str = "Marketplace",
                      dias: int = 7, ate: str | None = None) -> dict:
    """KPIs determinísticos. `dias` é a janela do relatório (7 = semanal) e
    `ate` o último dia dela (AAAA-MM-DD); sem `ate`, a janela termina no último
    dia da base. com_resumo=true tenta o parágrafo de IA; se o modelo falhar, o
    relatório volta igual, com resumo_disponivel=false."""
    if dias < 1:
        raise HTTPException(400, "dias deve ser >= 1")
    if ate and not RE_DATA.fullmatch(ate):
        raise HTTPException(400, f"ate deve estar no formato AAAA-MM-DD, recebido {ate!r}")
    if com_resumo:
        return gerar_relatorio_semanal(canal_foco=canal_foco, dias=dias, ate=ate)
    return {**gerar_relatorio_semanal_dados(canal_foco=canal_foco, dias=dias, ate=ate),
            "resumo_executivo": None, "resumo_disponivel": False}


@app.get("/api/relatorio.html")
def relatorio_semanal_html(com_resumo: bool = False, baixar: bool = False,
                           canal_foco: str = "Marketplace", dias: int = 7,
                           ate: str | None = None) -> Response:
    dados = relatorio_semanal(com_resumo=com_resumo, canal_foco=canal_foco,
                              dias=dias, ate=ate)
    nome = f"relatorio-margem-{time.strftime('%Y-%m-%d')}.html"
    return _resposta_html(render_relatorio_html(dados), nome, baixar)


def _validar_janela(dias: int, ate: str | None) -> None:
    if dias < 1:
        raise HTTPException(400, "dias deve ser >= 1")
    if ate and not RE_DATA.fullmatch(ate):
        raise HTTPException(400, f"ate deve estar no formato AAAA-MM-DD, recebido {ate!r}")


@app.get("/api/relatorio/cascata")
def relatorio_cascata(dias: int = 7, ate: str | None = None) -> dict:
    """Ponte da margem no período: margem calculada → cancelamento → pendência
    → devolução → atendimento → margem que se realiza.

    Mesma janela do relatório ([ate-dias+1, ate]) e mesma ferramenta que o
    agente usa — nenhum número é montado aqui."""
    _validar_janela(dias, ate)
    try:
        return executar("perda_pos_pedido", {"dias": dias, "ate": ate})
    except ValueError as e:      # janela sem nenhum pedido
        raise HTTPException(400, str(e))


@app.get("/api/relatorio/margem-por")
def relatorio_margem_por(dimensao: str = "canal", dias: int = 7,
                         ate: str | None = None) -> dict:
    """Margem aberta por canal ou categoria DENTRO da janela do relatório."""
    if dimensao not in ("canal", "categoria"):
        raise HTTPException(400, "dimensao deve ser 'canal' ou 'categoria'")
    _validar_janela(dias, ate)
    try:
        return executar("margem_por_dimensao",
                        {"dimensao": dimensao, "dias": dias, "ate": ate})
    except ValueError as e:
        raise HTTPException(400, str(e))


# --------------------------------------------------------------- visão geral


@app.get("/api/visao-geral")
def visao_geral(dias: int = 7, ate: str | None = None) -> dict:
    """Cockpit executivo: margem do período, drivers de perda, alertas de
    auditoria e as ações de maior valor — tudo do motor determinístico.

    Sobre os drivers: eles vêm em DOIS grupos que NÃO se somam entre si. Os do
    grupo `entre_receita_e_margem` (desconto, frete) medem o que se perde antes
    de a margem ser calculada; os de `depois_da_margem` (devolução,
    cancelamento, pendência, atendimento) medem o que se perde depois. Somar os
    dois conta a mesma perda duas vezes — é o alerta que `perda_pos_pedido`
    carrega no próprio retorno, e por isso esta rota devolve dois subtotais e
    nunca um total único.
    """
    _validar_janela(dias, ate)

    consolidado = executar("margem_consolidada")
    janela = executar("margem_na_janela", {"dias": dias, "ate": ate})
    frete = executar("custo_assimetria_frete", {"canal": "Marketplace"})
    pos = executar("perda_pos_pedido")
    devolucoes = executar("impacto_devolucoes", {"por": "canal"})

    def _ramo(nome: str) -> float:
        r = next((x for x in pos["ramos"] if x["ramo"] == nome), None)
        return float(r["margem_perdida_reais"]) if r else 0.0

    entre = [
        {"driver": "Desconto concedido", "valor_reais": consolidado["desconto_reais"],
         "fonte": "margem_consolidada",
         "nota": "concessão sobre a receita bruta da base inteira"},
        {"driver": "Frete evitável — Marketplace",
         "valor_reais": frete["frete_evitavel_reais"], "fonte": "custo_assimetria_frete",
         "nota": "frete que o canal paga e os demais não"},
    ]
    depois = [
        {"driver": "Devolução", "valor_reais": _ramo("Devolução"),
         "fonte": "perda_pos_pedido", "nota": "margem do pedido devolvido mais o frete de ida"},
        {"driver": "Cancelamento", "valor_reais": _ramo("Cancelamento"),
         "fonte": "perda_pos_pedido", "nota": "margem que nunca se realizou — não é economia capturável"},
        {"driver": "Pendência", "valor_reais": _ramo("Pendência"),
         "fonte": "perda_pos_pedido", "nota": "saneamento de registro, não ganho"},
        {"driver": "Atendimento", "valor_reais": _ramo("Atendimento"),
         "fonte": "perda_pos_pedido", "nota": "custo operacional dos tickets ligados a pedidos"},
    ]

    aud = executar("relatorio_auditoria_dados")
    alertas = []
    for c in aud.get("checagens", []):
        r = c.get("resultado") or {}
        if "erro" in c or r.get("status") in ("atencao", "revisar", "critico"):
            alvo = (c.get("parametros") or {})
            alertas.append({
                "checagem": c["checagem"],
                "rotulo": ROTULOS_CHECAGEM.get(c["checagem"], c["checagem"]),
                "status": "critico" if "erro" in c else r.get("status"),
                "alvo": " · ".join(f"{k}={v}" for k, v in alvo.items()),
                "parametros": alvo,
            })

    teto = executar("simular_teto_desconto", {"teto_pct": 20})
    acoes = [
        {"acao": "Impor teto de 20% no desconto",
         "valor_reais": teto["margem_recuperada_reais"],
         "unidade": "potencialmente preservado no recorte",
         "destino": "politica", "fonte": "simular_teto_desconto",
         "detalhe": f"{_int(teto['pedidos_afetados'])} pedidos afetados "
                    f"({_pct(teto['pct_pedidos_afetados'])} do recorte)"},
    ]

    atual, anterior = janela["janela_atual"], janela["janela_anterior"]
    return {
        "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "periodo": {"dias": janela["dias"], "inicio": atual.get("inicio"),
                    "fim": atual.get("fim"), "vazio": atual.get("vazio", False)},
        "periodo_anterior": {"inicio": anterior.get("inicio"), "fim": anterior.get("fim")},
        "margem": {
            # Mesma convenção de exibição do relatório e do deck: margem sobre
            # receita LÍQUIDA. O motor devolve os dois denominadores; quem
            # publica escolhe um, e é sempre este.
            "pct": _margem_exibida(atual), "reais": atual.get("margem_contribuicao"),
            "receita_bruta": atual.get("receita_bruta"),
            "receita_liquida": atual.get("receita_liquida"),
            "pedidos": atual.get("pedidos"),
            "anterior_pct": _margem_exibida(anterior),
            "base_do_percentual": "receita líquida",
            "variacao": _variacao_exibida(janela.get("variacao"), atual, anterior),
        },
        "valor_em_risco": {
            "entre_receita_e_margem": {
                "drivers": entre,
                "subtotal_reais": round(sum(d["valor_reais"] for d in entre), 2),
            },
            "depois_da_margem": {
                "drivers": depois,
                "subtotal_reais": round(sum(d["valor_reais"] for d in depois), 2),
            },
            "por_que_nao_ha_total_unico": pos["ALERTA_NAO_SOMAR"],
            "periodo": "base inteira (13 meses), não o período selecionado",
        },
        "alertas": alertas,
        "acoes": acoes,
        "devolucoes_taxa_pct": devolucoes["taxa_devolucao_global_pct"],
        "fontes": ["margem_na_janela", "margem_consolidada", "custo_assimetria_frete",
                   "perda_pos_pedido", "impacto_devolucoes", "relatorio_auditoria_dados",
                   "simular_teto_desconto"],
    }


@app.get("/api/auditoria")
def auditoria() -> dict:
    """Auditoria determinística + o recorte categoria x motivo_devolucao, que é
    o achado que motivou a camada (tamanho errado fora de Moda)."""
    dados = executar("relatorio_auditoria_dados")
    consistencia = executar("verificar_consistencia_categorica",
                            {"tabela": "vendas", "coluna_a": "categoria",
                             "coluna_b": "motivo_devolucao"})
    celulas = [c for c in consistencia["celulas"]
               if c["motivo_devolucao"] == "Tamanho errado"]
    dados["destaque_incoerencia"] = {
        "coluna_a": "categoria", "coluna_b": "motivo_devolucao",
        "valor_b": "Tamanho errado",
        "celulas": celulas,
        "fora": sum(c["registros"] for c in celulas if c["categoria"] != "Moda"),
    }
    return dados


@app.get("/api/auditoria/exportar")
def auditoria_exportar(request: Request, checagem: str) -> Response:
    """CSV com TODOS os registros que falharam uma checagem — a lista de
    trabalho de quem vai corrigir, não a amostra de 5-20 que a tela mostra.

    Os parâmetros da checagem vêm na própria query string, iguais aos que a
    tela recebeu em `parametros` (ex.: ?checagem=duplicatas_chave&tabela=vendas
    &coluna_chave=order_id).

    SÓ LEITURA: nada aqui escreve em data/*.csv. A exportação existe para ação
    humana no sistema de origem — o motor não corrige dado sozinho.
    """
    parametros = {k: v for k, v in request.query_params.items() if k != "checagem"}
    try:
        linhas = linhas_que_falharam(checagem, parametros)
    except KeyError as e:
        raise HTTPException(400, f"parâmetro obrigatório ausente para '{checagem}': {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))

    csv = linhas.to_csv(index=False)
    # O nome do arquivo é montado com valor que veio da URL e vai para um
    # cabeçalho HTTP: aspas e quebra de linha aqui quebrariam o Content-
    # Disposition, então só passa o que é seguro num nome de arquivo.
    alvo = _NOME_SEGURO.sub("", "-".join(str(v) for v in parametros.values() if v))
    nome = (f"correcao-{_NOME_SEGURO.sub('', checagem)}-{alvo or 'base'}"
            f"-{time.strftime('%Y-%m-%d')}.csv")
    return Response(
        # BOM: sem ele o Excel em pt-BR abre "Acessórios" como "AcessÃ³rios".
        content="﻿" + csv,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"',
                 "X-Registros": str(len(linhas))},
    )


@app.get("/api/auditoria.html")
def auditoria_html(baixar: bool = False) -> Response:
    dados = auditoria()
    nome = f"auditoria-dados-{time.strftime('%Y-%m-%d')}.html"
    return _resposta_html(
        render_auditoria_html(dados, dados.get("destaque_incoerencia")), nome, baixar)


# ------------------------------------------------------------ política vigente
class PoliticaRequest(BaseModel):
    teto_pct: float
    responsavel: str
    canal: str | None = None
    categoria: str | None = None
    vigencia: str | None = None


def _impacto_do_teto(teto_pct: float | None, canal: str | None,
                     categoria: str | None) -> dict | None:
    """Efeito determinístico do teto no recorte — é o que torna a tela de
    política uma decisão e não um cadastro: quantos pedidos ela toca, quanto de
    margem recupera e quanto disso aparece na margem consolidada."""
    if teto_pct is None:
        return None
    try:
        return executar("simular_teto_desconto", {
            "teto_pct": teto_pct, "canal": canal, "categoria": categoria})
    except Exception:
        return None


@app.get("/api/politica/simular")
def simular_politica(teto_pct: float, canal: str | None = None,
                     categoria: str | None = None) -> dict:
    """Prévia antes de aplicar: mesma conta da política vigente, com o teto que
    a pessoa acabou de digitar."""
    impacto = _impacto_do_teto(teto_pct, canal or None, categoria or None)
    if impacto is None:
        raise HTTPException(400, f"não foi possível simular teto de {teto_pct}%")
    return impacto


@app.get("/api/politica")
def consultar_politica(canal: str | None = None, categoria: str | None = None) -> dict:
    # O front manda ?canal=&categoria= quando o recorte é "todos" — string vazia
    # não é o mesmo que None para politica_vigente(), então normaliza aqui.
    canal, categoria = canal or None, categoria or None
    vigente = politica_vigente(canal, categoria)
    return {
        "vigente": vigente,
        "impacto": _impacto_do_teto(vigente["teto_pct"] if vigente else None,
                                    canal, categoria),
        "historico": historico(canal, categoria),
        # Histórico completo à parte: filtrado por recorte, a tela dava a
        # impressão de que as políticas de outros recortes tinham sumido.
        "historico_completo": historico(),
        "canais": _canais_disponiveis(),
        "categorias": _categorias_disponiveis(),
        "arquivo": str(caminho_arquivo().resolve()),
    }


@app.post("/api/politica")
def definir_politica_endpoint(req: PoliticaRequest) -> dict:
    """Registra uma NOVA política. Não apaga a anterior — o histórico é o que
    sustenta "regras versionadas com dono e vigência"."""
    try:
        entrada = definir_politica(
            canal=req.canal or None, categoria=req.categoria or None,
            teto_pct=req.teto_pct, responsavel=req.responsavel,
            vigencia=req.vigencia,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    canal, categoria = req.canal or None, req.categoria or None
    return {"definida": entrada, "vigente": politica_vigente(canal, categoria),
            "impacto": _impacto_do_teto(entrada["teto_pct"], canal, categoria),
            "historico": historico(canal, categoria)}


# ------------------------------------------------- ciclo de vida da proposta
class PropostaRequest(BaseModel):
    teto_pct: float
    responsavel: str
    canal: str | None = None
    categoria: str | None = None
    vigencia: str | None = None
    nota: str | None = None


class TransicaoRequest(BaseModel):
    """Quem faz a transição é obrigatório: é o registro que a governança pede."""
    quem: str
    nota: str | None = None


# Tetos comparados lado a lado na tela de política. Novembro fora porque é o
# mês de campanha: incluí-lo infla o efeito do teto com um comportamento que a
# empresa não pretende repetir o ano todo.
CENARIOS_TETO = (15, 20, 25, 30)
MESES_EXCLUIDOS_DO_CENARIO = [11]


@app.get("/api/politica/cenarios")
def politica_cenarios(canal: str | None = None, categoria: str | None = None) -> dict:
    """Os quatro tetos simulados de uma vez, para comparação lado a lado.

    Cada um é uma chamada a `simular_teto_desconto` — o mesmo motor que o
    agente usa. Nenhuma conta é feita aqui.
    """
    linhas = []
    for teto in CENARIOS_TETO:
        try:
            r = executar("simular_teto_desconto", {
                "teto_pct": teto, "canal": canal or None,
                "categoria": categoria or None,
                "excluir_meses": MESES_EXCLUIDOS_DO_CENARIO})
        except Exception as e:
            linhas.append({"teto_pct": teto, "erro": f"{type(e).__name__}: {e}"})
            continue
        linhas.append({
            "teto_pct": r["teto_aplicado_pct"],
            # "preservada", não "recuperada": a política ainda não rodou.
            "preservado_reais": r["contribuicao_preservada_reais"],
            "preservado_anualizado_reais": r.get("valor_anualizado_reais"),
            "pedidos_afetados": r["pedidos_afetados"],
            "pct_pedidos_afetados": r["pct_pedidos_afetados"],
            "ponto_de_equilibrio_pct": r["ponto_de_equilibrio_pct"],
            "ganho_margem_pp": r["ganho_margem_pp"],
            "periodo_coberto": r.get("periodo_coberto"),
            "recorte_aplicado": r.get("recorte_aplicado"),
        })
    return {
        "cenarios": linhas,
        "excluir_meses": MESES_EXCLUIDOS_DO_CENARIO,
        # A nota vai inteira para a tela: quanto mais curta, mais gente lê.
        # O essencial é a premissa (volume constante) e o status (não apurado).
        "nota": ("sob premissa de volume constante — os mesmos pedidos "
                 "aconteceriam com o teto em vigor."),
        "definicao_ponto_de_equilibrio": (
            "percentual dos pedidos afetados que poderiam deixar de acontecer "
            "antes de o ganho se anular"),
    }


@app.get("/api/politica/propostas")
def listar_propostas() -> dict:
    return {"propostas": propostas(), "estados": list(ESTADOS),
            "rotulos": ROTULOS_ESTADO,
            # Até onde o fluxo vai hoje, e o que a tela deve marcar como
            # implementação futura. A tela não decide isso sozinha.
            "etapas_habilitadas": list(etapas_habilitadas()),
            "etapas_futuras": list(etapas_futuras()),
            # Quem está esperando decisão de outra pessoa. Vai junto para a
            # tela não precisar de uma segunda chamada só para a fila.
            "aguardando_aprovacao": aguardando_aprovacao(),
            "transicoes": {k: list(v) for k, v in TRANSICOES.items()}}


@app.post("/api/politica/propostas")
def criar_proposta_endpoint(req: PropostaRequest) -> dict:
    """Nasce em rascunho. Não muda o teto vigente — só a aprovação faz isso."""
    try:
        return criar_proposta(teto_pct=req.teto_pct, responsavel=req.responsavel,
                              canal=req.canal or None, categoria=req.categoria or None,
                              vigencia=req.vigencia, nota=req.nota)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _transicao(proposta_id: str, destino: str, req: TransicaoRequest) -> dict:
    try:
        return avancar_estado(proposta_id, destino, quem=req.quem, nota=req.nota)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/politica/{proposta_id}/simular")
def proposta_simular(proposta_id: str, req: TransicaoRequest) -> dict:
    return _transicao(proposta_id, "simulacao", req)


@app.post("/api/politica/{proposta_id}/enviar-aprovacao")
def proposta_enviar_aprovacao(proposta_id: str, req: TransicaoRequest) -> dict:
    return _transicao(proposta_id, "aprovacao", req)


@app.post("/api/politica/{proposta_id}/aprovar")
def proposta_aprovar(proposta_id: str, req: TransicaoRequest) -> dict:
    """Aqui a proposta vira política vigente de verdade, por definir_politica()."""
    return _transicao(proposta_id, "ativa", req)


@app.post("/api/politica/{proposta_id}/monitorar")
def proposta_monitorar(proposta_id: str, req: TransicaoRequest) -> dict:
    return _transicao(proposta_id, "monitoramento", req)


# ----------------------------------------------------------- monitoramento
# A regra de parada é CONFIGURAÇÃO, não resultado: ela existe antes de
# qualquer teste rodar, e por isso aparece na tela mesmo sem teste ativo.
# Os números do teste em si (margem preservada real, volume contra o grupo de
# controle) vêm de `experimento.resultado()`, que mede a base dentro da janela
# do teste e devolve indisponível quando não há pedido lá — nunca estimativa.
REGRA_DE_PARADA = {
    "criterio": "Parar o teste se a conversão do grupo com teto cair mais de "
                "2 p.p. contra o grupo de controle, com significância a 95%.",
    "duracao_minima_semanas": 4,
    "amostra_minima_por_grupo": 1340,
    "significancia": 0.05,
    "fonte": "desenho experimental do case (Fase 4 do roadmap)",
}


class ExperimentoRequest(BaseModel):
    proposta_id: str
    teto_pct: float
    responsavel: str
    unidade: str = "cliente"
    proporcao_controle: float = 0.5
    duracao_dias: int = 30
    mde_relativo: float = 0.05
    canal: str | None = None
    categoria: str | None = None


class IniciarRequest(BaseModel):
    quem: str
    inicio: str | None = None       # AAAA-MM-DD; omitido = hoje


class EncerrarRequest(BaseModel):
    quem: str
    motivo: str


@app.get("/api/experimento/desenho")
def experimento_desenho(mde_relativo: float = 0.05, alpha: float = 0.05,
                        poder: float = 0.8, canal: str | None = None,
                        categoria: str | None = None) -> dict:
    """Tamanho de amostra e duração necessários, pelas duas unidades possíveis.

    É a resposta determinística para "esse teste é possível de rodar?" — vem da
    dispersão real da base, antes de qualquer decisão."""
    try:
        return desenho(mde_relativo=mde_relativo, alpha=alpha, poder=poder,
                       canal=canal or None, categoria=categoria or None)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/experimento/validacao-aa")
def experimento_validacao_aa(semente: str = "afericao", unidade: str = "cliente",
                             dias: int = 90, canal: str | None = None,
                             categoria: str | None = None) -> dict:
    """Teste A/A sobre a base histórica: afere a régua antes de usá-la."""
    try:
        return validacao_aa(semente=semente, unidade=unidade, dias=dias,
                            canal=canal or None, categoria=categoria or None)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/experimento/atribuicao")
def experimento_atribuicao(chave: str, semente: str,
                           proporcao_controle: float = 0.5) -> dict:
    """Em que grupo uma chave cai — a auditoria unidade a unidade."""
    return atribuicao_de(chave, semente, proporcao_controle)


@app.get("/api/experimento")
def experimento_corrente_endpoint() -> dict:
    """O experimento corrente com resultado real e veredicto da regra de parada."""
    exp = experimento_corrente()
    if exp is None:
        return {"experimento": None, "resultado": None, "regra_de_parada": None,
                "experimentos": experimentos()}
    res = resultado(exp)
    return {"experimento": exp, "resultado": res,
            "regra_de_parada": avaliar_regra_de_parada(exp, res),
            "experimentos": experimentos()}


@app.post("/api/experimento")
def experimento_criar(req: ExperimentoRequest) -> dict:
    """Desenha o experimento a partir de uma proposta. Nasce PLANEJADO."""
    try:
        return criar_experimento(
            proposta_id=req.proposta_id, teto_pct=req.teto_pct,
            responsavel=req.responsavel, unidade=req.unidade,
            proporcao_controle=req.proporcao_controle, duracao_dias=req.duracao_dias,
            mde_relativo=req.mde_relativo, canal=req.canal or None,
            categoria=req.categoria or None)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/experimento/{exp_id}/iniciar")
def experimento_iniciar(exp_id: str, req: IniciarRequest) -> dict:
    if req.inicio and not RE_DATA.fullmatch(req.inicio):
        raise HTTPException(400, f"inicio deve ser AAAA-MM-DD, recebido {req.inicio!r}")
    try:
        return iniciar_experimento(exp_id, quem=req.quem, inicio=req.inicio)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/experimento/{exp_id}/encerrar")
def experimento_encerrar(exp_id: str, req: EncerrarRequest) -> dict:
    """Encerrar exige motivo declarado — é o registro de por que se parou."""
    try:
        return encerrar_experimento(exp_id, quem=req.quem, motivo=req.motivo)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _desenho_silencioso(canal=None, categoria=None):
    """O cálculo de poder nunca derruba a tela de monitoramento.

    Ele lê a dispersão real da base e pode falhar por recorte vazio (um canal
    sem pedido suficiente, por exemplo). Quando falha, a tela mostra o resto —
    a alternativa seria a página inteira virar erro por causa de um bloco.
    """
    try:
        return desenho(canal=canal or None, categoria=categoria or None)
    except (ValueError, ZeroDivisionError):
        return None


@app.get("/api/monitoramento")
def monitoramento() -> dict:
    """Resultado real da política em teste — ou a declaração de que não há uma.

    Enquanto nenhuma proposta chegou a 'ativa', não existe teste rodando, e
    esta rota devolve `estado='aguardando'` com os campos de resultado nulos.
    Preencher esses campos com estimativa seria inventar resultado de um
    experimento que não aconteceu.
    """
    proposta = proposta_em_teste()
    if proposta is None:
        return {
            "estado": "aguardando",
            "titulo": "Sem política em teste",
            "explicacao": (
                "Nenhuma política está aplicada. O monitoramento começa quando "
                "uma proposta chega ao estado Ativa — etapa que ainda não está "
                "disponível no fluxo de Políticas (implementação futura)."
                if "ativa" not in etapas_habilitadas() else
                "Nenhuma política está aplicada. O monitoramento começa quando "
                "uma proposta chega ao estado Ativa, no fluxo de Políticas."),
            "proposta": None,
            "experimento": None,
            "desenho": _desenho_silencioso(),
            "regra_de_parada": REGRA_DE_PARADA,
            "resultados": None,
            "por_que_sem_numeros": "nenhuma política em teste",
        }

    # Com política ativa, o monitoramento é o do EXPERIMENTO: o resultado vem
    # de `experimento.resultado()`, que mede a base dentro da janela do teste e
    # devolve `disponivel=False` quando não há pedido lá — nunca uma estimativa.
    exp = experimento_corrente()
    res = resultado(exp) if exp else None
    parada = avaliar_regra_de_parada(exp, res) if exp else None

    return {
        "estado": proposta["estado"],
        "titulo": f"Política de teto {proposta['teto_pct']}% em "
                  f"{ROTULOS_ESTADO.get(proposta['estado'], proposta['estado'])}",
        "explicacao": "A política está aplicada.",
        "proposta": proposta,
        "experimento": exp,
        "desenho": _desenho_silencioso(proposta.get("canal"),
                                       proposta.get("categoria")),
        "resultado_experimento": res,
        "regra_de_parada": (
            {**REGRA_DE_PARADA, **parada} if parada else REGRA_DE_PARADA),
        "resultados": _resultados_do_experimento(res),
        "por_que_sem_numeros": (
            (res or {}).get("motivo")
            or "nenhum experimento desenhado"
            if not (res or {}).get("disponivel") else None),
    }


def _resultados_do_experimento(res: dict | None) -> dict:
    """Traduz o resultado do experimento para os campos que a tela mostra.

    Sem dado, todo campo sai None — é o que impede a tela de exibir estimativa
    onde deveria haver apuração."""
    vazio = {
        "margem_preservada_real_reais": None,
        "volume_grupo_teste": None,
        "volume_grupo_controle": None,
        "diferenca_relativa_pct": None,
        "p_valor": None,
        "status_do_teste": "aguardando dado do experimento",
    }
    if not res or not res.get("disponivel"):
        return vazio

    metricas = res.get("metricas") or {}
    volume = metricas.get("pedidos_por_cliente") or {}
    margem = metricas.get("margem_por_cliente") or metricas.get("margem_por_pedido") or {}
    if not volume.get("suficiente") and not margem.get("suficiente"):
        return vazio
    return {
        # "Preservada" é a diferença medida entre os grupos, não a simulação.
        "margem_preservada_real_reais": (
            round(margem["diferenca"] * res.get("unidades_teste", 0), 2)
            if margem.get("suficiente") else None),
        "volume_grupo_teste": volume.get("media_teste"),
        "volume_grupo_controle": volume.get("media_controle"),
        "diferenca_relativa_pct": volume.get("diferenca_relativa_pct"),
        "p_valor": volume.get("p_valor"),
        "status_do_teste": "medido na janela do experimento",
    }


def _canais_disponiveis() -> list[str]:
    from .data import carregar_vendas
    return sorted(carregar_vendas()["canal"].dropna().unique().tolist())


def _categorias_disponiveis() -> list[str]:
    from .data import carregar_vendas
    return sorted(carregar_vendas()["categoria"].dropna().unique().tolist())


# NOTA: /api/health carrega a trava do fluxo porque é a única rota que a tela
# chama antes de qualquer outra. Ver ETAPAS_HABILITADAS em politica.py.
# NOTA: /api/health carrega a trava do fluxo porque é a única rota que a tela
# chama antes de qualquer outra. Ver ETAPAS_HABILITADAS em politica.py.
@app.get("/api/health")
def health() -> dict:
    chave = config.chave_gateway()
    mock = _modo_mock()
    return {
        "ok": bool(chave) or mock,
        "modo_mock": mock,
        "chave_configurada": bool(chave),
        "modelo_investigacao": config.MODELO_INVESTIGACAO,
        "modelo_sintese": config.MODELO_SINTESE,
        "etapas_habilitadas": list(etapas_habilitadas()),
    }


# Serve o front-end estático (frontend/index.html, script.js, style.css) na
# raiz — mesma origem do /api/*, então nenhum CORS entra em jogo de verdade
# no uso normal (abrir http://localhost:8000/). Precisa ser o ÚLTIMO
# registrado: rotas /api/* já declaradas acima têm precedência.
_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
