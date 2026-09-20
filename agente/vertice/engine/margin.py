"""Margin Calculator — decomposição MECE da margem de contribuição.

Identidade contábil (por construção da base, verificada em tests/):
    receita_bruta = desconto + custo_produto + custo_frete + margem_contribuicao
Logo: margem% + desconto% + custo% + frete% = 100%.
"""
from __future__ import annotations

import re

import pandas as pd

from .. import config
from ..data import carregar_vendas, resumo_tratamento
from .registry import ferramenta

DIMENSOES = {
    "canal": "canal",
    "categoria": "categoria",
    "mes": "mes",
    "trimestre": "trimestre",
    "ano": "ano",
    "sku": "sku_id",
    "metodo_pagamento": "metodo_pagamento",
    "faixa_desconto": "faixa_desconto",
}


def recorte_janela(df: pd.DataFrame, dias, ate: str | None = None
                   ) -> tuple[pd.DataFrame, dict]:
    """Fatia `df` na janela [ate-dias+1, ate] — a MESMA convenção de
    `margem_na_janela`: fechada nos dois lados, e sem `ate` a janela termina no
    último pedido da base.

    Existe como função pública porque mais de um módulo do motor precisa da
    mesma janela (aqui e em `pos_pedido`), e duas implementações da mesma
    janela é como dois números para o mesmo período aparecem num relatório.
    """
    n = int(dias)
    if n < 1:
        raise ValueError(f"dias deve ser >= 1, recebido {dias}")
    d = pd.to_datetime(df["data_pedido"])
    fim = pd.to_datetime(ate).normalize() if ate else d.max().normalize()
    ini = fim - pd.Timedelta(days=n - 1)
    sel = df[(d >= ini) & (d < fim + pd.Timedelta(days=1))]
    return sel, {"inicio": str(ini.date()), "fim": str(fim.date()), "dias": n}


def _agrega(df: pd.DataFrame, por: list[str] | None = None) -> pd.DataFrame:
    g = df.groupby(por, observed=True) if por else df
    ag = {
        "pedidos": ("order_id", "count"),
        "receita_bruta": ("receita_bruta", "sum"),
        "receita_liquida": ("receita_liquida", "sum"),
        "desconto_reais": ("desconto_reais", "sum"),
        "custo_produto": ("custo_produto", "sum"),
        "custo_frete": ("custo_frete", "sum"),
        "margem_contribuicao": ("margem_contribuicao", "sum"),
        "quantidade": ("quantidade", "sum"),
    }
    out = g.agg(**ag) if por else pd.DataFrame([{k: getattr(df[v[0]], v[1])() for k, v in ag.items()}])
    out = out.reset_index() if por else out
    rb = out["receita_bruta"]
    rl = out["receita_liquida"]
    # DOIS denominadores, sempre os dois, sempre rotulados.
    #
    # `margem_pct` (sobre receita BRUTA) é o único que fecha a decomposição
    # MECE: margem% + desconto% + custo% + frete% = 100% é identidade contábil
    # sobre a receita bruta, e não sobre a líquida.
    #
    # `margem_pct_sobre_liquida` é a convenção de COMUNICAÇÃO — é a margem que a
    # apresentação e o comitê leem, porque desconto concedido não é receita da
    # empresa. As duas diferem em cerca de 4,3 p.p. na mesma base, e trocá-las é
    # erro de leitura, não de cálculo: por isso nenhuma das duas se chama apenas
    # "margem" e as duas viajam juntas em todo resultado.
    out["margem_pct"] = (out["margem_contribuicao"] / rb * 100).round(2)
    out["margem_pct_sobre_bruta"] = out["margem_pct"]
    out["margem_pct_sobre_liquida"] = (out["margem_contribuicao"] / rl * 100).round(2)
    out["desconto_pct"] = (out["desconto_reais"] / rb * 100).round(2)
    out["custo_pct"] = (out["custo_produto"] / rb * 100).round(2)
    out["frete_pct"] = (out["custo_frete"] / rb * 100).round(2)
    out["ticket_medio"] = (rb / out["pedidos"]).round(2)
    for c in ["receita_bruta", "receita_liquida", "desconto_reais", "custo_produto",
              "custo_frete", "margem_contribuicao"]:
        out[c] = out[c].round(2)
    return out


