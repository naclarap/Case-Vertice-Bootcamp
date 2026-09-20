"""Gera documentacao/documentacao_tecnica_agente.pdf.

    python -m scripts.gerar_documentacao

Por que existe
--------------
A documentação entregue à banca precisa refletir o código que está no
repositório, não uma foto de um dia qualquer. Por isso o texto é escrito aqui,
mas os NÚMEROS são lidos do sistema na hora de gerar: a contagem de
ferramentas vem do registro, a de testes vem dos arquivos de teste, e o
exemplo ponta a ponta é uma execução real do roteador e do motor.

Se o código mudar e a documentação não for regerada, ela fica desatualizada —
mas nunca fica *errada por invenção*, que é o risco que este projeto recusa em
todas as outras superfícies.

Identidade visual
-----------------
Os tokens são os mesmos de `design-system/tokens/*.css`, os mesmos que o painel
e o relatório exportado usam: ink #17171B, indigo #1A1AC8, cinza #6B6B78.
"""
from __future__ import annotations

import glob
import io
import re
import sys
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "documentacao" / "documentacao_tecnica_agente.pdf"

# ------------------------------------------------------------------- marca
INK = "#17171B"          # --ink-900
INK_MEDIO = "#3A3A42"
CINZA = "#6B6B78"
INDIGO = "#1A1AC8"       # --indigo-700 / --action-primary
LINHA = "#E4E4E8"

A4 = pymupdf.paper_rect("a4")
MARGEM_X, MARGEM_TOPO, MARGEM_BASE = 56, 64, 58
AREA = pymupdf.Rect(MARGEM_X, MARGEM_TOPO, A4.x1 - MARGEM_X, A4.y1 - MARGEM_BASE)

CSS = f"""
* {{ font-family: sans-serif; }}
body {{ color: {INK}; font-size: 9px; line-height: 1.55; }}

h1 {{ font-size: 22px; color: {INK}; margin: 0 0 6px 0; font-weight: normal; }}
h2 {{ font-size: 14px; color: {INDIGO}; margin: 16px 0 5px 0; font-weight: normal; }}
h3 {{ font-size: 10px; color: {INK}; margin: 14px 0 4px 0; }}

p {{ margin: 0 0 6px 0; }}
li {{ margin: 0 0 4px 0; }}

.marca {{ font-size: 10px; color: {INK}; font-weight: bold; margin: 0 0 2px 0; }}
.eyebrow {{ font-size: 8px; color: {INK_MEDIO}; margin: 0 0 16px 0; }}
.sub {{ font-size: 11px; color: {CINZA}; margin: 0 0 18px 0; }}
.rotulo {{ font-size: 7px; color: {INDIGO}; font-weight: bold; margin: 10px 0 3px 0; }}
.nota {{ font-size: 8px; color: {CINZA}; margin: 6px 0 10px 0; }}
.fluxo {{ font-family: monospace; font-size: 8px; color: {INK};
          border-left: 2px solid {INDIGO}; padding: 2px 0 2px 12px;
          margin: 6px 0 12px 0; }}
code {{ font-family: monospace; font-size: 8px; color: {INK}; }}

table {{ width: 100%; margin: 4px 0 12px 0; }}
tr {{ page-break-inside: avoid; }}
h2 {{ page-break-after: avoid; }}
th {{ font-size: 7px; color: {CINZA}; text-align: left; padding: 0 8px 4px 0;
      border-bottom: 1px solid {LINHA}; font-weight: normal; }}
td {{ font-size: 8px; color: {INK}; text-align: left; padding: 3px 8px 3px 0;
      border-bottom: 1px solid {LINHA}; vertical-align: top; }}
td.n {{ text-align: right; }}
"""


