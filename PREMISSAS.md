# Premissas e decisões de tratamento de dados

Toda decisão de filtro, exclusão ou interpretação usada pelo motor está aqui.
Nada é decidido implicitamente dentro do código: o que o motor faz com os dados
está descrito neste arquivo, e o resumo executável correspondente está em
`vertice/data.py::resumo_tratamento()` (exposto no retorno de
`margem_consolidada`, campo `base`).

---

## P1 — Só `status_pagamento == 'Aprovado'` é receita real

**Decisão.** Toda métrica financeira usada para decisão filtra
`status_pagamento == 'Aprovado'`.

**Por quê.** A coluna tem três valores: `Aprovado` (24.454 pedidos),
`Cancelado` (2.207) e `Aguardando` (1.097). Pedidos cancelados e aguardando
somam **R$ 2.407.110,01 — 11,73% da receita bruta reportada** em `vendas.csv`.
Esse dinheiro nunca foi recebido. Usar a receita bruta cheia infla a base de
qualquer cálculo de margem e leva a dimensionar errado qualquer oportunidade.

**Onde.** `vertice/data.py::carregar_vendas(apenas_aprovados=True)` — padrão.
Para exploração explícita do funil de pagamento, `apenas_aprovados=False`.

**Efeito.** Receita bruta de decisão: R$ 18.119.023,83 (e não R$ 20.526.133,84).

**Exceção única e nomeada: `perda_pos_pedido`.** Esta premissa é correta para
dimensionar margem, preço e desconto, e apaga da vista exatamente o que o
diagnóstico precisa mostrar: a margem que a empresa CALCULA e não realiza,
porque o pedido é cancelado ou fica pendente. `engine/pos_pedido.py` é a única
ferramenta do motor que lê todos os status, e por isso:

- declara em campo próprio que seus valores **não se somam** ao déficit medido
  por `margem_consolidada` — aquele mede o que se perde ENTRE a receita bruta e a
  margem, este mede o que se perde DEPOIS dela, e somar os dois conta a mesma
  perda duas vezes;
- declara que cancelamento e pendência são **margem que nunca se realizou, não
  economia capturável**. Apresentá-los como oportunidade produziria um ganho de
  R$ 2,63 milhões que não existe;
- a mesma trava está no system prompt do agente (armadilha nº 7), porque o
  motor pode devolver o número certo e o texto ainda somá-lo errado.

---

## P2 — `marketing.receita_gerada` não é usada para nenhum valor em R$

**Decisão.** Nenhuma estimativa financeira absoluta usa `receita_gerada` de
`marketing.csv`. ROAS é usado apenas como **ranking relativo** entre canais.

**Por quê.** Na mesma janela de `vendas.csv`, a soma de `receita_gerada` é
**R$ 315.414.157 — 17,4x a receita real aprovada**. A causa é a coluna
`atribuicao`: as campanhas usam Linear, First Click e Last Click
simultaneamente, e os três modelos contam a mesma venda. Somar as linhas conta
a mesma receita várias vezes.

**Onde.** `vertice/engine/extras.py::ranking_roas_canais` — devolve o ranking e,
junto, a auditoria do fator de inflação, para que o número inflado nunca circule
sem o aviso.

---

## P3 — A identidade contábil da margem é sanidade, não causa raiz

**Fato.** Para todo pedido, exatamente:

```
receita_bruta = desconto_reais + custo_produto + custo_frete + margem_contribuicao
```

Verificado com erro máximo de 9,1e-13 em 24.454 pedidos
(`tests/test_integridade_dados.py::test_identidade_contabil_por_pedido`).
Logo `margem% + desconto% + custo% + frete% = 100%` por definição.

**Consequência.** Uma regressão de `margem_pct` sobre
`desconto_pct + custo_pct + frete_pct` devolve **R² = 1,0 trivialmente**. Isso
confirma que a base fecha — e **não é achado de causa raiz**.

**Onde.** `regressao_linear_multipla` detecta esse caso e devolve o campo
`alerta_identidade_contabil` preenchido. O system prompt do agente proíbe
apresentar esse R² como descoberta de negócio.

