"""Relatórios em HTML — arquivo autocontido, legível na tela e imprimível.

Por que HTML e não só JSON: o JSON serve para máquina; quem recebe o relatório
semanal é gente. Este módulo gera um arquivo único, com o CSS embutido, que
abre no navegador e imprime em PDF direto pelo Ctrl+P.

Identidade visual: os tokens abaixo são os de design-system/tokens/*.css, os
mesmos do painel — um relatório que sai do MarginGuard precisa se parecer com
o MarginGuard. A ÚNICA dependência externa são as duas webfonts da marca; sem
rede, a pilha de reserva assume e o arquivo continua legível e imprimível.

Só tema claro, de propósito: relatório que se abre para ler, compartilhar e
imprimir não deve trocar de cor conforme o tema do sistema de quem abre.

Cores de status seguem a regra de nunca carregar significado sozinhas: todo
chip traz ícone + rótulo além da cor.
"""
from __future__ import annotations

import html
from typing import Any

# Fontes da marca (design-system/tokens/fonts.css). São o ÚNICO recurso remoto
# deste arquivo: sem rede, o navegador cai na pilha de reserva e o relatório
# continua legível e imprimível — só perde a face tipográfica.
_FONTES = ("https://fonts.googleapis.com/css2?"
           "family=Schibsted+Grotesk:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500"
           "&display=swap")

