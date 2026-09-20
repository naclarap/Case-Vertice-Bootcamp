"""Testes do agente ReAct: parser, loop, trace e contrato de saída."""
import json

import pytest

from vertice.agent.react import (AgenteMargem, extrair_acao, validar_formato_final)
from vertice.agent.trace import Trace

ACAO_TESTE_ESTATISTICO = ('AÇÃO: teste_t_welch\nPARÂMETROS: {"metrica": "margem_pct", '
                          '"coluna_grupo": "canal", "grupo_a": "Marketplace"}')

RESPOSTA_OK = ("FATO: margem consolidada de 49,99%.\n"
               "INFERÊNCIA: o desconto é o maior vazamento.\n"
               "RECOMENDAÇÃO: impor teto de 25%.\n"
               "FORÇA DA EVIDÊNCIA: FORTE (p<0,001, n=24.454).")


# ------------------------------------------------------------------- parser
@pytest.mark.parametrize("texto,ferramenta,params", [
    ('AÇÃO: margem_consolidada\nPARÂMETROS: {}', "margem_consolidada", {}),
    ('ACAO: margem_consolidada\nPARAMETROS: {}', "margem_consolidada", {}),  # sem acento
    ('**AÇÃO:** margem_por_dimensao\n**PARÂMETROS:** {"dimensao": "canal"}',
     "margem_por_dimensao", {"dimensao": "canal"}),
    ("AÇÃO: teste_t_welch\nPARÂMETROS: {'metrica': 'margem_pct',}",  # aspas simples + vírgula
     "teste_t_welch", {"metrica": "margem_pct"}),
    ('AÇÃO: `margem_consolidada`\nPARÂMETROS: {}', "margem_consolidada", {}),
    ('ação: margem_consolidada\nparâmetros: {}', "margem_consolidada", {}),  # minúsculas
])
def test_parser_extrai_acao(texto, ferramenta, params):
    f, p, _ = extrair_acao(texto)
    assert f == ferramenta
    assert p == params


def test_parser_extrai_pensamento():
    _, _, pens = extrair_acao("PENSAMENTO: preciso abrir por canal\n"
                              "AÇÃO: margem_por_dimensao\nPARÂMETROS: {}")
    assert pens == "preciso abrir por canal"


def test_parser_nao_confunde_resposta_final_com_acao():
    """A resposta final cita nomes de ferramenta no texto; não pode virar chamada."""
    texto = ("FATO: usei margem_consolidada e margem_por_dimensao.\n"
             "AÇÃO: nenhuma necessária.\nINFERÊNCIA: x\nRECOMENDAÇÃO: y\n"
             "FORÇA DA EVIDÊNCIA: FORTE")
    f, _, _ = extrair_acao(texto)
    assert f is None


def test_parser_tolera_texto_sem_acao():
    assert extrair_acao("Não sei o que fazer.") == (None, {}, None)
    assert extrair_acao("") == (None, {}, None)


def test_parser_params_ilegiveis_viram_dict_vazio():
    f, p, _ = extrair_acao("AÇÃO: margem_consolidada\nPARÂMETROS: {isso não é json")
    assert f == "margem_consolidada" and p == {}


# --------------------------------------------------------- formato de saída
def test_validador_aceita_formato_correto():
    assert validar_formato_final(RESPOSTA_OK)["valido"]


def test_validador_rejeita_secao_faltante():
    r = validar_formato_final("FATO: x\nINFERÊNCIA: y")
    assert not r["valido"]
    assert "RECOMENDAÇÃO" in r["faltando"]


def test_validador_rejeita_ordem_errada():
    r = validar_formato_final("INFERÊNCIA: y\nFATO: x\nRECOMENDAÇÃO: z\n"
                              "FORÇA DA EVIDÊNCIA: FRACA")
    assert not r["valido"]
    assert not r["na_ordem"]


def test_preambulo_e_removido_da_resposta_final():
    ag = AgenteMargem(mock=True, roteiro_mock=["Claro! Vou responder.\n\n" + RESPOSTA_OK],
                      verbose=False)
    tr = ag.investigar("qual a margem?")
    assert tr.resposta_final.startswith("FATO:")
    assert validar_formato_final(tr.resposta_final)["valido"]


# ------------------------------------------------------------------- loop
def test_pre_semeadura_chama_ferramenta_antes_do_modelo():
    """Sem pré-semear, o modelo pede dados ao usuário em vez de investigar."""
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    tr = ag.investigar("qual a margem consolidada?")
    assert tr.ferramentas_usadas[0] == "margem_consolidada"
    # A 1ª mensagem enviada ao modelo já contém o resultado da semente.
    primeira = ag.llm.chamadas[0]
    assert any("RESULTADO DE FERRAMENTA" in m["content"] for m in primeira)


def test_agente_encadeia_multiplas_ferramentas():
    roteiro = [
        'AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}',
        'AÇÃO: dispersao_componentes_entre_canais\nPARÂMETROS: {}',
        'AÇÃO: custo_assimetria_frete\nPARÂMETROS: {"canal": "Marketplace"}',
        RESPOSTA_OK,
    ]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("por que o Marketplace tem margem menor?")
    # Pergunta ABERTA: as duas sementes vêm antes (retrato consolidado e ponte
    # do pós-pedido), e só então a investigação do modelo.
    assert tr.ferramentas_usadas == ["margem_consolidada", "perda_pos_pedido",
                                     "margem_por_dimensao",
                                     "dispersao_componentes_entre_canais",
                                     "custo_assimetria_frete"]
    assert validar_formato_final(tr.resposta_final)["valido"]


def test_agente_se_recupera_de_ferramenta_inexistente():
    roteiro = ["AÇÃO: ferramenta_fantasma\nPARÂMETROS: {}",
               'AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}',
               ACAO_TESTE_ESTATISTICO, RESPOSTA_OK]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("teste de erro")
    erros = [p for p in tr.passos if p.tipo == "erro"]
    assert len(erros) == 1
    assert validar_formato_final(tr.resposta_final)["valido"]
    # O erro precisa voltar ao modelo de forma acionável (sugestão ou orientação).
    ultimo = ag.llm.chamadas[-1]
    assert any("ERRO DE FERRAMENTA" in m["content"] for m in ultimo)
    assert any("Você quis dizer" in m["content"] or "não invente uma" in m["content"]
               for m in ultimo)


def test_agente_se_recupera_de_parametro_invalido():
    roteiro = ['AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "galaxia"}',
               'AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}',
               ACAO_TESTE_ESTATISTICO, RESPOSTA_OK]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("teste")
    assert len([p for p in tr.passos if p.tipo == "erro"]) == 1
    assert tr.resposta_final.startswith("FATO:")


def test_limite_de_iteracoes_forca_sintese():
    """Modelo em loop infinito de ferramentas deve ser cortado e sintetizar."""
    roteiro = ["AÇÃO: margem_consolidada\nPARÂMETROS: {}"] * 20 + [RESPOSTA_OK]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, max_iteracoes=3, verbose=False)
    tr = ag.investigar("pergunta infinita")
    assert len(tr.ferramentas_usadas) == 5  # 2 sementes + 3 iterações
    assert tr.resposta_final.startswith("FATO:")


def test_resposta_sem_acao_e_sem_formato_forca_sintese():
    """Caso clássico do gateway: o modelo pede dados ao usuário."""
    roteiro = ["Preciso que você me envie os dados de vendas para começar.", RESPOSTA_OK]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("qual a margem?")
    assert validar_formato_final(tr.resposta_final)["valido"]
    ultimo = ag.llm.chamadas[-1]
    assert any("Pare de chamar ferramentas" in m["content"] for m in ultimo)


def test_historico_preserva_etiquetas_entre_perguntas():
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK, RESPOSTA_OK], verbose=False)
    ag.investigar("primeira pergunta")
    ag.investigar("segunda pergunta")
    assert len(ag.historico) == 4
    assert ag.historico[0]["content"].startswith("[PERGUNTA DO USUÁRIO]")
    assert ag.historico[0]["role"] == "user"
    assert ag.historico[1]["role"] == "assistant"


def test_todo_numero_da_resposta_vem_de_ferramenta():
    """O agente não pode calcular: a resposta final só pode conter números que
    apareceram em alguma observação de ferramenta."""
    # 1ª resposta dispara a cobrança por investigar; a 2ª dispara a cobrança de
    # teste estatístico (FORTE sem teste real); a 3ª é aceita (rebaixada p/ FRACA,
    # mas o número em FATO continua intacto).
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK, RESPOSTA_OK, RESPOSTA_OK],
                      verbose=False)
    tr = ag.investigar("qual a margem consolidada?")
    obs = [p for p in tr.passos if p.tipo == "observacao"]
    assert obs, "deve haver ao menos uma observação de ferramenta"
    # 49,99 aparece na resposta e veio de margem_consolidada.
    assert obs[0].conteudo["margem_pct"] == 49.99
    assert "49,99" in tr.resposta_final


# ------------------------------------------------------------------- trace
def test_trace_serializa_em_json_para_painel():
    ag = AgenteMargem(mock=True, roteiro_mock=[
        'AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}', RESPOSTA_OK], verbose=False)
    tr = ag.investigar("teste de trace")
    d = json.loads(tr.to_json())
    assert d["pergunta"] == "teste de trace"
    assert d["n_chamadas_ferramenta"] == 3
    assert {p["tipo"] for p in d["passos"]} >= {"pergunta", "acao", "observacao", "resposta_final"}
    for p in d["passos"]:
        assert {"indice", "tipo", "conteudo", "timestamp"} <= set(p)
    acoes = [p for p in d["passos"] if p["tipo"] == "acao"]
    assert all(a["ferramenta"] and a["parametros"] is not None for a in acoes)
    obs = [p for p in d["passos"] if p["tipo"] == "observacao"]
    assert all(o["duracao_ms"] is not None for o in obs)


def test_trace_salva_arquivo(tmp_path):
    tr = Trace(pergunta="x")
    tr.add("pensamento", "y")
    tr.encerrar("z")
    p = tr.salvar(tmp_path)
    assert p.exists()
    assert json.loads(p.read_text(encoding="utf-8"))["pergunta"] == "x"


def test_observacao_grande_e_truncada():
    """Resultado gigante (ex: SKU) não pode estourar o contexto do modelo."""
    ag = AgenteMargem(mock=True, roteiro_mock=[
        'AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "sku"}', RESPOSTA_OK], verbose=False)
    ag.investigar("margem por sku")
    enviados = [m["content"] for m in ag.llm.chamadas[-1] if "RESULTADO DE FERRAMENTA" in m["content"]]
    assert any("truncado" in c for c in enviados)


