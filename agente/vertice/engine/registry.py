"""Registro de ferramentas do motor determinístico.

Uma única fonte de verdade: cada ferramenta é registrada com nome, descrição e
esquema de parâmetros. O mesmo registro alimenta (a) o prompt textual do ReAct,
(b) o esquema `tools=` nativo da API OpenAI e (c) o despacho da execução.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict[str, str] = field(default_factory=dict)
    obrigatorios: list[str] = field(default_factory=list)
    fn: Callable[..., Any] = None
    # Parâmetros que o EXEMPLO de chamada sempre mostra, mesmo não sendo
    # exigidos no despacho. Existe porque os simuladores passaram a aceitar a
    # política vigente como padrão de teto_pct/desconto_pct: o parâmetro deixou
    # de ser obrigatório, mas continua sendo o que o modelo precisa preencher
    # quando não há política — e foi justamente a ausência dele no exemplo que
    # fez, em produção, o modelo repetir `PARÂMETROS: {}` duas vezes seguidas.
    principais: list[str] = field(default_factory=list)

    @property
    def destacados(self) -> list[str]:
        """O que o exemplo de chamada deve exibir preenchido."""
        return self.principais or self.obrigatorios

    def executar(self, **kwargs) -> Any:
        aceitos = set(inspect.signature(self.fn).parameters)
        desconhecidos = set(kwargs) - aceitos
        if desconhecidos:
            raise TypeError(
                f"Parâmetro(s) inválido(s) para '{self.nome}': {sorted(desconhecidos)}. "
                f"Aceitos: {sorted(aceitos)}"
            )
        faltando = [p for p in self.obrigatorios if p not in kwargs]
        if faltando:
            raise TypeError(f"Parâmetro(s) obrigatório(s) ausente(s) em '{self.nome}': {faltando}")
        return self.fn(**kwargs)

    def schema_openai(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.nome,
                "description": self.descricao,
                "parameters": {
                    "type": "object",
                    "properties": {
                        k: {"type": "string", "description": v}
                        for k, v in self.parametros.items()
                    },
                    "required": self.obrigatorios,
                },
            },
        }


REGISTRO: dict[str, Ferramenta] = {}


def ferramenta(nome: str, descricao: str, parametros: dict[str, str] | None = None,
               obrigatorios: list[str] | None = None,
               principais: list[str] | None = None):
    """Decorator que registra uma função do motor como ferramenta do agente."""
    def _wrap(fn):
        REGISTRO[nome] = Ferramenta(
            nome=nome,
            descricao=descricao.strip(),
            parametros=parametros or {},
            obrigatorios=obrigatorios or [],
            principais=principais or [],
            fn=fn,
        )
        return fn
    return _wrap


def _hash_da_base() -> str:
    """SHA-256 (12 primeiros caracteres) de vendas.csv, calculado uma vez.

    Serve para provar que dois resultados saíram do MESMO arquivo. Se a base for
    trocada sem aviso, o hash muda e a divergência fica visível em vez de virar
    discussão sobre quem calculou errado.
    """
    global _HASH_BASE
    if _HASH_BASE is None:
        import hashlib

        from .. import config
        caminho = config.DATA_DIR / config.ARQUIVOS["vendas"]
        try:
            _HASH_BASE = hashlib.sha256(caminho.read_bytes()).hexdigest()[:12]
        except OSError:
            _HASH_BASE = "indisponivel"
    return _HASH_BASE


_HASH_BASE: str | None = None


def _marca(resultado: dict) -> str:
    """● fato calculado · ◐ estimativa com premissa · ○ direção sem valor.

    A regra é objetiva e lida do próprio retorno, não anotada à mão: resultado
    que declara `premissa` depende de uma escolha e é estimativa; resultado de
    cobertura de dados é direção sem valor; o resto é fato calculado da base.
    Anotar à mão daria margem para a marca discordar do conteúdo.
    """
    def _e_premissa(chave: object) -> bool:
        # Só o campo `premissa` (ou `premissa_algo`) marca estimativa. NÃO vale
        # `premissas_aplicadas`, que margem_consolidada devolve para declarar o
        # tratamento da carga: dizer quais linhas foram filtradas é transparência
        # sobre um fato, não uma escolha que muda o número.
        return isinstance(chave, str) and (
            chave == "premissa" or chave.startswith("premissa_"))

    if "veredito" in resultado or "cobertura" in resultado:
        return "○"
    if any(_e_premissa(k) for k in resultado):
        return "◐"
    if any(isinstance(v, dict) and any(_e_premissa(k2) for k2 in v)
           for v in resultado.values()):
        return "◐"
    return "●"


def executar(nome: str, parametros: dict | None = None) -> Any:
    if nome not in REGISTRO:
        raise KeyError(
            f"Ferramenta '{nome}' não existe. Disponíveis: {sorted(REGISTRO)}"
        )
    resultado = REGISTRO[nome].executar(**(parametros or {}))
    # Procedência anexada a TODO resultado: qual ferramenta, sobre qual arquivo,
    # com que grau de certeza. É o que permite responder "de onde veio este
    # número?" sem reabrir o código.
    if isinstance(resultado, dict):
        resultado.setdefault("ferramenta", nome)
        resultado.setdefault("marca", _marca(resultado))
        resultado.setdefault("hash_base", _hash_da_base())
    return resultado


def catalogo_texto(compacto: bool = False) -> str:
    """Descrição das ferramentas em linguagem natural, para o system prompt.

    `compacto=True` emite só a primeira frase da descrição e os nomes dos
    parâmetros. Existe porque o catálogo completo tem ~12,8 mil caracteres e
    provedores com teto baixo de tokens por requisição (ex.: camada gratuita da
    Groq) devolvem 413 antes de o modelo responder. O padrão continua completo:
    a versão curta perde nuance (premissas, avisos) e só deve ser usada quando o
    provedor exige.
    """
    linhas = []
    for f in REGISTRO.values():
        if compacto:
            # As descrições são escritas em várias linhas: junta tudo numa só
            # ANTES de cortar a frase, senão o corte cai no meio ("ex: order_id.")
            inteiro = " ".join(f.descricao.split())
            primeira = inteiro.split(". ")[0].strip().rstrip(".")
            params = ", ".join(
                f"{k}{'*' if k in f.destacados else ''}" for k in f.parametros) or "—"
            linhas.append(f"- {f.nome}({params}): {primeira}.")
            continue
        params = ", ".join(
            f"{k}{'*' if k in f.destacados else ''} ({v})" for k, v in f.parametros.items()
        ) or "sem parâmetros"
        linhas.append(f"- {f.nome}\n    o que faz: {f.descricao}\n    parâmetros: {params}")
    return "\n".join(linhas)


def schemas_openai() -> list[dict]:
    return [f.schema_openai() for f in REGISTRO.values()]
