"""Gera docs/AUDITORIA_PERGUNTAS.md rodando as 95 perguntas do case no agente.

O relatório é DERIVADO da execução, nunca escrito à mão: a tabela sai do
roteador e do motor de verdade, então não existe versão bonita que já não
corresponda ao comportamento. Rode depois de mexer no roteamento:

    python -m scripts.auditoria_perguntas > docs/AUDITORIA_PERGUNTAS.md

As perguntas e o roteamento esperado vivem em tests/test_perguntas_negocio.py —
uma fonte só para o teste e para o relatório.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_perguntas_negocio import CASOS  # noqa: E402
from vertice.agent.router import (LIMITE_DE_DADOS, PERGUNTA_COMPLEXA, rotear,  # noqa: E402
                                  validar_parametros)
from vertice.engine import executar  # noqa: E402

# Chaves que, presentes no retorno, significam que a ferramenta já entregou a
# ressalva junto do número — é isso que a resposta final tem de repetir.
CHAVES_DE_RESSALVA = ("premissa", "ressalva_causal", "uso_permitido", "limitacao",
                      "nota", "lacuna", "origem_do_teto", "origem_das_alcadas",
                      "periodo_coberto", "leitura")

BLOCOS = [
    (1, 10, "Desconto e margem — diagnóstico"),
    (11, 25, "Desconto e margem — simulações"),
    (26, 37, "Política de descontos e alçadas"),
    (38, 47, "Frete — Marketplace"),
    (48, 66, "Devoluções"),
    (67, 72, "Sazonalidade e comparações"),
    (73, 86, "Perguntas executivas"),
    (87, 95, "Perguntas sem lastro nos dados"),
]


def _avaliar(caso) -> tuple[str, str]:
    """(veredito, observação) para uma pergunta, executando de verdade."""
    numero, pergunta, intencao, ferramenta, _ = caso
    r = rotear(pergunta)
    if r.intencao != intencao or r.ferramenta != ferramenta:
        return "FAIL", f"roteou para {r.intencao}/{r.ferramenta}"
    if r.intencao == PERGUNTA_COMPLEXA:
        return "ReAct", "investigação aberta: sem ferramenta única, por decisão"
    if not r.determinado:
        return "PEDE PARÂMETRO", f"falta {', '.join(r.faltando)} — a pergunta não traz"

    params, problemas = validar_parametros(ferramenta, r.parametros)
    if problemas:
        return "FAIL", f"parâmetros inválidos: {problemas}"
    try:
        resultado = executar(ferramenta, params)
    except Exception as e:                       # pragma: no cover - é o que o relatório existe para mostrar
        return "FAIL", f"{type(e).__name__}: {e}"
    if not resultado:
        return "FAIL", "ferramenta devolveu vazio"

    if r.intencao == LIMITE_DE_DADOS:
        return ("RECUSA MEDIDA" if resultado["veredito"] == "nao_respondivel"
                else "RESSALVA FORTE"), resultado["por_que"][:150]
    ressalvas = [k for k in CHAVES_DE_RESSALVA if k in resultado]
    if ressalvas:
        return "PASS com ressalva", "a ferramenta devolve " + ", ".join(ressalvas)
    return "PASS", ""


def main() -> None:
    print("# Auditoria das 95 perguntas do case\n")
    print("Gerado por `python -m scripts.auditoria_perguntas` — cada linha é uma "
          "execução real do roteador e do motor, não uma expectativa escrita à mão.\n")
    print("Legenda: **PASS** intenção, ferramenta, parâmetros e execução corretos · "
          "**PASS com ressalva** idem, e a ferramenta já devolve a premissa/limitação "
          "que a resposta precisa repetir · **RECUSA MEDIDA** a pergunta não tem "
          "lastro e a recusa vem com a medida que a sustenta · **ReAct** investigação "
          "aberta, sem ferramenta única por decisão · **PEDE PARÂMETRO** falta um "
          "valor que a pergunta não traz — o agente pergunta em vez de inventar.\n")

    contagem: dict[str, int] = {}
    for ini, fim, titulo in BLOCOS:
        print(f"\n## {titulo} (perguntas {ini}–{fim})\n")
        print("| # | Pergunta | Intenção | Ferramenta | Parâmetros | Veredito | Observação |")
        print("|---|---|---|---|---|---|---|")
        for caso in [c for c in CASOS if ini <= c[0] <= fim]:
            numero, pergunta, intencao, ferramenta, parametros = caso
            veredito, obs = _avaliar(caso)
            contagem[veredito] = contagem.get(veredito, 0) + 1
            par = ", ".join(f"{k}={v}" for k, v in parametros.items()) or "—"
            print(f"| {numero} | {pergunta} | {intencao} | {ferramenta or '—'} | "
                  f"{par} | {veredito} | {obs} |")

    print("\n## Resumo\n")
    for veredito, n in sorted(contagem.items(), key=lambda x: -x[1]):
        print(f"- **{veredito}**: {n}")
    print(f"- **total**: {sum(contagem.values())}")


if __name__ == "__main__":
    main()
