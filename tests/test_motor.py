"""Testes do motor determinístico: aditividade, achados de negócio e estatística."""
import pytest

from vertice.engine import REGISTRO, executar


# --------------------------------------------------------------- aditividade
@pytest.mark.parametrize("dim", ["canal", "categoria", "mes", "metodo_pagamento"])
def test_margem_por_dimensao_soma_de_volta_ao_consolidado(dim):
    total = executar("margem_consolidada")
    d = executar("margem_por_dimensao", {"dimensao": dim})
    soma_rb = sum(l["receita_bruta"] for l in d["linhas"])
    soma_mg = sum(l["margem_contribuicao"] for l in d["linhas"])
    assert soma_rb == pytest.approx(total["receita_bruta"], rel=1e-6)
    assert soma_mg == pytest.approx(total["margem_contribuicao"], rel=1e-6)


def test_faixas_de_desconto_cobrem_todos_os_pedidos():
    total = executar("margem_consolidada")
    f = executar("tabela_faixas_desconto")
    assert sum(x["pedidos"] for x in f["faixas"]) == total["pedidos"]


# ---------------------------------------------------- achados de negócio (1)
def test_marketplace_tem_margem_significativamente_menor():
    """Achado principal 1: Marketplace tem margem menor, com significância."""
    r = executar("teste_t_welch", {"metrica": "margem_pct", "coluna_grupo": "canal",
                                   "grupo_a": "Marketplace"})
    assert r["grupo_a"]["media"] < r["grupo_b"]["media"]
    assert r["p_valor"] < 0.001
    assert r["forca"] == "FORTE"
    assert r["ic95_diferenca"][1] < 0, "IC95 da diferença deve excluir zero"


def test_marketplace_nao_concede_frete_gratis():
    p = executar("politica_frete_por_canal")
    canais = {c["canal"]: c for c in p["por_canal"]}
    assert canais["Marketplace"]["pct_frete_gratis"] < 1.0
    outros = [c for n, c in canais.items() if n != "Marketplace"]
    assert all(c["pct_frete_gratis"] > 50 for c in outros)
    assert "Marketplace" in p["canais_fora_da_politica"]


# ---------------------------------------------------- achados de negócio (2)
def test_frete_e_o_componente_mais_disperso_entre_canais():
    """Achado principal 2: frete é mais disperso que desconto e custo."""
    d = executar("dispersao_componentes_entre_canais")
    assert d["componente_mais_disperso"] == "frete_pct"
    cv = {r["componente"]: r["coef_variacao"] for r in d["dispersao_ordenada"]}
    assert cv["frete_pct"] > cv["desconto_pct"] * 5
    assert cv["frete_pct"] > cv["custo_pct"] * 5


def test_assimetria_de_frete_do_marketplace_e_material():
    c = executar("custo_assimetria_frete", {"canal": "Marketplace"})
    assert c["frete_evitavel_reais"] > 0
    assert c["pct_frete_gratis_no_canal"] < c["pct_frete_gratis_nos_demais"]
    # Corrigir a assimetria aproxima o canal da margem dos demais.
    assert c["margem_pct_canal_pos_correcao"] > c["margem_pct_atual_canal"]
    assert "premissa" in c


# ---------------------------------------------------- achados de negócio (3)
def test_desconto_nao_compra_volume_incremental():
    """Achado principal 3: itens/pedido e ticket não variam entre faixas de desconto,
    mas a margem cai monotonicamente."""
    f = executar("tabela_faixas_desconto")
    faixas = [x for x in f["faixas"] if x["pedidos"] > 0]
    itens = [x["itens_por_pedido"] for x in faixas]
    assert max(itens) - min(itens) < 0.2, "itens/pedido deveria ser estável entre faixas"
    assert f["amplitude_ticket_pct"] < 10, "ticket médio deveria ser estável entre faixas"
    margens = [x["margem_pct"] for x in faixas]
    assert margens == sorted(margens, reverse=True), "margem deveria cair com o desconto"
    assert "CORRELAÇÃO" in f["ressalva_causal"].upper()


