"""Teste de aceite: o motor reproduz os números publicados no Livro de Números.

Este arquivo é a razão pela qual a divergência que originou esta correção não
pode voltar a acontecer sem que alguém veja.

A suíte já conferia identidade contábil, aditividade e comportamento do agente.
Nenhum teste conferia se uma ferramenta devolve o número que está no deck. Foi
exatamente nessa fresta que o motor e a apresentação passaram a responder
valores diferentes para a mesma pergunta: os dois estavam internamente corretos
e ninguém os comparava.

Cada asserção abaixo tem um ID do Livro de Números. Se uma falhar, ou o motor
mudou de comportamento ou o Livro mudou de valor, e as duas coisas exigem
decisão humana, não ajuste do teste.

É este arquivo que o "Passo 0" da demonstração ao vivo executa antes de
qualquer pergunta da banca.
"""
from __future__ import annotations

import pytest

from vertice.engine import executar

# Tolerância de um centavo: os valores do Livro são arredondados na publicação.
CENTAVO = 0.01


# ------------------------------------------------------- margem e receita
def test_N02_N03_pedidos_e_receita_liquida_de_2023():
    r = executar("margem_consolidada", {"ano": 2023})
    assert r["pedidos"] == 23388                                   # N02
    assert r["receita_liquida"] == pytest.approx(15966340.87, abs=CENTAVO)   # N03


def test_margem_de_2023_nos_dois_denominadores():
    """A mesma margem em R$, dois denominadores, ambos rotulados.

    54,34% (sobre receita líquida) é a convenção do deck e do comitê; 49,99%
    (sobre receita bruta) é a que fecha a decomposição MECE. Confundi-las é erro
    de 4,35 p.p., e é por isso que nenhuma das duas se chama apenas "margem".
    """
    r = executar("margem_consolidada", {"ano": 2023})
    assert r["margem_pct_sobre_liquida"] == pytest.approx(54.34, abs=0.01)
    assert r["margem_pct_sobre_bruta"] == pytest.approx(49.99, abs=0.01)
    assert r["denominadores"]["usado_na_comunicacao_ao_comite"] == "receita_liquida"


def test_N06_N07_N12_N13_margem_e_desconto_por_semestre():
    """Slide 3: a margem é estável e o desconto é que piora."""
    r = executar("comparar_periodos", {"periodo_a": "2023-01:2023-06",
                                       "periodo_b": "2023-07:2023-12"})
    s1, s2 = r["periodo_a"], r["periodo_b"]
    assert s1["margem_pct_sobre_liquida"] == pytest.approx(54.58, abs=0.01)   # N06
    assert s2["margem_pct_sobre_liquida"] == pytest.approx(54.12, abs=0.01)   # N07
    assert s1["desconto_pct"] == pytest.approx(7.53, abs=0.01)                # N12
    assert s2["desconto_pct"] == pytest.approx(8.44, abs=0.01)                # N13
    # A1 do apêndice: contribuição de cada semestre.
    assert s1["margem_contribuicao"] == pytest.approx(4166333.56, abs=CENTAVO)
    assert s2["margem_contribuicao"] == pytest.approx(4509278.44, abs=CENTAVO)


# --------------------------------------------------------- teto de desconto
def test_N38_teto_de_20_fora_de_novembro():
    """O número do caso-base, em cinco slides do deck."""
    r = executar("simular_teto_desconto", {"teto_pct": 20})
    assert r["contribuicao_preservada_reais"] == pytest.approx(241424.23, abs=CENTAVO)
    assert r["pct_pedidos_afetados"] == pytest.approx(19.81, abs=0.01)   # N38b
    assert r["ponto_de_equilibrio_pct"] == pytest.approx(26.3, abs=0.05)  # N38c
    # O recorte NÃO é escondido: vem declarado no resultado.
    rec = r["recorte_aplicado"]
    assert rec["convencao"] == "decisao"
    assert rec["ano"] == 2023
    assert rec["meses_excluidos"] == ["novembro"]
    assert rec["pedidos_devolvidos_excluidos"] is True