---

## P4 — Desconto x volume é correlação, não causalidade

**Fato observado.** Entre as faixas de desconto (0%, 0-10%, 10-20%, 20-25%,
25-30%, 30%+), itens por pedido variam de 3,432 a 3,556 (amplitude 0,124) e o
ticket médio de R$ 705,86 a R$ 759,56 (amplitude 7,26%), enquanto a margem cai
monotonicamente de 58,13% para 22,51%.

**Leitura permitida.** O desconto reduz margem sem comprar volume proporcional.

**Leitura proibida.** "O desconto não causa volume." Estes são dados
observacionais: não há grupo de controle nem variação exógena do desconto. O
resultado é compatível com viés de seleção (quem recebe desconto pode ser
sistematicamente diferente). A afirmação causal exige teste A/B.

**Onde.** `tabela_faixas_desconto` devolve `ressalva_causal` em todo retorno.

---

## P5 — Toda simulação assume volume constante

**Decisão.** `simular_teto_desconto` e `cenarios_reducao_desconto` assumem que
os pedidos afetados continuariam acontecendo com desconto menor.

**Por quê.** Não é possível estimar elasticidade-preço a partir desta base
(ver P4). A simulação é, portanto, um **teto de oportunidade**, não uma
previsão de resultado.

**Onde.** Ambas as ferramentas devolvem o campo `premissa` com o texto explícito,
e o agente é instruído a citar a premissa junto do número na RECOMENDAÇÃO.

---

## P6 — Sazonalidade e mês parcial

**Decisão.** O índice sazonal é calculado sobre **pedidos por dia**, não sobre o
total do mês, e o último mês da base é marcado como parcial.

**Por quê.** A base vai de **2023-01-01 a 2024-01-26**: janeiro/2024 tem apenas
26 dias observados. Comparar o total absoluto de 2024-01 com um mês cheio
produz uma queda artificial de ~16%. Além disso, novembro/2023 tem índice
sazonal 1,95 (quase o dobro da média) — comparar novembro com outro mês sem
ajuste lê sazonalidade normal como mudança estrutural.

**Onde.** `indice_sazonalidade` devolve `meses_parciais` e `alerta`;
`comparar_periodos` devolve um alerta permanente recomendando consultar a
sazonalidade antes de concluir.

---

## P7 — `margem_contribuicao` é anterior à devolução

**Fato.** A identidade de P3 fecha sem nenhum termo de devolução: a margem
reportada **não** desconta pedidos devolvidos. São 3.639 pedidos devolvidos
(14,88%), carregando R$ 1.351.707,09 de margem — **7,46 pp** da margem
consolidada.

**Decisão.** Esse valor é tratado como vazamento **adicional**, nunca somado
duas vezes ao déficit já medido pelos outros componentes.

**Onde.** `impacto_devolucoes`, e o campo `devolucao` em `margem_consolidada`.

---

## P8 — Margem negativa não é outlier a limpar

**Fato.** 427 pedidos (1,75%) têm margem de contribuição negativa, somando
−R$ 5.782,86. Não é erro de dado: são pedidos de ticket baixo (média R$ 103,90
contra R$ 740,94 geral) abaixo do limiar de frete grátis, em que o frete —
custo praticamente fixo por pedido, ~R$ 32 — supera a margem do produto. Na
faixa de ticket de R$ 0-50 a margem média é **−22,15%**.

**Decisão.** Esses pedidos permanecem na base e são expostos por ferramenta
própria, em vez de removidos como outliers.

**Onde.** `pedidos_margem_negativa`.

---

## P9 — Uma linha vazia descartada

`vendas.csv` tem 27.759 linhas de dados, sendo **1 linha totalmente vazia** ao
final (apenas `order_id`, `customer_id`, `sku_id`, `data_pedido`, `canal`,
`categoria` e `produto` preenchidos, todos os campos financeiros nulos).
Descartada na carga por `dropna(subset=["status_pagamento", "receita_bruta"])`.

---

## P10 — Encoding

