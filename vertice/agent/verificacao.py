"""Verificação de que todo número da resposta veio de uma ferramenta.

Esta é a garantia central do projeto: o LLM não calcula. O system prompt pede
isso, mas pedir não basta — em produção o modelo multiplicou receita por desconto
e apresentou o produto como se fosse dado apurado. Este módulo transforma a regra
em verificação executável: cada número da resposta final é confrontado com os
números que realmente apareceram nas observações de ferramenta.
"""
from __future__ import annotations

import re
from typing import Any

# Espaços que modelos usam como separador de milhar: comum, não-quebrável e
# estreito não-quebrável. O gpt-oss-120b escreve "R$ 34 973,55".
_ESPACOS = " \u00a0\u202f\u2009"

# Números em formato brasileiro (1.234.567,89), agrupados por espaço
# (34 973,55) ou simples (1234.56 / 1234).
#
# O agrupamento por espaço vem primeiro na alternância, senão o motor casa só
# "34" e deixa "973,55" solto — e foi assim que uma resposta correta teve cinco
# números legítimos acusados de inventados: eram os finais de 34.973,55,
# 21.162,40, 13.811,15, 9.058.427,55 e 9.072.238,70.
#
# O `(?:[\d.]*\d)?` do meio existe para o número NÃO poder terminar em ponto: o
# ponto final da frase era engolido. "V de Cramér é 0.0127." virava "0.0127.",
# cuja única leitura possível era 127 — e um número que veio direto da
# ferramenta foi acusado de inventado, bloqueando uma resposta correta. Com o
# decimal em vírgula o bug não aparecia (o casamento termina no ,\d+), então só
# mordia quando o modelo escrevia no formato en-US.
RE_NUMERO = re.compile(
    rf"-?\d{{1,3}}(?:[{_ESPACOS}]\d{{3}})+(?:,\d+)?"
    rf"|-?\d(?:[\d.]*\d)?(?:,\d+)?"
    rf"|-?\d+\.\d+")

# Abaixo deste número de dígitos significativos, não verificamos: são valores como
# 30%, 60%, 100% — retórica, não apuração. O risco de falso positivo supera o ganho.
MIN_DIGITOS = 4


def _interpretacoes(bruto: str) -> list[float]:
    """Devolve as leituras plausíveis de um número escrito por um LLM.

    '1.234' pode ser 1234 (milhar pt-BR) ou 1.234 (decimal en-US). Geramos as
    duas e aceitamos se QUALQUER uma casar: na dúvida, não acusamos.
    """
    txt = bruto.strip().rstrip("%")
    saidas: list[float] = []

    # Agrupado por espaço: "34 973,55" lê-se 34973,55. APENAS a leitura junta
    # entra aqui. Devolver também as partes soltas abriu um buraco grave: "9 820
    # 000" produzia [9820000, 9, 820, 0] e o "0" casava com qualquer resultado de
    # ferramenta, aprovando um número inventado. As partes são tratadas à parte,
    # em _partes_agrupadas, sob regra bem mais dura.
    if any(e in txt for e in _ESPACOS):
        junto = txt
        for e in _ESPACOS:
            junto = junto.replace(e, "")
        try:
            saidas.append(float(junto.replace(".", "").replace(",", ".")))
        except ValueError:
            pass
        return saidas
    if "," in txt:                       # vírgula decimal: ponto é milhar
        try:
            saidas.append(float(txt.replace(".", "").replace(",", ".")))
        except ValueError:
            pass
    else:
        try:                             # ponto como milhar
            saidas.append(float(txt.replace(".", "")))
        except ValueError:
            pass
        try:                             # ponto como decimal
            saidas.append(float(txt))
        except ValueError:
            pass
    return saidas


RE_COMPARADOR = re.compile(r"(?:<=|>=|<|>|≤|≥|≪|≫)\s*$")

# Estatística anunciada pelo nome: "R² = 0,85", "p-valor = 0,03", "F de 2,89".
# Existe porque MIN_DIGITOS abria um buraco previsível — um R² inventado com
# duas casas (0,85) tinha poucos dígitos e nunca era conferido, enquanto o
# mesmo R² real do motor (0,5185) era. Um número que o texto apresenta como
# resultado de teste é apuração por definição: não há caso em que ele possa
# ser retórica, então o piso de dígitos não se aplica a ele.
RE_ESTATISTICA_NOMEADA = re.compile(
    r"(?:^|[^0-9A-Za-zÀ-ÿ])"
    r"(?:r²|r2|r[-\s]?quadrado|eta²|eta2|η²|eta[-\s]?quadrado|f|t|p|"
    r"p[-\s]?valor|p[-\s]?value|"
    r"correlacao|correlação|coeficiente)"
    r"\s*(?:=|:|\bde\b)\s*$", re.I)

# Ruído de notação que o modelo coloca em volta do nome da estatística. O Gemini
# escreve em LaTeX: "$R^2 = 0,85$", "$\eta^2$ (eta-quadrado) de 0,513". Sem
# limpar isso, "R^2" não casa com o rótulo "r2" e o número volta a escapar pelo
# piso de dígitos — foi assim que um R² inventado passou DEPOIS da correção
# anterior, que só conhecia a forma "R²".
_RUIDO_DE_NOTACAO = str.maketrans("", "", "$\\^{}*`()")


