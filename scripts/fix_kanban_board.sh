#!/usr/bin/env bash
#
# Corrige o Project v2 "Kanban - Case Vértice":
#   1. Remove do board as issues antigas (#1-#30, já fechadas / substituídas
#      pelo plano atualizado) — elas continuam fechadas no repositório,
#      só saem do quadro.
#   2. Adiciona ao board as issues atuais (#31-#40) na coluna "Backlog".
#
# Pré-requisitos: os mesmos do setup_github_kanban.sh (gh + jq, autenticado
# com escopo 'project').
#
# Uso:
#   chmod +x scripts/fix_kanban_board.sh
#   ./scripts/fix_kanban_board.sh

set -euo pipefail

OWNER="naclarap"
REPO="Case-Vertice-Bootcamp"
REPO_FULL="${OWNER}/${REPO}"
PROJECT_TITLE="Kanban - Case Vértice"

command -v gh >/dev/null 2>&1 || { echo "Erro: gh CLI não encontrado."; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "Erro: jq não encontrado."; exit 1; }

PROJECT_NUMBER=$(gh project list --owner "$OWNER" --format json --jq ".projects[] | select(.title==\"${PROJECT_TITLE}\") | .number")
[ -n "$PROJECT_NUMBER" ] || { echo "Erro: não encontrei o project '${PROJECT_TITLE}' em ${OWNER}."; exit 1; }
echo "==> Project encontrado: número ${PROJECT_NUMBER}"

PROJECT_ID=$(gh project view "$PROJECT_NUMBER" --owner "$OWNER" --format json --jq '.id')

# ---------------------------------------------------------------------------
# 1) Remover issues #1-#30 (backlog antigo) do board
# ---------------------------------------------------------------------------
echo "==> Removendo issues antigas (#1-#30) do board..."

ITEMS_JSON=$(gh project item-list "$PROJECT_NUMBER" --owner "$OWNER" --format json --limit 200)

for n in $(seq 1 30); do
  item_id=$(echo "$ITEMS_JSON" | jq -r ".items[] | select(.content.number==${n} and .content.repository==\"${REPO_FULL}\") | .id")
  if [ -n "$item_id" ]; then
    echo "  -> Removendo issue #${n} (item ${item_id})"
    gh project item-delete "$PROJECT_NUMBER" --owner "$OWNER" --id "$item_id" >/dev/null
  fi
done

# ---------------------------------------------------------------------------
# 2) Adicionar issues #31-#40 (plano atual) ao board, na coluna Backlog
# ---------------------------------------------------------------------------
echo "==> Adicionando issues atuais (#31-#40) ao board, na coluna Backlog..."

FIELDS_JSON=$(gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --format json)
STATUS_FIELD_ID=$(echo "$FIELDS_JSON" | jq -r '.fields[] | select(.name=="Status") | .id')
BACKLOG_OPTION_ID=$(echo "$FIELDS_JSON" | jq -r '.fields[] | select(.name=="Status") | .options[] | select(.name=="Backlog") | .id')

if [ -z "$BACKLOG_OPTION_ID" ]; then
  echo "Aviso: não encontrei a opção 'Backlog' no campo Status. Ajuste o nome no script se você chamou a coluna de outra forma."
fi

for n in $(seq 31 40); do
  url="https://github.com/${REPO_FULL}/issues/${n}"
  echo "  -> Adicionando issue #${n}"
  item_id=$(gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "$url" --format json --jq '.id')
  if [[ -n "$STATUS_FIELD_ID" && -n "$BACKLOG_OPTION_ID" ]]; then
    gh project item-edit --id "$item_id" --project-id "$PROJECT_ID" --field-id "$STATUS_FIELD_ID" --single-select-option-id "$BACKLOG_OPTION_ID" >/dev/null
  fi
done

echo "==> Pronto. Board limpo: só as 10 issues atuais (#31-#40), todas em Backlog."
