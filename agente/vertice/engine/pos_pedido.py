"""Ponte do pós-pedido: a margem calculada que não se realiza.

Esta é a ÚNICA ferramenta do motor que lê pedidos não aprovados, e a exceção é
deliberada e travada.

Por quê a exceção existe
------------------------
A premissa P1 ("só `status_pagamento == 'Aprovado'` é receita real") é correta
para dimensionar margem, preço e desconto: usar a receita cheia inflaria a base
de qualquer cálculo de oportunidade. Mas ela apaga da vista exatamente o que o
diagnóstico do caso precisa mostrar: a margem que a empresa CALCULA e não
realiza, porque o pedido é cancelado, fica pendente, volta devolvido ou custa
atendimento depois de faturado.

Sem esta ferramenta, o maior número do diagnóstico (R$ 2,63 milhões, 26,7% da
margem calculada de 2023) não tem nenhuma função que o produza, e a única forma
de citá-lo seria o modelo fazer a conta — que é precisamente o que este projeto
não aceita.

A trava contra dupla contagem
-----------------------------
Os quatro ramos NÃO se somam ao déficit medido por `margem_consolidada`. Eles
explicam o caminho entre a margem CALCULADA (todos os status) e a margem que se
REALIZA. Somar os dois é contar a mesma perda duas vezes.

E, mais importante para o comitê: cancelamento e pendência **não são economia
capturável**. São margem que nunca se realizou. Tratá-los como oportunidade
produziria uma proposta fantasiosa de R$ 2,63 milhões, que é o erro mais caro
que este bloco pode gerar. Todo retorno carrega essa advertência em campo
próprio, e o valor recuperável de cada ramo vem declarado separadamente.
"""
from __future__ import annotations

import pandas as pd

from .. import config
from ..data import carregar_atendimento_vinculado, carregar_vendas
from .margin import recorte_janela
from .registry import ferramenta

# Categorias em que "Tamanho errado" é motivo plausível, porque o produto tem
# grade de tamanho. Em Beleza e Lifestyle o mesmo motivo aparece na mesma
# proporção e não pode ser tratado como troca: é o que torna o campo de motivo
# não confiável (448 casos em 2023).
#
# ESTA LISTA NÃO ENTRA MAIS NO VALOR PUBLICADO. Ela sobrevive porque alimenta
# `se_tamanho_errado_fosse_troca_reais`, a leitura alternativa declarada no
# resultado — não porque a ponte a subtraia. Ver a nota sobre a premissa de
# devolução em `perda_pos_pedido`.
CATEGORIAS_COM_GRADE = ("Moda", "Acessórios")


