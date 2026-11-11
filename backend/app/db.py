import os
import time
from pathlib import Path

from sqlalchemy import JSON, Boolean, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATA = Path(os.environ.get("DATA_DIR", "/data"))
DATA.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DATA / 'panel.db'}", connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def pragmas(connection, _):
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=10000")


Session = sessionmaker(engine, expire_on_commit=False)


def now() -> int:
    return int(time.time())


class Base(DeclarativeBase):
    pass


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    password: Mapped[str] = mapped_column(Text)


class LoginGuard(Base):
    __tablename__ = "login_guards"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    failures: Mapped[int] = mapped_column(default=0)
    until: Mapped[int] = mapped_column(default=0)


class WebSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    admin_id: Mapped[int] = mapped_column(Integer)
    csrf: Mapped[str] = mapped_column(String(100))
    expires: Mapped[int] = mapped_column(Integer)


class Server(Base):
    __tablename__ = "servers"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    metadata_json: Mapped[dict] = mapped_column(JSON)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    uuid: Mapped[str] = mapped_column(String(36), unique=True)
    email: Mapped[str] = mapped_column(String(150, collation="NOCASE"), unique=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(String(20), default="active")
    expires_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quota_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_bytes: Mapped[int] = mapped_column(Integer, default=0)
    last_up: Mapped[int] = mapped_column(Integer, default=0)
    last_down: Mapped[int] = mapped_column(Integer, default=0)
    last_activity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sync: Mapped[str] = mapped_column(String(30), default="pending_apply")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    historical_uuids: Mapped[list] = mapped_column(JSON, default=list)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notified: Mapped[int] = mapped_column(default=0)
    policy: Mapped[str] = mapped_column(String(30), default="ru-direct")
    created: Mapped[int] = mapped_column(default=now)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[int] = mapped_column(default=now, index=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")


class Sample(Base):
    __tablename__ = "samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[int] = mapped_column(default=now, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    delta: Mapped[int] = mapped_column(Integer)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


def audit(db, actor, action, user_id=None, detail=""):
    db.add(Audit(actor=actor, action=action, user_id=user_id, detail=detail))
