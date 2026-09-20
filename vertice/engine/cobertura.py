"""Cobertura de dados: a pergunta é respondível com o que existe na base?

Existe por causa do bloco de perguntas que o case planta de propósito — CAC,
LTV, churn, segmento de cliente, causa de devolução, previsão pós-intervenção.
Todas soam respondíveis, e algumas até encontram uma COLUNA com o nome certo
(`clientes.ltv_acumulado`, `marketing.cac`, `segmento_rfm`, `motivo_devolucao`).
Responder por existir a coluna é o erro caro: o campo existe e não reconcilia
com a transação.

Duas checagens, ambas determinísticas:

  1. ESQUEMA — o campo necessário existe em alguma tabela?
  2. RECONCILIAÇÃO — quando existe, ele bate com o que a venda mostra?

A reconciliação é o que separa este módulo de uma lista de desculpas escrita à
mão: `ltv_acumulado` correlaciona -0,02 com a receita real por cliente, e a
base de vendas cobre 346 dos 15.000 clientes. Isso não é opinião sobre o dado,
é medida sobre o dado — e é ela que sustenta a recusa.

Nada aqui estima o que falta. O veredito é "não respondível", "parcial com
ressalva" ou "respondível", sempre com o motivo medido junto.
"""
from __future__ import annotations

from functools import lru_cache

from ..data import (carregar_atendimento, carregar_clientes, carregar_marketing,
                    carregar_vendas)
from .registry import ferramenta

NAO = "nao_respondivel"
PARCIAL = "parcial_com_ressalva"
SIM = "respondivel"


@lru_cache(maxsize=1)
def _cobertura_de_clientes() -> dict:
    """Quanto da base de clientes aparece nas vendas, e o quanto os campos
    pré-calculados do cadastro batem com a transação observada."""
    c, v = carregar_clientes(), carregar_vendas()
    receita = v.groupby("customer_id")["receita_bruta"].sum()
    pedidos = v.groupby("customer_id")["order_id"].nunique()
    j = c.set_index("customer_id").join(receita.rename("receita"), how="inner")
    j = j.join(pedidos.rename("pedidos"), how="inner")
    return {
        "clientes_no_cadastro": int(c["customer_id"].nunique()),
        "clientes_com_pedido_na_base": int(v["customer_id"].nunique()),
        "cobertura_pct": round(100 * v["customer_id"].nunique() / c["customer_id"].nunique(), 2),
        "correlacao_ltv_acumulado_x_receita_observada": (
            round(float(j["ltv_acumulado"].corr(j["receita"])), 4) if len(j) > 2 else None),
        "correlacao_total_pedidos_historico_x_pedidos_observados": (
            round(float(j["total_pedidos_historico"].corr(j["pedidos"])), 4) if len(j) > 2 else None),
    }


def _tem(df, coluna: str) -> bool:
    return coluna in df.columns


def _assunto_cac() -> dict:
    m = carregar_marketing()
    from .extras import ranking_roas_canais  # reaproveita a conciliação já feita

    return {
        "campos_encontrados": ["marketing.cac", "marketing.investimento_reais",
                               "marketing.conversoes"],
        "campos_ausentes": ["marcação de cliente NOVO vs recorrente na venda",
                            "custo de aquisição conciliado com a venda"],
        "medida": {
            "campanhas": int(len(m)),
            "cac_mediano_reportado": round(float(m["cac"].median()), 2),
            **ranking_roas_canais()["auditoria_receita_gerada"],
        },
        "veredito": PARCIAL,
        "por_que": ("a coluna `cac` existe e pode ser reportada COMO ESTÁ, mas não "
                    "reconcilia: a receita_gerada das campanhas é múltiplas vezes a "
                    "receita real da base, e a venda não marca cliente novo — então "
                    "não dá para recalcular CAC nem afirmar que o reportado é o real"),
        "o_que_seria_preciso": ["flag de primeiro pedido por cliente",
                                "conciliação campanha→pedido (hoje só há atribuição declarada)"],
    }


