"""Card estruturado para o dashboard, derivado de uma investigação concluída.

O agente foi pensado como módulo de recomendação DENTRO do painel de vendas,
não como chat separado — e um componente visual não consome texto livre em 4
seções. Este módulo extrai, do trace já concluído, os campos que o card precisa.

Não substitui a resposta em FATO/INFERÊNCIA/RECOMENDAÇÃO/FORÇA DA EVIDÊNCIA:
é gerado a partir dela. E os números NÃO são reformulados pelo modelo — saem
das observações de ferramenta do próprio trace, a mesma fonte que alimenta a
verificação numérica. Se a investigação não produziu número de impacto, o campo
vem None: card sem número é melhor que card com número inventado.
"""
from __future__ import annotations

import re
from typing import Any

from .react import _corpo_da_secao, _forca_alegada, RE_SECAO

# Chaves de impacto em R$ que as ferramentas do motor devolvem, em ordem de
# preferência: efeito consolidado de uma simulação primeiro, depois o valor
# recuperável/evitável de um diagnóstico.
CHAVES_IMPACTO_RS = (
    "impacto_reais",
    "margem_recuperada_reais",
    "frete_evitavel_reais",
    "perda_total_reais",
    "margem_perdida_total_reais",
)

# Impacto em pontos percentuais. "consolidado" antes de "no_canal": o card vive
# no painel da empresa, onde o efeito no total é o que ancora a decisão.
CHAVES_IMPACTO_PP = (
    "ganho_margem_pp_consolidado",
    "impacto_pp_na_margem_consolidada",
    "ganho_margem_pp",
    "variacao_pp",
    "ganho_margem_pp_no_canal",
)

FORCAS = {"FORTE": "forte", "MODERADA": "moderada", "FRACA": "fraca"}


def _achatar(obj: Any, prefixo: str = "") -> dict[str, Any]:
    """Achata dict/lista aninhados em {chave: valor} para procurar as chaves de
    impacto em qualquer profundidade (ex: efeito_consolidado.impacto_reais)."""
    plano: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                plano.update(_achatar(v, k))
            else:
                plano.setdefault(k, v)
    elif isinstance(obj, list):
        for item in obj:
            plano.update(_achatar(item, prefixo))
    return plano


def _numeros_das_observacoes(trace) -> dict[str, Any]:
    """Só observações de ferramenta — nunca o texto do modelo."""
    plano: dict[str, Any] = {}
    for p in trace.passos:
        if p.tipo == "observacao":
            for k, v in _achatar(p.conteudo).items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    plano.setdefault(k, v)
    return plano


def _primeiro_valor(plano: dict[str, Any], chaves: tuple[str, ...]) -> float | None:
    for c in chaves:
        if c in plano:
            return float(plano[c])
    return None


def _frase_curta(texto: str, limite: int = 240) -> str:
    """Primeira frase útil de uma seção, sem markdown nem numeração de lista."""
    limpo = re.sub(r"[*_`#]", "", texto or "").strip()
    limpo = re.sub(r"^\s*(?:\d+[.)]|[-•])\s*", "", limpo, flags=re.MULTILINE)
    linhas = [l.strip() for l in limpo.splitlines() if l.strip()]
    if not linhas:
        return ""
    frase = linhas[0]
    corte = re.split(r"(?<=[.!?])\s", frase)
    return (corte[0] if corte else frase)[:limite].strip()


def _posicoes(texto: str) -> dict[str, int | None]:
    return {nome: (m.start() if (m := RE_SECAO[nome].search(texto)) else None)
            for nome in RE_SECAO}


def gerar_card(trace, titulo: str | None = None) -> dict:
    """Objeto estruturado para o painel, a partir de um trace já concluído.

    `titulo`: opcional. Sem ele, é derivado da pergunta do usuário — não é um
    campo calculado, é rótulo, então pode vir do texto sem risco numérico.
    """
    resposta = trace.resposta_final or ""
    pos = _posicoes(resposta)
    recomendacao = _frase_curta(_corpo_da_secao(resposta, "RECOMENDAÇÃO", pos))

    palavra = _forca_alegada(resposta)
    forca = FORCAS.get(palavra or "", "fraca")

    plano = _numeros_das_observacoes(trace)
    return {
        "titulo": (titulo or trace.pergunta or "Recomendação").strip()[:120],
        "recomendacao": recomendacao,
        "impacto_rs": _primeiro_valor(plano, CHAVES_IMPACTO_RS),
        "impacto_pp": _primeiro_valor(plano, CHAVES_IMPACTO_PP),
        "forca_evidencia": forca,
        "fontes": list(dict.fromkeys(trace.ferramentas_usadas)),
        "trace_id": trace.id,
        "origem_consulta": getattr(trace, "origem_consulta", "ad_hoc"),
    }
