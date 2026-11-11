#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo 'Запустите sudo bash scripts/update.sh'; exit 1; }
if [[ -f /root/.ssh/reality-control-config ]]; then
  export GIT_SSH_COMMAND='ssh -F /root/.ssh/reality-control-config'
fi
docker compose exec -T web python -m app.cli backup
git pull --ff-only
docker compose build
bash scripts/install_agent.sh
docker compose stop worker web
docker compose run --rm --no-deps migrate
docker compose up -d
docker compose ps