def test_fallback_quando_modelo_nunca_produz_formato_final():
    """Se o modelo insiste em não sintetizar, não devolvemos texto cru: entregamos
    um fallback auditável, ainda nas quatro seções, sem inventar conclusão."""
    roteiro = ["AÇÃO: margem_consolidada\nPARÂMETROS: {}"] * 30
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, max_iteracoes=2, verbose=False)
    tr = ag.investigar("pergunta que nunca converge")
    assert validar_formato_final(tr.resposta_final)["valido"]
    assert "não foi possível sintetizar" in tr.resposta_final.lower()
    assert tr.id in tr.resposta_final           # aponta o trace para auditoria
    assert "FRACA" in tr.resposta_final
    assert not tr.resposta_final.startswith("AÇÃO")


def test_fallback_nao_dispara_quando_ha_resposta_valida():
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    tr = ag.investigar("pergunta normal")
    assert "não foi possível sintetizar" not in tr.resposta_final.lower()


def test_segunda_tentativa_de_sintese_recupera_formato():
    """1ª síntese sai errada, 2ª sai certa: não deve cair no fallback."""
    roteiro = ["AÇÃO: margem_consolidada\nPARÂMETROS: {}",  # consome a iteração
               "Ainda preciso investigar mais.",             # síntese 1 falha
               RESPOSTA_OK]                                  # síntese 2 acerta
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, max_iteracoes=1, verbose=False)
    tr = ag.investigar("pergunta")
    assert validar_formato_final(tr.resposta_final)["valido"]
    assert "não foi possível sintetizar" not in tr.resposta_final.lower()


# --------------------------------------------------- modo de tools nativo
class _LLMNativo:
    """Simula function calling nativo da API, inclusive o modo de falha observado
    no gateway EloAgents: o modelo chamar uma ferramenta que não é nossa."""

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.chamadas = []

    def completar(self, mensagens, modelo, tools=None):
        self.chamadas.append(mensagens)
        item = self.roteiro.pop(0) if self.roteiro else ("texto", RESPOSTA_OK)
        tipo, carga = item
        if tipo == "texto":
            return type("M", (), {"content": carga, "tool_calls": None})()
        nome, args = carga
        fn = type("F", (), {"name": nome, "arguments": json.dumps(args)})()
        tc = type("TC", (), {"function": fn, "id": "call_1"})()
        return type("M", (), {"content": "", "tool_calls": [tc]})()


def test_modo_nativo_executa_tool_calls():
    llm = _LLMNativo([("tool", ("margem_por_dimensao", {"dimensao": "canal"})),
                      ("texto", RESPOSTA_OK)])
    ag = AgenteMargem(llm=llm, modo="nativo", verbose=False)
    tr = ag.investigar("teste nativo")
    assert tr.ferramentas_usadas == ["margem_consolidada", "perda_pos_pedido",
                                     "margem_por_dimensao"]
    assert validar_formato_final(tr.resposta_final)["valido"]


def test_modo_nativo_rejeita_ferramenta_de_plataforma():
    """Falha real do gateway: o modelo chama 'view_skill', que não existe no nosso
    registro. Tem de virar erro explícito, nunca número inventado."""
    llm = _LLMNativo([
        ("tool", ("view_skill", {})),
        ("tool", ("teste_t_welch", {"metrica": "margem_pct", "coluna_grupo": "canal",
                                    "grupo_a": "Marketplace"})),
        ("texto", RESPOSTA_OK),
    ])
    ag = AgenteMargem(llm=llm, modo="nativo", verbose=False)
    tr = ag.investigar("teste de ferramenta fantasma")
    erros = [p for p in tr.passos if p.tipo == "erro"]
    assert len(erros) == 1 and "view_skill" in erros[0].conteudo
    assert validar_formato_final(tr.resposta_final)["valido"]


# ------------------------------------------------------------------- CLI
@pytest.mark.parametrize("valor,casas,esperado", [
    (18119023.83, 2, "18.119.023,83"),
    (1450067.34, 2, "1.450.067,34"),
    (0.5, 2, "0,50"),
    (24454, 0, "24.454"),
])
def test_formatacao_brasileira_de_numeros(valor, casas, esperado):
    from vertice.cli import _brl
    assert _brl(valor, casas) == esperado


def test_cli_lista_ferramentas_sem_gateway(capsys):
    from vertice.cli import main
    assert main(["--ferramentas"]) == 0
    assert "ferramentas no motor determinístico" in capsys.readouterr().out


def test_cli_pergunta_unica_em_mock(capsys):
    from vertice.cli import main
    assert main(["--mock", "--silencioso", "-p", "qual a margem consolidada?"]) == 0
    assert "FATO:" in capsys.readouterr().out


# ------------------------------------------- regressões do bug de produção
@pytest.mark.parametrize("texto", [
    "Não há ferramenta para isso.\nAÇÃO: N/A",
    "AÇÃO: Não aplicável — não existe ferramenta para simular isso.",
    "AÇÃO: nenhuma",
    "AÇÃO: N",
])
def test_nao_acao_nao_vira_chamada_de_ferramenta(texto):
    """Regressão: 'AÇÃO: N/A' era capturado como a ferramenta 'N' porque
    re.IGNORECASE fazia [a-z_] casar maiúsculas."""
    f, _, _ = extrair_acao(texto)
    assert f is None


@pytest.mark.parametrize("texto", [
    "Precisamos avaliar a ação dos descontos sobre a margem consolidada.",
    "A ação dos gestores foi aumentar o desconto em novembro.",
    "Vou analisar o impacto da ação: dos descontos no Marketplace.",
    "Essa ação deve ser tomada com cautela.",
])
def test_prosa_no_meio_da_frase_nao_vira_acao(texto):
    """Regressão: o dois-pontos era opcional e o regex não era ancorado em linha,
    então 'a ação dos descontos' virava uma chamada à ferramenta 'dos'."""
    f, _, _ = extrair_acao(texto)
    assert f is None


def test_erro_sugere_ferramenta_parecida_em_vez_de_listar_todas():
    from vertice.agent.react import _sugestao
    assert "simular_teto_desconto" in _sugestao("simular_desconto")
    assert "margem_consolidada" in _sugestao("margem_consolidad")
    assert _sugestao("margem_consolidada") == ""       # nome válido, sem ruído
    assert "não invente uma" in _sugestao("xyzzy")     # nada parecido


def test_falha_identica_repetida_interrompe_o_loop():
    """Regressão: o agente repetiu 4x a mesma chamada inválida e queimou o limite
    de iterações. Três falhas idênticas devem cortar a investigação."""
    roteiro = ["AÇÃO: ferramenta_fantasma\nPARÂMETROS: {}"] * 10 + [RESPOSTA_OK]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, max_iteracoes=8, verbose=False)
    tr = ag.investigar("pergunta que trava")
    erros_ferramenta = [p for p in tr.passos if p.tipo == "erro" and p.ferramenta]
    assert len(erros_ferramenta) == 3, (
        f"deveria parar na 3ª falha idêntica, houve {len(erros_ferramenta)}")
    # Não gastou as 8 iterações batendo na mesma parede.
    assert len(tr.ferramentas_usadas) < 8
    assert validar_formato_final(tr.resposta_final)["valido"]


def test_segunda_falha_identica_recebe_aviso_explicito():
    roteiro = ["AÇÃO: ferramenta_fantasma\nPARÂMETROS: {}"] * 5 + [RESPOSTA_OK]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, max_iteracoes=8, verbose=False)
    ag.investigar("pergunta")
    todas = [m["content"] for ch in ag.llm.chamadas for m in ch]
    assert any("NÃO repita" in c for c in todas)


# --------------------------- formato final tolerante a markdown (bug real)
@pytest.mark.parametrize("texto", [
    "**FATO:** x\n**INFERÊNCIA:** y\n**RECOMENDAÇÃO:** z\n**FORÇA DA EVIDÊNCIA:** FORTE",
    "**FATO**: x\n\n**INFERÊNCIA**: y\n\n**RECOMENDAÇÃO**: z\n\n**FORÇA DA EVIDÊNCIA**: FORTE",
    "## FATO\nx\n## INFERÊNCIA\ny\n## RECOMENDAÇÃO\nz\n## FORÇA DA EVIDÊNCIA\nFORTE",
    "FATO: x\nINFERENCIA: y\nRECOMENDACAO: z\nFORCA DA EVIDENCIA: FORTE",
    "- FATO: x\n- INFERÊNCIA: y\n- RECOMENDAÇÃO: z\n- FORÇA DA EVIDÊNCIA: FORTE",
])
def test_validador_aceita_markdown_e_falta_de_acento(texto):
    """Regressão: o modelo devolvia '**FATO:**' e o validador rejeitava, jogando
    fora uma resposta boa e caindo no fallback."""
    assert validar_formato_final(texto)["valido"], texto[:40]


def test_normalizacao_produz_cabecalho_canonico():
    from vertice.agent.react import normalizar_formato_final
    bruto = ("**FATO:** a margem é 49,99%.\n**INFERÊNCIA:** y\n"
             "**RECOMENDAÇÃO:** z\n**FORÇA DA EVIDÊNCIA:** FORTE")
    out = normalizar_formato_final(bruto)
    assert out.startswith("FATO: a margem é 49,99%.")
    assert "**" not in out
    for secao in ["FATO:", "INFERÊNCIA:", "RECOMENDAÇÃO:", "FORÇA DA EVIDÊNCIA:"]:
        assert f"\n{secao} " in out or out.startswith(f"{secao} ")


def test_resposta_em_markdown_nao_cai_no_fallback():
    """Ponta a ponta: resposta em markdown tem de ser aceita e normalizada."""
    md = ("**FATO:** o Marketplace tem margem 47,57%.\n**INFERÊNCIA:** assimetria de frete.\n"
          "**RECOMENDAÇÃO:** equalizar política.\n**FORÇA DA EVIDÊNCIA:** FORTE")
    ag = AgenteMargem(mock=True, roteiro_mock=[
        'AÇÃO: custo_assimetria_frete\nPARÂMETROS: {"canal": "Marketplace"}',
        ACAO_TESTE_ESTATISTICO, md], verbose=False)
    tr = ag.investigar("por que o Marketplace tem margem menor?")
    assert validar_formato_final(tr.resposta_final)["valido"]
    assert "não foi possível sintetizar" not in tr.resposta_final.lower()
    assert tr.resposta_final.startswith("FATO: o Marketplace")
    assert "**" not in tr.resposta_final