def test_N39_teto_de_25_fora_de_novembro():
    r = executar("simular_teto_desconto", {"teto_pct": 25})
    assert r["contribuicao_preservada_reais"] == pytest.approx(135074.12, abs=CENTAVO)
    assert r["pct_pedidos_afetados"] == pytest.approx(14.56, abs=0.01)   # N39b
    assert r["ponto_de_equilibrio_pct"] == pytest.approx(22.8, abs=0.05)  # N39c


@pytest.mark.parametrize("teto,recorte,ganho,afetados", [
    (15, "fora_nov", 379544.69, 24.83),   # A2_15_foranov — deck: R$ 379,5 mil
    (15, "ano", 469635.36, 25.70),        # A2_15_ano     — deck: R$ 469,6 mil
    (20, "fora_nov", 241424.23, 19.81),   # A2_20_foranov — deck: R$ 241,4 mil
    (20, "ano", 299518.63, 20.79),        # A2_20_ano     — deck: R$ 299,5 mil
    (25, "fora_nov", 135074.12, 14.56),   # A2_25_foranov — deck: R$ 135,1 mil
    (25, "ano", 167746.74, 15.29),        # A2_25_ano     — deck: R$ 167,7 mil
    (30, "fora_nov", 59424.74, 9.70),     # A2_30_foranov — deck: R$ 59,4 mil
    (30, "ano", 74408.06, 10.15),         # A2_30_ano     — deck: R$ 74,4 mil
])
def test_A2_tabela_completa_de_tetos_do_apendice(teto, recorte, ganho, afetados):
    """As oito linhas do apêndice A2 do deck, uma a uma."""
    params = {"teto_pct": teto}
    if recorte == "ano":
        params["excluir_meses"] = "[]"
    r = executar("simular_teto_desconto", params)
    assert r["contribuicao_preservada_reais"] == pytest.approx(ganho, abs=CENTAVO)
    assert r["pct_pedidos_afetados"] == pytest.approx(afetados, abs=0.01)


@pytest.mark.parametrize("categoria,ganho", [
    ("Moda", 83093.59), ("Beleza", 73457.21),
    ("Lifestyle", 51081.88), ("Acessórios", 33791.55),
])
def test_N38_por_categoria(categoria, ganho):
    r = executar("simular_teto_desconto", {"teto_pct": 20, "categoria": categoria})
    assert r["contribuicao_preservada_reais"] == pytest.approx(ganho, abs=CENTAVO)


def test_a_base_de_diagnostico_continua_disponivel_e_declarada():
    """As duas leituras convivem: o que muda é o recorte, não o cálculo.

    É esta a resposta para "por que vocês tiraram novembro?": não tiramos,
    parametrizamos, e o número com novembro está a uma chamada de distância.
    """
    diag = executar("simular_teto_desconto",
                    {"teto_pct": 20, "convencao": "diagnostico"})
    assert diag["contribuicao_preservada_reais"] == pytest.approx(369836.50, abs=CENTAVO)
    assert diag["recorte_aplicado"]["convencao"] == "diagnostico"
    assert diag["recorte_aplicado"]["meses_observados"] == 13
    # Acumulado de 13 meses NÃO é um ano: a ferramenta entrega a anualização
    # pronta para o texto não ter de fazer a conta.
    assert diag["valor_anualizado_reais"] == pytest.approx(341387.54, abs=CENTAVO)


# ------------------------------------------------------------------- frete
def test_N46_regra_de_frete_no_marketplace():
    r = executar("regra_frete_por_limiar", {})
    assert r["contribuicao_preservada_reais"] == pytest.approx(108026.16, abs=CENTAVO)
    assert r["aderencia_da_regra_nos_demais_canais_pct"] == pytest.approx(100.0, abs=0.01)
    assert r["controle"].startswith("EXTERNO")
    # Novembro NÃO sai daqui: a exclusão vale para a política de desconto (Black
    # Friday sob orçamento de campanha), não para a regra de frete.
    assert r["recorte_aplicado"]["meses_excluidos"] == []


def test_N40_a_regra_de_frete_e_objetiva_em_todos_os_canais():
    r = executar("regra_frete_por_limiar", {})
    assert set(r["aderencia_por_canal_pct"].values()) == {100.0}


