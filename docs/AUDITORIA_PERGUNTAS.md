# Auditoria das 95 perguntas do case

Gerado por `python -m scripts.auditoria_perguntas` — cada linha é uma execução real do roteador e do motor, não uma expectativa escrita à mão.

Legenda: **PASS** intenção, ferramenta, parâmetros e execução corretos · **PASS com ressalva** idem, e a ferramenta já devolve a premissa/limitação que a resposta precisa repetir · **RECUSA MEDIDA** a pergunta não tem lastro e a recusa vem com a medida que a sustenta · **ReAct** investigação aberta, sem ferramenta única por decisão · **PEDE PARÂMETRO** falta um valor que a pergunta não traz — o agente pergunta em vez de inventar.


## Desconto e margem — diagnóstico (perguntas 1–10)

| # | Pergunta | Intenção | Ferramenta | Parâmetros | Veredito | Observação |
|---|---|---|---|---|---|---|
| 1 | Qual é o desconto médio atual? | MARGEM_CONSOLIDADA | margem_consolidada | — | PASS |  |
| 2 | Como o desconto evoluiu ao longo do semestre? | MARGEM_POR_DIMENSAO | margem_por_dimensao | dimensao=mes | PASS |  |
| 3 | Qual é o impacto dos descontos sobre a margem? | RELACAO_DESCONTO_MARGEM | tabela_faixas_desconto | — | PASS com ressalva | a ferramenta devolve ressalva_causal, leitura |
| 4 | Em quais canais o desconto é mais elevado? | MARGEM_POR_DIMENSAO | margem_por_dimensao | dimensao=canal | PASS |  |
| 5 | Em quais categorias o desconto é mais elevado? | MARGEM_POR_DIMENSAO | margem_por_dimensao | dimensao=categoria | PASS |  |
| 6 | Quais produtos concentram os maiores descontos? | MARGEM_POR_DIMENSAO | margem_por_dimensao | dimensao=sku | PASS |  |
| 7 | Quantos pedidos estão acima do teto de desconto? | VIOLACAO_POLITICA | pedidos_acima_do_teto | — | PASS com ressalva | a ferramenta devolve limitacao, origem_do_teto |
| 8 | Qual é o custo de não agir sobre esses descontos? | CUSTO_DE_NAO_AGIR | cenarios_reducao_desconto | — | PASS com ressalva | a ferramenta devolve premissa |
| 9 | Qual canal apresenta maior perda de margem associada a descontos? | MARGEM_POR_DIMENSAO | margem_por_dimensao | dimensao=canal | PASS |  |
| 10 | Qual categoria apresenta maior impacto dos descontos na margem? | MARGEM_POR_DIMENSAO | margem_por_dimensao | dimensao=categoria | PASS |  |

## Desconto e margem — simulações (perguntas 11–25)

