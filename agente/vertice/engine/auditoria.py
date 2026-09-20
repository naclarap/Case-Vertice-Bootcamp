"""Auditoria de qualidade de dados — camada determinística (nenhum LLM aqui).

Suporte lateral à governança: aponta incoerência para revisão humana, nunca
decide nada sozinho. Tudo aqui é contagem sobre a base bruta (`carregar_bruto`),
sem os filtros de PREMISSAS.md — auditar a base já limpa não encontraria o que
a limpeza escondeu.

"Verificado e sem problema" é resultado válido: as checagens devolvem o número
apurado mesmo quando ele é zero, para que o resultado limpo fique registrado em
vez de virar silêncio.

A camada semântica assistida por LLM fica FORA deste módulo, em
`vertice/auditoria_semantica.py` — o motor não importa nada do agente nem
chama modelo (ver README, "Arquitetura").
"""
from __future__ import annotations

import pandas as pd

from ..data import carregar_bruto
from .registry import ferramenta

# Onde procurar uma data de solicitação de devolução (item 5). Nomes prováveis
# em pt/en; a checagem é por substring no nome da coluna, insensível a caixa.
_PISTAS_DATA_SOLICITACAO = (
    "data_solicitacao", "data_devolucao", "data_pedido_devolucao",
    "solicitacao_devolucao", "return_request", "data_solicitacao_devolucao",
)

TEXTO_LACUNA_PRAZO_DEVOLUCAO = (
    "não é possível verificar prazo de devolução porque a data de solicitação "
    "não está registrada em nenhuma base disponível"
)


# Quantos exemplos cada checagem mostra por padrão. O corte existe para a tela
# não virar um despejo da base; `limite_exemplos=None` (ou "todos") devolve a
# lista inteira, que é o que alimenta a exportação para correção.
LIMITE_PADRAO = {"orfaos": 20, "duplicatas": 10, "linhas_quebradas": 5}


def _corte(valores: list, limite) -> list:
    """Aplica o limite de exibição. None ou "todos" devolvem a lista inteira;
    0 devolve nenhuma (é o padrão de quem não lista exemplo por padrão)."""
    if limite is None:
        return valores
    if isinstance(limite, str):
        if limite.strip().lower() in ("todos", "todas", "all", ""):
            return valores
        limite = int(limite)
    return valores[: int(limite)]


def _identificador(df: pd.DataFrame) -> str:
    """Coluna que identifica a linha para quem vai corrigir (order_id, sku_id…).
    A primeira coluna é a chave em todas as bases do caso."""
    return str(df.columns[0])


def _coluna(df: pd.DataFrame, tabela: str, coluna: str) -> pd.Series:
    if coluna not in df.columns:
        raise ValueError(
            f"coluna '{coluna}' não existe em '{tabela}'. Disponíveis: {sorted(df.columns)}"
        )
    return df[coluna]


@ferramenta(
    "checar_integridade_referencial",
    """Conta quantos valores de uma coluna (chave estrangeira) não têm
    correspondência na coluna-chave de outra tabela — ex: sku_id de vendas que
    não existe em estoque. Resultado zero é resultado válido e fica registrado.""",
    {"tabela_a": "tabela com a chave estrangeira (vendas, clientes, estoque, marketing, atendimento)",
     "coluna_fk": "coluna de chave estrangeira em tabela_a (ex 'sku_id')",
     "tabela_b": "tabela de referência (ex 'estoque')",
     "coluna_pk": "coluna-chave em tabela_b (ex 'sku_id')",
     "limite_exemplos": "quantos exemplos listar (padrão 20; None ou 'todos' = lista completa)"},
    ["tabela_a", "coluna_fk", "tabela_b", "coluna_pk"],
)
def checar_integridade_referencial(tabela_a: str, coluna_fk: str,
                                   tabela_b: str, coluna_pk: str,
                                   limite_exemplos=LIMITE_PADRAO["orfaos"]) -> dict:
    da, db = carregar_bruto(tabela_a), carregar_bruto(tabela_b)
    fk = _coluna(da, tabela_a, coluna_fk)
    pk = _coluna(db, tabela_b, coluna_pk)
    validos = set(pk.dropna().unique())
    presentes = fk.dropna()
    orfaos = presentes[~presentes.isin(validos)]
    valores_orfaos = _corte(sorted(orfaos.unique().tolist()), limite_exemplos)
    return {
        "tabela_a": tabela_a, "coluna_fk": coluna_fk,
        "tabela_b": tabela_b, "coluna_pk": coluna_pk,
        "linhas_verificadas": int(len(da)),
        "valores_nulos_na_fk": int(fk.isna().sum()),
        "registros_orfaos": int(len(orfaos)),
        "pct_orfaos": round(float(len(orfaos)) / len(da) * 100, 4) if len(da) else 0.0,
        "exemplos_orfaos": valores_orfaos,
        "status": "ok" if len(orfaos) == 0 else "atencao",
    }


