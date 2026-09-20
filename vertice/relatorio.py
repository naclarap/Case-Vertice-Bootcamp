"""Relatório semanal: automação determinística separada do insight por IA.

O envio do relatório não precisa de IA nenhuma — é automação que roda em
agenda. `gerar_relatorio_semanal_dados()` monta os KPIs sem tocar em LLM, sem
rede e sem chave de API configurada, para poder rodar num cron.

A IA entra só para REDIGIR, em cima do que já foi calculado
(`redigir_resumo_executivo`). Se ela falhar, o relatório sai do mesmo jeito,
sem o parágrafo — nunca travar a automação por causa da parte opcional.
"""
from __future__ import annotations

import time
from typing import Any

from .engine import executar

# Nunca importar o cliente de LLM no topo: este módulo precisa ser importável e
# executável em ambiente sem chave/rede. O import fica dentro da função que
# realmente usa o modelo.


# ---------------------------------------------- convenção de EXIBIÇÃO
# O motor calcula a margem nos DOIS denominadores e, de propósito, não chama
# nenhum deles apenas de "margem": sobre receita bruta fecha a decomposição
# MECE (identidade contábil), sobre receita líquida é o que o comitê lê. Quem
# publica precisa escolher, e a escolha não é técnica — é a convenção do case.
#
# O deck e o painel da Vértice publicam 54,34% (sobre a receita líquida). O
# relatório vinha publicando 49,99% (sobre a bruta) sob o rótulo "margem do
# período": o número estava certo e o rótulo, errado. Estas funções são o
# único lugar onde essa escolha é feita, e valem para a tela, para o arquivo
# exportado e para o texto enviado ao modelo.

def _margem_exibida(bloco: dict):
    """Margem sobre receita LÍQUIDA — a convenção do deck e do painel."""
    return (bloco or {}).get("margem_pct_sobre_liquida")


def _ticket_exibido(bloco: dict):
    """Ticket médio sobre receita LÍQUIDA, como no painel (R$ 681,65 na base
    inteira). O `ticket_medio` do motor é sobre a bruta (R$ 740,94): mesma
    conta, outro numerador, e os dois juntos numa mesa de comitê viram
    discussão sobre qual está errado — nenhum está."""
    receita, pedidos = (bloco or {}).get("receita_liquida"), (bloco or {}).get("pedidos")
    if not receita or not pedidos:
        return None
    return round(float(receita) / int(pedidos), 2)


def _variacao_exibida(variacao, atual: dict, anterior: dict):
    """A variação em p.p. acompanha o denominador exibido, não o do motor."""
    a, b = _margem_exibida(atual), _margem_exibida(anterior)
    if not variacao or a is None or b is None:
        return variacao
    return {**variacao, "margem_pp": round(a - b, 2)}


