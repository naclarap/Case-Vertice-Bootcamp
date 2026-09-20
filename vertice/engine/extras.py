"""Ferramentas complementares: devolução (fecha o MECE) e marketing (uso seguro)."""
from __future__ import annotations

import pandas as pd

from ..data import carregar_marketing, carregar_vendas
from .registry import ferramenta


@ferramenta(
    "impacto_devolucoes",
    """Vazamento de margem por devolução — o último componente do MECE
    (Receita − Desconto − Custo − Frete − Devolução). ATENÇÃO: a coluna
    margem_contribuicao NÃO desconta devolução, então este valor é adicional ao
    déficit já medido. Abre por canal, categoria, motivo, mês ou trimestre.""",
    {"por": "dimensão de abertura: canal, categoria, motivo_devolucao, mes ou "
            "trimestre (padrão canal)"},
)
def impacto_devolucoes(por: str = "canal") -> dict:
    df = carregar_vendas()
    # 'mes' e 'trimestre' entraram porque "quantos pedidos foram devolvidos em
    # maio?" não tinha resposta: o agente dizia, corretamente, que não conseguia
    # desagregar — só que a coluna existe e a abertura é a mesma das outras.
    # Recusa honesta continua sendo recusa; aqui a lacuna era do motor.
    dimensoes = ("canal", "categoria", "motivo_devolucao", "mes", "trimestre")
    if por not in dimensoes:
        raise ValueError(f"por deve ser um de {dimensoes}")
    dev = df[df["devolvido"]]
    g = df.groupby(por, observed=True).apply(
        lambda d: pd.Series({
            "pedidos": len(d),
            # A CONTAGEM, não só a taxa: sem ela a pergunta "quantos pedidos
            # foram devolvidos em maio?" exigiria multiplicar taxa por pedidos —
            # conta do modelo, que é exatamente o que este projeto não aceita.
            "pedidos_devolvidos": int(d["devolvido"].sum()),
            "taxa_devolucao_pct": d["devolvido"].mean() * 100,
            "margem_perdida_reais": d.loc[d["devolvido"], "margem_contribuicao"].sum(),
            "receita_devolvida": d.loc[d["devolvido"], "receita_bruta"].sum(),
        }), include_groups=False).round(2).reset_index().sort_values("margem_perdida_reais",
                                                                     ascending=False)
    rb = float(df["receita_bruta"].sum())
    perda = float(dev["margem_contribuicao"].sum())
    return {
        "dimensao": por,
        "taxa_devolucao_global_pct": round(float(df["devolvido"].mean()) * 100, 2),
        "margem_perdida_total_reais": round(perda, 2),
        "impacto_pp_na_margem_consolidada": round(perda / rb * 100, 2),
        "linhas": g.to_dict(orient="records"),
        "nota": "margem_contribuicao é PRÉ-devolução; esta perda soma ao déficit, não está nele.",
    }


@ferramenta(
    "ranking_roas_canais",
    """Ranking RELATIVO de eficiência de marketing por canal (mediana de ROAS e CAC).
    PROIBIDO usar para valor em R$: a coluna receita_gerada é inflada por atribuição
    sobreposta (Linear/First Click/Last Click contam a mesma venda várias vezes) e
    soma ~17x a receita real de vendas.csv. Serve apenas para ordenar canais.""",
)
def ranking_roas_canais() -> dict:
    mk = carregar_marketing()
    v = carregar_vendas()
    g = mk.groupby("canal", observed=True).agg(
        campanhas=("campanha_id", "count"),
        roas_mediano=("roas", "median"),
        cac_mediano=("cac", "median"),
        investimento_reais=("investimento_reais", "sum"),
    ).round(2).reset_index().sort_values("roas_mediano", ascending=False)
    g["posicao_roas"] = range(1, len(g) + 1)

    ini, fim = v["data_pedido"].min(), v["data_pedido"].max()
    janela = mk[(mk["data_inicio"] >= ini) & (mk["data_inicio"] <= fim)]
    inflacao = float(janela["receita_gerada"].sum()) / float(v["receita_bruta"].sum())
    return {
        "ranking": g.to_dict(orient="records"),
        "por_atribuicao": mk.groupby("atribuicao")["campanha_id"].count().to_dict(),
        "auditoria_receita_gerada": {
            "soma_receita_gerada_na_janela": round(float(janela["receita_gerada"].sum()), 2),
            "receita_bruta_aprovada_vendas": round(float(v["receita_bruta"].sum()), 2),
            "fator_inflacao": round(inflacao, 1),
            "veredito": f"receita_gerada é {inflacao:.1f}x a receita real — NÃO usar em R$.",
        },
        "uso_permitido": "ranking relativo entre canais apenas; nunca retorno absoluto em R$.",
    }


@ferramenta(
    "pedidos_margem_negativa",
    """Pedidos que destroem margem: margem_contribuicao < 0. Tipicamente pedidos de
    ticket baixo abaixo do limiar de frete grátis, em que o frete (custo quase fixo
    por pedido) supera a margem do produto. Abre por canal e por faixa de ticket e
    quantifica a perda total.""",
)
def pedidos_margem_negativa() -> dict:
    import numpy as np

    df = carregar_vendas()
    neg = df[df["margem_contribuicao"] < 0]
    if neg.empty:
        return {"pedidos_negativos": 0, "leitura": "nenhum pedido com margem negativa."}
    faixas = [0, 50, 100, 150, 200, 300, np.inf]
    rot = ["0-50", "50-100", "100-150", "150-200", "200-300", "300+"]
    d = df.assign(faixa_ticket=pd.cut(df["receita_bruta"], faixas, labels=rot))
    por_faixa = d.groupby("faixa_ticket", observed=False).apply(
        lambda x: pd.Series({
            "pedidos": len(x),
            "pct_com_margem_negativa": (x["margem_contribuicao"] < 0).mean() * 100,
            "frete_medio": x["custo_frete"].mean(),
            "frete_pct_receita": x["custo_frete"].sum() / x["receita_bruta"].sum() * 100,
            "margem_pct": x["margem_contribuicao"].sum() / x["receita_bruta"].sum() * 100,
        }), include_groups=False).round(2)
    por_canal = neg.groupby("canal", observed=True).agg(
        pedidos=("order_id", "count"),
        perda_reais=("margem_contribuicao", "sum"),
    ).round(2).sort_values("perda_reais").reset_index()
    return {
        "pedidos_negativos": int(len(neg)),
        "pct_dos_pedidos": round(len(neg) / len(df) * 100, 2),
        "perda_total_reais": round(float(neg["margem_contribuicao"].sum()), 2),
        "ticket_medio_dos_negativos": round(float(neg["receita_bruta"].mean()), 2),
        "ticket_medio_geral": round(float(df["receita_bruta"].mean()), 2),
        "frete_medio_dos_negativos": round(float(neg["custo_frete"].mean()), 2),
        "frete_pct_receita_nos_negativos": round(
            float(neg["custo_frete"].sum()) / float(neg["receita_bruta"].sum()) * 100, 2),
        "por_faixa_de_ticket": por_faixa.reset_index().to_dict(orient="records"),
        "por_canal": por_canal.to_dict(orient="records"),
        "leitura": (
            "O frete é um custo quase fixo por pedido; abaixo do limiar de frete grátis "
            "ele consome toda a margem do produto. A perda concentra-se nos tickets baixos."
        ),
    }