Os CSVs vêm com BOM UTF-8. Lidos com `encoding="utf-8-sig"`; sem isso, o nome da
primeira coluna de cada arquivo viria com `﻿` prefixado.

---

---

## P11 — O recorte da simulação é parâmetro declarado, nunca filtro implícito

**Decisão.** Toda ferramenta de simulação aceita `convencao`, `ano`,
`excluir_meses` e `excluir_devolvidos`, e **devolve o recorte usado** no campo
`recorte_aplicado`. Duas convenções estão nomeadas em `engine/recorte.py`:

| Convenção | População | Para quê |
|---|---|---|
| `decisao` (padrão dos simuladores) | ano 2023, pedidos mantidos, novembro fora | é a base sobre a qual o comitê decide |
| `diagnostico` | toda a base aprovada, 13 meses, nada excluído | dimensionar o problema sem recorte que possa parecer escolhido |

**Por quê.** O mesmo teto de 20% preserva R$ 241.424,23 na base de decisão e
R$ 369.836,50 na base inteira. Os dois números estão certos; o que muda é a
população. Enquanto o recorte não era parâmetro, não havia como pedir um ou
outro, nem como saber pela resposta qual tinha sido usado — e uma pergunta que
dizia "fora de novembro" produzia a mesma chamada que uma que não dizia.

**Por que novembro sai do teto, e só dele.** Novembro é Black Friday (índice
sazonal 1,95, quase o dobro da média) e roda sob orçamento de campanha aprovado,
não sob a política de desconto corrente. É também a única janela em que a base
mostra associação entre desconto e volume, e essa associação não é separável do
efeito da campanha. A regra de **frete** não tem relação com campanha: vale o ano
inteiro, e por isso `regra_frete_por_limiar` parte da convenção de decisão sem a
exclusão de meses.

**Onde.** `engine/recorte.py`; `agent/router.py::_recorte_dito` extrai o recorte
do texto da pergunta ("fora de novembro", "no ano todo", "com os devolvidos").

---

## P12 — Margem tem dois denominadores, e os dois viajam juntos

**Fato.** `margem_contribuicao ÷ receita_bruta` = 49,99%.
`margem_contribuicao ÷ receita_liquida` = 54,34%. É a mesma margem em R$.

**Decisão.** Nenhum campo se chama apenas `margem_pct` sem par: todo agregado
devolve `margem_pct_sobre_bruta` e `margem_pct_sobre_liquida`, e
`margem_consolidada` devolve o bloco `denominadores` dizendo qual serve para quê.

**Por quê.** A decomposição MECE (`margem% + desconto% + custo% + frete% = 100%`)
só fecha sobre a receita bruta, porque é identidade contábil sobre ela. O comitê
e a apresentação leem margem sobre receita líquida, porque desconto concedido não
é receita da empresa. Escolher uma só obrigaria a refazer um dos dois trabalhos;
trocar uma pela outra é erro de 4,35 p.p. com aparência de erro de digitação.

**Onde.** `engine/margin.py::_agrega`; armadilha nº 8 do system prompt proíbe
comparar uma com a outra ou rotular uma com o nome da outra.

---

## Limitações que estas premissas NÃO resolvem

1. **Sem contrafactual real.** Nenhum número deste projeto vem de experimento.
   Todos os impactos estimados são tetos sob premissa declarada.
2. **Assimetria de frete pode ser contratual.** O motor mede que o Marketplace
   paga frete que os outros canais não pagariam na mesma faixa de ticket. Se o
   marketplace **impõe** esse frete por contrato, o valor é custo de operar no
   canal, não economia capturável. `custo_assimetria_frete` declara isso no
   campo `premissa`; a verificação é documental e está fora dos dados.
3. **Janela de ~13 meses.** Não há ano anterior completo para comparação
   ano-contra-ano nem para separar tendência de ciclo.
4. **Grão de pedido, não de item.** `vendas.csv` tem um `sku_id` por pedido com
   uma `quantidade`; não há cesta multi-SKU. "Itens por pedido" é a quantidade
   do único SKU do pedido.
