# Case Vértice Retail — Bootcamp EloGroup

> **Como aumentar a margem de contribuição da Vértice Retail dentro de um
> horizonte de 90 dias?**

A Vértice Retail cresceu receita sem que a margem acompanhasse. Este
repositório tem as duas frentes do trabalho: a **análise** que descobriu onde a
margem vaza, e o **agente** que responde sobre ela em linguagem natural sem
nunca inventar um número.

| Frente | Onde | O que é |
|---|---|---|
| Análise | [`analise/`](analise/) | os quatro scripts do squad que geram e conferem os 358 números do trabalho |
| Protótipo de IA | [`agente/`](agente/) | o MarginGuard: motor determinístico, agente ReAct e painel web |
| Documentação | [`documentacao/`](documentacao/) | documentação técnica em PDF, para a banca |

---

## A análise

Quatro scripts em Python, sem internet e sem chave de API, rodando sobre as
cinco bases do case.

`livro_de_numeros.py` é o centro: ele calcula os **358 números** do trabalho —
margem no tempo, árvore de perdas, testes de desconto e volume, frete, business
case e demonstração do resultado — e publica cada um com ID, valor, marca de
confiança, base, cálculo e premissa. Todo número do deck sai dali.

Os outros três existem para não deixar nenhum número solto:
`memorias_de_calculo.py` refaz a demonstração do resultado conta por conta e
para com erro se divergir do Livro; `auditoria_dos_dados.py` audita as cinco
bases (tamanho, nulos, período, SHA-256, identidades); `checar_numeros.py`
confere o deck contra o Livro, exigindo que todo número do slide tenha lastro
num ID ou esteja declarado como derivado.

Detalhes e como rodar: [analise/README.md](analise/README.md).

## O agente

O **MarginGuard** responde perguntas sobre a margem em linguagem natural. O
princípio que organiza tudo é um só: **o LLM não calcula nada.** Todo número que
aparece numa resposta veio de uma chamada real a uma ferramenta Python
executada sobre os CSVs. O modelo decide como interpretar; a aritmética é
determinística e testada.

```
pergunta → roteador determinístico → ferramenta Python → resultado estruturado
        → o modelo interpreta → verificação numérica → resposta → trace
```

Três garantias sustentam isso, todas executáveis: **roteamento determinístico**
(qual ferramenta e quais parâmetros é o código que decide), **verificação
numérica** (número que não apareceu em resultado de ferramenta bloqueia a
publicação) e **cobertura de dados** (pergunta sem lastro vira recusa medida,
com a lacuna nomeada).

São **39 ferramentas** determinísticas e um painel web com chat, relatório,
auditoria, política de desconto e monitoramento. Entre os testes automatizados
estão **35 testes de aceite** que conferem, um a um, se o motor reproduz os
números do Livro gerado em `analise/` — é a costura que impede as duas frentes
de divergirem.

Arquitetura e decisões de projeto: [agente/README.md](agente/README.md).
Instalação e execução: [agente/docs/COMO_RODAR.md](agente/docs/COMO_RODAR.md).

## Como rodar o painel

A pasta `agente/` é autossuficiente — entre nela antes de qualquer comando.

```bash
cd agente
```

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
```

```bash
python -m vertice.api
```

Abra <http://localhost:8000>. O motor **não** precisa de internet nem de chave
de API: os números saem todos de código Python rodando sobre os CSVs em
`agente/data/`. A chave só serve para a camada de linguagem — o texto da
resposta. Sem ela, o painel sobe igual e os números continuam reais:

```bash
VERTICE_API_MOCK=1 python -m vertice.api
```

## Estrutura

```
Case-Vertice-Bootcamp/
├── agente/         o MarginGuard, autossuficiente
│   ├── data/       cinco CSVs do case (entrada; nunca reescritos)
│   ├── vertice/    motor + agente + API
│   ├── frontend/   painel web estático (sem framework, sem build)
│   ├── tests/      suíte automatizada, com os testes de aceite
│   ├── scripts/    auditoria das 95 perguntas e geração do PDF
│   ├── docs/       como rodar e relatório das 95 perguntas
│   └── PREMISSAS.md  as 12 premissas de dado, numeradas
├── analise/        os quatro scripts do squad
├── documentacao/   documentação técnica em PDF
└── scripts/        provisionamento do Kanban do projeto
```
