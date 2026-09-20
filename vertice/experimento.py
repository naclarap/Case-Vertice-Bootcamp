"""Teste A/B de política de desconto — desenho, atribuição e leitura do resultado.

O que este módulo É
-------------------
O instrumento do experimento: ele decide quem cai no grupo de controle e quem
cai no grupo de teste, calcula o tamanho de amostra necessário ANTES de
começar, e lê o resultado real DEPOIS. Toda conta é determinística, feita aqui
em Python sobre a base — nenhum número passa por modelo de linguagem.

O que este módulo NÃO É
-----------------------
Ele não inventa resultado. Enquanto não houver pedido dentro da janela do
experimento, `resultado()` devolve `disponivel=False` e diz por quê. A base do
case termina em 26/01/2024: um experimento iniciado hoje tem zero pedidos, e é
exatamente isso que a tela deve mostrar — não uma estimativa com cara de
apuração.

Atribuição sem escrever na base
-------------------------------
O motor é só-leitura por decisão de projeto, então o grupo de cada unidade não
é gravado em lugar nenhum: ele é DERIVADO por hash determinístico da chave mais
a semente do experimento. Mesma chave e mesma semente dão sempre o mesmo grupo,
em qualquer máquina e a qualquer momento — o que torna a atribuição auditável e
reproduzível sem custar uma linha de escrita. `atribuicao_de()` permite conferir
pedido a pedido.

Unidade de aleatorização
------------------------
Duas opções, e a escolha não é cosmética:

* por PEDIDO — mede efeito sobre margem por pedido. Amostra grande (24 mil),
  mas não enxerga perda de volume: um pedido que deixou de acontecer não está
  na base para ser contado.
* por CLIENTE — é a única que mede volume (pedidos por cliente), que é o risco
  que a regra de parada vigia. Exige, porém, clientes suficientes.

`desenho()` calcula as duas e diz se cada uma é viável com a base atual, em vez
de escolher no lugar de quem decide.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid

import numpy as np
import pandas as pd
from scipy import stats as sps

from .data import carregar_vendas
from .politica import _gravar_chave, caminho_arquivo

UNIDADES = ("pedido", "cliente")
ESTADOS_EXPERIMENTO = ("planejado", "rodando", "encerrado")

# Métrica primária por unidade de aleatorização. A de cliente é a que enxerga
# volume; a de pedido, não (ver docstring do módulo).
METRICA_PRIMARIA = {
    "pedido": "margem_contribuicao",
    "cliente": "pedidos",
}


# --------------------------------------------------------------- atribuição
def atribuir(chave: str, semente: str, proporcao_controle: float = 0.5) -> str:
    """Grupo determinístico a partir da chave e da semente.

    blake2b em vez de `hash()` do Python de propósito: o hash embutido é
    randomizado por processo (PYTHONHASHSEED), então a mesma chave cairia em
    grupos diferentes a cada execução — o oposto de auditável.
    """
    digest = hashlib.blake2b(f"{semente}:{chave}".encode("utf-8"), digest_size=8).digest()
    # 8 bytes → inteiro → fração uniforme em [0, 1).
    fracao = int.from_bytes(digest, "big") / 2 ** 64
    return "controle" if fracao < proporcao_controle else "teste"


def _coluna_de_grupo(chaves: pd.Series, semente: str, proporcao: float) -> pd.Series:
    return chaves.astype(str).map(lambda k: atribuir(k, semente, proporcao))


def atribuicao_de(chave: str, semente: str, proporcao_controle: float = 0.5) -> dict:
    """Confere em que grupo uma chave cai — a auditoria da aleatorização."""
    return {
        "chave": chave,
        "semente": semente,
        "proporcao_controle": proporcao_controle,
        "grupo": atribuir(chave, semente, proporcao_controle),
        "nota": ("derivado por hash determinístico; nada é gravado na base. "
                 "Mesma chave e mesma semente dão sempre o mesmo grupo."),
    }


# ------------------------------------------------------------------ recorte
def _recortar(df: pd.DataFrame, canal: str | None, categoria: str | None) -> pd.DataFrame:
    if canal:
        df = df[df["canal"] == canal]
    if categoria:
        df = df[df["categoria"] == categoria]
    return df


def _por_cliente(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("customer_id").agg(
        pedidos=("order_id", "count"),
        margem_contribuicao=("margem_contribuicao", "sum"),
        receita_bruta=("receita_bruta", "sum"),
    ).reset_index()


# ------------------------------------------------------------- poder do teste
def _n_por_grupo(desvio: float, delta: float, alpha: float, poder: float) -> int | None:
    """Amostra por grupo para detectar `delta` com `poder`, teste bicaudal.

    n = 2·(z(1-α/2) + z(poder))²·σ²/Δ² — a fórmula clássica de duas amostras
    independentes. Aproximação normal: com os n que este caso exige, a
    diferença para a t é irrelevante.
    """
    if not delta or delta <= 0 or not np.isfinite(desvio) or desvio <= 0:
        return None
    z_alpha = sps.norm.ppf(1 - alpha / 2)
    z_poder = sps.norm.ppf(poder)
    return int(np.ceil(2 * (z_alpha + z_poder) ** 2 * desvio ** 2 / delta ** 2))


def desenho(mde_relativo: float = 0.05, alpha: float = 0.05, poder: float = 0.8,
            canal: str | None = None, categoria: str | None = None) -> dict:
    """Tamanho de amostra e duração necessários, para as duas unidades.

    `mde_relativo` é o efeito mínimo detectável em proporção da média (0.05 =
    5%). Tudo vem da dispersão real da base — é a resposta determinística para
    "esse teste é possível de rodar?".
    """
    df = _recortar(carregar_vendas(), canal, categoria)
    if df.empty:
        raise ValueError("recorte sem pedidos: não há base para dimensionar o teste")

    dias_base = max(1, (df["data_pedido"].max() - df["data_pedido"].min()).days)
    pedidos_por_dia = len(df) / dias_base
    clientes = _por_cliente(df)
    clientes_por_dia = len(clientes) / dias_base

    linhas = []
    for unidade in UNIDADES:
        if unidade == "pedido":
            amostra = df["margem_contribuicao"]
            rotulo_metrica = "margem de contribuição por pedido"
            disponivel, por_dia = len(df), pedidos_por_dia
        else:
            amostra = clientes["pedidos"]
            rotulo_metrica = "pedidos por cliente"
            disponivel, por_dia = len(clientes), clientes_por_dia

        media = float(amostra.mean())
        desvio = float(amostra.std(ddof=1))
        delta = abs(media) * mde_relativo
        n = _n_por_grupo(desvio, delta, alpha, poder)
        n_total = n * 2 if n else None
        # Quantas unidades novas entram por dia é o que define a duração; com a
        # base parada, é uma projeção da taxa histórica, e vem rotulada assim.
        dias = int(np.ceil(n_total / por_dia)) if (n_total and por_dia) else None

        linhas.append({
            "unidade": unidade,
            "metrica_primaria": rotulo_metrica,
            "media": round(media, 4),
            "desvio_padrao": round(desvio, 4),
            "coeficiente_de_variacao": round(desvio / abs(media), 3) if media else None,
            "efeito_minimo_detectavel": round(delta, 4),
            "n_por_grupo": n,
            "n_total": n_total,
            "unidades_disponiveis_na_base": disponivel,
            "unidades_por_dia": round(por_dia, 2),
            "duracao_estimada_dias": dias,
            # Viável = a base tem, hoje, unidades suficientes para os dois grupos.
            "viavel_com_a_base_atual": bool(n_total and disponivel >= n_total),
            "mede_volume": unidade == "cliente",
        })

    por_unidade = {l["unidade"]: l for l in linhas}
    viavel_volume = por_unidade["cliente"]["viavel_com_a_base_atual"]
    return {
        "recorte": {"canal": canal, "categoria": categoria},
        "mde_relativo": mde_relativo,
        "alpha": alpha,
        "poder": poder,
        "periodo_da_base": [str(df["data_pedido"].min().date()),
                            str(df["data_pedido"].max().date())],
        "unidades": linhas,
        "leitura": (
            "A aleatorização por CLIENTE é a única que mede perda de volume, que é "
            "o risco vigiado pela regra de parada. "
            + ("Ela é viável com a base atual." if viavel_volume else
               f"Ela NÃO é viável com a base atual: o teste precisaria de "
               f"{por_unidade['cliente']['n_total']:,} clientes e a base tem "
               f"{por_unidade['cliente']['unidades_disponiveis_na_base']:,}."
               .replace(",", ".")) +
            " A aleatorização por PEDIDO tem amostra de sobra, mas mede margem por "
            "pedido, não volume: um pedido que deixou de acontecer não aparece na base."
        ),
        "nota_duracao": ("duração projetada pela taxa histórica de entrada de "
                         "unidades; não é promessa de calendário"),
    }


# -------------------------------------------------------------- persistência
def _carregar_tudo() -> dict:   # noqa: usado só por `_experimentos`
    p = caminho_arquivo()
    if not p.is_file():
        return {}
    try:
        dados = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"arquivo de políticas corrompido ({p}): {e}") from e
    return dados if isinstance(dados, dict) else {}


def _experimentos() -> list[dict]:
    return _carregar_tudo().get("experimentos", [])


def _gravar_experimentos(experimentos: list[dict]) -> None:
    """Preserva políticas e propostas — as três coleções dividem o mesmo JSON,
    e toda escrita passa pelo mesmo ponto (ver `politica._gravar_chave`)."""
    _gravar_chave("experimentos", experimentos)


def experimentos() -> list[dict]:
    return sorted(_experimentos(), key=lambda e: e.get("criado_em_ts", 0), reverse=True)


def obter_experimento(exp_id: str) -> dict | None:
    return next((e for e in _experimentos() if e.get("id") == exp_id), None)


def experimento_corrente() -> dict | None:
    """O que está rodando; se nenhum, o último planejado."""
    todos = experimentos()
    return (next((e for e in todos if e["estado"] == "rodando"), None)
            or next((e for e in todos if e["estado"] == "planejado"), None))


def criar_experimento(proposta_id: str, teto_pct: float, responsavel: str,
                      unidade: str = "cliente", proporcao_controle: float = 0.5,
                      duracao_dias: int = 30, mde_relativo: float = 0.05,
                      alpha: float = 0.05, poder: float = 0.8,
                      canal: str | None = None, categoria: str | None = None,
                      semente: str | None = None) -> dict:
    """Desenha o experimento. Ele nasce PLANEJADO: nada é medido até iniciar."""
    if unidade not in UNIDADES:
        raise ValueError(f"unidade inválida: {unidade!r}. Use uma de {list(UNIDADES)}")
    if not 0 < proporcao_controle < 1:
        raise ValueError("proporcao_controle deve estar entre 0 e 1 (exclusive)")
    if not responsavel or not str(responsavel).strip():
        raise ValueError("todo experimento precisa de um responsável")

    exp = {
        "id": "exp_" + uuid.uuid4().hex[:10],
        "proposta_id": proposta_id,
        "teto_pct": float(teto_pct),
        "responsavel": str(responsavel).strip(),
        "unidade": unidade,
        "proporcao_controle": float(proporcao_controle),
        "duracao_dias": int(duracao_dias),
        "mde_relativo": float(mde_relativo),
        "alpha": float(alpha),
        "poder": float(poder),
        "canal": canal,
        "categoria": categoria,
        # A semente entra no hash: trocá-la reembaralha os grupos, então ela é
        # fixada aqui e nunca mais muda — é o que torna a atribuição estável.
        "semente": semente or uuid.uuid4().hex[:12],
        "estado": "planejado",
        "criado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "criado_em_ts": time.time(),
        "inicio": None,
        "fim_previsto": None,
        "encerrado_em": None,
        "motivo_encerramento": None,
        "historico": [{"evento": "planejado", "quem": str(responsavel).strip(),
                       "quando": time.strftime("%Y-%m-%d %H:%M:%S")}],
    }
    todos = _experimentos()
    todos.append(exp)
    _gravar_experimentos(todos)
    return exp


def _mudar(exp_id: str, mudanca) -> dict:
    todos = _experimentos()
    idx = next((i for i, e in enumerate(todos) if e.get("id") == exp_id), None)
    if idx is None:
        raise ValueError(f"experimento {exp_id!r} não encontrado")
    mudanca(todos[idx])
    _gravar_experimentos(todos)
    return todos[idx]


def iniciar_experimento(exp_id: str, quem: str, inicio: str | None = None) -> dict:
    """Marca o começo. A janela de medição é [inicio, inicio + duracao_dias]."""
    if not quem or not str(quem).strip():
        raise ValueError("é preciso registrar quem iniciou o experimento")

    def _aplicar(e):
        if e["estado"] != "planejado":
            raise ValueError(f"só um experimento planejado pode iniciar (está em '{e['estado']}')")
        d0 = pd.to_datetime(inicio) if inicio else pd.Timestamp.now().normalize()
        e["estado"] = "rodando"
        e["inicio"] = str(d0.date())
        e["fim_previsto"] = str((d0 + pd.Timedelta(days=e["duracao_dias"] - 1)).date())
        e["historico"].append({"evento": "iniciado", "quem": str(quem).strip(),
                               "quando": time.strftime("%Y-%m-%d %H:%M:%S")})
    return _mudar(exp_id, _aplicar)


def encerrar_experimento(exp_id: str, quem: str, motivo: str) -> dict:
    if not quem or not str(quem).strip():
        raise ValueError("é preciso registrar quem encerrou o experimento")
    if not motivo or not str(motivo).strip():
        raise ValueError("encerrar um teste exige motivo declarado")

    def _aplicar(e):
        if e["estado"] != "rodando":
            raise ValueError(f"só um experimento em andamento pode ser encerrado "
                             f"(está em '{e['estado']}')")
        e["estado"] = "encerrado"
        e["encerrado_em"] = time.strftime("%Y-%m-%d %H:%M:%S")
        e["motivo_encerramento"] = str(motivo).strip()
        e["historico"].append({"evento": "encerrado", "quem": str(quem).strip(),
                               "quando": e["encerrado_em"], "motivo": e["motivo_encerramento"]})
    return _mudar(exp_id, _aplicar)


# ------------------------------------------------------------------ leitura
def _welch(a: pd.Series, b: pd.Series) -> dict:
    """t de Welch entre os dois grupos, com IC de 95% e tamanho de efeito."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return {"suficiente": False, "n_controle": na, "n_teste": nb}
    ma, mb = float(a.mean()), float(b.mean())
    va, vb = float(a.var(ddof=1)), float(b.var(ddof=1))
    t, p = sps.ttest_ind(b, a, equal_var=False)
    se = float(np.sqrt(va / na + vb / nb))
    gl = ((va / na + vb / nb) ** 2 /
          ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))) if se else 0
    crit = float(sps.t.ppf(0.975, gl)) if gl else 0
    dif = mb - ma
    dp = float(np.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))) if na + nb > 2 else 0
    d = dif / dp if dp else 0
    return {
        "suficiente": True,
        "n_controle": na, "n_teste": nb,
        "media_controle": round(ma, 4), "media_teste": round(mb, 4),
        "diferenca": round(dif, 4),
        "diferenca_relativa_pct": round(dif / ma * 100, 2) if ma else None,
        "ic95_diferenca": [round(dif - crit * se, 4), round(dif + crit * se, 4)],
        "estatistica_t": round(float(t), 4),
        "p_valor": float(p),
        "d_cohen": round(float(d), 4),
    }


