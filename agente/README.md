# Vértice Retail — Motor Determinístico + Agente de Diagnóstico de Margem

A Vértice Retail cresceu receita sem que a margem de contribuição acompanhasse.
Este projeto entrega o **motor de cálculo** que produz os números e o **agente
ReAct** que investiga hipóteses de margem e recomenda ação com impacto
financeiro estimado.

Princípio central: **o LLM não calcula nada.** Todo número que aparece numa
resposta veio de uma chamada real a uma ferramenta Python executada sobre os
CSVs. O modelo decide *como interpretar*; a aritmética é determinística e
testada — e, quando a pergunta é estruturada, quem decide *o que perguntar aos
dados* também é o código.

```
pergunta → roteador determinístico → ferramenta Python → resultado estruturado
        → o modelo interpreta → verificação numérica → resposta → trace
```

Três garantias sustentam isso, todas executáveis e testadas:

1. **Roteamento determinístico** — intenção, ferramenta e parâmetros decididos em Python antes de o modelo opinar.
2. **Verificação numérica** — número que não apareceu em resultado de ferramenta bloqueia a publicação.
3. **Cobertura de dados** — pergunta sem lastro vira recusa medida, com a lacuna nomeada.

| | |
|---|---|
| Ferramentas determinísticas | **39** |
| Testes automatizados | **925 passando**, 11 pulados |
| Testes de aceite contra o Livro de Números | **35** |
| Perguntas do case auditadas | **95**, nenhuma FAIL |
| Base | 24.454 pedidos aprovados · 01/01/2023 a 26/01/2024 |
| Base de decisão (padrão dos simuladores) | 2023 · pedidos mantidos · novembro fora do teto |

| Documentação | O que tem |
|---|---|
| [PREMISSAS.md](PREMISSAS.md) | as 12 premissas de dado, numeradas e citadas pelo código |
| [docs/COMO_RODAR.md](docs/COMO_RODAR.md) | instalação, execução e variáveis de ambiente |
| [docs/AUDITORIA_PERGUNTAS.md](docs/AUDITORIA_PERGUNTAS.md) | relatório gerado das 95 perguntas |
| [../documentacao/](../documentacao/) | documentação técnica em PDF |
| [../analise/](../analise/) | scripts do squad que geraram o Livro de Números |

## O recorte é sempre declarado

Os simuladores respondem sobre a **base de decisão** do caso (2023, pedidos
mantidos, novembro fora do teto por ser Black Friday sob orçamento de campanha),
e todo resultado devolve `recorte_aplicado` dizendo qual população foi usada:

```python
executar("simular_teto_desconto", {"teto_pct": 20})
# → R$ 241.424,23 · 19,81% dos pedidos · equilíbrio em 26,32%

executar("simular_teto_desconto", {"teto_pct": 20, "convencao": "diagnostico"})
# → R$ 369.836,50 nos 13 meses (R$ 341.387,54 anualizados)
```

Os dois números estão certos. O que muda é a população — e é para isso que
`recorte_aplicado` existe. Ver PREMISSAS.md P11.

## Instalação e uso