@ferramenta(
    "checar_duplicatas_chave",
    """Conta linhas cuja coluna-chave aparece mais de uma vez (ex: order_id
    repetido em vendas). Devolve também quantos valores distintos estão
    duplicados. Resultado zero é resultado válido e fica registrado.""",
    {"tabela": "tabela a verificar", "coluna_chave": "coluna que deveria ser única",
     "limite_exemplos": "quantos exemplos listar (padrão 10; None ou 'todos' = lista completa)"},
    ["tabela", "coluna_chave"],
)
def checar_duplicatas_chave(tabela: str, coluna_chave: str,
                            limite_exemplos=LIMITE_PADRAO["duplicatas"]) -> dict:
    df = carregar_bruto(tabela)
    col = _coluna(df, tabela, coluna_chave)
    duplicadas = col.duplicated(keep=False) & col.notna()
    valores = col[duplicadas].value_counts()
    return {
        "tabela": tabela, "coluna_chave": coluna_chave,
        "linhas_verificadas": int(len(df)),
        "linhas_duplicadas": int(duplicadas.sum()),
        "valores_distintos_duplicados": int(len(valores)),
        "exemplos": _corte([{"valor": str(v), "ocorrencias": int(n)}
                            for v, n in valores.items()], limite_exemplos),
        "status": "ok" if duplicadas.sum() == 0 else "atencao",
    }