@ferramenta(
    "margem_consolidada",
    """Margem de contribuição consolidada de toda a base aprovada: receita bruta,
    desconto, custo de produto, frete, margem em R$ e %, e a decomposição MECE
    (margem% + desconto% + custo% + frete% = 100%). Use SEMPRE como primeiro
    passo para dimensionar o problema antes de abrir por qualquer dimensão.
    Devolve a margem nos DOIS denominadores: sobre receita bruta (que fecha a
    decomposição MECE) e sobre receita líquida (a convenção de comunicação ao
    comitê). Por padrão cobre toda a base aprovada de 13 meses; passe ano para
    recortar o ano-calendário.""",
    {"ano": "ano-calendário (ex '2023'); omita para toda a base de 13 meses",
     "convencao": "'diagnostico' (padrão aqui: toda a base) ou 'decisao'",
     "excluir_meses": "meses a excluir; omita para nenhum",
     "excluir_devolvidos": "'true' exclui pedidos devolvidos; padrão inclui"},
)
def margem_consolidada(ano=None, convencao=None, excluir_meses=None,
                       excluir_devolvidos=None) -> dict:
    from . import recorte

    # O retrato consolidado é DIAGNÓSTICO: nenhum recorte por padrão, para o
    # dimensionamento do problema não depender de escolha nenhuma. Quem quiser a
    # base de decisão pede convencao='decisao' ou o ano.
    r = recorte.resolver(convencao or recorte.DIAGNOSTICO, ano, excluir_meses,
                         excluir_devolvidos)
    df = recorte.aplicar(carregar_vendas(), r)
    if df.empty:
        raise ValueError(f"nenhum pedido no recorte {recorte.descrever(r)}")
    linha = _agrega(df).iloc[0].to_dict()
    linha["recorte_aplicado"] = recorte.bloco(r, df)
    dev = df[df["devolvido"]]
    linha["decomposicao_mece_pct"] = {
        "margem": linha["margem_pct"],
        "desconto": linha["desconto_pct"],
        "custo_produto": linha["custo_pct"],
        "frete": linha["frete_pct"],
        "soma": round(
            linha["margem_pct"] + linha["desconto_pct"] + linha["custo_pct"] + linha["frete_pct"], 2
        ),
    }
    linha["denominadores"] = {
        "margem_pct_sobre_bruta": linha["margem_pct_sobre_bruta"],
        "margem_pct_sobre_liquida": linha["margem_pct_sobre_liquida"],
        "usado_na_decomposicao_mece": "receita_bruta (identidade contábil)",
        "usado_na_comunicacao_ao_comite": config.DENOMINADOR_COMUNICACAO,
        "aviso": (
            "as duas medem a MESMA margem em R$ com denominadores diferentes e diferem "
            "em ~4,3 p.p.; nunca compare uma com a outra nem apresente uma com o rótulo "
            "da outra"),
    }
    linha["devolucao"] = {
        "pedidos_devolvidos": int(len(dev)),
        "pct_pedidos": round(len(dev) / len(df) * 100, 2),
        "margem_em_pedidos_devolvidos": round(float(dev["margem_contribuicao"].sum()), 2),
        "nota": "margem_contribuicao NÃO desconta devolução; este valor é vazamento adicional.",
    }
    linha["base"] = resumo_tratamento()
    return linha


