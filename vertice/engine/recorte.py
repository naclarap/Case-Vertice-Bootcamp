"""Recorte da base: a única fonte de verdade sobre QUAL população é simulada.

Por que este módulo existe
--------------------------
O motor e o deck do case calculavam a mesma coisa sobre populações diferentes, e
os dois estavam certos dentro da própria convenção. O teto de 20% valia
R$ 369.836,50 no motor (13 meses, com novembro, com pedidos devolvidos) e
R$ 241.424,23 no deck (2023, sem novembro, só pedidos mantidos). Como o recorte
não era parâmetro de nada, não havia como pedir um ou outro — nem como saber,
lendo a resposta, qual deles tinha sido usado.

A correção não é escolher um número: é tornar o recorte um PARÂMETRO EXPLÍCITO,
com padrão declarado e sempre devolvido no resultado. Quem lê a resposta vê a
população; quem lê o trace reconstrói a chamada.

As duas convenções
------------------
DECISAO     — a base sobre a qual o comitê decide. Ano-calendário de 2023,
              pedidos mantidos (não devolvidos) e novembro fora, porque
              novembro é Black Friday e fica sob orçamento de campanha
              aprovado, não sob a política de teto.
DIAGNOSTICO — toda a base aprovada, 13 meses, nada excluído. É a leitura de
              diagnóstico: nenhum recorte que possa parecer escolhido para
              favorecer o resultado.

Nenhuma das duas é filtro escondido. `descrever_recorte()` devolve a descrição
em português que acompanha todo resultado, e é ela que a resposta final deve
citar junto do número.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .. import config

# ---------------------------------------------------------------- convenções
DECISAO = "decisao"
DIAGNOSTICO = "diagnostico"

CONVENCOES: dict[str, dict[str, Any]] = {
    DECISAO: {
        "ano": config.ANO_BASE,
        "excluir_meses": list(config.MESES_FORA_DO_TETO),
        "excluir_devolvidos": True,
    },
    DIAGNOSTICO: {
        "ano": None,
        "excluir_meses": [],
        "excluir_devolvidos": False,
    },
}

_MESES_NOME = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio", 6: "junho",
    7: "julho", 8: "agosto", 9: "setembro", 10: "outubro", 11: "novembro",
    12: "dezembro",
}


def _meses(valor: Any) -> list[int]:
    """Normaliza o que o usuário ou o modelo escreveu para uma lista de meses.

    Aceita 11, "11", [11], "novembro", ["novembro", "dezembro"], "nov" e a
    string vazia (= não excluir nada). Mês desconhecido levanta erro listando os
    aceitos, NUNCA escolhe o mais parecido: excluir o mês errado de uma
    simulação muda o número sem mudar nada na aparência da resposta.
    """
    if valor is None:
        return []
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto or texto.lower() in ("[]", "nenhum", "none"):
            return []
        bruto = [p.strip() for p in texto.strip("[]").split(",") if p.strip()]
    elif isinstance(valor, (int, float)):
        bruto = [valor]
    else:
        bruto = list(valor)

    from .filtros import MESES_PT

    saida: list[int] = []
    for item in bruto:
        if isinstance(item, (int, float)):
            n = int(item)
        else:
            chave = str(item).strip().strip("'\"").lower()
            if chave.isdigit():
                n = int(chave)
            elif chave in MESES_PT:
                n = MESES_PT[chave]
            else:
                achou = [v for k, v in MESES_PT.items() if k.startswith(chave)]
                if len(set(achou)) != 1:
                    raise ValueError(
                        f"mês '{item}' não reconhecido. Use o número (1 a 12) ou o "
                        f"nome por extenso: {', '.join(_MESES_NOME.values())}"
                    )
                n = achou[0]
        if not 1 <= n <= 12:
            raise ValueError(f"mês fora da faixa 1–12: {n}")
        saida.append(n)
    return sorted(set(saida))


def resolver(convencao: str | None = None, ano: Any = None,
             excluir_meses: Any = None,
             excluir_devolvidos: Any = None) -> dict[str, Any]:
    """Monta o recorte final: convenção de base + sobreposições explícitas.

    A convenção define o ponto de partida; cada parâmetro informado sobrepõe
    apenas o seu próprio campo. Assim "e se incluirmos novembro?" é
    `excluir_meses=[]` e NÃO desliga o filtro de pedidos devolvidos junto.
    """
    nome = (convencao or config.CONVENCAO_PADRAO or DECISAO).strip().lower()
    if nome not in CONVENCOES:
        raise ValueError(
            f"convencao '{convencao}' inválida. Use '{DECISAO}' (base de decisão do "
            f"caso: {config.ANO_BASE}, pedidos mantidos, novembro fora) ou "
            f"'{DIAGNOSTICO}' (toda a base aprovada)."
        )
    r = dict(CONVENCOES[nome])
    r["convencao"] = nome
    r["sobreposto"] = []

    if ano is not None and str(ano).strip() != "":
        r["ano"] = int(ano)
        r["sobreposto"].append("ano")
    if excluir_meses is not None:
        r["excluir_meses"] = _meses(excluir_meses)
        r["sobreposto"].append("excluir_meses")
    if excluir_devolvidos is not None:
        if isinstance(excluir_devolvidos, str):
            r["excluir_devolvidos"] = excluir_devolvidos.strip().lower() in (
                "1", "true", "sim", "yes", "t")
        else:
            r["excluir_devolvidos"] = bool(excluir_devolvidos)
        r["sobreposto"].append("excluir_devolvidos")
    return r


def descrever(r: dict[str, Any]) -> str:
    """Frase em português que a resposta final deve citar junto do número."""
    partes = []
    partes.append(f"ano {r['ano']}" if r.get("ano") else "toda a base (13 meses)")
    partes.append("pedidos aprovados")
    if r.get("excluir_devolvidos"):
        partes.append("mantidos (não devolvidos)")
    if r.get("excluir_meses"):
        nomes = ", ".join(_MESES_NOME[m] for m in r["excluir_meses"])
        partes.append(f"sem {nomes}")
    base = " · ".join(partes)
    if r.get("convencao") == DECISAO and not r.get("sobreposto"):
        return (f"{base} — base de DECISÃO do caso; novembro fica fora do teto "
                f"por ser Black Friday, sob orçamento de campanha aprovado")
    return base


def aplicar(df: pd.DataFrame, r: dict[str, Any]) -> pd.DataFrame:
    """Aplica o recorte a um DataFrame já carregado (aprovados ou não)."""
    out = df
    if r.get("ano"):
        out = out[out["ano"] == int(r["ano"])]
    if r.get("excluir_meses"):
        out = out[~out["data_pedido"].dt.month.isin(r["excluir_meses"])]
    if r.get("excluir_devolvidos") and "devolvido" in out.columns:
        out = out[~out["devolvido"]]
    return out


def bloco(r: dict[str, Any], df: pd.DataFrame) -> dict[str, Any]:
    """O campo `recorte_aplicado` que acompanha todo resultado recortado."""
    d = pd.to_datetime(df["data_pedido"])
    ini, fim = d.min(), d.max()
    meses_obs = df["data_pedido"].dt.to_period("M").nunique()
    return {
        "convencao": r.get("convencao"),
        "ano": r.get("ano"),
        "meses_excluidos": [_MESES_NOME[m] for m in r.get("excluir_meses", [])],
        "pedidos_devolvidos_excluidos": bool(r.get("excluir_devolvidos")),
        "parametros_sobrepostos_na_chamada": r.get("sobreposto", []),
        "pedidos_no_recorte": int(len(df)),
        "primeiro_pedido": str(ini.date()),
        "ultimo_pedido": str(fim.date()),
        "meses_observados": int(meses_obs),
        "descricao": descrever(r),
        "obrigatorio_citar": (
            "todo valor em R$ deste resultado vale para ESTE recorte; cite-o junto "
            "do número na resposta final"
        ),
    }
