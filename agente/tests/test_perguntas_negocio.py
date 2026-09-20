"""As 95 perguntas de negócio do case, rodadas contra o agente de verdade.

Não é teste de parser. Cada pergunta entra pelo roteador determinístico, a
ferramenta escolhida é executada no motor e o resultado é conferido — a mesma
sequência que roda em produção, sem o modelo no meio (o modelo explica o
resultado; ele não escolhe o número).

O critério de PASS é o do enunciado: intenção certa, ferramenta certa,
parâmetros certos, ferramenta executada, resultado utilizável, resposta presa
ao que a ferramenta devolveu. Pergunta que o motor não sustenta tem de sair
como limitação declarada — não como número plausível.

Três blocos convivem aqui de propósito:

  * roteadas — consulta estruturada: o roteador decide, o Python calcula.
    Falhar aqui é bug de roteamento, e o teste aponta onde.
  * PERGUNTA_COMPLEXA — investigação aberta (bloco executivo). O esperado é
    justamente NÃO haver ferramenta única: quem conduz é o ReAct, com o
    catálogo inteiro à disposição.
  * LIMITE_DE_DADOS — a pergunta cujo campo EXISTE na base e não sustenta a
    resposta (CAC, LTV, churn, causa de devolução). O esperado é a recusa
    medida, com a lacuna nomeada.

A tabela CASOS é a régua: mudou o roteamento de uma pergunta do case, o teste
quebra e alguém decide se a mudança é melhoria ou regressão.
"""
import pytest

from vertice.agent.router import (APLICAR_DESCONTO, COERENCIA_PRAZO,
                                  COMPARACAO_PERIODOS, CUSTO_DE_NAO_AGIR,
                                  DEVOLUCOES, FRETE, FRETE_PANORAMA,
                                  FRETE_REGRA_LIMIAR,
                                  LIMITE_DE_DADOS, MARGEM_CONSOLIDADA,
                                  MARGEM_NEGATIVA, MARGEM_POR_DIMENSAO,
                                  MARKETING, PERGUNTA_COMPLEXA, POLITICA_ALCADA,
                                  REAJUSTE_PRECO, RELACAO_DESCONTO_MARGEM,
                                  SAZONALIDADE, TESTE_ESTATISTICO, TETO_DESCONTO,
                                  VALIDACAO_MOTIVOS, VIOLACAO_POLITICA, rotear,
                                  validar_parametros)
from vertice.agent.verificacao import coletar_numeros, verificar_numeros
from vertice.engine import executar

