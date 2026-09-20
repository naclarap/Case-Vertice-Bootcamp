"""Roteamento determinístico de intenção (agent/router.py).

Caso que motivou o módulo: "O que aconteceria se eu limitasse o desconto de Moda
no Email Marketing a 17%?" não era respondida — a extração não conhecia
categoria, nada separava teto de aplicação, e a pista por palavra-chave casava
"Email Marketing" com *marketing*, sugerindo ranking de ROAS.
"""
import pytest

from vertice.agent import router
from vertice.agent.react import AgenteMargem
from vertice.agent.router import (APLICAR_DESCONTO, MARGEM_CONSOLIDADA,
                                  MARGEM_POR_DIMENSAO, ORIGEM_ROTEADOR,
                                  PERGUNTA_COMPLEXA, TETO_DESCONTO,
                                  TOOL_CALLED_SUCCESS, extrair_parametros, rotear,
                                  validar_parametros)

RESPOSTA_OK = ("FATO: x.\nINFERÊNCIA: y.\nRECOMENDAÇÃO: z.\n"
               "FORÇA DA EVIDÊNCIA: FRACA")


# ============================================================ TESTE 1 (teto)
def test_1_limitar_moda_no_email_marketing_a_17():
    r = rotear("O que aconteceria se eu limitasse o desconto de Moda no "
               "Email Marketing a 17%?")
    assert r.intencao == TETO_DESCONTO
    assert r.ferramenta == "simular_teto_desconto"
    assert r.parametros == {"teto_pct": 17.0, "canal": "Email Marketing",
                            "categoria": "Moda"}
    assert r.origem == ORIGEM_ROTEADOR
    assert r.determinado


def test_1b_a_ferramenta_e_realmente_executada_pelo_agente():
    """O agente não pode responder "a ferramenta não retornou": o resultado
    entra na conversa já calculado, antes do primeiro turno do modelo."""
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    tr = ag.investigar("O que aconteceria se eu limitasse o desconto de Moda "
                       "no Email Marketing a 17%?")

    assert "simular_teto_desconto" in tr.ferramentas_usadas
    assert tr.roteamento["intencao"] == TETO_DESCONTO
    assert tr.roteamento["status_ferramenta"] == TOOL_CALLED_SUCCESS

    obs = [p for p in tr.passos
           if p.tipo == "observacao" and p.ferramenta == "simular_teto_desconto"]
    assert len(obs) == 1
    resultado = obs[0].conteudo
    assert resultado["recorte"] == {"canal": "Email Marketing", "categoria": "Moda"}
    assert resultado["teto_aplicado_pct"] == 17.0
    assert resultado["pedidos_afetados"] > 0
    # a chamada foi decidida pelo código, não pelo modelo
    assert obs[0].origem == ORIGEM_ROTEADOR


# ======================================================= TESTE 2 (aplicação)
def test_2_aplicar_17_em_moda_no_email_marketing():
    r = rotear("E se eu aplicasse 17% de desconto em Moda no Email Marketing?")
    assert r.intencao == APLICAR_DESCONTO
    assert r.ferramenta == "simular_desconto_em_segmento"
    assert r.parametros == {"desconto_pct": 17.0, "canal": "Email Marketing",
                            "categoria": "Moda"}


def test_2b_teto_e_aplicacao_dao_resultados_diferentes():
    """Não é preciosismo de nome: limitar o que passa de 17% e colocar o
    segmento inteiro em 17% são contas diferentes."""
    from vertice.engine import executar
    seg = {"canal": "Email Marketing", "categoria": "Moda"}
    teto = executar("simular_teto_desconto", {"teto_pct": 17, **seg})
    aplicar = executar("simular_desconto_em_segmento", {"desconto_pct": 17, **seg})
    # o teto SÓ mexe em quem está acima dele; aplicar mexe no segmento inteiro
    assert teto["pedidos_afetados"] < aplicar["pedidos_no_segmento"]
    assert teto["margem_recuperada_reais"] > 0          # teto recupera margem
    assert aplicar["variacao_desconto_reais"] > 0       # aplicar 17% aumenta desconto