def test_desconto_alto_concentra_o_deficit():
    c = executar("cenarios_reducao_desconto", {"limiar_pct": 25})
    # Minoria dos pedidos, maioria do desconto concedido.
    assert c["grupo_alvo"]["pct_dos_pedidos"] < 20
    assert c["grupo_alvo"]["share_do_desconto_total_pct"] > 50


def test_cenarios_sao_monotonicos_e_declaram_premissa():
    c = executar("cenarios_reducao_desconto", {"limiar_pct": 25})
    ganhos = [x["margem_recuperada_reais"] for x in c["cenarios"]]
    assert ganhos == sorted(ganhos)
    assert "VOLUME CONSTANTE" in c["premissa"].upper()


def test_teto_de_desconto_reduz_desconto_do_grupo():
    s = executar("simular_teto_desconto", {"teto_pct": 25})
    assert s["desconto_pos_teto_no_grupo"] < s["desconto_atual_no_grupo"]
    assert s["margem_recuperada_reais"] > 0
    assert s["margem_pos_teto_reais"] > s["margem_atual_reais"]


# ------------------------------------------------------------- armadilhas
def test_regressao_da_identidade_contabil_e_sinalizada():
    """R²≈1 aqui é artefato; a ferramenta deve avisar em vez de deixar virar 'causa raiz'."""
    r = executar("regressao_linear_multipla",
                 {"y": "margem_pct", "x": "desconto_pct,custo_pct,frete_pct"})
    assert r["r2"] > 0.999
    assert r["alerta_identidade_contabil"] is not None
    assert "IDENTIDADE" in r["alerta_identidade_contabil"].upper()


def test_regressao_normal_nao_dispara_alerta_de_identidade():
    r = executar("regressao_linear_multipla", {"y": "margem_pct", "x": "desconto_pct"})
    assert r["alerta_identidade_contabil"] is None
    assert r["r2"] < 0.999


def test_marketing_sinaliza_inflacao_de_receita():
    r = executar("ranking_roas_canais")
    a = r["auditoria_receita_gerada"]
    assert a["fator_inflacao"] > 10
    assert "NÃO usar em R$" in a["veredito"]


def test_sazonalidade_identifica_mes_parcial():
    s = executar("indice_sazonalidade")
    assert s["meses_parciais"], "a base termina em mês parcial; precisa ser sinalizado"
    assert s["alerta"] is not None


# ------------------------------------------------------------- estatística
@pytest.mark.parametrize("p,r2,n,esperado", [
    (0.0001, 0.9, 50, "FORTE"),      # p<0,001 e R²>0,7
    (0.0001, 0.1, 5000, "FORTE"),    # p<0,001 e n>1000
    (0.0001, 0.1, 50, "FRACA"),      # p<0,001 mas nem R² nem n
    (0.02, None, 500, "MODERADA"),
    (0.02, None, 50, "FRACA"),
    (0.30, 0.9, 5000, "FRACA"),      # não significante
])
def test_classificacao_de_forca_da_evidencia(p, r2, n, esperado):
    r = executar("classificar_evidencia", {"p_valor": p, "r2": r2, "n": n})
    assert r["forca"] == esperado


def test_anova_entre_canais_detecta_diferenca():
    r = executar("anova_um_fator", {"metrica": "margem_pct", "coluna_grupo": "canal"})
    assert r["p_valor"] < 0.001
    assert r["n_grupos"] == 7
    assert 0 <= r["eta_quadrado"] <= 1


def test_qui_quadrado_canal_x_frete_gratis():
    r = executar("qui_quadrado_independencia",
                 {"coluna_a": "canal", "coluna_b": "frete_gratis"})
    assert r["p_valor"] < 0.001
    assert r["v_cramer"] > 0.3


# ------------------------------------------------------------- contrato das ferramentas
def test_ferramenta_inexistente_levanta_erro_util():
    with pytest.raises(KeyError, match="não existe"):
        executar("ferramenta_fantasma")


