"""Testes da API HTTP que liga o front-end MarginGuard ao agente."""
import os
import tempfile

import pytest

os.environ["VERTICE_API_MOCK"] = "1"
_TRACES_TMP = tempfile.mkdtemp(prefix="vertice_traces_test_")
os.environ["VERTICE_TRACES_DIR"] = _TRACES_TMP

from fastapi.testclient import TestClient  # noqa: E402

from vertice.api import app, _historico_do_frontend, Mensagem  # noqa: E402

client = TestClient(app)


def test_chat_aceita_mensagem_e_devolve_reply_e_trace_id():
    r = client.post("/api/chat", json={"message": "Por que a margem caiu?", "history": []})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["reply"], str) and body["reply"]
    assert isinstance(body["trace_id"], str) and body["trace_id"]


def test_chat_rejeita_mensagem_vazia():
    r = client.post("/api/chat", json={"message": "   ", "history": []})
    assert r.status_code == 400


def test_chat_aceita_historico_de_pares_pergunta_resposta():
    historico = [
        {"role": "user", "content": "Qual canal tem a pior margem?"},
        {"role": "assistant", "content": "FATO: Marketplace.\nINFERÊNCIA: x.\n"
                                          "RECOMENDAÇÃO: x.\nFORÇA DA EVIDÊNCIA: FRACA"},
    ]
    r = client.post("/api/chat", json={"message": "E o frete?", "history": historico})
    assert r.status_code == 200
    assert r.json()["reply"]


def test_chat_ignora_campos_de_papel_desconhecido_no_historico():
    historico = [{"role": "tool", "content": "não deveria vazar pro histórico do agente"}]
    r = client.post("/api/chat", json={"message": "pergunta", "history": historico})
    assert r.status_code == 200


def test_health_reporta_modo_mock_e_modelos():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["modo_mock"] is True
    assert body["ok"] is True
    assert "modelo_investigacao" in body and "modelo_sintese" in body


def test_frontend_e_servido_na_raiz():
    r = client.get("/")
    assert r.status_code == 200
    assert "MarginGuard" in r.text


# --------------------------------------- reconstrução de histórico
def test_historico_do_frontend_etiqueta_pergunta_do_usuario():
    from vertice.agent.prompts import ROTULO_PERGUNTA
    hist = _historico_do_frontend([Mensagem(role="user", content="oi")])
    assert hist == [{"role": "user", "content": f"{ROTULO_PERGUNTA} oi"}]


def test_historico_do_frontend_preserva_resposta_do_assistente_sem_etiqueta():
    hist = _historico_do_frontend([Mensagem(role="assistant", content="FATO: x")])
    assert hist == [{"role": "assistant", "content": "FATO: x"}]


def test_historico_do_frontend_descarta_papel_desconhecido():
    hist = _historico_do_frontend([Mensagem(role="system", content="nao deveria entrar")])
    assert hist == []