# ========================================================= TESTE 3 (sem recorte)
def test_3_limitar_descontos_a_20_sem_recorte():
    r = rotear("Se eu limitar os descontos a 20%, qual o impacto?")
    assert r.ferramenta == "simular_teto_desconto"
    assert r.parametros == {"teto_pct": 20.0}
    assert "canal" not in r.parametros and "categoria" not in r.parametros


# ============================================================ TESTE 4 (dimensão)
def test_4_qual_canal_tem_menor_margem():
    r = rotear("Qual canal tem menor margem?")
    assert r.intencao == MARGEM_POR_DIMENSAO
    assert r.ferramenta == "margem_por_dimensao"
    assert r.parametros["dimensao"] == "canal"


def test_4b_margem_consolidada_e_reconhecida():
    r = rotear("Qual é a margem consolidada?")
    assert r.intencao == MARGEM_CONSOLIDADA
    assert r.ferramenta == "margem_consolidada"


# ========================================================== TESTE 5 (complexa)
def test_5_pergunta_aberta_nao_e_roteada_e_vai_para_o_react():
    r = rotear("Por que o Marketplace tem margem menor e o que poderia ser feito?")
    assert r.intencao == PERGUNTA_COMPLEXA
    assert r.ferramenta is None


def test_5b_agente_investiga_livremente_na_pergunta_complexa():
    """O ReAct continua no lugar: sem rota fixa, quem escolhe é o modelo."""
    roteiro = ['AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}',
               'AÇÃO: custo_assimetria_frete\nPARÂMETROS: {"canal": "Marketplace"}',
               RESPOSTA_OK]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("Por que o Marketplace tem margem menor e o que poderia ser feito?")
    assert tr.roteamento["intencao"] == PERGUNTA_COMPLEXA
    assert tr.roteamento["ferramenta"] is None
    assert "margem_por_dimensao" in tr.ferramentas_usadas
    assert "custo_assimetria_frete" in tr.ferramentas_usadas


# ================================================= TESTE 6 (não inventar canal)
def test_6_sem_canal_na_pergunta_nenhum_canal_e_inventado():
    r = rotear("Limite Moda a 17%.")
    assert r.ferramenta == "simular_teto_desconto"
    assert r.parametros["categoria"] == "Moda"
    assert r.parametros["teto_pct"] == 17.0
    assert "canal" not in r.parametros


def test_6b_sem_canal_a_ferramenta_roda_no_escopo_que_aceita():
    """simular_teto_desconto não exige canal: o teto vale para Moda em todos os
    canais. Se fosse obrigatório, o roteador reportaria a falta em vez de supor."""
    params, problemas = validar_parametros(
        "simular_teto_desconto", {"teto_pct": 17.0, "categoria": "Moda"})
    assert problemas == []
    from vertice.engine import executar
    r = executar("simular_teto_desconto", params)
    assert r["recorte"] == {"categoria": "Moda"}


def test_6c_parametro_obrigatorio_ausente_e_reportado_nao_preenchido():
    _, problemas = validar_parametros("margem_por_dimensao", {})
    assert any("dimensao" in p for p in problemas)


# ==================================================== TESTE 7 (variações)
@pytest.mark.parametrize("pergunta", [
    "O que aconteceria se eu limitasse o desconto de Moda no Email Marketing a 17%?",
    "limitar o desconto de moda no email marketing para 17%",
    "teto de 17% para Moda no Email Marketing",
    "não deixar o desconto passar de 17% em Moda no Email Marketing",
    "quero um desconto máximo de 17% em Moda no Email Marketing",
    "NÃO ULTRAPASSAR 17% DE DESCONTO EM MODA NO EMAIL MARKETING",
])
def test_7_variacoes_chegam_na_mesma_intencao_e_parametros(pergunta):
    r = rotear(pergunta)
    assert r.intencao == TETO_DESCONTO
    assert r.ferramenta == "simular_teto_desconto"
    assert r.parametros == {"teto_pct": 17.0, "canal": "Email Marketing",
                            "categoria": "Moda"}


