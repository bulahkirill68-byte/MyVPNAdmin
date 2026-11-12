#!/usr/bin/env python3
"""Root host bridge: fixed Xray setup operations over a peer-checked Unix socket, no shell API."""
import base64
import argparse
import copy
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import socketserver
import stat
import struct
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit
from urllib.parse import urlencode

CONFIG = Path("/usr/local/etc/xray/config.json")
STATE = Path("/var/lib/reality-agent")
BACKUPS = Path("/var/backups/reality-agent")
SOCKET = Path("/run/reality-agent/control.sock")
INSTALLER = Path(__file__).with_name("install_xray_reality.sh")
LOCK = threading.Lock()
MAX_BODY = 4096
ACCESS_DIRECTORY = Path('/root')


def run(args, timeout=30):
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise
    if process.returncode:
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        logfile = STATE / "last-error.log"
        logfile.write_text((stdout + "\n" + stderr)[-65536:], encoding="utf-8")
        logfile.chmod(0o600)
        raise subprocess.CalledProcessError(process.returncode, args)
    return stdout


def validate_input(data):
    if set(data) - {"ip", "sni", "confirm"} or data.get("confirm") is not True:
        raise ValueError("Требуется явное подтверждение")
    address = ipaddress.IPv4Address(data["ip"])
    if not address.is_global:
        raise ValueError("Требуется публичный IPv4")
    target = data.get("sni", "www.wikipedia.org").rstrip(".").encode("idna").decode("ascii")
    if len(target) > 253 or "." not in target or any(
        not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
        for label in target.split(".")
    ):
        raise ValueError("Некорректный SNI")
    return str(address), target


def prepared_config(source):
    """Only management metadata is added; identity, REALITY, transports and outbounds are preserved."""
    config = copy.deepcopy(source)
    inbound = next((i for i in config.get("inbounds", []) if i.get("tag") == "vless-reality"), None)
    if not inbound or inbound.get("protocol") != "vless":
        raise ValueError("Не найден inbound vless-reality / VLESS")
    if inbound.get("streamSettings", {}).get("security") != "reality":
        raise ValueError("Нужен существующий REALITY inbound")
    api = config.setdefault("api", {})
    if api.get("listen") not in (None, "127.0.0.1:10085"):
        raise ValueError("API уже использует другой адрес; требуется ручная проверка")
    api.update({"listen": "127.0.0.1:10085", "tag": api.get("tag", "api"),
                "services": sorted(set(api.get("services", []) + ["HandlerService", "StatsService"]))})
    config.setdefault("stats", {})
    levels = config.setdefault("policy", {}).setdefault("levels", {})
    seen = set()
    for index, client in enumerate(inbound["settings"]["clients"]):
        identity = str(uuid.UUID(client["id"]))
        level = client.get("level", 0)
        if level != 0 or client.get("flow") != "xtls-rprx-vision":
            raise ValueError("Импорт поддерживает level 0 и xtls-rprx-vision")
        if not client.get("email"):
            client["email"] = "first-user@local.invalid" if index == 0 else f"import-{identity}@local.invalid"
        if not re.fullmatch(r"[A-Za-z0-9_.@+-]{1,150}", client["email"]):
            raise ValueError("Некорректный email существующего пользователя")
        if client["email"].lower() in seen:
            raise ValueError("Дублирующийся email")
        seen.add(client["email"].lower())
        levels.setdefault(str(level), {}).update({"statsUserUplink": True, "statsUserDownlink": True})
    if not seen:
        raise ValueError("В inbound нет пользователей для первоначального импорта")
    return config


def public_key(private):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    key = X25519PrivateKey.from_private_bytes(base64.urlsafe_b64decode(private + "=" * (-len(private) % 4)))
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def onboarding(ip):
    ip, _ = validate_input({"ip": ip, "confirm": True})
    config = json.loads(CONFIG.read_text())
    prepared = prepared_config(config)
    if prepared != config:
        raise ValueError("Сначала подготовьте существующий Xray: API, email и статистика")
    inbound = next(i for i in config["inbounds"] if i.get("tag") == "vless-reality")
    reality = inbound["streamSettings"]["realitySettings"]
    return {"server": {"ip": ip, "port": int(inbound["port"]), "tag": inbound["tag"],
                       "sni": reality["serverNames"][0], "public_key": public_key(reality["privateKey"]),
                       "short_id": reality["shortIds"][0]},
            "users": [{"name": f"Импортированный · {i + 1}", "uuid": c["id"], "email": c["email"],
                       "expires_at": None} for i, c in enumerate(inbound["settings"]["clients"])]}