@ferramenta(
    "perda_pos_pedido",
    """Ponte entre a margem CALCULADA e a margem que se REALIZA: quanto da margem
    de contribuição do ano se perde DEPOIS que o pedido é registrado, aberta nos
    quatro ramos — cancelamento, pendência, devolução e atendimento. É a ÚNICA
    ferramenta que lê pedidos não aprovados, e por isso declara explicitamente
    que seus valores NÃO se somam ao déficit medido por margem_consolidada.
    ATENÇÃO: cancelamento e pendência são margem que nunca se realizou, NÃO
    economia capturável — nenhum deles entra em caso-base ou business case.""",
    {"ano": "ano-calendário da ponte (padrão 2023)",
     "dias": "tamanho da janela em dias; informado, substitui o ano-calendário",
     "ate": "último dia da janela AAAA-MM-DD (só com 'dias')"},
)
def perda_pos_pedido(ano=config.ANO_BASE, dias=None, ate: str | None = None) -> dict:
    todos = carregar_vendas(apenas_aprovados=False)
    tickets = carregar_atendimento_vinculado()

    # O recorte padrão continua sendo o ano-calendário. `dias`/`ate` existem
    # para a mesma ponte sobre a janela escolhida na tela de relatório — os
    # tickets acompanham pela data do PEDIDO a que estão ligados, que é o que
    # os prende à margem daquele período.
    if dias:
        todos, janela = recorte_janela(todos, dias, ate)
        td = pd.to_datetime(tickets["data_pedido"])
        ini, fim = pd.to_datetime(janela["inicio"]), pd.to_datetime(janela["fim"])
        tickets = tickets[(td >= ini) & (td < fim + pd.Timedelta(days=1))]
        recorte = {"tipo": "janela", **janela}
        descricao = f"{janela['inicio']} a {janela['fim']}"
    else:
        ano = int(ano)
        todos = todos[todos["ano"] == ano]
        tickets = tickets[tickets["ano"] == ano]
        recorte = {"tipo": "ano", "ano": ano}
        descricao = str(ano)

    if todos.empty:
        raise ValueError(f"nenhum pedido em {descricao}")
    aprov = todos[todos["status_pagamento"] == config.STATUS_RECEITA_VALIDA]

    margem_calculada = float(todos["margem_contribuicao"].sum())

    canc = todos[todos["status_pagamento"] == "Cancelado"]
    pend = todos[todos["status_pagamento"] == "Aguardando"]

    # Devolução: TODO pedido devolvido conta. A margem do pedido some e o frete
    # de ida já foi pago — os dois entram, sem nenhuma exclusão por motivo.
    #
    # Havia aqui uma exclusão: "Tamanho errado" em Moda e Acessórios era tratado
    # como TROCA (o cliente fica com o produto no tamanho certo, a margem se
    # preserva), e os R$ 151.298,33 correspondentes saíam da ponte. A premissa é
    # defensável, mas não é a que o case publica: nem a demonstração do
    # resultado do deck — que reembolsa a receita líquida inteira dos 3.485
    # devolvidos e recupera só o CMV — nem o painel da Vértice — que conta os
    # 3.639 devolvidos sem separar motivo — tratam essas devoluções como troca.
    # Com a exclusão fora, a ponte reproduz o deck ao centavo: R$ 2.628.111,95
    # de perda e R$ 7.204.819,99 de margem que se realiza.
    #
    # A leitura alternativa não foi apagada: ela sai declarada no ramo, em
    # `se_tamanho_errado_fosse_troca_reais`, que é a origem dos R$ 1,18 mi de
    # "exposição central" citados no rodapé do slide 6.
    dev = aprov[aprov["devolvido"]]
    devolucao = float((dev["margem_contribuicao"] + dev["custo_frete"]).sum())
    troca = dev[(dev["motivo_devolucao"] == "Tamanho errado")
                & (dev["categoria"].isin(CATEGORIAS_COM_GRADE))]
    margem_troca = float(troca["margem_contribuicao"].sum())

    # Piso factual: o que a base REGISTRA como custo incorrido, sem nenhuma
    # premissa de reembolso. É o número que sobrevive a qualquer discussão sobre
    # a premissa de devolução, e por isso acompanha a exposição central.
    tickets_dev = tickets[tickets["devolvido"]]
    piso_factual = float(dev["custo_frete"].sum()) + float(
        tickets_dev["custo_operacional_ticket"].sum())

    atendimento = float(tickets["custo_operacional_ticket"].sum())

    total = float(canc["margem_contribuicao"].sum()) + float(
        pend["margem_contribuicao"].sum()) + devolucao + atendimento

    ramos = [
        {
            "ramo": "Devolução", "marca": "◐",
            "pedidos": int(len(dev)),
            "margem_perdida_reais": round(devolucao, 2),
            "recuperavel": "não estimável hoje",
            "controle": "Interno (dado e processo)",
            "dono": "COO / TI",
            "premissa": (
                "reembolso integral com item revendável, em TODOS os pedidos "
                "devolvidos — nenhum motivo é excluído. A base não registra "
                "destino do item, custo da logística reversa, data da devolução "
                "nem valor reembolsado, então o motivo declarado não sustenta "
                "tratar devolução como troca."),
            "se_tamanho_errado_fosse_troca_reais": round(devolucao - margem_troca, 2),
            "nota_leitura_alternativa": (
                f"se as devoluções por 'Tamanho errado' em "
                f"{' e '.join(CATEGORIAS_COM_GRADE)} ({int(len(troca))} pedidos) "
                f"fossem tratadas como TROCA, a margem se preservaria e a perda "
                f"do ramo cairia {round(margem_troca, 2)}. NÃO é a premissa "
                f"publicada: é a leitura alternativa, declarada para quem "
                f"quiser discuti-la."),
        },
        {
            "ramo": "Cancelamento", "marca": "●",
            "pedidos": int(len(canc)),
            "margem_perdida_reais": round(float(canc["margem_contribuicao"].sum()), 2),
            "recuperavel": "R$ 0 — margem que nunca se realizou",
            "controle": "Interno + gateway de pagamento",
            "dono": "CFO",
            "premissa": "nenhuma: soma direta de status_pagamento == 'Cancelado'",
        },
        {
            "ramo": "Pendência", "marca": "●",
            "pedidos": int(len(pend)),
            "margem_perdida_reais": round(float(pend["margem_contribuicao"].sum()), 2),
            "recuperavel": "R$ 0 — saneamento de registro, não ganho",
            "controle": "Interno",
            "dono": "Financeiro / Operações",
            "premissa": "nenhuma: soma direta de status_pagamento == 'Aguardando'",
        },
        {
            "ramo": "Atendimento", "marca": "◐",
            "pedidos": int(len(tickets)),
            "margem_perdida_reais": round(atendimento, 2),
            "recuperavel": "fora do escopo de margem",
            "controle": "Interno",
            "dono": "COO",
            "premissa": (
                "custo operacional fixo por canal de entrada (R$ 2 ChatBot, R$ 15 "
                "e-mail/telefone/WhatsApp, R$ 45 Reclame Aqui), somado apenas nos "
                "tickets abertos DEPOIS da data do pedido e ligados a pedido "
                "aprovado; os abertos antes não podem ter sido causados por ele"),
        },
    ]
    ramos.sort(key=lambda x: -x["margem_perdida_reais"])

    return {
        "ano": ano,
        "recorte": recorte,
        "base": "TODOS os status de pagamento (única exceção à premissa P1 no motor)",
        "margem_calculada_reais": round(margem_calculada, 2),
        "perda_pos_pedido_reais": round(total, 2),
        "perda_pct_da_margem_calculada": (round(total / margem_calculada * 100, 2)
                                          if margem_calculada else None),
        "margem_que_se_realiza_reais": round(margem_calculada - total, 2),
        "ramos": ramos,
        "formula": ("margem que se realiza = margem calculada − cancelamento − pendência "
                    "− devolução − atendimento (cada termo é um ramo, sem interseção)"),
        "piso_factual_da_devolucao_reais": round(piso_factual, 2),
        "nota_piso_factual": (
            "custo REGISTRADO na base, sem nenhuma premissa de reembolso: frete de ida "
            "dos pedidos devolvidos mais os tickets de atendimento ligados a eles. É o "
            "valor que sobrevive a qualquer discussão sobre a premissa de devolução."),
        "valor_recuperavel_total_reais": 0.0,
        "ALERTA_NAO_SOMAR": (
            "ESTES VALORES NÃO SE SOMAM ao déficit medido por margem_consolidada, "
            "simular_teto_desconto ou regra_frete_por_limiar: aqueles medem o que se "
            "perde ENTRE a receita bruta e a margem; este mede o que se perde DEPOIS "
            "da margem calculada. Somar os dois conta a mesma perda duas vezes."),
        "ALERTA_NAO_E_OPORTUNIDADE": (
            "Cancelamento e pendência são margem que NUNCA SE REALIZOU, não economia "
            "capturável: a pendência é margem que o relatório não deveria ter contado, "
            "e a causa do cancelamento não está na base (é uniforme em canal, categoria, "
            "meio de pagamento, ticket, quantidade e mês). Devolução e atendimento não "
            "têm meta em reais defensável enquanto os três campos ausentes (destino do "
            "item, custo reverso, motivo validado) não forem coletados. Apresentar este "
            "total como oportunidade de ganho é ERRO: ele dimensiona o problema e "
            "justifica coletar o dado, não promete recuperação."),
        "premissa": (
            "◐ ESTIMATIVA: os ramos de devolução e atendimento dependem das premissas "
            "declaradas em cada linha. Os ramos de cancelamento e pendência são ● fato "
            "calculado, sem premissa."),
    }


