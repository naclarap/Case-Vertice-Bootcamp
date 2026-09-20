"""CLI interativo do agente de margem da Vértice Retail.

    python -m vertice.cli                    # sessão interativa (gateway real)
    python -m vertice.cli --mock             # sessão offline, sem chamar o gateway
    python -m vertice.cli -p "sua pergunta"  # pergunta única
    python -m vertice.cli --ferramentas      # lista o motor
    python -m vertice.cli --diagnostico      # testa a conexão com o gateway
"""
from __future__ import annotations

import argparse
import sys

from . import config
from .agent.react import AgenteMargem, validar_formato_final
from .engine import REGISTRO, executar

BANNER = r"""
╔══════════════════════════════════════════════════════════════════════╗
║  VÉRTICE RETAIL · Agente de Diagnóstico de Margem                    ║
║  Motor determinístico + ReAct · todo número vem de ferramenta        ║
╚══════════════════════════════════════════════════════════════════════╝"""

EXEMPLOS = [
    "Por que a margem de contribuição caiu?",
    "Qual canal tem a pior margem e por quê?",
    "O desconto está comprando volume incremental?",
    "Quanto o Marketplace paga de frete que não pagaria em outro canal?",
    "Qual o impacto de impor um teto de 25% de desconto?",
    "A queda de margem em novembro é sazonalidade ou mudança estrutural?",
]

AJUDA = """
Comandos:
  /ferramentas      lista as ferramentas do motor
  /trace            mostra o trace da última investigação
  /salvar           salva o trace da última investigação em traces/
  /exemplos         mostra perguntas de exemplo
  /limpar           esquece o histórico da conversa
  /sair             encerra
"""


def _brl(valor: float, casas: int = 2) -> str:
    """Formata no padrão brasileiro: 18.119.023,83 (ponto de milhar, vírgula decimal)."""
    return f"{valor:,.{casas}f}".translate(str.maketrans({",": ".", ".": ","})) if casas \
        else f"{valor:,.0f}".replace(",", ".")


def _mostrar_ferramentas() -> None:
    print(f"\n{len(REGISTRO)} ferramentas no motor determinístico:\n")
    for nome, f in REGISTRO.items():
        desc = " ".join(f.descricao.split())
        print(f"  • {nome}\n      {desc[:200]}")
        if f.parametros:
            for k, v in f.parametros.items():
                marca = "*" if k in f.obrigatorios else " "
                print(f"        {marca}{k}: {v}")
    print("\n  (* = parâmetro obrigatório)\n")


def _diagnostico() -> int:
    print(f"Base URL : {config.ELO_BASE_URL}")
    chave = config.chave_gateway()
    print(f"Chave    : {'definida (' + chave[:8] + '…)' if chave else 'AUSENTE'}")
    print(f"Modelos  : investigação={config.MODELO_INVESTIGACAO} síntese={config.MODELO_SINTESE}")
    print(f"Modo     : {config.MODO_FERRAMENTAS}")
    if not chave:
        print("\n✗ Defina ELOAGENTS_API_KEY antes de usar o gateway. Use --mock para rodar offline.")
        return 1
    try:
        from .agent.llm import EloAgentsLLM
        llm = EloAgentsLLM()
        print("\nModelos disponíveis no gateway:")
        for m in llm.listar_modelos():
            print(f"  - {m}")
        msg = llm.completar([{"role": "user", "content": "responda apenas: ok"}],
                            config.MODELO_INVESTIGACAO)
        print(f"\n✓ Conexão OK. Resposta de teste: {(msg.content or '').strip()[:80]}")
        return 0
    except Exception as e:
        print(f"\n✗ Falha ao conectar: {type(e).__name__}: {e}")
        # O host vem de config, não fixo no texto: ELOAGENTS_BASE_URL pode apontar
        # para qualquer provedor compatível com OpenAI (Groq, Ollama, etc.), e
        # mandar conferir "chat.eloagents.click" nesse caso confunde.
        print(f"  Verifique a chave, a rede/proxy e se o host de {config.ELO_BASE_URL} "
              f"está acessível.")
        # Cada provedor escreve de um jeito: Groq diz "does not exist", Gemini
        # diz "is not found for API version". A dica só serve se disparar nos dois.
        texto_erro = str(e).lower()
        if any(m in texto_erro for m in ("model_not_found", "does not exist",
                                         "is not found", "not_found", "404")):
            print("  O nome do modelo não existe neste provedor — escolha um da lista "
                  "acima e ajuste VERTICE_MODEL_STEP / VERTICE_MODEL_FINAL.")
        return 1