| # | Pergunta | Intenção | Ferramenta | Parâmetros | Veredito | Observação |
|---|---|---|---|---|---|---|
| 11 | O que aconteceria se eu limitasse o desconto a 25%? | TETO_DESCONTO | simular_teto_desconto | teto_pct=25.0 | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |
| 12 | O que aconteceria se eu limitasse o desconto a 20%? | TETO_DESCONTO | simular_teto_desconto | teto_pct=20.0 | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |
| 13 | O que aconteceria se eu limitasse o desconto a 17%? | TETO_DESCONTO | simular_teto_desconto | teto_pct=17.0 | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |
| 14 | O que aconteceria se eu limitasse o desconto de Moda a 17%? | TETO_DESCONTO | simular_teto_desconto | teto_pct=17.0, categoria=Moda | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |
| 15 | O que aconteceria se eu limitasse o desconto de Moda no Email Marketing a 17%? | TETO_DESCONTO | simular_teto_desconto | teto_pct=17.0, canal=Email Marketing, categoria=Moda | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |
| 16 | O que aconteceria se eu aplicasse um desconto de 17% em Moda? | APLICAR_DESCONTO | simular_desconto_em_segmento | desconto_pct=17.0, categoria=Moda | PASS com ressalva | a ferramenta devolve premissa, periodo_coberto |
| 17 | O que aconteceria se eu aplicasse 17% de desconto no Email Marketing? | APLICAR_DESCONTO | simular_desconto_em_segmento | desconto_pct=17.0, canal=Email Marketing | PASS com ressalva | a ferramenta devolve premissa, periodo_coberto |
| 18 | Qual seria o impacto de limitar o desconto a 20% apenas no Marketplace? | TETO_DESCONTO | simular_teto_desconto | teto_pct=20.0, canal=Marketplace | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |
| 19 | Qual seria o impacto de limitar o desconto a 20% apenas em Beleza? | TETO_DESCONTO | simular_teto_desconto | teto_pct=20.0, categoria=Beleza | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |
| 20 | Quantos pedidos seriam afetados por um teto de 20%? | TETO_DESCONTO | simular_teto_desconto | teto_pct=20.0 | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |
| 21 | Quanto de margem seria recuperado com um teto de 20%? | TETO_DESCONTO | simular_teto_desconto | teto_pct=20.0 | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |
| 22 | Qual seria o impacto na margem do segmento de um desconto de 17% em Moda? | APLICAR_DESCONTO | simular_desconto_em_segmento | desconto_pct=17.0, categoria=Moda | PASS com ressalva | a ferramenta devolve premissa, periodo_coberto |
| 23 | Qual seria o impacto na margem consolidada de um teto de 20%? | TETO_DESCONTO | simular_teto_desconto | teto_pct=20.0 | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |
| 24 | Qual é a diferença entre a situação atual e o cenário simulado de teto de 20%? | TETO_DESCONTO | simular_teto_desconto | teto_pct=20.0 | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |
| 25 | Quais são as premissas da simulação de teto de 20%? | TETO_DESCONTO | simular_teto_desconto | teto_pct=20.0 | PASS com ressalva | a ferramenta devolve premissa, origem_do_teto, periodo_coberto |

## Política de descontos e alçadas (perguntas 26–37)

| # | Pergunta | Intenção | Ferramenta | Parâmetros | Veredito | Observação |
|---|---|---|---|---|---|---|
| 26 | Um desconto de 22% está dentro da política? | POLITICA_ALCADA | consultar_politica_desconto | desconto_pct=22.0 | PASS com ressalva | a ferramenta devolve origem_do_teto, origem_das_alcadas |
| 27 | Quem precisa aprovar um desconto de 10%? | POLITICA_ALCADA | consultar_politica_desconto | desconto_pct=10.0 | PASS com ressalva | a ferramenta devolve origem_do_teto, origem_das_alcadas |
| 28 | Quem precisa aprovar um desconto de 17%? | POLITICA_ALCADA | consultar_politica_desconto | desconto_pct=17.0 | PASS com ressalva | a ferramenta devolve origem_do_teto, origem_das_alcadas |
| 29 | Quem precisa aprovar um desconto de 25%? | POLITICA_ALCADA | consultar_politica_desconto | desconto_pct=25.0 | PASS com ressalva | a ferramenta devolve origem_do_teto, origem_das_alcadas |
| 30 | Quem precisa aprovar um desconto de 30%? | POLITICA_ALCADA | consultar_politica_desconto | desconto_pct=30.0 | PASS com ressalva | a ferramenta devolve origem_do_teto, origem_das_alcadas |
| 31 | Quando é necessária aprovação do gerente? | POLITICA_ALCADA | consultar_politica_desconto | — | PASS com ressalva | a ferramenta devolve nota, origem_do_teto, origem_das_alcadas |
| 32 | Quando é necessária aprovação do CMO e do CFO? | POLITICA_ALCADA | consultar_politica_desconto | — | PASS com ressalva | a ferramenta devolve nota, origem_do_teto, origem_das_alcadas |
| 33 | Existe algum desconto acima do limite permitido? | VIOLACAO_POLITICA | pedidos_acima_do_teto | — | PASS com ressalva | a ferramenta devolve limitacao, origem_do_teto |
| 34 | Como identificar possíveis exceções à política? | VIOLACAO_POLITICA | pedidos_acima_do_teto | — | PASS com ressalva | a ferramenta devolve limitacao, origem_do_teto |
| 35 | Como identificar possível tentativa de contornar a política? | VIOLACAO_POLITICA | pedidos_acima_do_teto | — | PASS com ressalva | a ferramenta devolve limitacao, origem_do_teto |
| 36 | Como tratar um pedido com margem negativa e desconto elevado? | MARGEM_NEGATIVA | pedidos_margem_negativa | — | PASS com ressalva | a ferramenta devolve leitura |
| 37 | Qual desconto exige justificativa de exceção? | POLITICA_ALCADA | consultar_politica_desconto | — | PASS com ressalva | a ferramenta devolve nota, origem_do_teto, origem_das_alcadas |

