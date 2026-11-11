import copy
import importlib.util
import json
from pathlib import Path
import subprocess

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
    assert c.post("/api/setup/import", json={"ip": "8.8.8.8", "confirm": True}).status_code == 202
    with Session() as db:
        assert db.get(Server, 1).metadata_json["ip"] == "8.8.8.8"
    assert c.post("/api/setup/import", json={"ip": "8.8.8.8", "confirm": True}).status_code == 409