# ------------------------------------------------- extração de parâmetros
def test_extracao_reconhece_canal_categoria_mes_e_percentual():
    a = extrair_parametros("simule 30% no Marketplace em novembro para Beleza")
    assert a["percentual"] == 30.0
    assert a["canal"] == "Marketplace"
    assert a["categoria"] == "Beleza"
    assert a["mes"] == "2023-11"


def test_extracao_devolve_o_valor_canonico_da_base():
    a = extrair_parametros("desconto em moda no email marketing")
    assert a["canal"] == "Email Marketing"     # não 'email marketing'
    assert a["categoria"] == "Moda"            # não 'moda'


def test_extracao_nao_confunde_palavra_maior_com_valor_do_dominio():
    """'moda' não pode casar dentro de 'modalidade'."""
    a = extrair_parametros("qual a modalidade de pagamento mais usada?")
    assert "categoria" not in a


def test_mes_ambiguo_nao_vira_palpite():
    """Janeiro existe em 2023 e 2024 nesta base: sem o ano, fica de fora."""
    assert "mes" not in extrair_parametros("simule 20% em janeiro")
    assert extrair_parametros("simule 20% em janeiro de 2024")["mes"] == "2024-01"


def test_canais_e_categorias_vem_da_base_nao_de_lista_fixa():
    dominio = router.valores_do_dominio()
    from vertice.data import carregar_vendas
    df = carregar_vendas()
    assert dominio["canal"] == sorted(df["canal"].dropna().astype(str).unique())
    assert dominio["categoria"] == sorted(df["categoria"].dropna().astype(str).unique())


def test_email_marketing_nao_dispara_mais_a_pista_de_roas():
    """Regressão direta: a pista casava 'Email Marketing' com *marketing* e
    sugeria ranking_roas_canais na pergunta de teto."""
    from vertice.agent.prompts import sugerir_ferramentas
    sugeridas = sugerir_ferramentas("limitar o desconto de Moda no Email Marketing a 17%")
    assert sugeridas[0] == "simular_teto_desconto"


# ------------------------------------------------------------ validação
def test_validacao_normaliza_sem_alterar_o_valor_canonico():
    params, problemas = validar_parametros(
        "simular_teto_desconto",
        {"teto_pct": 17, "canal": "email marketing", "categoria": "MODA"})
    assert problemas == []
    assert params["canal"] == "Email Marketing"
    assert params["categoria"] == "Moda"


def test_validacao_recusa_percentual_fora_da_faixa():
    _, problemas = validar_parametros("simular_teto_desconto", {"teto_pct": 250})
    assert any("0–100" in p for p in problemas)


def test_validacao_recusa_canal_inexistente():
    _, problemas = validar_parametros("simular_teto_desconto",
                                      {"teto_pct": 20, "canal": "Facebook Ads"})
    assert any("inexistente" in p for p in problemas)


# --------------------------------------------------- estados de execução
def test_trace_registra_a_origem_da_decisao_e_o_status_da_ferramenta():
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    tr = ag.investigar("Se eu limitar os descontos a 20%, qual o impacto?")
    d = tr.to_dict()
    assert d["roteamento"]["origem"] == ORIGEM_ROTEADOR
    assert d["roteamento"]["ferramenta"] == "simular_teto_desconto"
    assert d["roteamento"]["parametros"] == {"teto_pct": 20.0}
    assert d["roteamento"]["status_ferramenta"] == TOOL_CALLED_SUCCESS
    # o trace salvo continua serializável
    import json
    json.loads(tr.to_json())


def test_erro_de_ferramenta_e_distinguivel_de_ferramenta_nao_chamada():
    from vertice.agent.trace import Trace
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    tr = Trace(pergunta="x")
    ag._chamar_ferramenta("simular_teto_desconto", {"teto_pct": 20, "canal": "Inexistente"},
                          tr, iteracao=1)
    erro = [p for p in tr.passos if p.tipo == "erro"][0]
    from vertice.agent.router import TOOL_CALLED_ERROR
    assert erro.status == TOOL_CALLED_ERROR      # executou e falhou
    assert "inexistente" in str(erro.conteudo)   # com o motivo real


