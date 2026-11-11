"""Isolated test server. Never uses production DATA_DIR, creates no fictional monitoring."""
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="reality-e2e-")
os.environ["STATIC_DIR"] = str(ROOT / "frontend" / "dist")

import uvicorn
from alembic import command
from alembic.config import Config
from app.auth import hasher
from app.cli import import_data
from app.db import Admin, Session

config = Config()
config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
command.upgrade(config, "head")
with Session.begin() as db:
    db.add(Admin(name="e2e-owner", password=hasher.hash("e2e-only-long-password")))
import_data({"server": {"ip": "8.8.8.8", "port": 443, "sni": "example.com", "public_key": "A" * 43,
                        "short_id": "abcd", "tag": "vless-reality"},
             "users": [{"name": "Импортированный тест", "uuid": "f59127f8-f242-443d-86b6-a87841be4ceb",
                        "email": "e2e@local.invalid"}]})
uvicorn.run("app.main:app", host="127.0.0.1", port=8000, access_log=False)
