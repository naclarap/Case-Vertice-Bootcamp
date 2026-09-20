"""Política de desconto e alçadas de aprovação — a régua, aplicada ao dado.

O bloco de perguntas de governança do case ("Esse desconto está dentro da
política?", "Quem precisa aprovar 17%?", "Existe desconto acima do limite?",
"Como identificar tentativa de contornar a política?") não tinha nenhuma
ferramenta: as doze caíam em PERGUNTA_COMPLEXA e o modelo respondia de cabeça —
o pior caso possível, porque uma alçada inventada parece uma alçada de verdade.

Separação que este módulo mantém explícita em todo retorno:

  * o TETO vem de `politica.politica_vigente()` — estado registrado, com dono e
    vigência. Não havendo política registrada, o resultado diz isso em vez de
    escolher um número;
  * as ALÇADAS vêm de `config.alcadas()` — régua de governança da empresa,
    configurável, jamais derivada dos dados;
  * as CONTAGENS vêm da base, sempre.

`origem_do_teto` e `origem_das_alcadas` acompanham a resposta justamente para
que a síntese não apresente régua como apuração.
"""
from __future__ import annotations

import pandas as pd

from .. import config
from ..data import carregar_vendas
from .filtros import normalizar_filtro
from .registry import ferramenta


def _pct(valor) -> float:
    """Aceita 17 e 0,17 como o mesmo desconto — igual aos simuladores."""
    v = float(valor)
    return round(v * 100, 4) if v <= 1 else round(v, 4)


def _recorte(df: pd.DataFrame, canal, categoria) -> tuple[pd.DataFrame, dict]:
    usado: dict[str, str] = {}
    for coluna, valor in (("canal", canal), ("categoria", categoria)):
        if valor in (None, ""):
            continue
        alvo = normalizar_filtro(coluna, valor,
                                 sorted(df[coluna].dropna().astype(str).unique()))
        df = df[df[coluna] == alvo]
        usado[coluna] = alvo
    return df, usado


def _faixa_de_alcada(pct: float) -> tuple[dict, list[dict], str]:
    faixas, origem = config.alcadas()
    ordenadas = sorted(faixas, key=lambda f: float(f["ate_pct"]))
    escolhida = next((f for f in ordenadas if pct <= float(f["ate_pct"])), ordenadas[-1])
    anterior = 0.0
    for f in ordenadas:
        f["faixa"] = f"acima de {anterior:g}% até {float(f['ate_pct']):g}%"
        anterior = float(f["ate_pct"])
    return escolhida, ordenadas, origem


def _teto_vigente(canal, categoria) -> tuple[float | None, str]:
    from ..politica import politica_vigente

    p = politica_vigente(canal, categoria)
    if p is None:
        return None, ("nenhuma política de teto registrada para este recorte — "
                      "use definir_politica() para registrar uma, com responsável")
    return p["teto_pct"], (f"politica_vigente(canal={p.get('canal')}, "
                           f"categoria={p.get('categoria')}) definida por "
                           f"{p.get('responsavel')} em {p.get('vigencia')}")


@ferramenta(
    "consultar_politica_desconto",
    """Diz se um desconto está dentro da política e QUEM precisa aprovar. O teto
    vem da política vigente registrada (politica.py, com dono e vigência); as
    alçadas vêm da configuração de governança do projeto (config.alcadas()) e
    NÃO são apuradas dos dados — o retorno traz `origem_do_teto` e
    `origem_das_alcadas` para a resposta declarar isso. Sem desconto_pct,
    devolve só a régua vigente (útil para "quando é necessária aprovação do
    gerente?").""",
    {"desconto_pct": "desconto a avaliar, ex 17 (opcional: sem ele devolve só a régua)",
     "canal": "canal do recorte (opcional)",
     "categoria": "categoria do recorte (opcional)"},
    principais=["desconto_pct"],
)
def consultar_politica_desconto(desconto_pct=None, canal: str | None = None,
                                categoria: str | None = None) -> dict:
    teto, origem_teto = _teto_vigente(canal, categoria)
    _, tabela, origem_alcadas = _faixa_de_alcada(0.0)
    saida: dict = {
        "recorte": {"canal": canal, "categoria": categoria},
        "teto_vigente_pct": teto,
        "origem_do_teto": origem_teto,
        "tabela_de_alcadas": tabela,
        "origem_das_alcadas": origem_alcadas,
        "limiar_de_excecao_pct": config.LIMIAR_DESCONTO_ALTO * 100,
    }
    if desconto_pct is None:
        saida["nota"] = ("nenhum desconto informado: este retorno é a régua, não "
                         "uma avaliação de caso")
        return saida

    pct = _pct(desconto_pct)
    faixa, _, _ = _faixa_de_alcada(pct)
    saida.update({
        "desconto_consultado_pct": pct,
        "alcada_requerida": faixa["aprovador"],
        "faixa_de_alcada": faixa["faixa"],
        "exige_justificativa_de_excecao": bool(faixa["exige_justificativa"]),
        "dentro_do_teto_vigente": None if teto is None else pct <= teto,
    })
    if teto is not None:
        saida["distancia_do_teto_pp"] = round(pct - teto, 4)
    return saida