# --------------------------------------- trace salvo e recuperável (auditoria)
def test_chat_salva_trace_recuperavel_por_get():
    """Sem isso, o trace de uma pergunta feita pela interface web morre com a
    requisição — não tem como auditar depois o que o agente realmente fez
    (diferente do CLI, que tem /trace e /salvar na hora)."""
    r = client.post("/api/chat", json={"message": "Qual canal tem a pior margem?", "history": []})
    trace_id = r.json()["trace_id"]

    r2 = client.get(f"/api/trace/{trace_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == trace_id
    assert body["pergunta"] == "Qual canal tem a pior margem?"
    assert "passos" in body


def test_trace_inexistente_devolve_404():
    r = client.get("/api/trace/nao-existe-esse-id")
    assert r.status_code == 404


# --------------------------------------- relatório semanal, auditoria e política
# Tudo isto existe para que nada precise de terminal: o front chama estes
# endpoints. Os testes cobrem o contrato que o painel consome.
def test_relatorio_json_traz_os_kpis_e_nao_chama_modelo_por_padrao():
    r = client.get("/api/relatorio")
    assert r.status_code == 200
    body = r.json()
    for bloco in ("margem", "desconto", "margem_negativa", "frete_canal_foco",
                  "devolucoes", "pior_canal_por_margem", "fontes"):
        assert bloco in body
    assert body["resumo_disponivel"] is False
    assert body["resumo_executivo"] is None


def test_relatorio_html_abre_na_aba_e_baixar_manda_como_arquivo():
    r = client.get("/api/relatorio.html")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "content-disposition" not in r.headers
    assert "<html" in r.text and "Relatório por período" in r.text

    r2 = client.get("/api/relatorio.html?baixar=true")
    assert r2.headers["content-disposition"].startswith("attachment;")
    assert ".html" in r2.headers["content-disposition"]


def test_auditoria_json_traz_checagens_e_o_destaque_de_incoerencia():
    r = client.get("/api/auditoria")
    assert r.status_code == 200
    body = r.json()
    assert body["total_checagens"] == len(body["checagens"])
    destaque = body["destaque_incoerencia"]
    assert destaque["valor_b"] == "Tamanho errado"
    assert destaque["celulas"]
    # "fora" só conta o que NÃO é Moda — é esse o achado.
    esperado = sum(c["registros"] for c in destaque["celulas"] if c["categoria"] != "Moda")
    assert destaque["fora"] == esperado


def test_lacuna_de_prazo_sai_da_api_mesmo_fora_do_relatorio():
    """A lacuna continua DECLARADA — o que mudou foi onde ela aparece.

    A seção "Lacunas de dado" saiu das duas superfícies de leitura (a tela e o
    relatório exportado) a pedido do usuário. A auditoria não passou a
    estimar prazo nenhum: /api/auditoria continua devolvendo a lacuna e o
    `prazo_devolucao.disponivel=False`, que é o que sustenta a afirmação de
    que o dado não existe. Este teste guarda essa distinção — se algum dia a
    lacuna sumir também da API, é regressão de verdade.
    """
    dados = client.get("/api/auditoria").json()
    assert dados["prazo_devolucao"]["disponivel"] is False
    assert any("prazo de devolução" in l and "data de solicitação" in l
               for l in dados["lacunas_de_dado"])

    r = client.get("/api/auditoria.html")
    assert r.status_code == 200
    assert "Lacunas de dado" not in r.text


def test_barra_do_html_tem_largura_proporcional():
    """Regressão: o preenchimento era um <span> inline, então o width:% não
    valia nada e todas as barras saíam do mesmo tamanho."""
    from vertice.render_html import _barras, _CSS
    html = _barras([{"cat": "A", "registros": 100}, {"cat": "B", "registros": 25}], "cat")
    assert 'width:100.0%' in html and 'width:25.0%' in html
    assert ".bar-fill{display:block" in _CSS


def test_politica_get_lista_canais_e_categorias_para_o_formulario(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    r = client.get("/api/politica")
    assert r.status_code == 200
    body = r.json()
    assert body["vigente"] is None and body["historico"] == []
    assert "Marketplace" in body["canais"]
    assert "Moda" in body["categorias"]


def test_politica_post_registra_e_passa_a_valer_no_recorte(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    r = client.post("/api/politica", json={
        "canal": "Marketplace", "categoria": None,
        "teto_pct": 18, "responsavel": "Comitê de Margem"})
    assert r.status_code == 200
    assert r.json()["vigente"]["teto_pct"] == 18.0

    r2 = client.get("/api/politica?canal=Marketplace")
    assert r2.json()["vigente"]["responsavel"] == "Comitê de Margem"
    assert len(r2.json()["historico"]) == 1


def test_politica_post_sem_responsavel_e_recusada(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    r = client.post("/api/politica", json={
        "canal": None, "categoria": None, "teto_pct": 20, "responsavel": "  "})
    assert r.status_code == 400


def test_politica_trata_recorte_vazio_do_front_como_global(tmp_path, monkeypatch):
    """O front manda ?canal=&categoria= quando o recorte é "todos"; string vazia
    não pode ser tratada como um canal chamado "" — senão a política global some."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    client.post("/api/politica", json={
        "canal": None, "categoria": None, "teto_pct": 25, "responsavel": "Financeiro"})
    r = client.get("/api/politica?canal=&categoria=")
    assert r.json()["vigente"]["teto_pct"] == 25.0


def test_politica_mais_especifica_vence_no_recorte_dela(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    client.post("/api/politica", json={"canal": "Marketplace", "categoria": None,
                                       "teto_pct": 18, "responsavel": "Comercial"})
    client.post("/api/politica", json={"canal": "Marketplace", "categoria": "Moda",
                                       "teto_pct": 12, "responsavel": "Comitê"})
    assert client.get("/api/politica?canal=Marketplace"
                      "&categoria=Moda").json()["vigente"]["teto_pct"] == 12.0
    assert client.get("/api/politica?canal=Marketplace"
                      "&categoria=").json()["vigente"]["teto_pct"] == 18.0


# ------------------------------- janela do relatório e simulação de política
def test_relatorio_traz_o_bloco_da_semana():
    body = client.get("/api/relatorio").json()
    assert body["semana"]["dias"] == 7
    assert body["semana"]["inicio"] and body["semana"]["fim"]


def test_relatorio_aceita_outra_janela_e_recusa_janela_invalida():
    assert client.get("/api/relatorio?dias=30").json()["semana"]["dias"] == 30
    assert client.get("/api/relatorio?dias=0").status_code == 400


# ----------------------------------------- período com data de fim (regressão)
# `margem_na_janela` sempre aceitou `ate`, mas o parâmetro parava três camadas
# antes da tela: enquanto o relatório era semanal ninguém precisou de data de
# fim ("os últimos 7 dias" acaba hoje). Com a tela oferecendo escolha de
# período, a janela ia para março e voltava com os dados de janeiro.
def test_relatorio_respeita_a_data_de_fim_pedida():
    s = client.get("/api/relatorio?dias=31&ate=2023-03-31").json()["semana"]
    assert s["inicio"] == "2023-03-01"
    assert s["fim"] == "2023-03-31"
    assert s["dias"] == 31
    assert s["pedidos"] > 0


def test_sem_data_de_fim_a_janela_termina_no_ultimo_dia_da_base():
    """O padrão não mudou: relatório agendado continua sendo 'os últimos N dias'."""
    body = client.get("/api/relatorio?dias=7").json()
    assert body["semana"]["fim"] == body["janela"][1][:10]


def test_data_de_fim_muda_o_resultado_e_nao_so_o_rotulo():
    marco = client.get("/api/relatorio?dias=31&ate=2023-03-31").json()["semana"]
    ultimo = client.get("/api/relatorio?dias=31").json()["semana"]
    assert marco["pedidos"] != ultimo["pedidos"]
    assert marco["margem_pct"] != ultimo["margem_pct"]


def test_periodo_fora_da_base_devolve_janela_certa_e_zero_pedidos():
    """Não é erro: é o dado que não existe naquele intervalo. A janela volta
    rotulada corretamente para a tela poder dizer isso."""
    s = client.get("/api/relatorio?dias=7&ate=2025-06-01").json()["semana"]
    assert s["inicio"] == "2025-05-26" and s["fim"] == "2025-06-01"
    assert s["pedidos"] == 0


def test_data_de_fim_malformada_e_400_e_nao_500():
    """Sem a validação, '?ate=ontem' virava exceção do pandas — 500 sem pista."""
    r = client.get("/api/relatorio?ate=ontem")
    assert r.status_code == 400
    assert "AAAA-MM-DD" in r.json()["detail"]


def test_relatorio_html_tambem_aceita_a_data_de_fim():
    r = client.get("/api/relatorio.html?dias=31&ate=2023-03-31")
    assert r.status_code == 200
    assert "01/03/2023" in r.text or "2023-03-01" in r.text


def test_politica_simular_devolve_o_efeito_antes_de_aplicar(tmp_path, monkeypatch):
    """Prévia: a pessoa vê o que o teto faz sem registrar nada."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    r = client.get("/api/politica/simular?teto_pct=18&canal=Marketplace")
    assert r.status_code == 200
    body = r.json()
    assert body["recorte"] == {"canal": "Marketplace"}
    assert body["pedidos_afetados"] > 0
    assert body["margem_recuperada_reais"] > 0
    # nada foi gravado
    assert client.get("/api/politica").json()["historico_completo"] == []


def test_politica_vigente_vem_com_o_impacto_calculado(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    posted = client.post("/api/politica", json={
        "canal": "Marketplace", "categoria": None,
        "teto_pct": 18, "responsavel": "Comitê"}).json()
    assert posted["impacto"]["margem_recuperada_reais"] > 0

    consulta = client.get("/api/politica?canal=Marketplace").json()
    assert consulta["impacto"]["teto_aplicado_pct"] == 18.0
    assert consulta["impacto"]["recorte"] == {"canal": "Marketplace"}


def test_historico_completo_nao_some_ao_filtrar_por_recorte(tmp_path, monkeypatch):
    """Ao consultar UM recorte, o histórico filtrado escondia as políticas dos
    outros — dava a impressão de que não tinham sido salvas. A tela passou a
    mostrar o histórico completo, e a API a devolver os dois."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    client.post("/api/politica", json={"canal": "Marketplace", "categoria": None,
                                       "teto_pct": 18, "responsavel": "Ana"})
    client.post("/api/politica", json={"canal": "TikTok Ads", "categoria": None,
                                       "teto_pct": 12, "responsavel": "Bia"})

    body = client.get("/api/politica?canal=TikTok Ads").json()
    assert len(body["historico"]) == 1            # só a do recorte consultado
    assert len(body["historico_completo"]) == 2   # as duas continuam salvas
    assert body["arquivo"].endswith("p.json")


def test_politica_vigente_de_um_canal_nao_vale_para_a_consulta_global(tmp_path, monkeypatch):
    """Não é bug: política de canal não governa a base inteira. Por isso a tela
    tem seletor de recorte — sem ele, parecia que o cadastro não pegou."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    client.post("/api/politica", json={"canal": "Marketplace", "categoria": None,
                                       "teto_pct": 18, "responsavel": "Ana"})
    assert client.get("/api/politica").json()["vigente"] is None
    assert client.get("/api/politica?canal=Marketplace").json()["vigente"]["teto_pct"] == 18.0


def test_auditoria_reporta_a_linha_quebrada_e_o_que_requer_leitura():
    body = client.get("/api/auditoria").json()
    assert body["checagens_com_atencao"] >= 1
    assert body["checagens_a_revisar"] >= 1
    html = client.get("/api/auditoria.html").text
    assert "Requer leitura" in html


# ------------------------------- gateway fora do ar: degradar, não estourar
def test_chat_responde_com_os_numeros_quando_o_modelo_esta_indisponivel(monkeypatch):
    """Orçamento estourado / gateway fora derrubava a resposta inteira com 502,
    jogando fora os números que o roteador JÁ tinha apurado em Python."""
    import vertice.api as api

    class LLMQuebrado:
        def completar(self, *a, **k):
            raise RuntimeError("Error code: 400 - Budget exceeded: 20.05 >= 20.00 dollars")

    original = api.AgenteMargem

    def _agente_com_llm_quebrado(*a, **k):
        ag = original(*a, **k)
        ag.llm = LLMQuebrado()
        return ag
    monkeypatch.setattr(api, "AgenteMargem", _agente_com_llm_quebrado)

    r = client.post("/api/chat", json={
        "message": "O que aconteceria se eu limitasse o desconto de Moda no "
                   "Email Marketing a 17%?", "history": []})
    assert r.status_code == 200                       # não é mais 502
    reply = r.json()["reply"]
    assert reply.startswith("FATO:")
    assert "simular_teto_desconto" in reply
    assert "591" in reply and "8.590,02" in reply      # números reais do motor
    assert "Budget exceeded" in reply                 # e o motivo, sem esconder

    trace = client.get(f"/api/trace/{r.json()['trace_id']}").json()
    assert trace["roteamento"]["status_ferramenta"] == "TOOL_CALLED_SUCCESS"


# ------------------------------------------------------------ monitoramento
# Esta rota não tinha nenhum teste, e foi exatamente por isso que um decorador
# colado na função errada passou despercebido: `/api/monitoramento` chegou a
# responder o cálculo de poder no lugar do painel de monitoramento, com 912
# testes verdes. Os testes abaixo fixam o CONTRATO da rota — as chaves que a
# tela consome — além do comportamento.

def _monitoramento_isolado(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    return client.get("/api/monitoramento").json()


def test_monitoramento_responde_o_painel_e_nao_outra_coisa(tmp_path, monkeypatch):
    """O contrato da tela: se estas chaves sumirem, o painel quebra."""
    d = _monitoramento_isolado(tmp_path, monkeypatch)
    for chave in ("estado", "titulo", "explicacao", "proposta",
                  "regra_de_parada", "resultados", "desenho"):
        assert chave in d, f"a rota deixou de devolver {chave!r}"
    assert d["estado"] == "aguardando"
    assert d["proposta"] is None


def test_monitoramento_traz_o_calculo_de_poder_mesmo_sem_experimento(tmp_path, monkeypatch):
    """"Esse teste é possível de rodar?" se responde antes de existir teste.

    O desenho vem da dispersão real da base, então a tela vazia deixa de ser
    só uma recusa: ela já diz quantas unidades o teste exigiria.
    """
    d = _monitoramento_isolado(tmp_path, monkeypatch)
    unidades = {u["unidade"]: u for u in d["desenho"]["unidades"]}
    assert set(unidades) == {"pedido", "cliente"}
    assert unidades["cliente"]["mede_volume"] is True
    assert unidades["cliente"]["viavel_com_a_base_atual"] is False
    assert unidades["pedido"]["n_por_grupo"] > 0


def test_experimento_criado_aparece_no_monitoramento_sem_inventar_resultado(
        tmp_path, monkeypatch, fluxo_completo):
    """O caminho completo da tela: propor, aprovar, desenhar o teste, olhar.

    E a trava que importa: com o experimento recém-criado e sem pedido na
    janela, os resultados saem INDISPONÍVEIS. Preenchê-los com o valor da
    simulação seria apresentar estimativa como apuração.
    """
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    proposta = client.post("/api/politica/propostas",
                           json={"teto_pct": 20, "responsavel": "Ana"}).json()
    for destino, quem in [("simular", "Ana"), ("enviar-aprovacao", "Ana"),
                          ("aprovar", "CFO")]:
        r = client.post(f"/api/politica/{proposta['id']}/{destino}",
                        json={"quem": quem})
        assert r.status_code == 200, r.text

    criado = client.post("/api/experimento", json={
        "proposta_id": proposta["id"], "teto_pct": 20, "responsavel": "Ana",
        "unidade": "cliente", "duracao_dias": 30})
    assert criado.status_code == 200, criado.text

    d = client.get("/api/monitoramento").json()
    assert d["experimento"] is not None
    assert d["experimento"]["estado"] == "planejado"
    numericos = ("margem_preservada_real_reais", "volume_grupo_teste",
                 "volume_grupo_controle", "diferenca_relativa_pct", "p_valor")
    assert all(d["resultados"][k] is None for k in numericos)
    assert d["resultados"]["status_do_teste"] == "aguardando dado do experimento"
    assert d["por_que_sem_numeros"]


def test_encerrar_experimento_pela_api_exige_motivo(tmp_path, monkeypatch):
    """Parar um teste sem dizer por quê apaga a única informação da parada."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    exp = client.post("/api/experimento", json={
        "proposta_id": "prop_x", "teto_pct": 20, "responsavel": "Ana"}).json()
    client.post(f"/api/experimento/{exp['id']}/iniciar", json={"quem": "CFO"})
    sem_motivo = client.post(f"/api/experimento/{exp['id']}/encerrar",
                             json={"quem": "CFO", "motivo": ""})
    assert sem_motivo.status_code == 400
    com_motivo = client.post(f"/api/experimento/{exp['id']}/encerrar",
                             json={"quem": "CFO", "motivo": "fim da janela"})
    assert com_motivo.status_code == 200
    assert com_motivo.json()["motivo_encerramento"] == "fim da janela"


# ------------------------------------------------- segregação de funções
# O fluxo de cinco passos registrava quem fez cada transição, mas não impedia
# que fosse sempre a mesma pessoa — e o campo "quem" ainda vinha preenchido
# com o nome de quem propôs, então aprovar a própria política era um clique.
# Registro não é controle: estes testes fixam o controle.

def _proposta_pronta_para_aprovar(quem="Pablo"):
    proposta = client.post("/api/politica/propostas",
                           json={"teto_pct": 20, "responsavel": quem}).json()
    for destino in ("simular", "enviar-aprovacao"):
        r = client.post(f"/api/politica/{proposta['id']}/{destino}", json={"quem": quem})
        assert r.status_code == 200, r.text
    return proposta


def test_quem_propos_nao_aprova(tmp_path, monkeypatch, fluxo_completo):
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    proposta = _proposta_pronta_para_aprovar("Pablo")
    r = client.post(f"/api/politica/{proposta['id']}/aprovar", json={"quem": "Pablo"})
    assert r.status_code == 400
    assert "não pode aprová-la" in r.json()["detail"]
    # E a política NÃO passou a valer.
    assert client.get("/api/politica").json()["vigente"] is None


def test_nome_com_caixa_ou_espaco_diferente_nao_burla_o_controle(tmp_path, monkeypatch,
                                                                  fluxo_completo):
    """"pablo ", "PABLO" e "Pablo" são a mesma pessoa tentando o caminho curto."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    proposta = _proposta_pronta_para_aprovar("Pablo")
    for tentativa in (" pablo ", "PABLO", "PaBlO"):
        r = client.post(f"/api/politica/{proposta['id']}/aprovar", json={"quem": tentativa})
        assert r.status_code == 400, f"{tentativa!r} passou pelo controle"


def test_outra_pessoa_aprova_e_a_politica_passa_a_valer(tmp_path, monkeypatch,
                                                        fluxo_completo):
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    proposta = _proposta_pronta_para_aprovar("Pablo")
    r = client.post(f"/api/politica/{proposta['id']}/aprovar", json={"quem": "Carlos CFO"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ativa"
    assert r.json()["historico"][-1]["quem"] == "Carlos CFO"
    # A trilha agora mostra DUAS pessoas, que é o ponto do controle.
    nomes = {h["quem"] for h in r.json()["historico"]}
    assert nomes == {"Pablo", "Carlos CFO"}
    assert client.get("/api/politica").json()["vigente"]["teto_pct"] == 20


def test_so_a_aprovacao_exige_outra_pessoa(tmp_path, monkeypatch, fluxo_completo):
    """Simular e enviar para aprovação continuam sendo de quem propôs — o
    controle é sobre a decisão, não sobre o trabalho que a antecede."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    proposta = _proposta_pronta_para_aprovar("Pablo")   # dois passos, mesma pessoa
    assert client.get(f"/api/politica/propostas").json()["propostas"][0]["estado"] == "aprovacao"


def test_fila_de_aprovacao_mostra_quem_propos(tmp_path, monkeypatch, fluxo_completo):
    """Aprovação sem fila é um estado que só quem abriu a proposta enxerga."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    vazia = client.get("/api/politica/propostas").json()["aguardando_aprovacao"]
    assert vazia == []

    proposta = _proposta_pronta_para_aprovar("Pablo")
    fila = client.get("/api/politica/propostas").json()["aguardando_aprovacao"]
    assert [p["id"] for p in fila] == [proposta["id"]]
    assert fila[0]["proposta_por"] == "Pablo"

    client.post(f"/api/politica/{proposta['id']}/aprovar", json={"quem": "Carlos CFO"})
    assert client.get("/api/politica/propostas").json()["aguardando_aprovacao"] == []
def test_fluxo_para_em_simulacao_e_diz_que_o_resto_e_futuro(tmp_path, monkeypatch):
    """Sem a trava ligada, o fluxo não passa de Simulação — e a recusa explica
    por quê, em vez de devolver um erro de transição inválida."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    proposta = client.post("/api/politica/propostas",
                           json={"teto_pct": 20, "responsavel": "Ana"}).json()
    assert client.post(f"/api/politica/{proposta['id']}/simular",
                       json={"quem": "Ana"}).status_code == 200

    r = client.post(f"/api/politica/{proposta['id']}/enviar-aprovacao",
                    json={"quem": "Ana"})
    assert r.status_code == 400
    assert "implementação futura" in r.json()["detail"]

    # A proposta fica em Simulação, e nenhuma política passou a valer.
    assert client.get("/api/politica/propostas").json()["propostas"][0]["estado"] == "simulacao"
    assert client.get("/api/politica").json()["vigente"] is None


def test_a_tela_sabe_quais_etapas_estao_desligadas(tmp_path, monkeypatch):
    """A tela não decide isso sozinha: quem manda é o backend."""
    monkeypatch.setenv("VERTICE_POLITICAS_FILE", str(tmp_path / "p.json"))
    d = client.get("/api/politica/propostas").json()
    assert d["etapas_habilitadas"] == ["rascunho", "simulacao"]
    assert d["etapas_futuras"] == ["aprovacao", "ativa", "monitoramento"]