def test_fallback_guarda_a_resposta_rejeitada_no_trace():
    """Quando o fallback dispara, precisamos poder ver o que o modelo respondeu."""
    ag = AgenteMargem(mock=True, roteiro_mock=["texto sem formato"] * 6, max_iteracoes=1,
                      verbose=False)
    tr = ag.investigar("pergunta")
    erros = [p for p in tr.passos if p.tipo == "erro" and isinstance(p.conteudo, dict)]
    assert erros, "o fallback deve registrar a resposta rejeitada"
    assert "resposta_rejeitada" in erros[-1].conteudo
    assert "validacao" in erros[-1].conteudo


# ----------------------------------- cobrança por investigar (bug real)
def test_resposta_so_com_a_semente_e_cobrada_uma_vez():
    """Regressão: o agente respondeu uma pergunta de simulação usando só o retrato
    consolidado, sem chamar nenhuma ferramenta específica."""
    roteiro = [RESPOSTA_OK,  # tenta responder sem investigar -> cobrança
               'AÇÃO: simular_desconto_em_segmento\nPARÂMETROS: '
               '{"desconto_pct": "30", "canal": "Marketplace"}',
               RESPOSTA_OK]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    # Pergunta ABERTA de propósito: "simule 30% no Marketplace" passou a ser
    # resolvida pelo roteador determinístico (percentual + segmento explícitos),
    # e nesse caminho a ferramenta já roda antes do primeiro turno — não há o
    # que cobrar. A cobrança continua existindo para o que sobra ao ReAct.
    tr = ag.investigar("o que explica a queda de margem no fim do ano?")
    assert "simular_desconto_em_segmento" in tr.ferramentas_usadas
    assert validar_formato_final(tr.resposta_final)["valido"]
    todas = [m["content"] for ch in ag.llm.chamadas for m in ch]
    assert any("apenas o retrato consolidado" in c for c in todas)


def test_cobranca_por_investigar_nao_repete():
    """Se o modelo insistir em responder sem investigar, aceita na 2ª — a cobrança
    é uma só, senão o loop nunca termina."""
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK, RESPOSTA_OK], verbose=False)
    tr = ag.investigar("qual a margem consolidada?")
    assert validar_formato_final(tr.resposta_final)["valido"]
    assert len(tr.ferramentas_usadas) == 1     # só a semente
    cobrancas = [p for p in tr.passos if p.tipo == "pensamento"
                 and "cobrando investigação" in str(p.conteudo)]
    assert len(cobrancas) == 1


# ------------------- guarda de rastreabilidade numérica (bug crítico real)
RESPOSTA_INVENTADA = (
    "FATO: Desconto adicional: R$ 18.119.023,83 × 30% = R$ 5.435.707,15.\n"
    "Nova margem: R$ 3.622.720,40, ou 19,99%.\n"
    "INFERÊNCIA: queda de 30 pontos.\n"
    "RECOMENDAÇÃO: insustentável.\n"
    "FORÇA DA EVIDÊNCIA: Baixa."
)


def test_numero_inventado_e_bloqueado_e_nao_publicado():
    """Regressão do bug mais grave: o modelo multiplicou por conta própria e o
    sistema publicou o resultado como se fosse apuração."""
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_INVENTADA] * 6, verbose=False)
    tr = ag.investigar("simule 30% de desconto no Marketplace em novembro")
    assert validar_formato_final(tr.resposta_final)["valido"]
    assert "bloqueada por falha de rastreabilidade" in tr.resposta_final
    # Os valores inventados não podem ser apresentados como conclusão.
    depois_do_fato = tr.resposta_final.split("INFERÊNCIA")[1]
    assert "3.622.720,40" not in depois_do_fato
    assert "19,99%" not in depois_do_fato


def test_modelo_e_cobrado_antes_de_ser_bloqueado():
    """O bloqueio é último recurso: primeiro o agente cobra a correção."""
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_INVENTADA] * 6, verbose=False)
    ag.investigar("simule 30% de desconto")
    todas = [m["content"] for ch in ag.llm.chamadas for m in ch]
    assert any("NÃO apareceram em nenhum resultado de ferramenta" in c for c in todas)
    assert any("simular_desconto_em_segmento" in c for c in todas)


def test_modelo_que_se_corrige_chamando_a_ferramenta_e_aceito():
    boa = ("FATO: aplicar 30% nos 795 pedidos do Marketplace em novembro/2023 "
           "(R$ 553.175,73) custaria R$ 122.656,48; margem consolidada de 49,99% "
           "para 49,32%.\nINFERÊNCIA: perda direta sob volume constante.\n"
           "RECOMENDAÇÃO: testar em A/B.\nFORÇA DA EVIDÊNCIA: MODERADA.")
    ag = AgenteMargem(mock=True, roteiro_mock=[
        RESPOSTA_INVENTADA,
        'AÇÃO: simular_desconto_em_segmento\nPARÂMETROS: '
        '{"desconto_pct": "30", "canal": "Marketplace", "mes": "2023-11"}',
        ACAO_TESTE_ESTATISTICO, boa], verbose=False)
    tr = ag.investigar("simule 30% de desconto no Marketplace em novembro")
    assert "bloqueada" not in tr.resposta_final
    assert "122.656,48" in tr.resposta_final
    assert "simular_desconto_em_segmento" in tr.ferramentas_usadas


def test_verificacao_numerica_fica_registrada_no_trace():
    """O painel e a auditoria precisam ver que a checagem aconteceu."""
    ag = AgenteMargem(mock=True, roteiro_mock=[
        'AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}', RESPOSTA_OK],
        verbose=False)
    tr = ag.investigar("qual canal tem pior margem?")
    verifs = [p for p in tr.passos if p.tipo == "pensamento"
              and isinstance(p.conteudo, dict) and "verificacao_numerica" in p.conteudo]
    assert verifs, "a verificação numérica deve ficar no trace"
    assert verifs[-1].conteudo["verificacao_numerica"]["ok"]


def test_resposta_valida_nao_e_bloqueada_por_engano():
    """Não pode haver falso positivo: resposta honesta passa direto."""
    ag = AgenteMargem(mock=True, roteiro_mock=[
        'AÇÃO: margem_consolidada\nPARÂMETROS: {}', ACAO_TESTE_ESTATISTICO,
        "FATO: a margem consolidada é 49,99% sobre R$ 18.119.023,83.\n"
        "INFERÊNCIA: x\nRECOMENDAÇÃO: y\nFORÇA DA EVIDÊNCIA: FORTE"], verbose=False)
    tr = ag.investigar("qual a margem?")
    assert "bloqueada" not in tr.resposta_final
    assert tr.resposta_final.startswith("FATO: a margem consolidada é 49,99%")


# ------------- ferramenta citada na prosa mas nunca chamada (bug real)
DESISTE = (
    "FATO: não há dados segmentados por canal ou período.\n"
    "INFERÊNCIA: sem resultado da ferramenta `simular_desconto_em_segmento`, "
    "não é possível quantificar.\n"
    "RECOMENDAÇÃO: executar a ferramenta de simulação.\n"
    "FORÇA DA EVIDÊNCIA: Nenhuma."
)


def test_ferramenta_citada_sem_ser_chamada_e_cobrada():
    """Regressão: o modelo identificou a ferramenta certa, escreveu o nome dela na
    resposta e desistiu sem executá-la."""
    boa = ("FATO: R$ 122.656,48 de custo adicional.\nINFERÊNCIA: x\n"
           "RECOMENDAÇÃO: y\nFORÇA DA EVIDÊNCIA: MODERADA.")
    ag = AgenteMargem(mock=True, roteiro_mock=[
        DESISTE, DESISTE,
        'AÇÃO: simular_desconto_em_segmento\nPARÂMETROS: '
        '{"desconto_pct": "30", "canal": "Marketplace", "mes": "2023-11"}',
        boa], verbose=False)
    tr = ag.investigar("simule 30% de desconto no Marketplace em novembro")
    assert "simular_desconto_em_segmento" in tr.ferramentas_usadas
    assert validar_formato_final(tr.resposta_final)["valido"]


def test_cobranca_de_ferramenta_entrega_o_schema_de_parametros():
    """Só dizer 'chame a ferramenta' não bastou; a cobrança leva os parâmetros —
    e, quando a pergunta menciona canal, esse valor já vem preenchido."""
    ag = AgenteMargem(mock=True, roteiro_mock=[DESISTE] * 6, verbose=False)
    ag.investigar("o que explica a margem baixa no Marketplace?")
    todas = [m["content"] for ch in ag.llm.chamadas for m in ch]
    cobranca = [c for c in todas if "citou a(s) ferramenta" in c]
    assert cobranca
    assert "desconto_pct" in cobranca[0]
    assert "obrigatórios" in cobranca[0]
    assert '"canal": "Marketplace"' in cobranca[0]


def test_pergunta_roteada_nao_precisa_de_cobranca():
    """O outro lado da moeda: com o roteador resolvendo a simulação, a ferramenta
    já está executada quando o modelo fala pela primeira vez."""
    ag = AgenteMargem(mock=True, roteiro_mock=[DESISTE] * 6, verbose=False)
    tr = ag.investigar("simule 30% de desconto no Marketplace")
    assert "simular_desconto_em_segmento" in tr.ferramentas_usadas
    assert tr.roteamento["intencao"] == "APLICAR_DESCONTO"


def test_ferramenta_ja_chamada_nao_dispara_cobranca():
    """Citar uma ferramenta que FOI executada é legítimo — não pode acusar."""
    resposta = ("FATO: segundo margem_por_dimensao, o Marketplace tem 47,57%.\n"
                "INFERÊNCIA: x\nRECOMENDAÇÃO: y\nFORÇA DA EVIDÊNCIA: FORTE")
    ag = AgenteMargem(mock=True, roteiro_mock=[
        'AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}',
        ACAO_TESTE_ESTATISTICO, resposta],
        verbose=False)
    tr = ag.investigar("qual canal tem pior margem?")
    todas = [m["content"] for ch in ag.llm.chamadas for m in ch]
    assert not any("citou a(s) ferramenta" in c for c in todas)
    assert tr.resposta_final.startswith("FATO: segundo margem_por_dimensao")


def test_cobranca_de_ferramenta_acontece_uma_vez_so():
    """Se o modelo insistir em desistir, a resposta é aceita — senão o loop trava."""
    ag = AgenteMargem(mock=True, roteiro_mock=[DESISTE] * 8, max_iteracoes=6, verbose=False)
    tr = ag.investigar("simule 30% de desconto")
    cobrancas = [p for p in tr.passos if p.tipo == "pensamento"
                 and isinstance(p.conteudo, dict)
                 and "ferramentas_citadas_nao_chamadas" in p.conteudo]
    assert len(cobrancas) == 1
    assert validar_formato_final(tr.resposta_final)["valido"]


