"""Typed gRPC adapter; all RPCs have deadlines, no Xray subprocess or config writes."""
import grpc
from app import xray_pb2 as pb

HANDLER = "/xray.app.proxyman.command.HandlerService/"
STATS = "/xray.app.stats.command.StatsService/"


class Xray:
    def __init__(self):
        self.channel = grpc.insecure_channel("127.0.0.1:10085")

    def call(self, method, request, response):
        return self.channel.unary_unary(method, request_serializer=lambda x: x.SerializeToString(),
                                       response_deserializer=response.FromString)(request, timeout=4)

    def add(self, tag: str, uid: str, email: str):
        account = pb.Account(id=uid, flow="xtls-rprx-vision", encryption="none")
        user = pb.User(level=0, email=email, account=pb.TypedMessage(
            type="xray.proxy.vless.Account", value=account.SerializeToString()))
        operation = pb.AddUserOperation(user=user)
        self.call(HANDLER + "AlterInbound", pb.AlterInboundRequest(tag=tag, operation=pb.TypedMessage(
            type="xray.app.proxyman.command.AddUserOperation", value=operation.SerializeToString())), pb.Empty)

    def remove(self, tag: str, email: str):
        operation = pb.RemoveUserOperation(email=email)
        try:
            self.call(HANDLER + "AlterInbound", pb.AlterInboundRequest(tag=tag, operation=pb.TypedMessage(
                type="xray.app.proxyman.command.RemoveUserOperation", value=operation.SerializeToString())), pb.Empty)
        except grpc.RpcError as exc:
            detail = (exc.details() or "").lower()
            if f"user {email.lower()} not found" not in detail:
                raise

    def ensure(self, tag: str, uid: str, email: str, historical_uuids: list[str] | None = None):
        try:
            self.add(tag, uid, email)
        except grpc.RpcError as exc:
            if "already exists" not in (exc.details() or "").lower():
                raise
            # Verify identity on versions supporting GetInboundUsers. Do not remove unknown users.
            try:
                response = self.call(HANDLER + "GetInboundUsers", pb.GetInboundUserRequest(tag=tag, email=email),
                                     pb.GetInboundUserResponse)
            except grpc.RpcError as lookup:
                if lookup.code() == grpc.StatusCode.UNIMPLEMENTED:
                    raise RuntimeError("Xray требует GetInboundUsers для проверки UUID; обновите Xray") from lookup
                raise
            matches = [u for u in response.users if u.email == email]
            if len(matches) != 1 or matches[0].account.type != "xray.proxy.vless.Account":
                raise RuntimeError("Конфликт email/UUID Xray; требуется проверка импорта")
            actual = pb.Account.FromString(matches[0].account.value).id
            if actual == uid:
                return
            if actual in (historical_uuids or []):
                # Static config can resurrect a revoked credential on a host Xray restart.
                # Only replace an identity whose ownership was recorded by this panel.
                self.remove(tag, email)
                self.add(tag, uid, email)
                return
            raise RuntimeError("Конфликт email/UUID Xray; требуется проверка импорта")

    def stats(self) -> tuple[int, dict[str, int]]:
        uptime = self.call(STATS + "GetSysStats", pb.Empty(), pb.SysStatsResponse).Uptime
        stats = self.call(STATS + "QueryStats", pb.QueryStatsRequest(pattern="user>>>", reset=False),
                          pb.QueryStatsResponse)
        return uptime, {s.name: s.value for s in stats.stat}
