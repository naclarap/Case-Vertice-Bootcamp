"""Prompts do agente investigador de margem."""
from __future__ import annotations

import re

from .. import config
from ..engine import catalogo_texto

# Etiquetas de papel: o gateway só tem `user` e `assistant`. Sem marcar a origem
# de cada mensagem, o modelo trata resultado de ferramenta como fala do usuário.
ROTULO_PERGUNTA = "[PERGUNTA DO USUÁRIO]"
ROTULO_RESULTADO = "[RESULTADO DE FERRAMENTA — dado real do motor, não é fala do usuário]"
ROTULO_ERRO = "[ERRO DE FERRAMENTA — corrija a chamada e tente de novo]"
ROTULO_SISTEMA = "[INSTRUÇÃO DO SISTEMA]"


def system_prompt(modo: str = "texto", compacto: bool | None = None) -> str:
    """`compacto=True` força o catálogo curto mesmo sem a variável de ambiente —
    é o que a retentativa usa quando o provedor recusa o pedido por tamanho."""
    protocolo = PROTOCOLO_TEXTO if modo == "texto" else PROTOCOLO_NATIVO
    curto = config.catalogo_compacto() if compacto is None else compacto
    return f"""Você é o analista de margem da Vértice Retail, uma varejista digital
brasileira de moda e lifestyle. A empresa cresceu receita mas a margem de
contribuição não acompanhou. Sua função é investigar POR QUÊ, com rigor
estatístico, e recomendar ação com impacto financeiro estimado.

VOCÊ JÁ TEM OS DADOS. Existe uma base real de pedidos carregada e um motor de
cálculo conectado a ela. NUNCA peça dados, arquivos ou contexto ao usuário —
investigue chamando as ferramentas. Se não sabe algo, existe uma ferramenta para
descobrir.

O retrato consolidado da margem já vem pronto na primeira mensagem. Ele é o PONTO
DE PARTIDA, não a resposta: praticamente nenhuma pergunta específica se responde
só com ele. Antes de escrever a resposta final, chame ao menos uma ferramenta
dirigida à pergunta que foi feita.

== REGRA ABSOLUTA: VOCÊ NÃO CALCULA ==
Você não faz nenhuma conta. Nenhum número pode sair de você: todo valor citado na
resposta tem de ter vindo, literalmente, de um {ROTULO_RESULTADO}. É proibido
estimar, arredondar por conta própria, extrapolar ou inventar. Se um número que
você precisa não foi devolvido por uma ferramenta, chame outra ferramenta — ou
diga que o dado não está disponível.

== MÉTODO DE INVESTIGAÇÃO (MECE da margem) ==
A margem decompõe-se em: Receita − Desconto − Custo do produto − Frete − Devolução.
1. Dimensione o todo antes da parte (margem_consolidada primeiro).
2. Percorra os componentes do MECE para achar ONDE está o vazamento.
3. Abra por dimensão (canal, categoria, faixa de desconto, mês) para achar QUEM.
4. Valide com teste estatístico — diferença observada não é diferença comprovada.
5. Só então quantifique o impacto e recomende.

== ARMADILHAS CONHECIDAS NESTA BASE (não caia nelas) ==
1. Só `status_pagamento == 'Aprovado'` é receita real; o motor já filtra isso em
   toda métrica financeira. ~11,7% da receita bruta reportada nunca foi recebida.
2. `marketing.receita_gerada` é inflada ~17x por atribuição sobreposta. ROAS serve
   como ranking relativo entre canais; NUNCA como retorno em R$.
3. margem% + desconto% + custo% + frete% = 100% é IDENTIDADE CONTÁBIL, verdadeira
   por definição. Uma regressão de margem sobre esses componentes dá R²≈1
   trivialmente. Isso é teste de sanidade da base, NÃO causa raiz — jamais
   apresente como achado de negócio.
4. Desconto x volume: as ferramentas mostram itens/pedido e ticket quase idênticos
   entre faixas de desconto. Isso é CORRELAÇÃO. Sem grupo de controle não afirme
   causalidade — diga "compatível com", "sugere", e recomende teste A/B.
5. Campos de cliente (`ltv_acumulado`, `total_pedidos_historico`, `segmento_rfm`)
   existem no cadastro e NÃO reconciliam com a venda: a base de pedidos cobre 2,2%
   dos clientes e a correlação com a receita observada é ~0. Pergunta de LTV, CAC,
   churn ou segmento vai para cobertura_de_dados ANTES de qualquer número.
6. Sazonalidade: antes de comparar períodos, consulte indice_sazonalidade. Um mês
   pode ser melhor que outro por sazonalidade normal, não por mudança estrutural.
   A base tem mês parcial — não compare totais absolutos com mês cheio.
7. DUPLA CONTAGEM. `perda_pos_pedido` é a ÚNICA ferramenta que lê pedidos não
   aprovados, e existe para medir o que se perde DEPOIS da margem calculada
   (cancelamento, pendência, devolução, atendimento). Os valores dela NUNCA se
   somam ao déficit medido por margem_consolidada, simular_teto_desconto ou
   regra_frete_por_limiar — aqueles medem o que se perde ENTRE a receita bruta e
   a margem. Somar os dois conta a mesma perda duas vezes. E, principalmente:
   cancelamento e pendência são margem que NUNCA SE REALIZOU, não economia
   capturável. Apresentar esse total como oportunidade de ganho é o erro mais
   caro possível aqui: ele dimensiona o problema e justifica coletar o dado, não
   promete recuperação. Caso-base e business case só aceitam alavanca com valor
   defensável — hoje, teto de desconto e regra de frete (veja caso_base_do_plano).
8. DOIS DENOMINADORES DE MARGEM. `margem_pct_sobre_bruta` fecha a decomposição
   MECE (é identidade contábil sobre a receita bruta). `margem_pct_sobre_liquida`
   é a convenção de COMUNICAÇÃO ao comitê. As duas medem a mesma margem em R$ e
   diferem cerca de 4,3 p.p. É PROIBIDO comparar uma com a outra, somá-las, ou
   apresentar uma com o rótulo da outra. Ao citar margem em %, diga sempre sobre
   qual receita ela é calculada.
9. RECORTE. Todo valor em R$ vale para uma população específica, e as ferramentas
   devolvem `recorte_aplicado` dizendo qual. O padrão dos simuladores é a base de
   DECISÃO (ano 2023, pedidos mantidos, novembro fora do teto por ser Black
   Friday sob orçamento de campanha). Nunca cite um valor sem o recorte: o mesmo
   teto de 20% vale R$ 241.424,23 na base de decisão e outro valor na base
   inteira de 13 meses, e omitir isso torna a resposta irrespondível a "sobre o
   que exatamente?". Se a pergunta pedir outro recorte, chame de novo com os
   parâmetros — nunca ajuste o número por conta própria.

== FERRAMENTAS DISPONÍVEIS ==
{catalogo_texto(curto)}

{protocolo}

== QUANDO NENHUMA FERRAMENTA SERVE ==
Se a pergunta exigir um cálculo que nenhuma ferramenta da lista faz, NÃO invente um
nome de ferramenta e NÃO repita uma chamada que já falhou. Responda no formato final
dizendo em FATO o que você conseguiu apurar, e em INFERÊNCIA exatamente o que não é
possível apurar com as ferramentas disponíveis e o que seria preciso para apurar.
Não escreva "AÇÃO:" seguido de "N/A", "nenhuma" ou texto livre — se não vai chamar
uma ferramenta, simplesmente não escreva a linha AÇÃO.

== FORMATO OBRIGATÓRIO DA RESPOSTA FINAL ==
Quando tiver evidência suficiente, responda EXATAMENTE com estas quatro seções,
nesta ordem, sem nenhuma seção extra, sem preâmbulo e sem texto após a última:

FATO: o que os dados mostram. Apenas números que vieram de ferramentas, com a
dimensão e o recorte a que se referem.
INFERÊNCIA: o que isso significa em termos de negócio, e o que ainda não está
provado. Separe o que é correlação do que é causal.
RECOMENDAÇÃO: ação concreta, com CINCO elementos obrigatórios:
  (a) o valor, vindo de ferramenta;
  (b) o RECORTE a que o valor se refere (campo `recorte_aplicado`) e o período —
      se o resultado trouxer `valor_anualizado_reais`, use-o para falar "por ano";
  (c) a premissa sob a qual o impacto vale, escrita numa frase própria que
      COMEÇA com a palavra "PREMISSA:" — literalmente, com dois-pontos;
  (d) o CONTROLE: interno (a Vértice decide sozinha) ou externo (depende de
      terceiro), porque uma alavanca externa pode valer R$ 0 se a contraparte
      recusar, e o comitê precisa saber disso antes de aprovar;
  (e) o DONO da ação.
Frente sem valor defensável não recebe meta em reais: recomenda-se o dado ou o
processo que tornaria a meta possível, dizendo o que falta coletar.
FORÇA DA EVIDÊNCIA: FORTE, MODERADA ou FRACA, com o critério estatístico que
sustenta (p-valor, n, R², tamanho de efeito) e a principal limitação.

Escreva em português do Brasil, direto, sem jargão vazio.

CONCISÃO — os limites abaixo são limites, não sugestões:
  FATO: no máximo 2 frases.
  INFERÊNCIA: no máximo 2 frases, e nenhuma delas repetindo o que já está em
    FATO — a inferência acrescenta leitura, não resume o que veio acima.
  RECOMENDAÇÃO: os cinco elementos em no máximo 4 frases. A premissa tem frase
    própria (começa com "PREMISSA:"); controle e dono cabem numa frase só.
  FORÇA DA EVIDÊNCIA: 1 frase, com o critério estatístico e a limitação.

Os cinco elementos da RECOMENDAÇÃO não são descartáveis: para caber no limite,
diga cada um de forma mais curta — nunca omita um deles.

Corte sempre: preâmbulo, repetição da pergunta, anúncio do que você vai fazer,
fechamento do tipo "em resumo" ou "espero ter ajudado", e adjetivo que não muda
a decisão. Um número com o recorte colado vale mais que a frase que o explica."""


