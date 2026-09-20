"""KPIs de aceite do teto de desconto: o que medir para saber se a regra funciona.

Um teto aprovado sem KPI de aceite é uma decisão sem leitura. Este módulo produz
os três números que o roadmap precisa, todos derivados do mesmo simulador, para
que nenhum deles seja conta do modelo:

- a taxa de desconto de hoje e a que se espera sob o teto (KPI de resultado);
- a regra de parada do teste controlado (KPI de risco);
- a contribuição preservada média por mês (KPI de acompanhamento).

A regra de parada merece explicação, porque é o número que protege a empresa.
O ponto de equilíbrio diz quanto dos pedidos AFETADOS poderia se perder antes de
o ganho zerar. Convertido para o total de pedidos do recorte, vira uma queda
observável no volume. A regra de parada é METADE dessa queda: uma margem de
segurança de 50%, para que a decisão de interromper o teste seja tomada antes de
o prejuízo existir, e não depois. É desejável parar cedo porque o custo de
retomar o desconto é zero e o custo de descobrir tarde é a margem do período
inteiro.
"""
from __future__ import annotations

import numpy as np

from .. import config
from ..data import carregar_vendas
from . import recorte
from .filtros import normalizar_filtro
from .registry import ferramenta

# Fração do ponto de equilíbrio adotada como gatilho de parada. 0,5 = interrompe
# quando metade da folga tiver sido consumida.
MARGEM_DE_SEGURANCA = 0.5


def _reais(v: float) -> str:
    """Formata em padrão brasileiro. Só o número: aplicar a troca de separadores
    sobre a frase inteira corrompe a pontuação do texto."""
    return f"{v:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


