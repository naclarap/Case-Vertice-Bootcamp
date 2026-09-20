#!/usr/bin/env bash
#
# Provisiona labels, issues e o GitHub Project v2 ("Kanban - Case Vértice")
# no repositório naclarap/Case-Vertice-Bootcamp.
#
# Pré-requisitos:
#   1. GitHub CLI instalado (https://cli.github.com)
#   2. Autenticado com escopo de projeto:
#        gh auth login
#        gh auth refresh -s project,read:project
#   3. Rodar a partir de qualquer diretório (o script referencia o repo por owner/repo)
#
# Uso:
#   chmod +x scripts/setup_github_kanban.sh
#   ./scripts/setup_github_kanban.sh
#
# O script é seguro para reexecutar no que diz respeito a labels (usa --force).
# As issues NÃO são idempotentes: rodar o script duas vezes cria issues duplicadas.

set -euo pipefail

OWNER="naclarap"
REPO="Case-Vertice-Bootcamp"
REPO_FULL="${OWNER}/${REPO}"
PROJECT_TITLE="Kanban - Case Vértice"

command -v gh >/dev/null 2>&1 || { echo "Erro: gh CLI não encontrado. Instale em https://cli.github.com"; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "Erro: jq não encontrado (necessário para parsear saídas do gh)."; exit 1; }

echo "==> Repositório alvo: ${REPO_FULL}"
gh repo view "${REPO_FULL}" >/dev/null || { echo "Erro: não consegui acessar ${REPO_FULL}. Verifique 'gh auth status'."; exit 1; }

# ---------------------------------------------------------------------------
# 1) LABELS
# ---------------------------------------------------------------------------
echo "==> Criando labels..."

create_label() {
  local name="$1" color="$2" desc="$3"
  gh label create "$name" --repo "$REPO_FULL" --color "$color" --description "$desc" --force
}

# Fase (tons de roxo)
create_label "fase-0-definicao-problema" "5319e7" "Fase 0 — Definição do Problema"
create_label "fase-1-analise-hipoteses"  "7057ff" "Fase 1 — Análise de Hipóteses"
create_label "fase-2-prototipo-ia"       "9b7cf2" "Fase 2 — Protótipo de IA"
create_label "fase-3-narrativa-entrega"  "c4b5fd" "Fase 3 — Narrativa e Entrega"

# Tipo de trabalho (tons de laranja)
create_label "trabalho-individual"      "e85d04" "Tarefa a ser feita individualmente, antes de qualquer síntese em grupo"
create_label "trabalho-sintese-squad"   "fb8500" "Tarefa que exige reunião conjunta do squad"
create_label "trabalho-tecnico"         "ffb703" "Tarefa de execução técnica"

# Responsável (tons de azul)
create_label "owner-ana-clara" "0d419d" "Responsável: Ana Clara"
create_label "owner-lorenzo"   "1f6feb" "Responsável: Lorenzo"
create_label "owner-julia"     "58a6ff" "Responsável: Julia"
create_label "owner-squad"     "a5d6ff" "Responsável: squad inteiro"

# Prioridade (verde/amarelo/vermelho)
create_label "prioridade-alta"  "d73a4a" "Prioridade alta"
create_label "prioridade-media" "fbca04" "Prioridade média"
create_label "prioridade-baixa" "2ea44f" "Prioridade baixa"

echo "==> Labels prontas."

# ---------------------------------------------------------------------------
# 2) ISSUES
# ---------------------------------------------------------------------------
echo "==> Criando issues do backlog..."

TITLES=()
LABELS=()
DESCS=()
METODOS=()
PRAZOS=()
CRITERIOS=()

add_issue() {
  TITLES+=("$1")
  LABELS+=("$2")
  DESCS+=("$3")
  METODOS+=("$4")
  PRAZOS+=("$5")
  CRITERIOS+=("$6")
}

# --- FASE 0 ---
add_issue \
  '[Individual] Ana Clara — versão própria da árvore de hipóteses (estruturada em MECE)' \
  'fase-0-definicao-problema,trabalho-individual,owner-ana-clara,prioridade-alta' \
  'Construir individualmente uma árvore de hipóteses ancorada na fórmula de margem de contribuição (Receita Bruta − Desconto − Perda por Devolução − Custo do Produto − Custo do Frete), MECE (mutuamente exclusiva, coletivamente exaustiva).' \
  'Pensar sozinha antes da reunião de squad, sem consultar as versões dos colegas ainda, para gerar diversidade de raciocínio antes da síntese.' \
  'antes da reunião de segunda-feira' \
  'Árvore individual pronta com pelo menos uma hipótese por ramo da fórmula'