@ferramenta(
    "pedidos_acima_do_teto",
    """Conta os pedidos que excedem o teto e mede dois sinais de contorno da
    política: concentração logo ABAIXO do teto (desconto fatiado para não pedir
    aprovação) e pedidos que somam desconto alto a margem negativa. Sem
    teto_pct, usa a política vigente; não havendo política, diz isso em vez de
    escolher um número. Contagens vêm da base; o teto é régua declarada.""",
    {"teto_pct": "teto a aplicar, ex 25 (opcional: usa a política vigente)",
     "canal": "canal do recorte (opcional)",
     "categoria": "categoria do recorte (opcional)"},
    principais=["teto_pct"],
)
def pedidos_acima_do_teto(teto_pct=None, canal: str | None = None,
                          categoria: str | None = None) -> dict:
    df, usado = _recorte(carregar_vendas(), canal, categoria)
    if teto_pct is None:
        teto, origem = _teto_vigente(usado.get("canal"), usado.get("categoria"))
        if teto is None:
            # Sem política registrada, cai no limiar de exceção que o projeto já
            # usa em todo o motor (config.LIMIAR_DESCONTO_ALTO, o mesmo 25% de
            # cenarios_reducao_desconto). Devolver "não sei" aqui deixaria a
            # pergunta sem resposta por falta de um cadastro, não por falta de
            # dado — e a origem declarada impede que a régua vire apuração.
            teto = config.LIMIAR_DESCONTO_ALTO * 100
            origem = ("limiar de exceção configurado no projeto "
                      "(config.LIMIAR_DESCONTO_ALTO) — NÃO há política registrada "
                      "para este recorte")
    else:
        teto, origem = _pct(teto_pct), "parametro_explicito"

    d = df["desconto_pct"] * 100
    acima = df[d > teto]
    # Faixa de 3 p.p. logo abaixo do teto: é onde se acumula o desconto
    # "arredondado para baixo" quando o objetivo é não acionar a alçada.
    beira = df[(d > teto - 3) & (d <= teto)]
    com_desconto = df[d > 0]
    negativos = acima[acima["margem_contribuicao"] < 0]

    excedente = float(((d[d > teto] - teto) / 100 * df.loc[d > teto, "receita_bruta"]).sum())
    return {
        "recorte": usado,
        "teto_pct": teto,
        "origem_do_teto": origem,
        "pedidos_no_recorte": int(len(df)),
        "pedidos_acima_do_teto": int(len(acima)),
        "pct_dos_pedidos": round(100 * len(acima) / len(df), 2) if len(df) else 0.0,
        "receita_bruta_acima_do_teto": round(float(acima["receita_bruta"].sum()), 2),
        "desconto_concedido_acima_do_teto": round(float(acima["desconto_reais"].sum()), 2),
        "desconto_excedente_ao_teto": round(excedente, 2),
        "sinal_de_contorno": {
            "pedidos_na_faixa_3pp_abaixo_do_teto": int(len(beira)),
            "pct_dos_pedidos_com_desconto": (
                round(100 * len(beira) / len(com_desconto), 2) if len(com_desconto) else 0.0),
            "leitura": ("concentração logo abaixo do teto é INDÍCIO de desconto "
                        "ajustado para não acionar a alçada — não é prova: sem o "
                        "registro de quem aprovou cada pedido, a intenção não é "
                        "observável nesta base"),
        },
        "excecoes_criticas": {
            "pedidos_acima_do_teto_com_margem_negativa": int(len(negativos)),
            "margem_negativa_reais": round(float(negativos["margem_contribuicao"].sum()), 2),
        },
        "limitacao": ("a base não registra aprovador, justificativa nem data de "
                      "aprovação: é possível contar violações do teto, não "
                      "atribuir responsabilidade nem confirmar exceção autorizada"),
    }
