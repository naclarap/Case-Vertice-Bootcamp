"""Cliente do gateway EloAgents (API compatível com OpenAI) + duplo LLM para teste.

O gateway expõe apenas os papéis `user` e `assistant` — não há papel dedicado a
resultado de ferramenta. Por isso o loop ReAct etiqueta explicitamente cada
mensagem (ver prompts.ROTULO_*), evitando que o modelo confunda resultado de
ferramenta com pergunta do usuário em conversas de múltiplos turnos.
"""
from __future__ import annotations

import os
from typing import Any, Protocol

from .. import config


class LLM(Protocol):
    def completar(self, mensagens: list[dict], modelo: str, tools: list[dict] | None = None) -> Any:
        ...


class EloAgentsLLM:
    """Cliente real. `pip install openai`; a API é OpenAI-compatível mesmo os
    modelos por trás sendo Claude via Amazon Bedrock."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 temperatura: float = 0.0, timeout: float = 120.0):
        from openai import OpenAI  # import tardio: só é exigido no modo real

        key = api_key or config.chave_gateway()
        if not key:
            raise RuntimeError(
                "Chave de API ausente. Defina ELOAGENTS_API_KEY no ambiente "
                "(ex.: export ELOAGENTS_API_KEY=sk-...) ou use --mock para rodar offline."
            )
        self.cliente = OpenAI(api_key=key, base_url=base_url or config.ELO_BASE_URL,
                              timeout=timeout)
        self.temperatura = temperatura

    def completar(self, mensagens: list[dict], modelo: str,
                  tools: list[dict] | None = None) -> Any:
        kwargs: dict[str, Any] = {
            "model": modelo,
            "messages": mensagens,
            "temperature": self.temperatura,
        }
        teto = config.max_tokens_resposta()
        if teto:
            kwargs["max_tokens"] = teto
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = self.cliente.chat.completions.create(**kwargs)
        return resp.choices[0].message

    def listar_modelos(self) -> list[str]:
        return [m.id for m in self.cliente.models.list().data]


class MockLLM:
    """LLM determinístico para testes offline do loop ReAct.

    Não tenta imitar raciocínio: percorre um roteiro fixo de respostas em texto
    no mesmo formato que o modelo real deve produzir. Serve para validar o
    parser, o despacho de ferramentas, o trace e o formato de saída sem rede.
    """

    def __init__(self, roteiro: list[str] | None = None):
        self.roteiro = list(roteiro or [])
        self.chamadas: list[list[dict]] = []

    def completar(self, mensagens: list[dict], modelo: str,
                  tools: list[dict] | None = None) -> Any:
        self.chamadas.append(mensagens)
        texto = self.roteiro.pop(0) if self.roteiro else (
            "FATO: sem roteiro restante.\nINFERÊNCIA: -\nRECOMENDAÇÃO: -\n"
            "FORÇA DA EVIDÊNCIA: FRACA"
        )
        return type("Msg", (), {"content": texto, "tool_calls": None})()


def construir_llm(mock: bool = False, roteiro: list[str] | None = None) -> LLM:
    return MockLLM(roteiro) if mock else EloAgentsLLM()
