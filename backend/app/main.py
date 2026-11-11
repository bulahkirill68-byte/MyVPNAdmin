import base64
import os
from pathlib import Path
import secrets
import socket
from uuid import uuid4

import psutil
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Integer, delete, func, select
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.auth import authenticated, digest, login
from app.db import DATA, Audit, Sample, Server, Session, Setting, User, WebSession, audit, now
from app.domain import link, renewal, status
from app.routing import client_config, export, test_route
from app.schemas import Action, Credentials, Routing, Setup, UserInput

app = FastAPI(title="Reality Control", version="0.2.0", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])


@app.middleware("http")
async def security(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
            return JSONResponse({"detail": "Недопустимый Origin"}, status_code=403)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Некорректный Content-Length"}, status_code=400)
        if length > 131072:
            return JSONResponse({"detail": "Слишком большой запрос"}, status_code=413)
    response = await call_next(request)
    response.headers.update({
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer", "Cache-Control": "no-store",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                   "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
    })
    return response


def serialize(user):
    return {k: getattr(user, k) for k in ["id", "name", "email", "comment", "expires_at", "quota_bytes",
            "used_bytes", "last_activity", "sync", "error", "policy", "created"]} | {"status": status(user, now())}


def get_user(db, user_id):
    user = db.get(User, user_id)
    if not user or user.deleted:
        raise HTTPException(404, "Пользователь не найден")
    return user


@app.get("/health")
def health():
    with Session() as db:
        db.execute(select(1))
    return {"status": "ok"}


@app.post("/api/login")
def sign_in(data: Credentials, response: Response):
    token, csrf = login(data.name, data.password)
    response.set_cookie("panel_session", token, httponly=True, samesite="strict", max_age=28800,
                        secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true")
    return {"csrf": csrf}


@app.get("/api/me")
def me(request: Request, actor=Depends(authenticated)):
    return {"name": actor, "csrf": request.state.csrf}


@app.post("/api/logout")
def logout(request: Request, response: Response, actor=Depends(authenticated)):
    with Session.begin() as db:
        db.execute(delete(WebSession).where(WebSession.token_hash == digest(request.cookies.get("panel_session", ""))))
        audit(db, actor, "logout")
    response.delete_cookie("panel_session")
    return {"ok": True}


@app.get("/api/openapi.json")
def openapi(actor=Depends(authenticated)):
    return app.openapi()


@app.get("/api/users")
def users(actor=Depends(authenticated)):
    with Session() as db:
        return [serialize(u) for u in db.scalars(select(User).where(User.deleted.is_(False)).order_by(User.id.desc()))]


@app.post("/api/users", status_code=201)
def create_user(data: UserInput, actor=Depends(authenticated)):
    with Session.begin() as db:
        if not db.get(Server, 1):
            raise HTTPException(409, "Сначала импортируйте сервер через CLI")
        user = User(**data.model_dump(), uuid=str(uuid4()), email=f"u-{uuid4().hex}@panel.invalid")
        db.add(user)
        db.flush()
        audit(db, actor, "user_created", user.id)
        return serialize(user)


@app.put("/api/users/{user_id}")
def update_user(user_id: int, data: UserInput, actor=Depends(authenticated)):
    with Session.begin() as db:
        user = get_user(db, user_id)
        for key, value in data.model_dump().items():
            setattr(user, key, value)
        user.sync = "pending_apply"
        user.notified = 0
        audit(db, actor, "user_updated", user.id)
        return serialize(user)


@app.get("/api/users/{user_id}/renew-preview")
def preview(user_id: int, days: int = 30, mode: str = "expiry", actor=Depends(authenticated)):
    if not 1 <= days <= 3650 or mode not in ("now", "expiry"):
        raise HTTPException(422, "Некорректные параметры")
    with Session() as db:
        user = get_user(db, user_id)
        return {"expires_at": renewal(user.expires_at, days, mode, now())}


@app.post("/api/users/{user_id}/actions")
def action(user_id: int, data: Action, actor=Depends(authenticated)):
    with Session.begin() as db:
        user = get_user(db, user_id)
        if data.action in ("delete", "rotate", "revoke") and not data.confirm:
            raise HTTPException(409, "Требуется подтверждение")
        if data.action == "pause":
            user.intent = "paused"
        elif data.action == "resume":
            user.intent = "active"
        elif data.action == "revoke":
            user.intent, user.token_hash = "revoked", None
        elif data.action == "delete":
            user.deleted, user.intent, user.token_hash = True, "revoked", None
        elif data.action == "rotate":
            user.historical_uuids = [*user.historical_uuids, user.uuid]
            user.uuid, user.token_hash = str(uuid4()), None
        elif data.action == "renew":
            result = renewal(user.expires_at, data.days, data.mode, now())
            if data.expected_expires is None or abs(result - data.expected_expires) > 120:
                raise HTTPException(409, "Обновите предварительный расчёт срока")
            user.expires_at = data.expected_expires
        elif data.action == "token":
            token = secrets.token_urlsafe(48)
            user.token_hash = digest(token)
            audit(db, actor, "subscription_token_rotated", user.id)
            return {"url": f"http://localhost:8000/sub/{token}", "local_only": True,
                    "note": "Только через SSH-туннель; этот URL не доступен клиентам через интернет"}
        elif data.action == "revoke_token":
            user.token_hash = None
        user.sync = "pending_apply"
        audit(db, actor, data.action, user.id)
        return serialize(user)


@app.get("/api/users/{user_id}/access")
def access(user_id: int, actor=Depends(authenticated)):
    with Session.begin() as db:
        user = get_user(db, user_id)
        server = db.get(Server, 1)
        if not server:
            raise HTTPException(409, "Сервер не импортирован")
        audit(db, actor, "access_revealed", user.id)
        return {"uuid": user.uuid, "link": link(user, server.metadata_json), "status": status(user, now())}


@app.get("/sub/{token}", response_class=PlainTextResponse)
def subscription(token: str):
    with Session() as db:
        user = db.scalar(select(User).where(User.token_hash == digest(token)))
        server = db.get(Server, 1)
        if not user or not server or status(user, now()) != "active":
            raise HTTPException(404, "Подписка недоступна")
        return base64.b64encode(link(user, server.metadata_json).encode()).decode()


@app.get("/api/dashboard")
def dashboard(actor=Depends(authenticated)):
    stamp = now()
    with Session() as db:
        worker = db.get(Setting, "worker")
        state = worker.value if worker else {"ok": False, "reason": "Worker ещё не подключился к Xray"}
        if state.get("at", 0) < stamp - 60:
            state = {**state, "ok": False, "reason": "Нет свежих данных worker"}
        user_list = list(db.scalars(select(User).where(User.deleted.is_(False))))
        # UTC midnight and calendar month; only traffic observed since panel installation.
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        month = today.replace(day=1)
        totals = {name: db.scalar(select(func.coalesce(func.sum(Sample.delta), 0)).where(Sample.at >= int(dt.timestamp())))
                  for name, dt in [("day", today), ("month", month)]}
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(DATA))
    try:
        with socket.create_connection(("127.0.0.1", 443), timeout=0.5):
            tcp = True
    except OSError:
        tcp = False
    return {"worker": state, "tcp443": tcp, "active": sum(status(u, stamp) == "active" for u in user_list),
            "total": len(user_list), "traffic": totals,
            "resources": {"cpu": psutil.cpu_percent(interval=0.1), "ram": memory.percent,
                          "disk": disk.percent, "disk_free": disk.free}, "at": stamp}


@app.get("/api/traffic")
def traffic(user_id: int | None = None, actor=Depends(authenticated)):
    with Session() as db:
        bucket = (Sample.at / 3600).cast(Integer) * 3600
        query = select(bucket.label("at"), func.sum(Sample.delta).label("bytes")).where(Sample.at > now() - 7 * 86400)
        if user_id is not None:
            query = query.where(Sample.user_id == user_id)
        return [dict(r._mapping) for r in db.execute(query.group_by(bucket).order_by(bucket))]


@app.get("/api/audit")
def events(user_id: int | None = None, actor=Depends(authenticated)):
    with Session() as db:
        query = select(Audit)
        if user_id is not None:
            query = query.where(Audit.user_id == user_id)
        return [{"id": a.id, "at": a.at, "actor": a.actor, "action": a.action, "user_id": a.user_id,
                 "detail": a.detail} for a in db.scalars(query.order_by(Audit.id.desc()).limit(200))]


@app.get("/api/settings")
def settings(actor=Depends(authenticated)):
    with Session() as db:
        server = db.get(Server, 1)
        return {"server": server.metadata_json if server else None,
                "backups": [p.name for p in sorted((DATA / "backups").glob("*.sqlite3"), reverse=True)]}


@app.post("/api/backup")
def make_backup(actor=Depends(authenticated)):
    from app.cli import backup
    path = backup()
    with Session.begin() as db:
        audit(db, actor, "backup_created", detail=path.name)
    return {"name": path.name}


@app.get("/api/routing")
def routing(actor=Depends(authenticated)):
    with Session() as db:
        value = db.get(Setting, "routing")
        return value.value if value else Routing().model_dump()


@app.put("/api/routing")
def save_routing(data: Routing, actor=Depends(authenticated)):
    with Session.begin() as db:
        value = db.get(Setting, "routing")
        if value:
            value.value = data.model_dump()
        else:
            db.add(Setting(key="routing", value=data.model_dump()))
        audit(db, actor, "routing_updated")
    return data


@app.get("/api/routing/export")
def routing_export(actor=Depends(authenticated)):
    return export(Routing.model_validate(routing(actor)))


@app.get("/api/users/{user_id}/routing/export")
def user_routing_export(user_id: int, actor=Depends(authenticated)):
    policy = Routing.model_validate(routing(actor))
    with Session() as db:
        user = get_user(db, user_id)
        policy.preset = user.policy
    return export(policy)


@app.get("/api/routing/test")
def routing_test(target: str, actor=Depends(authenticated)):
    if len(target) > 253 or not target:
        raise HTTPException(422, "Некорректный адрес")
    try:
        return test_route(Routing.model_validate(routing(actor)), target)
    except (ValueError, UnicodeError):
        raise HTTPException(422, "Некорректный адрес") from None


@app.get("/api/users/{user_id}/client-config")
def user_client_config(user_id: int, actor=Depends(authenticated)):
    policy = Routing.model_validate(routing(actor))
    with Session.begin() as db:
        user = get_user(db, user_id)
        server = db.get(Server, 1)
        if not server:
            raise HTTPException(409, "Сервер не импортирован")
        audit(db, actor, "client_config_exported", user.id)
        return client_config(user, server.metadata_json, policy)


def agent_call(method, path, data=None):
    from app.host_agent import request
    try:
        return request(method, path, data)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    except (OSError, TimeoutError):
        raise HTTPException(503, "Хостовый агент недоступен. Выполните sudo bash scripts/install_agent.sh") from None


@app.get("/api/setup")
def setup_status(actor=Depends(authenticated)):
    from app.host_agent import request
    with Session() as db:
        imported = db.get(Server, 1) is not None
    try:
        return {"available": True, "imported": imported, **request("GET", "/status")}
    except (OSError, ValueError, TimeoutError):
        return {"available": False, "imported": imported,
                "reason": "Установите локальный host-agent: sudo bash scripts/install_agent.sh"}


@app.post("/api/setup/{operation}", status_code=202)
def setup_operation(operation: str, data: Setup, actor=Depends(authenticated)):
    if operation not in ("install", "prepare", "import"):
        raise HTTPException(404, "Неизвестная операция")
    if not data.confirm:
        raise HTTPException(409, "Подтвердите операцию")
    if operation == "import":
        from app.cli import import_data
        payload = agent_call("GET", f"/onboarding?ip={data.ip}")
        try:
            import_data(payload)
        except ValueError:
            raise HTTPException(409, "Сервер уже импортирован или метаданные некорректны") from None
        result = {"state": "succeeded", "message": "Сервер и пользователи импортированы без смены UUID"}
    else:
        result = agent_call("POST", f"/{operation}", data.model_dump())
    with Session.begin() as db:
        audit(db, actor, f"setup_{operation}")
    return result


static = Path(os.environ.get("STATIC_DIR", "/opt/static"))
if static.is_dir():
    app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith(("api/", "sub/")):
            raise HTTPException(404)
        return FileResponse(static / "index.html")