def test_pergunta_sem_rota_marca_ferramenta_nao_chamada():
    from vertice.agent.router import TOOL_NOT_CALLED
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    tr = ag.investigar("Por que a margem caiu e o que fazer?")
    assert tr.roteamento["status_ferramenta"] == TOOL_NOT_CALLED


def test_roteamento_vale_nos_dois_modos_de_ferramenta():
    """§9: o roteador entrega parâmetros estruturados ao executor antes do
    primeiro turno do modelo, então independe de function calling nativo estar
    disponível — o fallback textual recebe o mesmo resultado já apurado."""
    for modo in ("texto", "nativo"):
        ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], modo=modo, verbose=False)
        tr = ag.investigar("Se eu limitar os descontos a 20%, qual o impacto?")
        assert tr.roteamento["status_ferramenta"] == TOOL_CALLED_SUCCESS, modo
        assert "simular_teto_desconto" in tr.ferramentas_usadas, modo


def test_roteador_nao_repete_chamada_que_a_semente_ja_fez():
    """A semente executa margem_consolidada; rotear para ela de novo só
    duplicaria a chamada no trace."""
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    tr = ag.investigar("Qual é a margem consolidada?")
    assert tr.ferramentas_usadas.count("margem_consolidada") == 1
    assert "não repetida" in tr.roteamento["nota"]


def test_falha_do_roteador_nao_derruba_a_investigacao(monkeypatch):
    """O roteador é auxiliar: se quebrar, o ReAct assume como antes."""
    import vertice.agent.react as react

    def _explode(_):
        raise RuntimeError("roteador quebrado")
    monkeypatch.setattr(react, "rotear", _explode)

    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    tr = ag.investigar("Se eu limitar os descontos a 20%, qual o impacto?")
    assert tr.resposta_final                      # respondeu mesmo assim
    assert "margem_consolidada" in tr.ferramentas_usadas


def test_percentual_sem_simbolo_so_vale_em_contexto_de_desconto():
    """"limitar o desconto a 17" funciona; "top 5 canais" não vira 5%."""
    assert rotear("limitar o desconto de Moda a 17").parametros["teto_pct"] == 17.0
    assert "percentual" not in extrair_parametros("me mostre o top 5 canais por margem")
    assert "percentual" not in extrair_parametros("margem dos últimos 7 dias")


# --------------------- buracos encontrados testando perguntas de verdade
def test_pergunta_sobre_relacao_desconto_margem_vai_para_a_tabela_de_faixas():
    """Sem rota, o modelo INVENTOU as seis linhas da tabela de faixas — com
    valores que somados passavam da receita bruta da base."""
    from vertice.agent.router import RELACAO_DESCONTO_MARGEM
    r = rotear("Existe relação entre desconto e margem?")
    assert r.intencao == RELACAO_DESCONTO_MARGEM
    assert r.ferramenta == "tabela_faixas_desconto"


def test_estatisticamente_pior_roteia_para_anova():
    """"estatisticamente pior" não casava com "estatisticamente significativ" e
    a resposta saiu dizendo que não havia dado por canal — havia."""
    from vertice.agent.router import TESTE_ESTATISTICO
    r = rotear("O Marketplace é estatisticamente pior?")
    assert r.intencao == TESTE_ESTATISTICO
    assert r.ferramenta == "anova_um_fator"
    assert r.parametros == {"metrica": "margem_contribuicao", "coluna_grupo": "canal"}


def test_anova_agrupa_por_categoria_quando_a_pergunta_e_de_categoria():
    r = rotear("A diferença entre Moda e Beleza é estatisticamente significativa?")
    assert r.parametros["coluna_grupo"] == "categoria"


def test_essas_perguntas_executam_a_ferramenta_de_fato():
    for pergunta, esperada in [
        ("Existe relação entre desconto e margem?", "tabela_faixas_desconto"),
        ("O Marketplace é estatisticamente pior?", "anova_um_fator"),
    ]:
        ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
        tr = ag.investigar(pergunta)
        assert esperada in tr.ferramentas_usadas, pergunta
        assert tr.roteamento["status_ferramenta"] == TOOL_CALLED_SUCCESS, pergunta
