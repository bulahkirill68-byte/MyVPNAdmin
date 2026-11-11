import json
from pathlib import Path
import subprocess
import sys
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.cli import backup, import_data
from app.db import DATA, Session, engine
from app.routing import export, test_route as route_test
from app.schemas import RouteRule, Routing
from test_worker import payload


def test_migration_matches_models_and_wal():
    command.check(Config("alembic.ini"))
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
    assert "users" in inspect(engine).get_table_names()


def test_backup_and_restore_subprocess():
    import_data(payload())
    saved = backup()
    with Session.begin() as db:
        db.execute(text("UPDATE users SET name='changed'"))
    result = subprocess.run([sys.executable, "-m", "app.cli", "restore", str(saved)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with Session() as db:
        assert db.execute(text("SELECT name FROM users")).scalar() == "Первый"
    assert saved.parent == DATA / "backups"


def test_route_order_and_geo_uncertainty():
    policy = Routing(local_rules=[RouteRule(kind="domain", values=["domain:example.ru"], outbound="proxy")])
    rules = export(policy)["rules"]
    assert all(not ("domain" in r and "ip" in r) for r in rules)
    assert route_test(policy, "example.ru")["outbound"] == "proxy"
    assert route_test(policy, "192.168.1.1")["outbound"] == "direct"
    assert route_test(policy, "8.8.8.8")["approximate"]
    assert rules[-1]["outboundTag"] == "proxy"


def test_onboarding_export_never_leaks_private_key():
    import importlib.util
    script = Path(__file__).resolve().parents[2] / "scripts" / "export_xray.py"
    spec = importlib.util.spec_from_file_location("export_xray", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = {"api": {"listen": "127.0.0.1:10085", "services": ["HandlerService", "StatsService"]},
        "policy": {"levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True}}},
        "inbounds": [{"tag": "vless-reality", "port": 443, "protocol": "vless", "settings": {"clients": [
            {"id": payload()["users"][0]["uuid"], "email": "first@local.invalid", "flow": "xtls-rprx-vision"}]},
            "streamSettings": {"realitySettings": {"privateKey": "DO_NOT_EXPORT", "serverNames": ["example.com"],
                                                   "shortIds": ["abcd"]}}}]}
    result = module.extract(config, "8.8.8.8", "A" * 43, 12345)
    assert "DO_NOT_EXPORT" not in json.dumps(result)
    assert result["users"][0]["expires_at"] == 12345