def test_deteccao_de_ferramenta_citada_e_exata():
    """Não pode casar nome parcial nem ferramenta já usada."""
    from vertice.agent.react import AgenteMargem as A
    from vertice.agent.trace import Trace
    tr = Trace(pergunta="x")
    tr.add("acao", None, ferramenta="margem_consolidada")
    achadas = A._ferramentas_citadas_nao_chamadas(
        "preciso de simular_teto_desconto e já usei margem_consolidada", tr)
    assert achadas == ["simular_teto_desconto"]
    assert A._ferramentas_citadas_nao_chamadas("nenhuma ferramenta aqui", tr) == []


# ------------------- roteamento por palavra-chave (reduz idas ao gateway)
@pytest.mark.parametrize("pergunta,esperada", [
    ("Simule o impacto de aplicar 30% de desconto no Marketplace em novembro",
     "simular_desconto_em_segmento"),
    ("O desconto está comprando volume incremental?", "tabela_faixas_desconto"),
    ("Quanto o Marketplace paga de frete a mais?", "politica_frete_por_canal"),
    ("Qual canal tem a pior margem?", "margem_por_dimensao"),
    ("Isso é estatisticamente significativo?", "teste_t_welch"),
    ("A queda em novembro é sazonalidade?", "indice_sazonalidade"),
    ("Qual o impacto das devoluções?", "impacto_devolucoes"),
])
def test_roteamento_sugere_a_ferramenta_certa(pergunta, esperada):
    from vertice.agent.prompts import sugerir_ferramentas
    assert esperada in sugerir_ferramentas(pergunta)


def test_roteamento_e_limitado_para_nao_diluir():
    from vertice.agent.prompts import MAX_SUGESTOES, sugerir_ferramentas
    p = "simule o impacto do frete e do desconto no Marketplace em novembro por canal"
    assert len(sugerir_ferramentas(p)) <= MAX_SUGESTOES


def test_roteamento_so_sugere_ferramentas_existentes():
    from vertice.agent.prompts import PISTAS
    from vertice.engine import REGISTRO
    for _, ferramentas in PISTAS:
        for f in ferramentas:
            assert f in REGISTRO, f"pista aponta para ferramenta inexistente: {f}"


def test_pergunta_generica_nao_recebe_sugestao():
    from vertice.agent.prompts import bloco_sugestoes, sugerir_ferramentas
    assert sugerir_ferramentas("me fale sobre a empresa") == []
    assert bloco_sugestoes("me fale sobre a empresa") == ""


def test_sugestoes_chegam_na_primeira_mensagem_do_modelo():
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK, RESPOSTA_OK], verbose=False)
    ag.investigar("Simule 30% de desconto no Marketplace em novembro")
    primeira = ag.llm.chamadas[0]
    assert any("simular_desconto_em_segmento" in m["content"] for m in primeira)
    # A sugestão não pode ser imperativa: a escolha continua do agente.
    assert any("apenas uma pista" in m["content"] for m in primeira)


# ---------------------------------------------------- modelo padrão (Sonnet)
def test_modelo_padrao_da_config_e_sonnet_nos_dois_papeis(monkeypatch):
    """claude-haiku-45 errava demais a seleção entre 20 ferramentas; o padrão
    do projeto passou a ser claude-sonnet-46 nos dois papéis.

    O teste limpa VERTICE_MODEL_STEP/FINAL e recarrega o módulo: o assunto aqui
    é o PADRÃO do projeto. Sem isso, quem exportou outro modelo no terminal
    (apontando o projeto para Groq ou Ollama, por exemplo) via a suíte quebrar
    por causa do próprio ambiente — falha que não diz nada sobre o código.
    """
    import importlib

    from vertice import config
    monkeypatch.delenv("VERTICE_MODEL_STEP", raising=False)
    monkeypatch.delenv("VERTICE_MODEL_FINAL", raising=False)
    padrao = importlib.reload(config)
    try:
        assert padrao.MODELO_INVESTIGACAO == "claude-sonnet-46"
        assert padrao.MODELO_SINTESE == "claude-sonnet-46"
    finally:
        importlib.reload(config)   # devolve o módulo ao ambiente real


def test_modelo_pode_ser_trocado_por_variavel_de_ambiente(monkeypatch):
    """O outro lado da mesma moeda: é essa variável que permite apontar o
    projeto para outro provedor sem tocar no código."""
    import importlib

    from vertice import config
    monkeypatch.setenv("VERTICE_MODEL_STEP", "openai/gpt-oss-120b")
    try:
        assert importlib.reload(config).MODELO_INVESTIGACAO == "openai/gpt-oss-120b"
    finally:
        monkeypatch.delenv("VERTICE_MODEL_STEP", raising=False)
        importlib.reload(config)


def test_cli_expoe_flag_de_modelo_sintese():
    from vertice.cli import main
    import argparse
    ap = argparse.ArgumentParser()
    # Verificação indireta: --modelo-sintese precisa ser aceito sem erro de parse.
    assert main(["--mock", "--silencioso", "--modelo", "claude-haiku-45",
                "--modelo-sintese", "claude-opus-47", "-p", "teste"]) == 0


def test_cli_banner_mostra_os_dois_modelos_quando_diferentes(capsys):
    from vertice.cli import main
    main(["--mock", "-p", "teste"])
    # -p encerra sem imprimir banner; usamos --ferramentas só para checar que a
    # combinação de flags não quebra e o agente é construído com os dois valores.
    from vertice.agent.react import AgenteMargem
    ag = AgenteMargem(mock=True, modelo="claude-haiku-45", modelo_sintese="claude-opus-47")
    assert ag.modelo == "claude-haiku-45"
    assert ag.modelo_sintese == "claude-opus-47"


# --------- parâmetro obrigatório ausente vira exemplo pronto (bug real) ---------
def test_typeerror_de_parametro_devolve_exemplo_pronto_na_primeira_falha():
    """Regressão de produção: o modelo chamou simular_desconto_em_segmento({})
    DUAS vezes seguidas (mesmo TypeError as duas), porque a mensagem só nomeava
    o parâmetro ausente sem mostrar como preenchê-lo. Agora o exemplo já vem
    pronto na 1ª falha — sem contexto de pergunta, ao menos o obrigatório."""
    from vertice.agent.react import AgenteMargem
    from vertice.agent.trace import Trace

    ag = AgenteMargem(mock=True, roteiro_mock=["x"], verbose=False)
    tr = Trace(pergunta="teste")
    obs = ag._chamar_ferramenta("simular_desconto_em_segmento", {}, tr, iteracao=1)
    assert '"desconto_pct":' in obs
    assert "AÇÃO: simular_desconto_em_segmento" in obs
    # Não é a mensagem de "ferramenta inexistente" (essa não se aplica aqui).
    assert "Você quis dizer" not in obs
    assert "não invente uma" not in obs


def test_typeerror_de_parametro_prepreenche_com_valores_da_pergunta():
    """Regressão da 2ª rodada: mesmo com o exemplo abstrato (<placeholder>), o
    modelo NÃO tentou de novo — foi direto tentar responder com número
    inventado. Com a pergunta original, o exemplo vem com valores REAIS, não
    <placeholder>: a única ação que resta ao modelo é copiar a linha inteira."""
    from vertice.agent.react import AgenteMargem
    from vertice.agent.trace import Trace

    ag = AgenteMargem(mock=True, roteiro_mock=["x"], verbose=False)
    tr = Trace(pergunta="teste")
    pergunta = ("Simule o impacto de aplicar 30% de desconto no Marketplace "
                "durante novembro: quanto isso reduziria a margem consolidada?")
    obs = ag._chamar_ferramenta("simular_desconto_em_segmento", {}, tr, iteracao=1,
                                pergunta=pergunta)
    assert 'PARÂMETROS: {"desconto_pct": "30", "canal": "Marketplace", "mes": "2023-11"}' in obs
    assert "<" not in obs.split("PARÂMETROS:")[1]  # nenhum placeholder sobrando
    # opcional e não mencionado na pergunta: omitido do EXEMPLO, não inventado.
    # (a asserção é sobre a linha de exemplo — o texto do erro pode citar o
    # recorte consultado na política vigente, e isso não é o exemplo)
    linha_exemplo = obs.split("PARÂMETROS:")[-1]
    assert "categoria" not in linha_exemplo


def test_valueerror_de_regra_de_negocio_nao_ganha_exemplo_de_parametro():
    """ValueError (ex: canal inválido) já lista as opções válidas dentro da
    própria mensagem — não precisa (nem deve) do bloco de exemplo genérico."""
    from vertice.agent.react import AgenteMargem
    from vertice.agent.trace import Trace

    ag = AgenteMargem(mock=True, roteiro_mock=["x"], verbose=False)
    tr = Trace(pergunta="teste")
    obs = ag._chamar_ferramenta("margem_por_dimensao", {"dimensao": "planeta"}, tr, iteracao=1)
    assert "dimensao inválida" in obs
    assert "obrigatórios:" not in obs  # não é o bloco de exemplo do TypeError


def test_agente_se_recupera_de_parametro_vazio_em_uma_so_tentativa():
    """Ponta a ponta: com o exemplo na 1ª falha, o modelo corrige na 2ª chamada
    (não precisa de duas falhas idênticas para reagir)."""
    roteiro = [
        'AÇÃO: simular_desconto_em_segmento\nPARÂMETROS: {}',
        'AÇÃO: simular_desconto_em_segmento\nPARÂMETROS: '
        '{"desconto_pct": "30", "canal": "Marketplace", "mes": "2023-11"}',
        RESPOSTA_OK,
    ]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("simule 30% de desconto no Marketplace em novembro")
    erros = [p for p in tr.passos if p.tipo == "erro" and p.ferramenta]
    assert len(erros) == 1, f"deveria corrigir após 1 falha, houve {len(erros)}"
    assert "simular_desconto_em_segmento" in tr.ferramentas_usadas
    assert validar_formato_final(tr.resposta_final)["valido"]


# --------------- seção duplicada no fim da resposta (achado ao revisar) ---------------
def test_secao_duplicada_apos_forca_da_evidencia_e_cortada():
    """Achado ao conferir uma resposta bem-sucedida de produção: a síntese
    escreveu um 2º 'RECOMENDAÇÃO:' depois de 'FORÇA DA EVIDÊNCIA:' — o contrato
    diz 'sem seção extra, sem texto após a última'. validar_formato_final()
    olha só a 1ª ocorrência de cada cabeçalho e não pegava isso; agora
    normalizar_formato_final() corta a duplicata antes de sair do agente."""
    from vertice.agent.react import normalizar_formato_final

    bruto = ("FATO: x.\nINFERÊNCIA: y.\nRECOMENDAÇÃO: primeira.\n"
             "FORÇA DA EVIDÊNCIA: FORTE, conteúdo legítimo até aqui.\n"
             "RECOMENDAÇÃO: segunda, essa é a duplicata a cortar.")
    out = normalizar_formato_final(bruto)
    assert out.endswith("conteúdo legítimo até aqui.")
    assert "segunda, essa é a duplicata" not in out
    assert validar_formato_final(out)["valido"]


