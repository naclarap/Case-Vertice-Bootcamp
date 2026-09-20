"""Normalização determinística dos valores de filtro (mês, canal, categoria).

Motivo de existir: a pergunta chega em português — "30% no Marketplace em
novembro" — e o modelo transcreve o que leu. O motor exigia exatamente
'2023-11' e 'Marketplace', então `mes='novembro'` e `canal='marketplace'`
levantavam ValueError. Em produção isso custou a resposta inteira: o agente
tentou 'novembro', depois '11', depois 'novembro/2023', gastou as iterações e
respondeu "a ferramenta não retornou resultado".

A correção é no motor, não no prompt: aceitar a forma como a pessoa escreve é
determinístico e testável; pedir ao modelo que acerte o formato é torcer. Nada
aqui adivinha dado — só traduz o rótulo para o valor que existe na base, e
levanta erro listando as opções quando a tradução é ambígua ou impossível.
"""
from __future__ import annotations

import re
import unicodedata

MESES_PT = {
    "janeiro": 1, "jan": 1, "fevereiro": 2, "fev": 2, "marco": 3, "mar": 3,
    "abril": 4, "abr": 4, "maio": 5, "mai": 5, "junho": 6, "jun": 6,
    "julho": 7, "jul": 7, "agosto": 8, "ago": 8, "setembro": 9, "set": 9,
    "outubro": 10, "out": 10, "novembro": 11, "nov": 11, "dezembro": 12, "dez": 12,
}


def _chave(texto: str) -> str:
    """Minúsculas sem acento — 'Acessórios' e 'acessorios' viram a mesma chave."""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.strip().lower()


def _numero_do_mes(texto: str) -> tuple[int | None, int | None]:
    """(mes, ano) a partir do que a pessoa escreveu. ano=None quando não foi dito."""
    t = _chave(texto).replace(" de ", " ")

    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})", t)          # 2023-11, 2023/11
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.fullmatch(r"(\d{1,2})[-/](\d{4})", t)          # 11/2023
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.fullmatch(r"(\d{1,2})", t)                      # 11
    if m:
        return int(m.group(1)), None

    # nome do mês, com ou sem ano: "novembro", "nov 2023", "novembro/2023"
    palavras = re.split(r"[\s/\-]+", t)
    nome = next((p for p in palavras if p in MESES_PT), None)
    if nome is None:
        return None, None
    ano = next((int(p) for p in palavras if re.fullmatch(r"\d{4}", p)), None)
    return MESES_PT[nome], ano


def normalizar_mes(valor, disponiveis: list[str]) -> str:
    """Devolve o mês no formato AAAA-MM que existe na base.

    Aceita '2023-11', '11/2023', 'novembro', 'nov', 'novembro de 2023', '11'.
    Sem o ano, resolve sozinho SE só existir um ano com aquele mês na base;
    havendo mais de um, levanta erro listando os candidatos em vez de escolher.
    """
    bruto = str(valor).strip()
    if bruto in disponiveis:
        return bruto

    mes, ano = _numero_do_mes(bruto)
    if mes is None or not 1 <= mes <= 12:
        raise ValueError(
            f"mes '{valor}' não reconhecido. Use AAAA-MM (ex '2023-11') ou o nome do "
            f"mês (ex 'novembro'). Disponíveis: {disponiveis}"
        )

    if ano is not None:
        alvo = f"{ano:04d}-{mes:02d}"
        if alvo not in disponiveis:
            raise ValueError(f"mes '{valor}' (={alvo}) inexistente. Disponíveis: {disponiveis}")
        return alvo

    candidatos = [d for d in disponiveis if d.endswith(f"-{mes:02d}")]
    if not candidatos:
        raise ValueError(f"mes '{valor}' inexistente na base. Disponíveis: {disponiveis}")
    if len(candidatos) > 1:
        raise ValueError(
            f"mes '{valor}' é ambíguo: a base tem {candidatos}. Informe o ano "
            f"(ex '{candidatos[-1]}')."
        )
    return candidatos[0]


def normalizar_categorico(coluna: str, valor, disponiveis: list[str]) -> str:
    """Casa o valor com o que existe na coluna, ignorando caixa e acento.

    'marketplace' -> 'Marketplace', 'tiktok ads' -> 'TikTok Ads'. Sem match,
    levanta erro listando as opções — nunca escolhe a "mais parecida".
    """
    bruto = str(valor).strip()
    if bruto in disponiveis:
        return bruto
    mapa = {_chave(d): d for d in disponiveis}
    achado = mapa.get(_chave(bruto))
    if achado is None:
        raise ValueError(f"{coluna} '{valor}' inexistente. Disponíveis: {disponiveis}")
    return achado


def normalizar_filtro(coluna: str, valor, disponiveis: list[str]) -> str:
    """Ponto único de entrada: mês tem regra própria, o resto é categórico."""
    if coluna == "mes":
        return normalizar_mes(valor, disponiveis)
    return normalizar_categorico(coluna, valor, disponiveis)