def test_os_dois_metodos_de_frete_concordam_na_mesma_janela():
    """A regra determinística e o contrafactual estatístico medem a mesma coisa.

    Na mesma janela de 13 meses os dois ficam a 0,7% um do outro. Isso é
    argumento a favor da robustez do achado, e é assim que deve ser apresentado:
    não são dois números concorrentes, são duas rotas para o mesmo lugar.
    """
    regra = executar("regra_frete_por_limiar",
                     {"convencao": "diagnostico"})["contribuicao_preservada_reais"]
    contra = executar("custo_assimetria_frete", {})["frete_evitavel_reais"]
    assert abs(regra - contra) / contra < 0.01


# --------------------------------------------------------------- pós-pedido
def test_N18_N25_N26_N27_ponte_do_pos_pedido():
    """O título do deck: R$ 2,63 mi da margem de 2023 se perdem depois do pedido.

    Estes quatro valores reproduzem a demonstração do resultado do deck (slide
    17) ao centavo, e a nota NE8 os cita nominalmente. A ponte passou a bater
    quando a exclusão de troca saiu do ramo de devolução: nem o deck nem o
    painel da Vértice tratam "Tamanho errado" como troca, e a convenção do case
    é a deles.
    """
    r = executar("perda_pos_pedido", {})
    assert r["margem_calculada_reais"] == pytest.approx(9832931.94, abs=CENTAVO)   # N18
    assert r["perda_pos_pedido_reais"] == pytest.approx(2628111.95, abs=CENTAVO)   # N25
    assert r["perda_pct_da_margem_calculada"] == pytest.approx(26.7, abs=0.05)     # N26
    assert r["margem_que_se_realiza_reais"] == pytest.approx(7204819.99, abs=CENTAVO)  # N27


@pytest.mark.parametrize("ramo,valor,pedidos", [
    ("Devolução", 1335908.01, 3485),      # N21 — todos os devolvidos, sem exclusão
    ("Cancelamento", 774752.33, 2101),    # N19, N19b
    ("Pendência", 382567.61, 1049),       # N20, N20b
    ("Atendimento", 134884.00, 9127),     # N24
])
def test_os_quatro_ramos_da_ponte(ramo, valor, pedidos):
    r = executar("perda_pos_pedido", {})
    linha = next(x for x in r["ramos"] if x["ramo"] == ramo)
    assert linha["margem_perdida_reais"] == pytest.approx(valor, abs=CENTAVO)
    assert linha["pedidos"] == pedidos


def test_a_leitura_alternativa_de_troca_continua_declarada():
    """A premissa que saiu do valor publicado não saiu do resultado.

    O rodapé do slide 6 cita R$ 1,18 mi de "exposição central". Esse número
    nasce de tratar "Tamanho errado" em Moda e Acessórios como troca — leitura
    que o motor NÃO publica mais, porque nem o deck nem o painel a adotam. Ela
    continua calculada e rotulada no ramo: sem isso, o rodapé do deck ficaria
    sem nenhuma função que o produza, e a única forma de citá-lo seria o modelo
    fazer a conta.
    """
    r = executar("perda_pos_pedido", {})
    dev = next(x for x in r["ramos"] if x["ramo"] == "Devolução")
    assert dev["se_tamanho_errado_fosse_troca_reais"] == pytest.approx(1184609.68,
                                                                      abs=CENTAVO)
    assert "NÃO é a premissa" in dev["nota_leitura_alternativa"]
    # E a premissa publicada diz, em texto, que nenhum motivo é excluído.
    assert "nenhum motivo é excluído" in dev["premissa"]


def test_N22_piso_factual_da_devolucao():
    """O custo REGISTRADO, sem nenhuma premissa de reembolso."""
    r = executar("perda_pos_pedido", {})
    assert r["piso_factual_da_devolucao_reais"] == pytest.approx(64647.02, abs=CENTAVO)


def test_a_ponte_declara_que_nao_e_oportunidade_de_ganho():
    """A trava mais importante do módulo.

    Sem ela, R$ 2,63 mi viram uma "oportunidade" que não existe: cancelamento e
    pendência são margem que nunca se realizou. Apresentar isso como ganho
    recuperável seria a proposta fantasiosa que o caso não admite.
    """
    r = executar("perda_pos_pedido", {})
    assert r["valor_recuperavel_total_reais"] == 0.0
    assert "NÃO SE SOMAM" in r["ALERTA_NAO_SOMAR"]
    assert "NUNCA SE REALIZOU" in r["ALERTA_NAO_E_OPORTUNIDADE"]
    for ramo in ("Cancelamento", "Pendência"):
        linha = next(x for x in r["ramos"] if x["ramo"] == ramo)
        assert linha["recuperavel"].startswith("R$ 0")


