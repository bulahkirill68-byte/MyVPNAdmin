from concurrent.futures import ThreadPoolExecutor
import grpc
from app import xray_pb2 as pb
from app.xray import Xray


def test_real_grpc_wire_contract():
    seen = []

    def alter(request, context):
        seen.append(request)
        return pb.Empty()

    server = grpc.server(ThreadPoolExecutor(max_workers=2))
    server.add_generic_rpc_handlers([
        grpc.method_handlers_generic_handler("xray.app.proxyman.command.HandlerService", {
            "AlterInbound": grpc.unary_unary_rpc_method_handler(alter,
                request_deserializer=pb.AlterInboundRequest.FromString,
                response_serializer=pb.Empty.SerializeToString),
        }),
        grpc.method_handlers_generic_handler("xray.app.stats.command.StatsService", {
            "GetSysStats": grpc.unary_unary_rpc_method_handler(lambda r,c: pb.SysStatsResponse(Uptime=123),
                request_deserializer=pb.Empty.FromString, response_serializer=pb.SysStatsResponse.SerializeToString),
            "QueryStats": grpc.unary_unary_rpc_method_handler(lambda r,c: pb.QueryStatsResponse(
                stat=[pb.Stat(name="user>>>test>>>traffic>>>uplink", value=42)]),
                request_deserializer=pb.QueryStatsRequest.FromString, response_serializer=pb.QueryStatsResponse.SerializeToString),
        })])
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    adapter = Xray()
    adapter.channel.close()
    adapter.channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    try:
        adapter.add("vless-reality", "uuid", "email")
        operation = seen[0].operation
        assert operation.type == "xray.app.proxyman.command.AddUserOperation"
        user = pb.AddUserOperation.FromString(operation.value).user
        assert user.email == "email" and user.level == 0
        assert user.account.type == "xray.proxy.vless.Account"
        account = pb.Account.FromString(user.account.value)
        assert account.id == "uuid" and account.flow == "xtls-rprx-vision"
        adapter.remove("vless-reality", "email")
        assert pb.RemoveUserOperation.FromString(seen[1].operation.value).email == "email"
        assert adapter.stats() == (123, {"user>>>test>>>traffic>>>uplink": 42})
    finally:
        adapter.channel.close()
        server.stop(0)
