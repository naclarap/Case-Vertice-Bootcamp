"""Item 2 (relatório semanal determinístico + resumo opcional) e
Item 3 (card estruturado para o dashboard)."""
import pytest

from vertice.agent.card import gerar_card
from vertice.agent.react import AgenteMargem
from vertice.engine import executar
from vertice.relatorio import (gerar_relatorio_semanal, gerar_relatorio_semanal_dados,
                               redigir_resumo_executivo)

RESPOSTA_FRETE = (
    "FATO: o Marketplace paga R$ 172.828,86 de frete e R$ 135.256,57 é evitável.\n"
    "INFERÊNCIA: a diferença é de política de frete, não de custo estrutural.\n"
    "RECOMENDAÇÃO: equalizar a política de frete do Marketplace à dos demais canais.\n"
    "FORÇA DA EVIDÊNCIA: FORTE (p<0,001, n=24.454)."
)


# =================================================== item 2 — relatório semanal
class _LLMProibido:
    """Qualquer uso do modelo aqui é falha do teste: a automação determinística
    tem de rodar sem rede e sem chave."""

    def completar(self, mensagens, modelo, tools=None):
        raise AssertionError("gerar_relatorio_semanal_dados chamou o LLM")


class _LLMQuebrado:
    def completar(self, mensagens, modelo, tools=None):
        raise RuntimeError("gateway fora do ar")


class _LLMFalso:
    def completar(self, mensagens, modelo, tools=None):
        class _M:
            content = "A margem consolidada está em 49,99%."
            tool_calls = None
        return _M()


def test_relatorio_de_dados_nunca_chama_o_llm(monkeypatch):
    """Mockado para explodir se for chamado — garante que a função agendável
    não depende de rede nem de chave de API."""
    monkeypatch.setattr("vertice.agent.llm.construir_llm",
                        lambda *a, **k: _LLMProibido())
    monkeypatch.delenv("ELOAGENTS_API_KEY", raising=False)
    r = gerar_relatorio_semanal_dados()
    assert r["margem"]["margem_pct"] > 0


def test_relatorio_de_dados_traz_todos_os_kpis_esperados():
    r = gerar_relatorio_semanal_dados()
    for bloco in ("margem", "desconto", "margem_negativa", "frete_canal_foco",
                  "devolucoes", "pior_canal_por_margem"):
        assert bloco in r, bloco
    assert r["margem"]["margem_reais"] == 9058427.55
    assert r["desconto"]["taxa_desconto_pct"] == 8.0
    assert r["margem_negativa"]["pedidos"] == 427
    assert r["frete_canal_foco"]["frete_evitavel_reais"] == 135256.57
    assert r["devolucoes"]["taxa_global_pct"] == 14.88
    assert r["pior_canal_por_margem"]["canal"] == "Marketplace"


def test_janela_do_relatorio_aceita_data_de_fim():
    """O parâmetro existe em margem_na_janela desde sempre; o que faltava era o
    caminho até ele, e é este teste que garante que o caminho continua ligado."""
    r = gerar_relatorio_semanal_dados(dias=31, ate="2023-03-31")
    assert r["semana"]["inicio"] == "2023-03-01"
    assert r["semana"]["fim"] == "2023-03-31"
    # A janela anterior acompanha: 31 dias imediatamente antes.
    assert r["semana"]["anterior"]["fim"] == "2023-02-28"


def test_sem_data_de_fim_o_comportamento_padrao_nao_muda():
    r = gerar_relatorio_semanal_dados(dias=7)
    assert r["semana"]["fim"] == r["janela"][1][:10]


def test_acumulado_da_base_nao_muda_com_a_data_de_fim():
    """Só o bloco da janela é do período. Frete evitável, devolução e margem
    negativa continuam sendo diagnóstico de estoque, sobre a base inteira."""
    a = gerar_relatorio_semanal_dados(dias=31, ate="2023-03-31")
    b = gerar_relatorio_semanal_dados(dias=7)
    for bloco in ("margem", "desconto", "margem_negativa", "devolucoes", "frete_canal_foco"):
        assert a[bloco] == b[bloco], f"{bloco} mudou com a data de fim"
    assert a["semana"] != b["semana"]


def test_devolucao_declara_que_o_custo_nao_esta_deduzido_da_margem():
    """PREMISSA P7: margem_contribuicao é anterior à devolução. O KPI diz isso
    explicitamente em vez de deixar o leitor supor que já está descontado."""
    r = gerar_relatorio_semanal_dados()
    assert r["devolucoes"]["custo_registrado_na_margem"] is False
    assert r["devolucoes"]["pct_devolucoes_com_custo_deduzido"] == 0.0


def test_resumo_executivo_devolve_none_quando_o_llm_falha():
    assert redigir_resumo_executivo({"margem": {}}, llm=_LLMQuebrado()) is None


