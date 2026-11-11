#!/usr/bin/env bash
# Opt-in public browser access; Xray TCP 443 stays on the host untouched.
set -Eeuo pipefail
umask 022
cd "$(dirname "$0")/.."
[[ $EUID -eq 0 ]] || { echo 'Запустите от root'; exit 1; }
IP="${1:?Укажите публичный IPv4 VPS}"
PORT="${2:-8443}"
python3 - "$IP" "$PORT" <<'PY'
import ipaddress,sys
assert ipaddress.IPv4Address(sys.argv[1]).is_global
port=int(sys.argv[2]); assert 1024<=port<=65535 and port not in (8000,10085)
PY
if ss -ltnH "( sport = :$PORT )" | grep -q . && [[ ! -f /etc/nginx/conf.d/reality-panel-https.conf ]]; then
  echo 'Порт уже занят другим приложением'; exit 1
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx python3-venv python3-cryptography openssl ca-certificates >/dev/null
install -d -m 755 /opt/reality-public /var/lib/reality-acme-web/.well-known/acme-challenge
install -m 644 public/https_control.py /opt/reality-public/https_control.py
if [[ ! -x /opt/reality-certbot/bin/certbot ]]; then
  python3 -m venv /opt/reality-certbot
  /opt/reality-certbot/bin/pip install 'certbot>=5.4,<6'
fi
nginx -t
systemctl enable --now nginx
python3 /opt/reality-public/https_control.py init --ip "$IP" --port "$PORT"
if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
  ufw allow 80/tcp comment 'Reality ACME IP certificate'
  ufw allow "$PORT/tcp" comment 'Reality HTTPS admin panel'
fi
# ACME webroot supports IP identifiers in Certbot >=5.4. No untrusted/self-signed fallback.
/opt/reality-certbot/bin/certbot certonly --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring \
  --preferred-profile shortlived --webroot --webroot-path /var/lib/reality-acme-web \
  --ip-address "$IP" --cert-name reality-ip \
  --config-dir /etc/reality-control/acme --work-dir /var/lib/reality-acme --logs-dir /var/log/reality-acme
python3 - "$IP" "$PORT" <<'PY'
import pathlib,sys
p=pathlib.Path('.env'); lines=p.read_text().splitlines() if p.exists() else []
lines=[x for x in lines if not x.startswith(('PUBLIC_ORIGIN=','COOKIE_SECURE='))]
lines += ['COOKIE_SECURE=true',f'PUBLIC_ORIGIN=https://{sys.argv[1]}:{sys.argv[2]}']
p.write_text('\n'.join(lines)+'\n'); p.chmod(0o600)
PY
docker compose up -d --no-deps --force-recreate --wait web
python3 /opt/reality-public/https_control.py refresh
install -m 644 public/reality-public-{renew,guard}.{service,timer} /etc/systemd/system/
install -d -m 755 /etc/systemd/system/nginx.service.d
printf '[Service]\nExecStartPre=/usr/bin/python3 /opt/reality-public/https_control.py prepare\n' \
  > /etc/systemd/system/nginx.service.d/reality-public.conf
systemctl daemon-reload
systemctl enable --now reality-public-renew.timer reality-public-guard.timer
echo "Панель: https://$IP:$PORT — SSH-туннель больше не требуется."