@ferramenta(
    "margem_por_dimensao",
    """Margem aberta por uma dimensão, ordenada. Responde 'onde a margem é pior'.
    A soma das linhas reconstitui exatamente o consolidado.""",
    {
        "dimensao": "uma de: canal, categoria, mes, trimestre, ano, sku, metodo_pagamento, faixa_desconto",
        "ordenar_por": "coluna de ordenação (padrão margem_pct)",
        "top": "quantas linhas retornar (padrão todas; útil para sku)",
        "dias": "tamanho da janela em dias; omita para a base inteira",
        "ate": "último dia da janela AAAA-MM-DD (só com 'dias'); omita para o último dia da base",
    },
    ["dimensao"],
)
def margem_por_dimensao(dimensao: str, ordenar_por: str = "margem_pct",
                        top: str | int | None = None,
                        dias: str | int | None = None, ate: str | None = None) -> dict:
    if dimensao not in DIMENSOES:
        raise ValueError(f"dimensao inválida: '{dimensao}'. Use uma de: {sorted(DIMENSOES)}")
    df = carregar_vendas()
    # Sem `dias` nada muda: a leitura segue sendo a da base inteira, que é como
    # esta ferramenta sempre respondeu "onde a margem é pior".
    janela = None
    if dias:
        df, janela = recorte_janela(df, dias, ate)
        if df.empty:
            return {"dimensao": dimensao, "janela": janela, "n_grupos": 0,
                    "linhas": [], "vazio": True,
                    "checagem_aditividade": {"soma_margem_grupos": 0.0,
                                             "margem_consolidada": 0.0}}
    out = _agrega(df, [DIMENSOES[dimensao]])
    if ordenar_por not in out.columns:
        raise ValueError(f"ordenar_por inválido: '{ordenar_por}'. Colunas: {list(out.columns)}")
    cresc = dimensao in ("mes", "trimestre", "ano") and ordenar_por == "margem_pct"
    out = out.sort_values(DIMENSOES[dimensao] if cresc else ordenar_por, ascending=cresc)
    total = len(out)
    if top:
        out = out.head(int(top))
    return {
        "dimensao": dimensao,
        "janela": janela,
        "n_grupos": total,
        "linhas": out.to_dict(orient="records"),
        "checagem_aditividade": {
            "soma_margem_grupos": round(float(_agrega(df, [DIMENSOES[dimensao]])["margem_contribuicao"].sum()), 2),
            "margem_consolidada": round(float(df["margem_contribuicao"].sum()), 2),
        },
    }


RE_PERIODO = re.compile(r"^\d{4}-\d{2}(?::\d{4}-\d{2})?$")


@ferramenta(
    "comparar_periodos",
    """Compara margem entre dois períodos (formato AAAA-MM ou AAAA-MM:AAAA-MM) e
    decompõe a variação de margem% em contribuição de desconto, custo e frete.
    ATENÇÃO: compare períodos de tamanho equivalente e consulte
    indice_sazonalidade antes de atribuir a diferença a mudança estrutural.""",
    {"periodo_a": "período base, ex '2023-01' ou '2023-01:2023-06'",
     "periodo_b": "período comparado, ex '2023-11' ou '2023-07:2023-12'"},
    ["periodo_a", "periodo_b"],
)
def comparar_periodos(periodo_a: str, periodo_b: str) -> dict:
    df = carregar_vendas()

    def _fatia(p: str) -> pd.DataFrame:
        # Só aceita "AAAA-MM" ou "AAAA-MM:AAAA-MM" (intervalo contíguo). Uma
        # lista com vírgula ou meses fora de ordem (ex.: para excluir um mês
        # do meio) NÃO é suportada — sem esta checagem, o filtro abaixo é uma
        # comparação de STRING, e "2023-01:2023-10,2023-12,2024-01" passava
        # sem erro só que calculava um intervalo diferente e errado (parava
        # em outubro, perdendo dezembro e janeiro/2024) sem nenhum aviso: o
        # número publicado vinha de uma ferramenta de verdade, então o
        # guardrail de rastreabilidade não pegava — o erro era de ESCOPO, não
        # de origem. Falhar alto aqui é mais seguro que acertar por sorte.
        if not RE_PERIODO.match(p.strip()):
            raise ValueError(
                f"Período '{p}' fora do formato aceito. Use 'AAAA-MM' ou "
                f"'AAAA-MM:AAAA-MM' (um único intervalo contíguo — não é "
                f"possível excluir um mês do meio numa única chamada). "
                f"Meses disponíveis: {sorted(df['mes'].unique())}"
            )
        ini, _, fim = p.partition(":")
        fim = fim or ini
        sel = df[(df["mes"] >= ini.strip()) & (df["mes"] <= fim.strip())]
        if sel.empty:
            raise ValueError(
                f"Período '{p}' não retornou pedidos. Meses disponíveis: "
                f"{sorted(df['mes'].unique())}"
            )
        return sel

    a, b = _fatia(periodo_a), _fatia(periodo_b)
    ra, rb_ = _agrega(a).iloc[0].to_dict(), _agrega(b).iloc[0].to_dict()
    delta = {
        k: round(rb_[k] - ra[k], 2)
        for k in ["margem_pct", "desconto_pct", "custo_pct", "frete_pct", "ticket_medio"]
    }
    return {
        "periodo_a": {"rotulo": periodo_a, "meses": sorted(a["mes"].unique()), **ra},
        "periodo_b": {"rotulo": periodo_b, "meses": sorted(b["mes"].unique()), **rb_},
        "variacao_pp": delta,
        "decomposicao_da_queda_de_margem": {
            "queda_margem_pp": delta["margem_pct"],
            "explicada_por_desconto_pp": -delta["desconto_pct"],
            "explicada_por_custo_pp": -delta["custo_pct"],
            "explicada_por_frete_pp": -delta["frete_pct"],
            "nota": "os três componentes somam exatamente a variação de margem (identidade contábil).",
        },
        "alerta": "Períodos de tamanhos diferentes ou com sazonalidade distinta não são comparáveis "
                  "diretamente — rode indice_sazonalidade antes de concluir.",
    }


