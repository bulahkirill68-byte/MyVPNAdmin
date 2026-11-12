import copy
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from app.db import Server, Session
from test_api import client
from test_worker import payload


@pytest.fixture
def agent():
    path = Path(__file__).resolve().parents[2] / "host" / "agent.py"
    spec = importlib.util.spec_from_file_location("host_agent_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def existing():
    return {"log": {"loglevel": "warning"}, "routing": {"rules": []}, "inbounds": [{
        "tag": "vless-reality", "port": 443, "protocol": "vless", "settings": {
            "clients": [{"id": payload()["users"][0]["uuid"], "flow": "xtls-rprx-vision"}],
            "decryption": "none"}, "streamSettings": {"network": "raw", "security": "reality",
            "realitySettings": {"privateKey": "ORIGINAL-PRIVATE", "shortIds": ["abcdef"],
                                "serverNames": ["example.com"]}}}],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}]}


def test_prepare_preserves_identity_keys_ports_and_routing(agent):
    original = existing()
    saved = copy.deepcopy(original)
    updated = agent.prepared_config(original)
    assert original == saved
    assert updated["outbounds"] == original["outbounds"]
    assert updated["routing"] == original["routing"]
    before, after = original["inbounds"][0], updated["inbounds"][0]
    assert after["settings"]["clients"][0]["id"] == before["settings"]["clients"][0]["id"]
    assert before["streamSettings"] == after["streamSettings"]
    assert before["port"] == after["port"] == 443
    assert after["settings"]["clients"][0]["email"] == "first-user@local.invalid"
    assert updated["api"]["listen"] == "127.0.0.1:10085"
    assert agent.prepared_config(updated) == updated