def _janela(exp: dict) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    if not exp.get("inicio"):
        return None
    ini = pd.to_datetime(exp["inicio"])
    fim = pd.to_datetime(exp.get("fim_previsto") or exp["inicio"])
    return ini, fim


def resultado(exp: dict, ate: str | None = None) -> dict:
    """Resultado REAL do experimento, ou a declaração de que não há dado.

    Nunca estima: se a janela não tem pedido, devolve `disponivel=False` com o
    motivo. É o comportamento esperado enquanto a base histórica terminar antes
    do início do teste.
    """
    janela = _janela(exp)
    if janela is None:
        return {"disponivel": False,
                "motivo": "o experimento ainda não foi iniciado — não há janela para medir"}

    ini, fim = janela
    if ate:
        fim = min(fim, pd.to_datetime(ate))

    df = _recortar(carregar_vendas(), exp.get("canal"), exp.get("categoria"))
    d = pd.to_datetime(df["data_pedido"])
    sel = df[(d >= ini) & (d < fim + pd.Timedelta(days=1))]

    if sel.empty:
        ultimo = _dia(d.max().date()) if len(d) else "—"
        return {
            "disponivel": False,
            "janela": [str(ini.date()), str(fim.date())],
            "pedidos_na_janela": 0,
            # A janela crua (ISO) segue no campo `janela`, para quem consome a
            # API; a frase que vai à tela leva a data no formato do leitor.
            "motivo": (f"nenhum pedido na janela do teste. A base vai até {ultimo}, "
                       f"e o experimento começa em {_dia(ini.date())} — não há o "
                       f"que medir ainda. Nenhum número é estimado no lugar."),
        }

    unidade = exp.get("unidade", "cliente")
    semente, proporcao = exp["semente"], exp["proporcao_controle"]

    if unidade == "cliente":
        base = _por_cliente(sel)
        base["grupo"] = _coluna_de_grupo(base["customer_id"], semente, proporcao)
        metricas = {
            "pedidos_por_cliente": "pedidos",
            "margem_por_cliente": "margem_contribuicao",
        }
    else:
        base = sel.copy()
        base["grupo"] = _coluna_de_grupo(base["order_id"], semente, proporcao)
        metricas = {
            "margem_por_pedido": "margem_contribuicao",
            "receita_por_pedido": "receita_bruta",
        }

    controle = base[base["grupo"] == "controle"]
    teste = base[base["grupo"] == "teste"]
    saida = {rotulo: _welch(controle[col], teste[col]) for rotulo, col in metricas.items()}

    return {
        "disponivel": True,
        "janela": [str(ini.date()), str(fim.date())],
        "unidade": unidade,
        "pedidos_na_janela": int(len(sel)),
        "unidades_controle": int(len(controle)),
        "unidades_teste": int(len(teste)),
        "metricas": saida,
        "nota": ("grupos derivados por hash determinístico da chave com a semente "
                 "do experimento; a atribuição é conferível unidade a unidade."),
    }


