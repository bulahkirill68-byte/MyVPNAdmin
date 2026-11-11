from app.db import User
from app.domain import counter_delta, renewal, status
import pytest


@pytest.mark.parametrize("intent,expires,quota,used,expected", [
    ("active", None, None, 0, "active"), ("active", 100, None, 0, "expired"),
    ("active", 101, None, 0, "active"), ("paused", None, None, 0, "paused"),
    ("revoked", None, None, 0, "revoked"), ("active", None, 100, 100, "quota_exceeded"),
    ("active", None, 100, 99, "active"), ("active", 100, 100, 100, "expired"),
])
def test_states(intent, expires, quota, used, expected):
    user = User(intent=intent, expires_at=expires, quota_bytes=quota, used_bytes=used, deleted=False)
    assert status(user, 100) == expected


def test_renewal_modes():
    assert renewal(200, 7, "expiry", 100) == 200 + 7 * 86400
    assert renewal(50, 1, "expiry", 100) == 100 + 86400
    assert renewal(200, 1, "now", 100) == 100 + 86400
    assert renewal(None, 1, "expiry", 100) == 100 + 86400


def test_counter_reset_and_restart():
    assert counter_delta(100, 150) == 50
    assert counter_delta(150, 150) == 0
    assert counter_delta(150, 20) == 20
    assert counter_delta(20, 150, True) == 150