def test_prepare_validates_before_replacing_and_rolls_back(agent, monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    original = json.dumps(existing()).encode()
    path.write_bytes(original)
    monkeypatch.setattr(agent, "CONFIG", path)
    monkeypatch.setattr(agent, "BACKUPS", tmp_path / "backups")
    monkeypatch.setattr(agent.os, "chown", lambda *args: None, raising=False)
    calls = []

    def run(args, timeout=30):
        calls.append(args)
        if "-test" in args:
            assert args[-1].endswith(".json")  # Xray infers the loader from the filename extension.
        if args[:2] == ["systemctl", "is-active"]:
            raise subprocess.CalledProcessError(1, args)
        return ""
    monkeypatch.setattr(agent, "run", run)
    with pytest.raises(RuntimeError, match="восстановлен"):
        agent.prepare_existing()
    assert path.read_bytes() == original
    assert any("-test" in c for c in calls)
    assert len(list((tmp_path / "backups").glob("*.json"))) == 1


@pytest.mark.parametrize("ip,sni", [("127.0.0.1", "example.com"), ("8.8.8.8", "bad;touch /tmp/x"),
                                  ("8.8.8.8", "-bad.example"), ("8.8.8.8", "a..example")])
def test_no_command_injection_or_private_ips(agent, ip, sni):
    with pytest.raises(ValueError):
        agent.validate_input({"ip": ip, "sni": sni, "confirm": True})


def test_fresh_install_refuses_existing_config(agent, monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    config.write_text("{}")
    monkeypatch.setattr(agent, "CONFIG", config)
    with pytest.raises(ValueError, match="установлен"):
        agent.start_job("install", {"ip": "8.8.8.8", "confirm": True})
    assert not agent.LOCK.locked()


def test_authenticated_setup_bridge_and_import(monkeypatch):
    c = client()
    import app.host_agent
    calls = []

    def request(method, path, data=None):
        calls.append((method, path, data))
        if path.startswith("/onboarding"):
            return payload()
        if path == "/status":
            return {"installed": True, "config_exists": True, "job": {"state": "idle"}}
        return {"id": "job", "state": "running"}
    monkeypatch.setattr(app.host_agent, "request", request)
    assert c.get("/api/setup").json()["available"]
    assert c.post("/api/setup/prepare", json={"ip": "8.8.8.8"}).status_code == 409
    assert c.post("/api/setup/install", json={"ip": "8.8.8.8", "confirm": True},
                  headers={"X-CSRF-Token": "bad"}).status_code == 403
    assert c.post("/api/setup/prepare", json={"ip": "8.8.8.8", "confirm": True}).status_code == 202
    assert calls[-1][0:2] == ("POST", "/prepare")
    assert c.post("/api/setup/initialize", json={"ip": "8.8.8.8", "confirm": True}).status_code == 202
    assert calls[-1][0:2] == ("POST", "/initialize")
    assert c.post("/api/setup/import", json={"ip": "8.8.8.8", "confirm": True}).status_code == 202
    with Session() as db:
        assert db.get(Server, 1).metadata_json["ip"] == "8.8.8.8"
    assert c.post("/api/setup/import", json={"ip": "8.8.8.8", "confirm": True}).status_code == 409


@pytest.mark.parametrize('contents,expected,recoverable', [
    (None, 'missing', True), ('{}', 'empty', True), (' \n', 'empty', True), ('null', 'other', False),
    ('{"inbounds":[]}', 'other', False), ('not-json', 'invalid', False),
])
def test_empty_install_is_distinguished_from_unknown_configuration(agent, monkeypatch, tmp_path,
                                                                  contents, expected, recoverable):
    config = tmp_path / 'config.json'
    if contents is not None:
        config.write_text(contents)
    monkeypatch.setattr(agent, 'CONFIG', config)
    monkeypatch.setattr(agent.shutil, 'which', lambda _: '/usr/local/bin/xray')
    monkeypatch.setattr(agent, 'service_is_canonical', lambda: True)
    result = agent.configuration_state()
    assert result['configuration'] == expected
    assert result['can_initialize'] is recoverable
    assert not result['has_managed_inbound']


def test_unknown_systemd_config_is_not_initialized(agent, monkeypatch, tmp_path):
    config = tmp_path / 'config.json'
    config.write_text('{}')
    monkeypatch.setattr(agent, 'CONFIG', config)
    monkeypatch.setattr(agent.shutil, 'which', lambda _: '/usr/local/bin/xray')
    monkeypatch.setattr(agent, 'service_is_canonical', lambda: False)
    assert not agent.configuration_state()['can_initialize']
    with pytest.raises(ValueError, match='штатной службы'):
        agent.initialize_empty('8.8.8.8', 'example.com')
    assert config.read_text() == '{}'


def test_canonical_service_requires_exact_single_config(agent, monkeypatch):
    outputs = iter([
        '{ path=/usr/local/bin/xray ; argv[]=/usr/local/bin/xray run -config /usr/local/etc/xray/config.json ; ignore_errors=no ; }',
        '{ path=/usr/local/bin/xray ; argv[]=/usr/local/bin/xray run -confdir /etc/xray ; ignore_errors=no ; }',
        '{ path=/usr/local/bin/xray ; argv[]=/usr/local/bin/xray run -config /usr/local/etc/xray/config.json -config /other.json ; }',
    ])
    monkeypatch.setattr(agent.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=next(outputs)))
    assert agent.service_is_canonical()
    assert not agent.service_is_canonical()
    assert not agent.service_is_canonical()


def test_initialize_empty_creates_valid_crypto_and_never_rotates_existing_users(agent, monkeypatch, tmp_path):
    config = tmp_path / 'config.json'
    config.write_text('{}')
    monkeypatch.setattr(agent, 'CONFIG', config)
    monkeypatch.setattr(agent, 'BACKUPS', tmp_path / 'backups')
    monkeypatch.setattr(agent, 'ACCESS_DIRECTORY', tmp_path)
    monkeypatch.setattr(agent.shutil, 'which', lambda _: '/usr/local/bin/xray')
    monkeypatch.setattr(agent, 'service_is_canonical', lambda: True)
    monkeypatch.setattr(agent, 'service_group', lambda: 123)
    monkeypatch.setattr(agent, 'service_active', lambda: False)
    monkeypatch.setattr(agent, 'ensure_ports_free', lambda: None)
    monkeypatch.setattr(agent.os, 'chown', lambda *args: None, raising=False)
    calls = []
    def run(args, timeout=30):
        calls.append(args)
        if args[0] == 'openssl':
            return 'Verify return code: 0 (ok)\nALPN protocol: h2\n'
        return ''
    monkeypatch.setattr(agent, 'run', run)
    class Connected:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(agent.socket, 'create_connection', lambda *args, **kwargs: Connected())
    agent.initialize_empty('8.8.8.8', 'example.com')
    initialized = json.loads(config.read_text())
    inbound = initialized['inbounds'][0]
    assert inbound['tag'] == 'vless-reality' and inbound['port'] == 443
    assert initialized['api']['listen'] == '127.0.0.1:10085'
    assert agent.prepared_config(initialized) == initialized
    reality = inbound['streamSettings']['realitySettings']
    public = agent.public_key(reality['privateKey'])
    access = next(tmp_path.glob('xray-reality-access-*.txt')).read_text()
    assert public in access and 'fp=firefox' in access
    assert reality['privateKey'] not in access
    assert any('-test' in c for c in calls)
    assert agent.configuration_state()['has_managed_inbound']
    assert not agent.configuration_state()['can_initialize']
    saved = config.read_bytes()
    with pytest.raises(ValueError):
        agent.initialize_empty('8.8.8.8', 'example.com')
    assert config.read_bytes() == saved


def test_initialization_opens_only_vpn_port_in_active_ufw(agent, monkeypatch):
    monkeypatch.setattr(agent.shutil, 'which', lambda name: '/usr/sbin/ufw')
    calls = []
    def run(args, timeout=30):
        calls.append(args)
        return 'Status: active' if args == ['ufw', 'status'] else ''
    monkeypatch.setattr(agent, 'run', run)
    agent.allow_vpn_port()
    assert calls == [['ufw', 'status'], ['ufw', 'allow', '443/tcp', 'comment', 'Reality Xray']]