# ------------------------------------------------------- KPIs e caso-base
def test_N57_N58_N59_N60_N61_kpis_de_aceite_do_roadmap():
    r = executar("kpis_do_teto", {"teto_pct": 20})
    assert r["kpi_resultado"]["taxa_de_desconto_atual_pct"] == pytest.approx(7.73, abs=0.01)
    assert r["kpi_resultado"]["taxa_de_desconto_sob_o_teto_pct"] == pytest.approx(5.80, abs=0.01)
    assert r["kpi_risco"]["equilibrio_em_pct_de_todos_os_pedidos"] == pytest.approx(5.2, abs=0.05)
    assert r["kpi_risco"]["regra_de_parada_queda_de_pedidos_pct"] == pytest.approx(2.6, abs=0.05)
    assert r["kpi_acompanhamento"]["kpi_do_comite"] == pytest.approx(20118.69, abs=CENTAVO)


def test_N47_N48_N49_caso_base_do_plano():
    r = executar("caso_base_do_plano", {})
    assert r["caso_base_interno_reais"] == pytest.approx(241424.23, abs=CENTAVO)   # N47
    assert r["caso_base_com_externo_reais"] == pytest.approx(349450.39, abs=CENTAVO)  # N48
    assert r["parcela_sob_controle_interno_pct"] == pytest.approx(69.1, abs=0.05)  # N49
    controles = {a["controle"] for a in r["alavancas"]}
    assert controles == {"INTERNO", "EXTERNO"}


def test_o_caso_base_nao_inclui_frente_sem_valor_defensavel():
    """Devolução, cancelamento e pendência ficam de fora, e o resultado diz por quê."""
    r = executar("caso_base_do_plano", {})
    assert "NÃO entram" in r["fora_do_caso_base"]
    assert len(r["alavancas"]) == 2


# ------------------------------------------------- procedência do resultado
def test_todo_resultado_carrega_marca_e_hash_da_base():
    """Promessa do slide 9: hash da base e marca ● ◐ ○ em cada resultado."""
    fato = executar("relatorio_auditoria_dados", {})
    estimativa = executar("simular_teto_desconto", {"teto_pct": 20})
    direcao = executar("cobertura_de_dados", {"assunto": "ltv"})
    assert fato["marca"] == "●"
    assert estimativa["marca"] == "◐"
    assert direcao["marca"] == "○"
    for r in (fato, estimativa, direcao):
        assert r["hash_base"] == "0199d2f3e060"
        assert len(r["hash_base"]) == 12


def test_o_hash_nao_entra_no_conjunto_rastreavel_do_guardrail():
    """Um hash hexadecimal contém dígitos: deixá-lo entrar daria lastro falso a
    qualquer número que casasse com um pedaço dele."""
    from vertice.agent.verificacao import coletar_numeros

    r = executar("simular_teto_desconto", {"teto_pct": 20})
    numeros = coletar_numeros(r)
    assert 199.0 not in numeros and 2903.0 not in numeros


def test_o_guardrail_aprova_a_frase_do_deck():
    """A prova de que a convergência funcionou.

    Antes desta correção, a frase do slide 11 era BLOQUEADA pelo próprio
    guardrail do agente, porque o motor devolvia outro número. Agora ela passa.
    """
    from vertice.agent.verificacao import coletar_numeros, verificar_numeros

    r = executar("simular_teto_desconto", {"teto_pct": 20})
    frase = ("Com teto de 20% fora de novembro, a Vértice preservaria R$ 241.424,23 "
             "por ano (2023, pedidos mantidos). O teto atinge 19,81% dos pedidos e o "
             "ganho só zera se 26,32% deles deixarem de acontecer.")
    ver = verificar_numeros(frase, coletar_numeros(r), "teto de 20% fora de novembro?")
    assert ver["ok"], f"números sem lastro: {ver['suspeitos']}"