# Tokens de design-system/tokens/*.css. Claro apenas, de propósito: relatório
# que se abre para ler, compartilhar e imprimir não deve mudar de cor conforme
# o tema do sistema operacional de quem abre.
_CSS = """
:root{
  --indigo-900:#0C0C74; --indigo-800:#12129E; --indigo-700:#1A1AC8; --indigo-500:#4442E4;
  --lavender-300:#A5A2E8; --lavender-200:#C9C7F5; --lavender-100:#E8E7FC; --lavender-050:#F2F1FE;
  --ink-900:#17171B; --ink-700:#3A3A42; --ink-500:#6B6B78; --ink-400:#9A9AA6;
  --ink-300:#C4C4CC; --ink-200:#E3E3DF; --ink-100:#EDEDE9;
  --paper:#F6F6F4; --white:#FFFFFF;
  --copper-600:#B0521C;
  --green-500:#12805C; --green-100:#E3F2EC;
  --red-500:#B3261E; --red-100:#FBE9E7;
  --amber-500:#A8700F; --amber-100:#FBF1DF;

  --text-strong:var(--ink-900); --text-body:var(--ink-700);
  --text-muted:var(--ink-500); --text-faint:var(--ink-400);
  --text-accent:var(--indigo-700);
  --surface-page:var(--paper); --surface-card:var(--white); --surface-sunken:var(--ink-100);
  --line-soft:var(--ink-200); --line-strong:var(--ink-300); --line-accent:var(--lavender-200);
  --status-positive:var(--green-500); --status-positive-soft:var(--green-100);
  --status-negative:var(--red-500); --status-negative-soft:var(--red-100);
  --status-warning:var(--amber-500); --status-warning-soft:var(--amber-100);
  --action-primary:var(--indigo-700);

  --font-display:'Schibsted Grotesk','Helvetica Neue',Helvetica,Arial,sans-serif;
  --font-body:'Schibsted Grotesk','Helvetica Neue',Helvetica,Arial,sans-serif;
  --font-mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
  --label-tracking:0.16em;
  --radius-xs:3px; --radius-sm:6px; --radius-md:10px; --radius-pill:999px;
  color-scheme:light;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--surface-page); color:var(--text-body);
  font-family:var(--font-body); font-size:15px; line-height:1.5;
  -webkit-font-smoothing:antialiased;
  padding:48px 24px;
}
.wrap{max-width:1000px;margin:0 auto}

/* Eyebrow: mono maiúsculo com tracking largo — a forma de label do sistema. */
.eyebrow{
  font-family:var(--font-mono); font-size:11px; font-weight:400;
  letter-spacing:var(--label-tracking); text-transform:uppercase; color:var(--text-muted);
}
header{margin-bottom:40px}
h1{
  font-family:var(--font-display); font-size:34px; font-weight:400;
  line-height:1.04; letter-spacing:-0.022em; color:var(--text-strong);
  margin:12px 0 8px; text-wrap:balance;
}
.sub{color:var(--text-muted);font-size:15px;margin:0;max-width:62ch}
.legenda{color:var(--text-muted);font-size:13px;margin:-4px 0 16px;max-width:78ch;line-height:1.5}
h2{
  font-family:var(--font-display); font-size:19px; font-weight:600;
  letter-spacing:-0.012em; color:var(--text-strong); margin:40px 0 16px;
}

/* Card: fundo branco, hairline de 1px, raio 10px, padding 24px. Sem sombra —
   a estrutura do sistema vem da linha, não do relevo. */
.card{background:var(--surface-card);border:1px solid var(--line-soft);
  border-radius:var(--radius-md);padding:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:16px}
.kpi{background:var(--surface-card);border:1px solid var(--line-soft);
  border-radius:var(--radius-md);padding:20px;display:grid;gap:16px;align-content:start}
.kpi .lbl{
  font-family:var(--font-mono); font-size:11px; font-weight:400;
  letter-spacing:var(--label-tracking); text-transform:uppercase; color:var(--text-muted);
}
/* Número grande: face de display, -0.03em, legenda mono por baixo. */
.kpi .val{
  font-family:var(--font-display); font-size:34px; font-weight:400;
  letter-spacing:-0.03em; line-height:1; color:var(--text-strong);
  font-variant-numeric:tabular-nums; white-space:nowrap;
}
.kpi .val.longo{font-size:24px}
.kpi .ctx{font-family:var(--font-mono);font-size:12px;color:var(--text-faint);
  margin-top:-8px;font-variant-numeric:tabular-nums}

/* Em janela estreita, quem rola é o card da tabela — não a página inteira. */
.card:has(> table){overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{
  text-align:left; font-family:var(--font-mono); font-size:10px; font-weight:400;
  letter-spacing:var(--label-tracking); text-transform:uppercase; color:var(--text-muted);
  padding:12px 16px; border-bottom:1px solid var(--line-strong); white-space:nowrap;
}
td{padding:12px 16px;border-bottom:1px solid var(--line-soft);
  font-variant-numeric:tabular-nums;color:var(--text-body)}
tr:last-child td{border-bottom:none}
td.num,th.num{text-align:right}
/* Status é pílula, não número: cabeçalho e chip compartilham a borda esquerda. */
td.status-celula,th.status-celula{text-align:left;white-space:nowrap}
td.num{font-family:var(--font-mono)}

/* Pill de status: mono maiúsculo, raio pill, indicador de cor + rótulo. */
.chip{display:inline-flex;align-items:center;gap:8px;white-space:nowrap;
  font-family:var(--font-mono);font-size:11px;letter-spacing:var(--label-tracking);
  text-transform:uppercase;padding:5px 12px;border-radius:var(--radius-pill);
  border:1px solid transparent;color:var(--text-muted);background:var(--surface-sunken)}
.chip.ok{color:var(--status-positive);background:var(--status-positive-soft)}
.chip.warn{color:var(--status-warning);background:var(--status-warning-soft)}
.chip.crit{color:var(--status-negative);background:var(--status-negative-soft)}
.chip.rev{color:var(--text-accent);background:var(--lavender-100);border-color:var(--line-accent)}

.delta{font-family:var(--font-mono);font-size:12px;font-variant-numeric:tabular-nums}
.delta.sobe{color:var(--status-positive)} .delta.desce{color:var(--status-negative)}

.bars{display:flex;flex-direction:column;gap:8px;margin-top:4px}
.bar-row{display:grid;grid-template-columns:140px 1fr auto;align-items:center;gap:16px;font-size:13px}
.bar-track{background:var(--surface-sunken);border-radius:var(--radius-pill);height:10px;overflow:hidden}
.bar-fill{display:block;background:var(--action-primary);height:100%;
  border-radius:var(--radius-pill);min-width:4px}
.bar-val{font-family:var(--font-mono);font-size:12px;font-variant-numeric:tabular-nums;
  color:var(--text-strong);min-width:48px;text-align:right}

/* Nota: card accent do sistema (lavanda com hairline), sem barra colorida. */
.note{font-size:13px;color:var(--text-body);line-height:1.5;max-width:80ch;
  background:var(--lavender-050);border:1px solid var(--line-accent);
  padding:16px 20px;border-radius:var(--radius-sm);margin-top:16px}
.note strong{color:var(--text-strong)}

footer{margin-top:64px;padding-top:24px;border-top:1px solid var(--line-soft);
  font-size:12px;color:var(--text-faint);line-height:1.6}
code{font-family:var(--font-mono);font-size:11px;background:var(--surface-sunken);
  padding:2px 6px;border-radius:var(--radius-xs);border:1px solid var(--line-soft)}

@media print{
  body{background:var(--white);padding:0}
  .card,.kpi{break-inside:avoid-page}
  h2{break-after:avoid-page}
}
"""


