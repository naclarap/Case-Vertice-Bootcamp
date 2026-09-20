import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from vertice.data import carregar_vendas


# Variáveis que mudam o comportamento do agente e do motor. Um `export` deixado
# no terminal — VERTICE_TOOL_MODE=nativo depois de depurar um provedor, por
# exemplo — fazia a suíte passar aqui e falhar na máquina de quem exportou, com
# um erro que não tem nada a ver com o que a pessoa mexeu. Teste que lê ambiente
# vivo não é teste: cada um declara o que precisa, via monkeypatch.
_VARIAVEIS_DO_AMBIENTE = (
    "VERTICE_TOOL_MODE", "VERTICE_MAX_ITER", "VERTICE_MAX_HIST",
    "VERTICE_CATALOGO_COMPACTO", "VERTICE_MODEL_STEP", "VERTICE_MODEL_FINAL",
    "VERTICE_MAX_TOKENS",
    "VERTICE_DATA_DIR", "VERTICE_ALCADAS_FILE",
)


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch, tmp_path):
    for nome in _VARIAVEIS_DO_AMBIENTE:
        monkeypatch.delenv(nome, raising=False)
    # A política é estado em arquivo: sem isto, a suíte lê (e grava) o
    # politicas.json de verdade de quem está rodando, e o resultado do teste
    # passa a depender do que foi cadastrado na interface.
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "politicas.json"))


@pytest.fixture
def fluxo_completo(monkeypatch):
    """Liga as etapas que estão desligadas no produto.

    Aprovação, ativação e monitoramento funcionam: estão desligadas por decisão
    de produto (aprovar de verdade depende de identidade autenticada), não por
    estarem incompletas. Os testes do ciclo inteiro ligam a trava para esse
    caminho continuar coberto enquanto ele não é oferecido na tela — sem isso,
    religar a etapa um dia seria religar código sem teste nenhum.
    """
    from vertice import politica
    monkeypatch.setattr(politica, "ETAPAS_HABILITADAS", politica.ESTADOS)
    return politica.ESTADOS


@pytest.fixture(scope="session")
def vendas():
    return carregar_vendas()


@pytest.fixture(scope="session")
def vendas_todas():
    return carregar_vendas(apenas_aprovados=False)