PROTOCOLO_TEXTO = f"""== COMO USAR UMA FERRAMENTA ==
Para chamar uma ferramenta, responda EXATAMENTE neste formato e PARE — não escreva
mais nada depois:

PENSAMENTO: <por que esta ferramenta agora, em uma frase>
AÇÃO: <nome_exato_da_ferramenta>
PARÂMETROS: {{"chave": "valor"}}

Regras do protocolo:
- Uma ferramenta por vez. Espere o {ROTULO_RESULTADO} antes da próxima.
- PARÂMETROS é sempre um objeto JSON válido em UMA linha. Sem parâmetros: {{}}
- Nunca escreva AÇÃO e a resposta final na mesma mensagem.
- Nunca invente o resultado de uma ferramenta: ele chega na próxima mensagem.
- Se vier um {ROTULO_ERRO}, leia a mensagem, corrija o nome/parâmetro e repita."""


PROTOCOLO_NATIVO = """== COMO USAR UMA FERRAMENTA ==
Use o mecanismo nativo de function calling da API. Chame uma ferramenta por vez e
aguarde o resultado antes da próxima. Quando tiver evidência suficiente, responda
em texto no formato final obrigatório, sem chamar mais ferramentas."""


COBRAR_INVESTIGACAO = (
    f"{ROTULO_SISTEMA} Você respondeu usando apenas o retrato consolidado, sem chamar "
    "nenhuma ferramenta específica para esta pergunta. O consolidado é o ponto de "
    "partida, não a resposta. Escolha agora a ferramenta que responde diretamente à "
    "pergunta (por exemplo: uma simulação para perguntas do tipo 'e se...', "
    "margem_por_dimensao para 'qual canal/categoria', um teste estatístico para "
    "'isso é significativo', indice_sazonalidade antes de comparar períodos) e chame-a "
    "no formato AÇÃO/PARÂMETROS. Só depois responda no formato final."
)