_CSS_ACHADOS = """
  .achado{padding:18px 22px;background:var(--surface-card);
    border:1px solid var(--line-soft);border-radius:10px;margin-bottom:10px;}
  .achado.critico{border-color:var(--status-negative);}
  .achado.revisar,.achado.atencao{border-color:var(--status-warning);}
  .achado-titulo{display:flex;align-items:center;gap:10px;font-size:15px;
    font-weight:600;color:var(--text-strong);margin-bottom:6px;}
  .achado-ponto{width:9px;height:9px;border-radius:99px;flex:0 0 auto;
    background:var(--text-faint);}
  .achado.critico .achado-ponto{background:var(--status-negative);}
  .achado.revisar .achado-ponto,
  .achado.atencao .achado-ponto{background:var(--status-warning);}
  .achado-chip{margin-left:auto;}
  .achado-desc{font-size:14px;color:var(--text-body);line-height:1.6;max-width:78ch;}
  .achado-tec{margin-top:10px;font-family:var(--font-mono);font-size:11px;
    color:var(--text-faint);letter-spacing:.04em;}
  .achado-limpo{display:flex;align-items:center;gap:10px;padding:14px 22px;
    background:var(--surface-sunken);border-radius:10px;margin-bottom:6px;
    font-size:14px;color:var(--text-muted);}
  .achado-limpo .achado-ponto{background:var(--status-positive);}
"""

_CSS_GRAFICOS = """
  .grafico{display:grid;gap:10px;overflow-x:auto;margin:0 0 20px;}
  .cascata{display:flex;align-items:stretch;gap:16px;height:248px;
    padding-top:28px;position:relative;min-width:560px;}
  .cascata-col{flex:1;position:relative;min-width:86px;}
  .cascata-barra{position:absolute;left:0;right:0;min-height:2px;
    border-radius:4px;background:var(--lavender-300);}
  .cascata-barra.total{background:var(--action-primary);}
  .cascata-barra.baixa{background:var(--status-negative);}
  .cascata-barra.sobe{background:var(--status-positive);}
  .cascata-val{position:absolute;left:0;right:0;text-align:center;
    font-family:var(--font-mono);font-size:12px;color:var(--text-strong);
    white-space:nowrap;}
  .cascata-val.baixa{color:var(--status-negative);}
  .cascata-eixo{display:flex;gap:16px;border-top:1px solid var(--line-strong);
    padding-top:8px;min-width:560px;}
  .cascata-lbl{flex:1;min-width:0;text-align:center;line-height:1.4;
    font-family:var(--font-mono);font-size:11px;letter-spacing:.06em;
    text-transform:uppercase;color:var(--text-muted);}

  .barrav{display:flex;align-items:flex-end;gap:10px;height:180px;min-width:640px;}
  .barrav-col{flex:1;min-width:96px;display:flex;flex-direction:column;
    justify-content:flex-end;gap:4px;height:100%;}
  .barrav-val{font-family:var(--font-mono);font-size:12px;color:var(--text-muted);
    text-align:center;white-space:nowrap;}
  .barrav-barra{display:block;min-height:2px;background:var(--lavender-200);
    border-radius:4px;}
  .barrav-barra.destaque{background:var(--action-primary);}
  .barrav-eixo{display:flex;gap:10px;border-top:1px solid var(--line-soft);
    padding-top:8px;min-width:640px;}
  .barrav-lbl{flex:1;min-width:0;text-align:center;line-height:1.35;
    overflow-wrap:normal;word-break:normal;
    font-family:var(--font-mono);font-size:11px;letter-spacing:.06em;
    text-transform:uppercase;color:var(--text-faint);}
"""


ROTULOS_CHECAGEM = {
    "integridade_referencial": "Pedidos com referência quebrada",
    "duplicatas_chave": "Registros duplicados",
    "completude": "Campos obrigatórios faltando",
    "outliers_iqr": "Valores fora do padrão",
    "faixa_implausivel": "Valores fora da faixa esperada",
    "consistencia_categorica": "Categorias inconsistentes",
    "devolucao_fora_prazo": "Devoluções fora do prazo",
    "coerencia_motivo_entrega": "Motivo de devolução inconsistente",
}