def _e_estatistica_nomeada(texto: str, inicio: int) -> bool:
    """O número vem logo depois do nome de uma estatística ("R² = ", "$R^2 = ")."""
    janela = texto[max(0, inicio - 28):inicio].translate(_RUIDO_DE_NOTACAO)
    return bool(RE_ESTATISTICA_NOMEADA.search(janela))


def _e_limiar(texto: str, inicio: int) -> bool:
    """O número vem logo depois de um comparador — é um limite declarado, não
    uma medida afirmada. Distingue "p<0,001" de "p-valor = 0,00002"."""
    return bool(RE_COMPARADOR.search(texto[max(0, inicio - 12):inicio]))


# Cauda de notação científica logo depois do número: "e-52", "E-7",
# "× 10^{-19}", "x10^-19". O modelo escreve p-valores assim, e sem ler o
# expoente a mantissa vira um número solto ("3,09") que não existe em ferramenta
# nenhuma — falso positivo garantido justo na estatística que a regra de rótulo
# passou a conferir.
# Duas formas, e a diferença entre elas importa: a forma com "e" precisa vir
# COLADA no número, senão "entre 2023 e 2024" é lido como 2023×10²⁰² — o "e" da
# conjunção em português ocupa o mesmo lugar do "e" da notação. A forma com
# ×10 pode ter espaços porque não é ambígua.
RE_EXPOENTE = re.compile(
    r"^(?:[eE][+-]?\d{1,3}(?!\d|[.,]\d)"
    r"|\s*(?:\\times|[×xX\*])\s*10\s*\^?\s*\{?\s*([+-]?\d{1,3})\s*\}?)")


def _expoente_depois(texto: str, fim: int) -> int | None:
    m = RE_EXPOENTE.match(texto[fim:fim + 24])
    if not m:
        return None
    if m.group(1) is not None:            # forma "× 10^-19"
        return int(m.group(1))
    return int(m.group(0).lstrip("eE"))   # forma colada "e-19"


def _digitos_significativos(bruto: str) -> int:
    """Quantos dígitos o modelo realmente escreveu na mantissa."""
    return len(re.sub(r"\D", "", bruto).lstrip("0")) or 1


def _casa_cientifica(valor: float, conhecidos: set[float], significativos: int) -> bool:
    """Compara 3,09e-19 com 3,0871979...e-19.

    Arredondar em CASAS DECIMAIS não serve aqui: round(3,087e-19, 6) é zero. A
    comparação é por dígitos significativos, e só para número escrito em
    notação científica — aplicar isso a valor comum aceitaria "R$ 200.000" como
    leitura de 207.099,18.
    """
    for c in conhecidos:
        if c == 0:
            continue
        for k in range(max(1, significativos - 1), significativos + 2):
            if float(f"%.{k - 1}e" % c) == valor:
                return True
    return False


def _partes_agrupadas(bruto: str) -> list[float]:
    """Leitura alternativa de um número separado por espaços: dois (ou mais)
    números distintos que o espaço colou, como "166 843" em "166 dos 843".

    Só vale se TODAS as partes vierem de ferramenta — ver verificar_numeros.
    Exigir todas é o que separa "166 843" (dois números reais) de "9 820 000"
    (inventado, cujo "0" casaria com qualquer coisa sozinho).
    """
    if not any(e in bruto for e in _ESPACOS):
        return []
    partes: list[float] = []
    for pedaco in re.split(f"[{_ESPACOS}]", bruto.strip().rstrip("%")):
        try:
            partes.append(float(pedaco.replace(".", "").replace(",", ".")))
        except ValueError:
            return []
    return partes


def _digitos(bruto: str) -> int:
    return len(re.sub(r"\D", "", bruto))


# Chaves cujo conteúdo NÃO é apuração e não pode entrar no conjunto rastreável.
# `hash_base` é o caso perigoso: um hash hexadecimal contém dígitos, e deixá-lo
# entrar daria lastro falso a qualquer número que casasse com um pedaço dele —
# exatamente o buraco que fechou a falha nº 2 do histórico do guardrail.
CHAVES_NAO_APURACAO = frozenset({"hash_base", "marca", "ferramenta"})


