"""Normalização dos valores de filtro — mês e categórico.

Regressão de um caso real: a pergunta "Simule 30% no Marketplace em novembro"
não era respondida. O motor exigia '2023-11' e 'Marketplace' exatos, o modelo
mandava 'novembro' e 'marketplace', e as três tentativas queimavam as
iterações até o agente responder "a ferramenta não retornou resultado".
"""
import pytest

from vertice.engine import executar
from vertice.engine.filtros import (normalizar_categorico, normalizar_filtro,
                                    normalizar_mes)

MESES = ["2023-01", "2023-11", "2023-12", "2024-01"]
CANAIS = ["Email Marketing", "Marketplace", "TikTok Ads"]


# ------------------------------------------------------------------ mês
@pytest.mark.parametrize("escrito", [
    "2023-11", "2023/11", "11/2023", "11-2023",
    "novembro", "Novembro", "NOVEMBRO", "nov", "Nov",
    "novembro/2023", "novembro de 2023", "nov 2023",
])
def test_mes_aceita_as_formas_que_a_pessoa_escreve(escrito):
    assert normalizar_mes(escrito, MESES) == "2023-11"


def test_mes_sem_ano_resolve_quando_so_existe_um_ano_com_aquele_mes():
    assert normalizar_mes("dezembro", MESES) == "2023-12"
    assert normalizar_mes("12", MESES) == "2023-12"


def test_mes_ambiguo_levanta_erro_em_vez_de_escolher():
    """Janeiro existe em 2023 e 2024: escolher um seria inventar a intenção."""
    with pytest.raises(ValueError) as e:
        normalizar_mes("janeiro", MESES)
    assert "ambíguo" in str(e.value)
    assert "2023-01" in str(e.value) and "2024-01" in str(e.value)


def test_mes_com_ano_explicito_desfaz_a_ambiguidade():
    assert normalizar_mes("janeiro de 2024", MESES) == "2024-01"
    assert normalizar_mes("2023-01", MESES) == "2023-01"


def test_mes_inexistente_na_base_lista_os_disponiveis():
    with pytest.raises(ValueError) as e:
        normalizar_mes("julho", MESES)
    assert "2023-11" in str(e.value)


def test_mes_sem_sentido_nao_vira_numero_qualquer():
    for lixo in ("mês passado", "13", "0", "abcd"):
        with pytest.raises(ValueError):
            normalizar_mes(lixo, MESES)


# ---------------------------------------------------------- categórico
def test_categorico_ignora_caixa_e_acento():
    assert normalizar_categorico("canal", "marketplace", CANAIS) == "Marketplace"
    assert normalizar_categorico("canal", "TIKTOK ADS", CANAIS) == "TikTok Ads"
    assert normalizar_categorico("categoria", "acessorios", ["Acessórios"]) == "Acessórios"


def test_categorico_nao_chuta_o_mais_parecido():
    """'Facebook' não vira 'Email Marketing' por proximidade — erra explícito."""
    with pytest.raises(ValueError) as e:
        normalizar_categorico("canal", "Facebook", CANAIS)
    assert "Marketplace" in str(e.value)


def test_normalizar_filtro_escolhe_a_regra_pela_coluna():
    assert normalizar_filtro("mes", "novembro", MESES) == "2023-11"
    assert normalizar_filtro("canal", "marketplace", CANAIS) == "Marketplace"


# ------------------------------------------------- ponta a ponta no motor
def test_simulacao_responde_a_pergunta_em_portugues():
    r = executar("simular_desconto_em_segmento",
                 {"desconto_pct": "30", "canal": "marketplace", "mes": "novembro"})
    assert r["segmento"] == {"canal": "Marketplace", "mes": "2023-11"}
    assert r["pedidos_no_segmento"] > 0
    assert r["efeito_no_segmento"]["variacao_pp"] < 0   # 30% derruba a margem


def test_simulacao_de_teto_tambem_aceita_o_canal_em_minusculas():
    r = executar("simular_teto_desconto", {"teto_pct": "20", "canal": "tiktok ads"})
    assert r["pedidos_afetados"] >= 0


def test_assimetria_de_frete_aceita_canal_em_minusculas():
    assert executar("custo_assimetria_frete", {"canal": "marketplace"})["canal"] == "Marketplace"