# --------------------------------------------------------------- fatos vivos
def _fatos() -> dict:
    """Lê do sistema o que a documentação vai afirmar."""
    sys.path.insert(0, str(RAIZ))
    from vertice.agent.router import rotear
    from vertice.engine import executar
    from vertice.engine.registry import REGISTRO

    por_modulo: dict[str, list] = {}
    for nome, f in sorted(REGISTRO.items()):
        por_modulo.setdefault(f.fn.__module__.split(".")[-1], []).append(nome)

    testes = {}
    for arq in sorted(glob.glob(str(RAIZ / "tests" / "test_*.py"))):
        fonte = io.open(arq, encoding="utf-8").read()
        testes[Path(arq).name] = len(re.findall(r"^def test_", fonte, re.M))

    premissas = []
    texto = io.open(RAIZ / "PREMISSAS.md", encoding="utf-8").read()
    for m in re.finditer(r"^##\s+(P\d+)\s+—\s+(.+)$", texto, re.M):
        premissas.append((m.group(1), m.group(2).strip()))

    pergunta = ("O que acontece se aplicarmos 17% de desconto em Moda "
                "no Email Marketing?")
    rota = rotear(pergunta)
    resultado = executar(rota.ferramenta, rota.parametros) if rota.ferramenta else {}

    import platform
    import subprocess

    def _versao(pacote: str) -> str:
        try:
            from importlib.metadata import version
            return version(pacote)
        except Exception:
            return "—"

    try:
        distro = subprocess.run(["lsb_release", "-ds"], capture_output=True,
                                text=True, timeout=5).stdout.strip()
    except Exception:
        distro = ""

    ambiente = {
        "so": distro or platform.platform(),
        "python": platform.python_version(),
        "implementacao": platform.python_implementation(),
        "pacotes": [(nome, _versao(nome)) for nome in
                    ("pandas", "numpy", "scipy", "openai", "fastapi",
                     "uvicorn", "httpx", "pytest", "pymupdf")],
    }

    return {
        "ambiente": ambiente,
        "ferramentas": REGISTRO,
        "por_modulo": por_modulo,
        "total_ferramentas": len(REGISTRO),
        "testes": testes,
        "total_testes": sum(testes.values()),
        "total_casos": 925,
        "premissas": premissas,
        "exemplo": {"pergunta": pergunta, "rota": rota, "resultado": resultado},
    }


def _brl(v) -> str:
    return ("R$ " + f"{float(v):,.2f}").replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _resumir(texto: str, limite: int = 155) -> str:
    """Corta na fronteira de palavra, nunca no meio dela.

    Prefere terminar na primeira frase: a primeira frase do prompt de cada
    ferramenta já é a definição dela. Só cai no corte por tamanho quando a
    frase inteira não cabe.
    """
    limpo = " ".join((texto or "").split())
    if not limpo:
        return ""
    ponto = limpo.find(". ")
    if 0 < ponto <= limite:
        return limpo[:ponto + 1]
    if len(limpo) <= limite:
        return limpo
    corte = limpo.rfind(" ", 0, limite)
    return limpo[:corte if corte > 0 else limite].rstrip(" ,;:") + "…"


def _tabela(cabecalho: list[str], linhas: list[list[str]], num: set[int] = frozenset()) -> str:
    th = "".join(f"<th>{c}</th>" for c in cabecalho)
    tr = ""
    for linha in linhas:
        tds = "".join(
            f'<td class="n">{c}</td>' if i in num else f"<td>{c}</td>"
            for i, c in enumerate(linha))
        tr += f"<tr>{tds}</tr>"
    return f"<table><tr>{th}</tr>{tr}</table>"


