from app.cli import import_data
from app.db import Session, User
from app.routing import client_config, export, test_route as route_test
from app.schemas import Routing
from test_api import client
from test_worker import payload


def test_ru_split_tunnel_includes_international_services_and_ip_dns_strategy():
    policy = Routing()
    rules = export(policy)
    assert rules["domainStrategy"] == "IPOnDemand"
    for target in ["gosuslugi.ru", "банк.рф", "yandex.com", "cdn.yastatic.net", "vk.com", "ozonusercontent.com"]:
        assert route_test(policy, target)["outbound"] == "direct"
    assert rules["rules"][-1]["outboundTag"] == "proxy"


def test_full_config_uses_client_side_direct_and_only_public_reality_key():
    server = payload()["server"]
    user = User(name="Тест", uuid=payload()["users"][0]["uuid"], policy="ru-direct")
    config = client_config(user, server, Routing())
    assert config["routing"]["domainStrategy"] == "IPOnDemand"
    assert {o["tag"] for o in config["outbounds"]} == {"proxy", "direct", "block"}
    proxy = config["outbounds"][0]
    assert proxy["settings"]["vnext"][0]["users"][0]["id"] == user.uuid
    assert proxy["streamSettings"]["realitySettings"]["publicKey"] == server["public_key"]
    assert all(i["listen"] == "127.0.0.1" for i in config["inbounds"])
    assert "privateKey" not in proxy["streamSettings"]["realitySettings"]


def test_api_config_export_requires_login_and_audits():
    import_data(payload())
    c = client()
    with Session() as db:
        user = db.query(User).first()
        user_id = user.id
    result = c.get(f"/api/users/{user_id}/client-config")
    assert result.status_code == 200
    assert result.json()["routing"]["domainStrategy"] == "IPOnDemand"
    assert any(e["action"] == "client_config_exported" for e in c.get("/api/audit").json())
