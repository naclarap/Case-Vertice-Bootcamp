"""Testes de integridade da base e das premissas de tratamento."""
import pytest

from vertice import config
from vertice.data import resumo_tratamento
from vertice.engine import executar


def test_identidade_contabil_por_pedido(vendas):
    """margem + desconto + custo_produto + frete == receita_bruta, pedido a pedido."""
    soma = (vendas.desconto_reais + vendas.custo_produto
            + vendas.custo_frete + vendas.margem_contribuicao)
    dif = (soma - vendas.receita_bruta).abs()
    assert dif.max() < 1e-6, f"identidade contábil quebrou em {(dif > 1e-6).sum()} pedidos"


def test_identidade_contabil_percentual_fecha_em_100(vendas):
    """margem% + desconto% + custo% + frete% == 100% (por definição)."""
    total = (vendas.margem_pct + vendas.desconto_pct
             + vendas.custo_pct + vendas.frete_pct) * 100
    assert total.sub(100).abs().max() < 1e-6


def test_consolidado_fecha_em_100_pp():
    d = executar("margem_consolidada")["decomposicao_mece_pct"]
    assert abs(d["soma"] - 100) < 0.05, d


def test_apenas_pedidos_aprovados_na_base_financeira(vendas):
    assert set(vendas.status_pagamento.unique()) == {config.STATUS_RECEITA_VALIDA}


def test_receita_nao_aprovada_e_material(vendas_todas):
    """~11,7% da receita reportada nunca foi recebida — a premissa existe por isso."""
    t = resumo_tratamento()
    assert 10 < t["pct_receita_nao_realizada"] < 13
    assert t["receita_bruta_aprovada"] < t["receita_bruta_reportada"]


def test_linha_vazia_descartada():
    assert resumo_tratamento()["linhas_vazias_descartadas"] == 1


def test_sem_pedidos_duplicados(vendas):
    assert not vendas.order_id.duplicated().any()


@pytest.mark.parametrize("col,minimo,maximo", [
    ("desconto_pct", 0.0, 0.40),   # desconto nunca passa de 40% da receita
    ("custo_pct", 0.30, 0.50),     # custo de produto fica entre 30% e 50%
    ("frete_pct", 0.0, 2.0),       # frete PODE passar de 100% em ticket baixo
    ("margem_pct", -1.5, 0.70),    # margem PODE ser negativa (frete > receita)
])
def test_percentuais_em_intervalo_esperado(vendas, col, minimo, maximo):
    assert vendas[col].between(minimo, maximo).all(), (
        f"{col} fora de [{minimo}, {maximo}]: min={vendas[col].min()} max={vendas[col].max()}"
    )


def test_existem_pedidos_com_margem_negativa(vendas):
    """Não é erro de dado: em ticket baixo o frete supera a margem do produto.
    O motor precisa expor isso em vez de tratar como outlier a limpar."""
    neg = vendas[vendas.margem_contribuicao < 0]
    assert len(neg) > 0
    assert neg.receita_bruta.mean() < vendas.receita_bruta.mean() / 3
    assert (neg.custo_frete > 0).mean() > 0.9  # praticamente todos pagaram frete
