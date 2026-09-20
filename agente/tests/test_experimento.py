"""Teste A/B: atribuição, poder, leitura do resultado e regra de parada.

O que estes testes protegem, além do óbvio:

* a atribuição é DETERMINÍSTICA entre processos — se ela deixar de ser, o grupo
  de um cliente muda de uma execução para outra e o experimento inteiro perde
  o sentido;
* o resultado NUNCA é estimado: sem pedido na janela, sai `disponivel=False`;
* as três coleções do arquivo (políticas, propostas, experimentos) sobrevivem
  umas às gravações das outras — foi um bug real, e é do tipo que só aparece
  quando alguém aprova uma política com teste em andamento.
"""
from __future__ import annotations

import pytest

from vertice.experimento import (atribuicao_de, atribuir, avaliar_regra_de_parada,
                                 criar_experimento, desenho, encerrar_experimento,
                                 experimento_corrente, iniciar_experimento,
                                 resultado, validacao_aa)
from vertice.politica import avancar_estado, criar_proposta, politica_vigente


@pytest.fixture(autouse=True)
def arquivo_temporario(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "politicas.json"))


# ------------------------------------------------------------------ atribuição
def test_atribuicao_e_deterministica_e_estavel():
    a = atribuir("CLI-12360", "semente-fixa")
    b = atribuir("CLI-12360", "semente-fixa")
    assert a == b
    # O valor é fixo por construção (blake2b), não sorteado a cada processo:
    # se isto quebrar, a atribuição deixou de ser reproduzível.
    assert a in ("controle", "teste")
    assert atribuir("CLI-12360", "outra-semente") in ("controle", "teste")


def test_atribuicao_divide_perto_da_proporcao_pedida():
    chaves = [f"ORD-{i}" for i in range(20000)]
    controle = sum(1 for k in chaves if atribuir(k, "s", 0.5) == "controle")
    assert 0.48 < controle / len(chaves) < 0.52

    controle_30 = sum(1 for k in chaves if atribuir(k, "s", 0.3) == "controle")
    assert 0.28 < controle_30 / len(chaves) < 0.32


def test_atribuicao_de_explica_a_si_mesma():
    info = atribuicao_de("CLI-1", "s")
    assert info["grupo"] in ("controle", "teste")
    assert "nada é gravado" in info["nota"]


# ---------------------------------------------------------------- poder do teste
def test_desenho_calcula_as_duas_unidades_e_diz_qual_mede_volume():
    d = desenho(mde_relativo=0.05)
    por_unidade = {u["unidade"]: u for u in d["unidades"]}
    assert set(por_unidade) == {"pedido", "cliente"}
    # Só a aleatorização por cliente enxerga volume.
    assert por_unidade["cliente"]["mede_volume"] is True
    assert por_unidade["pedido"]["mede_volume"] is False
    for u in por_unidade.values():
        assert u["n_por_grupo"] > 0
        assert u["desvio_padrao"] > 0


def test_desenho_declara_inviabilidade_em_vez_de_esconder():
    """A base tem 331 clientes e dispersão altíssima de pedidos por cliente: o
    teste que mede volume não cabe nela, e o desenho precisa dizer isso."""
    d = desenho(mde_relativo=0.05)
    cliente = next(u for u in d["unidades"] if u["unidade"] == "cliente")
    assert cliente["viavel_com_a_base_atual"] is False
    assert cliente["n_total"] > cliente["unidades_disponiveis_na_base"]
    assert "NÃO é viável" in d["leitura"]


def test_efeito_menor_exige_amostra_maior():
    grosso = desenho(mde_relativo=0.20)
    fino = desenho(mde_relativo=0.05)
    n_grosso = next(u for u in grosso["unidades"] if u["unidade"] == "pedido")["n_por_grupo"]
    n_fino = next(u for u in fino["unidades"] if u["unidade"] == "pedido")["n_por_grupo"]
    assert n_fino > n_grosso


# ------------------------------------------------------------------ ciclo de vida
def _experimento_pronto(**kw):
    return criar_experimento(proposta_id="prop_1", teto_pct=20,
                             responsavel="Ana Diretoria", **kw)


def test_experimento_nasce_planejado_e_sem_janela():
    exp = _experimento_pronto()
    assert exp["estado"] == "planejado"
    assert exp["inicio"] is None
    r = resultado(exp)
    assert r["disponivel"] is False
    assert "ainda não foi iniciado" in r["motivo"]


def test_nao_da_para_iniciar_duas_vezes_nem_encerrar_sem_motivo():
    exp = iniciar_experimento(_experimento_pronto()["id"], quem="Carlos CFO")
    with pytest.raises(ValueError, match="planejado"):
        iniciar_experimento(exp["id"], quem="Carlos CFO")
    with pytest.raises(ValueError, match="motivo"):
        encerrar_experimento(exp["id"], quem="Carlos CFO", motivo="")
    encerrado = encerrar_experimento(exp["id"], quem="Carlos CFO", motivo="fim da janela")
    assert encerrado["estado"] == "encerrado"
    assert encerrado["motivo_encerramento"] == "fim da janela"