def gerar_relatorio_semanal_dados(canal_foco: str = "Marketplace",
                                  dias: int = 7, ate: str | None = None) -> dict:
    """KPIs do painel, 100% determinístico. Não chama LLM nem rede.

    `dias` define a JANELA do relatório (padrão 7 = semanal). Antes este
    relatório trazia só o acumulado dos 13 meses da base e mesmo assim se
    chamava semanal — o que ele não era. Agora o bloco `semana` é a janela
    recente comparada com a anterior, e os blocos estruturais (frete evitável,
    devoluções, pior canal) continuam no acumulado, rotulados como tal: são
    diagnósticos de estoque de problema, não de fluxo semanal.

    `ate` é o ÚLTIMO dia da janela (AAAA-MM-DD); sem ele, a janela termina no
    último dia da base. O parâmetro existe em `margem_na_janela` desde sempre —
    o que faltava era o caminho até ele. Enquanto o relatório era semanal
    ninguém precisou de data de fim ("os últimos 7 dias" acaba hoje), então o
    parâmetro parava três camadas antes da tela; com a tela passando a oferecer
    escolha de período, a data pedida precisa chegar ao motor.
    """
    consolidado = executar("margem_consolidada")
    semana = executar("margem_na_janela", {"dias": dias, "ate": ate})
    tem_pedido = not (semana.get("janela_atual") or {}).get("vazio", True)
    cascata = (executar("perda_pos_pedido", {"dias": dias, "ate": ate})
               if tem_pedido else None)
    por_canal_no_periodo = (executar("margem_por_dimensao",
                                     {"dimensao": "canal", "dias": dias, "ate": ate})
                            if tem_pedido else None)
    negativos = executar("pedidos_margem_negativa")
    devolucoes = executar("impacto_devolucoes", {"por": "canal"})
    frete_canal = executar("custo_assimetria_frete", {"canal": canal_foco})
    por_canal = executar("margem_por_dimensao", {"dimensao": "canal"})

    pior_canal = min(por_canal["linhas"], key=_margem_exibida)

    atual, anterior = semana["janela_atual"], semana["janela_anterior"]
    return {
        "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "janela": consolidado.get("base", {}).get("janela"),
        "semana": {
            "dias": semana["dias"],
            "inicio": atual.get("inicio"),
            "fim": atual.get("fim"),
            "pedidos": atual.get("pedidos"),
            "receita_bruta": atual.get("receita_bruta"),
            "receita_liquida": atual.get("receita_liquida"),
            "margem_pct": _margem_exibida(atual),
            "margem_reais": atual.get("margem_contribuicao"),
            "desconto_pct": atual.get("desconto_pct"),
            "ticket_medio": _ticket_exibido(atual),
            "base_do_percentual": "receita líquida",
            "anterior": {
                "inicio": anterior.get("inicio"), "fim": anterior.get("fim"),
                "pedidos": anterior.get("pedidos"),
                "margem_pct": _margem_exibida(anterior),
                "desconto_pct": anterior.get("desconto_pct"),
            },
            "variacao": _variacao_exibida(semana["variacao"], atual, anterior),
            "nota": semana["nota"],
        },
        "margem": {
            "receita_bruta": consolidado["receita_bruta"],
            "receita_liquida": consolidado["receita_liquida"],
            "margem_reais": consolidado["margem_contribuicao"],
            "margem_pct": _margem_exibida(consolidado),
            "base_do_percentual": "receita líquida",
        },
        "desconto": {
            "desconto_reais": consolidado["desconto_reais"],
            "taxa_desconto_pct": consolidado["desconto_pct"],
        },
        "margem_negativa": {
            "pedidos": negativos["pedidos_negativos"],
            "pct_dos_pedidos": negativos["pct_dos_pedidos"],
            "perda_reais": negativos["perda_total_reais"],
        },
        "frete_canal_foco": {
            "canal": canal_foco,
            "frete_pago_total": frete_canal["frete_pago_total"],
            "frete_evitavel_reais": frete_canal["frete_evitavel_reais"],
            "ganho_margem_pp_consolidado": frete_canal["ganho_margem_pp_consolidado"],
        },
        "devolucoes": {
            "taxa_global_pct": devolucoes["taxa_devolucao_global_pct"],
            "margem_perdida_reais": devolucoes["margem_perdida_total_reais"],
            "impacto_pp_na_margem": devolucoes["impacto_pp_na_margem_consolidada"],
            # PREMISSA P7: margem_contribuicao é anterior à devolução. Nenhum
            # custo de devolução está deduzido da margem reportada — por isso
            # este vazamento é ADICIONAL ao déficit já medido, e o KPI de
            # "custo registrado" é 0% por construção da base, não por acaso.
            "custo_registrado_na_margem": False,
            "pct_devolucoes_com_custo_deduzido": 0.0,
        },
        # Ponte da margem no período e margem por canal: os mesmos números
        # que a tela desenha, para o arquivo exportado desenhar iguais.
        "cascata": cascata,
        "margem_por_canal": por_canal_no_periodo,
        "pior_canal_por_margem": {
            "canal": pior_canal["canal"],
            "margem_pct": _margem_exibida(pior_canal),
        },
        "fontes": ["margem_na_janela", "margem_consolidada", "pedidos_margem_negativa",
                   "impacto_devolucoes", "custo_assimetria_frete",
                   "margem_por_dimensao"]
                  + (["perda_pos_pedido"] if tem_pedido else []),
    }