def _dia(d) -> str:
    """AAAA-MM-DD vira DD/MM/AAAA nas frases que a tela mostra."""
    partes = str(d)[:10].split("-")
    return f"{partes[2]}/{partes[1]}/{partes[0]}" if len(partes) == 3 else str(d)


def _ptbr(v, casas: int = 2) -> str:
    """Número com vírgula decimal, para as frases que vão à tela.

    O motor guarda float; quem escreve a frase é quem decide o formato, e o
    formato aqui é o do leitor — não o do repr do Python.
    """
    return f"{float(v):.{casas}f}".replace(".", ",")


def avaliar_regra_de_parada(exp: dict, res: dict, queda_maxima_pct: float = 2.0) -> dict:
    """A regra de parada aplicada ao resultado: continuar, parar ou sem dado.

    A métrica vigiada é a que mede VOLUME (pedidos por cliente). Sem ela — caso
    da aleatorização por pedido — a regra não se pronuncia, porque não há como
    ver perda de volume nessa unidade.
    """
    regra = {
        "queda_maxima_pct": queda_maxima_pct,
        "significancia": exp.get("alpha", 0.05),
        "metrica_vigiada": "pedidos por cliente",
    }
    if not res.get("disponivel"):
        return {**regra, "veredicto": "sem dado", "explicacao": res.get("motivo")}

    m = (res.get("metricas") or {}).get("pedidos_por_cliente")
    if not m or not m.get("suficiente"):
        return {**regra, "veredicto": "sem dado",
                "explicacao": ("a unidade deste experimento não mede volume: "
                               "pedidos por cliente só existe na aleatorização por cliente")}

    variacao = m.get("diferenca_relativa_pct") or 0
    queda = -variacao                       # queda positiva = volume caiu
    significativo = m["p_valor"] < exp.get("alpha", 0.05)
    parar = significativo and queda >= queda_maxima_pct
    # Volume que SOBE não é "queda negativa": dizer isso confunde quem lê.
    # E o número vai em pt-BR: esta frase é lida por um comitê brasileiro, não
    # por um log — "p = 0.9146" no meio de uma sentença em português é ruído.
    movimento = (f"queda de {_ptbr(queda)}%" if queda > 0
                 else f"alta de {_ptbr(abs(queda))}%" if queda < 0
                 else "nenhuma variação")
    return {
        **regra,
        "queda_observada_pct": round(queda, 2),
        "p_valor": m["p_valor"],
        "significativo": bool(significativo),
        "veredicto": "parar" if parar else "continuar",
        "explicacao": (
            f"{movimento} no volume do grupo com teto "
            f"({'significativa' if significativo else 'não significativa'}, "
            f"p = {_ptbr(m['p_valor'], 4)}); "
            + (f"o limite de {_ptbr(queda_maxima_pct)}% foi ultrapassado — "
               "interromper e reverter."
               if parar else
               "dentro do limite ou sem significância — o teste segue.")),
    }


