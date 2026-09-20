"""Discount Simulator — evidência sobre desconto e simulação de teto.

Toda simulação aqui assume VOLUME CONSTANTE (ver `premissa` no retorno). Os
dados observacionais não permitem estimar elasticidade: não há grupo de controle
nem variação exógena do desconto. A simulação é um teto de oportunidade, não uma
previsão.
"""
from __future__ import annotations

import pandas as pd

from ..data import carregar_vendas
from . import recorte
from .filtros import normalizar_filtro
from .registry import ferramenta

PREMISSA_VOLUME = (
    "PREMISSA EXPLÍCITA: volume constante — assume que os mesmos pedidos aconteceriam "
    "com a nova política de desconto, sem ganho nem perda de volume. Os dados são "
    "observacionais: não há grupo de controle nem variação exógena do desconto, então "
    "não é possível estimar elasticidade. O número é um cenário sob premissa, não uma "
    "previsão. Valide com experimento A/B antes de comprometer o resultado."
)


def _periodo_coberto(df) -> dict:
    """Janela de datas que o resultado realmente cobre, para o número não ser
    lido como mensal (ou anual) quando é acumulado da base."""
    d = pd.to_datetime(df["data_pedido"])
    ini, fim = d.min(), d.max()
    meses = (fim.year - ini.year) * 12 + (fim.month - ini.month) + 1
    return {
        "inicio": str(ini.date()), "fim": str(fim.date()), "meses": int(meses),
        "nota": (f"valores acumulados dos {meses} meses do recorte, NÃO mensais; "
                 f"para média por mês, divida por {meses}"),
    }


def _teto_ou_politica(valor, canal, categoria, ferramenta_nome: str,
                      parametro: str = "teto_pct") -> tuple[float, str]:
    """Resolve o percentual: o que veio na chamada, ou a política vigente.

    Quando não há nem parâmetro nem política, levanta TypeError com a mesma
    forma de antes ("Parâmetro(s) obrigatório(s) ausente(s)") — de propósito:
    é o TypeError que faz o loop do agente devolver o exemplo de chamada já
    preenchido ao modelo. Trocar por outro erro aqui quebraria essa correção.
    """
    if valor is not None:
        return valor, "parametro_explicito"
    from ..politica import politica_vigente

    p = politica_vigente(canal, categoria)
    if p is None:
        raise TypeError(
            f"Parâmetro(s) obrigatório(s) ausente(s) em '{ferramenta_nome}': "
            f"['{parametro}'] — e não há política vigente registrada para este "
            f"recorte (canal={canal}, categoria={categoria}) para usar como padrão."
        )
    rotulo = f"politica_vigente(canal={p.get('canal')}, categoria={p.get('categoria')})"
    return p["teto_pct"], f"{rotulo} definida por {p.get('responsavel')}"