add_issue \
  '[Individual] Lorenzo — versão própria da árvore de hipóteses (estruturada em MECE)' \
  'fase-0-definicao-problema,trabalho-individual,owner-lorenzo,prioridade-alta' \
  'Mesma tarefa do card anterior, feita de forma independente.' \
  'Pensar sozinho antes da reunião de squad.' \
  'antes da reunião de segunda-feira' \
  'Árvore individual pronta com pelo menos uma hipótese por ramo da fórmula'

add_issue \
  '[Individual] Julia — versão própria da árvore de hipóteses (estruturada em MECE)' \
  'fase-0-definicao-problema,trabalho-individual,owner-julia,prioridade-alta' \
  'Mesma tarefa, sob a ótica de experiência do cliente/atendimento — trazer também um olhar de quem vai comunicar isso depois.' \
  'Pensar sozinho(a) antes da reunião de squad.' \
  'antes da reunião de segunda-feira' \
  'Árvore individual pronta com pelo menos uma hipótese por ramo da fórmula'

add_issue \
  '[Síntese] Reunião de segunda-feira — consolidar árvore de hipóteses única do squad' \
  'fase-0-definicao-problema,trabalho-sintese-squad,owner-squad,prioridade-alta' \
  'Debater as 3 versões individuais e chegar em uma única árvore de hipóteses acordada pelo squad, com os 5 ramos da fórmula de margem.' \
  'Comparar as 3 versões, discutir divergências, sintetizar. Não usar dados fragmentados/atendimento como ramo principal — tratar como proxy dentro dos ramos da fórmula.' \
  'segunda-feira' \
  'Árvore de hipóteses única, aprovada pelos 3, documentada em arquivo compartilhado'

add_issue \
  'Formalizar definição do problema central (com prazo de 90 dias)' \
  'fase-0-definicao-problema,trabalho-sintese-squad,owner-squad,prioridade-alta' \
  'Escrever a declaração do problema explicitando o delimitador de tempo, conforme orientação do mentor.' \
  '"Como aumentar a margem de contribuição da Vértice Retail dentro do horizonte de 90 dias?" — usar essa frase como ponto de partida de toda a análise.' \
  'segunda-feira' \
  'Frase do problema central escrita e usada como cabeçalho de todos os documentos do projeto'

# --- FASE 1 ---
add_issue \
  'Recalcular tendência de margem ao longo do tempo (inclinação, não média)' \
  'fase-1-analise-hipoteses,trabalho-tecnico,owner-ana-clara,prioridade-alta' \
  'Verificar se a margem está de fato caindo, subindo, ou andando de lado — calculando a inclinação da curva mês a mês, não apenas a média do período.' \
  'Conforme orientado pelo mentor: "às vezes tem subida, tem descida, mas quando você olha um espaço de tempo maior, tá andando de lado" — medir o delta ao longo do tempo.' \
  '3 dias após a reunião de segunda' \
  'Gráfico de tendência com inclinação calculada e conclusão clara (caindo / estável / subindo)'

add_issue \
  '[Individual] Testar ramo Receita Bruta' \
  'fase-1-analise-hipoteses,trabalho-individual,owner-ana-clara,prioridade-alta' \
  'Investigar o que compõe e influencia a receita bruta (canal, categoria, sazonalidade).' \
  '-' \
  '4 dias após a reunião de segunda' \
  'Achados documentados com evidência de dados'

add_issue \
  '[Individual] Testar ramo Desconto' \
  'fase-1-analise-hipoteses,trabalho-individual,owner-lorenzo,prioridade-alta' \
  'Investigar se é possível reduzir desconto sem perder volume de vendas.' \
  '-' \
  '4 dias após a reunião de segunda' \
  'Achados documentados com evidência de dados'

add_issue \
  '[Individual] Testar ramo Perda por Devolução (usando atendimento como proxy)' \
  'fase-1-analise-hipoteses,trabalho-individual,owner-julia,prioridade-alta' \
  'Investigar indicadores de devolução, usando dados de atendimento.csv (categoria de problema, ex. "produto com defeito") como proxy, já que pode não haver dado direto de perda por devolução cruzado com todas as bases.' \
  'Conforme exemplo do mentor — usar volume de tickets sobre defeito/tamanho errado como proxy de perda por devolução.' \
  '4 dias após a reunião de segunda' \
  'Achados documentados, com a premissa do proxy explicitada'

