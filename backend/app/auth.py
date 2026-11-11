import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException, Request
from sqlalchemy import delete, select

from app.db import Admin, LoginGuard, Session, WebSession, audit, now

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY = hasher.hash(secrets.token_urlsafe(32))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def login(name: str, password: str) -> tuple[str, str]:
    with Session.begin() as db:
        guard = db.get(LoginGuard, "global")
        if not guard:
            guard = LoginGuard(key="global", failures=0, until=0)
            db.add(guard)
        if guard.until > now():
            raise HTTPException(429, "Слишком много попыток. Повторите через 15 минут")
        admin = db.scalar(select(Admin).where(Admin.name == name))
        try:
            valid = hasher.verify(admin.password if admin else DUMMY, password) and admin is not None
        except VerificationError:
            valid = False
        if not valid:
            guard.failures += 1
            if guard.failures >= 5:
                guard.until, guard.failures = now() + 900, 0
            audit(db, "anonymous", "login_failed")
        else:
            guard.failures, guard.until = 0, 0
            token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
            db.execute(delete(WebSession).where(WebSession.expires < now()))
            db.add(WebSession(token_hash=digest(token), admin_id=admin.id, csrf=csrf, expires=now() + 28800))
            audit(db, admin.name, "login")
    if not valid:
        raise HTTPException(401, "Неверное имя или пароль")
    return token, csrf


def authenticated(request: Request) -> str:
    with Session() as db:
        session = db.get(WebSession, digest(request.cookies.get("panel_session", "")))
        if not session or session.expires <= now():
            raise HTTPException(401, "Войдите в панель")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
                raise HTTPException(403, "Ошибка CSRF; обновите страницу")
        admin = db.get(Admin, session.admin_id)
        if not admin:
            raise HTTPException(401, "Сессия недействительна")
        request.state.csrf = session.csrf
        return admin.name