@ferramenta(
    "kpis_do_teto",
    """KPIs de aceite de um teto de desconto, para o roadmap e o teste controlado:
    taxa de desconto atual e esperada sob o teto (em % da receita bruta), regra de
    parada do teste (queda de volume que interrompe o piloto), contribuição
    preservada média por mês e por categoria. Todos derivados do mesmo recorte
    declarado do simulador, nenhum calculado fora de ferramenta.""",
    {"teto_pct": "teto de desconto em % (ex '20')",
     "canal": "restringe a um canal; omita para todos",
     "categoria": "restringe a uma categoria; omita para todas",
     "convencao": "'decisao' (padrão) ou 'diagnostico'",
     "ano": "ano-calendário do recorte",
     "excluir_meses": "meses fora do teto (padrão: novembro)",
     "excluir_devolvidos": "'true' conta só pedidos mantidos"},
    principais=["teto_pct"],
)
def kpis_do_teto(teto_pct=None, canal=None, categoria=None, convencao=None,
                 ano=None, excluir_meses=None, excluir_devolvidos=None) -> dict:
    from .discount import simular_teto_desconto

    sim = simular_teto_desconto(teto_pct=teto_pct, canal=canal, categoria=categoria,
                                convencao=convencao, ano=ano,
                                excluir_meses=excluir_meses,
                                excluir_devolvidos=excluir_devolvidos)
    teto = sim["teto_aplicado_pct"] / 100

    r = recorte.resolver(convencao, ano, excluir_meses, excluir_devolvidos)
    df = recorte.aplicar(carregar_vendas(), r)
    filtros = {}
    for col, val in [("canal", canal), ("categoria", categoria)]:
        if val in (None, ""):
            continue
        val = normalizar_filtro(col, val, sorted(df[col].astype(str).unique()))
        df = df[df[col].astype(str) == val]
        filtros[col] = val

    rb = float(df["receita_bruta"].sum())
    desconto_atual = float(df["desconto_reais"].sum())
    desconto_sob_teto = float(np.minimum(df["desconto_reais"],
                                         df["receita_bruta"] * teto).sum())

    meses = sim["recorte_aplicado"]["meses_observados"]
    preservado = sim["contribuicao_preservada_reais"]
    equilibrio = sim["ponto_de_equilibrio_pct"]
    afetados = sim["pct_pedidos_afetados"]

    # Equilíbrio expresso em % de TODOS os pedidos do recorte, não só dos
    # afetados: é assim que ele vira observável num painel de volume diário.
    equilibrio_total = (afetados * equilibrio / 100) if equilibrio is not None else None
    regra_parada = (equilibrio_total * MARGEM_DE_SEGURANCA
                    if equilibrio_total is not None else None)

    por_categoria = {}
    if "categoria" not in filtros:
        for cat in sorted(df["categoria"].astype(str).unique()):
            d = df[df["categoria"].astype(str) == cat]
            ganho = float((d["desconto_reais"] - d["receita_bruta"] * teto).clip(lower=0).sum())
            por_categoria[cat] = round(ganho, 2)

    return {
        "teto_pct": sim["teto_aplicado_pct"],
        "recorte_aplicado": sim["recorte_aplicado"],
        "segmento": filtros or {"escopo": "toda a população do recorte"},
        "kpi_resultado": {
            "taxa_de_desconto_atual_pct": round(desconto_atual / rb * 100, 2),
            "taxa_de_desconto_sob_o_teto_pct": round(desconto_sob_teto / rb * 100, 2),
            "reducao_esperada_pp": round((desconto_atual - desconto_sob_teto) / rb * 100, 2),
            "definicao": "desconto concedido ÷ receita bruta, no recorte declarado",
        },
        "kpi_risco": {
            "ponto_de_equilibrio_pct_dos_afetados": equilibrio,
            "pct_pedidos_afetados": afetados,
            "equilibrio_em_pct_de_todos_os_pedidos": (round(equilibrio_total, 2)
                                                      if equilibrio_total is not None else None),
            "regra_de_parada_queda_de_pedidos_pct": (round(regra_parada, 2)
                                                     if regra_parada is not None else None),
            "margem_de_seguranca": f"{MARGEM_DE_SEGURANCA:.0%} do equilíbrio",
            "definicao": (
                "interromper o teste se o grupo tratado tiver queda de pedidos igual ou "
                "maior que a regra de parada, medida contra o grupo de controle. É "
                "metade do ponto de equilíbrio convertido para o total de pedidos: para "
                "a decisão de parar vir antes de o prejuízo existir."),
        },
        # Duas médias mensais, porque respondem a perguntas diferentes e
        # confundi-las é erro de 9%. O KPI de acompanhamento do comitê é mensal
        # ao longo do ano-calendário (o teto vale o ano todo, mesmo nos meses em
        # que está suspenso); o valor por mês ATIVO é o que o piloto observa
        # enquanto roda. Ambos vêm rotulados para a resposta não ter de escolher.
        "kpi_acompanhamento": {
            "contribuicao_preservada_no_recorte_reais": preservado,
            "meses_com_teto_ativo": meses,
            "meses_do_ano_calendario": 12 if r.get("ano") else meses,
            "media_por_mes_do_ano_calendario_reais": round(
                preservado / (12 if r.get("ano") else meses), 2),
            "media_por_mes_ativo_reais": round(preservado / meses, 2),
            "kpi_do_comite": round(preservado / (12 if r.get("ano") else meses), 2),
            "premissa": (
                "distribuição uniforme ao longo dos meses. A média do ano-calendário "
                "divide por 12 mesmo quando o teto não vale em todos os meses, porque é "
                "assim que o benefício aparece no resultado anual; a média por mês ativo "
                f"divide pelos {meses} meses em que o teto de fato vigora."),
        },
        "contribuicao_preservada_por_categoria_reais": por_categoria,
        "premissa": sim["premissa"],
    }


