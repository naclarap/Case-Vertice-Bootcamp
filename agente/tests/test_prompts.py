"""Testes do extrator de valores literais da pergunta (prompts.py).

Este extrator NÃO calcula nada — só lê texto que o próprio usuário escreveu,
para pré-preencher a chamada de retentativa quando uma ferramenta falha por
parâmetro ausente. É crítico que ele nunca invente/adivinhe o que não está
explícito: um valor errado aqui vira um parâmetro errado na ferramenta.
"""
import pytest

from vertice.agent.prompts import (_extrair_valores_da_pergunta, cobrar_parametros,
                                   exemplo_chamada)


@pytest.mark.parametrize("pergunta,esperado", [
    ("aplicar 30% de desconto", "30"),
    ("e se desse 12,5% de desconto?", "12.5"),
    ("reduzir para 7.5% no grupo alvo", "7.5"),
    ("sem nenhum percentual aqui", None),
])
def test_extrai_percentual(pergunta, esperado):
    r = _extrair_valores_da_pergunta(pergunta)
    assert r.get("percentual") == esperado


def test_extrai_canal_conhecido_da_base():
    r = _extrair_valores_da_pergunta("quanto o marketplace paga de frete a mais?")
    assert r["canal"] == "Marketplace"  # capitalização real da base, não a da pergunta


def test_nao_extrai_canal_quando_nenhum_e_mencionado():
    r = _extrair_valores_da_pergunta("qual o impacto geral do desconto?")
    assert "canal" not in r


@pytest.mark.parametrize("mes,esperado", [
    ("durante novembro", "2023-11"),   # único novembro na base -> sem ambiguidade
    ("em dezembro", "2023-12"),
    ("no mês de março", "2023-03"),
])
def test_extrai_mes_sem_ano_quando_nao_ambiguo(mes, esperado):
    r = _extrair_valores_da_pergunta(f"simule o desconto {mes}")
    assert r.get("mes") == esperado


def test_janeiro_sem_ano_fica_ambiguo_e_nao_e_extraido():
    """A base cobre janeiro/2023 E janeiro/2024 — sem ano explícito, não adivinha."""
    r = _extrair_valores_da_pergunta("o que aconteceu em janeiro?")
    assert "mes" not in r


def test_janeiro_com_ano_explicito_resolve_a_ambiguidade():
    r = _extrair_valores_da_pergunta("o que aconteceu em janeiro de 2024?")
    assert r["mes"] == "2024-01"


def test_pergunta_sem_nenhum_valor_devolve_dict_vazio():
    assert _extrair_valores_da_pergunta("por que a margem caiu?") == {}


def test_extracao_e_best_effort_nunca_levanta_excecao():
    for p in ["", None, "   ", "!!!@#$%^&*()", "a" * 5000]:
        _extrair_valores_da_pergunta(p)  # não pode lançar


# --------------------------------------------------- exemplo_chamada / cobrança
def test_exemplo_sem_pergunta_so_mostra_o_obrigatorio():
    ex = exemplo_chamada("simular_desconto_em_segmento")
    assert '"desconto_pct":' in ex
    assert "canal" not in ex   # opcional, sem contexto -> omitido, não vira <placeholder>
    assert "mes" not in ex
    assert "categoria" not in ex


def test_exemplo_com_pergunta_completa_preenche_tudo_que_da():
    p = "Simule 30% de desconto no Marketplace em novembro"
    ex = exemplo_chamada("simular_desconto_em_segmento", p)
    assert '"desconto_pct": "30"' in ex
    assert '"canal": "Marketplace"' in ex
    assert '"mes": "2023-11"' in ex
    assert "categoria" not in ex  # não mencionado, opcional -> continua omitido
    assert "<" not in ex          # nada sobrou como placeholder


def test_exemplo_de_ferramenta_sem_parametros():
    # margem_consolidada passou a aceitar recorte (ano, convenção): todos
    # opcionais, então o exemplo continua sem parâmetros preenchidos.
    assert exemplo_chamada("margem_consolidada") == (
        "  margem_consolidada\n    obrigatórios: nenhum\n    PARÂMETROS: {}")


def test_cobrar_parametros_instrui_copiar_as_duas_linhas_exatas():
    msg = cobrar_parametros("simular_desconto_em_segmento",
                            "simule 30% no Marketplace em novembro")
    assert "AÇÃO: simular_desconto_em_segmento" in msg
    assert 'PARÂMETROS: {"desconto_pct": "30", "canal": "Marketplace", "mes": "2023-11"}' in msg
    assert "NÃO" in msg.upper() or "não" in msg  # reforça para não desistir