def service_is_canonical():
    """An empty default file is recoverable only for the known single-config systemd service."""
    try:
        result = subprocess.run(['systemctl', 'show', 'xray', '--property=ExecStart', '--value'],
                                capture_output=True, text=True, timeout=5, check=True).stdout
        match = re.search(r'argv\[\]=(.*?);', result)
        args = shlex.split(match.group(1)) if match else []
        return args == ['/usr/local/bin/xray', 'run', '-config', CONFIG.as_posix()]
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def configuration_state():
    installed = bool(shutil.which('xray'))
    result = {'installed': installed, 'config_exists': CONFIG.exists(),
              'has_managed_inbound': False, 'can_initialize': False}
    if CONFIG.is_symlink():
        return {**result, 'configuration': 'invalid', 'reason': 'config.json является symlink; нужна ручная проверка'}
    try:
        exists = CONFIG.exists()
        raw = CONFIG.read_text() if exists else ''
        data = (json.loads(raw) if raw.strip() else {}) if exists else None
    except (OSError, ValueError):
        return {**result, 'configuration': 'invalid', 'reason': 'Конфиг Xray не читается или не является JSON'}
    if not exists or data == {}:
        can_initialize = installed and service_is_canonical()
        return {**result, 'configuration': 'missing' if data is None else 'empty',
                'can_initialize': can_initialize,
                'reason': 'Бинарник установлен, но VLESS + REALITY ещё не настроен' if installed else 'Xray ещё не установлен'}
    inbounds = data.get('inbounds', []) if isinstance(data, dict) else []
    if isinstance(inbounds, list) and any(i.get('tag') == 'vless-reality' and i.get('protocol') == 'vless'
            and isinstance(i.get('streamSettings'), dict)
            and i.get('streamSettings', {}).get('security') == 'reality'
            for i in inbounds if isinstance(i, dict)):
        return {**result, 'configuration': 'managed', 'has_managed_inbound': True, 'reason': ''}
    return {**result, 'configuration': 'other',
            'reason': 'Конфиг не пустой, но inbound vless-reality / VLESS + REALITY не найден. Автозамена запрещена'}


