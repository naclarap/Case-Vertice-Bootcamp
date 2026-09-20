"""Política de desconto vigente — estado persistido, com dono e histórico.

O material de governança promete "regras versionadas: política, regra de frete
e motivos têm dono, vigência e histórico". Isso exige estado real, não
simulação stateless a cada chamada: aqui cada mudança vira uma entrada nova no
arquivo, e nada é sobrescrito — `politica_vigente()` lê a mais recente que se
aplica ao recorte, e o que veio antes continua consultável em `historico()`.

Armazenamento: um JSON local (protótipo). O caminho é lido do ambiente a CADA
chamada, nunca congelado no import — mesmo motivo de `config.chave_gateway()`:
constante fixada no import quebra em processo de vida longa e em teste.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

ARQUIVO_PADRAO = "politicas.json"


def caminho_arquivo() -> Path:
    return Path(os.getenv("VERTICE_POLITICAS_FILE", ARQUIVO_PADRAO))


def _carregar() -> list[dict]:
    p = caminho_arquivo()
    if not p.is_file():
        return []
    try:
        dados = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"arquivo de políticas corrompido ({p}): {e}") from e
    return dados.get("politicas", []) if isinstance(dados, dict) else list(dados)


def _documento() -> dict:
    """O arquivo inteiro. Três coleções dividem o mesmo JSON: `politicas`,
    `propostas` e `experimentos`."""
    p = caminho_arquivo()
    if not p.is_file():
        return {}
    try:
        dados = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"arquivo de políticas corrompido ({p}): {e}") from e
    if isinstance(dados, dict):
        return dados
    return {"politicas": list(dados)}          # formato antigo: lista solta


def _gravar_chave(chave: str, valor) -> None:
    """Escreve UMA coleção preservando as outras.

    Reler antes de escrever não é zelo excessivo: aprovar uma proposta chama
    `definir_politica()`, que grava políticas. Sem reler, essa gravação apagaria
    `propostas` e `experimentos` — o fluxo de aprovação destruiria justamente o
    registro de quem aprovou e o teste em andamento. Toda escrita neste arquivo
    passa por aqui, por isso.
    """
    p = caminho_arquivo()
    dados = _documento()
    dados[chave] = valor
    dados.setdefault("politicas", [])
    if p.parent and str(p.parent) not in ("", "."):
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(dados, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def _gravar(entradas: list[dict]) -> None:
    _gravar_chave("politicas", entradas)


def _norm_pct(valor) -> float:
    """Aceita 25 e 0.25 como o mesmo teto, igual aos simuladores já fazem."""
    v = float(valor)
    if v < 0:
        raise ValueError(f"teto_pct não pode ser negativo: {valor}")
    pct = v * 100 if v <= 1 else v
    if pct > 100:
        raise ValueError(f"teto_pct acima de 100%: {valor}")
    return round(pct, 4)


def definir_politica(canal: str | None, categoria: str | None, teto_pct,
                     responsavel: str, vigencia: str | None = None,
                     trace: Any = None) -> dict:
    """Registra uma NOVA política. Não apaga nem edita as anteriores.

    canal/categoria == None significa "vale para todos" naquele eixo.
    `trace`: qualquer objeto com .add(tipo, conteudo, **kw) — o Trace do agente
    serve. Recebido por duck-typing para este módulo não importar o agente.
    """
    if not responsavel or not str(responsavel).strip():
        raise ValueError("toda política precisa de um responsável (dono da regra)")
    entrada = {
        "canal": canal,
        "categoria": categoria,
        "teto_pct": _norm_pct(teto_pct),
        "responsavel": str(responsavel).strip(),
        "definida_em": time.time(),
        "vigencia": vigencia or time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    entradas = _carregar()
    entradas.append(entrada)
    _gravar(entradas)

    if trace is not None and hasattr(trace, "add"):
        trace.add("politica_definida", {
            "canal": canal, "categoria": categoria,
            "teto_pct": entrada["teto_pct"],
            "responsavel": entrada["responsavel"],
            "vigencia": entrada["vigencia"],
        })
    return entrada


def _aplica(entrada: dict, canal: str | None, categoria: str | None) -> bool:
    """Uma política com canal=None vale para qualquer canal; com canal='X' só
    vale se a consulta for sobre 'X'. Idem categoria."""
    return ((entrada.get("canal") is None or entrada.get("canal") == canal)
            and (entrada.get("categoria") is None or entrada.get("categoria") == categoria))


def _especificidade(entrada: dict) -> int:
    return (entrada.get("canal") is not None) + (entrada.get("categoria") is not None)


def politica_vigente(canal: str | None = None,
                     categoria: str | None = None) -> dict | None:
    """Política ativa para o recorte pedido, ou None se não há nenhuma.

    Entre as que se aplicam, vence a mais ESPECÍFICA (canal+categoria antes de
    só canal, antes da global); empate na especificidade, vence a mais RECENTE.
    """
    candidatas = [e for e in _carregar() if _aplica(e, canal, categoria)]
    if not candidatas:
        return None
    return max(candidatas, key=lambda e: (_especificidade(e), e.get("definida_em", 0)))


def historico(canal: str | None = None, categoria: str | None = None) -> list[dict]:
    """Todas as políticas já definidas para o recorte, da mais recente para a
    mais antiga. Nada é apagado — é isso que sustenta "histórico" na promessa
    de governança."""
    entradas = _carregar()
    if canal is not None or categoria is not None:
        entradas = [e for e in entradas if _aplica(e, canal, categoria)]
    return sorted(entradas, key=lambda e: e.get("definida_em", 0), reverse=True)


def teto_vigente_pct(canal: str | None = None,
                     categoria: str | None = None) -> float | None:
    """Só o número do teto vigente, para os simuladores usarem como default."""
    p = politica_vigente(canal, categoria)
    return p["teto_pct"] if p else None


# ============================================================================
# Ciclo de vida da proposta
# ----------------------------------------------------------------------------
# Uma política não nasce valendo: ela é proposta, simulada, aprovada e só então
# aplicada. Antes, a tela tinha um botão "Aplicar" que pulava esses passos —
# o que é um problema de governança, não de interface: sem estado persistido
# não há como responder "quem aprovou isto, e quando".
#
# As propostas moram no MESMO arquivo das políticas, sob outra chave. É de
# propósito que elas não se misturem: `politica_vigente()` continua lendo só
# `politicas`, então nada do que o motor e o agente já faziam muda por causa
# de uma proposta em rascunho. A proposta só vira política de verdade no passo
# de aprovação, que chama `definir_politica()` — o mesmo caminho de sempre.
# ============================================================================

ESTADOS = ("rascunho", "simulacao", "aprovacao", "ativa", "monitoramento")

# De onde se pode ir para onde. O fluxo é linear de propósito: não existe
# aprovar sem ter simulado, nem ativar sem ter aprovado.
TRANSICOES = {
    "rascunho": ("simulacao",),
    "simulacao": ("aprovacao",),
    "aprovacao": ("ativa",),
    "ativa": ("monitoramento",),
    "monitoramento": (),
}

# A transição que exige OUTRA pessoa. Aprovar é o único passo em que o
# sistema deixa de registrar e passa a controlar: proponente e aprovador não
# podem ser a mesma pessoa.
#
# Isto NÃO é autenticação — o nome continua sendo declarado, e ninguém prova
# ser quem diz. É segregação de funções, o controle que um comitê cobra: sem
# ele, o fluxo de cinco passos vira cinco cliques da mesma pessoa em trinta
# segundos, e a trilha de auditoria registra isso sem poder impedir. A
# identidade real vem do SSO da empresa na implantação, e aí este campo some
# da tela em vez de ser digitado.
TRANSICAO_QUE_EXIGE_OUTRA_PESSOA = "ativa"


def _mesma_pessoa(a: str, b: str) -> bool:
    """Compara nomes ignorando caixa e espaço de sobra.

    Comparação frouxa de propósito: "pablo" e "Pablo " são a mesma pessoa
    tentando aprovar a própria proposta, e o controle existe para pegar
    justamente o caminho de menor esforço.
    """
    return str(a or "").strip().casefold() == str(b or "").strip().casefold()


def quem_propos(proposta: dict) -> str:
    """Quem criou a proposta — o primeiro registro do histórico, não o campo
    `responsavel`, que é o dono da REGRA e pode ser outra pessoa."""
    historico = proposta.get("historico") or []
    if historico:
        return historico[0].get("quem") or proposta.get("responsavel", "")
    return proposta.get("responsavel", "")


# Até onde o fluxo vai HOJE.
#
# Aprovação, ativação e monitoramento existem no código, têm rota, tela e
# teste — e estão DESLIGADOS no produto. Aprovar uma política de verdade
# depende de identidade real (o nome aqui é declarado, não autenticado) e de
# um mandato que ainda não foi dado; ativar sem isso seria o sistema mudando
# o teto praticado com base em quem digitou um nome numa caixa de texto.
#
# Ligar é trocar esta tupla por ESTADOS. Nada mais precisa mudar: a tela lê
# daqui, a API lê daqui, e os testes do ciclo completo ligam via monkeypatch —
# então o caminho continua coberto enquanto está desligado.
ETAPAS_HABILITADAS = ("rascunho", "simulacao")


def etapas_habilitadas() -> tuple[str, ...]:
    """Lida por função, não pela constante: quem importa o valor no topo do
    módulo congela a trava e deixa de enxergar quando ela muda."""
    return ETAPAS_HABILITADAS


def etapas_futuras() -> tuple[str, ...]:
    """As que a tela mostra como implementação futura."""
    return tuple(e for e in ESTADOS if e not in ETAPAS_HABILITADAS)


ROTULOS_ESTADO = {
    "rascunho": "Rascunho",
    "simulacao": "Simulação",
    "aprovacao": "Aprovação",
    "ativa": "Ativa",
    "monitoramento": "Monitoramento",
}


def _carregar_propostas() -> list[dict]:
    p = caminho_arquivo()
    if not p.is_file():
        return []
    try:
        dados = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"arquivo de políticas corrompido ({p}): {e}") from e
    return dados.get("propostas", []) if isinstance(dados, dict) else []


def _gravar_propostas(propostas: list[dict]) -> None:
    _gravar_chave("propostas", propostas)


def _novo_id() -> str:
    return "prop_" + uuid.uuid4().hex[:10]


def _marca(estado: str, quem: str, nota: str | None = None) -> dict:
    """Quem e quando, em toda transição — é o que a governança promete."""
    return {
        "estado": estado,
        "quem": str(quem).strip(),
        "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
        "quando_ts": time.time(),
        "nota": nota,
    }


def criar_proposta(teto_pct, responsavel: str, canal: str | None = None,
                   categoria: str | None = None, vigencia: str | None = None,
                   nota: str | None = None) -> dict:
    """Nasce em RASCUNHO. Nada do que está aqui afeta o teto vigente."""
    if not responsavel or not str(responsavel).strip():
        raise ValueError("toda proposta precisa de um responsável (dono da regra)")
    proposta = {
        "id": _novo_id(),
        "canal": canal,
        "categoria": categoria,
        "teto_pct": _norm_pct(teto_pct),
        "responsavel": str(responsavel).strip(),
        "vigencia": vigencia,
        "estado": "rascunho",
        "criada_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "criada_em_ts": time.time(),
        "historico": [_marca("rascunho", responsavel, nota)],
        "politica_aplicada": None,
    }
    propostas = _carregar_propostas()
    propostas.append(proposta)
    _gravar_propostas(propostas)
    return proposta


def obter_proposta(proposta_id: str) -> dict | None:
    return next((p for p in _carregar_propostas() if p.get("id") == proposta_id), None)


def propostas(incluir_encerradas: bool = True) -> list[dict]:
    """Da mais recente para a mais antiga."""
    todas = sorted(_carregar_propostas(), key=lambda p: p.get("criada_em_ts", 0),
                   reverse=True)
    return todas if incluir_encerradas else [p for p in todas if p["estado"] != "monitoramento"]


def aguardando_aprovacao() -> list[dict]:
    """A fila: propostas paradas esperando a decisão de outra pessoa.

    Existe porque "aprovação" sem fila é um estado que só quem abriu a proposta
    enxerga. Cada item já vem com quem propôs, que é de quem o aprovador NÃO
    pode ser.
    """
    fila = [p for p in _carregar_propostas() if p.get("estado") == "aprovacao"]
    fila.sort(key=lambda p: p.get("criada_em_ts", 0), reverse=True)
    return [{**p, "proposta_por": quem_propos(p)} for p in fila]


def avancar_estado(proposta_id: str, destino: str, quem: str,
                   nota: str | None = None) -> dict:
    """Move a proposta um passo adiante, guardando quem e quando.

    Recusa salto de etapa: o fluxo existe para que aprovar seja uma decisão
    registrada, e não um efeito colateral de clicar em "aplicar".
    """
    if destino not in ESTADOS:
        raise ValueError(f"estado inválido: {destino!r}. Use um de {list(ESTADOS)}")
    if not quem or not str(quem).strip():
        raise ValueError("toda transição precisa de quem a fez")

    todas = _carregar_propostas()
    idx = next((i for i, p in enumerate(todas) if p.get("id") == proposta_id), None)
    if idx is None:
        raise ValueError(f"proposta {proposta_id!r} não encontrada")

    proposta = todas[idx]
    atual = proposta.get("estado", "rascunho")
    if destino not in TRANSICOES.get(atual, ()):
        permitido = ", ".join(TRANSICOES.get(atual, ())) or "nenhum (estado final)"
        raise ValueError(
            f"transição inválida: de '{ROTULOS_ESTADO.get(atual, atual)}' só se vai "
            f"para {permitido}, não para '{ROTULOS_ESTADO.get(destino, destino)}'")

    if destino not in ETAPAS_HABILITADAS:
        ate = ROTULOS_ESTADO.get(ETAPAS_HABILITADAS[-1], ETAPAS_HABILITADAS[-1])
        raise ValueError(
            f"'{ROTULOS_ESTADO.get(destino, destino)}' ainda não está disponível: "
            f"o fluxo vai até '{ate}'. Aprovar e aplicar uma política depende de "
            f"identidade autenticada, que este protótipo não tem — implementação "
            f"futura.")

    # Segregação de funções: aprovar é decisão de outra pessoa.
    autor = quem_propos(proposta)
    if destino == TRANSICAO_QUE_EXIGE_OUTRA_PESSOA and _mesma_pessoa(quem, autor):
        raise ValueError(
            f"{autor} propôs esta política e não pode aprová-la. A aprovação é de "
            f"outra pessoa — é o que separa uma decisão de comitê de um clique a mais.")

    proposta["estado"] = destino
    proposta.setdefault("historico", []).append(_marca(destino, quem, nota))

    # Aprovar é o que torna a política real: só aqui ela entra no arquivo de
    # políticas vigentes, pelo mesmo `definir_politica()` de sempre.
    if destino == "ativa":
        _gravar_propostas(todas)          # grava o estado antes de mexer nas políticas
        entrada = definir_politica(
            canal=proposta.get("canal"), categoria=proposta.get("categoria"),
            teto_pct=proposta["teto_pct"], responsavel=quem,
            vigencia=proposta.get("vigencia"),
        )
        todas = _carregar_propostas()
        proposta = next(p for p in todas if p["id"] == proposta_id)
        proposta["politica_aplicada"] = {
            "vigencia": entrada["vigencia"], "teto_pct": entrada["teto_pct"],
            "responsavel": entrada["responsavel"],
        }

    _gravar_propostas(todas)
    return proposta


def proposta_em_teste() -> dict | None:
    """A proposta que o Monitoramento observa: ativa ou em monitoramento.

    Devolve None quando não há nenhuma — que é o caso enquanto ninguém
    aprovou nada. A tela de Monitoramento depende disso para dizer "aguardando
    início do teste" em vez de inventar um resultado.
    """
    candidatas = [p for p in _carregar_propostas()
                  if p.get("estado") in ("ativa", "monitoramento")]
    if not candidatas:
        return None
    return max(candidatas, key=lambda p: p.get("criada_em_ts", 0))