# Exceção primeiro: o que pede ação vem antes do que veio limpo.
_ORDEM_STATUS = {"critico": 0, "revisar": 1, "atencao": 2, "ok": 3}


def _rotulo_checagem(nome: str) -> str:
    """Nome de negócio da checagem. O nome técnico continua sendo o do motor —
    isto é tradução de exibição, e só."""
    limpo = str(nome or "").removeprefix("checar_").removeprefix("verificar_")
    return ROTULOS_CHECAGEM.get(limpo, ROTULOS_CHECAGEM.get(str(nome), str(nome)))


def _status_da_checagem(c: dict) -> str:
    """Sem chave `status` NÃO é "sem problema": é checagem que não se pronuncia.
    Cair em "ok" por omissão foi como 1.910 outliers apareceram com selo verde.
    """
    if "erro" in c:
        return "critico"
    return (c.get("resultado") or {}).get("status") or "revisar"


def _peso_da_checagem(c: dict) -> int:
    return _ORDEM_STATUS.get(_status_da_checagem(c), _ORDEM_STATUS["revisar"])


def _e(v: Any) -> str:
    return html.escape(str(v))


def _brl(v: float | int | None, casas: int = 2) -> str:
    if v is None:
        return "—"
    # Sinal antes do símbolo ("−R$ 5.782,86"): "R$ -5.782,86" lê mal e é o
    # formato que nenhum extrato/banco brasileiro usa.
    sinal = "\u2212" if float(v) < 0 else ""
    s = f"{abs(float(v)):,.{casas}f}"
    return sinal + "R$\u00a0" + s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _pct(v: float | int | None, casas: int = 2) -> str:
    if v is None:
        return "—"
    return f"{float(v):.{casas}f}".replace(".", ",") + "%"


def _dt(iso: Any) -> str:
    """AAAA-MM-DD → DD/MM/AAAA. Mesma regra do painel: data mostrada a gente
    se lê em DD/MM/AAAA, sempre. Fatiar a string em vez de usar datetime é de
    propósito — não há fuso envolvido, e converter introduziria um.
    """
    p = str(iso or "")[:10].split("-")
    return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 and len(p[0]) == 4 else _e(iso or "—")


def _data_hora(iso: Any) -> str:
    """"2026-09-20 13:24:20" vira "20/09/2026 13:24:20". A hora acompanha
    quando existe; a data nunca sai em ISO para o leitor."""
    texto = str(iso or "")
    if not texto:
        return "—"
    partes = texto.split(" ", 1)
    return _dt(partes[0]) + (" " + partes[1] if len(partes) > 1 else "")


def _num(v: float | int | None, casas: int = 0) -> str:
    if v is None:
        return "—"
    s = f"{float(v):,.{casas}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _brl_curto(v: float | int | None) -> str:
    """R$ 1,2 mi / R$ 84,3 mil / R$ 512 — valor que cabe sob a barra."""
    if v is None:
        return "—"
    n = float(v)
    sinal = "−" if n < 0 else ""
    a = abs(n)
    if a >= 1_000_000:
        return f"{sinal}R$ {a / 1_000_000:.1f} mi".replace(".", ",")
    if a >= 1_000:
        return f"{sinal}R$ {a / 1_000:.1f} mil".replace(".", ",")
    return f"{sinal}R$ {a:.0f}"


