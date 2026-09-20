"""Camada 2 da auditoria: suspeita semântica assistida por LLM.

Vive FORA de `engine/` de propósito. O motor é determinístico e não importa
nada do agente (ver README, "Arquitetura"); esta camada fica acima dele:
pega a contagem determinística da Camada 1 e pede ao modelo só o JULGAMENTO de
domínio ("'Tamanho errado' faz sentido em Beleza?"), nunca o número.

Duas garantias que sustentam isso:
  1. Toda contagem devolvida aqui vem da tabela de contingência da Camada 1.
     Se o modelo citar um número, ele é ignorado — a célula é reconciliada por
     (valor_a, valor_b) contra o determinístico, e célula que não existe lá é
     descartada.
  2. Todo item sai com origem="sugestao_ia_pendente_revisao". É insumo para
     revisão humana, nunca achado confirmado.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .agent.llm import construir_llm
from .engine.auditoria import verificar_consistencia_categorica

ORIGEM_IA = "sugestao_ia_pendente_revisao"

_MAX_CELULAS_NO_PROMPT = 60

_INSTRUCAO = """Você é um auditor de qualidade de dados de e-commerce.

Abaixo está uma tabela de contingência REAL (contagens já apuradas por código
determinístico) entre duas colunas categóricas da base "{tabela}":
coluna_a = {coluna_a}, coluna_b = {coluna_b}.

{tabela_texto}

Avalie célula por célula se a combinação faz sentido de DOMÍNIO. Exemplo do
tipo de incoerência procurada: um motivo de devolução "Tamanho errado" em uma
categoria de produto onde tamanho não é atributo aplicável.

Responda SOMENTE com um JSON válido, sem texto fora dele, nesta forma:
{{"suspeitas": [{{"valor_a": "...", "valor_b": "...", "justificativa": "..."}}]}}

Regras:
- NÃO invente contagens. Não escreva números de registros: eles já são
  conhecidos e serão preenchidos pelo código.
- Inclua apenas combinações que você considera incoerentes. Se todas fizerem
  sentido, devolva {{"suspeitas": []}}.
- A justificativa deve explicar por que a combinação é implausível no domínio,
  em uma frase."""


def _tabela_para_texto(consistencia: dict) -> str:
    ca, cb = consistencia["coluna_a"], consistencia["coluna_b"]
    linhas = [f"{ca} | {cb} | registros"]
    for c in consistencia["celulas"][:_MAX_CELULAS_NO_PROMPT]:
        linhas.append(f"{c[ca]} | {c[cb]} | {c['registros']}")
    return "\n".join(linhas)


def _extrair_json(texto: str) -> dict:
    """O modelo às vezes embrulha o JSON em markdown ou em prosa."""
    try:
        return json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r"\{.*\}", texto or "", re.DOTALL)
    if not m:
        raise ValueError("resposta do modelo não contém JSON")
    return json.loads(m.group(0))


def sugerir_inconsistencias_semanticas(tabela: str, coluna_a: str, coluna_b: str,
                                       llm: Any = None, modelo: str | None = None) -> dict:
    """Suspeitas de incoerência semântica entre duas colunas categóricas.

    Nunca levanta exceção por falha do modelo: devolve
    {"disponivel": False, "motivo": ...} para não derrubar um relatório maior
    que dependa disso.
    """
    try:
        consistencia = verificar_consistencia_categorica(tabela, coluna_a, coluna_b)
    except Exception as e:
        return {"disponivel": False,
                "motivo": f"camada determinística falhou: {type(e).__name__}: {e}"}

    try:
        from . import config
        cliente = llm if llm is not None else construir_llm()
        prompt = _INSTRUCAO.format(
            tabela=tabela, coluna_a=coluna_a, coluna_b=coluna_b,
            tabela_texto=_tabela_para_texto(consistencia),
        )
        msg = cliente.completar([{"role": "user", "content": prompt}],
                                modelo or config.MODELO_SINTESE)
        bruto = (getattr(msg, "content", None) or "").strip()
        payload = _extrair_json(bruto)
    except Exception as e:
        return {"disponivel": False,
                "motivo": f"{type(e).__name__}: {e}",
                "tabela": tabela, "coluna_a": coluna_a, "coluna_b": coluna_b}

    # Reconcilia cada suspeita contra a contagem determinística. O número NUNCA
    # vem do modelo: célula que não existe na Camada 1 é descartada.
    por_chave = {(c[coluna_a], c[coluna_b]): c for c in consistencia["celulas"]}
    alertas, descartadas = [], []
    for s in (payload.get("suspeitas") or []):
        if not isinstance(s, dict):
            continue
        chave = (str(s.get("valor_a", "")), str(s.get("valor_b", "")))
        celula = por_chave.get(chave)
        if celula is None:
            descartadas.append({"valor_a": chave[0], "valor_b": chave[1],
                                "motivo": "combinação não existe na tabela determinística"})
            continue
        alertas.append({
            "tabela": tabela,
            "coluna_a": coluna_a, "valor_a": chave[0],
            "coluna_b": coluna_b, "valor_b": chave[1],
            "registros_afetados": celula["registros"],          # Camada 1
            "pct_do_total": celula["pct_do_total"],             # Camada 1
            "justificativa_ia": str(s.get("justificativa", "")).strip(),
            "origem": ORIGEM_IA,
        })
    alertas.sort(key=lambda a: a["registros_afetados"], reverse=True)

    return {
        "disponivel": True,
        "tabela": tabela, "coluna_a": coluna_a, "coluna_b": coluna_b,
        "registros_considerados": consistencia["registros_considerados"],
        "alertas": alertas,
        "total_alertas": len(alertas),
        "registros_sob_suspeita": sum(a["registros_afetados"] for a in alertas),
        "sugestoes_descartadas": descartadas,
        "nota": ("suspeita de IA pendente de revisão humana — não é achado "
                 "confirmado. As contagens vêm da camada determinística; "
                 "números citados pelo modelo são ignorados."),
    }
