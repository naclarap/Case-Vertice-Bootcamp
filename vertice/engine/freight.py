"""Freight Rule Detector — identifica assimetria de política de frete entre canais."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config
from ..data import carregar_vendas
from . import recorte
from .filtros import normalizar_categorico
from .registry import ferramenta

FAIXAS_TICKET = [0, 100, 200, 300, 400, 500, 750, 1000, np.inf]
ROT_TICKET = ["0-100", "100-200", "200-300", "300-400", "400-500", "500-750", "750-1000", "1000+"]


@ferramenta(
    "politica_frete_por_canal",
    """Mapeia a política de frete efetiva de cada canal: % de pedidos com frete
    grátis, frete médio, frete como % da receita, e o cruzamento canal x faixa de
    ticket. Revela se algum canal foge da regra de frete grátis acima de um ticket
    mínimo praticada pelos demais.""",
)
def politica_frete_por_canal() -> dict:
    df = carregar_vendas()
    g = df.groupby("canal", observed=True).agg(
        pedidos=("order_id", "count"),
        pct_frete_gratis=("frete_gratis", "mean"),
        frete_medio=("custo_frete", "mean"),
        frete_total=("custo_frete", "sum"),
        receita_bruta=("receita_bruta", "sum"),
        ticket_medio=("receita_bruta", "mean"),
        margem=("margem_contribuicao", "sum"),
    ).reset_index()
    g["pct_frete_gratis"] = (g["pct_frete_gratis"] * 100).round(2)
    g["frete_pct_receita"] = (g["frete_total"] / g["receita_bruta"] * 100).round(3)
    g["margem_pct"] = (g["margem"] / g["receita_bruta"] * 100).round(2)
    for c in ["frete_medio", "ticket_medio", "frete_total", "receita_bruta"]:
        g[c] = g[c].round(2)
    g = g.sort_values("pct_frete_gratis")

    # Cruzamento canal x faixa de ticket: identifica o limiar de frete grátis.
    d = df.assign(faixa_ticket=pd.cut(df["receita_bruta"], FAIXAS_TICKET, labels=ROT_TICKET))
    cruz = (d.pivot_table(index="faixa_ticket", columns="canal", values="frete_gratis",
                          aggfunc="mean", observed=False) * 100).round(1)

    outliers = g[g["pct_frete_gratis"] < 10]["canal"].tolist()
    # Limiar praticado pelos demais canais: 1ª faixa com >=50% de frete grátis.
    demais = d[~d["canal"].isin(outliers)]
    lim = demais.groupby("faixa_ticket", observed=False)["frete_gratis"].mean()
    limiar = next((str(f) for f, v in lim.items() if v >= 0.5), None)

    return {
        "por_canal": g.drop(columns=["margem"]).to_dict(orient="records"),
        "pct_frete_gratis_por_canal_e_faixa_de_ticket": cruz.to_dict(orient="index"),
        "canais_fora_da_politica": outliers,
        "limiar_frete_gratis_estimado_demais_canais": limiar,
        "leitura": (
            f"Canais {outliers} praticamente não concedem frete grátis, enquanto os demais "
            f"concedem a partir da faixa de ticket {limiar}."
        ) if outliers else "Nenhum canal fora da política.",
    }


@ferramenta(
    "dispersao_componentes_entre_canais",
    """Coeficiente de variação (CV = desvio-padrão / média) de frete%, desconto% e
    custo% ENTRE os canais. Identifica objetivamente qual componente da margem é
    o mais disperso — ou seja, onde a política é mais inconsistente entre canais.""",
)
def dispersao_componentes_entre_canais() -> dict:
    df = carregar_vendas()
    g = df.groupby("canal", observed=True).apply(
        lambda d: pd.Series({
            "frete_pct": d["custo_frete"].sum() / d["receita_bruta"].sum() * 100,
            "desconto_pct": d["desconto_reais"].sum() / d["receita_bruta"].sum() * 100,
            "custo_pct": d["custo_produto"].sum() / d["receita_bruta"].sum() * 100,
            "margem_pct": d["margem_contribuicao"].sum() / d["receita_bruta"].sum() * 100,
        }), include_groups=False)
    res = []
    for comp in ["frete_pct", "desconto_pct", "custo_pct"]:
        media, dp = float(g[comp].mean()), float(g[comp].std(ddof=1))
        res.append({
            "componente": comp,
            "media_entre_canais_pct": round(media, 3),
            "desvio_padrao_pp": round(dp, 3),
            "coef_variacao": round(dp / media, 4) if media else None,
            "min": round(float(g[comp].min()), 3),
            "max": round(float(g[comp].max()), 3),
            "amplitude_pp": round(float(g[comp].max() - g[comp].min()), 3),
        })
    res.sort(key=lambda r: -(r["coef_variacao"] or 0))
    return {
        "por_canal": g.round(3).reset_index().to_dict(orient="records"),
        "dispersao_ordenada": res,
        "componente_mais_disperso": res[0]["componente"],
        "leitura": (
            f"'{res[0]['componente']}' é o componente mais disperso entre canais "
            f"(CV={res[0]['coef_variacao']}), contra CV={res[1]['coef_variacao']} de "
            f"'{res[1]['componente']}' e CV={res[2]['coef_variacao']} de '{res[2]['componente']}'. "
            "CV alto indica política inconsistente entre canais, não variação natural de mix."
        ),
    }


@ferramenta(
    "custo_assimetria_frete",
    """Quantifica quanto um canal paga em frete que NÃO pagaria se seguisse a mesma
    regra dos demais canais. Aplica, pedido a pedido, a probabilidade de frete
    grátis observada nos outros canais para a mesma faixa de ticket (contrafactual),
    e devolve o frete evitável em R$ e em pp de margem.""",
    {"canal": "canal a avaliar (padrão Marketplace)"},
)
def custo_assimetria_frete(canal: str = config.CANAL_SOB_SUSPEITA) -> dict:
    df = carregar_vendas()
    canal = normalizar_categorico("canal", canal, sorted(df["canal"].astype(str).unique()))
    d = df.assign(faixa_ticket=pd.cut(df["receita_bruta"], FAIXAS_TICKET, labels=ROT_TICKET))
    alvo, outros = d[d["canal"] == canal], d[d["canal"] != canal]

    # Contrafactual: taxa de frete grátis dos DEMAIS canais, por faixa de ticket.
    taxa = outros.groupby("faixa_ticket", observed=False)["frete_gratis"].mean()
    p_gratis = alvo["faixa_ticket"].map(taxa).astype(float).fillna(0.0)
    frete_evitavel = float((alvo["custo_frete"] * p_gratis).sum())

    rb_total = float(df["receita_bruta"].sum())
    rb_alvo = float(alvo["receita_bruta"].sum())
    margem_alvo = float(alvo["margem_contribuicao"].sum())
    from .discount import _periodo_coberto

    return {
        "canal": canal,
        # A pergunta "qual o impacto ANUAL?" chegou a ser respondida com este
        # número sem ressalva: ele é a soma dos 13 meses do recorte, não um ano.
        # O período acompanha o resultado para a anualização ser explícita.
        "periodo_coberto": _periodo_coberto(alvo),
        "pedidos": int(len(alvo)),
        "pct_frete_gratis_no_canal": round(float(alvo["frete_gratis"].mean()) * 100, 2),
        "pct_frete_gratis_nos_demais": round(float(outros["frete_gratis"].mean()) * 100, 2),
        "frete_pago_total": round(float(alvo["custo_frete"].sum()), 2),
        "frete_evitavel_reais": round(frete_evitavel, 2),
        "pct_do_frete_do_canal_evitavel": round(
            frete_evitavel / float(alvo["custo_frete"].sum()) * 100, 2),
        "ganho_margem_pp_no_canal": round(frete_evitavel / rb_alvo * 100, 3),
        "ganho_margem_pp_consolidado": round(frete_evitavel / rb_total * 100, 3),
        "margem_pct_atual_canal": round(margem_alvo / rb_alvo * 100, 2),
        "margem_pct_canal_pos_correcao": round((margem_alvo + frete_evitavel) / rb_alvo * 100, 2),
        "taxa_frete_gratis_demais_por_faixa": {str(k): round(float(v) * 100, 1) for k, v in taxa.items()},
        "metodo": (
            "Contrafactual por faixa de ticket: para cada pedido do canal, aplica a "
            "probabilidade de frete grátis observada nos demais canais na mesma faixa de "
            "ticket. Não assume elasticidade de demanda — apenas equaliza a política."
        ),
        "premissa": (
            "PREMISSA: a assimetria é de POLÍTICA, não de custo estrutural do canal. Se o "
            "marketplace impõe contratualmente o frete pago, o valor é o custo de operar "
            "no canal, não uma economia capturável — verificar contrato antes de acionar."
        ),
    }


@ferramenta(
    "regra_frete_por_limiar",
    """Quanto um canal deixaria de pagar em frete se seguisse a MESMA REGRA
    OBJETIVA dos demais canais: a Vértice só arca com o frete de pedidos abaixo
    de um limiar de receita líquida (R$ 250 nesta base, com 100% de aderência nos
    6 canais fora do Marketplace). Devolve a contribuição preservada em R$, a
    aderência da regra nos demais canais e os pedidos afetados. É a alavanca
    NEGOCIÁVEL com o parceiro, e responde "quanto ganhamos se o Marketplace
    seguir a regra dos demais?". Diferente de custo_assimetria_frete, que é o
    DIAGNÓSTICO por contrafactual estatístico e responde "quanto do frete do
    canal seria evitável".""",
    {"canal": "canal a avaliar (padrão Marketplace)",
     "limite": "limiar de receita líquida em R$ (padrão 250)",
     "convencao": "'decisao' (padrão) ou 'diagnostico'",
     "ano": "ano-calendário do recorte; omita para o padrão da convenção",
     "excluir_meses": "meses a excluir; omita para o padrão da convenção",
     "excluir_devolvidos": "'true' conta só pedidos mantidos"},
)
def regra_frete_por_limiar(canal: str = config.CANAL_SOB_SUSPEITA,
                           limite=config.LIMIAR_FRETE_GRATIS_REAIS,
                           convencao=None, ano=None, excluir_meses=None,
                           excluir_devolvidos=None) -> dict:
    limite = float(limite)
    df_all = carregar_vendas()
    canal = normalizar_categorico("canal", canal,
                                  sorted(df_all["canal"].astype(str).unique()))
    # Novembro sai do recorte do TETO DE DESCONTO porque a política de desconto
    # da Black Friday é decidida por orçamento de campanha aprovado, e não pela
    # política corrente. A regra de frete não tem nada a ver com campanha: ela
    # vale o ano inteiro, inclusive em novembro. Por isso esta ferramenta parte
    # da convenção de decisão SEM a exclusão de meses — que continua disponível
    # como parâmetro, caso a pergunta peça outro recorte.
    if excluir_meses is None:
        excluir_meses = []
    r = recorte.resolver(convencao, ano, excluir_meses, excluir_devolvidos)
    pop = recorte.aplicar(df_all, r)
    if pop.empty:
        raise ValueError(f"nenhum pedido no recorte {recorte.descrever(r)}")

    alvo = pop[pop["canal"] == canal]
    outros = pop[pop["canal"] != canal]
    if alvo.empty:
        raise ValueError(f"nenhum pedido do canal '{canal}' no recorte")

    # Aderência: a regra "há frete se, e somente se, a receita líquida < limite"
    # acerta que fração dos pedidos dos DEMAIS canais? É esta medida que
    # transforma "os outros canais parecem cobrar diferente" em regra objetiva
    # oponível ao parceiro. Sem ela o número seria só uma diferença observada.
    previsto = outros["receita_liquida"] < limite
    observado = outros["custo_frete"] > 0
    aderencia = float((previsto == observado).mean()) * 100
    por_canal = {
        str(c): round(float(((d["receita_liquida"] < limite) == (d["custo_frete"] > 0)).mean()) * 100, 2)
        for c, d in outros.groupby("canal", observed=True)
    }

    acima = alvo[alvo["receita_liquida"] >= limite]
    preservado = float(acima["custo_frete"].sum())
    rb_alvo = float(alvo["receita_bruta"].sum())
    rl_alvo = float(alvo["receita_liquida"].sum())
    margem_alvo = float(alvo["margem_contribuicao"].sum())
    meses = recorte.bloco(r, pop)["meses_observados"]

    return {
        "canal": canal,
        "limite_receita_liquida_reais": limite,
        "recorte_aplicado": recorte.bloco(r, alvo),
        "aderencia_da_regra_nos_demais_canais_pct": round(aderencia, 2),
        "aderencia_por_canal_pct": por_canal,
        "pedidos_no_canal": int(len(alvo)),
        "pedidos_acima_do_limite": int(len(acima)),
        "pct_pedidos_acima_do_limite": round(len(acima) / len(alvo) * 100, 2),
        "frete_pago_no_canal": round(float(alvo["custo_frete"].sum()), 2),
        "contribuicao_preservada_reais": round(preservado, 2),
        "pct_do_frete_do_canal": round(
            preservado / float(alvo["custo_frete"].sum()) * 100, 2),
        "ganho_margem_pp_no_canal": round(preservado / rb_alvo * 100, 3),
        "margem_pct_sobre_bruta_atual": round(margem_alvo / rb_alvo * 100, 2),
        "margem_pct_sobre_liquida_atual": round(margem_alvo / rl_alvo * 100, 2),
        "margem_pct_sobre_liquida_pos_regra": round(
            (margem_alvo + preservado) / rl_alvo * 100, 2),
        "valor_anualizado_reais": (round(preservado, 2) if meses == 12
                                   else round(preservado / meses * 12, 2)),
        "nota_anualizacao": ("o recorte cobre 12 meses: o valor já é anual" if meses == 12
                             else f"o recorte cobre {meses} meses; veja valor_anualizado_reais"),
        "controle": "EXTERNO — depende de acordo com o parceiro do marketplace",
        "premissa": (
            "PREMISSA EXPLÍCITA: o parceiro aceita passar a praticar a mesma regra dos "
            "demais canais. Se recusar, o valor capturável é R$ 0 e vale o plano B "
            "(preço diferenciado por canal), sem valor estimável nesta base. PREMISSA "
            "ADICIONAL: `custo_frete` é tratado como custo arcado pela Vértice, porque é "
            "subtraído na margem — o dicionário do case não define o campo, e a leitura "
            "precisa ser confirmada com o COO antes de acionar a negociação. Volume "
            "constante: são os pedidos de 2023 mantidos, não uma previsão."
        ),
    }
