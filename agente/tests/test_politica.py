"""Política de desconto vigente: persistência, histórico e uso pelos simuladores."""
import json

import pytest

from vertice import politica
from vertice.engine import executar


@pytest.fixture(autouse=True)
def arquivo_isolado(tmp_path, monkeypatch):
    """Cada teste escreve no próprio arquivo — nada vaza para o politicas.json
    do projeto nem entre testes."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "politicas.json"))
    yield


# ------------------------------------------------------------ básico
def test_definir_e_consultar_politica():
    politica.definir_politica(canal="Marketplace", categoria=None, teto_pct=20,
                              responsavel="Ana (Comercial)")
    p = politica.politica_vigente(canal="Marketplace")
    assert p["teto_pct"] == 20.0
    assert p["responsavel"] == "Ana (Comercial)"
    assert p["canal"] == "Marketplace"


def test_sem_politica_definida_retorna_none():
    assert politica.politica_vigente() is None
    assert politica.teto_vigente_pct() is None


def test_politica_exige_responsavel():
    with pytest.raises(ValueError, match="responsável"):
        politica.definir_politica(canal=None, categoria=None, teto_pct=25, responsavel="")


def test_teto_aceita_25_e_0_25_como_mesmo_valor():
    politica.definir_politica(None, None, 0.25, "Ana")
    assert politica.politica_vigente()["teto_pct"] == 25.0


@pytest.mark.parametrize("invalido", [-5, 150])
def test_teto_fora_da_faixa_e_rejeitado(invalido):
    with pytest.raises(ValueError):
        politica.definir_politica(None, None, invalido, "Ana")


# ------------------------------------------------------ histórico preservado
def test_segunda_politica_vence_e_a_primeira_continua_no_historico():
    politica.definir_politica("Marketplace", None, 30, "Ana")
    politica.definir_politica("Marketplace", None, 20, "Bruno")

    vigente = politica.politica_vigente(canal="Marketplace")
    assert vigente["teto_pct"] == 20.0
    assert vigente["responsavel"] == "Bruno"

    hist = politica.historico(canal="Marketplace")
    assert len(hist) == 2
    assert [h["teto_pct"] for h in hist] == [20.0, 30.0]   # mais recente primeiro
    assert hist[-1]["responsavel"] == "Ana"                # a anterior não sumiu


def test_nada_e_sobrescrito_no_arquivo():
    politica.definir_politica("Marketplace", None, 30, "Ana")
    politica.definir_politica("Marketplace", None, 20, "Bruno")
    dados = json.loads(politica.caminho_arquivo().read_text(encoding="utf-8"))
    assert len(dados["politicas"]) == 2


def test_politica_mais_especifica_vence_a_global():
    politica.definir_politica(None, None, 25, "Global")
    politica.definir_politica("Marketplace", None, 15, "Dono do canal")
    assert politica.politica_vigente(canal="Marketplace")["teto_pct"] == 15.0
    assert politica.politica_vigente(canal="Google Ads")["teto_pct"] == 25.0


def test_politica_de_outro_canal_nao_vaza_para_consulta_global():
    politica.definir_politica("Marketplace", None, 15, "Ana")
    assert politica.politica_vigente() is None


# ----------------------------------------------------------- audit log (trace)
def test_definir_politica_registra_no_trace():
    from vertice.agent.trace import Trace

    tr = Trace(pergunta="revisão de política")
    politica.definir_politica("Marketplace", None, 20, "Ana", trace=tr)
    passos = [p for p in tr.passos if p.tipo == "politica_definida"]
    assert len(passos) == 1
    assert passos[0].conteudo["teto_pct"] == 20.0
    assert passos[0].conteudo["responsavel"] == "Ana"


def test_definir_politica_sem_trace_continua_funcionando():
    entrada = politica.definir_politica("Marketplace", None, 20, "Ana")
    assert entrada["teto_pct"] == 20.0


# --------------------------------------------- integração com os simuladores
def test_simular_teto_sem_parametro_usa_politica_vigente():
    politica.definir_politica(None, None, 20, "Ana")
    r = executar("simular_teto_desconto", {})
    assert r["teto_aplicado_pct"] == 20.0
    assert "politica_vigente" in r["origem_do_teto"]
    assert "Ana" in r["origem_do_teto"]


def test_parametro_explicito_continua_vencendo_a_politica():
    """Não quebra o comportamento existente: quem informa o teto, manda."""
    politica.definir_politica(None, None, 20, "Ana")
    r = executar("simular_teto_desconto", {"teto_pct": "25"})
    assert r["teto_aplicado_pct"] == 25.0
    assert r["origem_do_teto"] == "parametro_explicito"


def test_simular_teto_sem_parametro_e_sem_politica_levanta_typeerror():
    """TypeError de propósito (não ValueError): é ele que faz o loop do agente
    devolver o exemplo de chamada já preenchido ao modelo."""
    with pytest.raises(TypeError, match="teto_pct"):
        executar("simular_teto_desconto", {})


def test_simular_segmento_sem_desconto_usa_politica_do_recorte():
    politica.definir_politica("Marketplace", None, 10, "Ana")
    r = executar("simular_desconto_em_segmento", {"canal": "Marketplace"})
    assert r["desconto_aplicado_pct"] == 10.0
    assert "politica_vigente" in r["origem_do_desconto"]


def test_simular_segmento_com_desconto_explicito_ignora_politica():
    politica.definir_politica("Marketplace", None, 10, "Ana")
    r = executar("simular_desconto_em_segmento",
                 {"desconto_pct": "30", "canal": "Marketplace"})
    assert r["desconto_aplicado_pct"] == 30.0
    assert r["origem_do_desconto"] == "parametro_explicito"


def test_simular_segmento_sem_desconto_e_sem_politica_levanta_typeerror():
    with pytest.raises(TypeError, match="desconto_pct"):
        executar("simular_desconto_em_segmento", {"canal": "Marketplace"})


def test_exemplo_de_chamada_ainda_mostra_o_parametro_principal():
    """Regressão: o parâmetro virou opcional (por causa da política), mas o
    exemplo pronto tem de continuar mostrando ele — foi a ausência disso que
    fez o modelo repetir PARÂMETROS: {} em produção."""
    from vertice.agent.prompts import exemplo_chamada
    ex = exemplo_chamada("simular_desconto_em_segmento")
    assert '"desconto_pct":' in ex
    ex_teto = exemplo_chamada("simular_teto_desconto")
    assert '"teto_pct":' in ex_teto


def test_arquivo_corrompido_da_erro_claro():
    politica.caminho_arquivo().write_text("{ nao é json", encoding="utf-8")
    with pytest.raises(ValueError, match="corrompido"):
        politica.politica_vigente()


# ------------------------------- o teto de um canal só governa aquele canal
def test_teto_de_um_canal_nao_e_simulado_sobre_a_base_inteira():
    """Erro semântico real: canal/categoria serviam só para achar a política
    vigente, e a simulação rodava sobre todos os pedidos. Uma política "do
    Marketplace" passava a contar pedidos de Google Ads, TikTok e etc."""
    base = executar("simular_teto_desconto", {"teto_pct": 20})
    mkt = executar("simular_teto_desconto", {"teto_pct": 20, "canal": "Marketplace"})

    assert mkt["recorte"] == {"canal": "Marketplace"}
    assert mkt["pedidos_no_recorte"] < base["pedidos_no_recorte"]
    assert mkt["pedidos_afetados"] < base["pedidos_afetados"]
    assert mkt["margem_recuperada_reais"] < base["margem_recuperada_reais"]
    # o ganho continua medido contra a margem consolidada, que não muda
    assert mkt["margem_atual_reais"] == base["margem_atual_reais"]


