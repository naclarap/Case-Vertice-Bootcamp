"""Seasonality Normalizer — separa sazonalidade normal de mudança estrutural."""
from __future__ import annotations

import pandas as pd

from ..data import carregar_vendas
from .registry import ferramenta


def _mensal() -> pd.DataFrame:
    df = carregar_vendas()
    m = df.groupby("mes", observed=True).agg(
        pedidos=("order_id", "count"),
        receita_bruta=("receita_bruta", "sum"),
        margem=("margem_contribuicao", "sum"),
        desconto=("desconto_reais", "sum"),
    ).reset_index()
    m["dias_no_mes"] = (
        pd.PeriodIndex(m["mes"], freq="M").days_in_month
    )
    # O último mês da base é parcial: normaliza por dia observado, não por dia do mês.
    ult = df["data_pedido"].max()
    parcial = f"{ult.year:04d}-{ult.month:02d}"
    m.loc[m["mes"] == parcial, "dias_no_mes"] = ult.day
    m["mes_parcial"] = m["mes"] == parcial
    m["pedidos_por_dia"] = (m["pedidos"] / m["dias_no_mes"]).round(3)
    m["margem_pct"] = (m["margem"] / m["receita_bruta"] * 100).round(2)
    m["desconto_pct"] = (m["desconto"] / m["receita_bruta"] * 100).round(2)
    return m


@ferramenta(
    "indice_sazonalidade",
    """Índice sazonal por mês = volume do mês / volume médio mensal (>1 = mês acima
    da média). Calculado sobre pedidos/dia para não penalizar meses parciais.
    Rode ANTES de comparar dois períodos, para não ler sazonalidade normal como
    deterioração estrutural.""",
)
def indice_sazonalidade() -> dict:
    m = _mensal()
    media_dia = m["pedidos_por_dia"].mean()
    m["indice_sazonal"] = (m["pedidos_por_dia"] / media_dia).round(3)
    picos = m.nlargest(3, "indice_sazonal")[["mes", "indice_sazonal"]].to_dict(orient="records")
    vales = m.nsmallest(3, "indice_sazonal")[["mes", "indice_sazonal"]].to_dict(orient="records")
    parciais = m.loc[m["mes_parcial"], "mes"].tolist()
    return {
        "metodo": "índice = (pedidos/dia do mês) / (média de pedidos/dia dos meses)",
        "meses": m[["mes", "pedidos", "dias_no_mes", "pedidos_por_dia", "indice_sazonal",
                    "margem_pct", "desconto_pct", "mes_parcial"]].to_dict(orient="records"),
        "picos": picos,
        "vales": vales,
        "meses_parciais": parciais,
        "alerta": (
            f"Meses parciais na base: {parciais}. Não compare o total absoluto de um mês "
            "parcial com um mês cheio; use pedidos/dia ou percentuais."
        ) if parciais else None,
    }


@ferramenta(
    "tendencia_ajustada_sazonalidade",
    """Tendência de uma métrica percentual ao longo dos meses com regressão linear
    sobre o tempo, informando se a inclinação é estatisticamente significante.
    Responde 'isso é tendência estrutural ou ruído/sazonalidade?'.""",
    {"metrica": "uma de: margem_pct, desconto_pct"},
    ["metrica"],
)
def tendencia_ajustada_sazonalidade(metrica: str) -> dict:
    if metrica not in ("margem_pct", "desconto_pct"):
        raise ValueError("metrica deve ser 'margem_pct' ou 'desconto_pct'")
    from scipy import stats as sps

    from .stats import classificar_forca

    m = _mensal().sort_values("mes").reset_index(drop=True)
    # Meses parciais entram no percentual (é razão, não total), mas ficam sinalizados.
    x = range(len(m))
    reg = sps.linregress(list(x), m[metrica].astype(float))
    return {
        "metrica": metrica,
        "serie_mensal": m[["mes", metrica, "mes_parcial"]].to_dict(orient="records"),
        "inclinacao_pp_por_mes": round(float(reg.slope), 4),
        "variacao_total_estimada_pp": round(float(reg.slope) * (len(m) - 1), 3),
        "r2": round(float(reg.rvalue ** 2), 4),
        "p_valor": float(reg.pvalue),
        "n_meses": len(m),
        **classificar_forca(float(reg.pvalue), r2=float(reg.rvalue ** 2), n=len(m)),
        "nota": "n aqui é o número de MESES (não de pedidos); por isso a força raramente "
                "atinge FORTE mesmo com tendência visível. Combine com o teste no grão do pedido.",
    }