add_issue \
  'Testar ramo Custo do Produto' \
  'fase-1-analise-hipoteses,trabalho-tecnico,owner-ana-clara,prioridade-media' \
  'Investigar se há oportunidade de redução de custo do produto por categoria/fornecedor.' \
  '-' \
  '4 dias após a reunião de segunda' \
  'Achados documentados com evidência de dados'

add_issue \
  'Testar ramo Custo do Frete' \
  'fase-1-analise-hipoteses,trabalho-tecnico,owner-lorenzo,prioridade-media' \
  'Investigar oportunidades de redução de custo de frete (transportadora, região, prazo de entrega).' \
  '-' \
  '4 dias após a reunião de segunda' \
  'Achados documentados com evidência de dados'

add_issue \
  'Documentar premissas e proxies utilizados (gaps entre bases de dados)' \
  'fase-1-analise-hipoteses,trabalho-tecnico,owner-squad,prioridade-media' \
  'Listar explicitamente onde os dados são incompletos ou os períodos das bases não cruzam entre si, e quais proxies foram adotados para contornar isso.' \
  'Conforme orientado — deixar isso claro como premissa na apresentação, não escondido.' \
  '5 dias após a reunião de segunda' \
  'Lista de premissas e proxies documentada'

add_issue \
  '[Síntese] Reunião de squad — consolidar achados e priorizar por impacto (80/20)' \
  'fase-1-analise-hipoteses,trabalho-sintese-squad,owner-squad,prioridade-alta' \
  'Reunir os achados dos 5 ramos e priorizar onde está o maior gargalo, usando a regra de Pareto.' \
  'Focar esforço no(s) ramo(s) de maior impacto identificado, não tentar resolver todos igualmente.' \
  '6 dias após a reunião de segunda' \
  'Ramo(s) prioritário(s) definido(s) e acordado(s) pelo squad, com justificativa'

add_issue \
  'Artefato de processo — relatório de EDA consolidado (.md/.pdf)' \
  'fase-1-analise-hipoteses,trabalho-tecnico,owner-ana-clara,prioridade-media' \
  'Documentar toda a análise exploratória, achados por ramo, premissas e priorização final para rastreabilidade (entrega obrigatória do case).' \
  '-' \
  '6 dias após a reunião de segunda' \
  'Arquivo salvo com todos os achados e o racional de priorização'

# --- FASE 2 ---
add_issue \
  'Escolher e justificar o módulo de IA com base no ramo priorizado' \
  'fase-2-prototipo-ia,trabalho-sintese-squad,owner-squad,prioridade-alta' \
  'Definir entre Módulo A (funil/canais), B (classificador de atendimento), C (priorização), D (relatório automático) ou combinação/módulo próprio, com base no ramo de maior impacto identificado na Fase 1.' \
  '-' \
  'a definir conforme calendário do bootcamp' \
  'Módulo escolhido e justificado por escrito, ligado diretamente ao ramo priorizado da árvore de hipóteses'

add_issue \
  'Desenhar arquitetura do agente/protótipo' \
  'fase-2-prototipo-ia,trabalho-tecnico,owner-lorenzo,prioridade-alta' \
  'Definir fluxo de prompts, dados de entrada/saída, ferramentas necessárias.' \
  '-' \
  'a definir' \
  'Diagrama de fluxo do protótipo desenhado'

add_issue \
  'Implementar protótipo — versão inicial' \
  'fase-2-prototipo-ia,trabalho-tecnico,owner-lorenzo,prioridade-alta' \
  'Construir a primeira versão funcional do módulo escolhido.' \
  '-' \
  'a definir' \
  'Protótipo roda de ponta a ponta com dados de amostra'

add_issue \
  'Testar protótipo com amostra real dos dados' \
  'fase-2-prototipo-ia,trabalho-tecnico,owner-lorenzo,prioridade-alta' \
  'Rodar o protótipo em um subconjunto real do data room e avaliar qualidade.' \
  '-' \
  'a definir' \
  'Resultados de pelo menos 50 registros avaliados'