@ferramenta(
    "tabela_faixas_desconto",
    """Itens por pedido, ticket médio e margem por faixa de desconto (0%, 0-10%,
    10-20%, 20-25%, 25-30%, 30%+). Serve para testar se desconto compra volume
    incremental. ATENÇÃO: é evidência de CORRELAÇÃO — sem grupo de controle não
    se pode afirmar causalidade (pode haver viés de seleção de quem recebe
    desconto).""",
)
def tabela_faixas_desconto() -> dict:
    df = carregar_vendas()
    g = df.groupby("faixa_desconto", observed=False).agg(
        pedidos=("order_id", "count"),
        itens_por_pedido=("quantidade", "mean"),
        ticket_medio=("receita_bruta", "mean"),
        receita_bruta=("receita_bruta", "sum"),
        desconto_reais=("desconto_reais", "sum"),
        margem=("margem_contribuicao", "sum"),
    ).reset_index()
    g["margem_pct"] = (g["margem"] / g["receita_bruta"] * 100).round(2)
    g["itens_por_pedido"] = g["itens_por_pedido"].round(3)
    g["ticket_medio"] = g["ticket_medio"].round(2)
    g["share_pedidos_pct"] = (g["pedidos"] / len(df) * 100).round(2)
    g["share_desconto_pct"] = (g["desconto_reais"] / df["desconto_reais"].sum() * 100).round(2)

    com = g[g["pedidos"] > 0]
    amp_itens = float(com["itens_por_pedido"].max() - com["itens_por_pedido"].min())
    amp_ticket = float(com["ticket_medio"].max() - com["ticket_medio"].min())
    ticket_ref = float(com["ticket_medio"].mean())
    return {
        "faixas": g.drop(columns=["margem"]).to_dict(orient="records"),
        "amplitude_itens_por_pedido": round(amp_itens, 3),
        "amplitude_ticket_medio": round(amp_ticket, 2),
        "amplitude_ticket_pct": round(amp_ticket / ticket_ref * 100, 2),
        "leitura": (
            "Itens/pedido e ticket médio praticamente não variam entre as faixas, "
            "enquanto a margem cai monotonicamente conforme o desconto sobe: o desconto "
            "reduz margem sem comprar volume proporcional."
        ),
        "ressalva_causal": (
            "CORRELAÇÃO, NÃO CAUSALIDADE. Sem grupo de controle nem variação exógena do "
            "desconto, o resultado é compatível com viés de seleção. Confirmar com teste A/B."
        ),
    }


