"""As perguntas do deck, roteadas: regressão permanente.

Doze perguntas feitas nas palavras da apresentação. Antes da convergência, onze
falhavam, e seis delas falhavam EM SILÊNCIO: a resposta saía formatada, com
número rastreável e guardrail satisfeito, e mesmo assim contradizia o slide.

A falha silenciosa é a mais cara diante de uma banca, porque não há nada na tela
para conferir. Por isso ela vira teste, e não só correção.
"""
from __future__ import annotations

import pytest

from vertice.agent.router import rotear
from vertice.engine import executar

CASOS = [
    # (pergunta, ferramenta esperada, parâmetros que PRECISAM estar na chamada)
    ("Quanto preservamos por ano com um teto de desconto de 20% fora de novembro?",
     "simular_teto_desconto", {"teto_pct": 20.0, "excluir_meses": "[11]"}),
    ("Quanto a Vértice preservaria com um teto de 20%?",
     "simular_teto_desconto", {"teto_pct": 20.0}),
    ("E se incluirmos novembro no teto de 20%?",
     "simular_teto_desconto", {"teto_pct": 20.0, "excluir_meses": "[]"}),
    ("Qual o teto de 20% na base inteira, com os devolvidos?",
     "simular_teto_desconto", {"teto_pct": 20.0, "convencao": "diagnostico",
                               "excluir_devolvidos": "false"}),
    ("Quantos pedidos podemos perder antes de o ganho zerar?", "kpis_do_teto", {}),
    ("Qual o ponto de equilíbrio do teto de 20%?", "kpis_do_teto", {"teto_pct": 20.0}),
    ("Quanto ganhamos se o Marketplace seguir a mesma regra de frete dos demais canais?",
     "regra_frete_por_limiar", {"canal": "Marketplace"}),
    ("Quanto do frete do Marketplace seria evitável?",
     "custo_assimetria_frete", {"canal": "Marketplace"}),
    ("Quanto da margem se perde depois do pedido?", "perda_pos_pedido", {}),
    ("Qual é a margem que se realiza?", "perda_pos_pedido", {}),
    ("Qual o impacto do cancelamento e da pendência na margem?", "perda_pos_pedido", {}),
    ("Qual é o caso-base interno?", "caso_base_do_plano", {}),
    ("Qual deve ser o KPI de aceite do teto?", "kpis_do_teto", {}),
    ("Quantos pedidos estão Aguardando há mais de 30 dias?", "pendencias_antigas", {}),
    ("Qual é a margem consolidada de 2023?", "margem_consolidada", {"ano": "2023"}),
]


@pytest.mark.parametrize("pergunta,ferramenta,params", CASOS,
                         ids=[c[0][:42] for c in CASOS])
def test_pergunta_do_deck_vai_para_a_ferramenta_certa(pergunta, ferramenta, params):
    r = rotear(pergunta)
    assert r.ferramenta == ferramenta, f"{pergunta!r} -> {r.ferramenta} ({r.motivo})"
    for chave, valor in params.items():
        assert r.parametros.get(chave) == valor, (
            f"{pergunta!r}: parâmetro {chave} saiu como "
            f"{r.parametros.get(chave)!r}, esperado {valor!r}")


def test_o_qualificador_da_pergunta_nao_se_perde_no_caminho():
    """A falha mais perigosa que existia: 'fora de novembro' escrito na pergunta
    e ausente da chamada. O número saía diferente do slide sem nenhum aviso."""
    com = rotear("teto de 20% fora de novembro")
    sem = rotear("teto de 20% no ano todo")
    assert com.parametros["excluir_meses"] == "[11]"
    assert sem.parametros["excluir_meses"] == "[]"
    a = executar(com.ferramenta, com.parametros)["contribuicao_preservada_reais"]
    b = executar(sem.ferramenta, sem.parametros)["contribuicao_preservada_reais"]
    assert a != b, "o recorte mudou na pergunta e o número não mudou"
    assert a == pytest.approx(241424.23, abs=0.01)
    assert b == pytest.approx(299518.63, abs=0.01)


def test_as_duas_perguntas_de_frete_sao_ferramentas_diferentes():
    """'Seguir a regra dos demais' e 'quanto seria evitável' são perguntas
    distintas, com métodos e números distintos. Antes as duas caíam na mesma."""
    regra = rotear("o Marketplace seguindo a mesma regra dos demais canais")
    contra = rotear("quanto do frete do Marketplace é evitável?")
    assert regra.ferramenta == "regra_frete_por_limiar"
    assert contra.ferramenta == "custo_assimetria_frete"


def test_todo_roteamento_do_deck_executa_sem_erro():
    """Rotear certo e quebrar na execução não resolve nada."""
    for pergunta, _, _ in CASOS:
        r = rotear(pergunta)
        assert r.determinado, f"{pergunta!r} ficou com faltando={r.faltando}"
        resultado = executar(r.ferramenta, r.parametros)
        assert isinstance(resultado, dict) and resultado
        assert resultado["marca"] in ("●", "◐", "○")