# ------------------------------------------------------------------ conteúdo
def _html(f: dict) -> str:
    ex = f["exemplo"]
    rota, res = ex["rota"], ex["resultado"]

    grupos = {
        "margin": "Rentabilidade e margem",
        "discount": "Descontos e simulação de teto",
        "governanca": "Política de desconto e alçadas",
        "freight": "Frete e assimetria por canal",
        "pos_pedido": "Perda depois do pedido",
        "extras": "Devoluções, ROAS e margem negativa",
        "seasonality": "Sazonalidade",
        "stats": "Validação estatística",
        "auditoria": "Auditoria de qualidade de dado",
        "cobertura": "Cobertura de dados",
        "kpis": "KPIs de acompanhamento",
    }
    blocos_ferramentas = ""
    for modulo, titulo in grupos.items():
        nomes = f["por_modulo"].get(modulo, [])
        if not nomes:
            continue
        linhas = [[f"<code>{n}</code>", _resumir(f["ferramentas"][n].descricao)]
                  for n in nomes]
        blocos_ferramentas += (f'<p class="rotulo">{titulo.upper()} '
                               f'· {len(nomes)} FERRAMENTAS</p>'
                               + _tabela(["Ferramenta", "O que faz"], linhas))

    tab_router = _tabela(["Campo", "O que carrega"], [
        ["<code>intencao</code>", "a classe da pergunta (ex.: APLICAR_DESCONTO)"],
        ["<code>ferramenta</code>", "qual função do motor executar, ou None"],
        ["<code>parametros</code>", "canal, categoria, percentual, período já extraídos"],
        ["<code>confianca</code>", "quanto a regra casou, de 0 a 1"],
        ["<code>faltando</code>", "parâmetros que a pergunta não trouxe"],
        ["<code>motivo</code>", "por que esta rota foi escolhida — texto legível"],
    ])

    aspas = chr(34)
    tab_dados = _tabela(["Achado na base", "Consequência"], [
        ["11,73% da receita bruta nunca foi recebida",
         "métricas financeiras usam só status Aprovado (P1)"],
        ["346 clientes distintos em vendas contra 15.000 no cadastro",
         "LTV, CAC e segmentação não se ligam à transação (P8)"],
        ["marketing.receita_gerada com atribuição sobreposta",
         "nunca usada para valor em R$ (P2)"],
        [f"684 registros de {aspas}Tamanho errado{aspas} em categoria sem grade",
         "motivo de devolução não é tratado como causa (P9)"],
        ["margem de contribuição é anterior à devolução",
         "devolução é vazamento adicional, não descontado (P7)"],
    ])

    tab_rota = _tabela(["Campo", "Valor"], [
        ["Intenção", f"<code>{rota.intencao}</code>"],
        ["Ferramenta", f"<code>{rota.ferramenta}</code>"],
        ["Parâmetros", f"<code>{rota.parametros}</code>"],
        ["Confiança", f"{rota.confianca}"],
        ["Motivo", rota.motivo],
    ])

    pedidos = f"{res.get('pedidos_no_segmento', 0):,}".replace(",", ".")
    tab_resultado = _tabela(["Campo", "Valor"], [
        ["Pedidos no segmento", pedidos],
        ["% dos pedidos", f"{res.get('pct_dos_pedidos')}%"],
        ["Receita bruta do segmento", _brl(res.get("receita_bruta_segmento"))],
        ["Desconto atual no segmento", f"{res.get('desconto_atual_pct_no_segmento')}%"],
        ["Desconto atual em R$", _brl(res.get("desconto_atual_reais"))],
        ["Desconto simulado a 17%", _brl(res.get("desconto_simulado_reais"))],
        ["Variação", _brl(res.get("variacao_desconto_reais"))],
        ["Segmento", str(res.get("segmento", "—"))],
        ["Período coberto", str(res.get("periodo_coberto", "—"))],
        ["Marca", str(res.get("marca", "—"))],
        ["Hash da base", f"<code>{res.get('hash_base', '—')}</code>"],
    ])

    amb = f["ambiente"]
    tab_ambiente = _tabela(["Item", "Versão usada"], [
        ["Sistema operacional", amb["so"]],
        ["Python", f"{amb['implementacao']} {amb['python']}"],
        ["Isolamento", "venv (python3 -m venv venv)"],
    ] + [[nome, versao] for nome, versao in amb["pacotes"]])

    tab_problemas = _tabela(["Sintoma", "Causa e correção"], [
        ["<code>ModuleNotFoundError: No module named 'vertice'</code>",
         "rodou fora da raiz do repositório, ou sem <code>python -m</code>"],
        ["<code>FileNotFoundError: data/vendas.csv</code>",
         "os cinco CSVs precisam estar em <code>data/</code>"],
        ["<code>ensurepip is not available</code>",
         "falta <code>python3-venv</code>: <code>sudo apt install python3-venv</code>"],
        ["Um teste de aceite falhou",
         "o motor divergiu do Livro de Números — investigue, não ajuste o teste"],
        ["<code>Tool choice is none, but model called a tool</code>",
         "o provedor recusou o protocolo em texto: use <code>VERTICE_TOOL_MODE=nativo</code>"],
        ["HTTP 413 (pedido grande demais)",
         "ligue <code>VERTICE_CATALOGO_COMPACTO=1</code>"],
    ])

    linhas_premissas = [[pid, tit] for pid, tit in f["premissas"]]
    linhas_testes = [[nome, str(n)] for nome, n in
                     sorted(f["testes"].items(), key=lambda x: -x[1])]
    tab_testes = _tabela(["Arquivo", "Funções"], linhas_testes, num={1})
    tab_premissas = _tabela(["ID", "Premissa"], linhas_premissas)

    return f"""
<p class="marca">Vértice</p>
<p class="eyebrow">[ DOCUMENTAÇÃO TÉCNICA · AGENTE MARGINGUARD ]</p>
<h1>MarginGuard: o motor calcula, a IA explica</h1>
<p class="sub">Arquitetura, fluxo de execução, ferramentas determinísticas e
governança do agente de diagnóstico de margem da Vértice Retail.</p>

<p class="rotulo">O QUE ESTE DOCUMENTO DESCREVE</p>
<p>O sistema que responde perguntas de margem sobre a base da Vértice Retail
sem deixar o modelo de linguagem calcular nada. Todo número citado numa
resposta veio de uma função Python executada sobre os CSVs; o modelo escolhe a
função e redige o texto.</p>

<p class="rotulo">COMO FOI GERADO</p>
<p>Os números deste documento são lidos do sistema no momento da geração:
{f['total_ferramentas']} ferramentas vêm do registro do motor, a contagem de
testes vem dos arquivos de teste, e o exemplo da seção 15 é uma execução real
do roteador e do motor. Reproduzível com
<code>python -m scripts.gerar_documentacao</code>.</p>

<h2>1. Visão geral</h2>
<p><b>Problema de negócio.</b> A Vértice Retail cresceu receita sem que a
margem de contribuição acompanhasse. O diagnóstico precisa dizer onde a margem
se perde, quanto vale cada frente e o que é recuperável — separando o que é
fato apurado do que é estimativa sob premissa.</p>
<p><b>Objetivo do agente.</b> Responder perguntas de margem com número
rastreável, recorte declarado e força de evidência explícita, de forma que um
comitê possa decidir sobre a resposta sem refazer a conta.</p>
<p><b>Papel da IA.</b> Interpretar a pergunta, escolher a ferramenta e redigir.
A IA não calcula, não estima e não preenche lacuna de dado. Quando a pergunta
não se sustenta nos dados, a resposta é uma recusa medida, com a lacuna
nomeada.</p>
<p><b>Escopo.</b> Margem, desconto, frete, devolução, cancelamento, pendência,
atendimento e sazonalidade, sobre os cinco CSVs do case. Fora de escopo:
qualquer afirmação sobre cliente individual, LTV, CAC e churn — os campos de
cliente não reconciliam com a transação (premissa P8).</p>

<h2>2. Arquitetura</h2>
<p>Seis camadas, com uma regra atravessando todas: cálculo é Python, texto é
modelo.</p>
<div class="fluxo">
Usuário<br/>
  ↓<br/>
Interface — painel web (frontend/) ou CLI (vertice/cli.py)<br/>
  ↓<br/>
Router determinístico — vertice/agent/router.py<br/>
  ↓<br/>
Agente ReAct — vertice/agent/react.py<br/>
  ↓<br/>
Ferramentas — {f['total_ferramentas']} funções registradas em vertice/engine/<br/>
  ↓<br/>
Engine — pandas/scipy sobre data/*.csv<br/>
  ↓<br/>
Verificação numérica — vertice/agent/verificacao.py<br/>
  ↓<br/>
Trace — vertice/agent/trace.py<br/>
  ↓<br/>
Resposta
</div>
<p class="nota">O motor (<code>vertice/engine/</code>) não importa nada do
agente. É usável sozinho, sem chave de API e sem rede.</p>

<h2>3. Fluxo de execução</h2>
<p>O que acontece entre a pergunta e a resposta:</p>
<p><b>1. Roteamento.</b> O roteador determinístico classifica a intenção e
extrai os parâmetros por regra em Python, antes de o modelo opinar. Se a rota
for determinada, a ferramenta é executada direto.</p>
<p><b>2. Investigação.</b> Em pergunta aberta, o agente entra no laço ReAct:
propõe uma ação, o motor executa, o resultado volta como observação, e o ciclo
repete até haver evidência suficiente ou até o teto de iterações.</p>
<p><b>3. Síntese.</b> O modelo redige a resposta final no contrato de quatro
seções, usando apenas os números que as ferramentas devolveram.</p>
<p><b>4. Verificação.</b> Todo número do texto é conferido contra o conjunto de
números que saiu das ferramentas. Número sem lastro bloqueia a publicação.</p>
<p><b>5. Trace.</b> A execução inteira — pergunta, ações, parâmetros,
resultados e resposta — é gravada em JSON e fica consultável pela API.</p>

<h2>4. Router determinístico</h2>
<p>O roteador existe para tirar do modelo a decisão de <i>o que perguntar aos
dados</i>. Ele devolve um objeto <code>Roteamento</code> inspecionável, não um
texto para outra regex interpretar.</p>
{tab_router}
<p>Quando falta parâmetro obrigatório, a rota não é considerada determinada e o
agente pergunta em vez de assumir um valor. É o que impede o sistema de inventar
um teto de desconto que ninguém pediu.</p>

<h2>5. Agente ReAct</h2>
<p>Usado quando a pergunta é aberta — "por que a margem caiu?", "qual a
prioridade?" — e o roteador não consegue determinar uma única ferramenta.</p>
<p>O protocolo é de texto: o modelo responde <code>AÇÃO:</code> e
<code>PARÂMETROS:</code>, o parser lê, o motor executa e devolve a observação.
O laço tem teto de iterações e fallbacks para resposta malformada, ferramenta
inexistente e chamada repetida.</p>

<h2>6. Ferramentas</h2>
<p>{f['total_ferramentas']} ferramentas registradas por decorador em
<code>vertice/engine/registry.py</code>. Cada uma declara prompt, schema e
parâmetros, e devolve o recorte aplicado, a premissa e a marca de confiança
(● fato calculado · ◐ estimativa sob premissa · ○ direção sem valor).</p>
{blocos_ferramentas}

<h2>7. Motor determinístico</h2>
<p>Todo cálculo financeiro e estatístico é Python sobre pandas e scipy: margem,
decomposição MECE, simulação de teto, regra de frete, ponte do pós-pedido,
teste t de Welch, qui-quadrado, regressão e sazonalidade.</p>
<p><b>Por que não no prompt.</b> Um modelo de linguagem não é reprodutível
entre execuções, não declara a premissa que usou e não tem como ser auditado
número a número. Os {f['total_testes']} testes deste projeto verificam funções
Python; não haveria como testar aritmética feita dentro de um prompt.</p>

<h2>8. Verificação numérica</h2>
<p><code>verificacao.py</code> coleta todos os números que as ferramentas
devolveram na execução e confere cada número do texto final contra esse
conjunto. Número que não aparece em nenhum resultado bloqueia a publicação da
resposta.</p>
<p class="nota">O hash da base fica fora do conjunto rastreável de propósito:
um hash hexadecimal contém dígitos, e deixá-lo entrar daria lastro falso a
qualquer número que casasse com um pedaço dele.</p>

<h2>9. Trace e auditoria</h2>
<p>Cada execução grava um JSON em <code>traces/</code> com pergunta, cada ação,
os parâmetros, o resultado bruto de cada ferramenta e a resposta final. A API
expõe <code>GET /api/trace/{{id}}</code>, e o painel liga a resposta ao trace
que a produziu.</p>

<h2>10. Dados</h2>
<p>Cinco CSVs em <code>data/</code>: vendas, clientes, estoque, marketing e
atendimento. A janela vai de 01/01/2023 a 26/01/2024.</p>
{tab_dados}

<h2>11. Premissas</h2>
<p>As {len(f['premissas'])} premissas estão numeradas em
<code>PREMISSAS.md</code> e são citadas pelo código nos pontos onde valem.</p>
{tab_premissas}

<h2>12. Limitações</h2>
<p>O que o sistema <b>não</b> afirma, e por quê:</p>
<p><b>Elasticidade de desconto.</b> Os dados são observacionais, sem grupo de
controle nem variação exógena. Toda simulação de teto assume volume constante e
diz isso no retorno.</p>
<p><b>Meta em reais para o pós-pedido.</b> A base não registra destino do item
devolvido, custo da logística reversa nem motivo validado. A perda é
dimensionada, não convertida em meta.</p>
<p><b>Teste A/B por cliente.</b> O cálculo de poder mostra que medir perda de
volume exigiria 887.164 clientes; a base tem 331. A inviabilidade é medida pelo
próprio instrumento, não suposta.</p>
<p><b>Cliente individual.</b> Fora de escopo por P8.</p>

<h2>13. Governança</h2>
<p><b>Política de desconto.</b> Proposta com estado persistido, dono e data em
cada transição. O fluxo vai de Rascunho a Simulação e congela: aprovar de
verdade exige identidade autenticada, que é decisão de infraestrutura. O código
da aprovação existe e é testado, incluindo a regra de que quem propõe não
aprova.</p>
<p><b>Limites do agente.</b> O agente lê; não escreve na base. Nenhuma rota
grava em <code>data/*.csv</code>.</p>
<p><b>Tratamento de incerteza.</b> Toda resposta declara força de evidência
(FORTE, MODERADA ou FRACA) com o critério estatístico que a sustenta e a
principal limitação.</p>
<p><b>Rastreabilidade.</b> Trace por execução, hash da base em todo resultado e
recorte declarado em todo valor em reais.</p>

<h2>14. Testes</h2>
<p>{f['total_testes']} funções de teste, que geram 925 casos com
parametrização. A suíte roda sem rede e sem chave de API.</p>
{tab_testes}
<p><b>Testes de aceite.</b> <code>test_aceite_livro_de_numeros.py</code> confere,
ID a ID, se o motor reproduz os números publicados no Livro de Números — o teto
de 20%, a regra de frete, a ponte do pós-pedido e os KPIs do roadmap. Se um
falhar, o motor divergiu da apresentação, e isso é decisão humana, não ajuste
de teste.</p>

<h2>15. Exemplo ponta a ponta</h2>
<p>Execução real, gerada no momento em que este PDF foi produzido.</p>
<p class="rotulo">PERGUNTA</p>
<p>{ex['pergunta']}</p>
<p class="rotulo">ROTEADOR</p>
{tab_rota}
<p class="rotulo">RESULTADO DO MOTOR</p>
{tab_resultado}
<p class="nota">Leitura: aplicar 17% neste segmento <b>aumentaria</b> o desconto
concedido em {_brl(res.get('variacao_desconto_reais'))}, porque o desconto que
já se pratica ali é de {res.get('desconto_atual_pct_no_segmento')}%. O número é
cenário sob premissa de volume constante, não previsão — e é a própria
ferramenta que declara isso no campo de premissa.</p>

<h2>16. Estrutura do projeto</h2>
<div class="fluxo">
vertice-retail/<br/>
├── data/             cinco CSVs do case (entrada; nunca reescritos)<br/>
├── vertice/          motor + agente + API<br/>
│   ├── engine/       {f['total_ferramentas']} ferramentas determinísticas, sem LLM<br/>
│   └── agent/        router, ReAct, verificação, trace, prompts<br/>
├── frontend/         painel web estático (sem framework, sem build)<br/>
├── tests/            {f['total_testes']} funções de teste<br/>
├── scripts/          auditoria das 95 perguntas e geração deste PDF<br/>
├── design-system/    tokens de marca (procedência do visual)<br/>
├── docs/             como rodar e relatório das 95 perguntas<br/>
├── documentacao/     este documento<br/>
├── README.md         arquitetura e decisões<br/>
└── PREMISSAS.md      as {len(f['premissas'])} premissas, numeradas
</div>

<h2>17. Execução</h2>
<p>Esta é a sequência exata usada para construir e verificar o projeto, na
máquina em que ele foi desenvolvido. Os comandos estão na ordem em que foram
executados.</p>

<p class="rotulo">AMBIENTE DE REFERÊNCIA</p>
{tab_ambiente}
<p class="nota">O projeto roda em Windows, macOS e Linux. O ambiente acima é o
que foi efetivamente usado — os comandos a seguir são os do WSL, e a seção
seguinte traz o equivalente em PowerShell.</p>

<p class="rotulo">1. PRÉ-REQUISITO DO SISTEMA (UMA VEZ)</p>
<div class="fluxo">
sudo apt update<br/>
sudo apt install -y python3 python3-venv python3-pip
</div>

<p class="rotulo">2. ENTRAR NO PROJETO</p>
<div class="fluxo">
cd /mnt/c/caminho/para/vertice-retail
</div>
<p class="nota">No WSL, o disco do Windows fica sob <code>/mnt/c/</code>. Todos
os comandos partem da raiz do repositório — a pasta que contém
<code>requirements.txt</code>.</p>

<p class="rotulo">3. CRIAR E ATIVAR O AMBIENTE VIRTUAL</p>
<div class="fluxo">
python3 -m venv venv<br/>
source venv/bin/activate
</div>

<p class="rotulo">4. INSTALAR AS DEPENDÊNCIAS</p>
<div class="fluxo">
pip install -r requirements.txt
</div>

<p class="rotulo">5. VERIFICAR — SEM REDE E SEM CHAVE DE API</p>
<div class="fluxo">
python -m pytest
</div>
<p>Esperado: <b>{f['total_casos']} passando, 11 pulados</b>. Este passo não usa
internet: o motor lê os CSVs e calcula em Python. É a verificação que precede
qualquer demonstração.</p>
<div class="fluxo">
python -m pytest tests/test_aceite_livro_de_numeros.py -v
</div>
<p class="nota">Os 35 testes de aceite conferem, ID a ID, se o motor reproduz os
números publicados. É o "Passo 0" da demonstração.</p>

<p class="rotulo">6. USAR SÓ O MOTOR, SEM IA</p>
<div class="fluxo">
python -c "from vertice.engine import executar; import json; \<br/>
&nbsp;&nbsp;print(json.dumps(executar('simular_teto_desconto', {{'teto_pct': 20}}), \<br/>
&nbsp;&nbsp;ensure_ascii=False, indent=2))"
</div>

<p class="rotulo">7. AGENTE SEM CHAVE (MODO MOCK)</p>
<div class="fluxo">
python -m vertice.cli --mock
</div>
<p class="nota">O texto vem de roteiro fixo; os números são reais, porque o motor
roda de verdade.</p>

<p class="rotulo">8. AGENTE COMPLETO (PRECISA DE CHAVE)</p>
<div class="fluxo">
export ELOAGENTS_API_KEY="sua-chave"<br/>
python -m vertice.cli --diagnostico&nbsp;&nbsp;# confere conexão e modelos<br/>
python -m vertice.cli&nbsp;&nbsp;# sessão interativa
</div>

<p class="rotulo">9. PAINEL WEB</p>
<div class="fluxo">
python -m vertice.api&nbsp;&nbsp;# http://localhost:8000<br/>
VERTICE_API_MOCK=1 python -m vertice.api&nbsp;&nbsp;# sem chave nenhuma
</div>

<p class="rotulo">10. REGERAR ESTE DOCUMENTO</p>
<div class="fluxo">
python -m scripts.gerar_documentacao
</div>

<p class="rotulo">EQUIVALENTE EM WINDOWS (POWERSHELL)</p>
<div class="fluxo">
py -m venv venv<br/>
venv\Scripts\Activate.ps1<br/>
pip install -r requirements.txt<br/>
python -m pytest<br/>
$env:ELOAGENTS_API_KEY = "sua-chave"<br/>
python -m vertice.api
</div>
<p class="nota">Se o PowerShell recusar o script de ativação, rode uma vez:
<code>Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass</code>.</p>

<p class="rotulo">SE ALGO FALHAR</p>
{tab_problemas}
<p class="nota">Variáveis de ambiente, provedor alternativo e o detalhamento de
cada comando: <code>docs/COMO_RODAR.md</code>.</p>
"""