def coletar_numeros(obj: Any, destino: set[float] | None = None) -> set[float]:
    """Extrai recursivamente todo valor numérico de um retorno de ferramenta."""
    destino = destino if destino is not None else set()
    if isinstance(obj, bool):
        return destino
    if isinstance(obj, (int, float)):
        destino.add(float(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k in CHAVES_NAO_APURACAO:
                continue
            coletar_numeros(k, destino)
            coletar_numeros(v, destino)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            coletar_numeros(v, destino)
    elif isinstance(obj, str):
        # Strings de ferramenta também podem carregar números (ex.: mensagens).
        for m in RE_NUMERO.finditer(obj):
            for v in _interpretacoes(m.group()):
                destino.add(v)
    return destino


def _tolerancia(valor: float, c: float) -> float:
    """Folga aceitável entre o que o texto diz e o que a ferramenta devolveu.

    O piso absoluto de 0,02 existia para o arredondamento de valores do dia a
    dia (47,5712 citado como 47,57). Aplicado a números PEQUENOS ele virou um
    buraco: qualquer valor abaixo de 0,02 casava com o 0.0 que praticamente todo
    resultado de ferramenta contém — e foi assim que um p-valor inventado
    (0,00002) passou pela verificação. Abaixo de 1, a tolerância é proporcional.
    """
    escala = max(abs(valor), abs(c))
    if escala < 1:
        return max(escala * 1e-6, 1e-12)
    return max(0.02, escala * 1e-6)


def _casa(valor: float, conhecidos: set[float]) -> bool:
    """O valor bate com algum número de ferramenta, tolerando arredondamento."""
    for c in conhecidos:
        if abs(valor - c) <= _tolerancia(valor, c):
            return True
        # O modelo pode arredondar: 47,57 a partir de 47,5712…, e um p-valor
        # citado como 0,0019 vem de 0,00185706…, então a busca vai até a sexta
        # casa. A comparação continua exata (1e-9): arredondar mais fundo não
        # afrouxa nada — quem afrouxava era o piso absoluto de tolerância.
        for casas in range(0, 7):
            if abs(valor - round(c, casas)) <= 1e-9:
                return True
        # …ou citar em pontos percentuais um valor devolvido como fração.
        if abs(valor - c * 100) <= _tolerancia(valor, c * 100):
            return True
        # …ou citar a MAGNITUDE de um valor negativo, com a direção já dita por
        # um verbo/substantivo ("caiu 22,17 pontos", "queda de 22,17pp") em vez
        # de repetir o sinal. Falso positivo real observado: a ferramenta
        # devolveu variacao_pp=-22.17, o texto disse apenas "22,17" — o número
        # é o mesmo, só sem o sinal que a palavra "caiu" já carrega.
        if abs(valor - abs(c)) <= _tolerancia(valor, c):
            return True
    return False


def verificar_numeros(resposta: str, numeros_ferramenta: set[float],
                      contexto_livre: str = "") -> dict:
    """Confere se os números da resposta vieram de ferramenta.

    `contexto_livre` é a pergunta do usuário: números que a própria pergunta traz
    (ex.: "30% de desconto") são premissas do cenário, não apuração, e não contam
    como inventados.
    """
    da_pergunta: set[float] = set()
    for m in RE_NUMERO.finditer(contexto_livre or ""):
        da_pergunta.update(_interpretacoes(m.group()))

    suspeitos: list[str] = []
    verificados = 0
    limiares = 0
    texto = resposta or ""
    for m in RE_NUMERO.finditer(texto):
        bruto = m.group()
        if _digitos(bruto) < MIN_DIGITOS and not _e_estatistica_nomeada(texto, m.start()):
            continue
        # "p<0,001" é um LIMIAR (afirmação de que o valor está abaixo de algo),
        # não um valor apurado: o 0,001 não precisa existir em ferramenta
        # nenhuma. Exigir isso rejeitava resposta correta que usa a notação
        # convencional de significância. Já "p-valor = 0,00002" é afirmação de
        # medida e continua sendo verificada.
        if _e_limiar(texto, m.start()):
            limiares += 1
            continue
        leituras = _interpretacoes(bruto)
        if not leituras:
            continue
        # Anos não são apuração.
        if all(v.is_integer() and 1900 <= v <= 2100 for v in leituras):
            continue
        if any(_casa(v, da_pergunta) for v in leituras):
            continue
        expoente = _expoente_depois(texto, m.end())
        if expoente is not None:
            sig = _digitos_significativos(bruto)
            # Monta o valor pela STRING, não multiplicando: 3.09 * 10**-19 dá
            # 3.0899999999999995e-19, que não é igual a float("3.09e-19") — e a
            # comparação por dígitos significativos, que é exata, falhava por
            # erro de ponto flutuante num número correto.
            escalados = [float(f"{v!r}e{expoente}") for v in leituras]
            if any(_casa(v, da_pergunta) for v in escalados):
                continue
            verificados += 1
            if not any(_casa_cientifica(v, numeros_ferramenta, sig) for v in escalados):
                if bruto not in suspeitos:
                    suspeitos.append(bruto)
            continue
        verificados += 1
        if any(_casa(v, numeros_ferramenta) for v in leituras):
            continue
        # Última chance: o espaço pode ter colado dois números reais. Aceita só
        # se TODAS as partes vierem de ferramenta.
        partes = _partes_agrupadas(bruto)
        if partes and all(_casa(pe, numeros_ferramenta) for pe in partes):
            continue
        if bruto not in suspeitos:
            suspeitos.append(bruto)
    return {
        "ok": not suspeitos,
        "numeros_verificados": verificados,
        "limiares_ignorados": limiares,
        "suspeitos": suspeitos,
        "n_numeros_de_ferramenta": len(numeros_ferramenta),
    }
