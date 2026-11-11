#!/usr/bin/env bash
# Embedded fresh-install path based on the supplied install_xray_reality.sh.
# Existing installations are deliberately handled by the read/backup/test/rollback host-agent operation.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запускается только host-agent от root'; exit 1; }
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID =~ ^(22.04|24.04|26.04)$ ]] || { echo 'Нужна Ubuntu 22.04/24.04/26.04'; exit 1; }
IP='' TARGET='' YES=0
while (( $# )); do
  case "$1" in
    --yes) YES=1; shift;;
    --ip) IP="${2:?}"; shift 2;;
    --target) TARGET="${2:?}"; shift 2;;
    *) echo 'Недопустимый аргумент'; exit 1;;
  esac
done
[[ $YES == 1 && -n $IP && -n $TARGET ]] || exit 1
[[ ! -e /usr/local/etc/xray/config.json && ! -L /usr/local/etc/xray/config.json ]] || { echo 'Существующий config.json не заменяется'; exit 1; }
! command -v xray >/dev/null || { echo 'Xray уже установлен'; exit 1; }
python3 - "$IP" "$TARGET" <<'PY'
import ipaddress,re,sys
assert ipaddress.IPv4Address(sys.argv[1]).is_global
assert '.' in sys.argv[2] and len(sys.argv[2])<=253
assert all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',x) for x in sys.argv[2].split('.'))
PY
if ss -ltnH '( sport = :443 or sport = :10085 )' | grep -q .; then echo '443 или 10085 уже занят'; exit 1; fi
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates openssl python3 iproute2 unzip >/dev/null
TMP=$(mktemp -d)
CONFIG=/usr/local/etc/xray/config.json
TOUCHED=0
cleanup() {
  code=$?
  trap - EXIT
  if (( code != 0 && TOUCHED )); then
    systemctl stop xray || true
    # Only the file created by this invocation can be removed; no replace mode exists.
    rm -f -- "$CONFIG"
  fi
  rm -rf -- "$TMP"
  exit "$code"
}
trap cleanup EXIT
timeout 20 openssl s_client -connect "$TARGET:443" -servername "$TARGET" -tls1_3 -alpn h2 -verify_return_error </dev/null >"$TMP/tls" 2>&1 || true
grep -q 'Verify return code: 0 (ok)' "$TMP/tls" || { echo 'Ошибка проверки TLS target'; exit 1; }
grep -q 'ALPN protocol: h2' "$TMP/tls" || { echo 'Target не поддерживает h2'; exit 1; }
curl -4fL --retry 3 --connect-timeout 12 --max-time 120 https://raw.githubusercontent.com/XTLS/Xray-install/main/install-release.sh -o "$TMP/install.sh"
bash -n "$TMP/install.sh"
# A dedicated non-login user ensures predictable config permissions even if the official default changes.
id xray >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin xray
bash "$TMP/install.sh" install
xray uuid > "$TMP/uuid"
xray x25519 > "$TMP/keys"
openssl rand -hex 8 > "$TMP/sid"
python3 - "$TMP" "$IP" "$TARGET" <<'PY'
import json,pathlib,re,sys
p=pathlib.Path(sys.argv[1]); uid=(p/'uuid').read_text().strip(); keys=(p/'keys').read_text()
private=re.search(r'PrivateKey:\s*(\S+)',keys).group(1)
public=re.search(r'(?:Password|PublicKey|Public key):\s*(\S+)',keys).group(1)
sid=(p/'sid').read_text().strip(); target=sys.argv[3]
config={'log':{'loglevel':'warning'},'api':{'tag':'api','listen':'127.0.0.1:10085','services':['HandlerService','StatsService']},
 'stats':{},'policy':{'levels':{'0':{'statsUserUplink':True,'statsUserDownlink':True}}},
 'inbounds':[{'tag':'vless-reality','listen':'0.0.0.0','port':443,'protocol':'vless',
 'settings':{'clients':[{'id':uid,'email':'first-user@local.invalid','level':0,'flow':'xtls-rprx-vision'}],'decryption':'none'},
 'streamSettings':{'network':'raw','security':'reality','realitySettings':{'show':False,'target':target+':443',
 'xver':0,'serverNames':[target],'privateKey':private,'shortIds':[sid]}}}], 'outbounds':[{'tag':'direct','protocol':'freedom'}]}
(p/'config.json').write_text(json.dumps(config,indent=2))
(p/'access.txt').write_text(f'Server IPv4: {sys.argv[2]}\nUUID: {uid}\nPublic Key: {public}\nShort ID: {sid}\nSNI: {target}\n')
PY
xray run -test -config "$TMP/config.json"
# The official installer may have created an empty config. Never use this script on an existing Xray.
install -o root -g xray -m 640 "$TMP/config.json" "$CONFIG"
TOUCHED=1
install -o root -g root -m 600 "$TMP/access.txt" "/root/xray-reality-access-$(date -u +%Y%m%dT%H%M%SZ).txt"
systemctl enable xray
systemctl restart xray
sleep 2
systemctl is-active --quiet xray
ss -ltnH '( sport = :443 )' | grep -q .
TOUCHED=0
echo 'Xray установлен; приватные данные сохранены только в root-файлах.'