def service_active():
    try:
        return subprocess.run(['systemctl', 'is-active', '--quiet', 'xray'],
                              capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def service_group():
    import pwd
    name = run(['systemctl', 'show', 'xray', '--property=User', '--value']).strip()
    if name not in ('xray', 'nobody'):
        raise ValueError('Ожидается служба Xray от непривилегированного пользователя xray/nobody')
    return pwd.getpwnam(name).pw_gid


def apply_config(updated, expected, permissions=None, require_port=None):
    if CONFIG.is_symlink() or (CONFIG.read_bytes() if CONFIG.exists() else None) != expected:
        raise ValueError('Конфиг изменился во время настройки; применение отменено')
    original = expected
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    if original is not None:
        backup = BACKUPS / f"config-{time.time_ns()}.json"
        backup.write_bytes(original)
        backup.chmod(0o600)
    info = CONFIG.stat() if CONFIG.exists() else None
    owner, group, mode = ((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) if info
                          else (0, service_group(), 0o640))
    restore_owner, restore_group, restore_mode = owner, group, mode
    if permissions is not None:
        owner, group, mode = permissions
    if not CONFIG.parent.exists():
        CONFIG.parent.mkdir(mode=0o750, parents=True)
        os.chown(CONFIG.parent, 0, group)
        CONFIG.parent.chmod(0o750)
    was_active = service_active()
    fd, filename = tempfile.mkstemp(prefix=".panel-", suffix=".json", dir=CONFIG.parent)
    candidate = Path(filename)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(updated, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(candidate, owner, group)
        candidate.chmod(mode)
        run(["/usr/local/bin/xray", "run", "-test", "-config", str(candidate)])
        if CONFIG.is_symlink() or (CONFIG.read_bytes() if CONFIG.exists() else None) != original:
            raise ValueError('Конфиг изменился во время проверки; применение отменено')
        os.replace(candidate, CONFIG)
        try:
            run(["systemctl", "restart", "xray"])
            run(["systemctl", "is-active", "--quiet", "xray"])
            for port in [10085, *([require_port] if require_port else [])]:
                for attempt in range(20):
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=1):
                            break
                    except OSError:
                        if attempt == 19:
                            raise
                        time.sleep(0.25)
        except Exception:
            # Atomic rollback to original bytes and permissions, no key regeneration.
            if original is None:
                CONFIG.unlink(missing_ok=True)
            else:
                candidate.write_bytes(original)
                os.chown(candidate, restore_owner, restore_group)
                candidate.chmod(restore_mode)
                os.replace(candidate, CONFIG)
            run(["systemctl", "restart" if was_active else "stop", "xray"])
            raise RuntimeError("Проверка службы не пройдена; исходный конфиг восстановлен") from None
    finally:
        candidate.unlink(missing_ok=True)


def prepare_existing():
    if CONFIG.is_symlink() or not CONFIG.is_file():
        raise ValueError('Нет обычного файла конфигурации Xray')
    original = CONFIG.read_bytes()
    updated = prepared_config(json.loads(original))
    if updated != json.loads(original):
        apply_config(updated, original)


def ensure_ports_free():
    for port in (443, 10085):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(('127.0.0.1', port))
        except OSError:
            raise ValueError(f'Порт {port} уже занят; существующая служба не заменяется') from None


def allow_vpn_port():
    if shutil.which('ufw') and 'Status: active' in run(['ufw', 'status']):
        run(['ufw', 'allow', '443/tcp', 'comment', 'Reality Xray'])


def initialize_empty(ip, target):
    """Finish an interrupted fresh install, but never rotate identities in a non-empty config."""
    ip, target = validate_input({'ip': ip, 'sni': target, 'confirm': True})
    state = configuration_state()
    if not state['can_initialize']:
        raise ValueError('Инициализация разрешена только для отсутствующего или строго пустого {} конфига штатной службы')
    original = CONFIG.read_bytes() if CONFIG.exists() else None
    # Validate identity/service permissions before generating or applying anything.
    group = service_group()
    ensure_ports_free()
    output = run(['openssl', 's_client', '-connect', target + ':443', '-servername', target,
                  '-tls1_3', '-alpn', 'h2', '-verify_return_error', '-verify_hostname', target], timeout=20)
    if 'Verify return code: 0 (ok)' not in output or 'ALPN protocol: h2' not in output:
        raise ValueError('Target должен иметь действительный TLS-сертификат, TLS 1.3 и ALPN h2')
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    private = X25519PrivateKey.generate()
    def encode(value):
        return base64.urlsafe_b64encode(value).decode().rstrip('=')
    private_value = encode(private.private_bytes(serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw, serialization.NoEncryption()))
    public_value = encode(private.public_key().public_bytes(serialization.Encoding.Raw,
        serialization.PublicFormat.Raw))
    identity, sid = str(uuid.uuid4()), os.urandom(8).hex()
    config = {'log': {'loglevel': 'warning'}, 'api': {'tag': 'api', 'listen': '127.0.0.1:10085',
              'services': ['HandlerService', 'StatsService']}, 'stats': {},
        'policy': {'levels': {'0': {'statsUserUplink': True, 'statsUserDownlink': True}}},
        'inbounds': [{'tag': 'vless-reality', 'listen': '0.0.0.0', 'port': 443, 'protocol': 'vless',
            'settings': {'clients': [{'id': identity, 'email': 'first-user@local.invalid',
                          'level': 0, 'flow': 'xtls-rprx-vision'}], 'decryption': 'none'},
            'streamSettings': {'network': 'raw', 'security': 'reality', 'realitySettings': {
                'show': False, 'target': target + ':443', 'xver': 0, 'serverNames': [target],
                'privateKey': private_value, 'shortIds': [sid]}}}],
        'outbounds': [{'tag': 'direct', 'protocol': 'freedom'}]}
    apply_config(config, original, permissions=(0, group, 0o640), require_port=443)
    allow_vpn_port()
    query = urlencode({'encryption': 'none', 'security': 'reality', 'type': 'tcp',
         'flow': 'xtls-rprx-vision', 'sni': target, 'fp': 'firefox', 'pbk': public_value, 'sid': sid})
    access = ACCESS_DIRECTORY / f'xray-reality-access-{time.time_ns()}.txt'
    access.write_text(f'Server IPv4: {ip}\nUUID: {identity}\nPublic Key: {public_value}\n'
                      f'Short ID: {sid}\nSNI: {target}\nvless://{identity}@{ip}:443?{query}#Xray-Reality\n')
    access.chmod(0o600)


def job_state():
    try:
        return json.loads((STATE / "job.json").read_text())
    except FileNotFoundError:
        return {"state": "idle"}


def save_job(value):
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = STATE / "job.tmp"
    temporary.write_text(json.dumps(value, ensure_ascii=False))
    temporary.chmod(0o600)
    os.replace(temporary, STATE / "job.json")


def start_job(operation, data):
    ip, sni = validate_input(data)
    if operation == "install" and (CONFIG.exists() or shutil.which("xray")):
        raise ValueError("Xray уже установлен. Используйте подготовку и импорт")
    if operation == "prepare" and not CONFIG.exists():
        raise ValueError("Сначала установите Xray")
    if operation == 'prepare' and not configuration_state()['has_managed_inbound']:
        raise ValueError('VLESS ещё не настроен. Для пустого конфига выберите «Завершить настройку VLESS + REALITY»')
    if operation == 'initialize' and not configuration_state()['can_initialize']:
        raise ValueError('Непустая или неизвестная конфигурация не заменяется')
    if not LOCK.acquire(blocking=False):
        raise ValueError("Другая задача уже выполняется")
    identifier = uuid.uuid4().hex
    try:
        save_job({"id": identifier, "state": "running", "operation": operation, "started": int(time.time())})
    except Exception:
        LOCK.release()
        raise

    def work():
        state = {"id": identifier, "operation": operation, "finished": 0}
        try:
            if operation == "install":
                run(["bash", str(INSTALLER), "--yes", "--ip", ip, "--target", sni], timeout=900)
            elif operation == 'initialize':
                initialize_empty(ip, sni)
            else:
                prepare_existing()
            onboarding(ip)  # Validate allowed export before marking success.
            state.update(state="succeeded", message="Xray готов к импорту в панель")
        except Exception as exc:
            # Installer output can contain secrets. Only safe errors leave the host.
            message = (str(exc) if isinstance(exc, (ValueError, RuntimeError)) else
                       'Ошибка системной команды. Подробности: /var/lib/reality-agent/last-error.log'
                       if isinstance(exc, subprocess.CalledProcessError) else type(exc).__name__)
            state.update(state="failed", message=message)
        finally:
            state["finished"] = int(time.time())
            try:
                save_job(state)
            finally:
                LOCK.release()
    threading.Thread(target=work, daemon=True).start()
    return {"id": identifier, "state": "running"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_request(self):
        self.connection.settimeout(10)
        _, uid, _ = struct.unpack("3i", self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid not in (0, 10001):
            self.reply(403, {"detail": "Недопустимый Unix peer"})
            return
        parsed = urlsplit(self.path)
        try:
            if self.command == "GET" and parsed.path == "/status":
                self.reply(200, {"version": "0.3.0", **configuration_state(), "job": job_state()})
            elif self.command == "GET" and parsed.path == "/onboarding":
                ip = parse_qs(parsed.query).get("ip", [""])[0]
                self.reply(200, onboarding(ip))
            elif self.command == "POST" and parsed.path in ("/install", "/prepare", "/initialize"):
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise ValueError("Некорректная длина запроса")
                data = json.loads(self.rfile.read(length))
                self.reply(202, start_job(parsed.path[1:], data))
            else:
                self.reply(404, {"detail": "Неизвестная операция"})
        except ValueError as error:
            self.reply(409, {"detail": str(error)})
        except (KeyError, StopIteration):
            self.reply(409, {"detail": "Операция отклонена: проверьте состояние Xray и параметры"})
        except Exception:
            self.reply(503, {"detail": "Хостовая операция недоступна; проверьте журнал агента"})

    do_GET = handle_request
    do_POST = handle_request


def main():
    if os.geteuid() != 0:
        raise SystemExit("Host agent requires root on the host, never in a container")
    parser = argparse.ArgumentParser()
    parser.add_argument('command', nargs='?', choices=['initialize', 'status'])
    parser.add_argument('--ip')
    parser.add_argument('--sni', default='www.wikipedia.org')
    args = parser.parse_args()
    if args.command == 'status':
        print(json.dumps(configuration_state(), ensure_ascii=False))
        return
    if args.command == 'initialize':
        initialize_empty(args.ip, args.sni)
        if job_state().get('state') != 'running':
            save_job({'id': uuid.uuid4().hex, 'operation': 'initialize', 'state': 'succeeded',
                      'finished': int(time.time()), 'message': 'Xray готов к импорту в панель'})
        print('VLESS + REALITY настроен; данные доступа сохранены в /root, fp=firefox')
        return
    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True
    SOCKET.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(SOCKET.parent, 0, 10001)
    if job_state().get("state") == "running":
        save_job({"state": "failed", "message": "Агент перезапущен во время задачи; проверьте Xray"})
    SOCKET.unlink(missing_ok=True)
    with Server(str(SOCKET), Handler) as server:
        os.chown(SOCKET, 0, 10001)
        SOCKET.chmod(0o660)
        server.serve_forever()


if __name__ == "__main__":
    main()
