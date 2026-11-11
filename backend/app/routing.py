import ipaddress
from app.schemas import Routing


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
            {"type": "field", "domain": ["geosite:category-ru", "domain:ru", "domain:su", "domain:xn--p1ai"],
             "outboundTag": "direct"},
            {"type": "field", "ip": ["geoip:ru"], "outboundTag": "direct"},
        ]
    rules.append({"type": "field", "network": "tcp,udp", "outboundTag": "proxy"})
    return {"domainStrategy": "IPIfNonMatch", "rules": rules}


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
