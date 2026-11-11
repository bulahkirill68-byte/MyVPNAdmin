import ipaddress
from app.schemas import Routing

# Explicit fallbacks for Russian services using international TLDs/CDNs; GeoSite remains authoritative.
RU_DOMAINS = ["ru", "su", "xn--p1ai", "ya.ru", "yandex.com", "yandex.net", "yastatic.net",
              "vk.com", "vk.me", "vkuser.net", "userapi.com", "mycdn.me", "mail.ru", "ok.ru",
              "gosuslugi.ru", "sberbank.ru", "sber.ru", "tbank.ru", "tinkoff.ru", "ozon.ru",
              "ozonusercontent.com", "wildberries.ru", "wb.ru", "wbbasket.ru"]


def export(policy: Routing) -> dict:
    rules = []
    # Explicit client exceptions override user and global policy. First match wins.
    for rule in [*policy.local_rules, *policy.user_rules, *policy.rules]:
        rules.append({"type": "field", rule.kind: rule.values, "outboundTag": rule.outbound})
    if policy.preset != "all-proxy":
        rules += [
            {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
            {"type": "field", "domain": ["full:localhost", "domain:lan", "domain:local", "domain:home.arpa"],
             "outboundTag": "direct"},
            {"type": "field", "domain": ["geosite:category-ru", *[f"domain:{d}" for d in RU_DOMAINS]],
             "outboundTag": "direct"},
            {"type": "field", "ip": ["geoip:ru"], "outboundTag": "direct"},
        ]
    rules.append({"type": "field", "network": "tcp,udp", "outboundTag": "proxy"})
    # IPIfNonMatch + an unconditional final rule never reaches a DNS retry for unknown domains.
    # IPOnDemand resolves when evaluating GeoIP, including non-.ru domains hosted on Russian IPs.
    return {"domainStrategy": "IPOnDemand", "rules": rules}


def client_config(user, server: dict, policy: Routing) -> dict:
    policy = policy.model_copy(update={"preset": user.policy})
    return {
        "remarks": user.name,
        "log": {"loglevel": "warning"},
        "dns": {"servers": ["https+local://1.1.1.1/dns-query"], "queryStrategy": "UseIP"},
        "inbounds": [
            {"tag": "socks", "listen": "127.0.0.1", "port": 10808, "protocol": "socks",
             "settings": {"auth": "noauth", "udp": True},
             "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "routeOnly": True}},
            {"tag": "http", "listen": "127.0.0.1", "port": 10809, "protocol": "http", "settings": {}},
        ],
        "outbounds": [
            {"tag": "proxy", "protocol": "vless", "settings": {"vnext": [
                {"address": server["ip"], "port": server["port"], "users": [
                    {"id": user.uuid, "encryption": "none", "flow": "xtls-rprx-vision"}]}]},
             "streamSettings": {"network": "raw", "security": "reality", "realitySettings": {
                 "serverName": server["sni"], "fingerprint": "firefox", "publicKey": server["public_key"],
                 "shortId": server["short_id"], "spiderX": "/"}}},
            {"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIP"}},
            {"tag": "block", "protocol": "blackhole", "settings": {}},
        ],
        "routing": export(policy),
    }


def test_route(policy: Routing, target: str) -> dict:
    try:
        address = ipaddress.ip_address(target)
    except ValueError:
        address = None
        target = target.rstrip(".").encode("idna").decode("ascii").lower()
    unknown = False
    for i, rule in enumerate(export(policy)["rules"]):
        matched = "network" in rule
        for value in rule.get("domain", []):
            if address:
                continue
            if value.startswith("geosite:"):
                unknown = True
            elif value.startswith("full:"):
                matched |= target == value[5:]
            elif value.startswith("domain:"):
                matched |= target == value[7:] or target.endswith("." + value[7:])
            elif value.startswith("regexp:"):
                unknown = True  # Avoid untrusted regular expressions in server runtime.
            else:
                matched |= value.lower() in target
        for value in rule.get("ip", []):
            if value == "geoip:private" and address:
                matched |= address.is_private
            elif value.startswith("geoip:"):
                if address:
                    unknown = True
            elif address:
                try:
                    matched |= address in ipaddress.ip_network(value, strict=False)
                except ValueError:
                    unknown = True
        if matched:
            return {"outbound": rule["outboundTag"], "rule": i + 1, "approximate": unknown,
                    "note": "GeoIP/GeoSite и DNS проверяются клиентом; результат предварительный" if unknown
                    else "Совпадение с явным правилом"}
    return {"outbound": None, "approximate": True, "note": "Нет совпадения"}