def test_sem_secao_duplicada_nao_corta_nada():
    boa = RESPOSTA_OK
    from vertice.agent.react import normalizar_formato_final
    assert normalizar_formato_final(boa) == boa


def test_corte_de_duplicata_nao_afeta_conteudo_legitimo_apos_forca():
    """FORÇA DA EVIDÊNCIA pode ter várias linhas de conteúdo real — só corta
    se um cabeçalho de seção reaparecer, não no primeiro parágrafo depois."""
    from vertice.agent.react import normalizar_formato_final

    bruto = ("FATO: x.\nINFERÊNCIA: y.\nRECOMENDAÇÃO: z.\n"
             "FORÇA DA EVIDÊNCIA: alta.\nMais uma linha de limitação, sem "
             "cabeçalho novo, que precisa sobreviver ao corte.")
    out = normalizar_formato_final(bruto)
    assert out.endswith("precisa sobreviver ao corte.")


def test_resposta_incompleta_nao_e_alterada_pelo_corte():
    """Sem FORÇA DA EVIDÊNCIA, não há o que cortar — devolve como veio, para o
    validador (não este código) sinalizar o formato incompleto."""
    from vertice.agent.react import normalizar_formato_final

    incompleta = "FATO: x.\nINFERÊNCIA: y."
    assert normalizar_formato_final(incompleta) == incompleta


# --------------------------------------------------- "AÇÃO: Chamar X" (bug real)
@pytest.mark.parametrize("texto,esperado", [
    ('AÇÃO: Chamar indice_sazonalidade e tendencia_ajustada_sazonalidade '
     'para verificar a tendência.\nPARÂMETROS: {}', "indice_sazonalidade"),
    ('AÇÃO: Chamar a ferramenta indice_sazonalidade\nPARÂMETROS: {}', "indice_sazonalidade"),
    ('AÇÃO: Usar tendencia_ajustada_sazonalidade e depois indice_sazonalidade\n'
     'PARÂMETROS: {"metrica": "margem_pct"}', "tendencia_ajustada_sazonalidade"),
])
def test_parser_recupera_nome_real_quando_prefixado_por_verbo(texto, esperado):
    """Regressão de produção: 'AÇÃO: Chamar indice_sazonalidade' foi lido como
    a ferramenta 'Chamar' (inexistente). Agora procura, na mesma linha, o
    primeiro nome real do registro e usa esse."""
    f, _, _ = extrair_acao(texto)
    assert f == esperado


def test_parser_nao_inventa_ferramenta_quando_nao_ha_nome_real_na_linha():
    """Sem nenhum nome real na linha, continua caindo no erro normal — não
    tenta adivinhar."""
    f, _, _ = extrair_acao("AÇÃO: Chamar alguma coisa que não existe\nPARÂMETROS: {}")
    assert f == "Chamar"  # extração ingênua preservada; vira KeyError normal depois


def test_parser_recupera_nome_do_pensamento_quando_acao_vem_vazia():
    """Regressão de produção: o modelo escreveu 'AÇÃO: Chamar()' vazio e só
    citou o nome real da ferramenta na linha de PENSAMENTO, uma linha acima —
    a busca na MESMA linha da AÇÃO não encontrava nada e virava
    KeyError("Ferramenta 'Chamar' não existe"). Usa o ÚLTIMO nome citado no
    PENSAMENTO (mais perto da decisão)."""
    texto = ("PENSAMENTO: Preciso investigar sazonalidade. Vou chamar "
              "indice_sazonalidade\ne tendencia_ajustada_sazonalidade para "
              "confirmar se é mudança estrutural.\n\nAÇÃO: Chamar()\nPARÂMETROS: {}")
    f, _, _ = extrair_acao(texto)
    assert f == "tendencia_ajustada_sazonalidade"


def test_parser_recupera_nome_citado_depois_da_acao():
    """Regressão de produção: 'AÇÃO: Refazer()' seguido de um parênteses
    explicativo DEPOIS da linha da AÇÃO, citando o nome real. Sem nome nem na
    mesma linha nem no PENSAMENTO, cai no resto do texto após a AÇÃO."""
    texto = ("AÇÃO: Refazer()\nPARÂMETROS: {}\n\n"
              "(preciso rodar margem_por_dimensao de novo com o parâmetro certo)")
    f, _, _ = extrair_acao(texto)
    assert f == "margem_por_dimensao"


def test_agente_recupera_de_acao_vazia_com_nome_no_pensamento_ponta_a_ponta():
    """Cenário real ponta a ponta: 'AÇÃO: Chamar()' vazio com o nome real só
    no PENSAMENTO não deve mais gerar KeyError nem consumir uma rodada."""
    roteiro = [
        ("PENSAMENTO: preciso rodar margem_por_dimensao para abrir por canal.\n"
         'AÇÃO: Chamar()\nPARÂMETROS: {"dimensao": "canal"}'),
        RESPOSTA_OK,
    ]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    trace = ag.investigar("Qual canal tem a pior margem?")
    assert "margem_por_dimensao" in trace.ferramentas_usadas
    assert not any(p.tipo == "erro" and "não existe" in str(p.conteudo)
                   for p in trace.passos)


def test_agente_recupera_do_verbo_prefixado_ponta_a_ponta():
    """Simula o cenário real: o modelo escreve 'Chamar X e Y', o parser recupera
    X, e a investigação segue sem cair em erro de ferramenta inexistente."""
    roteiro = [
        'AÇÃO: Chamar indice_sazonalidade e tendencia_ajustada_sazonalidade\nPARÂMETROS: {}',
        RESPOSTA_OK,
    ]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("a queda em novembro é sazonal ou estrutural?")
    assert "indice_sazonalidade" in tr.ferramentas_usadas
    assert not any(p.tipo == "erro" and "não existe" in str(p.conteudo) for p in tr.passos)


# ------------------------------- vocabulário fechado de FORÇA DA EVIDÊNCIA
@pytest.mark.parametrize("palavra,esperado", [
    ("FORTE", True), ("MODERADA", True), ("FRACA", True),
    ("forte (p<0,001)", True),  # minúscula + contexto extra
    ("Alta", False), ("Baixa", False), ("Confiável", False), ("alta confiança", False),
])
def test_validador_exige_vocabulario_fechado_em_forca_da_evidencia(palavra, esperado):
    """vocabulario_evidencia_ok é informativo, não trava `valido` — ver
    docstring de validar_formato_final(). As 4 seções presentes e em ordem
    já bastam para `valido`; a palavra errada é tratada à parte, no loop."""
    resposta = f"FATO: x.\nINFERÊNCIA: y.\nRECOMENDAÇÃO: z.\nFORÇA DA EVIDÊNCIA: {palavra}."
    r = validar_formato_final(resposta)
    assert r["vocabulario_evidencia_ok"] is esperado
    assert r["valido"] is True


def test_secao_faltante_nao_e_confundida_com_vocabulario_errado():
    """Sem a seção, vocabulario_evidencia_ok fica True (não avaliado) — quem
    reporta o problema é 'faltando', não o vocabulário."""
    r = validar_formato_final("FATO: x.\nINFERÊNCIA: y.")
    assert r["vocabulario_evidencia_ok"] is True
    assert not r["valido"]
    assert "FORÇA DA EVIDÊNCIA" in r["faltando"]


def test_agente_cobra_vocabulario_errado_e_aceita_a_correcao():
    """Regressão de produção: o modelo escreveu 'Alta' em vez de FORTE/MODERADA
    /FRACA. Deve ser cobrado — e aceitar quando ele reescreve certo."""
    roteiro = [
        'AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}',
        ACAO_TESTE_ESTATISTICO,  # já satisfaz a exigência de teste real, à parte
        ("FATO: x.\nINFERÊNCIA: y.\nRECOMENDAÇÃO: z.\n"
         "FORÇA DA EVIDÊNCIA: Alta para classificação."),
        RESPOSTA_OK,
    ]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("teste")
    assert tr.resposta_final.rstrip().endswith("FORTE (p<0,001, n=24.454).")
    todas = [m["content"] for ch in ag.llm.chamadas for m in ch]
    assert any("FORTE, MODERADA ou FRACA" in c for c in todas)


def test_agente_forca_fraca_se_vocabulario_continuar_errado():
    """Diferente de número inventado, vocabulário fora do padrão NÃO bloqueia
    a resposta inteira — mas também não fica do jeito que veio: depois de 1
    cobrança, se a 2ª tentativa ainda usar palavra fora de FORTE/MODERADA/
    FRACA (ex.: "Alta"), o código força FRACA deterministicamente, com nota
    auditável, em vez de publicar a palavra errada como estava.

    Regressão real de produção (via API web): "Alta" e "NULA" chegaram como
    resposta final sem correção nenhuma, porque a versão antiga só cobrava
    1x e tolerava — sem reescrever nada — se persistisse."""
    persistente = ("FATO: x.\nINFERÊNCIA: y.\nRECOMENDAÇÃO: z.\n"
                   "FORÇA DA EVIDÊNCIA: Alta, mesmo depois da cobrança.")
    roteiro = [
        'AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}',
        persistente, persistente,
    ]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("teste")
    assert "bloqueada" not in tr.resposta_final
    assert "não foi possível sintetizar" not in tr.resposta_final.lower()
    assert tr.resposta_final.startswith("FATO: x.")
    assert "FORÇA DA EVIDÊNCIA: FRACA" in tr.resposta_final
    assert "normalizado automaticamente de 'Alta' para FRACA" in tr.resposta_final
    assert ", mesmo depois da cobrança." in tr.resposta_final  # resto do texto preservado


def test_agente_forca_fraca_para_palavra_sem_nenhum_overlap_com_vocabulario():
    """Caso mais extremo que 'Alta': "NULA" não compartilha nenhuma letra em
    comum de peso com FORTE/MODERADA/FRACA — confirma que a normalização não
    depende de a palavra errada "parecer" com a certa."""
    persistente = ("FATO: x.\nINFERÊNCIA: y.\nRECOMENDAÇÃO: z.\n"
                   "FORÇA DA EVIDÊNCIA: NULA")
    roteiro = [
        'AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}',
        persistente, persistente,
    ]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("teste")
    assert "FORÇA DA EVIDÊNCIA: FRACA" in tr.resposta_final
    assert "normalizado automaticamente de 'NULA' para FRACA" in tr.resposta_final


