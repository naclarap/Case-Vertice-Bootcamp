# Vértice Retail — Design System

**Vértice Retail** é um varejista fictício usado como case do **AI Consulting Lab (Bootcamp EloGroup)**: uma consultoria simulada de dados que precisa entregar duas peças a um comitê executivo — um **pitch de 10 minutos** e um **painel de acompanhamento de margem** — cobrindo os três eixos do case: **descontos**, **frete de marketplace** e **devoluções**.

A marca visual não é inventada: ela deriva da linguagem visual da **EloGroup**, fornecida como referência. Este design system traduz essa linguagem (indigo único sobre off-white, hairlines em vez de sombras, eyebrows em mono maiúsculo, números grandes com legenda mono) para as duas superfícies do case.

## Fontes recebidas

Sete screenshots, em `uploads/` — todo o sistema foi extraído deles:

| Arquivo | Conteúdo |
| --- | --- |
| `Captura de tela 2026-09-16 114252.png` | Hero do site EloGroup — "Somos builders.", hashtag mono, botões pill, motivo de linha geométrica |
| `Captura de tela 2026-09-16 114329.png` | Imagem full-bleed duotone azul + faixa de métricas (13 / 60+ / 200+ / 15+) com legendas mono |
| `Captura de tela 2026-09-16 114357.png` | Landing de Reforma Tributária — headline com destaque indigo, CTA mono, imagem P&B |
| `Captura de tela 2026-09-16 114425.png` | Grid de cases — pills de classificação (accent + neutro) e pares de métrica |
| `Captura de tela 2026-09-16 114453.png` | Slide "QA-first" — pill de framework, sequência 01–04 com fill lavanda progressivo, linha de resultados |
| `Captura de tela 2026-09-16 114519.png` | Slide de comparação H1/H2 — colunas espelhadas, listas numeradas em mono, callouts soft e escuro |
| `Captura de tela 2026-09-16 114545.png` | Slide de diagrama radial — círculo indigo central, nós numerados, linha de provocação no pé |

Não foram fornecidos: código-fonte, arquivo Figma, binários de fonte, arquivos de logo, imagens em alta. As consequências disso estão em **Substituições** no fim deste documento.

## Superfícies

1. **Pitch executivo** (`slides/`) — 10 slides 1280×720, um arquivo por tipo de slide.
2. **Margin Control** (`ui_kits/margin-control/`) — painel de margem com 5 telas navegáveis.

---

## CONTENT FUNDAMENTALS

**Idioma:** português do Brasil. Termos de negócio em inglês ficam em inglês quando é assim que o time fala (*marketplace*, *break-even*, *ticket médio*, *flywheel*, *supply chain*) — sem itálico, sem tradução defensiva.

**Voz:** terceira pessoa ou "nós" quando a consultoria fala de si. Nunca "você" acusatório — o cliente não é o problema, a regra é. Comparações são feitas contra metas e linhas de base, não contra pessoas.

**Casing:**
- Headlines em *sentence case*, com ponto final. "A margem não caiu. Ela vazou."
- Eyebrows, legendas de métrica, cabeçalhos de tabela e labels de formulário em MAIÚSCULAS com `--label-tracking` (0.16em), em mono.
- Rótulos de navegação em sentence case.

**A frase com um destaque.** Toda headline carrega no máximo **uma** expressão em indigo — o resto fica em tinta. É o gesto mais reconhecível da marca: "Somos **builders**.", "Acionando alavancas estratégicas no **novo ecossistema fiscal**", "A margem não caiu. **Ela vazou.**" Itálico no destaque só quando a frase gira sobre aquela palavra ("trata *só um deles*").

**Números.** Formato pt-BR: vírgula decimal, ponto de milhar (`11.865`), `R$ 4,2 mi`, `+2,4 p.p.` para pontos percentuais e `%` para taxas. Sinal explícito em variações (`+1,8 p.p.`, `-0,9 p.p.`). Número sempre acompanhado de base ("Base: 11.865 pedidos, abr–ago 2026") — a marca é afirmativa, não vaga.

**Estrutura de frase.** Afirmação primeiro, prova depois, recomendação por último. Frases curtas, verbo no presente. Parágrafo de apoio raramente passa de três linhas.

**Exemplos que valem como referência:**
- Headline de diagnóstico: "63% do vazamento está em três decisões operacionais."
- Leitura de dado: "Acima de 18%, o desconto para de comprar volume."
- Callout de resultado: "Retorno material · autofinancia o programa" (cláusulas separadas por middot)
- Eyebrow: `[ OS DOIS HORIZONTES DE IA ]` — colchetes com espaço interno, usados em cantos de slide
- Rodapé de slide: "Impacto estimado sobre a base atual de receita"

**Sem emoji.** Em nenhuma superfície. Nenhum screenshot da marca usa emoji, e o tom executivo não abre espaço para isso. Middot (`·`), travessão (`—`) e seta (`→`) fazem o trabalho de pontuação de apoio.

