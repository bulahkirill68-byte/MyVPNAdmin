"""The only privileged bridge is a narrow peer-checked host Unix socket, never a Docker socket."""
import http.client
import json
import os
import socket

SOCKET_PATH = os.environ.get("HOST_AGENT_SOCKET", "/run/reality-agent/control.sock")


class UnixHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        if not hasattr(socket, "AF_UNIX"):
            raise OSError("Host agent requires Linux Unix sockets")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET_PATH)


def request(method: str, path: str, data: dict | None = None) -> dict:
    connection = UnixHTTPConnection("localhost", timeout=8)
    try:
        body = json.dumps(data).encode() if data is not None else None
        connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        payload = json.loads(response.read(131072))
        if response.status >= 400:
            raise ValueError(payload.get("detail", "Хостовый агент отклонил операцию"))
        return payload
    finally:
        connection.close()