## Frete — Marketplace (perguntas 38–47)

| # | Pergunta | Intenção | Ferramenta | Parâmetros | Veredito | Observação |
|---|---|---|---|---|---|---|
| 38 | Quanto gastamos com frete? | FRETE_PANORAMA | politica_frete_por_canal | — | PASS com ressalva | a ferramenta devolve leitura |
| 39 | Qual é o frete médio por pedido? | FRETE_PANORAMA | politica_frete_por_canal | — | PASS com ressalva | a ferramenta devolve leitura |
| 40 | Como o custo de frete do Marketplace se compara aos demais canais? | FRETE_PANORAMA | politica_frete_por_canal | — | PASS com ressalva | a ferramenta devolve leitura |
| 41 | Quanto do frete do Marketplace é potencialmente evitável? | FRETE | custo_assimetria_frete | canal=Marketplace | PASS com ressalva | a ferramenta devolve premissa, periodo_coberto |
| 42 | Quanto economizaríamos se o Marketplace tivesse a mesma regra dos outros canais? | FRETE_REGRA_LIMIAR | regra_frete_por_limiar | canal=Marketplace | PASS com ressalva | a ferramenta devolve premissa |
| 43 | Qual é o impacto anual estimado dessa mudança de frete? | FRETE | custo_assimetria_frete | — | PASS com ressalva | a ferramenta devolve premissa, periodo_coberto |
| 44 | Por que o problema do Marketplace é principalmente contratual? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 45 | O que poderia ser feito caso não seja possível renegociar o contrato de frete? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 46 | Qual é o impacto de um reajuste de preço de 4,9% no Marketplace? | REAJUSTE_PRECO | simular_reajuste_preco | reajuste_pct=4.9, canal=Marketplace | PASS com ressalva | a ferramenta devolve premissa, periodo_coberto |
| 47 | Qual deveria ser a decisão sobre frete até o dia 60? | FRETE | custo_assimetria_frete | — | PASS com ressalva | a ferramenta devolve premissa, periodo_coberto |

## Devoluções (perguntas 48–66)