@ferramenta(
    "simular_teto_desconto",
    """Simula o efeito de impor um TETO de desconto: todos os pedidos com desconto
    acima do teto passam a receber exatamente o teto. Devolve a contribuição
    preservada em R$, os pedidos afetados e o PONTO DE EQUILÍBRIO (quanto dos
    pedidos afetados a empresa poderia perder antes de o ganho zerar), sob
    premissa de volume constante. O recorte da população simulada é parâmetro e
    vem declarado no resultado: por padrão usa a base de DECISÃO do caso (ano
    2023, pedidos mantidos, novembro fora, por ser Black Friday sob orçamento de
    campanha). Use convencao='diagnostico' para toda a base aprovada de 13
    meses.""",
    {"teto_pct": "teto de desconto em % (ex '25'); omita para usar a política vigente",
     "canal": "restringe o teto a um canal (ex 'Marketplace'); omita para todos",
     "categoria": "restringe o teto a uma categoria; omita para todas",
     "convencao": "'decisao' (padrão: 2023, pedidos mantidos, novembro fora) ou "
                  "'diagnostico' (toda a base aprovada, 13 meses)",
     "ano": "ano-calendário do recorte (ex '2023'); omita para o padrão da convenção",
     "excluir_meses": "meses fora do teto (ex 'novembro' ou '[11]'); '[]' inclui todos",
     "excluir_devolvidos": "'true' simula só pedidos mantidos; 'false' inclui devolvidos"},
    principais=["teto_pct"],
)
def simular_teto_desconto(teto_pct=None, canal=None, categoria=None,
                          convencao=None, ano=None, excluir_meses=None,
                          excluir_devolvidos=None) -> dict:
    teto_pct, origem_teto = _teto_ou_politica(teto_pct, canal, categoria,
                                              "simular_teto_desconto")
    teto = float(teto_pct) / 100 if float(teto_pct) > 1 else float(teto_pct)

    # O recorte temporal e de devolução vem ANTES do recorte de canal/categoria:
    # `populacao` é a base inteira sob a mesma convenção, e é contra ela que o
    # efeito em p.p. é medido. Medir o ganho de um canal contra a receita de
    # OUTRA população (a base sem recorte) misturava escopos em campos vizinhos
    # do mesmo retorno, que é exatamente o que produz erro de atribuição na
    # redação final.
    r = recorte.resolver(convencao, ano, excluir_meses, excluir_devolvidos)
    populacao = recorte.aplicar(carregar_vendas(), r)
    if populacao.empty:
        raise ValueError(f"nenhum pedido no recorte {recorte.descrever(r)}")

    # Uma política que vale para um canal só governa os pedidos daquele canal —
    # então o recorte também filtra a população simulada.
    df, filtros = populacao, {}
    for col, val in [("canal", canal), ("categoria", categoria)]:
        if val in (None, ""):
            continue
        val = normalizar_filtro(col, val, sorted(populacao[col].astype(str).unique()))
        df = df[df[col].astype(str) == val]
        filtros[col] = val
    if df.empty:
        raise ValueError(f"nenhum pedido no recorte {filtros}")

    acima = df[df["desconto_pct"] > teto]
    desconto_novo = df["desconto_reais"].where(df["desconto_pct"] <= teto,
                                               df["receita_bruta"] * teto)
    recuperado = float((df["desconto_reais"] - desconto_novo).sum())

    # Ponto de equilíbrio: o ganho é o desconto que deixa de ser concedido; a
    # perda máxima tolerável é a margem que esses mesmos pedidos ainda trariam
    # JÁ COM O TETO APLICADO. Se a empresa perder mais que essa fração dos
    # pedidos afetados, o ganho se anula. É esta grandeza que sustenta a regra
    # de parada do teste controlado.
    excedente_afetados = (acima["desconto_reais"] - acima["receita_bruta"] * teto)
    margem_afetados_pos_teto = float(
        (acima["margem_contribuicao"] + excedente_afetados).sum())
    equilibrio = (recuperado / margem_afetados_pos_teto * 100
                  if margem_afetados_pos_teto > 0 else None)

    rb_pop = float(populacao["receita_bruta"].sum())
    rb_recorte = float(df["receita_bruta"].sum())
    margem_pop = float(populacao["margem_contribuicao"].sum())
    meses = recorte.bloco(r, populacao)["meses_observados"]

    return {
        "teto_aplicado_pct": round(teto * 100, 2),
        "origem_do_teto": origem_teto,
        "recorte_aplicado": recorte.bloco(r, df),
        "recorte": filtros or {"escopo": "toda a população do recorte"},
        "pedidos_no_recorte": int(len(df)),
        "pedidos_afetados": int(len(acima)),
        "pct_pedidos_afetados": round(len(acima) / len(df) * 100, 2),
        "receita_bruta_afetada": round(float(acima["receita_bruta"].sum()), 2),
        "desconto_atual_no_grupo": round(float(acima["desconto_reais"].sum()), 2),
        "desconto_pos_teto_no_grupo": round(float(desconto_novo[acima.index].sum()), 2),
        "margem_recuperada_reais": round(recuperado, 2),
        "contribuicao_preservada_reais": round(recuperado, 2),
        "ponto_de_equilibrio_pct": round(equilibrio, 2) if equilibrio is not None else None,
        "definicao_ponto_de_equilibrio": (
            "percentual dos pedidos AFETADOS que poderiam deixar de acontecer antes "
            "de o ganho se anular = contribuição preservada ÷ margem desses mesmos "
            "pedidos já com o teto aplicado"
        ),
        "margem_atual_reais": round(margem_pop, 2),
        "margem_pos_teto_reais": round(margem_pop + recuperado, 2),
        "ganho_margem_pp": round(recuperado / rb_pop * 100, 3),
        "base_do_ganho_pp": (
            "receita bruta de toda a população do recorte declarado "
            f"(R$ {rb_pop:,.2f})".replace(",", "X").replace(".", ",").replace("X", ".")
        ),
        "ganho_margem_pp_no_segmento": (round(recuperado / rb_recorte * 100, 3)
                                        if filtros else None),
        # Sem dizer o período, o modelo inventa um: numa resposta real ele
        # apresentou os R$ 13.811,15 como ganho MENSAL, quando o valor é do
        # acumulado de 13 meses da base. A ferramenta declara o próprio escopo
        # temporal e, quando o recorte não é um ano fechado, também o valor
        # anualizado — para a frase "por ano" nunca ser conta do modelo.
        "periodo_coberto": _periodo_coberto(populacao),
        "valor_anualizado_reais": (round(recuperado, 2) if meses == 12
                                   else round(recuperado / meses * 12, 2)),
        "nota_anualizacao": (
            "o recorte cobre 12 meses: o valor já é anual"
            if meses == 12 else
            f"o recorte cobre {meses} meses; `valor_anualizado_reais` é o acumulado "
            f"reproporcionado para 12 meses"
        ),
        "premissa": PREMISSA_VOLUME,
    }


