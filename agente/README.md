# Vértice Retail — Motor Determinístico + Agente de Diagnóstico de Margem

A Vértice Retail cresceu receita sem que a margem de contribuição acompanhasse.
Este projeto entrega o **motor de cálculo** que produz os números e o **agente
ReAct** que investiga hipóteses de margem autonomamente e recomenda ação com
impacto financeiro estimado.

Princípio central: **o LLM não calcula nada**. Todo número que aparece numa
resposta veio de uma chamada real a uma ferramenta Python executada sobre os
CSVs. O modelo decide *como interpretar*; a aritmética é toda determinística e
testada — e, quando a pergunta é estruturada, quem decide *o que perguntar aos
dados* também é o código, não o modelo.

```
pergunta → roteador determinístico → ferramenta Python → resultado estruturado
        → o modelo interpreta → verificação numérica → resposta → trace
```

Três garantias sustentam isso, todas executáveis e testadas:

1. **Roteamento determinístico** — intenção, ferramenta e parâmetros decididos
   em Python antes de o modelo opinar ([detalhes](#o-roteador-determinístico)).
2. **Verificação numérica** — número da resposta que não apareceu em resultado
   de ferramenta bloqueia a publicação ([detalhes](#o-agente)).
3. **Cobertura de dados** — pergunta sem lastro vira recusa medida, com a
   lacuna nomeada ([detalhes](#cobertura-de-dados-a-pergunta-se-sustenta)).

| | |
|---|---|
| Ferramentas determinísticas | **39** |
| Testes automatizados | **925 passando**, 11 pulados |
| Testes de aceite contra o Livro de Números | **35** ([arquivo](tests/test_aceite_livro_de_numeros.py)) |
| Perguntas do case auditadas | **95**, nenhuma FAIL ([relatório](docs/AUDITORIA_PERGUNTAS.md)) |
| Base | 24.454 pedidos aprovados · 01/01/2023 a 26/01/2024 |
| Base de decisão (padrão dos simuladores) | 2023 · pedidos mantidos · novembro fora do teto |

### Documentação

| Onde | O que tem |
|---|---|
| este README | arquitetura, roteador, agente, ferramentas e decisões de projeto |
| [PREMISSAS.md](PREMISSAS.md) | as 12 premissas de dado, numeradas e citadas pelo código |
| [docs/COMO_RODAR.md](docs/COMO_RODAR.md) | instalação, execução, variáveis de ambiente e problemas comuns |
| [docs/AUDITORIA_PERGUNTAS.md](docs/AUDITORIA_PERGUNTAS.md) | relatório gerado das 95 perguntas do case |
| [documentacao/](documentacao/) | documentação técnica do agente em PDF, para a banca |
| [analise/](analise/) | scripts do squad que geraram o Livro de Números — a procedência dos testes de aceite |

### O recorte é sempre declarado

Os simuladores respondem sobre a **base de decisão** do caso (ano 2023, pedidos
mantidos, novembro fora do teto por ser Black Friday sob orçamento de campanha),
e todo resultado devolve `recorte_aplicado` dizendo qual população foi usada. A
base inteira continua a uma chamada de distância:

```python
executar("simular_teto_desconto", {"teto_pct": 20})
# → R$ 241.424,23 · 19,81% dos pedidos · equilíbrio em 26,32%

executar("simular_teto_desconto", {"teto_pct": 20, "convencao": "diagnostico"})
# → R$ 369.836,50 nos 13 meses (R$ 341.387,54 anualizados)
```

Os dois números estão certos. O que muda é a população, e é isso que o campo
`recorte_aplicado` existe para dizer. Ver [PREMISSAS.md](PREMISSAS.md) P11.

---

## Instalação

```bash
python3 -m venv venv && source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Os cinco CSVs devem estar em `data/` (já estão neste repositório):
`vendas.csv`, `clientes.csv`, `marketing.csv`, `estoque.csv`, `atendimento.csv`.
Para apontar para outra pasta, use `VERTICE_DATA_DIR`.

## Ordem de importação e a chave de API

`config.chave_gateway()` sempre relê `ELOAGENTS_API_KEY` do ambiente no momento
da chamada — nunca confie em `config.ELO_API_KEY` (constante fixada uma única
vez, no import do módulo). Isso importa em processos de vida longa que importam
`vertice` antes de a chave existir: o caso real é o notebook Colab, onde a
Parte 1 (motor) importa `vertice.engine` antes de a Parte 2 pedir e definir a
chave — sem essa leitura tardia, `EloAgentsLLM()` recusaria uma chave que na
verdade tinha sido definida corretamente, com o erro enganoso "Chave de API
ausente". O terminal (`python -m vertice.cli`) nunca teve esse problema porque
o processo Python só nasce depois do `export`.

`chave_gateway()` **não tem fallback** para `ELO_API_KEY`. Uma versão anterior
tinha `os.getenv(...) or ELO_API_KEY` como "rede de segurança" — e isso
reintroduzia o mesmo bug ao contrário: se a chave esteve presente em qualquer
momento anterior do processo (o caso comum no terminal, onde `export` roda
antes de `python -m pytest`), removê-la depois não tinha efeito, porque a
função caía de volta no valor congelado. `os.getenv` puro já resolve os dois
sentidos — o fallback nunca foi necessário.

## Variáveis de ambiente

Copie `.env.example` para `.env` ou exporte no shell. As três que mudam o
comportamento do agente:

| Variável | Obrigatória | Padrão | Para que serve |
|---|---|---|---|
| `ELOAGENTS_API_KEY` | **sim** (exceto `--mock`) | — | chave do gateway; só a camada de linguagem usa |
| `VERTICE_TOOL_MODE` | não | `texto` | `texto` (ReAct por parsing) ou `nativo` (`tools=`) |
| `VERTICE_MAX_ITER` | não | `8` | teto de iterações do loop ReAct |

A tabela completa — modelos, recorte padrão, caminhos de arquivo e modo mock —
está em **[docs/COMO_RODAR.md](docs/COMO_RODAR.md)**.

## Como rodar

```bash
# testa a conexão com o gateway e lista os modelos disponíveis
python -m vertice.cli --diagnostico

# sessão interativa (o que você usa para testar perguntas livres)
python -m vertice.cli

# testes
python -m pytest

```

Comandos da sessão interativa: `/ferramentas`, `/trace`, `/salvar`, `/exemplos`,
`/limpar`, `/ajuda`, `/sair`.

### Interface web (MarginGuard)

O front-end de chat já vem ligado ao motor
via `vertice/api.py`:

```bash
export ELOAGENTS_API_KEY="sua chave"
python -m vertice.api
# abrir http://localhost:8000 no navegador
```

`GET /api/health` devolve se a chave está configurada e quais modelos estão
em uso — útil pra depurar sem abrir o navegador:
`curl http://localhost:8000/api/health`.

Cada pergunta feita pela interface web salva o trace em `traces/` (igual o
`/salvar` do CLI) e devolve o `trace_id` na resposta — para auditar depois o
que o agente realmente fez: `curl http://localhost:8000/api/trace/<id>`.
Sem isso não haveria como investigar uma resposta estranha vinda da web,
diferente do CLI que tem `/trace` na hora.

O servidor é **stateless**: cada requisição reconstrói o histórico da
conversa a partir do que o próprio front-end manda de volta (ele já guarda
localmente os pares pergunta/resposta), em vez de manter uma sessão viva no
processo — mais simples e sem risco de misturar conversas de abas/pessoas
diferentes usando o mesmo servidor.

#### As quatro abas

| Aba | O que faz |
|---|---|
| **Perguntar ao agente** | chat com trilha de auditoria; cada resposta grava um trace |
| **Relatório por período** | KPIs de margem com data de início e fim escolhidas pelo usuário |
| **Auditoria de dados** | as checagens determinísticas, com status por checagem |
| **Política de desconto** | teto vigente por recorte, simulação antes de aplicar, histórico |

Nada de terminal é necessário: o que antes era `python -m vertice.relatorio` ou
uma chamada de ferramenta virou tela. Nenhum número é calculado no navegador —
tudo vem pronto de `/api/*`; o JavaScript só formata em pt-BR e desenha.

#### Regras de interface

**O período escolhido é respeitado.** A janela vai para a API como tamanho
(`dias`) mais data de fim (`ate`), que é como `margem_na_janela` sempre soube
trabalhar. Período fora do intervalo da base não vira erro: a janela volta
rotulada corretamente e a tela diz que não há pedido aprovado ali, com o
intervalo que a base cobre.

### Governança: auditoria, política e relatório

```bash
# relatório — 100% determinístico, agendável em cron, sem chave de API
python -m vertice.relatorio

# com o parágrafo de insight redigido por IA (opcional; sem ele o relatório sai igual)
python -m vertice.relatorio --com-resumo
```

---

## Arquitetura

```
vertice/
├── config.py              constantes de negócio e variáveis de ambiente
├── data.py                carga, filtros e derivadas  ── aplica as premissas
├── engine/                MOTOR DETERMINÍSTICO (nenhum LLM aqui)
│   ├── registry.py        registro de ferramentas: prompt + schema + despacho
│   ├── margin.py          Margin Calculator
│   ├── stats.py           Statistical Validator
│   ├── seasonality.py     Seasonality Normalizer
│   ├── discount.py        Discount Simulator
│   ├── freight.py         Freight Rule Detector
│   ├── auditoria.py       Data Quality Auditor (checagens determinísticas)
│   ├── governanca.py      política de desconto aplicada ao dado + alçadas
│   ├── cobertura.py       a pergunta é sustentável pelos dados? (esquema + reconciliação)
│   ├── filtros.py         normaliza mês/canal/categoria escritos em português
│   └── extras.py          devolução, marketing, margem negativa
├── agent/                 AGENTE (nenhum cálculo aqui)
│   ├── router.py          ROTEADOR DETERMINÍSTICO: intenção, ferramenta e parâmetros
│   ├── llm.py             cliente EloAgents + MockLLM determinístico
│   ├── prompts.py         system prompt, protocolo ReAct, etiquetas de papel
│   ├── react.py           loop, parser de AÇÃO/PARÂMETROS, fallbacks
│   ├── verificacao.py     confere que todo número da resposta veio de ferramenta
│   ├── card.py            card estruturado para o painel, a partir do trace
│   └── trace.py           trace estruturado (JSON) para auditoria e painel
├── politica.py            proposta, estados, segregação de funções, histórico
├── experimento.py         teste A/B: atribuição por hash, poder, regra de parada
├── relatorio.py           relatório por período determinístico + resumo opcional por IA
├── render_html.py         relatório e auditoria em HTML (abrir e baixar)
├── auditoria_semantica.py suspeita de incoerência assistida por LLM (camada 2)
├── cli.py                 terminal interativo
└── api.py                 servidor HTTP (FastAPI) para o front-end web
```

E o repositório inteiro:

```
agente/
├── data/                  os cinco CSVs do case (entrada; nunca reescritos)
├── vertice/               motor + agente + API  ── a árvore acima
├── frontend/              painel web estático (sem framework, sem build)
├── tests/                 925 testes
├── scripts/               auditoria_perguntas.py: gera docs/AUDITORIA_PERGUNTAS.md
├── design-system/         tokens de marca e regras de uso (proveniência do visual)
├── docs/                  como rodar + relatório gerado das 95 perguntas
├── README.md              este arquivo
├── PREMISSAS.md           toda decisão de filtro e exclusão, numerada
├── requirements.txt
└── .env.example           modelo do .env (a chave nunca é versionada)
```

### Onde o LLM pode e não pode entrar

O motor (`engine/`) continua sem tocar em LLM: a auditoria determinística vive
lá, e a camada semântica assistida por IA
(`auditoria_semantica.sugerir_inconsistencias_semanticas`) vive fora, acima
dele. Ela pede ao modelo só o **julgamento de domínio** ("'Tamanho errado' faz
sentido em Beleza?") — as contagens vêm sempre da camada determinística, e
número citado pelo modelo é descartado. Todo alerta sai com
`origem="sugestao_ia_pendente_revisao"`: é insumo para revisão humana, nunca
achado confirmado.

O motor não importa nada do agente. É usável sozinho:

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
| **Data Quality Auditor** | `checar_integridade_referencial`, `checar_duplicatas_chave`, `checar_completude`, `checar_outliers_iqr`, `checar_faixa_implausivel`, `verificar_consistencia_categorica`, `checar_devolucao_fora_prazo`, `coerencia_motivo_entrega`, `relatorio_auditoria_dados` |
| **Governança de desconto** | `consultar_politica_desconto`, `pedidos_acima_do_teto` |
| **Cobertura de dados** | `cobertura_de_dados` |

---

## O roteador determinístico

Entre a pergunta e o modelo existe uma camada de código que decide sozinha, sem
LLM, **qual é a intenção, qual ferramenta responde e com que parâmetros**
(`agent/router.py`). Quando ela resolve, a ferramenta é executada *antes do
primeiro turno do modelo* e o resultado entra na conversa como observação — o
modelo recebe número apurado e não a tarefa de escolher como apurá-lo.

O fluxo completo é:

```
pergunta → roteador determinístico → ferramenta Python → resultado estruturado
        → o modelo interpreta → verificação numérica → resposta → trace
```


### Quatro detalhes que decidem o acerto

**Teto ≠ aplicar.** Um teto limita quem passa do valor; aplicar define o valor do
segmento inteiro. Os gatilhos são **radicais**, não formas exatas — "capasse",
"travasse" e "restringisse" precisam cair em `TETO_DESCONTO` como "limitar".
Conjugar à mão deixou metade dos verbos de fora numa versão anterior, e a
pergunta devolvia outro número, não só outra ferramenta.

**Valores lidos da base, não de lista fixa.** Canal e categoria vêm de
`carregar_vendas()`: canal novo no Data Room passa a ser reconhecido sem editar
código. A busca casa por **limite de palavra** (para "moda" não acertar
"modalidade"), o mais **longo vence** ("Email Marketing" antes de um eventual
canal "Email"), e o trecho casado é **removido do texto** antes da detecção de
intenção — é isso que impede "Email Marketing" de disparar a pista de marketing.

**Gatilho curto casa só como palavra inteira.** Substring pura mandou
"classifi**cac**ão dos tickets" para o assunto CAC.

**Parâmetro que falta é reportado, nunca inventado.** `validar_parametros()`
normaliza canal/categoria contra a base e confere percentual na faixa 0–100.
Sem teto na pergunta e sem política registrada, o roteador marca `faltando` e o
agente pergunta — antes disso a ferramenta levantava `TypeError` e a pergunta
morria ali.

### Estados no trace

Cada decisão fica registrada com origem (`roteador_deterministico`, `llm_react`
ou `pre_semeadura`) e estado de execução (`TOOL_CALLED_SUCCESS`,
`TOOL_CALLED_ERROR`, `TOOL_RESULT_EMPTY`, `INVALID_PARAMETERS`,
`TOOL_NOT_CALLED`). "Não retornou" era ambíguo demais: não dava para saber se a
ferramenta nem foi chamada, se quebrou, ou se rodou e o recorte estava vazio — e
a resposta final dizia a mesma coisa nos três casos.

---

## Governança de desconto: política e alçadas

Duas coisas diferentes convivem em `engine/governanca.py`, e todo retorno diz
qual é qual:

- o **teto** vem de `politica.politica_vigente()` — estado registrado, com dono
  e vigência. Não havendo política, o resultado diz isso em vez de escolher um
  número (cai no limiar de exceção já configurado no projeto,
  `config.LIMIAR_DESCONTO_ALTO`, com a origem declarada);
- as **alçadas** vêm de `config.alcadas()` — régua de governança da empresa,
  configurável por `VERTICE_ALCADAS_FILE`, **jamais derivada dos dados**;
- as **contagens** vêm da base, sempre.

`origem_do_teto` e `origem_das_alcadas` acompanham a resposta justamente para a
síntese não apresentar régua como apuração. Alçada inventada parece alçada de
verdade — é o pior caso possível deste bloco.

`pedidos_acima_do_teto` ainda mede dois sinais de contorno: concentração logo
**abaixo** do teto (desconto fatiado para não acionar a aprovação) e pedidos que
somam desconto alto a margem negativa. Os dois saem rotulados como **indício**,
não prova: a base não registra aprovador, justificativa nem data de aprovação.

---

## Cobertura de dados: a pergunta se sustenta?

O case planta perguntas que *soam* respondíveis e encontram até uma coluna com o
nome certo — `clientes.ltv_acumulado`, `clientes.segmento_rfm` (que inclui o
rótulo "Churn"), `marketing.cac`. Responder por existir a coluna é o erro caro.

`cobertura_de_dados(assunto)` faz duas checagens determinísticas antes de
qualquer número: **esquema** (o campo existe?) e **reconciliação** (ele bate com
a venda observada?). O veredito sai como `nao_respondivel`,
`parcial_com_ressalva` ou `respondivel`, sempre com a medida que o sustenta e o
que seria preciso coletar.

A reconciliação é o que separa isto de uma lista de desculpas escrita à mão:

| Medida | Valor |
|---|---|
| clientes no cadastro | 15.000 |
| clientes com pedido na base | **331 (2,21%)** |
| correlação `ltv_acumulado` × receita observada | **−0,0165** |
| correlação `total_pedidos_historico` × pedidos observados | **−0,0167** |
| "Tamanho errado" em categoria sem grade de tamanho | **684 registros** |

Assuntos cobertos: `cac`, `ltv`, `churn`, `segmentos_de_clientes`,
`oferta_individual`, `classificacao_de_tickets`, `causa_de_devolucao`,
`previsao_de_devolucao`. O roteador manda essas perguntas para cá **antes** da
detecção de pergunta aberta — no ReAct, é justamente onde o modelo acha o campo.

---

## O agente

**Loop ReAct.** O agente recebe a pergunta, decide qual ferramenta chamar,
lê o resultado e decide a próxima — sem roteiro fixo. Termina quando tem
evidência suficiente, ou é forçado a sintetizar ao atingir `VERTICE_MAX_ITER`.

**Formato final obrigatório**, sempre nesta ordem e sem seções extras:
`FATO:` / `INFERÊNCIA:` / `RECOMENDAÇÃO:` / `FORÇA DA EVIDÊNCIA:`.
`validar_formato_final()` verifica presença e ordem; `normalizar_formato_final()`
reescreve os cabeçalhos na forma canônica.

A validação é **tolerante ao que o modelo realmente escreve** — `**FATO:**`,
`## FATO`, `- FATO:`, `INFERENCIA` sem acento — e a normalização entrega sempre
`FATO: `, sem markdown. Isso não é cosmético: a primeira versão exigia o
cabeçalho cru e, em produção, rejeitou uma resposta correta em markdown, jogando
fora a investigação inteira e caindo no fallback.

**Roteamento por palavra-chave.** No primeiro turno, o agente recebe uma lista
curta (máx. 4) de ferramentas que costumam responder perguntas daquele tipo. É
apenas uma pista — a escolha continua sendo dele, e o catálogo completo segue
disponível. Existe porque, com dezenas de ferramentas num prompt longo, o modelo pequeno
perdia o catálogo e desistia da pergunta; cada correção depois do fato custa uma
ida ao gateway (~30s), então evitar o erro vale mais que corrigi-lo.

**Ferramenta citada e não chamada.** Se a resposta final menciona uma ferramenta
do registro que nunca foi executada ("sem o resultado de `X` não é possível"),
o agente cobra a execução **entregando o schema de parâmetros da ferramenta**.
Em produção o modelo identificou a ferramenta certa pelo nome e mesmo assim
desistiu sem nunca emitir uma `AÇÃO`.

**Rastreabilidade numérica (a garantia central).** Antes de aceitar qualquer
resposta final, `verificar_numeros()` extrai todo número com 4+ dígitos
significativos e confronta com os números que realmente apareceram nas
observações de ferramenta daquela investigação. Se algum não bate, o agente cobra
a correção (nomeando os valores e a ferramenta certa); se o modelo insistir, a
resposta é **bloqueada** e substituída por um aviso que não publica os números.

Isso não é redundância do system prompt: em produção o modelo multiplicou
receita bruta por 30%, apresentou o produto como apuração, e o número estava
errado por ~44x (aplicou o desconto sobre a base inteira em vez do recorte
Marketplace-novembro). Pedir "não calcule" no prompt não impede o modelo de
calcular — só a verificação impede.

A verificação tolera arredondamento, fração apresentada como percentual
(0,4757 → 47,57%), ambiguidade de separador (`1.234` como milhar ou decimal),
a magnitude de um valor negativo citada sem o sinal (ferramenta devolve
`variacao_pp: -22.17`, texto diz "caiu 22,17 pontos" — a direção já vem do
verbo, o sinal é redundante), anos e números vindos da própria pergunta, para
não bloquear resposta legítima. A tolerância de magnitude corrigiu um falso
positivo real: antes dela, "caiu 22,17 pontos" era bloqueado por não bater com
o `-22.17` da ferramenta, mesmo o número sendo correto.

**Estatística anunciada pelo nome escapa do piso de dígitos.** Um número
apresentado como resultado de teste — `R² =`, `F =`, `p-valor =`, `eta² =` — é
apuração por definição, então é conferido mesmo com poucos dígitos. O rótulo é
procurado numa janela **sem o ruído de notação** (`$ \ ^ { } * ` e parênteses),
porque o modelo escreve em LaTeX: `$R^2 = 0{,}85$` precisa casar com o mesmo
rótulo que `R²`. O limiar convencional (`p < 0,001`) continua isento — é limite
declarado, não medida.

**Notação científica é lida.** `p-valor = $3{,}09 \times 10^{-19}$` é comparado
por dígitos significativos com o `3,0871979…e-19` da ferramenta. Dois detalhes
que custaram caro e viraram teste: a forma com "e" precisa vir **colada** ao
número (senão "entre 2023 e 2024" vira 2023×10²⁰²), e o valor é montado pela
string (`3.09 * 10**-19` dá `3.0899999999999995e-19`, e a comparação exata
reprovava um número certo).

**Número que o modelo digitou como parâmetro não vira apuração.**
`classificar_evidencia` devolve `p_valor`, `r2` e `n` exatamente como recebeu. O
modelo descobriu o atalho: chamou `classificar_evidencia(p_valor=0,0001)` sem
nenhum teste ter produzido esse valor, a ferramenta ecoou, e a verificação
aprovou — o número existia numa observação. Ao montar o conjunto rastreável, o
que entrou como **argumento** de uma chamada sai do resultado **dela**; se outra
ferramenta calculou o mesmo valor de verdade, ele continua rastreável por
aquela.

**Limite conhecido:** números com menos de 4 dígitos significativos e que não
são estatística nomeada não são verificados (de propósito — abaixo disso a
maioria é retórica: "30%", "60%").
Isso significa que uma variação percentual pequena que o modelo calcule sobre
dois números já verificados (ex.: "-1,35% em termos relativos" a partir de
49,32% e 49,99%) pode passar sem checagem — e, na prática, pode sair com erro
de arredondamento (observado: modelo escreveu -1,35%, o correto é -1,34%).
O impacto é baixo (a métrica relevante, em pp e em R$, vem sempre de
ferramenta), mas é honesto registrar que a garantia não é absoluta abaixo
desse tamanho de número.

**Limite de categoria diferente — correção de raciocínio, não de número.**
Observado em produção: um modelo comparou dois valores reais, ambos vindos de
ferramenta (índice sazonal de novembro = 1,953; de maio = 1,646), e escreveu
"novembro é o 2º maior pico, depois de maio" — quando 1,953 > 1,646, então
novembro é o 1º, não o 2º. Nenhum número foi inventado (os dois vieram de
`indice_sazonalidade`); o erro é de **comparação/ranking** entre números
corretos. `verificar_numeros()` confere se um número apareceu em algum
resultado de ferramenta — não confere se a relação entre dois números
corretos (qual é maior, qual é o mínimo de um conjunto) foi descrita certo.
Esse tipo de erro não tem guarda de código genérica sem arriscar bloquear
respostas legítimas; modelos maiores (sonnet/opus) erram menos nisso que
haiku, mas o risco não é zero. Leia comparações e rankings da resposta com
atenção — os números individuais são confiáveis, a relação entre eles nem
sempre.

**Limite de atribuição — o p-valor certo na conclusão errada.** Observado: uma
recomendação de teto de desconto encerrou com "FORÇA: FORTE, p-valor = 0,0" —
e o simulador não produz p-valor nenhum. O número existia (veio de uma ANOVA da
mesma investigação); a **atribuição** àquela conclusão é que estava errada. A
verificação confere de onde o dígito veio, não a qual afirmação ele pertence, e
não há regra determinística para isso que não gere falso positivo. É limitação
conhecida e declarada.

### O histórico deste guardrail

Vale registrar porque é o argumento a favor da arquitetura, não contra: o
guardrail cedeu **cinco vezes**, e as cinco foram encontradas rodando perguntas
de verdade, não pelos 800+ testes.

| # | Falha | Efeito | Correção |
|---|---|---|---|
| 1 | separador de milhar por espaço (`R$ 34 973,55`) | resposta **correta** bloqueada | o agrupamento por espaço entrou no regex |
| 2 | partes do número aceitas como alternativas | tabela **inteiramente inventada** aprovada (o "0" casava com qualquer coisa) | todas as partes precisam bater |
| 3 | piso absoluto de tolerância (0,02) | **nenhum p-valor** era conferido — qualquer valor < 0,02 casava com o 0.0 presente em todo resultado | tolerância proporcional abaixo de 1 |
| 4 | piso de dígitos + LaTeX | `R² = 0,85` inventado, publicado **três vezes** | estatística nomeada é conferida, com o rótulo lido sem ruído de notação |
| 5 | eco de parâmetro | p-valor inventado **lavado** por dentro de `classificar_evidencia` | argumento de uma chamada sai do resultado dela |

Um falso positivo do caminho oposto também entrou como teste: o ponto final da
frase era engolido pelo número (`"…é 0.0127."` casava como `0.0127.`, cuja única
leitura era 127), e um V de Cramér vindo direto do qui-quadrado foi acusado de
inventado — bloqueando uma resposta correta.

**Cobrança por investigar.** Se o modelo tenta responder usando apenas o retrato
consolidado da pré-semeadura, sem chamar nenhuma ferramenta dirigida à pergunta,
o loop cobra uma vez ("o consolidado é o ponto de partida, não a resposta") e só
aceita a resposta seguinte. A cobrança é única, para o loop sempre terminar.

**Guia de investigação:** MECE da margem
(Receita − Desconto − Custo do produto − Frete − Devolução), com sazonalidade
consultada antes de comparar períodos.

### Por que ReAct por texto e não `tools=` nativo

O gateway EloAgents não se mostrou confiável com o parâmetro `tools=` da API de
chat completions: em testes o modelo ignorou o schema enviado e, ao forçar
`tool_choice="required"`, chamou ferramentas de plataforma inexistentes no nosso
registro (ex.: `view_skill`). O padrão é, portanto, **ReAct por texto**: as
ferramentas são descritas no system prompt, o modelo responde

```
PENSAMENTO: <por que esta ferramenta agora>
AÇÃO: nome_da_ferramenta
PARÂMETROS: {"chave": "valor"}
```

e `react.extrair_acao()` interpreta com regex e executa localmente. Funciona
independentemente de suporte a function calling.

O modo nativo continua disponível (`--modo nativo`) e **valida toda chamada
contra o registro**: uma ferramenta de plataforma vira erro explícito devolvido
ao modelo, nunca um número inventado.

O parser tolera as variações reais de saída de LLM: `**AÇÃO:**` com markdown,
`ACAO` sem acento, minúsculas, aspas simples, vírgula sobrando no JSON, nome
entre crases. E **não** confunde a resposta final com uma ação, mesmo quando ela
cita nomes de ferramentas.

O regex é **ancorado em início de linha e exige os dois-pontos**, e a classe do
nome é explicitamente `[A-Za-z_]`. Isso não é preciosismo: a primeira versão,
com dois-pontos opcional e `[a-z_]` sob `re.IGNORECASE` (que casa maiúsculas),
lia a prosa `"avaliar a ação dos descontos"` como uma chamada à ferramenta `dos`,
e `"AÇÃO: N/A"` como a ferramenta `N`. Em produção isso transformou uma recusa
correta do modelo ("não há ferramenta para isso") em quatro chamadas fantasma que
queimaram o limite de iterações. Há testes de regressão para os dois casos.

Declarações de não-ação (`N/A`, `nenhuma`, `Não aplicável`) são reconhecidas como
"sem ferramenta a chamar", não como nome de ferramenta.

### Dois cuidados que o protocolo textual exige

1. **Pré-semeadura.** Antes do primeiro turno do modelo, o loop chama
   `margem_consolidada` e entrega o resultado já na primeira mensagem. Sem isso o
   modelo trata "Vértice Retail" como empresa desconhecida e pede dados ao
   usuário em vez de investigar.
2. **Etiquetas de papel.** O gateway só tem os papéis `user` e `assistant`, sem
   papel dedicado a resultado de ferramenta. Cada mensagem é prefixada com
   `[PERGUNTA DO USUÁRIO]`, `[RESULTADO DE FERRAMENTA — ...]`,
   `[ERRO DE FERRAMENTA — ...]` ou `[INSTRUÇÃO DO SISTEMA]`, para o modelo não
   confundir a origem em conversas de várias perguntas.

### Robustez

| Situação | Comportamento |
|---|---|
| `AÇÃO: Chamar X e Y` (verbo antes do nome) | parser procura, em ordem, a mesma linha, o bloco `PENSAMENTO` (último nome citado) e o resto do texto após a AÇÃO — em vez de tratar "Chamar"/"Refazer" como ferramenta |
| Ferramenta inexistente | erro volta ao modelo com sugestão por similaridade (`difflib`), não com o catálogo inteiro |
| Mesma chamada falha 2x | aviso explícito de "não repita" junto do erro |
| Mesma chamada falha 3x | investigação interrompida e síntese forçada, em vez de queimar as iterações |
| Nenhuma ferramenta serve | o prompt manda responder no formato final dizendo o que não é apurável, em vez de inventar ferramenta |
| Parâmetro obrigatório ausente/errado | erro vem com o **exemplo pronto de chamada**, já na 1ª falha — e com **valores reais pré-preenchidos** (%, canal, mês) extraídos da própria pergunta do usuário, não `<placeholder>` para o modelo compor |
| `FORÇA DA EVIDÊNCIA` fora do vocabulário (ex.: "Alta"/"NULA" em vez de FORTE/MODERADA/FRACA) | cobrada 1x, com instrução de chamar `classificar_evidencia` se não souber qual usar; se persistir, **normalizada para FRACA deterministicamente** (nota auditável), em vez de publicar a palavra errada — o conteúdo da resposta não é descartado, só a classificação é corrigida |
| `FORTE`/`MODERADA` sem nenhum teste estatístico chamado na investigação | cobrada 1x pedindo o teste real; se persistir, **rebaixada para `FRACA` deterministicamente**, com nota auditável no texto — confiança sem teste é tratada como infundada, não cosmética |
| Parâmetro com valor inválido (regra de negócio) | erro nomeia o parâmetro e lista os valores aceitos |
| JSON malformado | parser tenta reparo (aspas simples, vírgula sobrando) |
| Modelo pede dados ao usuário | detectado e forçado à síntese |
| Limite de iterações | síntese forçada, com 2ª tentativa mais dura se o formato falhar |
| Cita ferramenta sem executá-la | cobrança com o schema de parâmetros dela |
| Seção repetida após "FORÇA DA EVIDÊNCIA" | cortada por `normalizar_formato_final()` — o contrato é "sem texto após a última" |
| `comparar_periodos` com período em formato não suportado (ex.: lista com vírgula pra "excluir um mês") | rejeitado com `ValueError` explícito — antes era aceito em silêncio como comparação de string e calculava um intervalo diferente do pedido, sem erro |
| Modelo devolve resposta em branco (nem AÇÃO, nem FATO) | nunca ecoada como `content` vazio na próxima chamada — o gateway EloAgents/Bedrock rejeita mensagem com conteúdo vazio (400, "Member must not be null"); vira um marcador de texto não-vazio |
| Número não rastreável a ferramenta | cobrança nomeando os valores; 2 falhas → resposta bloqueada |
| Resposta em markdown | aceita e normalizada para o cabeçalho canônico |
| Resposta só com a semente | cobrada uma vez antes de ser aceita |
| Modelo nunca sintetiza | fallback auditável nas 4 seções, apontando o trace, **sem inventar conclusão**; a resposta rejeitada fica no trace para diagnóstico |
| Resultado gigante | truncado em 6.000 caracteres antes de ir ao modelo |

### Trace

Cada investigação produz um `Trace` serializável em JSON, com passos tipados
(`pergunta`, `pensamento`, `acao`, `observacao`, `erro`, `resposta_final`),
timestamp, duração por ferramenta e os parâmetros de cada chamada.

```python
tr = agente.investigar("...")
tr.to_dict()          # dict pronto para API/painel
tr.salvar("traces")   # traces/trace_<id>.json
print(tr.resumo_terminal())
```

A estrutura foi desenhada para ser consumida por um painel visual — cada passo é
um registro plano com `indice`, `tipo`, `ferramenta`, `parametros`, `conteudo`,
`duracao_ms` e `iteracao`. O painel em si está fora do escopo deste projeto.

---

## Premissas de dados

Todas as decisões de filtro e exclusão estão em **[PREMISSAS.md](PREMISSAS.md)**,
e o resumo executável correspondente está em `resumo_tratamento()` (devolvido no
campo `base` de `margem_consolidada`). Em resumo:

1. Só `status_pagamento == 'Aprovado'` conta como receita (11,73% da receita
   reportada nunca foi recebida).
2. `marketing.receita_gerada` é 17,4x a receita real por atribuição sobreposta —
   ROAS só como ranking relativo, nunca como R$.
3. `margem% + desconto% + custo% + frete% = 100%` é identidade contábil: R²≈1
   numa regressão é sanidade da base, **não causa raiz**.
4. Desconto x volume é **correlação**, não causalidade — exige teste A/B.
5. Toda simulação assume **volume constante**, declarado no retorno.
6. Base vai até um **mês parcial** (2024-01-26); sazonalidade calculada sobre
   pedidos/dia.
7. `margem_contribuicao` é **anterior à devolução** — devolução é vazamento
   adicional.
8. Os campos de cliente (`ltv_acumulado`, `total_pedidos_historico`,
   `segmento_rfm`) **não reconciliam** com a transação: a base de pedidos cobre
   2,21% do cadastro e a correlação com a receita observada é ≈ 0. Pergunta de
   LTV, CAC, churn ou segmento passa por `cobertura_de_dados` antes de qualquer
   número.
9. O motivo de devolução é **declarado, não apurado**: há 684 registros de
   "Tamanho errado" em categorias sem grade de tamanho, e 47,9% dos pedidos
   devolvidos por "Atraso na entrega" foram entregues dentro da mediana da
   base. Motivo nunca é tratado como causa.

---

## Testes

```bash
python -m pytest          # 925 passando, 11 pulados
```

| Arquivo | Testes | O que cobre |
|---|---|---|
| `test_perguntas_negocio.py` | 401 | as 95 perguntas do case, de ponta a ponta |
| `test_agente.py` | 152 | parser, loop, guardrails, trace, fallbacks |
| `test_motor.py` | 46 | identidade contábil, aditividade, achados de negócio |
| `test_api.py` | 46 | rotas HTTP e contratos do painel |
| `test_router.py` | 38 | roteamento de intenção e extração de parâmetros |
| `test_verificacao.py` | 38 | rastreabilidade numérica e os cinco buracos fechados |
| `test_aceite_livro_de_numeros.py` | 35 | o motor reproduz o Livro de Números, ID a ID |
| `test_auditoria.py` | 32 | checagens de qualidade de dado |
| `test_relatorio_e_card.py` | 27 | relatório determinístico e card do painel |
| `test_politica.py` | 26 | fluxo da proposta, segregação de funções, histórico |
| `test_filtros.py` | 23 | mês/canal/categoria escritos em português |
| `test_roteamento_do_deck.py` | 18 | as perguntas do deck caem na ferramenta certa |
| `test_prompts.py` | 17 | system prompt, catálogo, sugestões |
| `test_experimento.py` | 16 | teste A/B: atribuição, poder, regra de parada, A/A |
| `test_integridade_dados.py` | 12 | integridade das cinco bases |
| `test_config.py` | 7 | leitura de ambiente sem congelar no import |

A suíte é **hermética**: uma fixture `autouse` limpa toda `VERTICE_*` antes de
cada teste e aponta o arquivo de políticas para um diretório temporário. Isso
não é preciosismo — dois testes já passaram aqui e falharam na máquina de quem
tinha `VERTICE_TOOL_MODE=nativo` exportado no shell, com um erro sem relação
nenhuma com o que a pessoa tinha acabado de mexer.

Cobrem, entre outros:

- **Identidade contábil** fechando em ~100% (erro < 1e-6 em 24.454 pedidos).
- **Aditividade**: margem por canal / categoria / mês / método de pagamento soma
  de volta ao consolidado.
- **Achados de negócio**: Marketplace tem margem menor com significância
  estatística; frete é o componente mais disperso entre canais; desconto não
  compra volume incremental; desconto alto concentra o déficit.
- **Armadilhas**: a regressão da identidade dispara alerta; a inflação do
  marketing é sinalizada; o mês parcial é detectado.
- **Agente**: parser em 6 formatos de saída, recuperação de erro, limite de
  iterações, fallback de formato, modo nativo rejeitando ferramenta de
  plataforma, trace serializável.
- **Perguntas reais do case**: intenção, ferramenta, parâmetros, execução e
  rastreabilidade numérica para cada uma das 95 — incluindo os nove verbos de
  teto contra os oito de aplicação, o caso obrigatório de Moda no Email
  Marketing, e a checagem cruzada de que `pedidos_acima_do_teto` e
  `cenarios_reducao_desconto` concordam no mesmo recorte.

---

## Auditoria das 95 perguntas do case

`docs/AUDITORIA_PERGUNTAS.md` é gerado pela execução real, nunca escrito à mão:

```bash
python -m scripts.auditoria_perguntas > docs/AUDITORIA_PERGUNTAS.md
```

Cada linha é uma passagem pelo roteador e pelo motor, então não existe versão
bonita do relatório que já não corresponda ao comportamento. Rode depois de
mexer no roteamento: se uma pergunta trocar de rota, o diff mostra qual.

| Veredito | Perguntas | Significado |
|---|---|---|
| PASS com ressalva | 47 | tudo certo, e a ferramenta já devolve a premissa/limitação que a resposta precisa repetir |
| PASS | 20 | intenção, ferramenta, parâmetros e execução corretos |
| ReAct | 16 | investigação aberta — sem ferramenta única, por decisão |
| RECUSA MEDIDA | 8 | sem lastro nos dados; a recusa vem com a medida que a sustenta |
| RESSALVA FORTE | 3 | respondível só parcialmente, com a limitação nomeada |
| PEDE PARÂMETRO | 1 | falta um valor que a pergunta não traz — o agente pergunta em vez de chutar |

Na primeira passada, antes das correções, o placar era outro: 34 perguntas
caíam em `PERGUNTA_COMPLEXA` (o modelo respondia de cabeça), 2 quebravam com
`TypeError` e o bloco inteiro de política e alçadas — doze perguntas — não
tinha ferramenta nenhuma.

---

## Exemplo de saída real

Pergunta: *"Por que a margem do Marketplace é menor que a dos outros canais e
quanto isso custa?"*

Ferramentas chamadas em sequência pelo agente:
`margem_consolidada` (semente) → `margem_por_dimensao(canal)` →
`dispersao_componentes_entre_canais` → `politica_frete_por_canal` →
`teste_t_welch` → `custo_assimetria_frete`.

> **FATO:** o Marketplace tem margem de 47,57% contra 50,17%-51,60% dos demais
> canais, e concede frete grátis em 0,0% dos 5.315 pedidos, contra 79,86% nos
> outros canais. O frete consome 4,53% da receita do canal, contra 0,38%-1,02%
> nos demais. Entre os três componentes de custo, o frete é o mais disperso
> entre canais (CV=1,0081), contra 0,0646 do desconto e 0,0033 do custo de
> produto. O teste t de Welch confirma a diferença (t=-15,72; p=6,2e-55;
> n=24.454; IC95 da diferença -4,76pp a -3,70pp). O frete evitável é de
> R$ 135.256,57 — 78,26% do frete pago pelo canal.
>
> **INFERÊNCIA:** a diferença não vem de desconto nem de custo de produto —
> esses são praticamente uniformes entre canais. Vem de assimetria de política
> de frete. O d de Cohen de -0,2376 indica efeito pequeno no grão do pedido, mas
> o efeito agregado é material porque atinge todos os 5.315 pedidos do canal.
>
> **RECOMENDAÇÃO:** equalizar a política de frete do Marketplace à dos demais
> canais, recuperando R$ 135.256,57 e levando a margem do canal de 47,57% para
> 51,12%. PREMISSA: a assimetria é de política e não de imposição contratual —
> verificar o contrato antes de acionar.
>
> **FORÇA DA EVIDÊNCIA:** FORTE. Critério: p<0,001 com n>1000. Limitação: o
> tamanho de efeito no grão do pedido é pequeno e o frete evitável é
> contrafactual por faixa de ticket, não resultado de experimento.
