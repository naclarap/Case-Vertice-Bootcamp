"""Auditoria de qualidade de dados: camada determinística + camada semântica."""
import pytest

from vertice.auditoria_semantica import ORIGEM_IA, sugerir_inconsistencias_semanticas
from vertice.engine import REGISTRO, executar
from vertice.engine.auditoria import TEXTO_LACUNA_PRAZO_DEVOLUCAO


# ------------------------------------------ regressão dos números já validados
def test_nenhum_sku_orfao_em_vendas():
    r = executar("checar_integridade_referencial",
                 {"tabela_a": "vendas", "coluna_fk": "sku_id",
                  "tabela_b": "estoque", "coluna_pk": "sku_id"})
    assert r["registros_orfaos"] == 0
    assert r["status"] == "ok"


def test_nenhum_cliente_orfao_em_vendas():
    r = executar("checar_integridade_referencial",
                 {"tabela_a": "vendas", "coluna_fk": "customer_id",
                  "tabela_b": "clientes", "coluna_pk": "customer_id"})
    assert r["registros_orfaos"] == 0


def test_nenhuma_duplicata_de_order_id():
    r = executar("checar_duplicatas_chave", {"tabela": "vendas", "coluna_chave": "order_id"})
    assert r["linhas_duplicadas"] == 0
    assert r["status"] == "ok"


def test_outlier_de_desconto_fica_perto_de_7_pct():
    """~6,9% já validado manualmente contra a base real — mais alto que as
    demais colunas numéricas, por isso é o caso de regressão."""
    r = executar("checar_outliers_iqr", {"tabela": "vendas", "coluna": "desconto_reais"})
    assert 6.0 <= r["pct_outliers"] <= 8.0, r["pct_outliers"]
    assert r["outliers"] > 0


def test_resultado_limpo_tambem_e_registrado():
    """'Verificado e sem problema' é resultado válido: a checagem devolve o
    número apurado (zero) em vez de omitir."""
    r = executar("checar_duplicatas_chave", {"tabela": "clientes",
                                              "coluna_chave": "customer_id"})
    assert r["linhas_duplicadas"] == 0
    assert r["linhas_verificadas"] > 0
    assert r["status"] == "ok"


# --------------------------------------------------------- completude e faixas
def test_completude_lista_pct_de_nulo_por_coluna():
    r = executar("checar_completude", {"tabela": "vendas"})
    assert r["colunas"] == len(r["por_coluna"])
    assert all("pct_nulos" in c for c in r["por_coluna"])
    # ordenado do mais incompleto para o menos
    pcts = [c["pct_nulos"] for c in r["por_coluna"]]
    assert pcts == sorted(pcts, reverse=True)


def test_faixa_implausivel_nao_acha_tempo_de_entrega_negativo():
    r = executar("checar_faixa_implausivel",
                 {"tabela": "vendas", "coluna": "tempo_entrega_real", "minimo": 0})
    assert r["abaixo_do_minimo"] == 0
    assert r["status"] == "ok"


def test_faixa_implausivel_exige_ao_menos_um_limite():
    with pytest.raises(ValueError, match="minimo"):
        executar("checar_faixa_implausivel", {"tabela": "vendas", "coluna": "quantidade"})


def test_coluna_inexistente_lista_as_disponiveis():
    with pytest.raises(ValueError, match="não existe em"):
        executar("checar_outliers_iqr", {"tabela": "vendas", "coluna": "coluna_fantasma"})
    with pytest.raises(ValueError, match="não existe em"):
        executar("verificar_consistencia_categorica",
                 {"tabela": "vendas", "coluna_a": "canal", "coluna_b": "coluna_fantasma"})


def test_tabela_inexistente_lista_as_disponiveis():
    with pytest.raises(ValueError, match="tabela 'galaxia' não existe"):
        executar("checar_completude", {"tabela": "galaxia"})


# ------------------------------------------- o caso real: motivo x categoria
def test_tamanho_errado_fora_de_moda_passa_de_400_registros():
    """O achado do mentor, agora como ferramenta reutilizável: 'Tamanho errado'
    aplicado a categoria onde tamanho não é atributo relevante."""
    r = executar("verificar_consistencia_categorica",
                 {"tabela": "vendas", "coluna_a": "categoria",
                  "coluna_b": "motivo_devolucao"})
    fora_de_moda = sum(c["registros"] for c in r["celulas"]
                       if c["motivo_devolucao"] == "Tamanho errado"
                       and c["categoria"] != "Moda")
    assert fora_de_moda >= 400, fora_de_moda