@ferramenta(
    "cenarios_reducao_desconto",
    """Cenários conservador / base / agressivo de redução do desconto no grupo que
    hoje recebe acima de um limiar (padrão 25%). Reduz o desconto médio do grupo
    em 25% / 50% / 75% do excedente sobre o limiar, sob volume constante.""",
    {"limiar_pct": "limiar do grupo alvo em % (padrão 25)"},
)
def cenarios_reducao_desconto(limiar_pct=25) -> dict:
    lim = float(limiar_pct) / 100 if float(limiar_pct) > 1 else float(limiar_pct)
    df = carregar_vendas()
    alvo = df[df["desconto_pct"] > lim]
    if alvo.empty:
        raise ValueError(f"nenhum pedido acima de {lim*100:.0f}% de desconto")
    rb = float(df["receita_bruta"].sum())
    margem_atual = float(df["margem_contribuicao"].sum())
    excedente = float((alvo["desconto_reais"] - alvo["receita_bruta"] * lim).sum())

    cenarios = []
    for nome, captura in [("conservador", 0.25), ("base", 0.50), ("agressivo", 0.75)]:
        ganho = excedente * captura
        cenarios.append({
            "cenario": nome,
            "captura_do_excedente_pct": round(captura * 100),
            "descricao": f"reduz {captura*100:.0f}% do desconto que excede {lim*100:.0f}%",
            "margem_recuperada_reais": round(ganho, 2),
            "ganho_margem_pp": round(ganho / rb * 100, 3),
            "margem_pct_resultante": round((margem_atual + ganho) / rb * 100, 2),
        })
    return {
        "limiar_pct": round(lim * 100, 2),
        "grupo_alvo": {
            "pedidos": int(len(alvo)),
            "pct_dos_pedidos": round(len(alvo) / len(df) * 100, 2),
            "receita_bruta": round(float(alvo["receita_bruta"].sum()), 2),
            "desconto_reais": round(float(alvo["desconto_reais"].sum()), 2),
            "share_do_desconto_total_pct": round(
                float(alvo["desconto_reais"].sum()) / float(df["desconto_reais"].sum()) * 100, 2),
            "margem_pct": round(float(alvo["margem_contribuicao"].sum())
                                / float(alvo["receita_bruta"].sum()) * 100, 2),
        },
        "excedente_sobre_limiar_reais": round(excedente, 2),
        "margem_pct_atual": round(margem_atual / rb * 100, 2),
        "cenarios": cenarios,
        "premissa": PREMISSA_VOLUME,
    }


