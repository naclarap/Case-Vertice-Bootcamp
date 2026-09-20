"""Testes da garantia central: todo número da resposta veio de uma ferramenta."""
import pytest

from vertice.agent.verificacao import coletar_numeros, verificar_numeros
from vertice.engine import executar


@pytest.fixture(scope="module")
def numeros_consolidado():
    return coletar_numeros(executar("margem_consolidada"))


# ------------------------------------------------------- coleta de números
def test_coleta_percorre_estrutura_aninhada():
    obj = {"a": 1.5, "b": [2.5, {"c": 3.5}], "d": ("x", 4.5), "e": {"f": {"g": 5.5}}}
    assert coletar_numeros(obj) >= {1.5, 2.5, 3.5, 4.5, 5.5}


def test_coleta_ignora_booleanos():
    """True/False são 1/0 em Python; se entrassem, validariam qualquer '1'."""
    assert coletar_numeros({"devolvido": True, "x": False}) == set()


def test_coleta_le_numeros_dentro_de_strings():
    assert 47.57 in coletar_numeros({"leitura": "margem de 47,57% no canal"})


def test_coleta_de_ferramenta_real_e_rica(numeros_consolidado):
    assert len(numeros_consolidado) > 20
    assert 49.99 in numeros_consolidado


# ------------------------------------------- detecção de número inventado
def test_detecta_multiplicacao_feita_pelo_modelo(numeros_consolidado):
    """Caso real: o modelo multiplicou 18.119.023,83 x 30% e publicou o produto."""
    ruim = ("FATO: Desconto adicional: R$ 18.119.023,83 × 30% = R$ 5.435.707,15. "
            "Nova margem: R$ 3.622.720,40 = 19,99%.")
    r = verificar_numeros(ruim, numeros_consolidado, "aplicar 30% de desconto")
    assert not r["ok"]
    assert "5.435.707,15" in r["suspeitos"]
    assert "3.622.720,40" in r["suspeitos"]


def test_aprova_resposta_que_so_cita_numeros_de_ferramenta(numeros_consolidado):
    bom = ("FATO: a margem consolidada é 49,99% sobre receita bruta de "
           "R$ 18.119.023,83, com desconto de R$ 1.450.067,34.")
    assert verificar_numeros(bom, numeros_consolidado, "qual a margem?")["ok"]


def test_numeros_da_pergunta_nao_sao_inventados(numeros_consolidado):
    """'30%' veio do usuário: é premissa do cenário, não apuração."""
    r = verificar_numeros("FATO: simulei 1234,56 de desconto",
                          numeros_consolidado | {1234.56}, "aplique 1234,56")
    assert r["ok"]


# ------------------------------------------------- ausência de falso positivo
def test_numeros_pequenos_nao_sao_verificados(numeros_consolidado):
    """30%, 60%, 100% são retórica; verificá-los geraria acusação indevida."""
    r = verificar_numeros("FATO: cai 30%, ou 60% da margem, chegando a 100%.",
                          numeros_consolidado, "")
    assert r["ok"]


def test_anos_nao_sao_verificados(numeros_consolidado):
    r = verificar_numeros("FATO: entre 2023 e 2024 a margem caiu.", numeros_consolidado, "")
    assert r["ok"]


def test_tolera_arredondamento():
    assert verificar_numeros("FATO: margem de 47,57%", {47.5712}, "")["ok"]
    assert verificar_numeros("FATO: total de 1.234.567,89", {1234567.891}, "")["ok"]


def test_tolera_fracao_apresentada_como_percentual():
    """A ferramenta devolve 0,4757 e o modelo escreve 47,57%."""
    assert verificar_numeros("FATO: margem de 47,57%", {0.4757}, "")["ok"]


def test_tolera_ambiguidade_de_separador():
    """'1.234' pode ser milhar pt-BR ou decimal en-US: na dúvida, não acusa."""
    assert verificar_numeros("FATO: valor 1.234", {1234.0}, "")["ok"]
    assert verificar_numeros("FATO: valor 1.234", {1.234}, "")["ok"]


def test_resposta_sem_numeros_e_valida(numeros_consolidado):
    r = verificar_numeros("FATO: não foi possível apurar.", numeros_consolidado, "")
    assert r["ok"] and r["numeros_verificados"] == 0


def test_relatorio_conta_numeros_verificados(numeros_consolidado):
    r = verificar_numeros("FATO: 18.119.023,83 e 9.058.427,55", numeros_consolidado, "")
    assert r["numeros_verificados"] == 2
    assert r["n_numeros_de_ferramenta"] == len(numeros_consolidado)