def _grafico_cascata(c: dict | None) -> str:
    """Ponte da margem no período, na mesma ordem fixa da tela: a cascata conta
    uma sequência, não um ranking."""
    if not c or not c.get("ramos"):
        return ""

    def ramo(nome: str) -> float:
        linha = next((x for x in c["ramos"] if x["ramo"] == nome), None)
        return float(linha["margem_perdida_reais"]) if linha else 0.0

    passos = [
        ("Margem calculada", float(c["margem_calculada_reais"]), True),
        ("Cancelamento", -ramo("Cancelamento"), False),
        ("Pendência", -ramo("Pendência"), False),
        ("Devolução", -ramo("Devolução"), False),
        ("Atendimento", -ramo("Atendimento"), False),
        ("Margem realizada", float(c["margem_que_se_realiza_reais"]), True),
    ]

    correndo, pontos = 0.0, []
    for rotulo, valor, total in passos:
        ini = 0.0 if total else correndo
        fim = valor if total else correndo + valor
        correndo = valor if total else fim
        pontos.append((rotulo, valor, total, max(ini, fim), min(ini, fim)))

    maximo = max([p[3] for p in pontos] + [1.0])
    barras, rotulos = [], []
    for rotulo, valor, total, topo, base in pontos:
        classe = "total" if total else ("baixa" if valor < 0 else "sobe")
        barras.append(
            f'<div class="cascata-col">'
            f'<span class="cascata-val {classe}" '
            f'style="bottom:calc({topo / maximo * 100:.2f}% + 6px)">'
            f'{_e(_brl_curto(valor))}</span>'
            f'<span class="cascata-barra {classe}" '
            f'style="bottom:{base / maximo * 100:.2f}%;'
            f'height:{(topo - base) / maximo * 100:.2f}%"></span></div>')
        rotulos.append(f'<span class="cascata-lbl">{_e(rotulo)}</span>')

    perdeu = _pct(c.get("perda_pct_da_margem_calculada"))
    return (f'<h2>Ponte da margem no período</h2>'
            f'<div class="card"><div class="grafico">'
            f'<div class="cascata">{"".join(barras)}</div>'
            f'<div class="cascata-eixo">{"".join(rotulos)}</div></div>'
            f'<p class="legenda">Perda pós-pedido de '
            f'{_brl(c.get("perda_pos_pedido_reais"))} · {perdeu} da margem '
            f'calculada.</p>'
            f'<p class="legenda">Piso factual da devolução: '
            f'{_brl(c.get("piso_factual_da_devolucao_reais"))}.</p></div>')


def _grafico_margem_por_canal(b: dict | None) -> str:
    """Margem por canal no período, da pior para a melhor — a leitura do
    gráfico é 'onde dói'."""
    linhas = (b or {}).get("linhas") or []
    if not linhas:
        return ""
    ordenadas = sorted(linhas, key=lambda x: x["margem_pct_sobre_liquida"])
    maximo = max([abs(x["margem_pct_sobre_liquida"]) for x in ordenadas] + [1.0])
    pior = ordenadas[0]

    colunas, rotulos = [], []
    for linha in ordenadas:
        valor = linha["margem_pct_sobre_liquida"]
        destaque = " destaque" if linha is pior else ""
        colunas.append(
            f'<div class="barrav-col">'
            f'<span class="barrav-val">{_pct(valor)}</span>'
            f'<span class="barrav-barra{destaque}" '
            f'style="height:{abs(valor) / maximo * 100:.2f}%"></span></div>')
        rotulos.append(f'<span class="barrav-lbl">{_e(linha["canal"])}</span>')

    return (f'<h2>Margem por canal</h2>'
            f'<div class="card"><div class="grafico">'
            f'<div class="barrav">{"".join(colunas)}</div>'
            f'<div class="barrav-eixo">{"".join(rotulos)}</div></div>'
            f'<p class="legenda">Margem de contribuição sobre receita líquida. '
            f'Pior canal: <strong>{_e(pior["canal"])}</strong>, '
            f'{_pct(pior["margem_pct_sobre_liquida"])} em '
            f'{_num(pior["pedidos"])} pedidos.</p></div>')


def _kpi(label: str, valor: str, contexto: str = "") -> str:
    ctx = f'<div class="ctx">{_e(contexto)}</div>' if contexto else ""
    # Valor numa linha só (quebrar "R$ 135.256,57" no meio fica ilegível); o
    # que não cabe na largura do card ganha um corpo menor em vez de estourar.
    classe = "val longo" if len(valor) > 12 else "val"
    return (f'<div class="kpi"><div class="lbl">{_e(label)}</div>'
            f'<div class="{classe}">{_e(valor)}</div>{ctx}</div>')


def _chip(status: str) -> str:
    """Cor NUNCA sozinha: sempre com ícone e rótulo."""
    mapa = {
        "ok": ("ok", "✓", "Sem problema"),
        # Terceiro estado: a checagem ACHOU algo, mas achado não é erro provado
        # (outlier estatístico, incoerência de domínio). Marcar isso como "Sem
        # problema" era mentira — foi a reclamação que criou este status.
        "revisar": ("rev", "◆", "Requer leitura"),
        "atencao": ("warn", "▲", "Atenção"),
        "critico": ("crit", "✕", "Crítico"),
    }
    classe, icone, rotulo = mapa.get(status, ("warn", "▲", "Atenção"))
    return f'<span class="chip {classe}">{icone} {rotulo}</span>'