@ferramenta(
    "simular_desconto_em_segmento",
    """Simula APLICAR um desconto hipotético a um recorte da base (canal, mês e/ou
    categoria) e devolve o efeito na margem do segmento e na margem CONSOLIDADA.
    Diferente de simular_teto_desconto (que impõe um teto), esta ferramenta define
    a taxa de desconto do segmento no valor informado. Serve para perguntas do tipo
    'e se eu desse 30% de desconto no Marketplace em novembro?'. Volume constante.""",
    {"desconto_pct": "desconto a aplicar em % (ex '30'); omita para usar o teto da "
                     "política vigente do recorte",
     "canal": "filtrar por canal (ex 'Marketplace'); omita para todos",
     "mes": "filtrar por mês AAAA-MM (ex '2023-11'); omita para todos",
     "categoria": "filtrar por categoria; omita para todas"},
    principais=["desconto_pct"],
)
def simular_desconto_em_segmento(desconto_pct=None, canal: str | None = None,
                                 mes: str | None = None,
                                 categoria: str | None = None) -> dict:
    desconto_pct, origem_desconto = _teto_ou_politica(
        desconto_pct, canal, categoria, "simular_desconto_em_segmento", "desconto_pct")
    novo = float(desconto_pct) / 100 if float(desconto_pct) > 1 else float(desconto_pct)
    if not 0 <= novo <= 1:
        raise ValueError("desconto_pct deve estar entre 0 e 100")
    df = carregar_vendas()

    filtros: dict[str, str] = {}
    seg = df
    for col, val in [("canal", canal), ("mes", mes), ("categoria", categoria)]:
        if val in (None, ""):
            continue
        disponiveis = sorted(df[col].astype(str).unique())
        # 'novembro' e 'marketplace' viram '2023-11' e 'Marketplace' aqui: quem
        # pergunta escreve em português, e recusar a forma escrita custou a
        # resposta inteira em produção (ver vertice/engine/filtros.py).
        val = normalizar_filtro(col, val, disponiveis)
        seg = seg[seg[col].astype(str) == val]
        filtros[col] = val
    if seg.empty:
        raise ValueError(f"nenhum pedido no segmento {filtros}")

    rb_seg = float(seg["receita_bruta"].sum())
    rb_total = float(df["receita_bruta"].sum())
    margem_total = float(df["margem_contribuicao"].sum())
    desc_atual = float(seg["desconto_reais"].sum())
    desc_novo = rb_seg * novo
    delta = desc_novo - desc_atual          # >0 = desconto aumenta = margem cai
    margem_seg = float(seg["margem_contribuicao"].sum())

    return {
        "segmento": filtros or {"escopo": "base inteira"},
        "periodo_coberto": _periodo_coberto(seg),
        "desconto_aplicado_pct": round(novo * 100, 2),
        "origem_do_desconto": origem_desconto,
        "pedidos_no_segmento": int(len(seg)),
        "pct_dos_pedidos": round(len(seg) / len(df) * 100, 2),
        "receita_bruta_segmento": round(rb_seg, 2),
        "pct_da_receita_total": round(rb_seg / rb_total * 100, 2),
        "desconto_atual_pct_no_segmento": round(desc_atual / rb_seg * 100, 2),
        "desconto_atual_reais": round(desc_atual, 2),
        "desconto_simulado_reais": round(desc_novo, 2),
        "variacao_desconto_reais": round(delta, 2),
        "efeito_no_segmento": {
            "margem_atual_reais": round(margem_seg, 2),
            "margem_simulada_reais": round(margem_seg - delta, 2),
            "margem_atual_pct": round(margem_seg / rb_seg * 100, 2),
            "margem_simulada_pct": round((margem_seg - delta) / rb_seg * 100, 2),
            "variacao_pp": round(-delta / rb_seg * 100, 2),
        },
        "efeito_consolidado": {
            "margem_atual_reais": round(margem_total, 2),
            "margem_simulada_reais": round(margem_total - delta, 2),
            "margem_atual_pct": round(margem_total / rb_total * 100, 2),
            "margem_simulada_pct": round((margem_total - delta) / rb_total * 100, 2),
            "variacao_pp": round(-delta / rb_total * 100, 2),
            "impacto_reais": round(-delta, 2),
        },
        "premissa": PREMISSA_VOLUME + (
            " Atenção ao sentido desta simulação: se ela AUMENTA o desconto, volume constante "
            "é o cenário mais pessimista (todo o desconto extra vira perda de margem). "
            "A tabela de faixas de desconto mostra que, historicamente, volume e ticket não "
            "acompanharam o desconto — mas isso é correlação e não prova que um desconto novo "
            "não geraria volume incremental. Só um teste A/B responde."
        ),
    }