# ------------------------------------------------- coerência com o motor real
def test_resposta_correta_da_simulacao_passa_na_verificacao():
    """A resposta certa para a pergunta que falhou tem de ser aprovada."""
    numeros = coletar_numeros(executar("simular_desconto_em_segmento",
                                       {"desconto_pct": "30", "canal": "Marketplace",
                                        "mes": "2023-11"}))
    numeros |= coletar_numeros(executar("margem_consolidada"))
    boa = ("FATO: aplicar 30% nos 795 pedidos do Marketplace em novembro/2023 "
           "(R$ 553.175,73) custaria R$ 122.656,48 adicionais; a margem do segmento "
           "cairia de 47,01% para 24,84% e a consolidada de 49,99% para 49,32%.")
    r = verificar_numeros(boa, numeros, "aplicar 30% de desconto no Marketplace em novembro")
    assert r["ok"], f"suspeitos indevidos: {r['suspeitos']}"


def test_resposta_errada_da_simulacao_e_reprovada():
    """A resposta que o modelo deu de fato (30% sobre a base inteira) é reprovada."""
    numeros = coletar_numeros(executar("margem_consolidada"))
    r = verificar_numeros("FATO: custo adicional de R$ 5.435.707,15, margem vai a 19,99%.",
                          numeros, "aplicar 30% de desconto no Marketplace em novembro")
    assert not r["ok"]


# ---------------------------------- estatística anunciada pelo nome (buraco 4)
def test_r2_inventado_com_duas_casas_e_reprovado():
    """Caso real: o Gemini escreveu "R² = 0,85 obtidos por validação estatística
    formal" em três respostas. O motor devolve r2=None na ANOVA — o número não
    existe em lugar nenhum. Passava porque 0,85 tem menos que MIN_DIGITOS
    dígitos e o piso dispensava a conferência."""
    numeros = coletar_numeros(executar("anova_um_fator",
                                       {"metrica": "margem_contribuicao",
                                        "coluna_grupo": "canal"}))
    r = verificar_numeros("INFERÊNCIA: R² = 0,85 obtidos por validação estatística.",
                          numeros, "")
    assert not r["ok"]
    assert "0,85" in r["suspeitos"]


def test_estatistica_nomeada_real_continua_passando():
    numeros = coletar_numeros(executar("anova_um_fator",
                                       {"metrica": "desconto_pct",
                                        "coluna_grupo": "canal"}))
    r = verificar_numeros("FATO: F = 3,4963, eta² = 0,0009 e p = 0,0019.", numeros, "")
    assert r["ok"], f"suspeitos indevidos: {r['suspeitos']}"


def test_limiar_de_significancia_continua_isento():
    """"p < 0,001" é notação convencional de limiar, não medida — e o nome da
    estatística vem antes dele, então as duas regras se cruzam aqui."""
    numeros = coletar_numeros(executar("margem_consolidada"))
    r = verificar_numeros("FORÇA DA EVIDÊNCIA: FORTE (p < 0,001).", numeros, "")
    assert r["ok"]
    assert r["limiares_ignorados"] == 1


def test_percentual_retorico_nao_vira_estatistica(numeros_consolidado):
    """A regra vale para o número anunciado como resultado de teste; "corte de
    10%" e "R$ 30,00" seguem fora — senão o piso de dígitos deixa de existir."""
    r = verificar_numeros("RECOMENDAÇÃO: corte 10% do frete e teste 30% de desconto.",
                          numeros_consolidado, "")
    assert r["ok"]


# ------------------------------- notação do modelo (buracos 5 e 6)
def test_ponto_final_da_frase_nao_e_engolido_pelo_numero():
    """Falso positivo real: 'V de Cramér é 0.0127.' virava '0.0127.', cuja única
    leitura possível era 127 — e o número, que veio direto do qui-quadrado, foi
    acusado de inventado. A resposta correta inteira foi bloqueada."""
    numeros = coletar_numeros(executar("qui_quadrado_independencia",
                                       {"coluna_a": "motivo_devolucao",
                                        "coluna_b": "categoria"}))
    r = verificar_numeros("FATO: o V de Cramér entre motivo e categoria é 0.0127.",
                          numeros, "")
    assert r["ok"], f"bloqueou número de ferramenta: {r['suspeitos']}"


@pytest.mark.parametrize("escrito", [
    "chi2 = 11392.2504.", "o índice é 1.953.", "a média é 0.5509.",
])
def test_decimal_en_us_no_fim_da_frase(escrito):
    r = verificar_numeros(f"FATO: {escrito}", {11392.2504, 1.953, 0.5509}, "")
    assert r["ok"], r["suspeitos"]


