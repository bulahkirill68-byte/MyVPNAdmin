from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from app.db import User


def status(user: User, at: int) -> str:
    if user.deleted or user.intent == "revoked":
        return "revoked"
    if user.intent == "paused":
        return "paused"
    if user.expires_at is not None and user.expires_at <= at:
        return "expired"
    if user.quota_bytes is not None and user.used_bytes >= user.quota_bytes:
        return "quota_exceeded"
    return "active"


def renewal(expires: int | None, days: int, mode: str, at: int) -> int:
    return (max(at, expires or at) if mode == "expiry" else at) + days * 86400


def counter_delta(previous: int, current: int, restarted: bool = False) -> int:
    return current if restarted or current < previous else current - previous


def link(user: User, server: dict) -> str:
    query = urlencode(dict(encryption="none", security="reality", type="tcp", flow="xtls-rprx-vision",
                           sni=server["sni"], fp="chrome", pbk=server["public_key"], sid=server["short_id"]))
    return f"vless://{user.uuid}@{server['ip']}:{server['port']}?{query}#{quote(user.name)}"


def utc_date(value: int) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat()
