"""Administrative commands run over SSH, inside the unprivileged application container."""
import argparse
import getpass
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import secrets

from sqlalchemy import select

from app.auth import hasher
from app.db import DATA, Admin, Server, Session, User, audit, now
from app.schemas import Onboarding


def backup() -> Path:
    if shutil.disk_usage(DATA).free < 100 * 1024 * 1024:
        raise RuntimeError("Недостаточно места для резервной копии")
    directory = DATA / "backups"
    directory.mkdir(exist_ok=True, mode=0o700)
    target = directory / f"panel-{time.time_ns()}.sqlite3"
    with sqlite3.connect(DATA / "panel.db") as source, sqlite3.connect(target) as dest:
        source.backup(dest)
        if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Проверка резервной копии не пройдена")
    os.chmod(target, 0o600)
    for stale in sorted(directory.glob("panel-*.sqlite3"), key=lambda p: p.stat().st_mtime)[:-14]:
        stale.unlink()
    return target


def import_data(payload: dict):
    data = Onboarding.model_validate(payload)
    with Session.begin() as db:
        if db.get(Server, 1):
            raise ValueError("Сервер уже импортирован; повторный импорт запрещён")
        db.add(Server(id=1, metadata_json=data.server.model_dump()))
        emails, uuids = set(), set()
        for user in data.users:
            if user.email.lower() in emails or str(user.uuid) in uuids:
                raise ValueError("Повторяющиеся UUID/email")
            emails.add(user.email.lower())
            uuids.add(str(user.uuid))
            db.add(User(name=user.name, uuid=str(user.uuid), email=user.email, expires_at=user.expires_at,
                        applied_uuid=str(user.uuid)))
        audit(db, "cli", "onboarding", detail=f"Импортировано пользователей: {len(data.users)}")


def bootstrap_admin(name="admin"):
    if not 1 <= len(name) <= 80 or not name.strip():
        raise ValueError("Некорректное имя администратора")
    with Session.begin() as db:
        existing = db.scalar(select(Admin).order_by(Admin.id))
        if existing:
            return {"created": False, "username": existing.name}
        password = secrets.token_urlsafe(24)
        db.add(Admin(name=name, password=hasher.hash(password)))
        audit(db, "installer", "admin_created")
        return {"created": True, "username": name, "password": password}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["admin", "import", "backup", "restore", "subscription", "smoke",
                                            "bootstrap-admin", "bootstrap-state"])
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        print(json.dumps(bootstrap_admin(args.argument or "admin")))
    elif args.command == "bootstrap-state":
        with Session() as db:
            print(json.dumps({"admin_exists": db.scalar(select(Admin)) is not None,
                              "imported": db.get(Server, 1) is not None}))
    elif args.command == "admin":
        name = input("Имя администратора: ").strip()
        password = getpass.getpass("Пароль (минимум 14 символов): ")
        if not 1 <= len(name) <= 80 or not 14 <= len(password) <= 256:
            raise ValueError("Некорректное имя или длина пароля")
        if password != getpass.getpass("Повторите пароль: "):
            raise ValueError("Пароли не совпадают")
        with Session.begin() as db:
            if db.scalar(select(Admin)):
                raise ValueError("Администратор уже существует")
            db.add(Admin(name=name, password=hasher.hash(password)))
            audit(db, "cli", "admin_created")
    elif args.command == "import":
        import_data(json.load(sys.stdin))
        print("Импорт завершён. UUID и конфигурация Xray сохранены.")
    elif args.command == "backup":
        print(backup())
    elif args.command == "restore":
        # Caller must stop web/worker. Acquire same worker lock as an extra guard.
        from filelock import FileLock
        from app.db import engine
        source = Path(args.argument or "").resolve()
        directory = (DATA / "backups").resolve()
        if source.parent != directory or not source.is_file():
            raise ValueError("Восстановление допускается только из /data/backups")
        with FileLock(str(DATA / "worker.lock"), timeout=0):
            with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as saved:
                if saved.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Повреждённая копия")
                tables = {x[0] for x in saved.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"users", "servers", "alembic_version", "admins"} <= tables:
                    raise ValueError("Это не резервная копия панели")
                backup()
                engine.dispose()
                with sqlite3.connect(DATA / "panel.db") as destination:
                    saved.backup(destination)
                    destination.execute("DELETE FROM sessions")
                    destination.commit()
        print("База восстановлена; запустите миграции и сервисы")
    elif args.command == "subscription":
        from app.domain import link, status
        with Session() as db:
            user = db.get(User, int(args.argument or "0"))
            server = db.get(Server, 1)
            if not user or not server or status(user, now()) != "active":
                raise ValueError("Нет активного пользователя/сервера")
            print(link(user, server.metadata_json))
    elif args.command == "smoke":
        from app.xray import Xray
        adapter = Xray()
        uptime, counters = adapter.stats()
        print(json.dumps({"uptime": uptime, "counters": len(counters)}))


if __name__ == "__main__":
    main()