def test_parametro_invalido_e_rejeitado():
    with pytest.raises(TypeError, match="inválido"):
        executar("margem_por_dimensao", {"dimensao": "canal", "coluna_inventada": "x"})


def test_parametro_obrigatorio_ausente_e_rejeitado():
    with pytest.raises(TypeError, match="obrigatório"):
        executar("margem_por_dimensao", {})


def test_valor_invalido_de_dimensao_lista_opcoes():
    with pytest.raises(ValueError, match="dimensao inválida"):
        executar("margem_por_dimensao", {"dimensao": "planeta"})


# --------------------------------------------------- comparar_periodos (bug real)
def test_comparar_periodos_aceita_mes_unico_e_intervalo():
    r = executar("comparar_periodos", {"periodo_a": "2023-01:2023-10", "periodo_b": "2023-11"})
    assert r["periodo_a"]["meses"] == [f"2023-{m:02d}" for m in range(1, 11)]
    r2 = executar("comparar_periodos", {"periodo_a": "2023-01", "periodo_b": "2023-11"})
    assert r2["periodo_a"]["meses"] == ["2023-01"]


def test_comparar_periodos_rejeita_lista_com_virgula():
    """Regressão de produção: o modelo pediu 'excluir novembro' com
    '2023-01:2023-10,2023-12,2024-01' (formato não suportado). Sem validação,
    o filtro fazia comparação de STRING e calculava, em silêncio, um período
    diferente do pedido (parava em outubro — perdia dezembro e janeiro/2024)
    sem levantar erro. O número citado na resposta vinha de uma ferramenta de
    verdade, então o guardrail de rastreabilidade não pegava: o erro era de
    ESCOPO dos dados, não de origem do número. Agora falha alto e explícito."""
    with pytest.raises(ValueError, match="formato aceito"):
        executar("comparar_periodos",
                  {"periodo_a": "2023-01:2023-10,2023-12,2024-01", "periodo_b": "2023-11"})


def test_todas_as_ferramentas_tem_descricao_e_schema():
    assert len(REGISTRO) >= 18
    for nome, f in REGISTRO.items():
        assert f.descricao and len(f.descricao) > 40, nome
        s = f.schema_openai()
        assert s["function"]["name"] == nome
        assert set(f.obrigatorios) <= set(f.parametros), nome


# ------------------------------- simulação de desconto aplicado a um segmento
def test_simular_desconto_em_segmento_responde_pergunta_de_canal_e_mes():
    """Caso real que falhou em produção por não existir ferramenta:
    'aplicar 30% de desconto no Marketplace durante novembro'."""
    r = executar("simular_desconto_em_segmento",
                 {"desconto_pct": "30", "canal": "Marketplace", "mes": "2023-11"})
    assert r["segmento"] == {"canal": "Marketplace", "mes": "2023-11"}
    assert r["desconto_aplicado_pct"] == 30.0
    assert r["pedidos_no_segmento"] > 0
    # Subir o desconto de ~7,8% para 30% tem de reduzir a margem.
    assert r["efeito_no_segmento"]["variacao_pp"] < 0
    assert r["efeito_consolidado"]["variacao_pp"] < 0
    assert r["efeito_consolidado"]["impacto_reais"] < 0
    assert "VOLUME CONSTANTE" in r["premissa"].upper()


def test_simulacao_de_segmento_bate_com_a_identidade_contabil():
    """A margem simulada tem de ser exatamente a atual menos a variação de desconto."""
    r = executar("simular_desconto_em_segmento", {"desconto_pct": "30", "canal": "Marketplace"})
    e = r["efeito_no_segmento"]
    assert e["margem_simulada_reais"] == pytest.approx(
        e["margem_atual_reais"] - r["variacao_desconto_reais"], abs=0.02)
    c = r["efeito_consolidado"]
    assert c["margem_simulada_reais"] == pytest.approx(
        c["margem_atual_reais"] - r["variacao_desconto_reais"], abs=0.02)


