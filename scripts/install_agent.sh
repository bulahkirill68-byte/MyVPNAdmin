#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo 'Запустите sudo bash scripts/install_agent.sh'; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-cryptography >/dev/null
install -d -o root -g root -m 755 /opt/reality-agent
install -o root -g root -m 644 host/agent.py /opt/reality-agent/agent.py
install -o root -g root -m 700 host/install_xray_reality.sh /opt/reality-agent/install_xray_reality.sh
install -o root -g root -m 644 host/reality-agent.service /etc/systemd/system/reality-agent.service
systemctl daemon-reload
systemctl enable --now reality-agent
systemctl restart reality-agent
echo 'Хостовый агент готов. Xray не изменён; установка/подготовка запускается из панели.'
