#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T web python -m app.cli backup
git pull --ff-only
docker compose build
docker compose stop worker web
docker compose run --rm --no-deps migrate
docker compose up -d
docker compose ps