def validacao_aa(semente: str, unidade: str = "cliente", proporcao_controle: float = 0.5,
                 dias: int = 90, canal: str | None = None,
                 categoria: str | None = None) -> dict:
    """Teste A/A sobre a base histórica: mesma máquina, nenhum tratamento.

    Serve para provar que o instrumento não inventa diferença. Os dois grupos
    receberam exatamente o mesmo tratamento (nenhum), então uma diferença
    significativa aqui seria defeito da aleatorização, não efeito de política.
    Isto NÃO é o resultado do teste A/B — é a aferição da régua.
    """
    df = _recortar(carregar_vendas(), canal, categoria)
    if df.empty:
        raise ValueError("recorte sem pedidos para validar a aleatorização")
    d = pd.to_datetime(df["data_pedido"])
    fim = d.max().normalize()
    ini = fim - pd.Timedelta(days=dias - 1)
    sel = df[(d >= ini) & (d < fim + pd.Timedelta(days=1))]

    falso = {"id": "aa", "semente": semente, "proporcao_controle": proporcao_controle,
             "unidade": unidade, "inicio": str(ini.date()), "fim_previsto": str(fim.date()),
             "canal": canal, "categoria": categoria, "alpha": 0.05}
    res = resultado(falso)
    metricas = res.get("metricas") or {}
    uteis = [m for m in metricas.values() if m.get("suficiente")]
    passou = all(m.get("p_valor", 1) >= 0.05 for m in uteis)
    # Maior diferença observada entre dois grupos que receberam o MESMO
    # tratamento — ou seja, ruído puro.
    ruido = max((abs(m.get("diferenca_relativa_pct") or 0) for m in uteis), default=0)

    if not res.get("disponivel"):
        leitura = res.get("motivo")
    elif not passou:
        leitura = ("a aleatorização produziu diferença significativa sem nenhum "
                   "tratamento aplicado: isso é defeito do instrumento, não efeito "
                   "de política. Não use este desenho.")
    elif ruido >= 10:
        # Passar no A/A com diferença enorme não é boa notícia: significa que o
        # teste não conseguiria distinguir efeito de ruído nesse tamanho.
        leitura = (f"nenhuma diferença significativa (p ≥ 0,05), como esperado — mas "
                   f"dois grupos SEM tratamento nenhum já diferem em {ruido:.0f}% na "
                   f"métrica mais ruidosa. Isso não atesta equilíbrio: atesta que, "
                   f"com esta amostra, o teste não separa efeito de ruído. Ver o "
                   f"cálculo de poder no desenho.")
    else:
        leitura = ("os dois grupos receberam o mesmo tratamento (nenhum) e não "
                   "diferem significativamente: a aleatorização não cria diferença "
                   "sozinha, e a régua está aferida.")

    return {
        **res,
        "tipo": "A/A",
        "passou": bool(passou) if res.get("disponivel") else None,
        "maior_diferenca_sem_tratamento_pct": round(ruido, 2) if uteis else None,
        "leitura": leitura,
    }
