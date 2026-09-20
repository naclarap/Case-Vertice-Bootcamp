# Como rodar

## 1. Instalar (uma vez só)

**Linux / macOS / WSL**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

No WSL, o disco do Windows fica sob `/mnt/c/` — entre na pasta do projeto por
lá antes de criar o ambiente. Se `venv` falhar com `ensurepip is not
available`, instale o pacote uma vez:

```bash
sudo apt install -y python3-venv
```

**Windows (PowerShell)**

```powershell
py -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Se o PowerShell recusar o script de ativação, rode uma vez:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

---

## 2. Conferir que está tudo certo (sem internet, sem chave)

```bash
python -m pytest
```

Esperado: **925 passando, 11 pulados**.

Entre eles, **35 testes de aceite** que conferem, um a um, se o motor reproduz os
números publicados no Livro de Números — o teto de 20%, o frete do Marketplace, a
ponte do pós-pedido, os KPIs do roadmap. Se algum falhar, o motor divergiu. **não ajuste o teste, investigue.**

```bash
python -m pytest tests/test_aceite_livro_de_numeros.py -v
```

```bash
python -m scripts.auditoria_perguntas > docs/AUDITORIA_PERGUNTAS.md
```

Roda as 95 perguntas do enunciado pelo roteador e pelo motor e gera o relatório.
Esperado: **0 FAIL**.

---

## 3. Usar só o motor (sem IA nenhuma)

```bash
python -c "from vertice.engine import executar; import json; print(json.dumps(executar('simular_teto_desconto', {'teto_pct': 20}), ensure_ascii=False, indent=2))"
```

Perguntas prontas, todas sem chave:

| Chamada | Resultado |
|---|---|
| `executar('simular_teto_desconto', {'teto_pct': 20})` | R$ 241.424,23 |
| `executar('regra_frete_por_limiar', {})` | R$ 108.026,16 |
| `executar('perda_pos_pedido', {})` | R$ 2.628.111,95 |
| `executar('caso_base_do_plano', {})` | R$ 349.450,39 |
| `executar('kpis_do_teto', {'teto_pct': 20})` | KPIs do roadmap |

Todo resultado traz: o recorte usado, a premissa, a marca (● fato, ◐ estimativa,
○ direção) e o hash do arquivo de dados.

---

## 4. Usar o agente sem chave de API (modo mock)

```bash
python -m vertice.cli --mock
```

O texto da resposta vem de um roteiro fixo, mas **todos os números são reais**: o
motor roda de verdade. Serve para demonstrar o fluxo sem rede.

---

## 5. Usar o agente completo (precisa de chave)

**Linux / macOS**

```bash
export ELOAGENTS_API_KEY="sua-chave"
```

**Windows (PowerShell)**

```powershell
$env:ELOAGENTS_API_KEY = "sua-chave"
```

Conferir a conexão e a lista de modelos que a conta aceita:

```bash
python -m vertice.cli --diagnostico
```

Sessão interativa no terminal:

```bash
python -m vertice.cli
```

Uma pergunta só:

```bash
python -m vertice.cli -p "Quanto preservamos com um teto de 20% fora de novembro?"
```

Painel web (chat, relatório, auditoria, política e monitoramento):

```bash
python -m vertice.api
```

Abra <http://localhost:8000>.

Painel sem chave nenhuma:

```bash
VERTICE_API_MOCK=1 python -m vertice.api          # Linux/macOS
```

```powershell
$env:VERTICE_API_MOCK=1; python -m vertice.api    # Windows
```

---

## 6. Rodar com Google AI Studio (alternativa gratuita ao gateway)

Pegue a chave em <https://aistudio.google.com/apikey> e exporte:

```bash
export ELOAGENTS_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
export ELOAGENTS_API_KEY="cole-sua-chave"
export VERTICE_MODEL_STEP=gemini-flash-lite-latest
export VERTICE_MODEL_FINAL=gemini-flash-lite-latest
export VERTICE_TOOL_MODE=nativo
export VERTICE_CATALOGO_COMPACTO=1
```

Depois rode `python -m vertice.cli --diagnostico`: ele imprime os modelos que a
sua conta aceita. Nomes de modelo mudam; use o que aparecer na lista.

---

## 7. Variáveis de ambiente

| Variável | O que faz |
|---|---|
| `ELOAGENTS_API_KEY` | chave do gateway (só para a camada de linguagem) |
| `ELOAGENTS_BASE_URL` | endpoint compatível com OpenAI |
| `VERTICE_MODEL_STEP` | modelo dos passos de investigação |
| `VERTICE_MODEL_FINAL` | modelo da síntese final |
| `VERTICE_TOOL_MODE` | `texto` (padrão) ou `nativo` |
| `VERTICE_MAX_ITER` | teto de iterações do loop (padrão 8) |
| `VERTICE_MAX_TOKENS` | teto de tokens da resposta. Vazio (padrão) = sem teto. Truncar quebra o contrato de quatro seções — para encurtar, aperte o bloco CONCISÃO do system prompt |
| `VERTICE_MAX_HIST` | mensagens de conversa anterior enviadas (padrão 6) |
| `VERTICE_CATALOGO_COMPACTO=1` | encurta o catálogo de ferramentas |
| `VERTICE_CONVENCAO` | `decisao` (padrão) ou `diagnostico` — recorte padrão das simulações. Use com cuidado: vale para a sessão inteira e aparece em todo resultado |
| `VERTICE_DATA_DIR` | pasta dos CSVs (padrão `./data`) |
| `VERTICE_POLITICAS_FILE` | política de desconto vigente + histórico |
| `VERTICE_ALCADAS_FILE` | faixas de alçada em JSON |
| `VERTICE_TRACES_DIR` | onde a API salva o trace de cada pergunta |
| `VERTICE_API_MOCK=1` | roda a API sem gateway |

---