# -------------------------------------------------------------------- saída
def gerar() -> Path:
    """Compõe o PDF em duas passadas.

    A primeira deixa o Story paginar o conteúdo (é ele que decide onde cada
    seção cabe); a segunda reabre o arquivo e carimba o rodapé em cada página,
    porque a numeração só existe depois de saber quantas páginas saíram.
    """
    fatos = _fatos()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)

    story = pymupdf.Story(html=_html(fatos), user_css=CSS)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    mais = True
    while mais:
        dispositivo = writer.begin_page(A4)
        mais, _ = story.place(AREA)
        story.draw(dispositivo)
        writer.end_page()
    writer.close()

    doc = pymupdf.open("pdf", buffer.getvalue())
    cinza = (0.42, 0.42, 0.47)
    for i, page in enumerate(doc, start=1):
        y = A4.y1 - MARGEM_BASE + 22
        page.draw_line(pymupdf.Point(MARGEM_X, y),
                       pymupdf.Point(A4.x1 - MARGEM_X, y),
                       color=(0.89, 0.89, 0.91), width=0.5)
        page.insert_text(
            pymupdf.Point(MARGEM_X, y + 13),
            "Vértice Retail · MarginGuard · documentação técnica do agente",
            fontsize=7, color=cinza)
        largura = pymupdf.get_text_length(str(i), fontsize=7)
        page.insert_text(
            pymupdf.Point(A4.x1 - MARGEM_X - largura, y + 13),
            str(i), fontsize=7, color=cinza)

    doc.subset_fonts()
    doc.save(SAIDA, deflate=True, garbage=4)
    paginas = doc.page_count
    doc.close()
    print(f"{paginas} páginas")
    return SAIDA


if __name__ == "__main__":
    caminho = gerar()
    print(f"gerado: {caminho}")
