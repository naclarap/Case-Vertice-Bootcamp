"""Trace estruturado do raciocínio do agente.

Formato pensado para ser consumido por um painel visual (fora do escopo deste
projeto): lista ordenada de passos tipados, cada um com timestamp, duração e
carga útil serializável em JSON.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

TipoPasso = Literal["pergunta", "roteamento", "pensamento", "acao", "observacao",
                    "erro", "resposta_final"]

# De onde veio a consulta. O caso de uso do agente é gestor revisando política
# periodicamente, não vendedor pedindo aprovação em tempo real — sem registrar
# isso, o consumidor do trace (painel, auditoria) não consegue separar uma
# pergunta pontual de uma revisão agendada.
OrigemConsulta = Literal["ad_hoc", "revisao_periodica"]
ORIGENS_CONSULTA = ("ad_hoc", "revisao_periodica")


@dataclass
class Passo:
    indice: int
    tipo: TipoPasso
    conteudo: Any
    timestamp: float = field(default_factory=time.time)
    duracao_ms: float | None = None
    ferramenta: str | None = None
    parametros: dict | None = None
    iteracao: int | None = None
    # Estado explícito da execução (ver agent/router.py): sem ele, "a ferramenta
    # não retornou" cobria três casos diferentes — não chamada, erro, e recorte
    # vazio — e a auditoria não conseguia distinguir.
    status: str | None = None
    origem: str | None = None      # quem decidiu a chamada: roteador ou LLM


@dataclass
class Trace:
    """Registro auditável de uma investigação completa."""

    pergunta: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    modelo: str = ""
    modo_ferramentas: str = ""
    inicio: float = field(default_factory=time.time)
    fim: float | None = None
    passos: list[Passo] = field(default_factory=list)
    resposta_final: str | None = None
    ferramentas_usadas: list[str] = field(default_factory=list)
    origem_consulta: OrigemConsulta = "ad_hoc"
    # Decisão do roteador determinístico (agent/router.py), quando houve uma.
    roteamento: dict | None = None

    def add(self, tipo: TipoPasso, conteudo: Any, **kw) -> Passo:
        p = Passo(indice=len(self.passos), tipo=tipo, conteudo=conteudo, **kw)
        self.passos.append(p)
        if tipo == "acao" and p.ferramenta:
            self.ferramentas_usadas.append(p.ferramenta)
        return p

    def encerrar(self, resposta: str | None) -> None:
        self.resposta_final = resposta
        self.fim = time.time()

    @property
    def duracao_s(self) -> float:
        return round((self.fim or time.time()) - self.inicio, 2)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pergunta": self.pergunta,
            "modelo": self.modelo,
            "modo_ferramentas": self.modo_ferramentas,
            "origem_consulta": self.origem_consulta,
            "roteamento": self.roteamento,
            "duracao_s": self.duracao_s,
            "n_passos": len(self.passos),
            "ferramentas_usadas": self.ferramentas_usadas,
            "n_chamadas_ferramenta": len(self.ferramentas_usadas),
            "resposta_final": self.resposta_final,
            "passos": [asdict(p) for p in self.passos],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)

    def salvar(self, diretorio: str | Path = "traces") -> Path:
        d = Path(diretorio)
        d.mkdir(parents=True, exist_ok=True)
        caminho = d / f"trace_{self.id}.json"
        caminho.write_text(self.to_json(), encoding="utf-8")
        return caminho

    def resumo_terminal(self) -> str:
        ic = {"pergunta": "❓", "roteamento": "🧭", "pensamento": "🧠", "acao": "🔧",
              "observacao": "📊", "erro": "⚠️ ", "resposta_final": "✅"}
        linhas = [f"TRACE {self.id} · {len(self.passos)} passos · {self.duracao_s}s "
                  f"· {len(self.ferramentas_usadas)} chamadas de ferramenta"]
        for p in self.passos:
            if p.tipo == "acao":
                origem = f" [{p.origem}]" if p.origem else ""
                txt = f"{p.ferramenta}({json.dumps(p.parametros, ensure_ascii=False)}){origem}"
            else:
                txt = str(p.conteudo).replace("\n", " ")
            linhas.append(f"  {p.indice:>2} {ic.get(p.tipo,'·')} [{p.tipo}] {txt[:150]}")
        return "\n".join(linhas)