def test_cobranca_de_vocabulario_e_numeros_nao_se_confundem():
    """As duas cobranças (números e vocabulário) são independentes: uma
    resposta com número inventado é pega primeiro, antes de chegar a avaliar
    o vocabulário da seção final. (O texto "FORTE, MODERADA ou FRACA" já
    aparece no system prompt estático — o teste procura o texto específico
    da cobrança de vocabulário, não essa frase genérica.)"""
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_INVENTADA] * 6, verbose=False)
    tr = ag.investigar("teste")
    todas = [m["content"] for ch in ag.llm.chamadas for m in ch]
    assert any("NÃO apareceram em nenhum resultado de ferramenta" in c for c in todas)
    assert not any("Reescreva a resposta final inteira" in c for c in todas)


# ------------------- FORTE/MODERADA exige teste estatístico (achado real) ---
def test_forte_sem_teste_estatistico_e_cobrado():
    """Regressão de produção: o modelo rotulou 'FORTE' uma conclusão de mudança
    estrutural usando só indice_sazonalidade (descritivo, não teste de
    significância) — nunca chamou tendencia_ajustada_sazonalidade."""
    roteiro = [
        'AÇÃO: indice_sazonalidade\nPARÂMETROS: {}',
        ("FATO: novembro é pico sazonal com margem mais baixa.\n"
         "INFERÊNCIA: mudança estrutural.\nRECOMENDAÇÃO: investigar.\n"
         "FORÇA DA EVIDÊNCIA: FORTE — série completa de 13 meses analisada."),
        RESPOSTA_OK,  # aceito na 2ª, já rebaixado
    ]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("a queda em novembro é sazonal ou estrutural?")
    todas = [m["content"] for ch in ag.llm.chamadas for m in ch]
    assert any("NENHUMA ferramenta estatística foi chamada" in c for c in todas)
    assert any("tendencia_ajustada_sazonalidade" in c for c in todas)


def test_forte_sem_teste_e_rebaixado_para_fraca_se_persistir():
    """Se o modelo insistir em FORTE sem nunca chamar um teste, a resposta é
    aceita mas com a palavra corrigida — não bloqueada feito número inventado
    (a diferença: aqui é possível corrigir deterministicamente, sem palpite)."""
    persiste = ("FATO: novembro é pico sazonal com margem mais baixa.\n"
                "INFERÊNCIA: mudança estrutural.\nRECOMENDAÇÃO: investigar.\n"
                "FORÇA DA EVIDÊNCIA: FORTE — série completa analisada.")
    roteiro = ['AÇÃO: indice_sazonalidade\nPARÂMETROS: {}', persiste, persiste]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("teste")
    assert "bloqueada" not in tr.resposta_final
    assert "não foi possível sintetizar" not in tr.resposta_final.lower()
    assert "FORÇA DA EVIDÊNCIA: FRACA" in tr.resposta_final
    assert "rebaixado automaticamente de FORTE" in tr.resposta_final
    assert tr.resposta_final.startswith("FATO: novembro é pico sazonal")


def test_forte_com_teste_estatistico_real_passa_direto():
    """Quando um teste estatístico FOI chamado, FORTE não é questionado."""
    roteiro = [
        'AÇÃO: tendencia_ajustada_sazonalidade\nPARÂMETROS: {"metrica": "margem_pct"}',
        RESPOSTA_OK,
    ]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("teste")
    assert tr.resposta_final.rstrip().endswith("FORTE (p<0,001, n=24.454).")
    todas = [m["content"] for ch in ag.llm.chamadas for m in ch]
    assert not any("NENHUMA ferramenta estatística foi chamada" in c for c in todas)


def test_fraca_nao_exige_teste_estatistico():
    """FRACA é sempre uma classificação segura de fazer sem teste — não deveria
    disparar a cobrança (só FORTE/MODERADA fazem uma alegação de confiança)."""
    fraca = ("FATO: x.\nINFERÊNCIA: y.\nRECOMENDAÇÃO: z.\n"
             "FORÇA DA EVIDÊNCIA: FRACA — dado insuficiente para mais.")
    ag = AgenteMargem(mock=True, roteiro_mock=[
        'AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}', fraca], verbose=False)
    tr = ag.investigar("teste")
    todas = [m["content"] for ch in ag.llm.chamadas for m in ch]
    assert not any("NENHUMA ferramenta estatística foi chamada" in c for c in todas)
    assert tr.resposta_final.endswith("FRACA — dado insuficiente para mais.")


def test_forca_alegada_le_a_secao_certa():
    from vertice.agent.react import _forca_alegada
    assert _forca_alegada("FATO: x.\nFORÇA DA EVIDÊNCIA: MODERADA (p<0,05).") == "MODERADA"
    assert _forca_alegada("FATO: x.\nINFERÊNCIA: y.") is None  # seção ausente


def test_rebaixar_forca_preserva_texto_anterior_a_secao():
    from vertice.agent.react import _rebaixar_forca_para_fraca
    texto = "FATO: x.\nINFERÊNCIA: y.\nRECOMENDAÇÃO: z.\nFORÇA DA EVIDÊNCIA: FORTE."
    out = _rebaixar_forca_para_fraca(texto, "FORTE")
    assert out.startswith("FATO: x.\nINFERÊNCIA: y.\nRECOMENDAÇÃO: z.\n")
    assert "FORÇA DA EVIDÊNCIA: FRACA" in out
    assert "FORTE" not in out.split("FORÇA DA EVIDÊNCIA:")[1].split("[rebaixado")[0]


# --------------------------------------- número com sinal trocado (achado real)
def test_verificacao_aceita_magnitude_de_numero_negativo():
    """Regressão de produção: a ferramenta devolveu variacao_pp=-22.17, o texto
    disse apenas '22,17' (a direção já vem do verbo 'caiu') — falso positivo
    real na verificação numérica antes desta correção."""
    from vertice.agent.verificacao import verificar_numeros
    r = verificar_numeros("FATO: a margem caiu 22,17 pontos percentuais.",
                          {-22.17, 47.01, 24.84}, "")
    assert r["ok"], r["suspeitos"]


def test_verificacao_ainda_rejeita_magnitude_sem_correspondente_real():
    from vertice.agent.verificacao import verificar_numeros
    r = verificar_numeros("FATO: a margem caiu 99,99 pontos percentuais.",
                          {-22.17, 47.01, 24.84}, "")
    assert not r["ok"]
    assert "99,99" in r["suspeitos"]


# --------------------------------------- content vazio quebra o gateway (bug real)
class _LLMRoteiroCru:
    """Fake LLM que devolve exatamente os textos do roteiro (sem RESPOSTA_OK de
    fallback) e grava toda mensagem enviada, para inspecionar content vazio."""

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.mensagens_enviadas: list[dict] = []

    def completar(self, mensagens, modelo, tools=None):
        self.mensagens_enviadas.extend(dict(m) for m in mensagens)
        texto = self.roteiro.pop(0) if self.roteiro else RESPOSTA_OK

        class _Msg:
            pass
        m = _Msg()
        m.content = texto
        m.tool_calls = None
        return m


def test_resposta_vazia_do_modelo_nunca_vira_content_vazio_na_proxima_chamada():
    """Regressão de produção: o modelo devolveu uma resposta em branco (só
    espaço) — nem AÇÃO nem FATO casaram — e o código ecoava content="" de
    volta na próxima mensagem. A EloAgents/Bedrock rejeitou com 400
    'Value null at messages.N.member.content: Member must not be null' (o
    gateway normaliza string vazia para null). Content vazio nunca pode ser
    enviado de volta ao gateway."""
    roteiro = ['AÇÃO: margem_por_dimensao\nPARÂMETROS: {"dimensao": "canal"}',
               "   ",  # resposta em branco do modelo
               RESPOSTA_OK]
    fake = _LLMRoteiroCru(roteiro)
    ag = AgenteMargem(llm=fake, verbose=False)
    ag.investigar("O desconto está comprando volume incremental?")
    vazios = [m for m in fake.mensagens_enviadas if m["content"] == ""]
    assert not vazios, f"mensagem com content vazio enviada ao gateway: {vazios}"


def test_sintese_forcada_com_primeira_tentativa_vazia_nao_envia_content_vazio():
    """Mesmo bug, no caminho de _forcar_sintese: se a 1ª tentativa de síntese
    vem vazia, o eco dela na 2ª tentativa não pode ser content=""."""
    roteiro = ["AÇÃO: margem_consolidada\nPARÂMETROS: {}"] * 20 + ["", RESPOSTA_OK]
    fake = _LLMRoteiroCru(roteiro)
    ag = AgenteMargem(llm=fake, max_iteracoes=20, verbose=False)
    ag.investigar("Por que a margem caiu?")
    vazios = [m for m in fake.mensagens_enviadas if m["content"] == ""]
    assert not vazios, f"mensagem com content vazio enviada ao gateway: {vazios}"


# ------------------------------------- origem da consulta (ad_hoc x agendada)
def test_investigacao_normal_registra_origem_ad_hoc():
    """O caso de uso é gestor revisando política periodicamente, não vendedor
    pedindo aprovação em tempo real. Sem esse campo, o consumidor do trace
    (painel, auditoria) não consegue separar os dois."""
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    tr = ag.investigar("teste")
    assert tr.origem_consulta == "ad_hoc"
    assert tr.to_dict()["origem_consulta"] == "ad_hoc"


def test_investigacao_agendada_registra_revisao_periodica():
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    tr = ag.investigar("teste", origem_consulta="revisao_periodica")
    assert tr.origem_consulta == "revisao_periodica"
    assert tr.to_dict()["origem_consulta"] == "revisao_periodica"


def test_origem_de_consulta_invalida_e_rejeitada():
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    with pytest.raises(ValueError, match="origem_consulta inválida"):
        ag.investigar("teste", origem_consulta="qualquer_coisa")


def test_origem_de_consulta_sobrevive_ao_json_do_trace():
    import json
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    tr = ag.investigar("teste", origem_consulta="revisao_periodica")
    assert json.loads(tr.to_json())["origem_consulta"] == "revisao_periodica"


def test_grau_de_duas_palavras_nao_deixa_sobra_no_texto():
    """Regressão de leitura: "Muito Baixa" virava "FRACA Baixa" porque só a
    primeira palavra era substituída."""
    from vertice.agent.react import (_forcar_vocabulario_fechado,
                                     _palavra_alegada_fora_do_vocabulario)
    texto = ("FATO: x\nINFERÊNCIA: y\nRECOMENDAÇÃO: z\n"
             "FORÇA DA EVIDÊNCIA: Muito Baixa para a simulação específica.")
    palavra = _palavra_alegada_fora_do_vocabulario(texto)
    saida = _forcar_vocabulario_fechado(texto, palavra)
    assert "FRACA para a simulação" in saida
    assert "Baixa" not in saida.split("FORÇA DA EVIDÊNCIA:")[1].split("[")[0]
    assert "normalizado automaticamente" in saida   # continua auditável