def test_relatorio_final_e_montado_mesmo_com_resumo_falhando():
    """O parágrafo de IA é opcional: a falha dele não pode derrubar a geração."""
    r = gerar_relatorio_semanal(llm=_LLMQuebrado())
    assert r["resumo_executivo"] is None
    assert r["resumo_disponivel"] is False
    assert r["margem"]["margem_pct"] > 0          # dado determinístico presente
    assert r["frete_canal_foco"]["frete_evitavel_reais"] == 135256.57


def test_relatorio_final_inclui_o_resumo_quando_o_llm_responde():
    r = gerar_relatorio_semanal(llm=_LLMFalso())
    assert r["resumo_disponivel"] is True
    assert "49,99%" in r["resumo_executivo"]


def test_relatorio_sem_resumo_nao_tenta_gerar_texto():
    r = gerar_relatorio_semanal(com_resumo=False, llm=_LLMProibido())
    assert r["resumo_executivo"] is None


def test_resumo_vazio_do_modelo_conta_como_indisponivel():
    class _Vazio:
        def completar(self, mensagens, modelo, tools=None):
            class _M:
                content = "   "
                tool_calls = None
            return _M()
    assert redigir_resumo_executivo({}, llm=_Vazio()) is None


# ======================================================== item 3 — card
def _trace_de_frete(origem_consulta: str = "ad_hoc"):
    """Cenário Marketplace/frete, o mesmo já usado nos testes existentes.

    O teste_t_welch está aqui porque a resposta reivindica FORTE, e o guardrail
    existente rebaixa FORTE/MODERADA sem teste estatístico real — sem essa
    chamada o cenário não seria representativo de uma investigação aceita.
    """
    roteiro = ['AÇÃO: custo_assimetria_frete\nPARÂMETROS: {"canal": "Marketplace"}',
               'AÇÃO: teste_t_welch\nPARÂMETROS: {"metrica": "frete_pct", '
               '"coluna_grupo": "canal", "grupo_a": "Marketplace"}',
               RESPOSTA_FRETE]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    return ag.investigar("Quanto o Marketplace paga de frete a mais?",
                         origem_consulta=origem_consulta)


def test_card_traz_impacto_rs_do_valor_ja_validado_no_motor():
    card = gerar_card(_trace_de_frete())
    assert card["impacto_rs"] == 135256.57      # frete evitável, valor do motor
    assert card["impacto_pp"] == 0.746          # ganho consolidado, valor do motor


def test_card_tem_todos_os_campos_do_contrato():
    card = gerar_card(_trace_de_frete())
    for campo in ("titulo", "recomendacao", "impacto_rs", "impacto_pp",
                  "forca_evidencia", "fontes"):
        assert campo in card, campo
    assert isinstance(card["fontes"], list)
    assert "custo_assimetria_frete" in card["fontes"]


def test_card_usa_vocabulario_minusculo_de_forca():
    card = gerar_card(_trace_de_frete())
    assert card["forca_evidencia"] in ("forte", "moderada", "fraca")
    assert card["forca_evidencia"] == "forte"


def test_card_extrai_a_recomendacao_como_frase_curta():
    card = gerar_card(_trace_de_frete())
    assert card["recomendacao"].startswith("equalizar a política de frete")
    assert "\n" not in card["recomendacao"]


def test_card_sem_numero_disponivel_devolve_none_em_vez_de_inventar():
    """Investigação que não produziu nenhum número de impacto: o card sai com
    impacto None, não com número reformulado pelo modelo."""
    resposta = ("FATO: não foi possível apurar o recorte pedido.\n"
                "INFERÊNCIA: falta dado para responder.\n"
                "RECOMENDAÇÃO: rodar a simulação com o recorte correto.\n"
                "FORÇA DA EVIDÊNCIA: FRACA")
    ag = AgenteMargem(mock=True, roteiro_mock=[resposta, resposta, resposta],
                      verbose=False)
    tr = ag.investigar("pergunta sem dado")
    # zera as observações para simular investigação sem número nenhum
    tr.passos = [p for p in tr.passos if p.tipo != "observacao"]
    card = gerar_card(tr)
    assert card["impacto_rs"] is None
    assert card["impacto_pp"] is None
    assert card["forca_evidencia"] == "fraca"


def test_card_nao_quebra_com_trace_sem_resposta_final():
    from vertice.agent.trace import Trace
    card = gerar_card(Trace(pergunta="sem resposta"))
    assert card["impacto_rs"] is None
    assert card["recomendacao"] == ""
    assert card["fontes"] == []


def test_titulo_pode_ser_informado_pelo_painel():
    card = gerar_card(_trace_de_frete(), titulo="Recomendação de frete — Marketplace")
    assert card["titulo"] == "Recomendação de frete — Marketplace"


