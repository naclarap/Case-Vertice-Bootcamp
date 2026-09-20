"""Statistical Validator — testes de hipótese e classificação de força da evidência.

Nenhum teste aqui é chamado pelo LLM com números inventados: as amostras são
extraídas da base pelo próprio motor a partir de nomes de coluna/filtro.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

from ..data import carregar_vendas
from .registry import ferramenta

# Colunas numéricas que podem ser usadas como métrica nos testes.
METRICAS = [
    "margem_pct", "desconto_pct", "custo_pct", "frete_pct", "margem_contribuicao",
    "receita_bruta", "desconto_reais", "custo_frete", "custo_produto", "quantidade",
    "ticket_medio_proxy", "tempo_entrega_real",
]
GRUPOS = ["canal", "categoria", "mes", "ano", "metodo_pagamento", "faixa_desconto", "devolvido"]


def _base(metrica: str) -> pd.DataFrame:
    df = carregar_vendas()
    if metrica == "ticket_medio_proxy":
        df = df.assign(ticket_medio_proxy=df["receita_bruta"])
    if metrica not in df.columns:
        raise ValueError(f"métrica '{metrica}' inválida. Use uma de: {METRICAS}")
    return df.dropna(subset=[metrica])


def classificar_forca(p_valor: float, r2: float | None = None, n: int | None = None) -> dict:
    """Critério objetivo e fixo de força de evidência.

    FORTE    : p < 0,001 E (R² > 0,7 OU n > 1000)
    MODERADA : p < 0,05  E n >= 100
    FRACA    : demais casos (inclui p >= 0,05)

    Com n grande quase tudo dá significante; por isso os testes também devolvem
    tamanho de efeito (d de Cohen / eta²) e a leitura deve considerá-lo.
    """
    p_valor = float(p_valor)
    if np.isnan(p_valor):
        return {"forca": "FRACA", "criterio": "p-valor indefinido (amostra insuficiente)"}
    if p_valor < 0.001 and ((r2 is not None and r2 > 0.7) or (n is not None and n > 1000)):
        forca, crit = "FORTE", "p<0,001 e (R²>0,7 ou n>1000)"
    elif p_valor < 0.05 and (n is not None and n >= 100):
        forca, crit = "MODERADA", "p<0,05 e n>=100"
    else:
        forca, crit = "FRACA", "não atinge p<0,05 com n>=100"
    return {"forca": forca, "criterio": crit, "p_valor": p_valor, "r2": r2, "n": n}


@ferramenta(
    "classificar_evidencia",
    """Classifica a força de uma evidência estatística (FORTE/MODERADA/FRACA) por
    critério objetivo: FORTE = p<0,001 e (R²>0,7 ou n>1000); MODERADA = p<0,05 e
    n>=100; FRACA caso contrário. Use para preencher a seção FORÇA DA EVIDÊNCIA.""",
    {"p_valor": "p-valor do teste", "r2": "R² se houver (opcional)", "n": "tamanho da amostra"},
    ["p_valor"],
)
def classificar_evidencia(p_valor, r2=None, n=None) -> dict:
    return classificar_forca(float(p_valor),
                             float(r2) if r2 not in (None, "") else None,
                             int(n) if n not in (None, "") else None)


@ferramenta(
    "teste_t_welch",
    """Teste t de Welch (variâncias desiguais) comparando uma métrica entre dois
    grupos de uma coluna categórica. Ex: margem_pct de Marketplace vs todos os
    outros canais. Devolve médias, p-valor, IC95 da diferença, d de Cohen e a
    classificação de força.""",
    {"metrica": f"métrica numérica, uma de: {METRICAS}",
     "coluna_grupo": f"coluna categórica, uma de: {GRUPOS}",
     "grupo_a": "valor do grupo A (ex 'Marketplace')",
     "grupo_b": "valor do grupo B; use 'RESTO' para comparar contra todos os demais"},
    ["metrica", "coluna_grupo", "grupo_a"],
)
def teste_t_welch(metrica: str, coluna_grupo: str, grupo_a: str, grupo_b: str = "RESTO") -> dict:
    df = _base(metrica)
    if coluna_grupo not in df.columns:
        raise ValueError(f"coluna_grupo '{coluna_grupo}' inválida. Use: {GRUPOS}")
    col = df[coluna_grupo].astype(str)
    a = df.loc[col == str(grupo_a), metrica]
    b = df.loc[col != str(grupo_a), metrica] if grupo_b == "RESTO" else df.loc[col == str(grupo_b), metrica]
    if len(a) < 2 or len(b) < 2:
        raise ValueError(
            f"amostra insuficiente (A={len(a)}, B={len(b)}). Valores disponíveis em "
            f"{coluna_grupo}: {sorted(col.unique())[:15]}"
        )
    t, p = sps.ttest_ind(a, b, equal_var=False)
    dif = float(a.mean() - b.mean())
    # d de Cohen com desvio-padrão agrupado.
    sp = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
    d = dif / sp if sp else np.nan
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    gl = se**4 / ((a.var(ddof=1) / len(a))**2 / (len(a) - 1) + (b.var(ddof=1) / len(b))**2 / (len(b) - 1))
    crit = sps.t.ppf(0.975, gl)
    n = len(a) + len(b)
    return {
        "teste": "t de Welch",
        "metrica": metrica,
        "grupo_a": {"rotulo": grupo_a, "n": len(a), "media": round(float(a.mean()), 4)},
        "grupo_b": {"rotulo": grupo_b, "n": len(b), "media": round(float(b.mean()), 4)},
        "diferenca_medias": round(dif, 4),
        "ic95_diferenca": [round(dif - crit * se, 4), round(dif + crit * se, 4)],
        "estatistica_t": round(float(t), 4),
        "p_valor": float(p),
        "d_cohen": round(float(d), 4),
        "tamanho_efeito": ("desprezível" if abs(d) < 0.2 else "pequeno" if abs(d) < 0.5
                           else "médio" if abs(d) < 0.8 else "grande"),
        **classificar_forca(float(p), n=n),
    }


@ferramenta(
    "anova_um_fator",
    """ANOVA de um fator: testa se a média de uma métrica difere entre TODOS os
    níveis de uma coluna categórica. Devolve F, p-valor, eta² (proporção da
    variância explicada) e a média por grupo.""",
    {"metrica": f"métrica numérica, uma de: {METRICAS}",
     "coluna_grupo": f"coluna categórica, uma de: {GRUPOS}"},
    ["metrica", "coluna_grupo"],
)
def anova_um_fator(metrica: str, coluna_grupo: str) -> dict:
    df = _base(metrica)
    if coluna_grupo not in df.columns:
        raise ValueError(f"coluna_grupo '{coluna_grupo}' inválida. Use: {GRUPOS}")
    grupos = [g[metrica].values for _, g in df.groupby(coluna_grupo, observed=True) if len(g) > 1]
    if len(grupos) < 2:
        raise ValueError(f"'{coluna_grupo}' precisa de ao menos 2 grupos com n>1.")
    f, p = sps.f_oneway(*grupos)
    grande = df[metrica].mean()
    ss_ent = sum(len(g) * (g.mean() - grande) ** 2 for g in grupos)
    ss_tot = ((df[metrica] - grande) ** 2).sum()
    eta2 = float(ss_ent / ss_tot) if ss_tot else 0.0
    medias = (df.groupby(coluna_grupo, observed=True)[metrica]
              .agg(["count", "mean"]).round(4).sort_values("mean").reset_index())
    return {
        "teste": "ANOVA de um fator",
        "metrica": metrica,
        "fator": coluna_grupo,
        "n_grupos": len(grupos),
        "estatistica_f": round(float(f), 4),
        "p_valor": float(p),
        "eta_quadrado": round(eta2, 4),
        "leitura_eta2": f"o fator explica {eta2*100:.1f}% da variância de {metrica}",
        "medias_por_grupo": medias.to_dict(orient="records"),
        **classificar_forca(float(p), n=len(df)),
    }


@ferramenta(
    "regressao_linear_multipla",
    """Regressão linear múltipla (OLS) de uma métrica sobre variáveis explicativas
    numéricas. Devolve coeficientes, erro-padrão, t, p, R² e R² ajustado.
    CUIDADO: regredir margem_pct sobre desconto_pct+custo_pct+frete_pct dá R²≈1
    por identidade contábil — isso é teste de sanidade da base, NÃO causa raiz.""",
    {"y": "variável dependente (ex margem_pct)",
     "x": "variáveis explicativas separadas por vírgula (ex 'desconto_pct,frete_pct')"},
    ["y", "x"],
)
def regressao_linear_multipla(y: str, x: str) -> dict:
    cols = [c.strip() for c in (x.split(",") if isinstance(x, str) else x) if c.strip()]
    df = _base(y)
    faltando = [c for c in cols if c not in df.columns]
    if faltando:
        raise ValueError(f"variáveis inexistentes: {faltando}. Disponíveis: {METRICAS}")
    d = df[[y] + cols].dropna()
    Y = d[y].to_numpy(float)
    X = np.column_stack([np.ones(len(d))] + [d[c].to_numpy(float) for c in cols])
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    resid = Y - X @ beta
    n, k = X.shape
    gl = n - k
    sigma2 = resid @ resid / gl
    xtx_inv = np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.diag(sigma2 * xtx_inv))
    t = beta / se
    p = 2 * (1 - sps.t.cdf(np.abs(t), gl))
    ss_tot = ((Y - Y.mean()) ** 2).sum()
    r2 = 1 - (resid @ resid) / ss_tot if ss_tot else 0.0
    r2_aj = 1 - (1 - r2) * (n - 1) / gl
    f_stat = (r2 / (k - 1)) / ((1 - r2) / gl) if r2 < 1 and k > 1 else float("inf")
    p_modelo = float(1 - sps.f.cdf(f_stat, k - 1, gl)) if np.isfinite(f_stat) else 0.0
    nomes = ["intercepto"] + cols
    identidade = r2 > 0.999 and set(cols) >= {"desconto_pct", "custo_pct", "frete_pct"}
    return {
        "teste": "Regressão linear múltipla (OLS)",
        "y": y, "x": cols, "n": int(n),
        "r2": round(float(r2), 6), "r2_ajustado": round(float(r2_aj), 6),
        "p_valor": p_modelo,
        "coeficientes": [
            {"variavel": nm, "beta": round(float(b), 6), "erro_padrao": round(float(s), 6),
             "t": round(float(tt), 4), "p_valor": float(pp)}
            for nm, b, s, tt, pp in zip(nomes, beta, se, t, p)
        ],
        "alerta_identidade_contabil": (
            "R²≈1 aqui é ARTEFATO da identidade margem%+desconto%+custo%+frete%=100%. "
            "É teste de sanidade da base, não achado de causa raiz — não apresente como tal."
        ) if identidade else None,
        **classificar_forca(p_modelo, r2=float(r2), n=int(n)),
    }


@ferramenta(
    "qui_quadrado_independencia",
    """Qui-quadrado de independência entre duas colunas categóricas (ex: canal x
    frete_gratis, ou faixa_desconto x devolvido). Devolve a tabela de contingência,
    chi², p-valor e V de Cramér (tamanho de efeito).""",
    {"coluna_a": "primeira coluna categórica", "coluna_b": "segunda coluna categórica"},
    ["coluna_a", "coluna_b"],
)
def qui_quadrado_independencia(coluna_a: str, coluna_b: str) -> dict:
    df = carregar_vendas()
    validas = GRUPOS + ["frete_gratis", "devolvido", "status_pagamento", "motivo_devolucao"]
    for c in (coluna_a, coluna_b):
        if c not in df.columns:
            raise ValueError(f"coluna '{c}' inválida. Sugestões: {validas}")
    tab = pd.crosstab(df[coluna_a].astype(str), df[coluna_b].astype(str))
    chi2, p, gl, _ = sps.chi2_contingency(tab)
    n = int(tab.values.sum())
    v = float(np.sqrt(chi2 / (n * (min(tab.shape) - 1)))) if min(tab.shape) > 1 else 0.0
    return {
        "teste": "Qui-quadrado de independência",
        "colunas": [coluna_a, coluna_b],
        "tabela_contingencia": tab.to_dict(orient="index"),
        "chi2": round(float(chi2), 4), "graus_liberdade": int(gl), "p_valor": float(p),
        "v_cramer": round(v, 4),
        "tamanho_efeito": ("desprezível" if v < 0.1 else "pequeno" if v < 0.3
                           else "médio" if v < 0.5 else "grande"),
        **classificar_forca(float(p), n=n),
    }
