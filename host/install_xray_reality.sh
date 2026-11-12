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
cleanup() {
  code=$?
  trap - EXIT
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
# The official installer creates {}. The same guarded initializer also resumes interrupted installs.
# Python X25519 generation avoids version-dependent parsing of `xray x25519` output labels.
python3 "$(dirname "$0")/agent.py" initialize --ip "$IP" --sni "$TARGET"
