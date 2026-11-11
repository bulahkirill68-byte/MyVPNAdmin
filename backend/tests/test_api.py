import base64
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hasher
from app.cli import import_data
from app.db import Admin, Session, User, now
from app.main import app
from test_worker import payload


def client():
    with Session.begin() as db:
        db.add(Admin(name="owner", password=hasher.hash("a-strong-password-123")))
    c = TestClient(app)
    result = c.post("/api/login", json={"name": "owner", "password": "a-strong-password-123"})
    assert result.status_code == 200
    c.headers["X-CSRF-Token"] = result.json()["csrf"]
    return c


def test_auth_csrf_host_and_rate_limit():
    c = TestClient(app)
    assert c.get("/api/users").status_code == 401
    for _ in range(5):
        assert c.post("/api/login", json={"name": "bad", "password": "bad"}).status_code == 401
    assert c.post("/api/login", json={"name": "bad", "password": "bad"}).status_code == 429
    assert c.get("/health", headers={"host": "evil.example"}).status_code == 400


def test_crud_renewal_access_tokens_and_logout():
    import_data(payload())
    c = client()
    assert any("HttpOnly" in cookie._rest for cookie in c.cookies.jar)
    assert c.post("/api/users", json={"name": "Bad"}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert c.post("/api/users", json={"name": "Bad"}, headers={"Origin": "http://evil.example"}).status_code == 403
    result = c.post("/api/users", json={"name": "Анна", "quota_bytes": 100})
    assert result.status_code == 201
    user = result.json()
    assert user["sync"] == "pending_apply"
    uid = user["id"]
    access = c.get(f"/api/users/{uid}/access").json()
    assert access["link"].startswith("vless://") and "flow=xtls-rprx-vision" in access["link"]
    assert "uuid" not in c.get("/api/users").json()[0]
    assert c.post(f"/api/users/{uid}/actions", json={"action": "delete"}).status_code == 409
    preview = c.get(f"/api/users/{uid}/renew-preview?days=7&mode=now").json()["expires_at"]
    result = c.post(f"/api/users/{uid}/actions", json={"action": "renew", "days": 7, "mode": "now", "expected_expires": preview})
    assert result.json()["expires_at"] == preview
    token_url = c.post(f"/api/users/{uid}/actions", json={"action": "token"}).json()["url"]
    token_path = "/sub/" + token_url.rsplit("/", 1)[1]
    assert base64.b64decode(c.get(token_path).text).decode() == access["link"]
    with Session() as db:
        assert db.get(User, uid).token_hash not in token_url
    c.post(f"/api/users/{uid}/actions", json={"action": "pause"})
    assert c.get(token_path).status_code == 404
    c.post(f"/api/users/{uid}/actions", json={"action": "resume"})
    c.post(f"/api/users/{uid}/actions", json={"action": "rotate", "confirm": True})
    assert c.get(token_path).status_code == 404
    c.post(f"/api/users/{uid}/actions", json={"action": "delete", "confirm": True})
    assert c.get(f"/api/users/{uid}/access").status_code == 404
    assert c.post("/api/logout").status_code == 200
    assert c.get("/api/users").status_code == 401


def test_quota_null_and_zero_validation():
    import_data(payload())
    c = client()
    assert c.post("/api/users", json={"name": "Invalid", "quota_bytes": 0}).status_code == 422
    assert c.post("/api/users", json={"name": "Valid", "quota_bytes": None, "expires_at": None}).status_code == 201
    assert c.post("/api/users", json={"name": "Extra", "uuid": "custom"}).status_code == 422
    with Session() as db:
        users = list(db.scalars(select(User)))
        assert len({u.uuid for u in users}) == len(users)
        assert all(u.expires_at is None for u in users)
    assert c.get("/api/dashboard").json()["at"] <= now()