def _brl(v) -> str:
    """R$ 186.653,95 — vírgula decimal, ponto de milhar, sinal antes do símbolo."""
    if v is None:
        return "—"
    sinal = "−" if float(v) < 0 else ""
    s = f"{abs(float(v)):,.2f}"
    return sinal + "R$ " + s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _pct(v, casas: int = 2) -> str:
    return "—" if v is None else f"{float(v):.{casas}f}".replace(".", ",") + "%"


def _pp(v, casas: int = 2) -> str:
    """Pontos percentuais levam sinal explícito: +1,8 p.p. / -0,9 p.p."""
    if v is None:
        return "—"
    sinal = "+" if float(v) > 0 else ""
    return sinal + f"{float(v):.{casas}f}".replace(".", ",") + " p.p."


def _int(v) -> str:
    if v is None:
        return "—"
    return f"{int(v):,}".replace(",", ".")


def _kpis_em_pt_br(d: dict) -> str:
    """Os KPIs já escritos como se lêem em português.

    O modelo copia o que recebe: mandar `186653.95` produz "receita bruta de
    186653.95" no meio da frase — ponto decimal, sem símbolo, ilegível para a
    diretoria. Formatar ANTES de enviar é o que garante o formato pt-BR no
    texto final, porque aí a regra "use somente os números acima" passa a
    trabalhar a favor: a string certa já está lá para ser copiada.
    """
    s, m = d.get("semana") or {}, d.get("margem") or {}
    ant, var = s.get("anterior") or {}, s.get("variacao") or {}
    desc = d.get("desconto") or {}
    neg = d.get("margem_negativa") or {}
    frete = d.get("frete_canal_foco") or {}
    dev = d.get("devolucoes") or {}
    pior = d.get("pior_canal_por_margem") or {}
    janela = d.get("janela") or ["?", "?"]

    def dt(iso):
        p = str(iso or "")[:10].split("-")
        return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else "—"

    return "\n".join([
        f"PERÍODO: {dt(s.get('inicio'))} a {dt(s.get('fim'))} ({_int(s.get('dias'))} dias)",
        f"  receita bruta: {_brl(s.get('receita_bruta'))}",
        f"  margem de contribuição: {_pct(s.get('margem_pct'))} sobre a receita líquida "
        f"({_brl(s.get('margem_reais'))})",
        f"  taxa de desconto: {_pct(s.get('desconto_pct'))}",
        f"  receita líquida: {_brl(s.get('receita_liquida'))}",
        f"  pedidos: {_int(s.get('pedidos'))} · ticket médio {_brl(s.get('ticket_medio'))}",
        f"  período anterior ({dt(ant.get('inicio'))} a {dt(ant.get('fim'))}): "
        f"margem {_pct(ant.get('margem_pct'))}, desconto {_pct(ant.get('desconto_pct'))}, "
        f"{_int(ant.get('pedidos'))} pedidos",
        f"  variação: margem {_pp(var.get('margem_pp'))}, desconto {_pp(var.get('desconto_pp'))}, "
        f"receita {_pct(var.get('receita_pct'))}, pedidos {_pct(var.get('pedidos_pct'))}",
        "",
        f"ACUMULADO DA BASE ({dt(janela[0])} a {dt(janela[-1])}):",
        f"  margem consolidada: {_pct(m.get('margem_pct'))} ({_brl(m.get('margem_reais'))} "
        f"sobre {_brl(m.get('receita_liquida'))} de receita líquida)",
        f"  desconto concedido: {_pct(desc.get('taxa_desconto_pct'))} ({_brl(desc.get('desconto_reais'))})",
        f"  pedidos com margem negativa: {_int(neg.get('pedidos'))} "
        f"({_pct(neg.get('pct_dos_pedidos'))} dos pedidos, {_brl(neg.get('perda_reais'))} de perda)",
        f"  frete evitável em {frete.get('canal', '—')}: {_brl(frete.get('frete_evitavel_reais'))} "
        f"({_pp(frete.get('ganho_margem_pp_consolidado'), 3)} na margem consolidada)",
        f"  devoluções: taxa de {_pct(dev.get('taxa_global_pct'))}, "
        f"{_brl(dev.get('margem_perdida_reais'))} de margem perdida "
        f"({_pp(dev.get('impacto_pp_na_margem'))} na margem)",
        f"  pior canal por margem: {pior.get('canal', '—')} com {_pct(pior.get('margem_pct'))}",
    ])