def _assunto_ltv() -> dict:
    cob = _cobertura_de_clientes()
    return {
        "campos_encontrados": ["clientes.ltv_acumulado", "clientes.total_pedidos_historico"],
        "campos_ausentes": ["histórico de compras que sustente o LTV declarado",
                            "data de churn / fim de relacionamento"],
        "medida": cob,
        "veredito": NAO,
        "por_que": ("o campo existe, mas não é verificável: a base de vendas cobre "
                    f"{cob['cobertura_pct']}% dos clientes do cadastro e o "
                    "`ltv_acumulado` praticamente não correlaciona com a receita "
                    "observada desses clientes (correlação "
                    f"{cob['correlacao_ltv_acumulado_x_receita_observada']}). "
                    "Reportá-lo como LTV seria repetir um número de origem desconhecida"),
        "o_que_seria_preciso": ["histórico transacional completo por cliente",
                                "definição e data de churn"],
    }


def _assunto_churn() -> dict:
    c, cob = carregar_clientes(), _cobertura_de_clientes()
    return {
        "campos_encontrados": (["clientes.segmento_rfm (inclui o rótulo 'Churn')"]
                               if _tem(c, "segmento_rfm") else []),
        "campos_ausentes": ["data de cancelamento ou de última compra por cliente",
                            "janela de observação definida", "regra de churn documentada"],
        "medida": {**cob,
                   "rotulos_de_segmento": sorted(c["segmento_rfm"].dropna().unique().tolist())},
        "veredito": NAO,
        "por_que": ("existe um RÓTULO 'Churn' no cadastro, não um EVENTO de churn: "
                    "sem data de última compra nem janela declarada, não há como "
                    "recalcular a taxa nem datar o que já foi rotulado"),
        "o_que_seria_preciso": ["data da última compra por cliente",
                                "definição de janela (ex.: sem compra em 180 dias)"],
    }


def _assunto_segmentos() -> dict:
    cob = _cobertura_de_clientes()
    return {
        "campos_encontrados": ["clientes.segmento_rfm", "clientes.nivel_fidelidade",
                               "vendas.customer_id (juntável)"],
        "campos_ausentes": ["regra de construção do segmento", "vigência do rótulo"],
        "medida": cob,
        "veredito": PARCIAL,
        "por_que": ("dá para cruzar segmento com margem observada, mas só para os "
                    f"{cob['clientes_com_pedido_na_base']} clientes que aparecem em "
                    f"vendas ({cob['cobertura_pct']}% do cadastro) — e o rótulo é "
                    "pré-calculado por regra desconhecida, então o resultado descreve "
                    "o rótulo, não a qualidade do cliente"),
        "o_que_seria_preciso": ["regra do RFM e data de cálculo",
                                "cobertura transacional do cadastro"],
    }


def _assunto_oferta_individual() -> dict:
    return {
        "campos_encontrados": ["clientes.opt_in_newsletter", "clientes.customer_id"],
        "campos_ausentes": ["resposta a oferta anterior", "elasticidade por cliente",
                            "grupo de controle"],
        "medida": _cobertura_de_clientes(),
        "veredito": NAO,
        "por_que": ("escolher quem recebe oferta exige estimar resposta individual; a "
                    "base não tem nenhuma oferta passada com resultado, nem grupo de "
                    "controle — qualquer lista sairia de um modelo sem evidência"),
        "o_que_seria_preciso": ["histórico de campanhas por cliente com resposta",
                                "teste A/B com grupo de controle"],
    }


def _assunto_tickets() -> dict:
    a = carregar_atendimento()
    tem_texto = _tem(a, "texto_cliente")
    rotulados = int(a["categoria_problema"].notna().sum()) if _tem(a, "categoria_problema") else 0
    return {
        "campos_encontrados": [c for c in ("atendimento.texto_cliente",
                                           "atendimento.categoria_problema")
                               if _tem(a, c.split(".")[1])],
        "campos_ausentes": ["rótulo auditado por humano (o existente é o próprio "
                            "campo que se quer prever)", "conjunto de validação"],
        "medida": {"tickets": int(len(a)), "com_categoria": rotulados,
                   "tem_texto_livre": tem_texto},
        "veredito": PARCIAL,
        "por_que": ("há texto e uma categoria já preenchida, então é tecnicamente "
                    "treinável — mas a qualidade do rótulo existente não foi "
                    "auditada, e um classificador treinado nele só reproduz o "
                    "critério de quem preencheu"),
        "o_que_seria_preciso": ["amostra revisada por humano para medir acurácia real"],
    }