add_issue \
  'Validação e revisão crítica do protótipo' \
  'fase-2-prototipo-ia,trabalho-tecnico,owner-ana-clara,prioridade-media' \
  'Sanity checks, casos de erro e limites do modelo.' \
  '-' \
  'a definir' \
  'Lista de casos de falha documentada com plano de mitigação'

add_issue \
  'Artefato de processo — log de validação do protótipo (.md/.pdf)' \
  'fase-2-prototipo-ia,trabalho-tecnico,owner-lorenzo,prioridade-media' \
  'Documentar testes, validações e outputs intermediários do agente.' \
  '-' \
  'a definir' \
  'Arquivo salvo com evidências do processo de validação'

add_issue \
  'Construir dashboard de gestão' \
  'fase-2-prototipo-ia,trabalho-tecnico,owner-ana-clara,prioridade-alta' \
  'Painel com os indicadores executivos ligados ao ramo priorizado da fórmula de margem.' \
  '-' \
  'a definir' \
  'Dashboard navegável com os KPIs principais'

# --- FASE 3 ---
add_issue \
  'Montar business case' \
  'fase-3-narrativa-entrega,trabalho-tecnico,owner-ana-clara,prioridade-alta' \
  'Estimar impacto financeiro (margem recuperada, economia, payback) dentro do horizonte de 90 dias.' \
  '-' \
  'a definir' \
  'Números de impacto estimado com premissas explícitas'

add_issue \
  'Montar roadmap 30-60-90 dias' \
  'fase-3-narrativa-entrega,trabalho-sintese-squad,owner-squad,prioridade-alta' \
  'Plano de implementação com quick wins nos primeiros 30 dias, iniciativas estruturais até 60, e resultado consolidado até 90.' \
  'Conforme orientado pelo mentor — o roadmap só pode ser definido depois que a solução estiver escolhida, não antes.' \
  'a definir' \
  'Roadmap visual com as 3 fases e responsáveis definidos'

add_issue \
  'Levantar riscos e plano de governança' \
  'fase-3-narrativa-entrega,trabalho-tecnico,owner-lorenzo,prioridade-media' \
  'Riscos de dados, viés, alucinação e adoção pelo time, com controles propostos.' \
  '-' \
  'a definir' \
  'Lista de riscos com mitigação correspondente'

add_issue \
  'Estruturar narrativa da apresentação final (roteiro de 11 slides)' \
  'fase-3-narrativa-entrega,trabalho-sintese-squad,owner-julia,prioridade-alta' \
  'Costurar problema (com prazo de 90 dias), árvore de hipóteses, insights, priorização, solução, demonstração, business case, roadmap e recomendação final.' \
  '-' \
  'a definir' \
  'Roteiro completo dos 11 slides com conteúdo definido'

add_issue \
  'Design visual da apresentação' \
  'fase-3-narrativa-entrega,trabalho-tecnico,owner-julia,prioridade-alta' \
  'Hierarquia visual, gráficos (incluindo o gráfico de tendência de margem), foco em decisão.' \
  '-' \
  'a definir' \
  'Slides finalizados visualmente'

add_issue \
  'Preparar demonstração ao vivo (protótipo/dashboard)' \
  'fase-3-narrativa-entrega,trabalho-tecnico,owner-lorenzo,prioridade-alta' \
  'Garantir que a demonstração funcione sem falhas ao vivo, com plano B.' \
  '-' \
  'a definir' \
  'Demonstração testada e com plano B caso falhe'

add_issue \
  'Ensaio geral da apresentação' \
  'fase-3-narrativa-entrega,trabalho-sintese-squad,owner-squad,prioridade-alta' \
  'Treinar timing e divisão de fala entre os 3 membros do squad.' \
  '-' \
  'a definir' \
  'Apresentação completa ensaiada dentro do tempo permitido'

add_issue \
  'Organizar e revisar artefatos de processo para entrega' \
  'fase-3-narrativa-entrega,trabalho-sintese-squad,owner-squad,prioridade-alta' \
  'Reunir relatórios, validações, cálculos e análises parciais em .md/.pdf/.html (obrigatório pelo case).' \
  '-' \
  'a definir' \
  'Pasta de entrega completa e revisada'

add_issue \
  'Pitch Final' \
  'fase-3-narrativa-entrega,trabalho-sintese-squad,owner-squad,prioridade-alta' \
  'Apresentação da solução completa à banca do EloGroup.' \
  '-' \
  '14/09' \
  'Apresentação realizada'