```bash
python3 -m venv venv && source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

```bash
python -m vertice.api        # painel web em http://localhost:8000
python -m vertice.cli        # sessão interativa no terminal
python -m pytest             # 925 passando, 11 pulados
```

O motor **não precisa de internet nem de chave de API** — a chave
(`ELOAGENTS_API_KEY`) só serve para a camada de linguagem. Sem ela,
`--mock` mantém todos os números reais e troca apenas o texto.

### O painel

| Aba | O que faz |
|---|---|
| **Perguntar ao agente** | chat com trilha de auditoria; cada resposta grava um trace |
| **Relatório por período** | KPIs de margem com início e fim escolhidos pelo usuário |
| **Auditoria de dados** | as checagens determinísticas, com status por checagem |
| **Política de desconto** | teto vigente por recorte, simulação antes de aplicar, histórico |

Nenhum número é calculado no navegador: tudo vem pronto de `/api/*`; o
JavaScript só formata em pt-BR e desenha. O servidor é **stateless** — cada
requisição reconstrói o histórico a partir do que o front-end manda de volta.

## Arquitetura

```
vertice/
├── engine/     MOTOR DETERMINÍSTICO (nenhum LLM aqui)
│              margem, estatística, sazonalidade, desconto, frete,
│              auditoria, governança, cobertura, filtros
├── agent/      AGENTE (nenhum cálculo aqui)
│              router, llm, prompts, react, verificação, card, trace
├── politica.py     proposta, estados, segregação de funções, histórico
├── experimento.py  teste A/B: atribuição por hash, poder, regra de parada
├── relatorio.py    relatório por período + resumo opcional por IA
├── cli.py          terminal interativo
└── api.py          servidor HTTP (FastAPI) para o painel
```

O motor não importa nada do agente — é usável sozinho:

```python
from vertice.engine import executar
executar("custo_assimetria_frete", {"canal": "Marketplace"})
```

### As 39 ferramentas

| Módulo | Ferramentas |
|---|---|
| **Margin Calculator** | `margem_consolidada`, `margem_por_dimensao`, `margem_na_janela`, `comparar_periodos` |
| **Statistical Validator** | `teste_t_welch`, `anova_um_fator`, `regressao_linear_multipla`, `qui_quadrado_independencia`, `classificar_evidencia` |
| **Seasonality Normalizer** | `indice_sazonalidade`, `tendencia_ajustada_sazonalidade` |
| **Discount Simulator** | `tabela_faixas_desconto`, `simular_teto_desconto`, `cenarios_reducao_desconto`, `simular_desconto_em_segmento`, `simular_reajuste_preco` |
| **Freight Rule Detector** | `politica_frete_por_canal`, `dispersao_componentes_entre_canais`, `custo_assimetria_frete` |
| **Complementares** | `impacto_devolucoes`, `ranking_roas_canais`, `pedidos_margem_negativa` |
| **Data Quality Auditor** | 9 checagens de integridade, duplicata, completude, outlier, faixa, categoria, prazo e coerência |
| **Governança de desconto** | `consultar_politica_desconto`, `pedidos_acima_do_teto` |
| **Cobertura de dados** | `cobertura_de_dados` |

## Decisões que sustentam o resultado

**Roteador determinístico.** Entre a pergunta e o modelo há código que decide
sozinho qual é a intenção, qual ferramenta responde e com que parâmetros. A
ferramenta roda *antes do primeiro turno do modelo*. Quatro detalhes decidem o
acerto: teto ≠ aplicar (gatilhos por radical, não por forma exata); canal e
categoria lidos da base, não de lista fixa; gatilho curto casa só como palavra
inteira; e parâmetro que falta é **reportado, nunca inventado**.

**ReAct por texto, não `tools=` nativo.** O gateway não se mostrou confiável com
o parâmetro `tools=`: o modelo ignorou o schema e, sob `tool_choice="required"`,
chamou ferramentas de plataforma inexistentes no registro. As ferramentas são
descritas no prompt e o parser executa localmente. O modo nativo continua
disponível e **valida toda chamada contra o registro** — ferramenta de
plataforma vira erro explícito, nunca número inventado.

**Governança separa régua de apuração.** O teto vem da política registrada; as
alçadas vêm de configuração, **jamais derivadas dos dados**; as contagens vêm da
base. `origem_do_teto` e `origem_das_alcadas` acompanham a resposta — alçada
inventada parece alçada de verdade, e é o pior caso possível deste bloco.

**Trace.** Cada investigação produz um JSON com passos tipados, timestamp,
duração por ferramenta e parâmetros de cada chamada. É o que permite auditar
depois o que o agente realmente fez.

## Premissas de dados

As 12 estão em [PREMISSAS.md](PREMISSAS.md), numeradas e citadas pelo código. As
que mais mudam resposta:

- Só `status_pagamento == 'Aprovado'` conta como receita — **11,73%** da receita reportada nunca foi recebida.
- `marketing.receita_gerada` é **17,4x** a receita real por atribuição sobreposta: ROAS só como ranking, nunca como R$.
- `margem% + desconto% + custo% + frete% = 100%` é identidade contábil — R²≈1 é sanidade da base, **não causa raiz**.
- Desconto × volume é **correlação**, não causalidade. Toda simulação assume volume constante, e declara isso.
- `margem_contribuicao` é **anterior à devolução** — devolução é vazamento adicional.
- Campos de cliente (LTV, RFM) **não reconciliam**: a base de pedidos cobre 2,21% do cadastro. Pergunta de LTV, CAC ou churn passa por `cobertura_de_dados` antes de qualquer número.
- Motivo de devolução é **declarado, não apurado**: 684 registros de "Tamanho errado" em categorias sem grade, e 47,9% das devoluções por "Atraso" foram entregues dentro da mediana.

## Testes

```bash
python -m pytest          # 925 passando, 11 pulados
```

Os maiores: `test_perguntas_negocio.py` (401 — as 95 perguntas de ponta a
ponta), `test_agente.py` (152 — parser, loop, guardrails, trace),
`test_motor.py` (46), `test_api.py` (46), `test_router.py` (38),
`test_verificacao.py` (38) e `test_aceite_livro_de_numeros.py` (35 — o motor
reproduz o Livro de Números, ID a ID).

Cobrem identidade contábil fechando em ~100% (erro < 1e-6 em 24.454 pedidos),
aditividade da margem por canal/categoria/mês, os achados de negócio com
significância estatística, as armadilhas (a regressão da identidade dispara
alerta; a inflação do marketing é sinalizada; o mês parcial é detectado) e a
rastreabilidade numérica de cada uma das 95 perguntas.

## Auditoria das 95 perguntas

`docs/AUDITORIA_PERGUNTAS.md` é gerado por execução real — não existe versão
bonita do relatório que já não corresponda ao comportamento:

```bash
python -m scripts.auditoria_perguntas > docs/AUDITORIA_PERGUNTAS.md
```

| Veredito | Perguntas | Significado |
|---|---|---|
| PASS com ressalva | 47 | certo, e a ferramenta já devolve a premissa que a resposta precisa repetir |
| PASS | 20 | intenção, ferramenta, parâmetros e execução corretos |
| ReAct | 16 | investigação aberta — sem ferramenta única, por decisão |
| RECUSA MEDIDA | 8 | sem lastro nos dados; a recusa vem com a medida que a sustenta |
| RESSALVA FORTE | 3 | respondível só parcialmente, com a limitação nomeada |
| PEDE PARÂMETRO | 1 | falta um valor que a pergunta não traz — o agente pergunta em vez de chutar |