def _pagina(titulo: str, subtitulo: str, corpo: str, rodape: str) -> str:
    # O CSS dos gráficos acompanha a página: arquivo exportado abre offline.
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(titulo)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{_FONTES}">
<style>{_CSS}{_CSS_GRAFICOS}{_CSS_ACHADOS}</style></head>
<body><div class="wrap">
<header>
  <div class="eyebrow">Vértice Retail · MarginGuard</div>
  <h1>{_e(titulo)}</h1>
  <p class="sub">{_e(subtitulo)}</p>
</header>
{corpo}
<footer>{rodape}</footer>
</div></body></html>"""


# ------------------------------------------------------- relatório por período
def render_relatorio_html(d: dict) -> str:
    m, desc = d["margem"], d["desconto"]
    neg, frete = d["margem_negativa"], d["frete_canal_foco"]
    dev, pior = d["devolucoes"], d["pior_canal_por_margem"]

    bloco_periodo = _periodo(d.get("semana"))
    graficos = (_grafico_cascata(d.get("cascata"))
                + _grafico_margem_por_canal(d.get("margem_por_canal"))
                if (d.get("semana") or {}).get("pedidos") else "")

    kpis = "".join([
        _kpi("Margem de contribuição", _pct(m["margem_pct"]),
             f'{_brl(m["margem_reais"])} sobre receita líquida'),
        _kpi("Taxa de desconto", _pct(desc["taxa_desconto_pct"]),
             _brl(desc["desconto_reais"])),
        _kpi("Pedidos com margem negativa", _num(neg["pedidos"]),
             f'{_pct(neg["pct_dos_pedidos"])} dos pedidos · {_brl(neg["perda_reais"])}'),
        _kpi(f'Frete evitável — {frete["canal"]}', _brl(frete["frete_evitavel_reais"]),
             f'+{_pct(frete["ganho_margem_pp_consolidado"], 3).replace("%", " p.p.")} '
             f'na margem consolidada'),
        _kpi("Taxa de devolução", _pct(dev["taxa_global_pct"]),
             f'{_brl(dev["margem_perdida_reais"])} de margem'),
        _kpi("Pior canal por margem", pior["canal"], _pct(pior["margem_pct"])),
    ])

    resumo = ""
    if d.get("resumo_executivo"):
        resumo = (f'<h2>Resumo executivo</h2><div class="card">'
                  f'<p style="margin:0">{_e(d["resumo_executivo"])}</p>'
                  f'<div class="note">Parágrafo redigido por IA a partir dos KPIs '
                  f'já apurados acima. Os números são os mesmos — o modelo não '
                  f'recalcula nada.</div></div>')

    devol = f"""<h2>Devoluções</h2><div class="card">