def test_card_registra_origem_da_consulta():
    """O painel precisa distinguir revisão agendada de pergunta pontual."""
    tr = _trace_de_frete(origem_consulta="revisao_periodica")
    assert gerar_card(tr)["origem_consulta"] == "revisao_periodica"


def test_numeros_do_card_vem_de_ferramenta_e_nao_do_texto_do_modelo():
    """O texto cita R$ 172.828,86 primeiro; o card precisa pegar o campo de
    impacto da OBSERVAÇÃO (135.256,57), não o primeiro número do texto."""
    card = gerar_card(_trace_de_frete())
    assert card["impacto_rs"] != 172828.86
    assert card["impacto_rs"] == 135256.57


# ------------------------------------------------- janela semanal de verdade
# O relatório se chamava semanal e mostrava os 13 meses inteiros da base.
def test_margem_na_janela_compara_duas_semanas_consecutivas():
    r = executar("margem_na_janela", {"dias": 7})
    atual, anterior = r["janela_atual"], r["janela_anterior"]
    assert atual["pedidos"] > 0 and anterior["pedidos"] > 0
    # janelas coladas e sem sobreposição
    assert anterior["fim"] < atual["inicio"]
    assert isinstance(atual["pedidos"], int)      # contagem não é 259.0
    assert set(r["variacao"]) == {"margem_pp", "desconto_pp", "receita_pct", "pedidos_pct"}


def test_janela_de_7_dias_cobre_exatamente_7_dias():
    import datetime as dt
    r = executar("margem_na_janela", {"dias": 7})
    a = dt.date.fromisoformat(r["janela_atual"]["inicio"])
    b = dt.date.fromisoformat(r["janela_atual"]["fim"])
    assert (b - a).days == 6                      # [ini, fim] fechado = 7 dias


def test_janela_maior_pega_mais_pedidos_que_a_semana():
    sete = executar("margem_na_janela", {"dias": 7})["janela_atual"]["pedidos"]
    trinta = executar("margem_na_janela", {"dias": 30})["janela_atual"]["pedidos"]
    assert trinta > sete


def test_janela_invalida_e_recusada():
    with pytest.raises(ValueError):
        executar("margem_na_janela", {"dias": 0})


def test_relatorio_semanal_traz_a_semana_e_nao_so_o_acumulado():
    d = gerar_relatorio_semanal_dados()
    sem = d["semana"]
    assert sem["dias"] == 7
    assert sem["inicio"] and sem["fim"]
    assert sem["anterior"]["fim"] < sem["inicio"]
    # a semana é um recorte, então não pode repetir o consolidado da base
    assert sem["margem_reais"] < d["margem"]["margem_reais"]
    assert "margem_na_janela" in d["fontes"]


def test_relatorio_aceita_outra_janela():
    d = gerar_relatorio_semanal_dados(dias=30)
    assert d["semana"]["dias"] == 30


def test_html_do_relatorio_mostra_o_periodo_antes_do_acumulado():
    """O relatório deixou de ser semanal quando ganhou seletor de período, mas
    o HTML continuava escrevendo "Semana de" — inclusive numa janela de 391
    dias. A tela já dizia "período"; o arquivo exportado precisa dizer igual."""
    from vertice.render_html import render_relatorio_html
    d = {**gerar_relatorio_semanal_dados(), "resumo_executivo": None}
    html = render_relatorio_html(d)
    assert "Período de" in html
    assert "Semana de" not in html and "semana anterior" not in html
    assert html.index("Período de") < html.index("Acumulado da base")


def test_html_do_relatorio_traz_os_mesmos_graficos_da_tela():
    """O arquivo exportado saía sem a ponte da margem e sem a margem por canal:
    mesmo relatório, conteúdo diferente do que a pessoa tinha acabado de ver."""
    from vertice.render_html import render_relatorio_html
    d = {**gerar_relatorio_semanal_dados(), "resumo_executivo": None}
    html = render_relatorio_html(d)
    assert "Ponte da margem no período" in html
    assert "Margem por canal" in html
    # E os gráficos são CSS puro: o arquivo abre offline, sem script nenhum.
    assert "cascata-barra" in html and "barrav-barra" in html
    assert "<script" not in html


def test_periodo_sem_pedido_nao_derruba_o_relatorio():
    """Regressão: `perda_pos_pedido` levanta ValueError em janela vazia, e o
    relatório aceita período fora da base de propósito — para dizer que não há
    pedido, não para quebrar."""
    from vertice.render_html import render_relatorio_html
    d = gerar_relatorio_semanal_dados(dias=7, ate="2025-06-01")
    assert d["cascata"] is None and d["margem_por_canal"] is None
    html = render_relatorio_html({**d, "resumo_executivo": None})
    assert "Ponte da margem" not in html
