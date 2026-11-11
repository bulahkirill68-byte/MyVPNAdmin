import grpc
import pytest
from app import xray_pb2 as pb
from app.xray import Xray


class Exists(grpc.RpcError):
    def details(self):
        return "User email already exists."


def test_reconciliation_replaces_only_known_historical_identity(monkeypatch):
    adapter = Xray()
    calls = []
    account = pb.Account(id="old", flow="xtls-rprx-vision")
    existing = pb.User(email="owned", account=pb.TypedMessage(type="xray.proxy.vless.Account",
                                                             value=account.SerializeToString()))

    def add(tag, uid, email):
        calls.append(("add", uid))
        if len(calls) == 1:
            raise Exists()

    monkeypatch.setattr(adapter, "add", add)
    monkeypatch.setattr(adapter, "remove", lambda tag, email: calls.append(("remove", email)))
    monkeypatch.setattr(adapter, "call", lambda *args: pb.GetInboundUserResponse(users=[existing]))
    adapter.ensure("tag", "new", "owned", ["old"])
    assert calls == [("add", "new"), ("remove", "owned"), ("add", "new")]
    calls.clear()
    with pytest.raises(RuntimeError, match="Конфликт"):
        adapter.ensure("tag", "new", "owned", [])
    assert calls == [("add", "new")]
    adapter.channel.close()