def _assunto_causa_devolucao() -> dict:
    from .auditoria import verificar_consistencia_categorica

    cons = verificar_consistencia_categorica("vendas", "motivo_devolucao", "categoria")
    tamanho_sem_tamanho = [c for c in cons["celulas"]
                           if c["motivo_devolucao"] == "Tamanho errado"
                           and c["categoria"] in ("Beleza", "Lifestyle", "Acessórios")]
    return {
        "campos_encontrados": ["vendas.motivo_devolucao", "vendas.devolvido"],
        "campos_ausentes": ["data da solicitação de devolução", "laudo/evidência do defeito",
                            "texto livre do cliente na devolução", "quem registrou o motivo"],
        "medida": {
            "motivo_tamanho_errado_em_categoria_sem_tamanho": [
                {k: c[k] for k in ("motivo_devolucao", "categoria", "registros")}
                for c in tamanho_sem_tamanho],
            "total_desses_registros": int(sum(c["registros"] for c in tamanho_sem_tamanho)),
        },
        "veredito": NAO,
        "por_que": ("o campo registra o motivo DECLARADO no atendimento, não a causa "
                    "apurada, e ele próprio é inconsistente: há 'Tamanho errado' em "
                    "categorias onde tamanho não é atributo. Tratar motivo como causa "
                    "propagaria o erro de registro para a decisão"),
        "o_que_seria_preciso": ["evidência por devolução (laudo, foto, texto)",
                                "processo de validação do motivo no atendimento"],
    }


def _assunto_previsao_devolucao() -> dict:
    return {
        "campos_encontrados": ["vendas.devolvido (situação observada)"],
        "campos_ausentes": ["qualquer intervenção passada com antes/depois",
                            "grupo de controle", "variação exógena"],
        "medida": {},
        "veredito": NAO,
        "por_que": ("prever a redução exige efeito causal estimado; a base é "
                    "observacional e não contém nenhuma intervenção anterior para "
                    "medir. É possível dizer quanto está em jogo hoje, não quanto "
                    "cairá depois"),
        "o_que_seria_preciso": ["piloto com grupo de controle", "janela antes/depois"],
    }


ASSUNTOS = {
    "cac": _assunto_cac,
    "ltv": _assunto_ltv,
    "churn": _assunto_churn,
    "segmentos_de_clientes": _assunto_segmentos,
    "oferta_individual": _assunto_oferta_individual,
    "classificacao_de_tickets": _assunto_tickets,
    "causa_de_devolucao": _assunto_causa_devolucao,
    "previsao_de_devolucao": _assunto_previsao_devolucao,
}


@ferramenta(
    "cobertura_de_dados",
    """Responde se uma pergunta é sustentável pelos dados ANTES de tentar
    respondê-la. Checa o esquema (o campo existe?) e a reconciliação (ele bate
    com a venda observada?) e devolve veredito 'nao_respondivel',
    'parcial_com_ressalva' ou 'respondivel', com a medida que sustenta o
    veredito e o que seria preciso coletar. Use em CAC, LTV, churn, segmento de
    cliente, oferta individual, classificação de tickets, causa de devolução e
    previsão de redução de devolução — perguntas cujo campo existe na base mas
    não reconcilia com a transação.""",
    {"assunto": ("um de: cac, ltv, churn, segmentos_de_clientes, oferta_individual, "
                 "classificacao_de_tickets, causa_de_devolucao, previsao_de_devolucao")},
    obrigatorios=["assunto"],
)
def cobertura_de_dados(assunto: str) -> dict:
    chave = str(assunto).strip().lower()
    if chave not in ASSUNTOS:
        raise ValueError(f"assunto '{assunto}' desconhecido. Disponíveis: {sorted(ASSUNTOS)}")
    return {"assunto": chave, **ASSUNTOS[chave](),
            "nota": ("veredito sobre a COBERTURA do dado, não sobre o negócio: "
                     "'nao_respondivel' significa que qualquer número aqui seria "
                     "inventado, não que o tema seja irrelevante")}
