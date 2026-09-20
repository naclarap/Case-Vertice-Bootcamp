"""Carga e normalização dos dados.

Todas as decisões de tratamento aplicadas aqui estão documentadas em
PREMISSAS.md. Nada é filtrado silenciosamente: `resumo_tratamento()` devolve o
que foi excluído e por quê, e esse resumo é exposto ao agente como ferramenta.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from . import config

# Registro do que foi descartado na carga, para auditoria.
_TRATAMENTO: dict[str, Any] = {}


def _caminho(nome: str):
    p = config.DATA_DIR / config.ARQUIVOS[nome]
    if not p.exists():
        raise FileNotFoundError(
            f"Arquivo '{p}' não encontrado. Coloque os CSVs em {config.DATA_DIR} "
            f"ou aponte a variável de ambiente VERTICE_DATA_DIR para a pasta correta."
        )
    return p


@lru_cache(maxsize=None)
def _raw(nome: str) -> pd.DataFrame:
    # utf-8-sig: os CSVs vêm com BOM, que senão vira parte do nome da 1ª coluna.
    return pd.read_csv(_caminho(nome), encoding="utf-8-sig")


def carregar_bruto(nome: str) -> pd.DataFrame:
    """Tabela exatamente como está no CSV, SEM nenhum filtro ou derivada.

    As demais funções de carga aplicam as premissas (só aprovados, descarte de
    linha vazia, colunas derivadas) — o que é certo para calcular margem e
    errado para auditar qualidade de dado: uma auditoria que só enxerga a base
    já limpa não encontra o que a limpeza escondeu. Use esta aqui em
    `engine/auditoria.py`, e as outras em todo o resto.
    """
    if nome not in config.ARQUIVOS:
        raise ValueError(
            f"tabela '{nome}' não existe. Disponíveis: {sorted(config.ARQUIVOS)}"
        )
    return _raw(nome).copy()


@lru_cache(maxsize=None)
def carregar_vendas(apenas_aprovados: bool = True) -> pd.DataFrame:
    """Carrega vendas.csv com as colunas derivadas usadas pelo motor.

    apenas_aprovados=True (padrão) é a base para QUALQUER número financeiro de
    decisão. Use False somente para exploração explícita do funil de pagamento.
    """
    df = _raw("vendas").copy()
    n0 = len(df)

    # Uma linha totalmente vazia no fim do arquivo (só order_id preenchido).
    df = df.dropna(subset=["status_pagamento", "receita_bruta"])
    n_vazias = n0 - len(df)

    df["data_pedido"] = pd.to_datetime(df["data_pedido"])
    df["ano"] = df["data_pedido"].dt.year
    df["mes"] = df["data_pedido"].dt.to_period("M").astype(str)
    df["trimestre"] = df["data_pedido"].dt.to_period("Q").astype(str)
    df["devolvido"] = df["devolvido"].astype(str).str.lower().isin(["true", "1"])

    n_aprov = int((df["status_pagamento"] == config.STATUS_RECEITA_VALIDA).sum())
    rb_total = float(df["receita_bruta"].sum())
    rb_aprov = float(
        df.loc[df["status_pagamento"] == config.STATUS_RECEITA_VALIDA, "receita_bruta"].sum()
    )

    _TRATAMENTO["vendas"] = {
        "linhas_originais": n0,
        "linhas_vazias_descartadas": int(n_vazias),
        "pedidos_aprovados": n_aprov,
        "pedidos_nao_aprovados": int(len(df) - n_aprov),
        "receita_bruta_reportada": round(rb_total, 2),
        "receita_bruta_aprovada": round(rb_aprov, 2),
        "pct_receita_nao_realizada": round((1 - rb_aprov / rb_total) * 100, 2),
        "janela": [str(df["data_pedido"].min()), str(df["data_pedido"].max())],
    }

    if apenas_aprovados:
        df = df[df["status_pagamento"] == config.STATUS_RECEITA_VALIDA].copy()

    # Derivadas percentuais. receita_bruta > 0 em toda a base; o guard existe
    # para não quebrar caso um pedido zerado apareça numa carga futura.
    rb = df["receita_bruta"].replace(0, np.nan)
    df["desconto_pct"] = (df["desconto_reais"] / rb).fillna(0.0)
    df["margem_pct"] = (df["margem_contribuicao"] / rb).fillna(0.0)
    df["custo_pct"] = (df["custo_produto"] / rb).fillna(0.0)
    df["frete_pct"] = (df["custo_frete"] / rb).fillna(0.0)
    df["frete_gratis"] = df["custo_frete"] == 0
    df["faixa_desconto"] = faixa_desconto(df["desconto_pct"])
    return df


def faixa_desconto(serie: pd.Series) -> pd.Series:
    """Classifica o desconto percentual nas faixas de config.FAIXAS_DESCONTO."""
    bordas = [config.FAIXAS_DESCONTO[0][1] - 1e-9] + [f[2] for f in config.FAIXAS_DESCONTO]
    rotulos = [f[0] for f in config.FAIXAS_DESCONTO]
    return pd.cut(serie, bins=bordas, labels=rotulos, ordered=True)


@lru_cache(maxsize=None)
def carregar_clientes() -> pd.DataFrame:
    return _raw("clientes").copy()


@lru_cache(maxsize=None)
def carregar_estoque() -> pd.DataFrame:
    return _raw("estoque").copy()


@lru_cache(maxsize=None)
def carregar_atendimento() -> pd.DataFrame:
    df = _raw("atendimento").copy()
    df["data_abertura"] = pd.to_datetime(df["data_abertura"])
    return df


@lru_cache(maxsize=None)
def carregar_atendimento_vinculado(ano: int | None = None) -> pd.DataFrame:
    """Tickets LIGADOS a um pedido aprovado e abertos DEPOIS dele.

    Duas regras de vínculo, ambas necessárias para o custo de atendimento ser
    atribuível ao pedido:

    1. O ticket tem `order_id` que existe entre os pedidos aprovados. Ticket sem
       pedido correspondente não tem margem à qual ser debitado.
    2. O ticket foi aberto em data igual ou posterior à do pedido. 13,0% dos
       tickets vinculados abrem ANTES do pedido a que se referem — não podem ter
       sido causados por ele, e entram no custo apenas por coincidência de
       `order_id`. Ficam de fora.

    `custo_operacional_ticket` é custo fixo por canal de entrada na base
    (R$ 2 ChatBot · R$ 15 e-mail, telefone e WhatsApp · R$ 45 Reclame Aqui).
    """
    tickets = carregar_atendimento()
    vendas = carregar_vendas()[["order_id", "data_pedido", "devolvido", "canal", "ano"]]
    j = tickets.merge(vendas, on="order_id", how="inner", suffixes=("", "_venda"))
    j = j[j["data_abertura"] >= j["data_pedido"]]
    if ano is not None:
        j = j[j["ano"] == int(ano)]
    return j.copy()


@lru_cache(maxsize=None)
def carregar_marketing() -> pd.DataFrame:
    """marketing.csv — ATENÇÃO: `receita_gerada` é inflada por atribuição
    sobreposta (ver PREMISSAS.md #2). Nunca use para valor absoluto em R$.
    """
    df = _raw("marketing").copy()
    df["data_inicio"] = pd.to_datetime(df["data_inicio"])
    df["data_fim"] = pd.to_datetime(df["data_fim"])
    return df


def resumo_tratamento() -> dict[str, Any]:
    """O que foi excluído na carga e por quê — para auditoria e para o agente."""
    if "vendas" not in _TRATAMENTO:
        carregar_vendas()
    t = dict(_TRATAMENTO["vendas"])
    t["premissas_aplicadas"] = [
        "Métricas financeiras usam apenas status_pagamento == 'Aprovado' "
        f"({t['pct_receita_nao_realizada']}% da receita bruta reportada nunca foi recebida).",
        "Linha totalmente vazia ao final de vendas.csv descartada.",
        "marketing.receita_gerada NÃO é usada para nenhuma estimativa em R$ "
        "(atribuição sobreposta infla o total ~17x).",
        "margem_contribuicao é anterior a devolução: devolvido=True é um vazamento "
        "adicional, não descontado da margem reportada.",
    ]
    return t