def cobrar_investigacao() -> str:
    from ..engine import REGISTRO
    return COBRAR_INVESTIGACAO + f"\nFerramentas disponíveis: {', '.join(sorted(REGISTRO))}."


# Roteamento por palavra-chave: NÃO decide nada, apenas destaca candidatas no
# primeiro turno. Com 20 ferramentas num prompt longo, o modelo pequeno perde o
# catálogo e desiste da pergunta; cada correção custa uma ida ao gateway (~30s).
# A escolha continua sendo do agente, que pode ignorar as sugestões.
PISTAS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("simul", "e se", "cenario", "cenário", "aplicar", "impacto de aplicar", "teto"),
     ("simular_desconto_em_segmento", "simular_teto_desconto", "cenarios_reducao_desconto")),
    (("frete", "entrega", "marketplace"),
     ("politica_frete_por_canal", "custo_assimetria_frete",
      "dispersao_componentes_entre_canais")),
    (("volume", "incremental", "compra volume", "faixa de desconto"),
     ("tabela_faixas_desconto",)),
    (("sazonal", "novembro", "dezembro", "mes", "mês", "periodo", "período", "trimestre",
      "estrutural", "tendencia", "tendência"),
     ("indice_sazonalidade", "comparar_periodos", "tendencia_ajustada_sazonalidade")),
    (("canal", "categoria", "sku", "onde", "qual canal", "pior margem"),
     ("margem_por_dimensao",)),
    (("significat", "estatistic", "estatístic", "prova", "confia", "acaso", "correlac"),
     ("teste_t_welch", "anova_um_fator", "qui_quadrado_independencia",
      "classificar_evidencia")),
    (("devolu", "reembolso", "troca"), ("impacto_devolucoes",)),
    (("marketing", "roas", "campanha", "cac", "investimento"), ("ranking_roas_canais",)),
    (("negativa", "prejuizo", "prejuízo", "destroi", "destrói", "ticket baixo"),
     ("pedidos_margem_negativa",)),
]


