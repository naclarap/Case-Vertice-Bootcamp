"""Configuração central do projeto Vértice Retail."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("VERTICE_DATA_DIR", PROJECT_ROOT / "data"))

ARQUIVOS = {
    "vendas": "vendas.csv",
    "clientes": "clientes.csv",
    "marketing": "marketing.csv",
    "estoque": "estoque.csv",
    "atendimento": "atendimento.csv",
}

# --- Gateway EloAgents (compatível com o formato OpenAI) ---------------------
ELO_BASE_URL = os.getenv("ELOAGENTS_BASE_URL", "https://chat.eloagents.click/api")

# ATENÇÃO: não use esta constante para decidir se a chave existe — ela é fixada
# uma única vez, no momento em que o módulo é importado, e nunca mais reflete o
# ambiente. É só um resquício informativo; a leitura de verdade é chave_gateway().
ELO_API_KEY = os.getenv("ELOAGENTS_API_KEY", "")


def chave_gateway() -> str:
    """Lê ELOAGENTS_API_KEY sempre no momento da chamada, não no import.

    Sem fallback para ELO_API_KEY de propósito. Uma versão anterior desta função
    tinha `os.getenv(...) or ELO_API_KEY`, pensada como rede de segurança — mas
    isso reintroduzia exatamente o bug que a função existe para evitar: se a
    chave esteve presente em QUALQUER momento anterior do processo (o caso comum
    no terminal, onde `export ELOAGENTS_API_KEY=...` roda antes de `python -m
    pytest`), remover a variável depois — um teste com monkeypatch.delenv, por
    exemplo — não tinha efeito, porque a função caía de volta no valor
    congelado. `os.getenv` sozinho já resolve o cenário original (notebook: a
    Parte 1 importa antes de a Parte 2 definir a chave), porque nesse caso a
    variável JÁ está no ambiente no momento em que chave_gateway() é chamada —
    o fallback nunca foi necessário, só nocivo.
    """
    return os.getenv("ELOAGENTS_API_KEY", "")


# Padrão: claude-sonnet-46 nos dois papéis. claude-haiku-45 é mais barato, mas em
# testes com o catálogo de 20 ferramentas errou repetidamente a seleção (chamou
# ferramenta errada, desistiu citando a ferramenta certa sem executá-la) — cada
# correção custa uma ida ao gateway, então o ganho de acerto do Sonnet compensa o
# custo maior por chamada. Troque via VERTICE_MODEL_STEP/VERTICE_MODEL_FINAL, ou
# --modelo/--modelo-sintese na CLI, se quiser voltar ao Haiku ou tentar Opus.
MODELO_INVESTIGACAO = os.getenv("VERTICE_MODEL_STEP", "claude-sonnet-46")
MODELO_SINTESE = os.getenv("VERTICE_MODEL_FINAL", "claude-sonnet-46")

# "texto" = ReAct via parsing de texto (padrão, funciona sem function calling
# nativo). "nativo" = usa o parâmetro tools= da API de chat completions.
MODO_FERRAMENTAS = os.getenv("VERTICE_TOOL_MODE", "texto")

MAX_ITERACOES = int(os.getenv("VERTICE_MAX_ITER", "8"))


def max_tokens_resposta() -> int | None:
    """Teto de tokens da resposta do modelo. Sem valor = sem teto.

    Fica DESLIGADO por padrão de propósito. Cortar por token corta no meio da
    frase, e a resposta final tem contrato de quatro seções: uma resposta
    truncada perde FORÇA DA EVIDÊNCIA e chega quebrada no painel. Quem quiser
    encurtar deve apertar o bloco CONCISÃO do system prompt, que faz o modelo
    escrever menos em vez de escrever cortado.

    Este teto existe como rede contra resposta disparada, não como estilo.
    Lido a cada chamada, nunca congelado no import (mesmo motivo de
    `chave_gateway()`).
    """
    bruto = os.getenv("VERTICE_MAX_TOKENS", "").strip()
    if not bruto:
        return None
    valor = int(bruto)
    if valor < 1:
        raise ValueError(f"VERTICE_MAX_TOKENS deve ser >= 1, recebido {bruto!r}")
    return valor


def max_mensagens_historico() -> int:
    """Quantas mensagens de conversas anteriores acompanham a pergunta atual.

    O histórico crescia sem limite: cada pergunta somava o par
    pergunta/resposta ao pedido seguinte, e em provedor com teto baixo de tokens
    a terceira ou quarta pergunta da sessão passava a falhar com 413 — a
    primeira funcionava, as seguintes não. 6 = três trocas, suficiente para
    "e no Marketplace?" continuar fazendo sentido.
    """
    return max(0, int(os.getenv("VERTICE_MAX_HIST", "6")))


def catalogo_compacto() -> bool:
    """Catálogo de ferramentas curto no system prompt (lido a cada chamada).

    O catálogo completo tem ~12,8 mil caracteres; provedores com teto baixo de
    tokens por requisição (camada gratuita da Groq, por exemplo) recusam com 413
    antes de o modelo responder. Ligue com VERTICE_CATALOGO_COMPACTO=1.
    """
    return os.getenv("VERTICE_CATALOGO_COMPACTO", "").lower() in ("1", "true", "yes")

# --- Constantes de negócio (ver PREMISSAS.md) --------------------------------
STATUS_RECEITA_VALIDA = "Aprovado"

# Teto de desconto recomendado ao comitê. Era 0,25 e passou a 0,20 para alinhar
# o motor à recomendação do caso: entregar um sistema cuja política padrão
# autoriza exatamente o que a apresentação pede para proibir é incoerência que
# a banca lê como falta de cuidado. 0,20 é o teto do caso-base (R$ 241.424,23
# por ano na base de decisão); acima disso, desconto é exceção.
LIMIAR_DESCONTO_ALTO = 0.20

CANAL_SOB_SUSPEITA = "Marketplace"

# --- Convenção de recorte (ver engine/recorte.py) ----------------------------
# Ano-calendário da base de decisão. O business case é anual; a base tem 13
# meses (jan/2023 a 26/jan/2024), então somar tudo e chamar de "por ano"
# superestima em 8,3%.
ANO_BASE = 2023

# Novembro fica fora do teto de desconto: é Black Friday (índice sazonal 1,95,
# quase o dobro da média) e roda sob orçamento de campanha aprovado, não sob a
# política de desconto corrente. É a única janela em que a base mostra
# associação entre desconto e volume, e essa associação não é separável do
# efeito da campanha.
MESES_FORA_DO_TETO = (11,)

# "decisao" = base sobre a qual o comitê decide (ANO_BASE, pedidos mantidos,
# MESES_FORA_DO_TETO fora). "diagnostico" = toda a base aprovada, nada excluído.
# O padrão é declarado em todo resultado, nunca aplicado em silêncio.
CONVENCAO_PADRAO = os.getenv("VERTICE_CONVENCAO", "decisao")

# Limiar de frete dos demais canais: abaixo dele a Vértice arca com o frete.
# Regra observada com 100,0% de aderência nos 6 canais fora do Marketplace.
LIMIAR_FRETE_GRATIS_REAIS = 250.0

# Denominador usado para COMUNICAR margem. A decomposição MECE só fecha sobre a
# receita bruta (identidade contábil); o comitê e a apresentação leem margem
# sobre receita líquida. As ferramentas devolvem as duas, sempre rotuladas.
DENOMINADOR_COMUNICACAO = "receita_liquida"

FAIXAS_DESCONTO = [
    ("0%", 0.0, 0.0001),
    ("0-10%", 0.0001, 0.10),
    ("10-20%", 0.10, 0.20),
    ("20-25%", 0.20, 0.25),
    ("25-30%", 0.25, 0.30),
    ("30%+", 0.30, 1.01),
]

# --- Alçadas de aprovação de desconto ----------------------------------------
# Governança, não dado: nenhuma coluna da base diz quem aprovou um desconto, e
# nenhuma diz quem PODERIA ter aprovado. As faixas abaixo são o padrão do
# PROJETO, ancorado no que já estava configurado aqui — LIMIAR_DESCONTO_ALTO
# (25%) é o ponto a partir do qual o desconto é tratado como exceção em todo o
# motor, então é ele que separa a última faixa. Trocar a régua da empresa não
# exige mexer em código: aponte VERTICE_ALCADAS_FILE para um JSON com a mesma
# forma (lista de {ate_pct, aprovador, exige_justificativa}).
#
# Toda ferramenta que usa esta tabela devolve a origem junto do resultado, para
# a resposta nunca apresentar régua de governança como se fosse apuração.
ALCADAS_PADRAO = [
    {"ate_pct": 10.0, "aprovador": "Analista comercial (automático no sistema)",
     "exige_justificativa": False},
    # Última faixa dentro da política: o teto recomendado ao comitê é 20%.
    {"ate_pct": LIMIAR_DESCONTO_ALTO * 100, "aprovador": "Gerente Comercial",
     "exige_justificativa": False},
    # Acima do teto já é EXCEÇÃO à política, e por isso exige justificativa.
    {"ate_pct": 25.0, "aprovador": "Diretor Comercial (exceção ao teto de 20%)",
     "exige_justificativa": True},
    {"ate_pct": 100.0, "aprovador": "CMO + CFO (exceção)", "exige_justificativa": True},
]


def alcadas() -> tuple[list[dict], str]:
    """(faixas de alçada, origem). Lidas do arquivo a CADA chamada, nunca no import."""
    caminho = os.getenv("VERTICE_ALCADAS_FILE", "")
    if caminho:
        import json
        p = Path(caminho)
        if p.is_file():
            dados = json.loads(p.read_text(encoding="utf-8"))
            faixas = dados.get("alcadas", dados) if isinstance(dados, dict) else dados
            return list(faixas), f"arquivo de alçadas ({p})"
    return [dict(f) for f in ALCADAS_PADRAO], (
        "padrão do projeto em config.ALCADAS_PADRAO — parâmetro de governança "
        "definido pela empresa, NÃO apurado dos dados")