def test_r2_inventado_em_latex_tambem_e_reprovado():
    """O modelo passou a escrever em LaTeX. '$R^2 = 0,85$' não casava com o
    rótulo 'R²', então o mesmo R² inventado voltou a passar DEPOIS da correção
    anterior — que só conhecia a forma com o expoente Unicode."""
    numeros = coletar_numeros(executar("simular_teto_desconto", {"teto_pct": 25}))
    for escrito in (r"$R^2 = 0,85$", "R² = 0,85", "R2 = 0,85", "R-quadrado de 0,85"):
        r = verificar_numeros(f"FORÇA DA EVIDÊNCIA: FORTE, com {escrito}.", numeros, "")
        assert not r["ok"], f"{escrito} passou"
        assert "0,85" in r["suspeitos"]


def test_estatistica_real_em_latex_continua_passando():
    numeros = coletar_numeros(executar("anova_um_fator",
                                       {"metrica": "margem_pct",
                                        "coluna_grupo": "faixa_desconto"}))
    boa = (r"FATO: $F = 5151,4716$ com $p < 0,001$ e $\eta^2$ (eta-quadrado) de "
           r"0,513, sobre $n = 24.454$ pedidos.")
    r = verificar_numeros(boa, numeros, "")
    assert r["ok"], f"suspeitos indevidos: {r['suspeitos']}"


# ------------------- número que o modelo digitou não vira apuração (buraco 7)
def test_parametro_inventado_nao_vira_evidencia_por_eco_da_ferramenta():
    """`classificar_evidencia` devolve p_valor e n como vieram. O modelo chamou
    classificar_evidencia(p_valor=0,0001) sem nenhum teste ter produzido esse
    valor, a ferramenta ecoou, e a verificação aprovou — o número existia numa
    observação. Aconteceu duas vezes em produção (p=0,05 e p=0,0001)."""
    from vertice.agent.react import AgenteMargem
    from vertice.agent.trace import Trace

    ag = AgenteMargem(mock=True, verbose=False)
    tr = Trace(pergunta="o que fazer nos próximos 30 dias?")
    params = {"p_valor": 0.0001, "n": 3764}
    tr.add("observacao", executar("classificar_evidencia", params),
           ferramenta="classificar_evidencia", parametros=params)
    r = ag._verificar("FORÇA DA EVIDÊNCIA: FORTE, com p-valor = 0,0001.", tr, "")
    assert not r["ok"]
    assert "0,0001" in r["suspeitos"]


def test_valor_calculado_de_verdade_continua_rastreavel():
    """O outro lado: o p que a ANOVA CALCULOU não é parâmetro de ninguém."""
    from vertice.agent.react import AgenteMargem
    from vertice.agent.trace import Trace

    ag = AgenteMargem(mock=True, verbose=False)
    tr = Trace(pergunta="x")
    params = {"metrica": "margem_pct", "coluna_grupo": "canal"}
    tr.add("observacao", executar("anova_um_fator", params),
           ferramenta="anova_um_fator", parametros=params)
    r = ag._verificar("FATO: F = 42,8749 e eta² = 0,0104.", tr, "")
    assert r["ok"], r["suspeitos"]


# ------------------------------------------- notação científica (buraco 8)
@pytest.mark.parametrize("escrito", [
    r"$3,09 \times 10^{-19}$", "3,09e-19", "3,09E-19", "3,087e-19", "3,1e-19",
    "3,09 x 10^-19",
])
def test_p_valor_em_notacao_cientifica_e_reconhecido(escrito):
    """Sem ler o expoente, a mantissa vira um número solto que não existe em
    ferramenta nenhuma — falso positivo justo na estatística que a regra de
    rótulo passou a conferir."""
    numeros = coletar_numeros(executar("anova_um_fator",
                                       {"metrica": "desconto_reais",
                                        "coluna_grupo": "canal"}))
    r = verificar_numeros(f"FATO: p-valor = {escrito}.", numeros, "")
    assert r["ok"], f"{escrito} foi acusado: {r['suspeitos']}"


@pytest.mark.parametrize("escrito", ["9,99e-19", "3,09e-18", "1,00e-7"])
def test_mantissa_ou_expoente_errado_e_reprovado(escrito):
    numeros = coletar_numeros(executar("anova_um_fator",
                                       {"metrica": "desconto_reais",
                                        "coluna_grupo": "canal"}))
    assert not verificar_numeros(f"FATO: p-valor = {escrito}.", numeros, "")["ok"]


def test_notacao_cientifica_nao_afrouxa_numero_comum():
    """A comparação por dígitos significativos vale SÓ para notação científica.
    Solta, ela aceitaria 'R$ 200.000' como leitura de 207.099,18."""
    numeros = coletar_numeros(executar("simular_teto_desconto", {"teto_pct": 25}))
    assert not verificar_numeros("FATO: recupera R$ 200.000,00.", numeros, "")["ok"]
