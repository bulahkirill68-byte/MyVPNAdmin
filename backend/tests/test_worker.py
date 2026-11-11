from sqlalchemy import func, select
from app.cli import import_data
from app.db import Audit, Sample, Session, Setting, User, now
from app.worker import tick
import pytest

UID = "a2edbd13-4a82-441e-bda4-f53144b7a027"


def payload():
    return {"server": {"ip": "8.8.8.8", "port": 443, "sni": "example.com", "public_key": "A" * 43,
                       "short_id": "abcd", "tag": "vless-reality"},
            "users": [{"name": "Первый", "uuid": UID, "email": "first@local.invalid", "expires_at": None}]}


class FakeXray:
    def __init__(self):
        self.users = {"first@local.invalid": UID}
        self.values = {}
        self.uptime = 100
        self.fail = False
        self.stats_fail = False

    def stats(self):
        if self.fail or self.stats_fail:
            raise RuntimeError("unavailable")
        return self.uptime, self.values

    def ensure(self, tag, uid, email, historical_uuids=None):
        if self.fail:
            raise RuntimeError("unavailable")
        self.users[email] = uid

    def remove(self, tag, email):
        if self.fail:
            raise RuntimeError("unavailable")
        self.users.pop(email, None)


def test_import_preserves_uuid_and_rejects_reimport():
    import_data(payload())
    with Session() as db:
        user = db.scalar(select(User))
        assert user.uuid == UID
        assert user.email == "first@local.invalid"
        assert user.expires_at is None
    with pytest.raises(ValueError):
        import_data(payload())


def test_reconcile_expiry_restart_rotation_and_tombstone():
    import_data(payload())
    adapter = FakeXray()
    tick(adapter)
    adapter.users.clear()
    tick(adapter)
    assert adapter.users["first@local.invalid"] == UID
    with Session.begin() as db:
        user = db.scalar(select(User))
        user.uuid = "5295d2c3-9c5d-4bf1-9f2f-179653c6407f"
    tick(adapter)
    assert adapter.users["first@local.invalid"] != UID
    with Session.begin() as db:
        db.scalar(select(User)).expires_at = now() - 1
    tick(adapter)
    assert not adapter.users
    adapter.users["first@local.invalid"] = UID  # static config resurrects on Xray restart
    with Session.begin() as db:
        db.scalar(select(User)).deleted = True
    tick(adapter)
    assert not adapter.users


def test_quota_deltas_repeated_tick_reset_and_restart():
    import_data(payload())
    adapter = FakeXray()
    up, down = "user>>>first@local.invalid>>>traffic>>>uplink", "user>>>first@local.invalid>>>traffic>>>downlink"
    adapter.values = {up: 40, down: 40}
    with Session.begin() as db:
        db.scalar(select(User)).quota_bytes = 100
    tick(adapter)
    tick(adapter)
    with Session() as db:
        assert db.scalar(select(User)).used_bytes == 80
        assert db.scalar(select(func.count()).select_from(Sample)) == 1
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action == "quota_notification")) == 1
    adapter.values = {up: 5, down: 5}  # external counter reset
    tick(adapter)
    adapter.values = {up: 20, down: 20}
    adapter.uptime = 1  # restart, new counters greater than previous sample
    tick(adapter)
    with Session() as db:
        assert db.scalar(select(User)).used_bytes == 130
    assert not adapter.users


def test_api_failure_pending_error_and_recovery():
    import_data(payload())
    adapter = FakeXray()
    adapter.fail = True
    tick(adapter)
    with Session() as db:
        assert db.scalar(select(User)).sync == "error"
        assert not db.get(Setting, "worker").value["ok"]
    adapter.fail = False
    tick(adapter)
    with Session() as db:
        assert db.scalar(select(User)).sync == "applied"


def test_expiry_enforced_when_stats_unavailable():
    import_data(payload())
    with Session.begin() as db:
        db.scalar(select(User)).expires_at = now() - 10
    adapter = FakeXray()
    adapter.stats_fail = True
    tick(adapter)
    assert not adapter.users