# (nº no enunciado, pergunta, intenção esperada, ferramenta esperada, parâmetros)
CASOS = [
    (1, 'Qual é o desconto médio atual?',
     MARGEM_CONSOLIDADA, 'margem_consolidada', {}),
    (2, 'Como o desconto evoluiu ao longo do semestre?',
     MARGEM_POR_DIMENSAO, 'margem_por_dimensao', {'dimensao': 'mes'}),
    (3, 'Qual é o impacto dos descontos sobre a margem?',
     RELACAO_DESCONTO_MARGEM, 'tabela_faixas_desconto', {}),
    (4, 'Em quais canais o desconto é mais elevado?',
     MARGEM_POR_DIMENSAO, 'margem_por_dimensao', {'dimensao': 'canal'}),
    (5, 'Em quais categorias o desconto é mais elevado?',
     MARGEM_POR_DIMENSAO, 'margem_por_dimensao', {'dimensao': 'categoria'}),
    (6, 'Quais produtos concentram os maiores descontos?',
     MARGEM_POR_DIMENSAO, 'margem_por_dimensao', {'dimensao': 'sku'}),
    (7, 'Quantos pedidos estão acima do teto de desconto?',
     VIOLACAO_POLITICA, 'pedidos_acima_do_teto', {}),
    (8, 'Qual é o custo de não agir sobre esses descontos?',
     CUSTO_DE_NAO_AGIR, 'cenarios_reducao_desconto', {}),
    (9, 'Qual canal apresenta maior perda de margem associada a descontos?',
     MARGEM_POR_DIMENSAO, 'margem_por_dimensao', {'dimensao': 'canal'}),
    (10, 'Qual categoria apresenta maior impacto dos descontos na margem?',
     MARGEM_POR_DIMENSAO, 'margem_por_dimensao', {'dimensao': 'categoria'}),
    (11, 'O que aconteceria se eu limitasse o desconto a 25%?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 25.0}),
    (12, 'O que aconteceria se eu limitasse o desconto a 20%?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 20.0}),
    (13, 'O que aconteceria se eu limitasse o desconto a 17%?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 17.0}),
    (14, 'O que aconteceria se eu limitasse o desconto de Moda a 17%?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 17.0, 'categoria': 'Moda'}),
    (15, 'O que aconteceria se eu limitasse o desconto de Moda no Email Marketing a 17%?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 17.0, 'canal': 'Email Marketing', 'categoria': 'Moda'}),
    (16, 'O que aconteceria se eu aplicasse um desconto de 17% em Moda?',
     APLICAR_DESCONTO, 'simular_desconto_em_segmento', {'desconto_pct': 17.0, 'categoria': 'Moda'}),
    (17, 'O que aconteceria se eu aplicasse 17% de desconto no Email Marketing?',
     APLICAR_DESCONTO, 'simular_desconto_em_segmento', {'desconto_pct': 17.0, 'canal': 'Email Marketing'}),
    (18, 'Qual seria o impacto de limitar o desconto a 20% apenas no Marketplace?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 20.0, 'canal': 'Marketplace'}),
    (19, 'Qual seria o impacto de limitar o desconto a 20% apenas em Beleza?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 20.0, 'categoria': 'Beleza'}),
    (20, 'Quantos pedidos seriam afetados por um teto de 20%?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 20.0}),
    (21, 'Quanto de margem seria recuperado com um teto de 20%?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 20.0}),
    (22, 'Qual seria o impacto na margem do segmento de um desconto de 17% em Moda?',
     APLICAR_DESCONTO, 'simular_desconto_em_segmento', {'desconto_pct': 17.0, 'categoria': 'Moda'}),
    (23, 'Qual seria o impacto na margem consolidada de um teto de 20%?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 20.0}),
    (24, 'Qual é a diferença entre a situação atual e o cenário simulado de teto de 20%?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 20.0}),
    (25, 'Quais são as premissas da simulação de teto de 20%?',
     TETO_DESCONTO, 'simular_teto_desconto', {'teto_pct': 20.0}),
    (26, 'Um desconto de 22% está dentro da política?',
     POLITICA_ALCADA, 'consultar_politica_desconto', {'desconto_pct': 22.0}),
    (27, 'Quem precisa aprovar um desconto de 10%?',
     POLITICA_ALCADA, 'consultar_politica_desconto', {'desconto_pct': 10.0}),
    (28, 'Quem precisa aprovar um desconto de 17%?',
     POLITICA_ALCADA, 'consultar_politica_desconto', {'desconto_pct': 17.0}),
    (29, 'Quem precisa aprovar um desconto de 25%?',
     POLITICA_ALCADA, 'consultar_politica_desconto', {'desconto_pct': 25.0}),
    (30, 'Quem precisa aprovar um desconto de 30%?',
     POLITICA_ALCADA, 'consultar_politica_desconto', {'desconto_pct': 30.0}),
    (31, 'Quando é necessária aprovação do gerente?',
     POLITICA_ALCADA, 'consultar_politica_desconto', {}),
    (32, 'Quando é necessária aprovação do CMO e do CFO?',
     POLITICA_ALCADA, 'consultar_politica_desconto', {}),
    (33, 'Existe algum desconto acima do limite permitido?',
     VIOLACAO_POLITICA, 'pedidos_acima_do_teto', {}),
    (34, 'Como identificar possíveis exceções à política?',
     VIOLACAO_POLITICA, 'pedidos_acima_do_teto', {}),
    (35, 'Como identificar possível tentativa de contornar a política?',
     VIOLACAO_POLITICA, 'pedidos_acima_do_teto', {}),
    (36, 'Como tratar um pedido com margem negativa e desconto elevado?',
     MARGEM_NEGATIVA, 'pedidos_margem_negativa', {}),
    (37, 'Qual desconto exige justificativa de exceção?',
     POLITICA_ALCADA, 'consultar_politica_desconto', {}),
    (38, 'Quanto gastamos com frete?',
     FRETE_PANORAMA, 'politica_frete_por_canal', {}),
    (39, 'Qual é o frete médio por pedido?',
     FRETE_PANORAMA, 'politica_frete_por_canal', {}),
    (40, 'Como o custo de frete do Marketplace se compara aos demais canais?',
     FRETE_PANORAMA, 'politica_frete_por_canal', {}),
    (41, 'Quanto do frete do Marketplace é potencialmente evitável?',
     FRETE, 'custo_assimetria_frete', {'canal': 'Marketplace'}),
    (42, 'Quanto economizaríamos se o Marketplace tivesse a mesma regra dos outros canais?',
     FRETE_REGRA_LIMIAR, 'regra_frete_por_limiar', {'canal': 'Marketplace'}),
    (43, 'Qual é o impacto anual estimado dessa mudança de frete?',
     FRETE, 'custo_assimetria_frete', {}),
    (44, 'Por que o problema do Marketplace é principalmente contratual?',
     PERGUNTA_COMPLEXA, None, {}),
    (45, 'O que poderia ser feito caso não seja possível renegociar o contrato de frete?',
     PERGUNTA_COMPLEXA, None, {}),
    (46, 'Qual é o impacto de um reajuste de preço de 4,9% no Marketplace?',
     REAJUSTE_PRECO, 'simular_reajuste_preco', {'reajuste_pct': 4.9, 'canal': 'Marketplace'}),
    (47, 'Qual deveria ser a decisão sobre frete até o dia 60?',
     FRETE, 'custo_assimetria_frete', {}),
    (48, 'Qual é a taxa de devolução?',
     DEVOLUCOES, 'impacto_devolucoes', {'por': 'canal'}),
    (49, 'Quantos pedidos foram devolvidos?',
     DEVOLUCOES, 'impacto_devolucoes', {'por': 'canal'}),
    (50, 'Quais são os motivos de devolução registrados?',
     VALIDACAO_MOTIVOS, 'verificar_consistencia_categorica', {'tabela': 'vendas', 'coluna_a': 'motivo_devolucao', 'coluna_b': 'categoria'}),
    (51, 'Os motivos de devolução registrados são confiáveis?',
     VALIDACAO_MOTIVOS, 'verificar_consistencia_categorica', {'tabela': 'vendas', 'coluna_a': 'motivo_devolucao', 'coluna_b': 'categoria'}),
    (52, 'Existem inconsistências nos motivos de devolução?',
     VALIDACAO_MOTIVOS, 'verificar_consistencia_categorica', {'tabela': 'vendas', 'coluna_a': 'motivo_devolucao', 'coluna_b': 'categoria'}),
    (53, "Existem registros de 'Tamanho errado' em categorias que não possuem tamanho?",
     VALIDACAO_MOTIVOS, 'verificar_consistencia_categorica', {'tabela': 'vendas', 'coluna_a': 'motivo_devolucao', 'coluna_b': 'categoria'}),
    (54, "Existem registros de 'Atraso' em pedidos entregues dentro do prazo?",
     COERENCIA_PRAZO, 'coerencia_motivo_entrega', {}),
    (55, 'Quais informações estão faltando nos registros de devolução?',
     DEVOLUCOES, 'impacto_devolucoes', {'por': 'canal'}),
    (56, 'Por que não podemos afirmar quais são as verdadeiras causas das devoluções?',
     LIMITE_DE_DADOS, 'cobertura_de_dados', {'assunto': 'causa_de_devolucao'}),
    (57, 'Podemos calcular o custo real das devoluções com os dados atuais?',
     DEVOLUCOES, 'impacto_devolucoes', {'por': 'canal'}),
    (58, 'Qual é a faixa de impacto financeiro das devoluções suportada pelos dados?',
     DEVOLUCOES, 'impacto_devolucoes', {'por': 'canal'}),
    (59, 'Por que ainda não devemos estabelecer uma meta de redução de devoluções?',
     LIMITE_DE_DADOS, 'cobertura_de_dados', {'assunto': 'previsao_de_devolucao'}),
    (60, "Quantos motivos de 'Tamanho errado' são coerentes com a categoria?",
     VALIDACAO_MOTIVOS, 'verificar_consistencia_categorica', {'tabela': 'vendas', 'coluna_a': 'motivo_devolucao', 'coluna_b': 'categoria'}),
    (61, "Quantos registros de 'Atraso' são coerentes com o prazo de entrega?",
     COERENCIA_PRAZO, 'coerencia_motivo_entrega', {}),
    (62, "Quantos casos de 'Defeito' possuem evidência compatível?",
     LIMITE_DE_DADOS, 'cobertura_de_dados', {'assunto': 'causa_de_devolucao'}),
    (63, 'Quantos registros de devolução podem ser considerados confiáveis?',
     VALIDACAO_MOTIVOS, 'verificar_consistencia_categorica', {'tabela': 'vendas', 'coluna_a': 'motivo_devolucao', 'coluna_b': 'categoria'}),
    (64, 'Quantos registros de devolução precisam ser revisados?',
     VALIDACAO_MOTIVOS, 'verificar_consistencia_categorica', {'tabela': 'vendas', 'coluna_a': 'motivo_devolucao', 'coluna_b': 'categoria'}),
    (65, 'Qual percentual dos motivos de devolução pode ser validado?',
     VALIDACAO_MOTIVOS, 'verificar_consistencia_categorica', {'tabela': 'vendas', 'coluna_a': 'motivo_devolucao', 'coluna_b': 'categoria'}),
    (66, 'Quais campos estão faltando para melhorar a qualidade da informação de devolução?',
     DEVOLUCOES, 'impacto_devolucoes', {'por': 'canal'}),
    (67, 'Existe sazonalidade nas vendas?',
     SAZONALIDADE, 'indice_sazonalidade', {}),
    (68, 'Quais meses apresentam melhor desempenho?',
     SAZONALIDADE, 'indice_sazonalidade', {}),
    (69, 'Quais meses apresentam pior desempenho?',
     SAZONALIDADE, 'indice_sazonalidade', {}),
    (70, 'Como comparar o segundo semestre de 2023 com o primeiro?',
     COMPARACAO_PERIODOS, 'comparar_periodos', {'periodo_a': '2023-01:2023-06', 'periodo_b': '2023-07:2023-12'}),
    (71, 'Houve mudança significativa entre os períodos?',
     COMPARACAO_PERIODOS, 'comparar_periodos', {}),
    (72, 'Existe diferença estatisticamente significativa de margem entre os canais?',
     TESTE_ESTATISTICO, 'anova_um_fator', {'metrica': 'margem_contribuicao', 'coluna_grupo': 'canal'}),
    (73, 'Qual é o principal problema identificado nos dados?',
     PERGUNTA_COMPLEXA, None, {}),
    (74, 'Qual é o maior vazamento financeiro?',
     PERGUNTA_COMPLEXA, None, {}),
    (75, 'Qual é a maior oportunidade de recuperação?',
     PERGUNTA_COMPLEXA, None, {}),
    (76, 'Qual frente deveria ser priorizada?',
     PERGUNTA_COMPLEXA, None, {}),
    (77, 'Quanto pode ser recuperado em cada frente?',
     PERGUNTA_COMPLEXA, None, {}),
    (78, 'Qual deveria ser a prioridade número 1?',
     PERGUNTA_COMPLEXA, None, {}),
    (79, 'Quais são as principais recomendações para o comitê?',
     PERGUNTA_COMPLEXA, None, {}),
    (80, 'Quais são os principais riscos?',
     PERGUNTA_COMPLEXA, None, {}),
    (81, 'O que deve ser feito nos próximos 30 dias?',
     PERGUNTA_COMPLEXA, None, {}),
    (82, 'O que deve ser feito entre 31 e 60 dias?',
     PERGUNTA_COMPLEXA, None, {}),
    (83, 'O que deve ser feito entre 61 e 90 dias?',
     PERGUNTA_COMPLEXA, None, {}),
    (84, 'Qual decisão precisa ser tomada pelo comitê?',
     PERGUNTA_COMPLEXA, None, {}),
    (85, 'Quais conclusões são fatos e quais são cenários?',
     PERGUNTA_COMPLEXA, None, {}),
    (86, 'Qual é a força da evidência de cada conclusão?',
     PERGUNTA_COMPLEXA, None, {}),
    (87, 'Qual é o CAC?',
     LIMITE_DE_DADOS, 'cobertura_de_dados', {'assunto': 'cac'}),
    (88, 'Qual é o ROAS real por canal?',
     MARKETING, 'ranking_roas_canais', {}),
    (89, 'Qual é o LTV dos clientes?',
     LIMITE_DE_DADOS, 'cobertura_de_dados', {'assunto': 'ltv'}),
    (90, 'Qual é o churn?',
     LIMITE_DE_DADOS, 'cobertura_de_dados', {'assunto': 'churn'}),
    (91, 'Quais são os melhores segmentos de clientes?',
     LIMITE_DE_DADOS, 'cobertura_de_dados', {'assunto': 'segmentos_de_clientes'}),
    (92, 'Quais clientes deveriam receber uma oferta individual?',
     LIMITE_DE_DADOS, 'cobertura_de_dados', {'assunto': 'oferta_individual'}),
    (93, 'Podemos automatizar a classificação dos tickets?',
     LIMITE_DE_DADOS, 'cobertura_de_dados', {'assunto': 'classificacao_de_tickets'}),
    (94, 'Quais são as verdadeiras causas das devoluções?',
     LIMITE_DE_DADOS, 'cobertura_de_dados', {'assunto': 'causa_de_devolucao'}),
    (95, 'Qual será exatamente a redução das devoluções depois da intervenção?',
     LIMITE_DE_DADOS, 'cobertura_de_dados', {'assunto': 'previsao_de_devolucao'}),
]

ROTEADAS = [c for c in CASOS if c[3] is not None]
COMPLEXAS = [c for c in CASOS if c[2] == PERGUNTA_COMPLEXA]
SEM_DADO = [c for c in CASOS if c[2] == LIMITE_DE_DADOS]


def _id(caso):
    return f"Q{caso[0]}"


# ------------------------------------------------ 1) intenção e ferramenta
@pytest.mark.parametrize("caso", CASOS, ids=_id)
def test_intencao_e_ferramenta_esperadas(caso):
    numero, pergunta, intencao, ferramenta, _ = caso
    r = rotear(pergunta)
    assert r.intencao == intencao, (
        f"Q{numero} mudou de intenção: {r.intencao} (esperado {intencao}) — {r.motivo}")
    assert r.ferramenta == ferramenta, f"Q{numero} foi para {r.ferramenta}"


@pytest.mark.parametrize("caso", ROTEADAS, ids=_id)
def test_parametros_extraidos_da_pergunta(caso):
    numero, pergunta, _, ferramenta, parametros = caso
    r = rotear(pergunta)
    assert r.parametros == parametros, f"Q{numero}: {r.parametros}"
    validados, problemas = validar_parametros(ferramenta, r.parametros)
    assert not problemas or r.faltando, f"Q{numero} tem parâmetro inválido: {problemas}"


# ------------------------------------------------ 2) a ferramenta executa
@pytest.mark.parametrize("caso", ROTEADAS, ids=_id)
def test_ferramenta_executa_e_devolve_resultado_utilizavel(caso):
    numero, pergunta, _, ferramenta, _ = caso
    r = rotear(pergunta)
    if not r.determinado:          # falta parâmetro: o agente pergunta, não chuta
        assert r.faltando, f"Q{numero} indeterminada sem dizer o que falta"
        return
    validados, problemas = validar_parametros(ferramenta, r.parametros)
    assert not problemas, f"Q{numero}: {problemas}"
    resultado = executar(ferramenta, validados)
    assert isinstance(resultado, dict) and resultado, f"Q{numero} devolveu vazio"
    if caso[2] != LIMITE_DE_DADOS:
        # Recusa medida pode não ter número nenhum — "não há intervenção anterior
        # para medir" é exatamente a ausência de dado, e é o teste 4 que a cobra.
        assert coletar_numeros(resultado), f"Q{numero} não devolveu número nenhum"


# ------------------------------------------------ 3) o que é do ReAct
@pytest.mark.parametrize("caso", COMPLEXAS, ids=_id)
def test_pergunta_aberta_nao_e_forcada_em_ferramenta_unica(caso):
    """Bloco executivo: reduzir "qual a prioridade nº 1?" a uma consulta só seria
    pior que investigar — o roteador se declara incompetente e o ReAct assume."""
    numero, pergunta, _, _, _ = caso
    r = rotear(pergunta)
    assert r.ferramenta is None
    assert r.origem == "llm_react", f"Q{numero} não foi entregue ao ReAct"


# ------------------------------------------------ 4) o que não tem resposta
@pytest.mark.parametrize("caso", SEM_DADO, ids=_id)
def test_pergunta_sem_lastro_sai_como_limitacao_medida(caso):
    """Nenhuma destas pode virar número. Todas têm de virar lacuna nomeada, com
    a medida que sustenta a recusa e o que seria preciso coletar."""
    numero, pergunta, _, _, parametros = caso
    r = rotear(pergunta)
    resultado = executar("cobertura_de_dados", r.parametros)
    assert resultado["veredito"] in ("nao_respondivel", "parcial_com_ressalva"), (
        f"Q{numero} foi dada como respondível")
    assert resultado["por_que"], f"Q{numero} recusou sem dizer por quê"
    assert resultado["campos_ausentes"], f"Q{numero} não nomeou o que falta"
    assert resultado["o_que_seria_preciso"], f"Q{numero} não disse como destravar"


# ------------------------------------------------ 5) teto ≠ aplicar
# O enunciado exige a distinção verbo a verbo: limitar/capar/travar impõem um
# TETO (só os pedidos acima dele mudam); aplicar/dar/oferecer definem o desconto
# do segmento INTEIRO. A conta é diferente, não só a ferramenta.
@pytest.mark.parametrize("verbo", [
    "limitasse o desconto de Moda a 17%",
    "limitar o desconto de Moda a 17%",
    "impusesse um teto de 17% em Moda",
    "colocasse o desconto máximo de Moda em 17%",
    "não deixasse o desconto de Moda passar de 17%",
    "não permitisse desconto acima de 17% em Moda",
    "capasse o desconto de Moda em 17%",
    "restringisse o desconto de Moda a 17%",
    "travasse o desconto de Moda em 17%",
])
def test_verbo_de_limite_vira_teto(verbo):
    r = rotear(f"O que aconteceria se eu {verbo}?")
    assert r.intencao == TETO_DESCONTO, r.motivo
    assert r.ferramenta == "simular_teto_desconto"
    assert r.parametros["teto_pct"] == 17.0
    assert r.parametros["categoria"] == "Moda"


@pytest.mark.parametrize("verbo", [
    "aplicasse um desconto de 17% em Moda",
    "aplicar 17% de desconto em Moda",
    "desse 17% de desconto em Moda",
    "oferecesse 17% de desconto em Moda",
    "concedesse 17% de desconto em Moda",
    "passasse a dar 17% de desconto em Moda",
    "praticasse 17% de desconto em Moda",
    "fizesse uma campanha de 17% em Moda",
])
def test_verbo_de_aplicacao_vira_desconto_no_segmento(verbo):
    r = rotear(f"O que aconteceria se eu {verbo}?")
    assert r.intencao == APLICAR_DESCONTO, r.motivo
    assert r.ferramenta == "simular_desconto_em_segmento"
    assert r.parametros["desconto_pct"] == 17.0
    assert r.parametros["categoria"] == "Moda"


def test_teto_e_aplicacao_dao_numeros_diferentes():
    """Se as duas ferramentas devolvessem o mesmo, a distinção seria decorativa."""
    teto = executar("simular_teto_desconto", {"teto_pct": 17, "categoria": "Moda"})
    aplic = executar("simular_desconto_em_segmento", {"desconto_pct": 17, "categoria": "Moda"})
    assert teto["margem_recuperada_reais"] > 0          # teto RECUPERA margem
    assert aplic["efeito_no_segmento"]["variacao_pp"] < 0   # aplicar 17% em todos DERRUBA


# ------------------------------------------------ 6) o caso obrigatório
def test_regressao_obrigatoria_moda_no_email_marketing():
    """O caso que não era respondido: canal composto cujo nome contém
    'Marketing', categoria junto, teto com percentual. Roteava para ROAS."""
    r = rotear("O que aconteceria se eu limitasse o desconto de Moda "
               "no Email Marketing a 17%?")
    assert r.intencao == TETO_DESCONTO
    assert r.ferramenta == "simular_teto_desconto"
    assert r.parametros == {"teto_pct": 17.0, "canal": "Email Marketing",
                            "categoria": "Moda"}
    assert r.determinado

    resultado = executar("simular_teto_desconto", r.parametros)
    assert resultado["recorte"] == {"canal": "Email Marketing", "categoria": "Moda"}
    assert 0 < resultado["pedidos_afetados"] < resultado["pedidos_no_recorte"]
    assert resultado["margem_recuperada_reais"] > 0


@pytest.mark.parametrize("pergunta", [
    "O que aconteceria se eu limitasse o desconto de Moda no Email Marketing a 17%?",
    "Qual o impacto de um teto de 20% no Email Marketing?",
    "E se eu desse 30% de desconto no Email Marketing?",
])
def test_email_marketing_nunca_vira_pergunta_de_roas(pergunta):
    """'Marketing' no nome do canal não pode arrastar a pergunta para o ranking
    de mídia — foi essa pista de palavra-chave que quebrou o caso original."""
    r = rotear(pergunta)
    assert r.ferramenta != "ranking_roas_canais"
    assert r.intencao != MARKETING
    assert r.parametros.get("canal") == "Email Marketing"


# ------------------------------------------------ 7) política e alçadas
@pytest.mark.parametrize("pct,aprovador", [
    (5, "Analista"), (10, "Analista"), (10.5, "Gerente"), (17, "Gerente"),
    (20, "Gerente"), (22, "Diretor"), (25, "Diretor"), (30, "CMO"), (40, "CMO"),
])
def test_alcada_por_faixa_de_desconto(pct, aprovador):
    r = executar("consultar_politica_desconto", {"desconto_pct": pct})
    assert aprovador in r["alcada_requerida"]
    assert r["desconto_consultado_pct"] == float(pct)


def test_alcada_declara_que_e_governanca_e_nao_apuracao():
    """A régua não sai dos dados. Se o resultado não disser isso, a resposta
    final apresenta política como se fosse achado — o erro mais caro do bloco."""
    r = executar("consultar_politica_desconto", {"desconto_pct": 17})
    assert "NÃO apurado dos dados" in r["origem_das_alcadas"]
    assert r["origem_do_teto"]


def test_excecao_acima_do_limiar_exige_justificativa():
    assert executar("consultar_politica_desconto",
                    {"desconto_pct": 30})["exige_justificativa_de_excecao"]
    assert not executar("consultar_politica_desconto",
                        {"desconto_pct": 15})["exige_justificativa_de_excecao"]


def test_politica_registrada_vence_o_padrao_do_projeto(tmp_path, monkeypatch):
    """Registrada uma política, o teto passa a vir dela — com dono e vigência."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    from vertice.politica import definir_politica

    definir_politica(canal=None, categoria=None, teto_pct=18, responsavel="Comitê")
    r = executar("consultar_politica_desconto", {"desconto_pct": 20})
    assert r["teto_vigente_pct"] == 18.0
    assert r["dentro_do_teto_vigente"] is False
    assert "Comitê" in r["origem_do_teto"]


def test_violacao_do_teto_conta_pedidos_e_marca_a_origem_da_regua():
    r = executar("pedidos_acima_do_teto", {"teto_pct": 25})
    assert r["pedidos_acima_do_teto"] > 0
    assert r["desconto_excedente_ao_teto"] > 0
    # O mesmo recorte apurado por outra ferramenta: se divergir, uma das duas
    # está errada — e o case inteiro depende deste número.
    cen = executar("cenarios_reducao_desconto")
    assert r["pedidos_acima_do_teto"] == cen["grupo_alvo"]["pedidos"]
    assert r["desconto_excedente_ao_teto"] == cen["excedente_sobre_limiar_reais"]


def test_sinal_de_contorno_e_indicio_declarado_nao_acusacao():
    r = executar("pedidos_acima_do_teto", {"teto_pct": 25})
    assert r["sinal_de_contorno"]["pedidos_na_faixa_3pp_abaixo_do_teto"] >= 0
    assert "não é prova" in r["sinal_de_contorno"]["leitura"]
    assert "não registra aprovador" in r["limitacao"]


# ------------------------------------------------ 8) ponta a ponta, com trace
# Aqui o LLM é um dublê: ele não decide nada, só devolve o texto final. É
# exatamente esse o papel dele na arquitetura — a ferramenta já rodou antes do
# primeiro turno, pelo roteador.
from vertice.agent.react import AgenteMargem, validar_formato_final  # noqa: E402

RESPOSTA_GENERICA = ("FATO: resultado apurado pela ferramenta.\n"
                     "INFERÊNCIA: o recorte concentra desconto acima da média.\n"
                     "RECOMENDAÇÃO: revisar a política do recorte.\n"
                     "FORÇA DA EVIDÊNCIA: MODERADA (n>1000).")


@pytest.mark.parametrize("pergunta,ferramenta", [
    ("O que aconteceria se eu limitasse o desconto de Moda no Email Marketing a 17%?",
     "simular_teto_desconto"),
    ("Quem precisa aprovar um desconto de 17%?", "consultar_politica_desconto"),
    ("Quantos pedidos estão acima do teto de desconto?", "pedidos_acima_do_teto"),
    ("Quanto gastamos com frete?", "politica_frete_por_canal"),
    ("Os motivos de devolução registrados são confiáveis?",
     "verificar_consistencia_categorica"),
    ("Qual é o LTV dos clientes?", "cobertura_de_dados"),
])
def test_agente_executa_a_ferramenta_antes_do_modelo_falar(pergunta, ferramenta):
    """Contrato central: quando a rota é determinística, a ferramenta roda ANTES
    do primeiro turno e o resultado entra na conversa como observação. O modelo
    recebe número apurado, não a tarefa de calcular."""
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_GENERICA], verbose=False)
    tr = ag.investigar(pergunta)
    assert ferramenta in tr.ferramentas_usadas, f"{pergunta} não executou {ferramenta}"
    assert tr.roteamento and tr.roteamento["ferramenta"] == ferramenta
    assert tr.roteamento["origem"] == "roteador_deterministico"
    assert validar_formato_final(tr.resposta_final)["valido"]


def test_trace_registra_a_decisao_de_roteamento_para_auditoria():
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_GENERICA], verbose=False)
    tr = ag.investigar("O que aconteceria se eu limitasse o desconto de Moda "
                       "no Email Marketing a 17%?")
    passo = next(p for p in tr.passos if p.tipo == "roteamento")
    assert passo.conteudo["intencao"] == TETO_DESCONTO
    assert passo.conteudo["parametros"]["canal"] == "Email Marketing"
    assert passo.conteudo["motivo"], "roteamento sem justificativa não é auditável"
    # O estado da execução é gravado no registro depois que a ferramenta roda —
    # o passo é escrito antes, quando ainda não se sabe se vai dar certo.
    assert tr.roteamento["status_ferramenta"] == "TOOL_CALLED_SUCCESS"
    acao = next(p for p in tr.passos if p.tipo == "acao"
                and p.ferramenta == "simular_teto_desconto")
    assert acao.origem == "roteador_deterministico"


# ------------------------------------------------ 9) o número tem de ser o da ferramenta
def test_resposta_com_os_numeros_da_ferramenta_passa_na_verificacao():
    """A resposta correta para o caso obrigatório, montada só com o que
    simular_teto_desconto devolveu."""
    r = executar("simular_teto_desconto",
                 {"teto_pct": 17, "canal": "Email Marketing", "categoria": "Moda"})
    numeros = coletar_numeros(r)
    resposta = (
        f"FATO: dos {r['pedidos_no_recorte']} pedidos de Moda no Email Marketing, "
        f"{r['pedidos_afetados']} estão acima de 17% de desconto; o teto recuperaria "
        f"R$ {r['margem_recuperada_reais']:.2f}.\n"
        "INFERÊNCIA: o excedente está concentrado em poucos pedidos.\n"
        "RECOMENDAÇÃO: aplicar o teto no recorte.\n"
        "FORÇA DA EVIDÊNCIA: MODERADA (n>1000).")
    assert verificar_numeros(resposta, numeros, "")["ok"]


def test_resposta_com_numero_plausivel_porem_inventado_e_reprovada():
    """O modo de falha que o case pune: o número certo de casas decimais, a
    ordem de grandeza certa, e origem nenhuma."""
    r = executar("simular_teto_desconto",
                 {"teto_pct": 17, "canal": "Email Marketing", "categoria": "Moda"})
    ruim = ("FATO: o teto de 17% recuperaria R$ 48.221,90 em margem, "
            "elevando a margem do recorte para 53,88%.\n"
            "INFERÊNCIA: ganho relevante.\nRECOMENDAÇÃO: aplicar.\n"
            "FORÇA DA EVIDÊNCIA: FORTE (p<0,001).")
    assert not verificar_numeros(ruim, coletar_numeros(r), "")["ok"]


@pytest.mark.parametrize("caso", [c for c in ROTEADAS if c[2] != LIMITE_DE_DADOS], ids=_id)
def test_numeros_da_ferramenta_sao_rastreaveis_na_resposta(caso):
    """Para cada pergunta roteada: os números que a ferramenta devolve são
    aceitos pela verificação. Se não fossem, toda resposta correta seria
    bloqueada — foi o que aconteceu quando o separador de milhar era espaço."""
    numero, pergunta, _, ferramenta, _ = caso
    r = rotear(pergunta)
    if not r.determinado:
        pytest.skip("pergunta depende de parâmetro que ela não traz")
    resultado = executar(ferramenta, validar_parametros(ferramenta, r.parametros)[0])
    numeros = coletar_numeros(resultado)
    amostra = sorted(v for v in numeros if abs(v) >= 1000)[:3]
    if not amostra:
        pytest.skip("resultado sem número grande o bastante para ser verificado")
    texto = "FATO: " + "; ".join(f"{v:,.2f}".replace(",", "X").replace(".", ",")
                                 .replace("X", ".") for v in amostra) + "."
    r_ver = verificar_numeros(texto, numeros, "")
    assert r_ver["ok"], f"Q{numero}: {r_ver['suspeitos']} vieram da própria ferramenta"


# ------------------------------------------------ 10) motivo declarado ≠ causa
def test_motivo_de_devolucao_nao_pode_ser_apresentado_como_causa():
    """Exigência explícita do enunciado. A ferramenta de cobertura é quem
    sustenta a recusa, e ela sustenta com contagem: há 'Tamanho errado' em
    categorias onde tamanho não é atributo."""
    r = executar("cobertura_de_dados", {"assunto": "causa_de_devolucao"})
    assert r["veredito"] == "nao_respondivel"
    assert r["medida"]["total_desses_registros"] > 0, (
        "sem a contagem, a recusa vira opinião")
    assert "motivo DECLARADO" in r["por_que"]


def test_inconsistencia_de_motivo_por_categoria_e_contada_e_nao_estimada():
    r = executar("verificar_consistencia_categorica",
                 {"tabela": "vendas", "coluna_a": "motivo_devolucao",
                  "coluna_b": "categoria"})
    celulas = {(c["motivo_devolucao"], c["categoria"]): c["registros"] for c in r["celulas"]}
    assert celulas.get(("Tamanho errado", "Beleza"), 0) > 0, (
        "o achado que sustenta a desconfiança do motivo sumiu da tabela")
    assert r["registros_considerados"] > 0


def test_motivo_atraso_e_confrontado_com_o_tempo_de_entrega_registrado():
    """"Atraso na entrega" é verificável contra tempo_entrega_real — e não se
    sustenta: metade dos casos foi entregue dentro da régua da própria base."""
    r = executar("coerencia_motivo_entrega", {})
    assert r["pedidos_com_motivo_atraso"] > 0
    assert r["motivo_atraso_entregue_dentro_da_regua"] > 0
    assert r["status"] == "revisar"
    assert "NÃO tem coluna de SLA" in r["origem_da_regua"], (
        "sem declarar que a régua é interna, o número vira SLA inventado")


def test_prazo_de_devolucao_continua_declarado_como_lacuna():
    """A data de solicitação não existe em base nenhuma: a ferramenta diz isso
    em vez de aproximar pela data do pedido."""
    r = executar("checar_devolucao_fora_prazo", {})
    assert r["disponivel"] is False
    assert "não está registrada" in r["lacuna"]


# ------------------------------------------------ 11) descritivo ≠ significativo
def test_comparacao_de_periodos_e_descritiva_e_nao_afirma_significancia():
    r = executar("comparar_periodos", {"periodo_a": "2023-01:2023-06",
                                       "periodo_b": "2023-07:2023-12"})
    assert "p_valor" not in r and "forca" not in r, (
        "comparar_periodos é decomposição contábil; anunciar força aqui seria "
        "transformar diferença descritiva em significância")
    assert r["variacao_pp"]["margem_pct"] != 0


def test_sazonalidade_e_descritiva_e_o_teste_de_tendencia_e_que_conclui():
    """Regressão de um erro real: 'FORTE' numa conclusão de mudança estrutural
    apoiada só no índice de sazonalidade. O teste que de fato responde dá p alto."""
    from vertice.agent.react import FERRAMENTAS_ESTATISTICAS

    assert "indice_sazonalidade" not in FERRAMENTAS_ESTATISTICAS
    assert "tendencia_ajustada_sazonalidade" in FERRAMENTAS_ESTATISTICAS
    tendencia = executar("tendencia_ajustada_sazonalidade", {"metrica": "margem_pct"})
    assert "p_valor" in tendencia and "forca" in tendencia


def test_teste_estatistico_traz_criterio_de_forca_junto_do_p():
    r = executar("anova_um_fator", {"metrica": "margem_contribuicao",
                                    "coluna_grupo": "canal"})
    assert r["forca"] in ("FORTE", "MODERADA", "FRACA")
    assert r["criterio"] and r["p_valor"] is not None
    assert r["r2"] is None, (
        "a ANOVA não devolve R² — se passar a devolver, a resposta que cita "
        "'R² = 0,85' deixa de ser detectável como invenção")


# ------------------------------------------------ 12) devolução por mês
def test_devolucao_abre_por_mes_com_a_contagem_e_nao_so_a_taxa():
    """"Quantos pedidos foram devolvidos em maio?" não tinha resposta: a
    ferramenta abria só por canal, categoria e motivo. A recusa era honesta, mas
    a lacuna era do motor — a coluna existe e a abertura é a mesma."""
    r = executar("impacto_devolucoes", {"por": "mes"})
    maio = next(l for l in r["linhas"] if l["mes"] == "2023-05")
    assert maio["pedidos_devolvidos"] > 0
    # A contagem tem de vir da ferramenta: taxa × pedidos seria conta do modelo.
    assert sum(l["pedidos_devolvidos"] for l in r["linhas"]) == 3639