def test_consistencia_categorica_traz_contagem_e_percentual_por_celula():
    r = executar("verificar_consistencia_categorica",
                 {"tabela": "vendas", "coluna_a": "canal", "coluna_b": "metodo_pagamento"})
    assert r["celulas_preenchidas"] > 0
    c = r["celulas"][0]
    assert c["registros"] > 0
    for campo in ("pct_do_total", "pct_da_linha", "pct_da_coluna"):
        assert 0 <= c[campo] <= 100
    assert sum(x["registros"] for x in r["celulas"]) == r["registros_considerados"]


@pytest.mark.parametrize("tabela,ca,cb", [
    ("vendas", "categoria", "motivo_devolucao"),
    ("vendas", "canal", "metodo_pagamento"),
    ("estoque", "categoria", "subcategoria"),
    ("atendimento", "categoria_problema", "canal_entrada"),
])
def test_pares_de_colunas_do_teste_inicial_rodam(tabela, ca, cb):
    r = executar("verificar_consistencia_categorica",
                 {"tabela": tabela, "coluna_a": ca, "coluna_b": cb})
    assert r["registros_considerados"] > 0
    assert r["celulas_preenchidas"] > 0


# -------------------------------------------- auditoria roda sobre base bruta
def test_auditoria_le_a_base_bruta_e_nao_a_filtrada():
    """A base de margem só tem pedidos aprovados (24.454); a auditoria precisa
    enxergar a base inteira, senão não encontra o que o filtro escondeu."""
    from vertice.data import carregar_vendas
    r = executar("checar_completude", {"tabela": "vendas"})
    assert r["linhas"] > len(carregar_vendas())


# ------------------------------------------------ item 5: lacuna de prazo CDC
def test_prazo_de_devolucao_relata_lacuna_sem_estimar():
    """Não existe data de solicitação de devolução em nenhuma base — a função
    declara a lacuna e não tenta aproximar o cálculo por data de pedido."""
    r = executar("checar_devolucao_fora_prazo", {})
    assert r["disponivel"] is False
    assert r["lacuna"] == TEXTO_LACUNA_PRAZO_DEVOLUCAO
    # nenhum número de prazo é estimado
    assert "devolucoes_fora_do_prazo" not in r
    assert "pct_fora_do_prazo" not in r


def test_lacuna_de_prazo_aparece_no_relatorio_de_auditoria():
    r = executar("relatorio_auditoria_dados", {})
    assert TEXTO_LACUNA_PRAZO_DEVOLUCAO in r["lacunas_de_dado"]


def test_relatorio_de_auditoria_registra_tambem_o_que_veio_limpo():
    r = executar("relatorio_auditoria_dados", {})
    assert r["total_checagens"] >= 7
    limpas = [c for c in r["checagens"]
              if c.get("resultado", {}).get("status") == "ok"]
    assert limpas, "resultado sem problema também precisa ficar registrado"


# ------------------------------------------------ camada 2: assistida por LLM
class _LLMQuebrado:
    def completar(self, mensagens, modelo, tools=None):
        raise RuntimeError("gateway fora do ar")


class _LLMFalso:
    def __init__(self, conteudo):
        self.conteudo = conteudo

    def completar(self, mensagens, modelo, tools=None):
        class _M:
            pass
        m = _M()
        m.content = self.conteudo
        m.tool_calls = None
        return m


def test_sugestao_semantica_degrada_sem_excecao_quando_llm_falha():
    r = sugerir_inconsistencias_semanticas("vendas", "categoria", "motivo_devolucao",
                                            llm=_LLMQuebrado())
    assert r["disponivel"] is False
    assert "gateway fora do ar" in r["motivo"]


def test_sugestao_semantica_usa_contagem_deterministica_e_nao_a_do_modelo():
    """O modelo cita um número errado de propósito; o alerta tem de sair com a
    contagem real da Camada 1."""
    resposta = ('{"suspeitas": [{"valor_a": "Beleza", "valor_b": "Tamanho errado",'
                ' "justificativa": "Beleza nao tem tamanho como atributo (999999 casos)"}]}')
    r = sugerir_inconsistencias_semanticas("vendas", "categoria", "motivo_devolucao",
                                            llm=_LLMFalso(resposta))
    assert r["disponivel"] is True
    alerta = r["alertas"][0]
    assert alerta["registros_afetados"] == 318      # contagem real de Beleza
    assert alerta["registros_afetados"] != 999999


def test_todo_alerta_semantico_e_marcado_como_pendente_de_revisao():
    resposta = ('{"suspeitas": [{"valor_a": "Beleza", "valor_b": "Tamanho errado",'
                ' "justificativa": "implausivel"}]}')
    r = sugerir_inconsistencias_semanticas("vendas", "categoria", "motivo_devolucao",
                                            llm=_LLMFalso(resposta))
    assert all(a["origem"] == ORIGEM_IA for a in r["alertas"])
    assert r["alertas"][0]["origem"] == "sugestao_ia_pendente_revisao"


