#!/usr/bin/env python3
"""Optional host-side IP HTTPS gateway. TLS is published only with a valid, trusted IP certificate."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import tempfile

CONFIG = Path('/etc/reality-control/public.json')
CERT_DIR = Path('/etc/reality-control/acme/live/reality-ip')
HTTP_CONF = Path('/etc/nginx/conf.d/reality-panel-http.conf')
TLS_CONF = Path('/etc/nginx/conf.d/reality-panel-https.conf')
STATE = Path('/var/lib/reality-public')
MARKER = '# Managed by Reality Control public HTTPS\n'


def validate(ip, port):
    address = ipaddress.IPv4Address(ip)
    if not address.is_global or not 1024 <= port <= 65535 or port in (8000, 10085):
        raise ValueError('Нужны публичный IPv4 и отдельный порт 1024–65535, кроме 8000/10085')
    return {'ip': str(address), 'port': port}


def trusted_chain():
    result = subprocess.run(['openssl', 'verify', '-CAfile', '/etc/ssl/certs/ca-certificates.crt',
                             '-untrusted', str(CERT_DIR / 'chain.pem'), str(CERT_DIR / 'cert.pem')],
                            capture_output=True, timeout=10)
    return result.returncode == 0


def certificate_valid(config, at=None):
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    try:
        cert = x509.load_pem_x509_certificate((CERT_DIR / 'cert.pem').read_bytes())
        key = serialization.load_pem_private_key((CERT_DIR / 'privkey.pem').read_bytes(), password=None)
        stamp = at or datetime.now(timezone.utc)
        before = (cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc')
                  else cert.not_valid_before.replace(tzinfo=timezone.utc))
        after = (cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc')
                 else cert.not_valid_after.replace(tzinfo=timezone.utc))
        addresses = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        encoding, form = serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        return (before <= stamp and after > stamp + timedelta(hours=1)
                and x509.IPAddress(ipaddress.ip_address(config['ip'])) in addresses
                and key.public_key().public_bytes(encoding, form) == cert.public_key().public_bytes(encoding, form)
                and trusted_chain())
    except (OSError, ValueError, x509.ExtensionNotFound, subprocess.SubprocessError):
        return False


def render_http(config):
    return MARKER + f'''server {{
    listen 80;
    server_name {config['ip']};
    access_log off;
    location ^~ /.well-known/acme-challenge/ {{
        root /var/lib/reality-acme-web;
        try_files $uri =404;
    }}
    location / {{ return 308 https://{config['ip']}:{config['port']}$request_uri; }}
}}
'''


def render_tls(config):
    return MARKER + f'''limit_req_zone $binary_remote_addr zone=reality_login:10m rate=6r/m;
server {{
    listen {config['port']} ssl;
    server_name {config['ip']};
    if ($host != "{config['ip']}") {{ return 444; }}
    server_tokens off;
    ssl_certificate {CERT_DIR}/fullchain.pem;
    ssl_certificate_key {CERT_DIR}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_tickets off;
    ssl_session_cache shared:reality_tls:10m;
    client_max_body_size 128k;
    access_log off;
    proxy_http_version 1.1;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Connection "";
    proxy_read_timeout 30s;
    location = /api/login {{
        limit_req zone=reality_login burst=5 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:8000;
    }}
    location ^~ /sub/ {{ return 404; }}
    location / {{ proxy_pass http://127.0.0.1:8000; }}
}}
'''


def managed_write(path, contents):
    if path.exists() and not path.read_text().startswith(MARKER):
        raise ValueError(f'Файл {path} не принадлежит Reality Control; перезапись запрещена')
    if contents is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.reality-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(contents)
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def refresh(prepare_only=False):
    if not CONFIG.exists():
        return
    config = validate(**json.loads(CONFIG.read_text()))
    valid = certificate_valid(config)
    old_http = HTTP_CONF.read_text() if HTTP_CONF.exists() else None
    old_tls = TLS_CONF.read_text() if TLS_CONF.exists() else None
    managed_write(HTTP_CONF, render_http(config))
    managed_write(TLS_CONF, render_tls(config) if valid else None)
    if prepare_only:
        return
    digest = hashlib.sha256(((CERT_DIR / 'fullchain.pem').read_bytes() if valid else b'closed')
                            + render_http(config).encode() + (render_tls(config).encode() if valid else b'')).hexdigest()
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = STATE / 'applied.sha256'
    if stamp.exists() and stamp.read_text() == digest and old_http == HTTP_CONF.read_text() and (
            old_tls == (TLS_CONF.read_text() if TLS_CONF.exists() else None)):
        return
    try:
        subprocess.run(['nginx', '-t'], check=True, timeout=15)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True, timeout=20)
    except Exception:
        managed_write(HTTP_CONF, old_http)
        managed_write(TLS_CONF, old_tls)
        raise
    stamp.write_text(digest)
    print('HTTPS активен' if valid else 'HTTPS закрыт: нет действительного доверенного IP-сертификата')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['init', 'prepare', 'refresh', 'renew'])
    parser.add_argument('--ip')
    parser.add_argument('--port', type=int, default=8443)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Запустите на хосте от root')
    if args.command == 'init':
        data = validate(args.ip, args.port)
        CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(data))
        CONFIG.chmod(0o600)
        refresh()
    elif args.command == 'renew':
        result = subprocess.run(['/opt/reality-certbot/bin/certbot', 'renew', '--quiet',
                                 '--config-dir', '/etc/reality-control/acme',
                                 '--work-dir', '/var/lib/reality-acme', '--logs-dir', '/var/log/reality-acme'])
        refresh()  # Always check expiry, including when renewal fails.
        raise SystemExit(result.returncode)
    else:
        refresh(prepare_only=args.command == 'prepare')


if __name__ == '__main__':
    main()