def test_simulacao_de_segmento_sem_filtro_afeta_a_base_inteira():
    r = executar("simular_desconto_em_segmento", {"desconto_pct": "30"})
    total = executar("margem_consolidada")
    assert r["pedidos_no_segmento"] == total["pedidos"]
    assert r["pct_da_receita_total"] == pytest.approx(100.0, abs=0.01)


def test_reduzir_desconto_no_segmento_aumenta_margem():
    """Sentido oposto: 0% de desconto no Marketplace tem de melhorar a margem."""
    r = executar("simular_desconto_em_segmento", {"desconto_pct": "0", "canal": "Marketplace"})
    assert r["efeito_no_segmento"]["variacao_pp"] > 0
    assert r["efeito_consolidado"]["impacto_reais"] > 0


@pytest.mark.parametrize("params,trecho", [
    ({"desconto_pct": "30", "canal": "Shopee"}, "inexistente"),
    ({"desconto_pct": "30", "mes": "2019-01"}, "inexistente"),
    ({"desconto_pct": "150"}, "entre 0 e 100"),
])
def test_simulacao_de_segmento_rejeita_entrada_invalida(params, trecho):
    with pytest.raises(ValueError, match=trecho):
        executar("simular_desconto_em_segmento", params)


def test_erro_de_segmento_lista_valores_disponiveis():
    """O modelo precisa conseguir se corrigir a partir da mensagem."""
    with pytest.raises(ValueError, match="Marketplace"):
        executar("simular_desconto_em_segmento", {"desconto_pct": "30", "canal": "Shopee"})


# ------------------------------------------- catálogo compacto (limite de tokens)
def test_catalogo_compacto_e_bem_menor_e_nao_perde_ferramenta():
    """Provedores com teto baixo de tokens por requisição (camada gratuita da
    Groq) recusavam com 413: o catálogo completo sozinho tem ~12,8 mil chars."""
    from vertice.engine.registry import REGISTRO, catalogo_texto
    completo, compacto = catalogo_texto(), catalogo_texto(compacto=True)
    assert len(compacto) < len(completo) / 2
    for nome in REGISTRO:
        assert nome in compacto          # nenhuma ferramenta some


def test_catalogo_compacto_preserva_a_distincao_teto_x_aplicar():
    """É a distinção que o roteador existe para respeitar — não pode sumir no
    encurtamento."""
    from vertice.engine.registry import catalogo_texto
    linhas = {l.split("(")[0].lstrip("- "): l for l in
              catalogo_texto(compacto=True).splitlines()}
    assert "TETO" in linhas["simular_teto_desconto"]
    assert "APLICAR" in linhas["simular_desconto_em_segmento"]


def test_catalogo_compacto_nao_corta_frase_no_meio():
    from vertice.engine.registry import catalogo_texto
    for linha in catalogo_texto(compacto=True).splitlines():
        assert linha.endswith("."), linha
        assert not linha.endswith("ex:."), linha


# ------------------------------------------- janela com data de fim explícita
def test_janela_com_ate_termina_no_dia_pedido():
    r = executar("margem_na_janela", {"dias": 31, "ate": "2023-03-31"})
    assert r["janela_atual"]["inicio"] == "2023-03-01"
    assert r["janela_atual"]["fim"] == "2023-03-31"
    assert r["janela_anterior"]["fim"] == "2023-02-28"


def test_janela_sem_ate_termina_no_ultimo_dia_da_base():
    r = executar("margem_na_janela", {"dias": 7})
    assert r["janela_atual"]["fim"] == str(r["ultima_data_da_base"])[:10]


def test_ressalva_de_amostra_pequena_acompanha_o_tamanho_da_janela():
    """Ressalva certa com o número errado é pior que ressalva nenhuma: parece
    apurada. O texto dizia "uma semana" numa janela de 31 dias."""
    curta = executar("margem_na_janela", {"dias": 7})["nota"]
    longa = executar("margem_na_janela", {"dias": 31, "ate": "2023-03-31"})["nota"]
    assert "7 dia(s) é pequena" in curta
    assert "pequena" not in longa
    assert "não é previsão nem ajuste sazonal" in curta and "não é previsão" in longa