MAX_SUGESTOES = 4


def sugerir_ferramentas(pergunta: str, limite: int = MAX_SUGESTOES) -> list[str]:
    """Candidatas prováveis para a pergunta, por palavra-chave. Apenas uma pista.

    Limitado de propósito: uma lista longa dilui o sinal tanto quanto o catálogo
    inteiro. A ordem de PISTAS coloca as intenções mais específicas primeiro.
    """
    from ..engine import REGISTRO

    texto = (pergunta or "").lower()
    saida: list[str] = []

    # A ferramenta que o roteador determinístico escolheu vem primeiro. Sem
    # isso, "limitar o desconto de Moda no Email Marketing a 17%" casava com a
    # pista de *marketing* e sugeria ranking_roas_canais — a pista empurrava o
    # modelo para o lado errado justamente na pergunta que ele já errava.
    try:
        from .router import rotear
        escolhida = rotear(pergunta).ferramenta
        if escolhida and escolhida in REGISTRO:
            saida.append(escolhida)
    except Exception:
        pass

    for gatilhos, ferramentas in PISTAS:
        if any(g in texto for g in gatilhos):
            for f in ferramentas:
                if f in REGISTRO and f not in saida:
                    saida.append(f)
    return saida[:limite]


def bloco_sugestoes(pergunta: str) -> str:
    sugeridas = sugerir_ferramentas(pergunta)
    if not sugeridas:
        return ""
    return (
        f"\n\nFerramentas que costumam responder perguntas como esta: "
        f"{', '.join(sugeridas)}. É apenas uma pista — você decide quais chamar, e "
        f"pode usar qualquer outra do catálogo."
    )


# Meses em português -> número. A base só cobre 2023-01 a 2024-01: para
# fevereiro-dezembro existe um único ano possível nos dados (2023); só janeiro é
# ambíguo (2023-01 ou 2024-01) e exige ano explícito na pergunta para resolver.
_MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}