ISSUE_URLS=()

for i in "${!TITLES[@]}"; do
  title="${TITLES[$i]}"
  labels="${LABELS[$i]}"
  body="## Descrição
${DESCS[$i]}

## Método
${METODOS[$i]}

## Prazo
${PRAZOS[$i]}

## Critério de \"Pronto\"
- [ ] ${CRITERIOS[$i]}"

  echo "  -> Criando issue: ${title}"
  url=$(gh issue create --repo "$REPO_FULL" --title "$title" --label "$labels" --body "$body")
  ISSUE_URLS+=("$url")
done

echo "==> ${#ISSUE_URLS[@]} issues criadas."

# ---------------------------------------------------------------------------
# 3) GITHUB PROJECT V2 ("Kanban - Case Vértice")
# ---------------------------------------------------------------------------
echo "==> Criando Project v2 '${PROJECT_TITLE}'..."

PROJECT_URL=$(gh project create --owner "$OWNER" --title "$PROJECT_TITLE" --format json --jq '.url')
PROJECT_NUMBER=$(basename "$PROJECT_URL")
echo "    Project criado: ${PROJECT_URL} (número ${PROJECT_NUMBER})"

PROJECT_ID=$(gh project view "$PROJECT_NUMBER" --owner "$OWNER" --format json --jq '.id')

FIELDS_JSON=$(gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --format json)
STATUS_FIELD_ID=$(echo "$FIELDS_JSON" | jq -r '.fields[] | select(.name=="Status") | .id')
TODO_OPTION_ID=$(echo "$FIELDS_JSON" | jq -r '.fields[] | select(.name=="Status") | .options[] | select(.name=="Todo") | .id')

echo "==> Adicionando as ${#ISSUE_URLS[@]} issues ao Project, na coluna Backlog (= 'Todo' antes de você renomear as opções)..."
for url in "${ISSUE_URLS[@]}"; do
  item_id=$(gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "$url" --format json --jq '.id')
  if [[ -n "$STATUS_FIELD_ID" && -n "$TODO_OPTION_ID" ]]; then
    gh project item-edit --id "$item_id" --project-id "$PROJECT_ID" --field-id "$STATUS_FIELD_ID" --single-select-option-id "$TODO_OPTION_ID" >/dev/null
  fi
done

echo ""
echo "======================================================================"
echo " Concluído. Repositório, labels, issues e Project v2 provisionados."
echo ""
echo " PASSOS MANUAIS RESTANTES (a API do GitHub não expõe isso):"
echo ""
echo " 1. Abra ${PROJECT_URL} > Settings do campo 'Status' e:"
echo "      - Renomeie 'Todo'        -> 'Backlog'"
echo "      - Renomeie 'In Progress' -> 'Em Andamento'"
echo "      - Adicione uma opção nova -> 'Em Revisão' (entre Em Andamento e Done)"
echo "      - Renomeie 'Done'        -> 'Pronto'"
echo "    (Renomear preserva o id da opção, então as issues já adicionadas"
echo "     continuam corretamente na antiga coluna 'Todo' = 'Backlog'.)"
echo ""
echo " 2. Crie a view de board por Status:"
echo "      - A view padrão 'Board' já agrupa por Status. Confirme o agrupamento"
echo "        em '... > Group by > Status' se não vier assim por padrão."
echo ""
echo " 3. Crie a 2ª view (agrupada por Fase):"
echo "      - '+ New view' > Board (ou Table) > '... > Group by' > escolha o"
echo "        campo de label (ou crie um campo 'Fase' e associe via label) >"
echo "        selecione as labels fase-0-definicao-problema, fase-1-analise-hipoteses,"
echo "        fase-2-prototipo-ia, fase-3-narrativa-entrega."
echo "      - Nomeie a view como 'Por Fase'."
echo ""
echo " 4. Crie a 3ª view (agrupada por Tipo de trabalho):"
echo "      - '+ New view' > Board > Group by label > selecione"
echo "        trabalho-individual, trabalho-sintese-squad, trabalho-tecnico."
echo "      - Nomeie a view como 'Por Tipo de Trabalho'."
echo ""
echo " 5. Convide os colaboradores (permissão de escrita):"
echo "      gh api repos/${REPO_FULL}/collaborators/<username> -X PUT -f permission=push"
echo "======================================================================"
