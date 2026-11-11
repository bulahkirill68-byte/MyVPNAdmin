import json
import logging
import os
import time

import grpc
from filelock import FileLock
from sqlalchemy import delete, select

from app.db import DATA, Sample, Server, Session, Setting, User, audit, now
from app.domain import counter_delta, status
from app.xray import Xray

log = logging.getLogger("worker")
INTERVAL = max(5, int(os.environ.get("POLL_SECONDS", "15")))


def tick(adapter):
    with Session.begin() as db:
        server = db.get(Server, 1)
        if not server:
            heartbeat = db.get(Setting, "worker")
            value = {"at": now(), "ok": False, "stats": False, "reason": "Сервер ещё не импортирован"}
            if heartbeat:
                heartbeat.value = value
            else:
                db.add(Setting(key="worker", value=value))
            return
        stamp = now()
        previous = db.get(Setting, "worker")
        old = previous.value if previous else {}
        stats_ok = True
        try:
            uptime, counters = adapter.stats()
        except Exception as exc:
            log.warning("stats_unavailable: %s", type(exc).__name__)
            stats_ok = False
            uptime, counters = None, {}
        # Compare estimated process start, not just uptime (restart can outlive polling gap).
        started = stamp - uptime if uptime is not None else old.get("started")
        restarted = (started is not None and old.get("started") is not None
                     and abs(started - old["started"]) > 3)
        errors = 0
        for user in db.scalars(select(User)):
            delta = 0
            for direction, attr in [("uplink", "last_up"), ("downlink", "last_down")]:
                key = f"user>>>{user.email}>>>traffic>>>{direction}"
                if key in counters:
                    value = max(0, counters[key])
                    delta += counter_delta(getattr(user, attr), value, restarted)
                    setattr(user, attr, value)
                elif restarted:
                    setattr(user, attr, 0)
            if delta:
                user.used_bytes += delta
                user.last_activity = stamp
                db.add(Sample(user_id=user.id, delta=delta, at=stamp))
            if user.quota_bytes:
                percent = user.used_bytes * 100 / user.quota_bytes
                threshold = next((x for x in [100, 95, 80] if percent >= x), 0)
                if threshold > user.notified:
                    audit(db, "worker", "quota_notification", user.id, f"{threshold}%")
                    user.notified = threshold
            desired = status(user, stamp)
            try:
                if desired == "active":
                    if user.applied_uuid and user.applied_uuid != user.uuid:
                        adapter.remove(server.metadata_json["tag"], user.email)
                    adapter.ensure(server.metadata_json["tag"], user.uuid, user.email, user.historical_uuids)
                    user.applied_uuid = user.uuid
                else:
                    adapter.remove(server.metadata_json["tag"], user.email)
                    user.applied_uuid = None
                if user.sync != "applied" or user.error:
                    audit(db, "worker", "applied", user.id, desired)
                user.sync, user.error = "applied", None
            except Exception as exc:
                errors += 1
                if isinstance(exc, grpc.RpcError):
                    message = f"Xray API: {exc.code().name}. Проверьте inbound tag, версию и доступность API"
                elif isinstance(exc, RuntimeError):
                    message = str(exc)
                else:
                    message = f"Не удалось применить: {type(exc).__name__}"
                user.sync, user.error = "error", message
                if old.get("ok", True):
                    audit(db, "worker", "apply_error", user.id, user.error)
        info = {"at": stamp, "ok": errors == 0 and stats_ok, "stats": stats_ok, "uptime": uptime,
                "started": started, "errors": errors, "interval": INTERVAL}
        if not stats_ok:
            info["reason"] = "StatsService недоступен; трафик не измеряется"
        if previous:
            previous.value = info
        else:
            db.add(Setting(key="worker", value=info))
        db.execute(delete(Sample).where(Sample.at < stamp - 90 * 86400))


def main():
    from app.cli import backup
    from app.logging_config import configure
    configure()
    with FileLock(str(DATA / "worker.lock"), timeout=0):
        adapter = Xray()
        last_backup = 0
        while True:
            try:
                tick(adapter)
                if now() - last_backup >= 86400:
                    backup()
                    last_backup = now()
                log.info(json.dumps({"job": "reconcile", "at": now()}))
            except Exception as exc:
                # SQL exceptions can contain query parameters: never log their raw traceback.
                log.error("worker_tick_failed: %s", type(exc).__name__)
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
