"""Regressão: a chave de API não pode ficar travada no momento do import.

Bug real observado: no notebook, a Parte 1 (motor) importa vertice.config antes
de a Parte 2 pedir e definir ELOAGENTS_API_KEY. Como config.ELO_API_KEY era lido
uma única vez no import, ficava travado em "" para sempre, e EloAgentsLLM()
recusava uma chave que na verdade tinha sido definida corretamente.
"""
import importlib
import os

import pytest


@pytest.fixture
def sem_chave_no_ambiente(monkeypatch):
    monkeypatch.delenv("ELOAGENTS_API_KEY", raising=False)
    yield monkeypatch


def test_chave_gateway_le_o_ambiente_atual(sem_chave_no_ambiente):
    from vertice import config
    assert config.chave_gateway() == ""
    sem_chave_no_ambiente.setenv("ELOAGENTS_API_KEY", "sk-teste-123")
    assert config.chave_gateway() == "sk-teste-123"


def test_chave_gateway_funciona_mesmo_com_constante_congelada_vazia(sem_chave_no_ambiente):
    """Reproduz o bug: importa o módulo (congela ELO_API_KEY="") ANTES de definir
    a variável de ambiente — exatamente a ordem Parte 1 -> Parte 2 do notebook."""
    from vertice import config
    importlib.reload(config)          # simula "config já foi importado sem a chave"
    assert config.ELO_API_KEY == ""   # a constante congelada continua vazia — esperado

    sem_chave_no_ambiente.setenv("ELOAGENTS_API_KEY", "sk-definida-depois")
    assert config.chave_gateway() == "sk-definida-depois", (
        "chave_gateway() tem de reler o ambiente, não confiar na constante congelada"
    )
    # SEM reload aqui: recarregar com a chave ainda no ambiente (o monkeypatch só
    # desfaz depois que a função termina) congelaria essa chave de teste na
    # constante do módulo e vazaria para os testes seguintes.


def test_elo_agents_llm_aceita_chave_definida_depois_do_import(sem_chave_no_ambiente):
    """O caso de ponta a ponta: construir o cliente real depois que a chave foi
    definida em um processo que já tinha importado vertice antes."""
    from vertice import config
    importlib.reload(config)
    from vertice.agent.llm import EloAgentsLLM

    sem_chave_no_ambiente.setenv("ELOAGENTS_API_KEY", "sk-3e1fe11506bd4db6904e5cb9dcd482c3")
    cliente = EloAgentsLLM()  # não pode levantar RuntimeError
    assert cliente.cliente.api_key == "sk-3e1fe11506bd4db6904e5cb9dcd482c3"
    # Mesmo cuidado do teste anterior: nada de reload com a chave ainda setada.


def test_elo_agents_llm_ainda_recusa_chave_realmente_ausente(sem_chave_no_ambiente):
    from vertice.agent.llm import EloAgentsLLM
    with pytest.raises(RuntimeError, match="Chave de API ausente"):
        EloAgentsLLM()


def test_api_key_explicito_tem_prioridade_sobre_o_ambiente(sem_chave_no_ambiente):
    from vertice.agent.llm import EloAgentsLLM
    cliente = EloAgentsLLM(api_key="sk-explicita")
    assert cliente.cliente.api_key == "sk-explicita"


def test_cli_diagnostico_le_chave_definida_apos_importar_vertice(sem_chave_no_ambiente, capsys):
    """O mesmo bug existia em cli.py: _diagnostico() lia a constante congelada."""
    from vertice import config, cli
    importlib.reload(config)
    assert config.ELO_API_KEY == ""

    sem_chave_no_ambiente.setenv("ELOAGENTS_API_KEY", "sk-definida-depois")
    # A rede está bloqueada neste ambiente de teste: o diagnóstico vai falhar na
    # conexão, mas NÃO pode reportar "AUSENTE" — o que importa aqui é a leitura.
    cli._diagnostico()
    saida = capsys.readouterr().out
    assert "AUSENTE" not in saida
    assert "sk-defin" in saida  # cli.py trunca em 8 caracteres + reticências


def test_chave_gateway_nao_cai_de_volta_no_valor_congelado(monkeypatch):
    """Regressão de produção: chave_gateway() tinha `or ELO_API_KEY` como
    'rede de segurança'. Isso reintroduzia o próprio bug que a função existe
    para evitar — só na direção oposta.

    Cenário real: o usuário roda `export ELOAGENTS_API_KEY=...` no shell ANTES
    de `python -m pytest` (é a instrução do README). A primeira importação de
    vertice.config nesse processo já vê a chave e congela ELO_API_KEY com o
    valor real. Um teste que depois faz monkeypatch.delenv (simulando ausência
    de chave) esperava chave_gateway() == "", mas o fallback devolvia o valor
    congelado — a chave "removida" nunca desaparecia de verdade.
    """
    from vertice import config

    # Simula a ordem exata do shell dela: a chave já existe no ambiente quando
    # o módulo é importado pela primeira vez.
    monkeypatch.setenv("ELOAGENTS_API_KEY", "sk-3e1fe11506bd4db6904e5cb9dcd482c3")
    importlib.reload(config)
    assert config.ELO_API_KEY == "sk-3e1fe11506bd4db6904e5cb9dcd482c3", (
        "pré-condição: a constante congelada precisa ter capturado a chave real"
    )

    # Remove do ambiente DEPOIS do import — é o que monkeypatch.delenv faz.
    monkeypatch.delenv("ELOAGENTS_API_KEY", raising=False)
    assert config.chave_gateway() == "", (
        "chave_gateway() caiu de volta no valor congelado em vez de refletir "
        "a ausência real da variável — o fallback `or ELO_API_KEY` está de volta"
    )

    importlib.reload(config)  # não vaza o congelamento para outros testes