<table><tr><th>Indicador</th><th class="num">Valor</th></tr>
<tr><td>Taxa global de devolução</td><td class="num">{_pct(dev["taxa_global_pct"])}</td></tr>
<tr><td>Margem carregada nos pedidos devolvidos</td><td class="num">{_brl(dev["margem_perdida_reais"])}</td></tr>
<tr><td>Impacto na margem consolidada</td><td class="num">{_pct(dev["impacto_pp_na_margem"]).replace("%"," p.p.")}</td></tr>
<tr><td>Custo de devolução deduzido da margem</td><td class="num">{_chip("atencao")} Não</td></tr>
</table></div>"""

    fontes = ", ".join(f"<code>{_e(f)}</code>" for f in d.get("fontes", []))
    rodape = (f'Gerado em {_e(_data_hora(d.get("gerado_em")))} · Todo número vem '
              f'de ferramenta determinística do motor: {fontes}. Nenhum valor foi '
              f'calculado por modelo de linguagem.')

    janela = d.get("janela") or []
    base = (f'base de {_dt(janela[0])} a {_dt(janela[1])}'
            if len(janela) == 2 else "")
    sem = d.get("semana") or {}
    sub = (f'Período de {_dt(sem.get("inicio"))} a {_dt(sem.get("fim"))} · {base}'
           if sem.get("fim") else base or "Relatório por período")

    corpo = (f'{bloco_periodo}{graficos}'
             f'<h2>Acumulado da base</h2>'
             f'<p class="legenda">{_e(base)}</p>'
             f'<div class="grid">{kpis}</div>{resumo}{devol}')
    return _pagina("Relatório por período", sub, corpo, rodape)


def _delta(valor, sufixo: str, bom_quando_sobe: bool = True) -> str:
    """Variação com sinal e direção — cor nunca sozinha: o sinal já diz."""
    if valor is None:
        return ""
    classe = "sobe" if (valor >= 0) == bom_quando_sobe else "desce"
    sinal = "+" if valor > 0 else ("−" if valor < 0 else "")
    corpo = f"{abs(float(valor)):.2f}".replace(".", ",")
    return f'<span class="delta {classe}">{sinal}{corpo} {sufixo}</span>'


def _periodo(sem: dict | None) -> str:
    """O período escolhido é o assunto do relatório — vem antes do acumulado."""
    if not sem or not sem.get("fim"):
        return ""
    ant, var = sem.get("anterior") or {}, sem.get("variacao") or {}
    comparativo = (f'vs {_dt(ant.get("inicio"))} a {_dt(ant.get("fim"))}'
                   if ant.get("fim") else "sem janela anterior para comparar")

    kpis = "".join([
        _kpi("Margem do período", _pct(sem.get("margem_pct")),
             f'{_brl(sem.get("margem_reais"))} sobre receita líquida · anterior '
             f'{_pct(ant.get("margem_pct"))}'),
        _kpi("Taxa de desconto", _pct(sem.get("desconto_pct")),
             f'anterior {_pct(ant.get("desconto_pct"))}'),
        _kpi("Pedidos", _num(sem.get("pedidos")),
             f'anterior {_num(ant.get("pedidos"))}'),
        _kpi("Ticket médio", _brl(sem.get("ticket_medio")),
             _brl(sem.get("receita_liquida")) + " de receita líquida"),
    ])

    linhas = "".join([
        f'<tr><td>Margem de contribuição</td><td class="num">'
        f'{_delta(var.get("margem_pp"), "p.p.")}</td></tr>',
        f'<tr><td>Taxa de desconto</td><td class="num">'
        f'{_delta(var.get("desconto_pp"), "p.p.", bom_quando_sobe=False)}</td></tr>',
        f'<tr><td>Receita bruta</td><td class="num">'
        f'{_delta(var.get("receita_pct"), "%")}</td></tr>',
        f'<tr><td>Pedidos</td><td class="num">'
        f'{_delta(var.get("pedidos_pct"), "%")}</td></tr>',
    ]) if var else ""

    variacao = (f'<table><tr><th>Indicador</th><th class="num">Variação sobre o '
                f'período anterior</th></tr>{linhas}</table>') if linhas else ""

    return (f'<h2>Período de {_dt(sem.get("inicio"))} a {_dt(sem.get("fim"))}</h2>'
            f'<p class="legenda">{_e(comparativo)} · janela de '
            f'{_num(sem.get("dias"))} dias</p>'
            f'<div class="grid">{kpis}</div>'
            + (f'<div class="card" style="margin-top:12px">{variacao}</div>'
               if variacao else ""))


# ------------------------------------------------------------------- auditoria
def _barras(celulas: list[dict], coluna_rotulo: str, limite: int = 6) -> str:
    if not celulas:
        return ""
    topo = celulas[:limite]
    maximo = max(c["registros"] for c in topo) or 1
    linhas = "".join(
        f'<div class="bar-row"><span>{_e(c[coluna_rotulo])}</span>'
        f'<span class="bar-track"><span class="bar-fill" '
        f'style="width:{c["registros"] / maximo * 100:.1f}%"></span></span>'
        f'<span class="bar-val">{_num(c["registros"])}</span></div>'
        for c in topo
    )
    return f'<div class="bars">{linhas}</div>'


def render_auditoria_html(d: dict, destaque: dict | None = None) -> str:
    """Mesmo desenho da tela de Auditoria: o que pede ação vira card, do mais
    grave ao mais leve; o que veio limpo fica listado abaixo. Antes isto era uma
    tabela única com o nome da função do motor na primeira coluna — o arquivo
    exportado dizia `outliers_iqr` onde a tela dizia "Valores fora do padrão".
    """
    checagens = sorted(d.get("checagens", []), key=_peso_da_checagem)
    com_problema = [c for c in checagens if _status_da_checagem(c) != "ok"]
    limpas = [c for c in checagens if _status_da_checagem(c) == "ok"]

    cards = []
    for c in com_problema:
        r = c.get("resultado") or {}
        status = _status_da_checagem(c)
        texto = _e(c["erro"]) if "erro" in c else _detalhe_checagem(c["checagem"], r)
        alvo = " · ".join(f"{k}={v}" for k, v in (c.get("parametros") or {}).items())
        cards.append(
            f'<div class="achado {status}">'
            f'<div class="achado-titulo"><span class="achado-ponto"></span>'
            f'{_e(_rotulo_checagem(c["checagem"]))}'
            f'<span class="achado-chip">{_chip(status)}</span></div>'
            f'<div class="achado-desc">{texto}</div>'
            f'<div class="achado-tec">{_e(c["checagem"])}'
            + (f' · {_e(alvo)}' if alvo else "")
            + '</div></div>')

    limpos = "".join(
        f'<div class="achado-limpo"><span class="achado-ponto"></span>'
        f'{_e(_rotulo_checagem(c["checagem"]))} — '
        f'{_detalhe_checagem(c["checagem"], c.get("resultado") or {})}</div>'
        for c in limpas)

    tabela = ("".join(cards) or
              '<div class="achado-limpo"><span class="achado-ponto"></span>'
              'Nenhuma checagem com problema.</div>')
    if limpos:
        tabela += f'<h2>Verificado e sem problema</h2>{limpos}'

    bloco_destaque = ""
    if destaque and destaque.get("celulas"):
        bloco_destaque = f"""<h2>Incoerência de domínio encontrada</h2><div class="card">