# ------------------- números agrupados por espaço (falso positivo real)
def test_numero_com_espaco_de_milhar_nao_e_acusado_de_inventado():
    """Regressão de produção: um modelo que escreve "R$ 34 973,55" (espaço como
    separador de milhar) fazia a verificação capturar só "973,55" e acusar cinco
    números CORRETOS de terem sido inventados. Eram os finais de 34.973,55,
    21.162,40, 13.811,15, 9.058.427,55 e 9.072.238,70."""
    from vertice.agent.verificacao import verificar_numeros
    resposta = ("FATO: o desconto do grupo cai de R$ 34 973,55 para R$ 21 162,40, "
                "recuperando R$ 13 811,15 de margem; a consolidada vai de "
                "R$ 9 058 427,55 para R$ 9 072 238,70.")
    numeros = {34973.55, 21162.40, 13811.15, 9058427.55, 9072238.70}
    v = verificar_numeros(resposta, numeros)
    assert v["ok"], v["suspeitos"]
    assert v["numeros_verificados"] == 5


def test_espaco_estreito_nao_quebravel_tambem_conta_como_milhar():
    from vertice.agent.verificacao import verificar_numeros
    assert verificar_numeros("FATO: R$ 34 973,55.", {34973.55})["ok"]
    assert verificar_numeros("FATO: R$ 34 973,55.", {34973.55})["ok"]


def test_numero_inventado_com_espaco_continua_sendo_barrado():
    """A tolerância não pode virar um buraco: 99 999,99 não veio de ferramenta."""
    from vertice.agent.verificacao import verificar_numeros
    v = verificar_numeros("FATO: economia de R$ 99 999,99.", {34973.55})
    assert not v["ok"]
    assert "99 999,99" in v["suspeitos"]


def test_dois_numeros_separados_por_espaco_nao_sao_colados_indevidamente():
    """"166 dos 843" são dois números; só o agrupamento de 3 dígitos junta."""
    from vertice.agent.verificacao import RE_NUMERO
    assert RE_NUMERO.findall("166 dos 843 pedidos") == ["166", "843"]


def test_numero_inventado_escrito_com_espaco_nao_passa_pela_verificacao():
    """Buraco grave e real: um modelo inventou a tabela inteira de faixas de
    desconto escrevendo "R$ 9 820 000". Com o extrator antigo o número virava
    ["9","820","000"] — todos abaixo do mínimo de dígitos — e a verificação nem
    olhava. Depois, tratar as partes como leituras alternativas manteve o buraco:
    o "0" casava com qualquer resultado de ferramenta.
    """
    from vertice.agent.verificacao import coletar_numeros, verificar_numeros
    from vertice.engine import executar

    conhecidos = coletar_numeros(executar("tabela_faixas_desconto"))
    inventada = ("FATO: faixa 0% margem 52,3% (R$ 9 820 000); "
                 "faixa 30%+ margem 27,5% (R$ 1 210 000).")
    v = verificar_numeros(inventada, conhecidos)
    assert not v["ok"]
    assert "9 820 000" in v["suspeitos"] and "1 210 000" in v["suspeitos"]


def test_dois_numeros_reais_colados_por_espaco_continuam_aceitos():
    """A regra dura não pode acusar "166 dos 843": o espaço colou dois números
    que vieram de ferramenta. Aceita só quando TODAS as partes são conhecidas."""
    from vertice.agent.verificacao import verificar_numeros
    assert verificar_numeros("FATO: 1 234 e 5 678 pedidos.", {1234.0, 5678.0})["ok"]
    # uma parte desconhecida já basta para acusar
    assert not verificar_numeros("FATO: 1 234 e 9 999 pedidos.", {1234.0, 5678.0})["ok"]


def test_numero_inventado_na_sintese_final_tambem_e_bloqueado():
    """A guarda numérica rodava só DENTRO do loop. Esgotadas as iterações, o
    texto de _forcar_sintese ia direto para publicação, sem checagem — um número
    inventado ali saía como se fosse apuração. Reproduzido com MAX_ITER baixo,
    mas alcançável em qualquer investigação longa."""
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_INVENTADA] * 8,
                      max_iteracoes=2, verbose=False)
    tr = ag.investigar("simule 30% de desconto no Marketplace em novembro")
    assert "bloqueada por falha de rastreabilidade" in tr.resposta_final
    assert validar_formato_final(tr.resposta_final)["valido"]
    # O número aparece, mas DENUNCIADO — nunca afirmado. É essa a diferença
    # entre publicar um valor inventado e mostrar qual valor foi recusado.
    assert "NÃO apareceram em nenhum resultado de ferramenta" in tr.resposta_final
    assert "5.435.707,15" in tr.resposta_final.split("NÃO apareceram")[1]
    assert "Nova margem" not in tr.resposta_final       # a afirmação original não vaza


def test_resposta_legitima_nao_e_bloqueada_pela_checagem_final():
    """A porta nova não pode acusar resposta boa: os números de RESPOSTA_FRETE
    vêm de custo_assimetria_frete, chamada no roteiro."""
    roteiro = ['AÇÃO: custo_assimetria_frete\nPARÂMETROS: {"canal": "Marketplace"}',
               "FATO: o Marketplace paga R$ 172.828,86 de frete, dos quais "
               "R$ 135.256,57 são evitáveis.\nINFERÊNCIA: é política, não custo.\n"
               "RECOMENDAÇÃO: equalizar.\nFORÇA DA EVIDÊNCIA: FRACA"]
    ag = AgenteMargem(mock=True, roteiro_mock=roteiro, verbose=False)
    tr = ag.investigar("qual o impacto do frete no Marketplace?")
    assert "bloqueada" not in tr.resposta_final
    assert "172.828,86" in tr.resposta_final


def test_fallback_do_sistema_nao_acusa_a_si_mesmo():
    """O texto do fallback cita números do trace; reverificá-lo o faria acusar
    a própria resposta e cair em loop de bloqueio."""
    from vertice.agent.react import AgenteMargem as _Ag
    for texto in ("FATO: resposta bloqueada por falha de rastreabilidade numérica.",
                  "INFERÊNCIA: não foi possível sintetizar uma conclusão.",
                  "INFERÊNCIA: a leitura interpretativa não pôde ser redigida — x."):
        assert _Ag._veio_do_fallback(texto)
    assert not _Ag._veio_do_fallback("FATO: margem de 49,99%.")


# ------------------------------------------ limiar não é medida (falso positivo)
def test_limiar_de_significancia_nao_e_tratado_como_numero_inventado():
    """"p<0,001" declara um LIMITE, não afirma uma medida: o 0,001 não precisa
    existir em ferramenta nenhuma. Exigir isso rejeitava resposta correta que usa
    a notação convencional de significância."""
    from vertice.agent.verificacao import verificar_numeros
    v = verificar_numeros("FATO: margem de 49,99%.\nFORÇA DA EVIDÊNCIA: FORTE "
                          "(p<0,001, n>1.000).", {49.99})
    assert v["ok"]
    assert v["limiares_ignorados"] == 2


def test_p_valor_afirmado_como_medida_continua_sendo_verificado():
    """Buraco real: o modelo escreveu "ANOVA retornou p-valor = 0,00002" sem ter
    executado ANOVA nenhuma. A tolerância tinha piso absoluto de 0,02, então
    qualquer valor abaixo disso casava com o 0.0 que todo resultado de ferramenta
    contém — um p-valor inventado sempre passava."""
    from vertice.agent.verificacao import verificar_numeros
    v = verificar_numeros("FATO: a ANOVA retornou p-valor = 0,00002.", {0.0, 49.99, 24454.0})
    assert not v["ok"]
    assert "0,00002" in v["suspeitos"]


def test_p_valor_real_minusculo_continua_passando():
    """O p de verdade desta base é 2,8e-81, que o modelo escreve como 0,00000."""
    from vertice.agent.verificacao import coletar_numeros, verificar_numeros
    from vertice.engine import executar
    reais = coletar_numeros(executar("anova_um_fator",
                                     {"metrica": "margem_contribuicao",
                                      "coluna_grupo": "canal"}))
    assert verificar_numeros("FATO: F = 65,6288 e eta quadrado = 0,0159.", reais)["ok"]


def test_historico_longo_nao_vai_inteiro_para_o_modelo():
    """Sem corte, cada pergunta carregava a conversa inteira e o pedido crescia
    até o provedor recusar por tamanho: a 1ª pergunta da sessão funcionava e as
    seguintes falhavam com 413."""
    ag = AgenteMargem(mock=True, roteiro_mock=[RESPOSTA_OK], verbose=False)
    ag.historico = [{"role": "user", "content": f"antiga {i}"} for i in range(30)]
    enviadas = []

    class _Espiao:
        def completar(self, msgs, *a, **k):
            enviadas.append(sum(1 for m in msgs if m["content"].startswith("antiga")))
            raise RuntimeError("interrompe aqui")

    ag.llm = _Espiao()
    ag.investigar("pergunta nova")
    from vertice import config
    assert enviadas[0] == config.max_mensagens_historico() == 6


def test_fallback_sem_modelo_mostra_as_linhas_da_tabela():
    """Listas eram descartadas inteiras no resumo: "qual canal tem menor margem?"
    saía como "dimensao = canal; n grupos = 7" — verdadeiro e inútil."""
    class _Fora:
        def completar(self, *a, **k):
            raise RuntimeError("413 Request too large")

    ag = AgenteMargem(mock=True, verbose=False)
    ag.llm = _Fora()
    resposta = ag.investigar("Qual canal tem menor margem?").resposta_final
    assert "Marketplace" in resposta and "47.57" in resposta
    assert "Email Marketing" in resposta
    # e sem despejar as treze colunas de cada canal
    assert "custo_produto" not in resposta


# ------------------- provedor recusa por tamanho: encolher e tentar de novo
ERRO_413 = ("Error code: 413 - {'error': {'message': 'Request too large for model "
            "`openai/gpt-oss-120b` on tokens per minute (TPM): Limit 8000, "
            "Requested 9412, please reduce your message size.'}}")