@ferramenta(
    "caso_base_do_plano",
    """Caso-base do plano: soma as alavancas com valor defensável e separa o que
    está sob controle INTERNO do que depende de terceiros. Responde "quanto vale o
    plano?" e "o que sobra se o parceiro recusar?". Devolve o teto de desconto
    (interno), a regra de frete do Marketplace (externo), o total e a parcela sob
    controle interno. NÃO inclui devolução, cancelamento nem pendência: essas
    frentes não têm meta em reais defensável nesta base — veja perda_pos_pedido
    para dimensioná-las sem prometer recuperação.""",
    {"teto_pct": "teto de desconto do caso-base em % (padrão 20)",
     "limite_frete": "limiar de receita líquida da regra de frete (padrão 250)",
     "ano": "ano-calendário do caso-base (padrão 2023)"},
)
def caso_base_do_plano(teto_pct=None, limite_frete=None, ano=None) -> dict:
    from .discount import simular_teto_desconto
    from .freight import regra_frete_por_limiar

    teto_pct = config.LIMIAR_DESCONTO_ALTO * 100 if teto_pct is None else float(teto_pct)
    limite_frete = (config.LIMIAR_FRETE_GRATIS_REAIS if limite_frete is None
                    else float(limite_frete))

    desconto = simular_teto_desconto(teto_pct=teto_pct, ano=ano)
    frete = regra_frete_por_limiar(limite=limite_frete, ano=ano)

    interno = desconto["contribuicao_preservada_reais"]
    externo = frete["contribuicao_preservada_reais"]
    total = interno + externo

    return {
        "ano": desconto["recorte_aplicado"]["ano"],
        "alavancas": [
            {
                "alavanca": f"Teto de desconto de {teto_pct:.0f}%",
                "controle": "INTERNO",
                "contribuicao_preservada_reais": interno,
                "recorte": desconto["recorte_aplicado"]["descricao"],
                "pedidos_afetados_pct": desconto["pct_pedidos_afetados"],
                "ponto_de_equilibrio_pct": desconto["ponto_de_equilibrio_pct"],
                "dono": "CMO, acompanhamento do CFO",
                "tempo_ate_o_valor": "30 a 60 dias",
                "premissa": "volume constante, testada fora de novembro",
            },
            {
                "alavanca": f"Regra de frete no Marketplace (R$ {limite_frete:.0f})",
                "controle": "EXTERNO",
                "contribuicao_preservada_reais": externo,
                "recorte": frete["recorte_aplicado"]["descricao"],
                "aderencia_da_regra_nos_demais_pct":
                    frete["aderencia_da_regra_nos_demais_canais_pct"],
                "dono": "COO",
                "tempo_ate_o_valor": "60 a 90 dias",
                "premissa": "o parceiro aceita a regra; se recusar, R$ 0",
            },
        ],
        "caso_base_interno_reais": round(interno, 2),
        "caso_base_com_externo_reais": round(total, 2),
        "parcela_sob_controle_interno_pct": round(interno / total * 100, 2),
        "leitura": (
            "Se o parceiro do marketplace recusar a regra de frete, o caso-base "
            f"permanece em R$ {_reais(interno)}, integralmente sob controle da "
            "Vértice. A recomendação não depende de terceiros."),
        "fora_do_caso_base": (
            "Devolução, cancelamento e pendência NÃO entram: as taxas são "
            "estatisticamente iguais em todas as dimensões da base (canal, categoria, "
            "meio de pagamento, quantidade, fornecedor, faixa de desconto), então não há "
            "alavanca cuja correção produza redução mensurável. Sustentam governança do "
            "dado com KPI de aceite, não meta em reais. Ver perda_pos_pedido."),
        "premissa": (
            "◐ ESTIMATIVA. 'Contribuição preservada' é o desconto que deixa de ser "
            "concedido ou o frete que deixa de ser pago em PEDIDOS MANTIDOS do ano-base, "
            "sob volume constante. Não é previsão de resultado nem 'desconto removido': "
            "é o teto da oportunidade sob premissa declarada."),
    }