def _extrair_valores_da_pergunta(pergunta: str) -> dict[str, str]:
    """Valores literais da pergunta (percentual, canal, categoria, mês) para
    pré-preencher o exemplo de chamada.

    Delega para `agent/router.extrair_parametros`, que é a fonte única dessa
    leitura — quando este módulo tinha a sua própria cópia, ela não conhecia
    CATEGORIA e o exemplo saía sem ela justamente nas perguntas de segmento.
    Nada é adivinhado: mês ambíguo (janeiro, que existe em 2023 e 2024) fica
    de fora em vez de virar palpite.
    """
    from .router import extrair_parametros

    try:
        achados = extrair_parametros(pergunta)
    except Exception:
        return {}      # best-effort: nunca pode derrubar o loop do agente
    achados.pop("_texto_sem_dominio", None)
    pct = achados.pop("percentual", None)
    saida = {k: str(v) for k, v in achados.items()}
    if pct is not None:
        # inteiro sai sem ".0": "17", não "17.0" — é o que o modelo copia.
        saida["percentual"] = str(int(pct)) if float(pct).is_integer() else str(pct)
    return saida


def exemplo_chamada(nome: str, pergunta: str = "") -> str:
    """Bloco 'PARÂMETROS: {...}' de exemplo para uma ferramenta, com nomes reais
    dos parâmetros e suas descrições. Quando `pergunta` é passada e algum valor
    (percentual/canal/mês) aparece nela literalmente, o parâmetro correspondente
    já vem PREENCHIDO, não como <placeholder> — reduz o passo de composição que,
    em produção, um modelo mais fraco (claude-haiku-45) falhou em completar
    sozinho mesmo depois de ver o exemplo abstrato.
    """
    from ..engine import REGISTRO

    f = REGISTRO[nome]
    if not f.parametros:
        return f"  {nome}\n    PARÂMETROS: {{}}"

    achados = _extrair_valores_da_pergunta(pergunta)
    # "desconto_pct", "teto_pct", "limiar_pct" etc. -> valor percentual extraído.
    pct = achados.get("percentual")

    partes = []
    for k, desc in f.parametros.items():
        if pct is not None and "pct" in k:
            valor = pct
        elif k == "canal" and "canal" in achados:
            valor = achados["canal"]
        elif k == "mes" and "mes" in achados:
            valor = achados["mes"]
        elif k == "categoria" and "categoria" in achados:
            valor = achados["categoria"]
        elif k in f.destacados:
            # obrigatório (ou principal) e não extraído: precisa ficar visível
            # que falta preencher. `destacados` inclui o parâmetro que virou
            # opcional só porque existe política vigente como padrão — sem ele
            # no exemplo, o modelo repetia `PARÂMETROS: {}`.
            valor = f"<{desc}>"
        else:
            # opcional sem valor extraído: OMITE, não deixa <placeholder>. Se o
            # modelo copiar a linha ao pé da letra (é o que pedimos em
            # cobrar_parametros), um placeholder aqui viraria um valor literal
            # inválido — "<filtrar por categoria...>" não é uma categoria real.
            continue
        partes.append(f'"{k}": "{valor}"')
    obrig = ", ".join(f.destacados) or "nenhum"
    return f"  {nome}\n    obrigatórios: {obrig}\n    PARÂMETROS: {{{', '.join(partes)}}}"


def cobrar_parametros(nome: str, pergunta: str = "") -> str:
    """A ferramenta certa foi chamada, mas com parâmetro obrigatório ausente ou
    desconhecido. Diferente de citar-sem-chamar: aqui o modelo já tentou, então a
    falha é de PREENCHIMENTO — a resposta tem de ser o exemplo pronto para copiar,
    não uma segunda explicação do que está errado (isso ele já recebeu no erro).

    Regressão real: mesmo com o exemplo abstrato (<placeholder>), o modelo NÃO
    tentou de novo — foi direto tentar responder com número inventado. Com
    `pergunta`, o exemplo já vem com os valores literais prontos: a única ação
    que resta ao modelo é copiar a linha inteira, não compor JSON do zero.
    """
    ex = exemplo_chamada(nome, pergunta)
    return (
        f"{ROTULO_SISTEMA} Sua última chamada a '{nome}' falhou por parâmetro "
        f"ausente. Isto NÃO é motivo para desistir e responder sem o dado — a "
        f"ferramenta existe e está disponível agora. Sua PRÓXIMA mensagem tem "
        f"de ser exatamente estas duas linhas, sem nada mais:\n\n"
        f"AÇÃO: {nome}\n{ex.split(chr(10))[-1].strip()}"
    )