def test_celula_inventada_pelo_modelo_e_descartada():
    """Combinação que não existe na tabela determinística não vira alerta."""
    resposta = ('{"suspeitas": [{"valor_a": "Categoria Fantasma", '
                '"valor_b": "Motivo Fantasma", "justificativa": "inventado"}]}')
    r = sugerir_inconsistencias_semanticas("vendas", "categoria", "motivo_devolucao",
                                            llm=_LLMFalso(resposta))
    assert r["alertas"] == []
    assert r["sugestoes_descartadas"][0]["valor_a"] == "Categoria Fantasma"


def test_sugestao_semantica_tolera_json_embrulhado_em_markdown():
    resposta = ('Claro! Segue a análise:\n```json\n{"suspeitas": '
                '[{"valor_a": "Beleza", "valor_b": "Tamanho errado", '
                '"justificativa": "x"}]}\n```')
    r = sugerir_inconsistencias_semanticas("vendas", "categoria", "motivo_devolucao",
                                            llm=_LLMFalso(resposta))
    assert r["disponivel"] is True
    assert r["total_alertas"] == 1


def test_resposta_sem_json_nenhum_degrada_em_vez_de_quebrar():
    r = sugerir_inconsistencias_semanticas("vendas", "categoria", "motivo_devolucao",
                                            llm=_LLMFalso("não consegui analisar"))
    assert r["disponivel"] is False


def test_ferramentas_de_auditoria_estao_no_registro():
    for nome in ("checar_integridade_referencial", "checar_duplicatas_chave",
                 "checar_completude", "checar_outliers_iqr",
                 "checar_faixa_implausivel", "verificar_consistencia_categorica",
                 "checar_devolucao_fora_prazo", "relatorio_auditoria_dados"):
        assert nome in REGISTRO, nome


# --------------------------------------------- status honesto das checagens
# "Sem problema" para uma checagem que ACHOU algo é o pior resultado possível
# numa auditoria: esconde justamente o que ela existe para mostrar.
def test_completude_encontra_a_linha_quebrada_e_marca_atencao():
    """Contar COLUNA com nulo escondia o achado: as 13 colunas com nulo em
    vendas são todas a MESMA linha, um registro com quase tudo vazio."""
    r = executar("checar_completude", {"tabela": "vendas"})
    assert r["linhas_incompletas"] == 1
    assert r["linhas_quebradas"] == 1
    assert r["status"] == "atencao"
    exemplo = r["exemplos_linhas_quebradas"][0]
    assert exemplo["campos_vazios"] >= 10
    assert exemplo["order_id"].startswith("ORD-")


def test_outliers_com_achado_nunca_saem_como_sem_problema():
    r = executar("checar_outliers_iqr", {"tabela": "vendas", "coluna": "desconto_reais"})
    assert r["outliers"] > 0
    assert r["status"] == "revisar"     # nem 'ok' (achou algo) nem 'atencao' (não é erro provado)


def test_faixa_de_dominio_responde_o_que_o_outlier_deixa_em_aberto():
    """O par das duas checagens é o que fecha a leitura: há 1.910 outliers
    estatísticos em desconto_reais, e zero valor impossível."""
    r = executar("checar_faixa_implausivel",
                 {"tabela": "vendas", "coluna": "desconto_reais", "minimo": 0})
    assert r["fora_da_faixa"] == 0
    assert r["status"] == "ok"


def test_relatorio_separa_atencao_de_revisar_de_limpa():
    r = executar("relatorio_auditoria_dados")
    assert r["checagens_com_atencao"] >= 1          # a linha quebrada
    assert r["checagens_a_revisar"] >= 1            # os outliers
    soma = (r["checagens_com_atencao"] + r["checagens_a_revisar"]
            + r["checagens_limpas"])
    assert soma == r["total_checagens"]


def test_html_nao_inventa_sem_problema_para_checagem_sem_status():
    """Regressão: o render caía em 'ok' quando o resultado não trazia status —
    foi assim que 1.910 outliers apareceram com selo verde."""
    from vertice.render_html import render_auditoria_html
    d = {"checagens": [{"checagem": "x", "parametros": {}, "resultado": {"nada": 1}}],
         "total_checagens": 1, "checagens_com_atencao": 0, "checagens_a_revisar": 0}
    html = render_auditoria_html(d)
    assert "Sem problema" not in html
    assert "Requer leitura" in html