def _responder(agente: AgenteMargem, pergunta: str):
    trace = agente.investigar(pergunta)
    print("\n" + "─" * 72)
    print(trace.resposta_final)
    print("─" * 72)
    v = validar_formato_final(trace.resposta_final)
    if not v["valido"]:
        print(f"⚠️  formato final fora do padrão (faltando: {v['faltando']})")
    print(f"({len(trace.ferramentas_usadas)} chamadas de ferramenta · {trace.duracao_s}s "
          f"· trace {trace.id})\n")
    return trace


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Agente de diagnóstico de margem — Vértice Retail")
    ap.add_argument("-p", "--pergunta", help="faz uma pergunta e encerra")
    ap.add_argument("--mock", action="store_true",
                    help="roda sem gateway (LLM determinístico de teste)")
    ap.add_argument("--modo", choices=["texto", "nativo"], default=config.MODO_FERRAMENTAS,
                    help="transporte de ferramentas (padrão: texto)")
    ap.add_argument("--modelo", default=config.MODELO_INVESTIGACAO,
                    help="modelo dos passos de investigação (padrão: "
                         f"{config.MODELO_INVESTIGACAO})")
    ap.add_argument("--modelo-sintese", default=config.MODELO_SINTESE,
                    help="modelo da resposta final FATO/INFERÊNCIA/RECOMENDAÇÃO "
                         f"(padrão: {config.MODELO_SINTESE})")
    ap.add_argument("--max-iter", type=int, default=config.MAX_ITERACOES)
    ap.add_argument("--silencioso", action="store_true", help="não mostra o raciocínio")
    ap.add_argument("--ferramentas", action="store_true", help="lista as ferramentas e sai")
    ap.add_argument("--diagnostico", action="store_true", help="testa a conexão e sai")
    ap.add_argument("--salvar-trace", action="store_true", help="salva o trace em traces/")
    args = ap.parse_args(argv)

    if args.ferramentas:
        _mostrar_ferramentas()
        return 0
    if args.diagnostico:
        return _diagnostico()

    try:
        agente = AgenteMargem(modelo=args.modelo, modelo_sintese=args.modelo_sintese,
                              modo=args.modo, mock=args.mock,
                              max_iteracoes=args.max_iter, verbose=not args.silencioso)
    except RuntimeError as e:
        print(f"✗ {e}")
        return 1

    if args.mock:
        print("⚠️  MODO MOCK: respostas do LLM são um roteiro fixo de teste. "
              "Os NÚMEROS continuam reais (vêm do motor).")

    if args.pergunta:
        tr = _responder(agente, args.pergunta)
        if args.salvar_trace:
            print(f"trace salvo em {tr.salvar()}")
        return 0

    print(BANNER)
    modelos = args.modelo if args.modelo == args.modelo_sintese else f"{args.modelo}+{args.modelo_sintese}"
    print(f"Motor: {len(REGISTRO)} ferramentas · Modelo: {modelos} · Modo: {args.modo}")
    total = executar("margem_consolidada")
    print(f"Base: {_brl(total['pedidos'], 0)} pedidos aprovados · "
          f"R$ {_brl(total['receita_bruta'])} de receita · margem {total['margem_pct']}%")
    print("\nDigite sua pergunta, ou /ajuda para os comandos.")
    print("Exemplos:")
    for e in EXEMPLOS[:3]:
        print(f"  · {e}")

    ultimo = None
    while True:
        try:
            entrada = input("\n\033[1mvértice>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAté logo.")
            return 0
        if not entrada:
            continue
        cmd = entrada.lower()
        if cmd in ("/sair", "/quit", "/exit", "sair"):
            print("Até logo.")
            return 0
        if cmd in ("/ajuda", "/help", "?"):
            print(AJUDA)
            continue
        if cmd == "/ferramentas":
            _mostrar_ferramentas()
            continue
        if cmd == "/exemplos":
            for e in EXEMPLOS:
                print(f"  · {e}")
            continue
        if cmd == "/limpar":
            agente.historico.clear()
            print("Histórico esquecido.")
            continue
        if cmd == "/trace":
            print(ultimo.resumo_terminal() if ultimo else "Nenhuma investigação ainda.")
            continue
        if cmd == "/salvar":
            print(f"trace salvo em {ultimo.salvar()}" if ultimo else "Nenhuma investigação ainda.")
            continue
        if cmd.startswith("/"):
            print(f"Comando desconhecido: {entrada}. Use /ajuda.")
            continue
        try:
            ultimo = _responder(agente, entrada)
            if args.salvar_trace:
                ultimo.salvar()
        except KeyboardInterrupt:
            print("\n(investigação interrompida)")
        except Exception as e:
            print(f"\n✗ Erro na investigação: {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