def test_recorte_mais_estreito_recupera_menos_que_o_mais_largo():
    canal = executar("simular_teto_desconto", {"teto_pct": 20, "canal": "Marketplace"})
    fatia = executar("simular_teto_desconto",
                     {"teto_pct": 20, "canal": "Marketplace", "categoria": "Moda"})
    assert fatia["margem_recuperada_reais"] < canal["margem_recuperada_reais"]


def test_recorte_vazio_e_recusado_em_vez_de_dividir_por_zero():
    with pytest.raises(ValueError):
        executar("simular_teto_desconto",
                 {"teto_pct": 20, "canal": "Marketplace", "categoria": "Categoria Inexistente"})


# ------------------------------- o número precisa dizer que período ele cobre
def test_simulacao_declara_o_periodo_para_nao_ser_lida_como_mensal():
    """Erro real de leitura: o modelo apresentou um acumulado como ganho MENSAL.
    A guarda numérica não pega isso — o número está certo, o qualificador de tempo
    é que era inventado. Então a ferramenta declara o próprio escopo.

    O padrão do simulador passou a ser a base de DECISÃO (ano-calendário 2023),
    então são 12 meses; a base inteira de 13 continua a uma chamada de distância,
    e as duas dizem qual recorte usaram."""
    r = executar("simular_teto_desconto",
                 {"teto_pct": 17, "canal": "Email Marketing", "categoria": "Moda"})
    p = r["periodo_coberto"]
    assert p["meses"] == 12
    assert r["recorte_aplicado"]["convencao"] == "decisao"
    assert r["recorte_aplicado"]["ano"] == 2023
    assert "NÃO mensais" in p["nota"]

    tudo = executar("simular_teto_desconto",
                    {"teto_pct": 17, "canal": "Email Marketing", "categoria": "Moda",
                     "convencao": "diagnostico"})
    assert tudo["periodo_coberto"]["meses"] == 13
    assert tudo["periodo_coberto"]["inicio"] == "2023-01-01"
    assert tudo["periodo_coberto"]["fim"] == "2024-01-26"


def test_simulacao_de_segmento_tambem_declara_o_periodo():
    r = executar("simular_desconto_em_segmento",
                 {"desconto_pct": 30, "canal": "Marketplace", "mes": "2023-11"})
    p = r["periodo_coberto"]
    assert p["meses"] == 1                      # o recorte é de um mês só
    assert p["inicio"].startswith("2023-11")


def test_periodo_acompanha_o_recorte_e_nao_a_base_inteira():
    mes = executar("simular_desconto_em_segmento",
                   {"desconto_pct": 20, "mes": "2023-11"})["periodo_coberto"]
    tudo = executar("simular_desconto_em_segmento",
                    {"desconto_pct": 20})["periodo_coberto"]
    assert mes["meses"] < tudo["meses"]
