#!/usr/bin/env python3
"""Read-only allowlist export. Run on host as root; never exports privateKey."""
import argparse
import json
import sys
import uuid


def extract(config, ip, public_key, expires=None):
    if config.get("api", {}).get("listen") != "127.0.0.1:10085":
        raise ValueError("API должен слушать 127.0.0.1:10085; исправьте вручную с backup и xray run -test")
    services = config.get("api", {}).get("services", [])
    if not {"HandlerService", "StatsService"} <= set(services):
        raise ValueError("Нужны HandlerService и StatsService")
    level = config.get("policy", {}).get("levels", {}).get("0", {})
    if not level.get("statsUserUplink") or not level.get("statsUserDownlink"):
        raise ValueError("Включите статистику уровня 0")
    inbound = next(x for x in config["inbounds"] if x.get("tag") == "vless-reality")
    if inbound["protocol"] != "vless":
        raise ValueError("Ожидается VLESS")
    reality = inbound["streamSettings"]["realitySettings"]
    users = []
    for i, client in enumerate(inbound["settings"]["clients"]):
        uuid.UUID(client["id"])
        if not client.get("email"):
            raise ValueError("У существующего пользователя нет email. Добавьте стабильный email вручную с backup/test")
        if client.get("level", 0) != 0 or client.get("flow") != "xtls-rprx-vision":
            raise ValueError("Поддерживается уровень 0 и xtls-rprx-vision")
        users.append({"name": f"Импортированный · {i + 1}", "uuid": client["id"],
                      "email": client["email"], "expires_at": expires})
    return {"server": {"ip": ip, "port": inbound["port"], "tag": inbound["tag"],
                       "sni": reality["serverNames"][0], "public_key": public_key,
                       "short_id": reality["shortIds"][0]}, "users": users}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/usr/local/etc/xray/config.json")
    parser.add_argument("--ip", required=True)
    parser.add_argument("--public-key", required=True, help="Public Key из защищённого access-файла (не privateKey)")
    parser.add_argument("--expires-at", type=int, help="Существующий срок UTC Unix timestamp; без параметра бессрочно")
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as f:
        payload = extract(json.load(f), args.ip, args.public_key, args.expires_at)
    json.dump(payload, sys.stdout, ensure_ascii=False)