def test_toda_transicao_registra_quem_e_quando():
    exp = iniciar_experimento(_experimento_pronto()["id"], quem="Carlos CFO")
    eventos = {h["evento"]: h for h in exp["historico"]}
    assert eventos["planejado"]["quem"] == "Ana Diretoria"
    assert eventos["iniciado"]["quem"] == "Carlos CFO"
    assert all(h.get("quando") for h in exp["historico"])


# --------------------------------------------------------------------- resultado
def test_sem_pedido_na_janela_nao_inventa_numero():
    """Janela no futuro: a base histórica acaba antes, então não há o que medir."""
    exp = iniciar_experimento(_experimento_pronto()["id"], quem="Ana",
                              inicio="2099-01-01")
    r = resultado(exp)
    assert r["disponivel"] is False
    assert r["pedidos_na_janela"] == 0
    assert "não há o que medir" in r["motivo"]
    # E a regra de parada não se pronuncia sobre o que não foi medido.
    assert avaliar_regra_de_parada(exp, r)["veredicto"] == "sem dado"


def test_resultado_real_em_janela_com_dados():
    exp = iniciar_experimento(
        _experimento_pronto(unidade="cliente", duracao_dias=60)["id"],
        quem="Ana", inicio="2023-10-01")
    r = resultado(exp)
    assert r["disponivel"] is True
    assert r["pedidos_na_janela"] > 0
    assert r["unidades_controle"] > 0 and r["unidades_teste"] > 0
    volume = r["metricas"]["pedidos_por_cliente"]
    assert volume["suficiente"] is True
    assert 0 <= volume["p_valor"] <= 1
    assert len(volume["ic95_diferenca"]) == 2


def test_unidade_pedido_nao_finge_medir_volume():
    exp = iniciar_experimento(
        _experimento_pronto(unidade="pedido", duracao_dias=60)["id"],
        quem="Ana", inicio="2023-10-01")
    r = resultado(exp)
    assert "pedidos_por_cliente" not in r["metricas"]
    parada = avaliar_regra_de_parada(exp, r)
    assert parada["veredicto"] == "sem dado"
    assert "não mede volume" in parada["explicacao"]


def test_regra_de_parada_manda_parar_com_queda_significativa():
    exp = _experimento_pronto()
    res_falso = {
        "disponivel": True,
        "metricas": {"pedidos_por_cliente": {
            "suficiente": True, "diferenca_relativa_pct": -8.0, "p_valor": 0.001}},
    }
    parada = avaliar_regra_de_parada(exp, res_falso, queda_maxima_pct=2.0)
    assert parada["veredicto"] == "parar"
    assert parada["queda_observada_pct"] == 8.0

    # Mesma queda sem significância não interrompe nada.
    res_falso["metricas"]["pedidos_por_cliente"]["p_valor"] = 0.42
    assert avaliar_regra_de_parada(exp, res_falso)["veredicto"] == "continuar"


def test_volume_que_sobe_nao_vira_queda_negativa_no_texto():
    exp = _experimento_pronto()
    res_falso = {"disponivel": True, "metricas": {"pedidos_por_cliente": {
        "suficiente": True, "diferenca_relativa_pct": 12.0, "p_valor": 0.01}}}
    parada = avaliar_regra_de_parada(exp, res_falso)
    assert parada["veredicto"] == "continuar"
    assert "alta de 12" in parada["explicacao"]


# ------------------------------------------------------------------ validação A/A
def test_validacao_aa_afere_a_regua():
    aa = validacao_aa(semente="afericao", unidade="cliente", dias=120)
    assert aa["tipo"] == "A/A"
    assert aa["disponivel"] is True
    # Dois grupos sem tratamento nenhum não devem diferir significativamente.
    assert aa["passou"] is True
    # E, com esta base, a leitura precisa avisar que passar não atesta poder.
    assert aa["maior_diferenca_sem_tratamento_pct"] is not None


# ----------------------------------------------- convivência das três coleções
def test_aprovar_politica_nao_apaga_o_experimento(fluxo_completo):
    """Regressão: `definir_politica` regravava o arquivo só com as políticas,
    e o experimento em andamento — mais as propostas — sumiam junto."""
    exp = iniciar_experimento(_experimento_pronto()["id"], quem="Ana")
    proposta = criar_proposta(teto_pct=20, responsavel="Ana")
    for destino, quem in [("simulacao", "Ana"), ("aprovacao", "Ana"), ("ativa", "CFO")]:
        proposta = avancar_estado(proposta["id"], destino, quem=quem)

    assert politica_vigente() is not None          # a política foi aplicada
    ainda_la = experimento_corrente()
    assert ainda_la is not None and ainda_la["id"] == exp["id"]
    assert ainda_la["estado"] == "rodando"