def redigir_resumo_executivo(payload_kpis: dict, llm: Any = None,
                             modelo: str | None = None) -> str | None:
    """Parágrafo de insight em cima dos KPIs já calculados. OPCIONAL.

    Devolve None em qualquer falha (sem chave, gateway fora, resposta vazia) —
    quem chamou monta o relatório sem o parágrafo. O modelo só redige: todo
    número que ele citar já está no payload determinístico, e já formatado em
    pt-BR (ver `_kpis_em_pt_br`).
    """
    try:
        from . import config
        from .agent.llm import construir_llm

        cliente = llm if llm is not None else construir_llm()
        prompt = (
            "Você é analista de margem da Vértice Retail e escreve para um "
            "comitê executivo. Escreva UM parágrafo de resumo executivo a "
            "partir dos KPIs abaixo, já apurados por motor determinístico.\n\n"
            f"{_kpis_em_pt_br(payload_kpis)}\n\n"
            "REGRAS DE CONTEÚDO\n"
            "- Use SOMENTE números que aparecem acima. Não recalcule, não "
            "arredonde diferente, não invente causa que os dados não mostrem.\n"
            "- Copie cada número EXATAMENTE como está escrito acima, com "
            "'R$', '%', 'p.p.', vírgula decimal e ponto de milhar. Nunca "
            "escreva um número solto como 186653.95.\n"
            "- No máximo 4 números no parágrafo inteiro: escolha os que "
            "sustentam a leitura, não todos os disponíveis.\n\n"
            "REGRAS DE ESCRITA\n"
            "- 4 a 5 frases curtas, verbo no presente, um parágrafo corrido "
            "sem bullet points e sem título.\n"
            "- Afirmação primeiro, prova depois, recomendação por último.\n"
            "- Terceira pessoa. Nunca 'você'. Sem emoji.\n"
            "- Não abra com 'No fechamento da semana' nem repita o período "
            "inteiro: quem lê já tem a data no cabeçalho do relatório.\n"
            "- Comece pela leitura do que aconteceu com a margem."
        )
        msg = cliente.completar([{"role": "user", "content": prompt}],
                                modelo or config.MODELO_SINTESE)
        texto = (getattr(msg, "content", None) or "").strip()
        return texto or None
    except Exception:
        # A automação não pode cair por causa da parte opcional.
        return None


def gerar_relatorio_semanal(canal_foco: str = "Marketplace", com_resumo: bool = True,
                            llm: Any = None, dias: int = 7,
                            ate: str | None = None) -> dict:
    """Relatório completo: dados determinísticos sempre; resumo em texto como
    campo opcional, que pode vir None."""
    dados = gerar_relatorio_semanal_dados(canal_foco=canal_foco, dias=dias, ate=ate)
    resumo = redigir_resumo_executivo(dados, llm=llm) if com_resumo else None
    return {
        **dados,
        "resumo_executivo": resumo,
        "resumo_disponivel": resumo is not None,
    }


def main(argv: list[str] | None = None) -> int:
    """Entrada para agendamento:

        python -m vertice.relatorio                 # só dados, sem LLM (cron)
        python -m vertice.relatorio --com-resumo    # tenta o parágrafo de IA

    Sem --com-resumo nada de rede acontece, então roda em máquina sem chave.
    """
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Relatório semanal — Vértice Retail")
    ap.add_argument("--com-resumo", action="store_true",
                    help="tenta redigir o resumo executivo com o LLM (opcional)")
    ap.add_argument("--canal-foco", default="Marketplace")
    args = ap.parse_args(argv)

    r = (gerar_relatorio_semanal(canal_foco=args.canal_foco)
         if args.com_resumo
         else gerar_relatorio_semanal_dados(canal_foco=args.canal_foco))
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
