"""Agente ReAct de investigação de margem. Nenhum cálculo acontece aqui."""
from .react import AgenteMargem, validar_formato_final  # noqa: F401
from .trace import Trace  # noqa: F401

__all__ = ["AgenteMargem", "validar_formato_final", "Trace"]