class _ProvedorComTeto:
    """Recusa pedidos acima de `teto` caracteres, como camada gratuita faz."""

    def __init__(self, teto=30000, resposta=None):
        self.teto, self.tentativas = teto, []
        self.resposta = resposta or ("FATO: 166 de 843 pedidos acima do teto.\n"
                                     "INFERÊNCIA: x.\nRECOMENDAÇÃO: y.\n"
                                     "FORÇA DA EVIDÊNCIA: FRACA")

    def completar(self, msgs, *a, **k):
        self.tentativas.append(msgs)
        if sum(len(m["content"]) for m in msgs) > self.teto:
            raise RuntimeError(ERRO_413)
        return type("M", (), {"content": self.resposta, "tool_calls": None})()


def _agente_com_historico_grande(provedor):
    ag = AgenteMargem(mock=True, verbose=False)
    ag.llm = provedor
    ag.historico = [{"role": "user", "content": "antiga " * 400},
                    {"role": "assistant", "content": "resposta " * 400}] * 3
    return ag


def test_pedido_grande_demais_e_reenviado_menor_em_vez_de_falhar():
    """A camada gratuita da Groq recusava toda pergunta a partir da segunda da
    sessão. O teto varia por conta, então calibrar por variável de ambiente
    exigiria adivinhar o número: o sistema encolhe sozinho e tenta de novo."""
    p = _ProvedorComTeto()
    tr = _agente_com_historico_grande(p).investigar(
        "O que acontece se eu limitar Moda no Email Marketing a 17%?")

    assert len(p.tentativas) == 2
    tam = [sum(len(m["content"]) for m in t) for t in p.tentativas]
    assert tam[1] < tam[0] / 2
    assert "FATO:" in tr.resposta_final
    assert "não pôde ser redigida" not in tr.resposta_final   # não caiu no fallback
    reducoes = [p for p in tr.passos if p.tipo == "pensamento"
                and isinstance(p.conteudo, dict) and "pedido_reduzido" in p.conteudo]
    assert len(reducoes) == 1


def test_o_resultado_da_ferramenta_sobrevive_ao_encolhimento():
    """O que encolhe é catálogo e histórico. O resultado da ferramenta da
    pergunta atual NUNCA some: é dele que sai o número da resposta."""
    p = _ProvedorComTeto()
    _agente_com_historico_grande(p).investigar(
        "O que acontece se eu limitar Moda no Email Marketing a 17%?")

    segunda = " ".join(m["content"] for m in p.tentativas[1])
    assert "simular_teto_desconto" in segunda
    assert "8590.02" in segunda or "8.590,02" in segunda   # a contribuição preservada
    assert "591" in segunda


def test_erro_que_nao_e_de_tamanho_nao_dispara_retentativa():
    """Orçamento estourado ou chave inválida não melhoram com pedido menor:
    vão direto para a resposta determinística."""
    class _SemOrcamento:
        def __init__(self): self.n = 0
        def completar(self, *a, **k):
            self.n += 1
            raise RuntimeError("Error code: 400 - Budget exceeded: 20.05 >= 20.00")

    ag = AgenteMargem(mock=True, verbose=False)
    ag.llm = p = _SemOrcamento()
    tr = ag.investigar("O que acontece se eu limitar Moda no Email Marketing a 17%?")
    assert p.n == 1                                    # uma tentativa só
    assert "não pôde ser redigida" in tr.resposta_final
    assert "8.590,02" in tr.resposta_final             # e os números vêm junto


def test_mensagem_do_provedor_nao_corta_o_limite_informado():
    """Cortar em 160 caracteres escondia o fim da mensagem — que é onde vem
    "Limit 8000, Requested 9412", o número que diz o quanto encolher."""
    from vertice.agent.react import _erro_curto
    curto = _erro_curto(f"RuntimeError: {ERRO_413}")
    assert "Limit 8000" in curto and "Requested 9412" in curto


ERRO_FERRAMENTA_INDEVIDA = (
    "Error code: 400 - {'error': {'message': 'Tool choice is none, but model called "
    "a tool', 'type': 'invalid_request_error', 'code': 'tool_use_failed', "
    "'failed_generation': '{\"name\": \"tabela_faixas_desconto\", \"arguments\": "
    "PENSAMENTO: obter distribuição de desconto por faixa\\nAÇÃO: "
    "tabela_faixas_desconto\\nPARÂMETROS: {}}'}}")


def test_modelo_que_exige_function_calling_recebe_as_ferramentas():
    """A chamada recusada vinha CORRETA: nome e parâmetros válidos. O gpt-oss é
    treinado para function calling — insistir em texto é remar contra. A resposta
    certa é ligar as ferramentas nativas e deixá-lo trabalhar como sabe."""
    class _ExigeFerramentas:
        def __init__(self): self.chamadas = []

        def completar(self, msgs, modelo, tools=None):
            self.chamadas.append(bool(tools))
            if tools is None:
                raise RuntimeError(ERRO_FERRAMENTA_INDEVIDA)
            if any("Ferramenta: margem_por_dimensao" in m["content"] for m in msgs):
                return type("M", (), {"content": RESPOSTA_OK, "tool_calls": None})()
            tc = type("TC", (), {"function": type("F", (), {
                "name": "tool_margem_por_dimensao",       # com prefixo, como a Groq manda
                "arguments": '{"dimensao": "categoria"}'})()})()
            return type("M", (), {"content": "", "tool_calls": [tc]})()

    ag = AgenteMargem(mock=True, verbose=False)
    ag.llm = p = _ExigeFerramentas()
    tr = ag.investigar("Quais categorias deveriam ter o desconto reduzido?")

    # a 1ª vai sem ferramentas (e é recusada); da 2ª em diante, sempre com.
    # O número de rodadas depois disso depende dos outros guardrails (aqui o de
    # teste estatístico cobra uma), então não se fixa o total.
    assert p.chamadas[0] is False
    assert all(p.chamadas[1:]) and len(p.chamadas) >= 3
    assert "margem_por_dimensao" in tr.ferramentas_usadas
    assert "não pôde ser redigida" not in tr.resposta_final
    ligou = [x for x in tr.passos if x.tipo == "pensamento" and isinstance(x.conteudo, dict)
             and "ferramentas_nativas_ligadas" in x.conteudo]
    assert len(ligou) == 1


def test_nome_de_ferramenta_com_prefixo_do_provedor_e_reconhecido():
    """A Groq devolveu "tool_margem_por_dimensao"; o registro tem
    "margem_por_dimensao". Sem tirar o prefixo, a chamada certa morreria como
    "ferramenta não existe"."""
    from vertice.agent.react import _nome_de_ferramenta
    assert _nome_de_ferramenta("tool_margem_por_dimensao") == "margem_por_dimensao"
    assert _nome_de_ferramenta("functions.margem_consolidada") == "margem_consolidada"
    assert _nome_de_ferramenta("margem_consolidada") == "margem_consolidada"
    # nome que não existe continua saindo intacto, para o erro dizer a verdade
    assert _nome_de_ferramenta("tool_inexistente") == "tool_inexistente"


def test_chamada_nativa_e_executada_mesmo_no_modo_texto():
    """Antes só o modo "nativo" olhava para tool_calls; vindo no modo texto, a
    chamada era descartada em silêncio."""
    class _SoChamaNativo:
        def __init__(self): self.n = 0

        def completar(self, msgs, modelo, tools=None):
            self.n += 1
            if self.n == 1:
                tc = type("TC", (), {"function": type("F", (), {
                    "name": "margem_por_dimensao",
                    "arguments": '{"dimensao": "canal"}'})()})()
                return type("M", (), {"content": "", "tool_calls": [tc]})()
            return type("M", (), {"content": RESPOSTA_OK, "tool_calls": None})()

    ag = AgenteMargem(mock=True, modo="texto", verbose=False)
    ag.llm = _SoChamaNativo()
    tr = ag.investigar("Qual canal tem menor margem?")
    assert "margem_por_dimensao" in tr.ferramentas_usadas


def test_insistencia_no_erro_de_ferramenta_cai_no_deterministico():
    """Uma vez ligamos as ferramentas; se ainda assim falhar, a resposta sai com
    os números do motor em vez de o agente ficar preso."""
    class _SempreFalha:
        def __init__(self): self.n = 0
        def completar(self, *a, **k):
            self.n += 1
            raise RuntimeError(ERRO_FERRAMENTA_INDEVIDA)

    ag = AgenteMargem(mock=True, verbose=False)
    ag.llm = p = _SempreFalha()
    tr = ag.investigar("O que acontece se eu limitar Moda no Email Marketing a 17%?")
    assert p.n == 2
    assert "não pôde ser redigida" in tr.resposta_final
    assert "8.590,02" in tr.resposta_final


# -------------------------------------- cota esgotada != gateway fora do ar
ERRO_COTA = ("Error code: 413 - {'error': {'message': 'Request too large for model "
             "`openai/gpt-oss-20b` on tokens per minute (TPM): Limit 6000, Used 5200, "
             "Requested 3100. Please try again in 21.5s. Need more tokens? Upgrade to "
             "Dev Tier', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}")


def test_cota_esgotada_e_reportada_como_cota_com_o_tempo_de_espera():
    """A Groq usa "Request too large" tanto para pedido grande quanto para cota
    estourada, mas o código é 'rate_limit_exceeded'. Mandar "tente quando o
    gateway voltar" para quem só precisa esperar 21 segundos é inútil."""
    class _SemCota:
        def completar(self, *a, **k):
            raise RuntimeError(ERRO_COTA)

    ag = AgenteMargem(mock=True, verbose=False)
    ag.llm = _SemCota()
    r = ag.investigar("Existe relação entre desconto e margem?").resposta_final
    assert "COTA DE TOKENS" in r
    assert "Aguarde 21.5s" in r
    assert "gateway voltar" not in r
    assert "58.13" in r or "58,13" in r          # e os números vêm junto


def test_erro_sem_cota_mantem_a_mensagem_de_indisponibilidade():
    class _Fora:
        def completar(self, *a, **k):
            raise RuntimeError("Connection error.")

    ag = AgenteMargem(mock=True, verbose=False)
    ag.llm = _Fora()
    r = ag.investigar("Existe relação entre desconto e margem?").resposta_final
    assert "COTA DE TOKENS" not in r
    assert "gateway voltar" in r


def test_classificacao_separa_cota_de_tamanho_de_indisponibilidade():
    from vertice.agent.react import _erro_de_cota, _erro_de_tamanho, _espera_sugerida
    cota = RuntimeError(ERRO_COTA)
    assert _erro_de_cota(cota)
    assert _espera_sugerida(str(cota)) == "21.5s"
    # pedido grande sem cota: encolher ajuda, esperar não
    tamanho = RuntimeError("Error code: 413 - Request too large: maximum context length")
    assert _erro_de_tamanho(tamanho) and not _erro_de_cota(tamanho)
    assert not _erro_de_cota(RuntimeError("Connection error."))