@ferramenta(
    "simular_reajuste_preco",
    """Simula um REAJUSTE DE PREÇO em um recorte (canal, categoria e/ou mês) e
    devolve o efeito na margem do segmento e na consolidada. Responde "qual é o
    impacto de um reajuste de 4,9% no Marketplace?". O custo de produto e o
    frete não mudam: o reajuste vai inteiro para a margem. PREMISSA FORTE:
    volume constante — elasticidade de preço não é estimável nesta base
    (observacional, sem variação exógena de preço), então o resultado é o TETO
    do ganho, não uma previsão.""",
    {"reajuste_pct": "reajuste em % (ex '4.9'); negativo simula redução de preço",
     "canal": "filtrar por canal; omita para todos",
     "categoria": "filtrar por categoria; omita para todas",
     "mes": "filtrar por mês AAAA-MM; omita para todos"},
    obrigatorios=["reajuste_pct"],
    principais=["reajuste_pct"],
)
def simular_reajuste_preco(reajuste_pct, canal: str | None = None,
                           categoria: str | None = None, mes: str | None = None) -> dict:
    taxa = float(reajuste_pct)
    taxa = taxa * 100 if -1 < taxa < 1 and taxa != 0 else taxa
    if not -100 <= taxa <= 100:
        raise ValueError("reajuste_pct deve estar entre -100 e 100")

    df = carregar_vendas()
    filtros: dict[str, str] = {}
    seg = df
    for col, val in [("canal", canal), ("categoria", categoria), ("mes", mes)]:
        if val in (None, ""):
            continue
        val = normalizar_filtro(col, val, sorted(df[col].astype(str).unique()))
        seg = seg[seg[col].astype(str) == val]
        filtros[col] = val
    if seg.empty:
        raise ValueError(f"nenhum pedido no segmento {filtros}")

    rb_seg = float(seg["receita_bruta"].sum())
    rb_total = float(df["receita_bruta"].sum())
    margem_seg = float(seg["margem_contribuicao"].sum())
    margem_total = float(df["margem_contribuicao"].sum())
    # O desconto é percentual sobre o preço, então acompanha o reajuste; custo e
    # frete não. O ganho líquido é a receita adicional menos o desconto adicional.
    desc_seg = float(seg["desconto_reais"].sum())
    ganho = (rb_seg - desc_seg) * taxa / 100

    return {
        "segmento": filtros or {"escopo": "base inteira"},
        "periodo_coberto": _periodo_coberto(seg),
        "reajuste_pct": round(taxa, 4),
        "pedidos_no_segmento": int(len(seg)),
        "receita_bruta_atual": round(rb_seg, 2),
        "receita_bruta_simulada": round(rb_seg * (1 + taxa / 100), 2),
        "ganho_de_margem_reais": round(ganho, 2),
        "efeito_no_segmento": {
            "margem_atual_reais": round(margem_seg, 2),
            "margem_simulada_reais": round(margem_seg + ganho, 2),
            "margem_atual_pct": round(margem_seg / rb_seg * 100, 2),
            "margem_simulada_pct": round((margem_seg + ganho) / (rb_seg * (1 + taxa / 100)) * 100, 2),
        },
        "efeito_consolidado": {
            "margem_atual_reais": round(margem_total, 2),
            "margem_simulada_reais": round(margem_total + ganho, 2),
            "variacao_pp": round(
                (margem_total + ganho) / (rb_total + rb_seg * taxa / 100) * 100
                - margem_total / rb_total * 100, 3),
        },
        "premissa": (
            "PREMISSA EXPLÍCITA: volume constante e mix constante. Reajuste de preço "
            "muda a demanda, e esta base não permite estimar elasticidade — não há "
            "variação exógena de preço nem grupo de controle. O número é o TETO do "
            "ganho (nenhum cliente deixa de comprar), não uma previsão. Custo de "
            "produto e frete são mantidos; o desconto percentual acompanha o preço."
        ),
    }
