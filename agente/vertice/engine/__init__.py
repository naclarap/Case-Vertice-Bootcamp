"""Motor determinístico. Importar este pacote popula o registro de ferramentas."""
from . import (auditoria, cobertura, discount, extras, freight, governanca,  # noqa: F401
               kpis, margin, pos_pedido, seasonality, stats)
from .registry import REGISTRO, catalogo_texto, executar, schemas_openai  # noqa: F401

__all__ = ["REGISTRO", "executar", "catalogo_texto", "schemas_openai"]