| # | Pergunta | Intenção | Ferramenta | Parâmetros | Veredito | Observação |
|---|---|---|---|---|---|---|
| 48 | Qual é a taxa de devolução? | DEVOLUCOES | impacto_devolucoes | por=canal | PASS com ressalva | a ferramenta devolve nota |
| 49 | Quantos pedidos foram devolvidos? | DEVOLUCOES | impacto_devolucoes | por=canal | PASS com ressalva | a ferramenta devolve nota |
| 50 | Quais são os motivos de devolução registrados? | VALIDACAO_MOTIVOS | verificar_consistencia_categorica | tabela=vendas, coluna_a=motivo_devolucao, coluna_b=categoria | PASS |  |
| 51 | Os motivos de devolução registrados são confiáveis? | VALIDACAO_MOTIVOS | verificar_consistencia_categorica | tabela=vendas, coluna_a=motivo_devolucao, coluna_b=categoria | PASS |  |
| 52 | Existem inconsistências nos motivos de devolução? | VALIDACAO_MOTIVOS | verificar_consistencia_categorica | tabela=vendas, coluna_a=motivo_devolucao, coluna_b=categoria | PASS |  |
| 53 | Existem registros de 'Tamanho errado' em categorias que não possuem tamanho? | VALIDACAO_MOTIVOS | verificar_consistencia_categorica | tabela=vendas, coluna_a=motivo_devolucao, coluna_b=categoria | PASS |  |
| 54 | Existem registros de 'Atraso' em pedidos entregues dentro do prazo? | COERENCIA_PRAZO | coerencia_motivo_entrega | — | PASS com ressalva | a ferramenta devolve leitura |
| 55 | Quais informações estão faltando nos registros de devolução? | DEVOLUCOES | impacto_devolucoes | por=canal | PASS com ressalva | a ferramenta devolve nota |
| 56 | Por que não podemos afirmar quais são as verdadeiras causas das devoluções? | LIMITE_DE_DADOS | cobertura_de_dados | assunto=causa_de_devolucao | RECUSA MEDIDA | o campo registra o motivo DECLARADO no atendimento, não a causa apurada, e ele próprio é inconsistente: há 'Tamanho errado' em categorias onde tamanho |
| 57 | Podemos calcular o custo real das devoluções com os dados atuais? | DEVOLUCOES | impacto_devolucoes | por=canal | PASS com ressalva | a ferramenta devolve nota |
| 58 | Qual é a faixa de impacto financeiro das devoluções suportada pelos dados? | DEVOLUCOES | impacto_devolucoes | por=canal | PASS com ressalva | a ferramenta devolve nota |
| 59 | Por que ainda não devemos estabelecer uma meta de redução de devoluções? | LIMITE_DE_DADOS | cobertura_de_dados | assunto=previsao_de_devolucao | RECUSA MEDIDA | prever a redução exige efeito causal estimado; a base é observacional e não contém nenhuma intervenção anterior para medir. É possível dizer quanto es |
| 60 | Quantos motivos de 'Tamanho errado' são coerentes com a categoria? | VALIDACAO_MOTIVOS | verificar_consistencia_categorica | tabela=vendas, coluna_a=motivo_devolucao, coluna_b=categoria | PASS |  |
| 61 | Quantos registros de 'Atraso' são coerentes com o prazo de entrega? | COERENCIA_PRAZO | coerencia_motivo_entrega | — | PASS com ressalva | a ferramenta devolve leitura |
| 62 | Quantos casos de 'Defeito' possuem evidência compatível? | LIMITE_DE_DADOS | cobertura_de_dados | assunto=causa_de_devolucao | RECUSA MEDIDA | o campo registra o motivo DECLARADO no atendimento, não a causa apurada, e ele próprio é inconsistente: há 'Tamanho errado' em categorias onde tamanho |
| 63 | Quantos registros de devolução podem ser considerados confiáveis? | VALIDACAO_MOTIVOS | verificar_consistencia_categorica | tabela=vendas, coluna_a=motivo_devolucao, coluna_b=categoria | PASS |  |
| 64 | Quantos registros de devolução precisam ser revisados? | VALIDACAO_MOTIVOS | verificar_consistencia_categorica | tabela=vendas, coluna_a=motivo_devolucao, coluna_b=categoria | PASS |  |
| 65 | Qual percentual dos motivos de devolução pode ser validado? | VALIDACAO_MOTIVOS | verificar_consistencia_categorica | tabela=vendas, coluna_a=motivo_devolucao, coluna_b=categoria | PASS |  |
| 66 | Quais campos estão faltando para melhorar a qualidade da informação de devolução? | DEVOLUCOES | impacto_devolucoes | por=canal | PASS com ressalva | a ferramenta devolve nota |

## Sazonalidade e comparações (perguntas 67–72)

| # | Pergunta | Intenção | Ferramenta | Parâmetros | Veredito | Observação |
|---|---|---|---|---|---|---|
| 67 | Existe sazonalidade nas vendas? | SAZONALIDADE | indice_sazonalidade | — | PASS |  |
| 68 | Quais meses apresentam melhor desempenho? | SAZONALIDADE | indice_sazonalidade | — | PASS |  |
| 69 | Quais meses apresentam pior desempenho? | SAZONALIDADE | indice_sazonalidade | — | PASS |  |
| 70 | Como comparar o segundo semestre de 2023 com o primeiro? | COMPARACAO_PERIODOS | comparar_periodos | periodo_a=2023-01:2023-06, periodo_b=2023-07:2023-12 | PASS |  |
| 71 | Houve mudança significativa entre os períodos? | COMPARACAO_PERIODOS | comparar_periodos | — | PEDE PARÂMETRO | falta periodo_a, periodo_b — a pergunta não traz |
| 72 | Existe diferença estatisticamente significativa de margem entre os canais? | TESTE_ESTATISTICO | anova_um_fator | metrica=margem_contribuicao, coluna_grupo=canal | PASS |  |

## Perguntas executivas (perguntas 73–86)

