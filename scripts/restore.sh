#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
name="${1:?Укажите имя копии из data/backups, например panel-123.sqlite3}"
[[ "$name" =~ ^panel-[0-9]+\.sqlite3$ ]] || { echo 'Некорректное имя'; exit 1; }
[[ -f "data/backups/$name" ]] || { echo 'Копия не найдена'; exit 1; }
read -r -p 'Восстановить SQLite? Изменения после копии будут потеряны. Введите RESTORE: ' answer
[[ "$answer" == RESTORE ]] || exit 1
docker compose stop worker web
# Failure deliberately leaves services stopped: inspect logs and rerun or restart explicitly.
docker compose run --rm --no-deps web python -m app.cli restore "/data/backups/$name"
docker compose run --rm --no-deps migrate
docker compose up -d
echo 'Восстановлено. Сессии администратора сброшены. Проверьте статусы применения.'