def cobrar_ferramenta_citada(nomes: list[str], pergunta: str = "") -> str:
    """O modelo nomeou a ferramenta certa na prosa mas não a executou.

    Devolvemos o schema exato de parâmetros — com valores já extraídos da
    pergunta quando possível (ver exemplo_chamada) — porque em produção o
    modelo identificou a ferramenta corretamente e mesmo assim desistiu, sem
    nunca emitir uma AÇÃO.
    """
    from ..engine import REGISTRO

    lista = "\n".join(exemplo_chamada(n, pergunta) for n in nomes[:3])
    return (
        f"{ROTULO_SISTEMA} Você citou a(s) ferramenta(s) {', '.join(nomes[:3])} na sua "
        f"resposta e disse que faltava o resultado dela — mas NÃO a executou. Ela existe "
        f"e está disponível agora. Não desista da pergunta: chame-a.\n\n"
        f"Formato dos parâmetros:\n{lista}\n\n"
        f"Responda AGORA apenas com as linhas AÇÃO e PARÂMETROS, preenchendo os valores "
        f"com o recorte que a pergunta pede. Nada de resposta final nesta mensagem."
    )


def cobrar_vocabulario_evidencia() -> str:
    """FORÇA DA EVIDÊNCIA usou palavra fora do vocabulário fechado ("Alta" em vez
    de FORTE/MODERADA/FRACA). Diferente de número inventado, isso não é
    incorreto — é só fora do contrato de formato. Uma cobrança leve, não um
    bloqueio: o conteúdo pode estar certo, só a palavra precisa trocar."""
    return (
        f"{ROTULO_SISTEMA} Sua seção FORÇA DA EVIDÊNCIA precisa terminar em "
        f'exatamente uma destas três palavras: FORTE, MODERADA ou FRACA — não '
        f'"Alta", "Baixa", "Confiável" ou qualquer outra. Se não tem certeza de '
        f"qual usar, chame classificar_evidencia com o p-valor/R²/n do teste que "
        f"você já rodou (ou rode um teste estatístico primeiro, se ainda não "
        f"rodou nenhum). Reescreva a resposta final inteira, com a palavra certa."
    )


def cobrar_teste_estatistico(palavra: str) -> str:
    """FORTE/MODERADA foi usado sem nenhum teste estatístico ter sido chamado.

    Regressão real: o modelo rotulou "FORTE" uma conclusão de mudança
    estrutural usando só indice_sazonalidade (descritivo, não teste de
    significância) — nunca chamou tendencia_ajustada_sazonalidade, que,
    chamada de verdade, dá p=0,17 (FRACA). FORTE/MODERADA sem teste real por
    trás é confiança tão infundada quanto um número inventado.
    """
    testes = ["teste_t_welch", "anova_um_fator", "regressao_linear_multipla",
              "qui_quadrado_independencia", "classificar_evidencia",
              "tendencia_ajustada_sazonalidade"]
    return (
        f"{ROTULO_SISTEMA} Você classificou a evidência como {palavra}, mas nesta "
        f"investigação NENHUMA ferramenta estatística foi chamada — {palavra} exige "
        f"um teste real (p-valor, R², n), não uma leitura qualitativa de tabela ou "
        f"índice descritivo (indice_sazonalidade, por exemplo, não é teste de "
        f"significância).\n"
        f"Ferramentas que produzem esse critério: {', '.join(testes)}.\n"
        f"Chame a que for adequada à pergunta AGORA, ou reescreva a resposta final "
        f"usando FRACA se decidir não rodar nenhuma."
    )