| # | Pergunta | Intenção | Ferramenta | Parâmetros | Veredito | Observação |
|---|---|---|---|---|---|---|
| 73 | Qual é o principal problema identificado nos dados? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 74 | Qual é o maior vazamento financeiro? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 75 | Qual é a maior oportunidade de recuperação? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 76 | Qual frente deveria ser priorizada? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 77 | Quanto pode ser recuperado em cada frente? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 78 | Qual deveria ser a prioridade número 1? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 79 | Quais são as principais recomendações para o comitê? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 80 | Quais são os principais riscos? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 81 | O que deve ser feito nos próximos 30 dias? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 82 | O que deve ser feito entre 31 e 60 dias? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 83 | O que deve ser feito entre 61 e 90 dias? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 84 | Qual decisão precisa ser tomada pelo comitê? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 85 | Quais conclusões são fatos e quais são cenários? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |
| 86 | Qual é a força da evidência de cada conclusão? | PERGUNTA_COMPLEXA | — | — | ReAct | investigação aberta: sem ferramenta única, por decisão |

## Perguntas sem lastro nos dados (perguntas 87–95)

| # | Pergunta | Intenção | Ferramenta | Parâmetros | Veredito | Observação |
|---|---|---|---|---|---|---|
| 87 | Qual é o CAC? | LIMITE_DE_DADOS | cobertura_de_dados | assunto=cac | RESSALVA FORTE | a coluna `cac` existe e pode ser reportada COMO ESTÁ, mas não reconcilia: a receita_gerada das campanhas é múltiplas vezes a receita real da base, e a |
| 88 | Qual é o ROAS real por canal? | MARKETING | ranking_roas_canais | — | PASS com ressalva | a ferramenta devolve uso_permitido |
| 89 | Qual é o LTV dos clientes? | LIMITE_DE_DADOS | cobertura_de_dados | assunto=ltv | RECUSA MEDIDA | o campo existe, mas não é verificável: a base de vendas cobre 2.21% dos clientes do cadastro e o `ltv_acumulado` praticamente não correlaciona com a r |
| 90 | Qual é o churn? | LIMITE_DE_DADOS | cobertura_de_dados | assunto=churn | RECUSA MEDIDA | existe um RÓTULO 'Churn' no cadastro, não um EVENTO de churn: sem data de última compra nem janela declarada, não há como recalcular a taxa nem datar  |
| 91 | Quais são os melhores segmentos de clientes? | LIMITE_DE_DADOS | cobertura_de_dados | assunto=segmentos_de_clientes | RESSALVA FORTE | dá para cruzar segmento com margem observada, mas só para os 331 clientes que aparecem em vendas (2.21% do cadastro) — e o rótulo é pré-calculado por  |
| 92 | Quais clientes deveriam receber uma oferta individual? | LIMITE_DE_DADOS | cobertura_de_dados | assunto=oferta_individual | RECUSA MEDIDA | escolher quem recebe oferta exige estimar resposta individual; a base não tem nenhuma oferta passada com resultado, nem grupo de controle — qualquer l |
| 93 | Podemos automatizar a classificação dos tickets? | LIMITE_DE_DADOS | cobertura_de_dados | assunto=classificacao_de_tickets | RESSALVA FORTE | há texto e uma categoria já preenchida, então é tecnicamente treinável — mas a qualidade do rótulo existente não foi auditada, e um classificador trei |
| 94 | Quais são as verdadeiras causas das devoluções? | LIMITE_DE_DADOS | cobertura_de_dados | assunto=causa_de_devolucao | RECUSA MEDIDA | o campo registra o motivo DECLARADO no atendimento, não a causa apurada, e ele próprio é inconsistente: há 'Tamanho errado' em categorias onde tamanho |
| 95 | Qual será exatamente a redução das devoluções depois da intervenção? | LIMITE_DE_DADOS | cobertura_de_dados | assunto=previsao_de_devolucao | RECUSA MEDIDA | prever a redução exige efeito causal estimado; a base é observacional e não contém nenhuma intervenção anterior para medir. É possível dizer quanto es |

## Resumo

- **PASS com ressalva**: 47
- **PASS**: 20
- **ReAct**: 16
- **RECUSA MEDIDA**: 8
- **RESSALVA FORTE**: 3
- **PEDE PARÂMETRO**: 1
- **total**: 95
