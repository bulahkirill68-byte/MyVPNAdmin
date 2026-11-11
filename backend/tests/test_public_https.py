from datetime import datetime, timedelta, timezone
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest


@pytest.fixture
def control(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[2] / 'public' / 'https_control.py'
    spec = importlib.util.spec_from_file_location('public_control_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, value in {'CERT_DIR': tmp_path, 'CONFIG': tmp_path / 'public.json',
                        'HTTP_CONF': tmp_path / 'http.conf', 'TLS_CONF': tmp_path / 'https.conf',
                        'STATE': tmp_path / 'state'}.items():
        monkeypatch.setattr(module, name, value)
    monkeypatch.setattr(module, 'trusted_chain', lambda: True)
    return module


def certificate(directory, address='8.8.8.8', hours=100):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, address)])
    stamp = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(stamp - timedelta(hours=24))
            .not_valid_after(stamp + timedelta(hours=hours))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(address))]), False)
            .sign(key, hashes.SHA256()))
    (directory / 'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (directory / 'privkey.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


@pytest.mark.parametrize('address,hours,expected', [('8.8.8.8', 100, True), ('1.1.1.1', 100, False),
                                                 ('8.8.8.8', -1, False), ('8.8.8.8', 0.5, False)])
def test_ip_san_expiry_and_guard_margin(control, address, hours, expected):
    certificate(control.CERT_DIR, address, hours)
    assert control.certificate_valid({'ip': '8.8.8.8', 'port': 8443}) is expected


def test_untrusted_certificate_and_mismatched_private_key_are_rejected(control, monkeypatch):
    certificate(control.CERT_DIR)
    monkeypatch.setattr(control, 'trusted_chain', lambda: False)
    assert not control.certificate_valid({'ip': '8.8.8.8', 'port': 8443})
    monkeypatch.setattr(control, 'trusted_chain', lambda: True)
    other = ec.generate_private_key(ec.SECP256R1())
    (control.CERT_DIR / 'privkey.pem').write_bytes(other.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    assert not control.certificate_valid({'ip': '8.8.8.8', 'port': 8443})


def test_invalid_cert_closes_only_managed_https_and_keeps_acme(control, monkeypatch):
    control.CONFIG.write_text(json.dumps({'ip': '8.8.8.8', 'port': 8443}))
    control.TLS_CONF.write_text(control.MARKER + 'previous TLS config')
    commands = []
    monkeypatch.setattr(control.subprocess, 'run', lambda args, **kwargs: commands.append(args))
    control.refresh()
    assert not control.TLS_CONF.exists()
    assert 'acme-challenge' in control.HTTP_CONF.read_text()
    assert commands == [['nginx', '-t'], ['systemctl', 'reload', 'nginx']]
    control.TLS_CONF.write_text('unrelated user config')
    with pytest.raises(ValueError):
        control.managed_write(control.TLS_CONF, None)


def test_public_host_is_opt_in_and_https_origin_is_valid():
    code = '''
from fastapi.testclient import TestClient
from app.main import app
c=TestClient(app,base_url='https://8.8.8.8:8443')
assert c.get('/health').status_code==200
assert c.get('/health',headers={'Host':'evil.example'}).status_code==400
r=c.post('/api/login',json={'name':'nobody','password':'bad'},headers={'Origin':'https://8.8.8.8:8443'})
assert r.status_code==401,r.text
r=c.post('/api/login',json={'name':'nobody','password':'bad'},headers={'Origin':'https://evil.example'})
assert r.status_code==403,r.text
'''
    env = {**os.environ, 'PUBLIC_ORIGIN': 'https://8.8.8.8:8443', 'COOKIE_SECURE': 'true'}
    result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