---

## VISUAL FOUNDATIONS

**Paleta.** Um hue de marca (indigo `--indigo-700` #1A1AC8) sobre off-white `--paper` #F6F6F4. Lavanda (#E8E7FC → #A5A2E8) é o único apoio: preenche steps, barras de base e superfícies soft. Navy `--navy-900` #0E2036 é a única superfície escura (sidebar, callout de resultado forte, slide de fechamento). Verde/vermelho/âmbar existem exclusivamente para direção de margem — nunca como decoração. Máximo de dois fundos por peça.

**Tipografia.** Uma família grotesca geométrica em três papéis: display (peso 400, `-0.022em`, line-height 1.04) para headlines; heading (600) para títulos de card e tela; body (400) em 17/15/13px. Mono espaçada em maiúsculas cobre todo label, eyebrow e legenda. Nada de peso 700 em texto corrido; ênfase vem de cor e escala.

**Números grandes.** Métricas usam a face de display com `-0.03em` e legenda mono por baixo, em até 22 caracteres. Em faixa, quatro por linha no máximo, separados por hairlines verticais.

**Fundos.** Cor plana, sempre. Sem gradiente de fundo, sem textura, sem padrão repetido. A profundidade vem de três valores de superfície: página off-white, card branco, sunken cinza. Imagens, quando existem, são full-bleed e tratadas: P&B de alto contraste ou duotone indigo (as duas únicas variações vistas na marca) — nunca foto colorida crua, nunca foto atrás de texto sem tratamento.

**Motivo geométrico.** Formas de raio muito grande (200–420px) desenhadas apenas em contorno de 1px, sangrando pelas bordas atrás da headline. Nunca preenchidas, nunca em indigo, nunca acima do texto.

**Estrutura por hairline.** A linha de 1px (`--line-soft` #E3E3DF) é o principal elemento estrutural: separa colunas, delimita cards, forma tabelas e fecha o pé de cada slide. Sombras existem no sistema (`--shadow-1/2/3`) mas só aparecem em card clicável no hover e em overlay. Nada de sombra estática.

**Cards.** Fundo branco, borda hairline, raio 10px, padding 24px. Sem borda colorida à esquerda, sem cabeçalho colorido. Variações: sunken (cinza, sem borda), accent (lavanda claro com borda `--line-accent`), dark (navy).

**Raios.** 3 / 6 / 10 / 16 / 24 / pill. Controles de formulário 6px, cards 10px, botões e pills sempre `--radius-pill`.

**Transparência e blur.** Praticamente ausentes. A única transparência do sistema é o realce do item ativo na sidebar navy (`rgba(255,255,255,.10)`) e os hairlines sobre escuro (`rgba(255,255,255,.18)`). Nenhum `backdrop-filter` — texto sempre em opacidade cheia, para manter contraste em projeção.

**Animação.** Discreta e curta. Controles: 120ms com `cubic-bezier(.2,.6,.2,1)` em cor e borda. Revelação de dado (barras, progress): 420ms `ease-out` sobre largura/altura. Sem bounce, sem escala, sem parallax, sem entrada de slide animada.

**Hover.** Botão primário escurece (`--indigo-800`); secundário ganha borda `--ink-900` e fundo branco; item de lista/sidebar ganha realce sutil; card clicável recebe `--shadow-2`. Nunca opacidade como hover.

**Press.** Indigo mais escuro (`--indigo-900`) + `translateY(1px)`. Sem redução de escala.

**Foco.** Borda indigo + anel de 3px (`--shadow-focus`). Nunca outline padrão do navegador.

**Layout.** Painel: sidebar fixa de 248px (sticky, altura total), topbar de 64px, conteúdo em grid de 8/16/24px. Slides: canvas fixo de 1280×720 com padding de 64px, wordmark no topo à esquerda, tag em colchetes no topo à direita, rodapé hairline com contexto à esquerda e número à direita. Texto de apoio limitado a ~62ch.

**Contraste.** Tinta cheia sobre fundo claro; em navy, texto branco e apoio `--text-on-dark-muted` #A9B7C6. Nenhum texto em cor "esmaecida" por alpha.

---

## ICONOGRAPHY

Nenhum ícone, sprite ou fonte de ícone foi fornecido — os screenshots mostram apenas glifos de linha fina genéricos (seta, chevron, chat) e nenhum asset extraível.

**Substituição declarada:** usamos **Lucide** (traço 2px, terminais arredondados) via CDN — `https://unpkg.com/lucide-static@0.452.0/icons/<slug>.svg` — sempre através do componente `Icon`, que aplica o SVG como máscara CSS para o glifo herdar `currentColor`. É a correspondência mais próxima do peso de linha visto na marca. **Se você tiver o set real da EloGroup/Vértice, envie os SVGs: trocamos o `BASE` de `Icon.jsx` e nada mais muda.**

Regras de uso:
- Tamanhos: 12 (dentro de pill), 14 (em botão e linha de tabela), 16 (padrão), 18–20 (destaque em card).
- Ícone nunca aparece sozinho como decoração; sempre acompanha label, KPI ou ação.
- Um ícone por KPI, no canto superior direito, em `--text-faint`.
- Slugs em uso: `arrow-right`, `arrow-up-right`, `arrow-down-right`, `chevron-down`, `percent`, `tag`, `truck`, `package-x`, `layout-dashboard`, `list-checks`, `download`, `search`, `sliders-horizontal`, `trending-up`, `trending-down`, `alert-triangle`, `pie-chart`, `receipt`, `banknote`, `focus`, `check`, `save`.
- **Sem emoji** e sem caractere unicode fazendo papel de ícone. Middot, travessão e seta são pontuação, não iconografia.
- Não há logo. Onde uma marca gráfica iria, o sistema escreve **Vértice** na face de display (peso 500/600, `-0.03em`) — ver o card "Wordmark (type only)". O logo da EloGroup aparece nos screenshots e **não foi reconstruído**, por ser marca de terceiro.

---

## Componentes

Nenhuma biblioteca de componentes foi fornecida (só screenshots), então o inventário abaixo foi autorado do zero, dimensionado para as duas superfícies do case.

**`components/core/`** — `Button`, `IconButton`, `Icon`, `Eyebrow`, `Divider`
**`components/display/`** — `Card`, `SectionHeader`, `Badge`, `StepCard`, `ResultCallout`, `QuoteBlock`
**`components/data/`** — `KpiCard`, `MetricFigure`, `TrendPill`, `DataTable`, `ProgressBar`
**`components/forms/`** — `Input`, `Select`, `SegmentedControl`, `Switch`
**`components/navigation/`** — `SideNav`, `Tabs`
**`components/charts/`** — `WaterfallChart`, `BarChart`
**`components/frameworks/`** — `FrameworkFlow`, `PhaseTimeline`, `Roadmap`, `FlywheelDiagram`, `ComparisonColumns`

Cada diretório tem `<Name>.jsx`, `<Name>.d.ts`, `<Name>.prompt.md` e um card de vitrine. Consumo: `const { KpiCard } = window.VRticeRetailDesignSystem_247525` depois de carregar `_ds_bundle.js`.

**Adições intencionais:** `Icon` (wrapper para o set substituto), `WaterfallChart` e `BarChart` (o case exige decomposição de margem e não havia gráfico na referência — foram construídos com os mesmos hairlines e a mesma paleta), `StepCard` e `ResultCallout` (derivados diretamente dos slides "QA-first" e "H1/H2"), `FrameworkFlow`, `PhaseTimeline`, `Roadmap`, `FlywheelDiagram` e `ComparisonColumns` (grupo `frameworks` — diagramas de processo/plano recorrentes no case, no motivo do vértice e no acento cobre).

## Índice de arquivos

| Caminho | O que é |
| --- | --- |
| `styles.css` | Entrada global — apenas `@import` |
| `tokens/colors.css` | Base + aliases semânticos de cor |
| `tokens/typography.css` | Famílias, escalas, tracking |
| `tokens/spacing.css` | Escala de 4px e medidas de layout |
| `tokens/shape.css` | Raios, bordas, sombras |
| `tokens/motion.css` | Easings e durações |
| `tokens/fonts.css` | Carregamento das fontes (substitutas) |
| `tokens/base.css` | Reset mínimo, links, seleção, `.eyebrow` |
| `guidelines/*.card.html` | 19 cards de fundação (Colors, Type, Spacing, Brand) |
| `components/<grupo>/` | Primitivas + contratos + cards |
| `ui_kits/margin-control/` | Painel Margin Control (5 telas) — ver README do diretório |
| `slides/` | 10 slides do pitch + `slide.css` |
| `thumbnail.html` | Tile do design system |
| `SKILL.md` | Empacotamento como Agent Skill |

## Substituições (pendências para o usuário)

1. **Fontes.** Os binários da face original não foram enviados. Em uso: **Schibsted Grotesk** (display/body) e **IBM Plex Mono** (labels), via Google Fonts em `tokens/fonts.css`. A referência aparenta ser uma grotesca proprietária da classe Aeonik / Neue Haas Grotesk Display, com uma mono espaçada de apoio. **Envie os arquivos `.woff2` e trocamos por `@font-face` real** — só `tokens/fonts.css` e `--font-display`/`--font-mono` mudam.
2. **Ícones.** Lucide via CDN, no lugar do set real (ver ICONOGRAPHY).
3. **Logo.** Ausente por decisão: a marca dos screenshots é da EloGroup e não foi reconstruída. Wordmark tipográfico no lugar.
4. **Imagens.** Não há imagem de marca em `assets/` — os screenshots não são assets licenciáveis. Onde a linguagem pede foto full-bleed (P&B de alto contraste ou duotone indigo), as peças deixam o espaço vazio em vez de improvisar. **Envie as imagens** e elas entram nos slides de abertura e fechamento.