@ferramenta(
    "margem_na_janela",
    """Margem da janela mais recente da base (padrão 7 dias) comparada com a
    janela imediatamente anterior de mesmo tamanho. É o que sustenta um
    relatório SEMANAL de verdade: margem consolidada olha os 13 meses inteiros
    e não responde "como foi a semana". Devolve os dois períodos e a variação
    em p.p. / %, sem nenhuma projeção.""",
    {"dias": "tamanho da janela em dias (padrão 7)",
     "ate": "data final AAAA-MM-DD (padrão: último pedido da base)"},
)
def margem_na_janela(dias: str | int = 7, ate: str | None = None) -> dict:
    df = carregar_vendas()
    d = pd.to_datetime(df["data_pedido"])
    n = int(dias)
    if n < 1:
        raise ValueError(f"dias deve ser >= 1, recebido {dias}")

    fim = pd.to_datetime(ate).normalize() if ate else d.max().normalize()
    # Janela fechada nos dois lados: [fim-n+1, fim] cobre exatamente n dias.
    ini = fim - pd.Timedelta(days=n - 1)
    ini_ant, fim_ant = ini - pd.Timedelta(days=n), ini - pd.Timedelta(days=1)

    def _periodo(a, b) -> dict:
        sel = df[(d >= a) & (d < b + pd.Timedelta(days=1))]
        if sel.empty:
            return {"inicio": str(a.date()), "fim": str(b.date()), "pedidos": 0,
                    "vazio": True}
        linha = _agrega(sel).iloc[0].to_dict()
        linha["pedidos"] = int(linha["pedidos"])   # contagem não é 259.0
        linha.update({"inicio": str(a.date()), "fim": str(b.date()), "vazio": False})
        return linha

    atual, anterior = _periodo(ini, fim), _periodo(ini_ant, fim_ant)

    variacao = None
    if not atual["vazio"] and not anterior["vazio"]:
        variacao = {
            "margem_pp": round(atual["margem_pct"] - anterior["margem_pct"], 2),
            "desconto_pp": round(atual["desconto_pct"] - anterior["desconto_pct"], 2),
            "receita_pct": round(
                (atual["receita_bruta"] / anterior["receita_bruta"] - 1) * 100, 2),
            "pedidos_pct": round((atual["pedidos"] / anterior["pedidos"] - 1) * 100, 2),
        }

    return {
        "dias": n,
        "janela_atual": atual,
        "janela_anterior": anterior,
        "variacao": variacao,
        "ultima_data_da_base": str(d.max()),
        # A ressalva de amostra pequena acompanha o TAMANHO real da janela: com
        # `ate` chegando até aqui, uma janela de 31 dias passou a ser pedida
        # pela tela, e o texto continuava dizendo "uma semana" — ressalva certa
        # com o número errado é pior que ressalva nenhuma, porque parece apurada.
        "nota": ("comparação entre duas janelas consecutivas da base histórica; "
                 "não é previsão nem ajuste sazonal." +
                 (f" Amostra de {n} dia(s) é pequena — variação de poucos p.p. "
                  "pode ser ruído." if n <= 14 else "")),
    }