<p style="margin:0 0 14px;color:var(--text-body)">Motivo de devolução
<strong>"{_e(destaque.get("valor_b", ""))}"</strong> por categoria de produto —
registros em categorias onde o atributo não se aplica indicam preenchimento
incorreto na origem.</p>
{_barras(destaque["celulas"], destaque["coluna_a"])}
<div class="note"><strong>{_num(destaque.get("fora", 0))} registros</strong>
fora da categoria esperada. A contagem é determinística; o julgamento de que a
combinação é implausível é leitura de domínio, e fica para revisão humana.</div>
</div>"""

    # A seção "Lacunas de dado" saiu da tela E do relatório, a pedido do
    # usuário. O motor continua devolvendo `lacunas_de_dado` e
    # `prazo_devolucao` em /api/auditoria e no trace — o que mudou é o que
    # estas duas superfícies desenham, não o que a auditoria apura.

    rodape = ('Auditoria determinística sobre a base bruta (sem os filtros de '
              'PREMISSAS.md) — auditar a base já limpa não encontraria o que a '
              'limpeza escondeu.')
    n = len(com_problema)
    titulo = ("Nenhum ponto de atenção na base" if n == 0 else
              "1 ponto encontrado" if n == 1 else
              f"{n} pontos encontrados, do mais grave ao mais leve")
    sub = (f'{_num(d.get("total_checagens", 0))} checagens determinísticas '
           f'sobre a base bruta')
    return _pagina(titulo, sub, tabela + bloco_destaque, rodape)


def _detalhe_checagem(nome: str, r: dict) -> str:
    if nome == "integridade_referencial":
        return f'{_num(r.get("registros_orfaos"))} órfãos em {_num(r.get("linhas_verificadas"))} linhas'
    if nome == "duplicatas_chave":
        return f'{_num(r.get("linhas_duplicadas"))} duplicadas em {_num(r.get("linhas_verificadas"))} linhas'
    if nome == "completude":
        quebradas = r.get("linhas_quebradas", 0)
        if quebradas:
            ex = (r.get("exemplos_linhas_quebradas") or [{}])[0]
            ident = next((v for k, v in ex.items()
                          if k not in ("linha", "campos_vazios")), "")
            return (f'{_num(quebradas)} linha(s) com {ex.get("campos_vazios", "?")} '
                    f'campos vazios (ex: {ident})')
        if r.get("linhas_incompletas"):
            return (f'{_num(r["linhas_incompletas"])} linha(s) com algum nulo em '
                    f'{len(r.get("colunas_com_nulo", []))} coluna(s)')
        return "nenhum nulo"
    if nome == "outliers_iqr":
        return (f'{_num(r.get("outliers"))} outliers ({_pct(r.get("pct_outliers"))}) '
                f'em {r.get("coluna", "")} — máx observado '
                f'{_num(r.get("maximo_observado"), 2)}')
    if nome == "faixa_implausivel":
        return (f'{_num(r.get("fora_da_faixa"))} fora da faixa esperada em '
                f'{r.get("coluna", "")}')
    return "—"