@ferramenta(
    "pendencias_antigas",
    """Pedidos com status 'Aguardando' há mais de N dias, e a margem não confirmada
    que eles carregam. Mede o estoque de pendências a sanear. A margem aqui NÃO é
    recuperável: é margem que o relatório não deveria estar contando.""",
    {"dias": "idade mínima em dias (padrão 30)",
     "ate": "data de corte AAAA-MM-DD; omita para o último dia da base"},
)
def pendencias_antigas(dias=30, ate: str | None = None) -> dict:
    dias = int(dias)
    todos = carregar_vendas(apenas_aprovados=False)
    corte_base = pd.to_datetime(ate) if ate else todos["data_pedido"].max()
    limite = corte_base - pd.Timedelta(days=dias)
    pend = todos[(todos["status_pagamento"] == "Aguardando")
                 & (todos["data_pedido"] < limite)]
    idade = (corte_base - pend["data_pedido"]).dt.days if len(pend) else None
    return {
        "dias_minimos": dias,
        "data_de_corte": str(corte_base.date()),
        "pedidos_pendentes": int(len(pend)),
        "margem_nao_confirmada_reais": round(float(pend["margem_contribuicao"].sum()), 2),
        "idade_media_dias": round(float(idade.mean()), 1) if idade is not None and len(pend) else None,
        "idade_maxima_dias": int(idade.max()) if idade is not None and len(pend) else None,
        "por_mes": (pend.groupby("mes", observed=True)["order_id"].count().to_dict()
                    if len(pend) else {}),
        "recuperavel_reais": 0.0,
        "leitura": (
            "Pedido 'Aguardando' há mais de um ano é falha de processo ou de registro. "
            "O saneamento não gera caixa: corrige a margem reportada, que hoje conta "
            "receita nunca confirmada."),
        "dono": "Financeiro / Operações",
    }