@ferramenta(
    "checar_completude",
    """Percentual de valores nulos por coluna de uma tabela, ordenado do mais
    incompleto para o menos. Serve para saber onde o dado simplesmente não
    existe antes de tirar conclusão de qualquer análise que use aquela coluna.""",
    {"tabela": "tabela a verificar",
     "limite_exemplos": "quantas linhas quebradas listar (padrão 5; None ou 'todos' = lista completa)"},
    ["tabela"],
)
def checar_completude(tabela: str,
                      limite_exemplos=LIMITE_PADRAO["linhas_quebradas"]) -> dict:
    df = carregar_bruto(tabela)
    total = len(df)
    linhas = [
        {"coluna": c,
         "nulos": int(df[c].isna().sum()),
         "pct_nulos": round(float(df[c].isna().sum()) / total * 100, 2) if total else 0.0}
        for c in df.columns
    ]
    linhas.sort(key=lambda x: x["pct_nulos"], reverse=True)
    completas = [x["coluna"] for x in linhas if x["nulos"] == 0]

    # Contar COLUNA com nulo escondia o achado: 13 colunas da base de vendas têm
    # nulo, mas é sempre a MESMA linha — um registro com quase todos os campos
    # vazios. "13 de 20 colunas com algum nulo" não diz isso; "1 linha com 13
    # campos vazios" diz. Por isso a checagem também olha por linha.
    nulos_por_linha = df.isna().sum(axis=1)
    incompletas = int((nulos_por_linha > 0).sum())
    metade = max(1, len(df.columns) // 2)
    quebradas = nulos_por_linha[nulos_por_linha >= metade]
    exemplos = []
    if len(quebradas):
        chave = df.columns[0]
        exemplos = [{"linha": int(i), str(chave): str(df.at[i, chave]),
                     "campos_vazios": int(nulos_por_linha[i])}
                    for i in _corte(list(quebradas.index), limite_exemplos)]

    # Registro quebrado (metade ou mais dos campos vazios) é defeito em qualquer
    # domínio. Nulo espalhado numa coluna pode ser legítimo (um chamado ainda
    # aberto não tem data de fechamento) — isso é 'revisar', não 'ok'.
    if len(quebradas):
        status = "atencao"
    elif incompletas:
        status = "revisar"
    else:
        status = "ok"

    return {
        "tabela": tabela,
        "linhas": total,
        "colunas": len(df.columns),
        "por_coluna": linhas,
        "colunas_sem_nulo": completas,
        "colunas_com_nulo": [x["coluna"] for x in linhas if x["nulos"] > 0],
        "linhas_incompletas": incompletas,
        "linhas_quebradas": int(len(quebradas)),
        "exemplos_linhas_quebradas": exemplos,
        "status": status,
    }


@ferramenta(
    "checar_outliers_iqr",
    """Registros fora de Q1 - m·IQR / Q3 + m·IQR numa coluna numérica
    (m = multiplicador, padrão 3.0 = outlier severo). ATENÇÃO: outlier aqui é
    marcação estatística, não erro de dado comprovado — desconto alto legítimo
    e erro de digitação caem no mesmo balde; serve para direcionar revisão.""",
    {"tabela": "tabela a verificar", "coluna": "coluna numérica",
     "multiplicador": "multiplicador do IQR (padrão 3.0)",
     "limite_exemplos": "quantos registros fora da cerca listar (padrão 0 = nenhum; None ou 'todos' = lista completa)"},
    ["tabela", "coluna"],
)
def checar_outliers_iqr(tabela: str, coluna: str, multiplicador=3.0,
                        limite_exemplos=0) -> dict:
    df = carregar_bruto(tabela)
    col = pd.to_numeric(_coluna(df, tabela, coluna), errors="coerce")
    if col.notna().sum() == 0:
        raise ValueError(f"coluna '{coluna}' de '{tabela}' não tem valor numérico algum")
    m = float(multiplicador)
    q1, q3 = float(col.quantile(0.25)), float(col.quantile(0.75))
    iqr = q3 - q1
    piso, teto = q1 - m * iqr, q3 + m * iqr
    fora = col[(col < piso) | (col > teto)]
    validos = int(col.notna().sum())
    # Exemplo de registro só aparece quando pedido: por padrão esta checagem
    # devolve contagem, não despejo de linha (ver `limite_exemplos`).
    exemplos = {}
    if limite_exemplos != 0:
        ident = _identificador(df)
        exemplos["exemplos"] = _corte(
            [{"linha": int(i), ident: str(df.at[i, ident]), coluna: float(col[i])}
             for i in fora.index], limite_exemplos)
    return {
        "tabela": tabela, "coluna": coluna, "multiplicador": m,
        **exemplos,
        "q1": round(q1, 4), "q3": round(q3, 4), "iqr": round(iqr, 4),
        "limite_inferior": round(piso, 4), "limite_superior": round(teto, 4),
        "valores_considerados": validos,
        "outliers": int(len(fora)),
        "pct_outliers": round(float(len(fora)) / validos * 100, 2) if validos else 0.0,
        "minimo_observado": round(float(col.min()), 4),
        "maximo_observado": round(float(col.max()), 4),
        "nota": "outlier estatístico não é erro comprovado; direciona revisão humana.",
        # 'ok' aqui seria mentira: 1.910 registros marcados é achado. Também não é
        # 'atencao', porque outlier não é erro provado — daí o terceiro status.
        "status": "revisar" if len(fora) else "ok",
    }


@ferramenta(
    "checar_faixa_implausivel",
    """Valores fora de uma faixa esperada informada por quem conhece o negócio
    (ex: tempo de entrega negativo, quantidade zero, preço acima de um teto).
    Diferente de outlier estatístico: aqui a faixa é uma regra de domínio, não
    uma propriedade da distribuição.""",
    {"tabela": "tabela a verificar", "coluna": "coluna numérica",
     "minimo": "menor valor plausível (omita para não checar piso)",
     "maximo": "maior valor plausível (omita para não checar teto)",
     "limite_exemplos": "quantos registros fora da faixa listar (padrão 0 = nenhum; None ou 'todos' = lista completa)"},
    ["tabela", "coluna"],
)
def checar_faixa_implausivel(tabela: str, coluna: str, minimo=None, maximo=None,
                             limite_exemplos=0) -> dict:
    if minimo is None and maximo is None:
        raise ValueError("informe ao menos um de 'minimo' ou 'maximo'")
    df = carregar_bruto(tabela)
    col = pd.to_numeric(_coluna(df, tabela, coluna), errors="coerce")
    lo = float(minimo) if minimo is not None else None
    hi = float(maximo) if maximo is not None else None
    abaixo = col < lo if lo is not None else pd.Series(False, index=col.index)
    acima = col > hi if hi is not None else pd.Series(False, index=col.index)
    fora = abaixo | acima
    validos = int(col.notna().sum())
    exemplos = {}
    if limite_exemplos != 0:
        ident = _identificador(df)
        exemplos["exemplos"] = _corte(
            [{"linha": int(i), ident: str(df.at[i, ident]), coluna: float(col[i])}
             for i in fora[fora].index], limite_exemplos)
    return {
        "tabela": tabela, "coluna": coluna,
        "minimo_esperado": lo, "maximo_esperado": hi,
        **exemplos,
        "valores_considerados": validos,
        "abaixo_do_minimo": int(abaixo.sum()),
        "acima_do_maximo": int(acima.sum()),
        "fora_da_faixa": int(fora.sum()),
        "pct_fora_da_faixa": round(float(fora.sum()) / validos * 100, 2) if validos else 0.0,
        "minimo_observado": round(float(col.min()), 4) if validos else None,
        "maximo_observado": round(float(col.max()), 4) if validos else None,
        "status": "ok" if fora.sum() == 0 else "atencao",
    }


@ferramenta(
    "verificar_consistencia_categorica",
    """Tabela de contingência entre duas colunas categóricas, com contagem e
    percentual por célula — ex: categoria x motivo_devolucao, que revela
    combinação sem sentido de domínio ('Tamanho errado' em Beleza). Esta
    ferramenta só CONTA; julgar se a combinação faz sentido é leitura humana
    (ou da camada semântica, sempre pendente de revisão).""",
    {"tabela": "tabela a verificar", "coluna_a": "primeira coluna categórica",
     "coluna_b": "segunda coluna categórica"},
    ["tabela", "coluna_a", "coluna_b"],
)
def verificar_consistencia_categorica(tabela: str, coluna_a: str, coluna_b: str) -> dict:
    df = carregar_bruto(tabela)
    a = _coluna(df, tabela, coluna_a)
    b = _coluna(df, tabela, coluna_b)
    ct = pd.crosstab(a, b)
    total = int(ct.values.sum())
    celulas = []
    for va in ct.index:
        for vb in ct.columns:
            n = int(ct.loc[va, vb])
            if n == 0:
                continue
            total_linha = int(ct.loc[va].sum())
            total_coluna = int(ct[vb].sum())
            celulas.append({
                coluna_a: str(va), coluna_b: str(vb),
                "registros": n,
                "pct_do_total": round(n / total * 100, 2) if total else 0.0,
                "pct_da_linha": round(n / total_linha * 100, 2) if total_linha else 0.0,
                "pct_da_coluna": round(n / total_coluna * 100, 2) if total_coluna else 0.0,
            })
    celulas.sort(key=lambda x: x["registros"], reverse=True)
    return {
        "tabela": tabela, "coluna_a": coluna_a, "coluna_b": coluna_b,
        "registros_considerados": total,
        "valores_de_a": [str(v) for v in ct.index],
        "valores_de_b": [str(v) for v in ct.columns],
        "celulas": celulas,
        "celulas_preenchidas": len(celulas),
        "combinacoes_possiveis": int(len(ct.index) * len(ct.columns)),
    }


# --------------------------------------------------------- item 5: prazo (CDC)
@ferramenta(
    "checar_devolucao_fora_prazo",
    """Devoluções aceitas fora do prazo legal de arrependimento (CDC art. 49,
    7 dias corridos do recebimento). CONDICIONAL AO DADO: exige uma data de
    SOLICITAÇÃO de devolução, separada da data do pedido/entrega. Se essa data
    não existir em nenhuma base, devolve a lacuna declarada e NÃO estima nada —
    aproximar prazo legal por data de pedido produziria número inventado sobre
    risco jurídico.""",
    {"dias_limite": "prazo legal em dias corridos (padrão 7, CDC art. 49)"},
)
def checar_devolucao_fora_prazo(dias_limite=7) -> dict:
    from .. import config

    encontradas = []
    for tabela in config.ARQUIVOS:
        try:
            cols = carregar_bruto(tabela).columns
        except Exception:
            continue
        for c in cols:
            if any(p in c.lower() for p in _PISTAS_DATA_SOLICITACAO):
                encontradas.append(f"{tabela}.{c}")

    if not encontradas:
        return {
            "disponivel": False,
            "dias_limite": int(dias_limite),
            "lacuna": TEXTO_LACUNA_PRAZO_DEVOLUCAO,
            "colunas_de_data_existentes": {
                t: [c for c in carregar_bruto(t).columns if "data" in c.lower()]
                for t in config.ARQUIVOS
            },
            "nota": ("nenhum cálculo de prazo foi feito. Aproximar a data de "
                     "solicitação pela data do pedido ou da entrega mediria outra "
                     "coisa e daria número errado sobre exposição legal."),
        }

    return {
        "disponivel": False,
        "dias_limite": int(dias_limite),
        "colunas_candidatas": encontradas,
        "lacuna": ("coluna candidata a data de solicitação encontrada, mas o cálculo "
                   "não está implementado: confirme com o time de dados qual coluna "
                   "representa a solicitação de devolução antes de medir prazo."),
    }


# ------------------------------------------------- exportação para correção
# NÃO é ferramenta do agente de propósito: devolve a base inteira que falhou
# uma checagem, o que não cabe num passo de raciocínio. Serve à exportação em
# CSV da tela de auditoria — leitura, como todo o resto deste módulo. Nada
# aqui escreve em data/*.csv: a lista existe para ação humana, e a correção
# acontece no sistema de origem, não por este caminho.
def linhas_que_falharam(checagem: str, parametros: dict) -> pd.DataFrame:
    """As linhas exatas que falharam uma checagem — todas, sem corte.

    Cada linha sai como está na base bruta, mais uma coluna
    `motivo_da_falha` dizendo por que ela entrou na lista.
    """
    p = dict(parametros or {})

    if checagem == "integridade_referencial":
        da = carregar_bruto(p["tabela_a"])
        db = carregar_bruto(p["tabela_b"])
        fk = _coluna(da, p["tabela_a"], p["coluna_fk"])
        validos = set(_coluna(db, p["tabela_b"], p["coluna_pk"]).dropna().unique())
        fora = da[fk.notna() & ~fk.isin(validos)].copy()
        fora["motivo_da_falha"] = (
            f"{p['coluna_fk']} sem correspondência em {p['tabela_b']}.{p['coluna_pk']}")
        return fora

    if checagem == "duplicatas_chave":
        df = carregar_bruto(p["tabela"])
        col = _coluna(df, p["tabela"], p["coluna_chave"])
        fora = df[col.duplicated(keep=False) & col.notna()].copy()
        fora = fora.sort_values(p["coluna_chave"])
        fora["motivo_da_falha"] = f"{p['coluna_chave']} repetido"
        return fora

    if checagem == "completude":
        df = carregar_bruto(p["tabela"])
        nulos = df.isna()
        n = nulos.sum(axis=1)
        fora = df[n > 0].copy()
        fora["campos_vazios"] = n[n > 0]
        fora["colunas_vazias"] = [
            ", ".join(df.columns[nulos.loc[i]]) for i in fora.index]
        fora["motivo_da_falha"] = "linha com campo vazio"
        return fora.sort_values("campos_vazios", ascending=False)

    if checagem in ("outliers_iqr", "faixa_implausivel"):
        df = carregar_bruto(p["tabela"])
        col = pd.to_numeric(_coluna(df, p["tabela"], p["coluna"]), errors="coerce")
        if checagem == "outliers_iqr":
            m = float(p.get("multiplicador", 3.0) or 3.0)
            q1, q3 = float(col.quantile(0.25)), float(col.quantile(0.75))
            piso, teto = q1 - m * (q3 - q1), q3 + m * (q3 - q1)
            marca = (col < piso) | (col > teto)
            motivo = (f"{p['coluna']} fora da cerca IQR "
                      f"[{round(piso, 4)}, {round(teto, 4)}] (m={m})")
        else:
            lo = float(p["minimo"]) if p.get("minimo") is not None else None
            hi = float(p["maximo"]) if p.get("maximo") is not None else None
            abaixo = col < lo if lo is not None else pd.Series(False, index=col.index)
            acima = col > hi if hi is not None else pd.Series(False, index=col.index)
            marca = abaixo | acima
            motivo = (f"{p['coluna']} fora da faixa esperada "
                      f"[{lo if lo is not None else '−∞'}, {hi if hi is not None else '∞'}]")
        fora = df[marca.fillna(False)].copy()
        fora["motivo_da_falha"] = motivo
        return fora

    raise ValueError(
        f"checagem '{checagem}' não tem exportação de registros. "
        f"Disponíveis: integridade_referencial, duplicatas_chave, completude, "
        f"outliers_iqr, faixa_implausivel")


# ------------------------------------------------------------- relatório único
@ferramenta(
    "relatorio_auditoria_dados",
    """Roda de uma vez as checagens determinísticas de qualidade sobre as bases
    do case (integridade referencial, duplicata, completude, outlier, faixa
    implausível) e lista as lacunas de dado conhecidas. Devolve também o que
    veio limpo — resultado sem problema é resultado, não silêncio.""",
)
def relatorio_auditoria_dados() -> dict:
    checagens: list[dict] = []

    def _rodar(nome: str, fn, **kw):
        try:
            checagens.append({"checagem": nome, "parametros": kw, "resultado": fn(**kw)})
        except Exception as e:  # uma checagem quebrada não derruba o relatório
            checagens.append({"checagem": nome, "parametros": kw,
                              "erro": f"{type(e).__name__}: {e}"})

    _rodar("integridade_referencial", checar_integridade_referencial,
           tabela_a="vendas", coluna_fk="sku_id", tabela_b="estoque", coluna_pk="sku_id")
    _rodar("integridade_referencial", checar_integridade_referencial,
           tabela_a="vendas", coluna_fk="customer_id", tabela_b="clientes",
           coluna_pk="customer_id")
    _rodar("duplicatas_chave", checar_duplicatas_chave, tabela="vendas",
           coluna_chave="order_id")
    _rodar("duplicatas_chave", checar_duplicatas_chave, tabela="clientes",
           coluna_chave="customer_id")
    _rodar("completude", checar_completude, tabela="vendas")
    _rodar("outliers_iqr", checar_outliers_iqr, tabela="vendas", coluna="desconto_reais")
    _rodar("faixa_implausivel", checar_faixa_implausivel, tabela="vendas",
           coluna="tempo_entrega_real", minimo=0)
    # Par do outlier acima: outlier estatístico só direciona revisão, quem decide
    # se há valor IMPOSSÍVEL é a regra de domínio. Sem esta linha, "1.910
    # outliers em desconto_reais" fica sem resposta.
    _rodar("faixa_implausivel", checar_faixa_implausivel, tabela="vendas",
           coluna="desconto_reais", minimo=0)
    _rodar("faixa_implausivel", checar_faixa_implausivel, tabela="vendas",
           coluna="quantidade", minimo=1)

    prazo = checar_devolucao_fora_prazo()
    lacunas = [prazo["lacuna"]] if not prazo.get("disponivel") else []

    def _com_status(*valores):
        return [c for c in checagens if c.get("resultado", {}).get("status") in valores]

    return {
        "checagens": checagens,
        "total_checagens": len(checagens),
        "checagens_com_atencao": len(_com_status("atencao")),
        "checagens_a_revisar": len(_com_status("revisar")),
        "checagens_limpas": len(_com_status("ok")),
        "lacunas_de_dado": lacunas,
        "prazo_devolucao": prazo,
        "nota": ("camada determinística apenas. Suspeita de incoerência semântica "
                 "(ex: motivo de devolução incompatível com a categoria) vem da "
                 "camada assistida por IA, sempre marcada como pendente de revisão."),
    }


@ferramenta(
    "coerencia_motivo_entrega",
    """Testa se o motivo de devolução 'Atraso na entrega' é coerente com o tempo
    de entrega efetivamente registrado no pedido. Compara a distribuição de
    tempo_entrega_real dos pedidos devolvidos por atraso com a dos demais
    (teste t de Welch) e conta quantos foram entregues em tempo IGUAL OU MENOR
    que a mediana da base — ou seja, sem sinal de atraso. Sem SLA declarado na
    base, a mediana é a única régua interna disponível; informe sla_dias se a
    empresa tiver um prazo contratado.""",
    {"sla_dias": "prazo contratado em dias (opcional); sem ele, usa a mediana da base"},
)
def coerencia_motivo_entrega(sla_dias=None) -> dict:
    from scipy import stats as sps

    df = carregar_bruto("vendas")
    if "tempo_entrega_real" not in df.columns or "motivo_devolucao" not in df.columns:
        return {"disponivel": False,
                "lacuna": "faltam tempo_entrega_real e/ou motivo_devolucao na base"}

    d = df[df["tempo_entrega_real"].notna()]
    atraso = d[d["motivo_devolucao"].astype(str).str.contains("Atraso", case=False, na=False)]
    resto = d[~d.index.isin(atraso.index)]
    mediana = float(d["tempo_entrega_real"].median())
    regua = float(sla_dias) if sla_dias is not None else mediana
    origem_regua = ("sla_dias informado na chamada" if sla_dias is not None else
                    "mediana de tempo_entrega_real da base — a base NÃO tem coluna "
                    "de SLA contratado")
    dentro = atraso[atraso["tempo_entrega_real"] <= regua]

    t = p = None
    if len(atraso) > 1 and len(resto) > 1:
        t, p = sps.ttest_ind(atraso["tempo_entrega_real"], resto["tempo_entrega_real"],
                             equal_var=False)
    return {
        "pedidos_com_motivo_atraso": int(len(atraso)),
        "tempo_entrega_medio_motivo_atraso": round(float(atraso["tempo_entrega_real"].mean()), 2),
        "tempo_entrega_medio_demais": round(float(resto["tempo_entrega_real"].mean()), 2),
        "diferenca_dias": round(float(atraso["tempo_entrega_real"].mean()
                                      - resto["tempo_entrega_real"].mean()), 2),
        "estatistica_t": None if t is None else round(float(t), 4),
        "p_valor": None if p is None else float(p),
        "regua_de_prazo_dias": regua,
        "origem_da_regua": origem_regua,
        "motivo_atraso_entregue_dentro_da_regua": int(len(dentro)),
        "pct_do_motivo_atraso_sem_sinal_de_atraso": (
            round(100 * len(dentro) / len(atraso), 2) if len(atraso) else 0.0),
        "status": "revisar" if len(dentro) else "sem problema",
        "leitura": ("se o tempo de entrega dos devolvidos por 'Atraso' for igual ao "
                    "dos demais, o motivo registrado não está discriminando atraso "
                    "real — é indício de rótulo pouco confiável, não prova de erro "
                    "em cada pedido"),
    }
