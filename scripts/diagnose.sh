#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
docker compose ps
systemctl is-active xray || true
ss -ltn '( sport = :443 or sport = :8000 or sport = :10085 )'
df -h ./data
curl --fail --silent http://127.0.0.1:8000/health
printf '\n'
docker compose exec -T web python -m app.cli smoke
echo 'Ожидается: 8000 и 10085 только 127.0.0.1; 443 — действующий Xray.'
