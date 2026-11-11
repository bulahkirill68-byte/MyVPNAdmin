#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo 'Запустите: sudo bash scripts/install.sh'; exit 1; }
command -v docker >/dev/null || { echo 'Установите Docker Engine и Compose plugin по docs.docker.com/engine/install/ubuntu/'; exit 1; }
docker compose version
[[ -e .env ]] || cp .env.example .env
chmod 600 .env
if [[ -L data ]]; then echo 'data не должен быть символической ссылкой'; exit 1; fi
mkdir -p data
chown 10001:10001 data
chmod 700 data
bash scripts/install_agent.sh
docker compose config --quiet
docker compose up -d --build
echo 'Панель запущена на 127.0.0.1:8000. Создайте администратора:'
echo 'docker compose exec web python -m app.cli admin'
echo 'Далее импортируйте Xray по README. Xray не изменён.'