def cobrar_numeros(suspeitos: list[str]) -> str:
    from ..engine import REGISTRO
    return (
        f"{ROTULO_SISTEMA} PARE. Sua resposta contém números que NÃO apareceram em "
        f"nenhum resultado de ferramenta: {', '.join(suspeitos[:8])}. Você os calculou "
        f"por conta própria, e isso é proibido neste sistema — inclusive multiplicar, "
        f"somar ou aplicar um percentual sobre um número de ferramenta.\n"
        f"Se precisa desse cálculo, existe uma ferramenta que o faz: chame-a. Para "
        f"cenários do tipo 'e se aplicar X% de desconto em um canal/mês', use "
        f"simular_desconto_em_segmento com os parâmetros do recorte pedido.\n"
        f"Ferramentas disponíveis: {', '.join(sorted(REGISTRO))}.\n"
        f"Responda agora com AÇÃO/PARÂMETROS chamando a ferramenta correta, ou refaça "
        f"a resposta final usando SOMENTE números que apareceram nos resultados."
    )


def prompt_sintese(pergunta: str) -> str:
    return (
        f"{ROTULO_SISTEMA} Você já reuniu evidência suficiente (ou atingiu o limite de "
        f"investigação). Pare de chamar ferramentas e responda AGORA à pergunta "
        f'"{pergunta}" usando SOMENTE os números que apareceram nos resultados de '
        f"ferramenta acima. Use exatamente as quatro seções FATO / INFERÊNCIA / "
        f"RECOMENDAÇÃO / FORÇA DA EVIDÊNCIA, sem nenhuma seção extra."
    )


def cobrar_periodo_na_recomendacao() -> str:
    """A RECOMENDAÇÃO traz valor em R$ sem dizer a que período e recorte ele se
    refere.

    É a falha que a verificação numérica NÃO pega: o dígito está certo e veio de
    ferramenta, mas o qualificador que o acompanha não. Um acumulado de 13 meses
    apresentado como anual superestima em 8,3%; apresentado como mensal,
    superestima 13 vezes. A ferramenta já devolve `recorte_aplicado`,
    `periodo_coberto` e, quando cabe, `valor_anualizado_reais` — a cobrança é
    para o texto usar o que já está no resultado."""
    return (
        f"{ROTULO_SISTEMA} Sua RECOMENDAÇÃO cita um valor em R$ sem dizer a que "
        f"PERÍODO e a que RECORTE ele se refere. Todo valor do motor vale para uma "
        f"população específica, e o resultado da ferramenta traz isso pronto nos "
        f"campos `recorte_aplicado` e `periodo_coberto` (e `valor_anualizado_reais`, "
        f"quando o recorte não fecha 12 meses). Reescreva a resposta final inteira "
        f"citando o recorte junto do número — por exemplo \"R$ X por ano (2023, "
        f"pedidos mantidos, novembro fora)\". Não recalcule nada: use os campos que "
        f"a ferramenta já devolveu."
    )


# Um valor em reais na RECOMENDAÇÃO precisa vir acompanhado de janela temporal.
RE_VALOR_REAIS = re.compile(r"R\$\s*\d")
MARCAS_DE_PERIODO = (
    "por ano", "ao ano", "anual", "anualizado", "por mês", "por mes", "mensal",
    "2023", "2024", "13 meses", "12 meses", "no ano", "do ano", "por semana",
    "recorte", "acumulado", "período", "periodo", "base de decisão",
    "base de decisao", "pedidos mantidos", "por trimestre",
)


def recomendacao_declara_periodo(texto: str) -> bool:
    """A seção RECOMENDAÇÃO cita período/recorte junto do valor em R$?

    Só cobra quando HÁ valor em R$ na seção: recomendação sem número (coletar o
    dado, negociar o contrato) não precisa declarar período nenhum, e cobrá-la
    seria falso positivo — o tipo de rigidez que já custou uma investigação
    inteira neste projeto quando o formato foi exigido ao pé da letra.
    """
    m = re.search(r"RECOMENDA[ÇC][ÃA]O:(.*?)(?=FOR[ÇC]A\s+DA\s+EVID|$)",
                  texto or "", re.S | re.I)
    if not m:
        return True
    secao = m.group(1)
    if not RE_VALOR_REAIS.search(secao):
        return True
    baixo = secao.lower()
    return any(marca in baixo for marca in MARCAS_DE_PERIODO)
