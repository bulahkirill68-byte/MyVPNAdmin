"""Real Xray + local DNS/TLS regression. No external server or system VPN changes."""
import argparse
from datetime import datetime, timedelta, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import socketserver
import ssl
import struct
import subprocess
import tempfile
import threading
import time
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--temp-root', type=Path)
    args = parser.parse_args()
    queries = []

    class DnsHandler(socketserver.BaseRequestHandler):
        def handle(self):
            packet, connection = self.request
            cursor = 12
            labels = []
            while packet[cursor]:
                size = packet[cursor]
                labels.append(packet[cursor + 1:cursor + 1 + size].decode())
                cursor += size + 1
            cursor += 1
            kind, _ = struct.unpack('!HH', packet[cursor:cursor + 4])
            queries.append('.'.join(labels).lower())
            answer = b'\xc0\x0c' + struct.pack('!HHIH', 1, 1, 30, 4) + socket.inet_aton('127.0.0.1') if kind == 1 else b''
            response = packet[:2] + struct.pack('!HHHHH', 0x8180, 1, int(bool(answer)), 0, 0) + packet[12:cursor + 4] + answer
            connection.sendto(response, self.client_address)

    class HttpHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'local-direct-ok'
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    with tempfile.TemporaryDirectory(prefix='reality-direct-', dir=args.temp_root) as temp:
        temp = Path(temp)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Local routing regression')])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
                .not_valid_after(datetime.now(timezone.utc) + timedelta(hours=1))
                .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName('ya.ru'), x509.DNSName('yandex.ru')]), critical=False)
                .sign(key, hashes.SHA256()))
        cert_file, key_file = temp / 'cert.pem', temp / 'key.pem'
        cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        dns = socketserver.ThreadingUDPServer(('127.0.0.1', 0), DnsHandler)
        server = ThreadingHTTPServer(('127.0.0.1', 0), HttpHandler)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert_file, key_file)
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        for service in [dns, server]:
            threading.Thread(target=service.serve_forever, daemon=True).start()
        process = None
        try:
            config = json.loads((ROOT / 'android/app/build/test-split-dns.json').read_text())
            proxy_port = free_port()
            config['inbounds'] = [{'tag': 'tun', 'protocol': 'http', 'listen': '127.0.0.1', 'port': proxy_port}]
            # Substitute local test resources; preserve Java-generated rules/tags/DNS policy.
            config['outbounds'][0]['settings']['vnext'][0].update(address='127.0.0.1', port=free_port())
            direct_dns = config['dns']['servers'][1]
            direct_dns.update(address='127.0.0.1', port=dns.server_address[1])
            config['dns']['servers'] = [config['dns']['servers'][0], direct_dns]
            file = temp / 'config.json'
            file.write_text(json.dumps(config))
            engine = ROOT / 'windows/assets/engine'
            with (temp / 'xray.log').open('wb') as log:
                process = subprocess.Popen([str(engine / 'xray.exe'), 'run', '-config', str(file)], stdout=log, stderr=log,
                                           env={**os.environ, 'XRAY_LOCATION_ASSET': str(engine)}, creationflags=subprocess.CREATE_NO_WINDOW)
                deadline = time.monotonic() + 8
                while True:
                    try:
                        with socket.create_connection(('127.0.0.1', proxy_port), timeout=.2):
                            break
                    except OSError:
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError('Test core did not start')
                        time.sleep(.05)
                trust = ssl.create_default_context(cafile=str(cert_file))
                for host in ['ya.ru', 'yandex.ru']:
                    connection = http.client.HTTPSConnection('127.0.0.1', proxy_port, context=trust, timeout=8)
                    connection.set_tunnel(host, server.server_address[1])
                    connection.request('GET', '/')
                    response = connection.getresponse()
                    assert response.status == 200 and response.read() == b'local-direct-ok', host
                    connection.close()
                assert {'ya.ru', 'yandex.ru'}.issubset(queries), queries
                print('PASS: ya.ru and yandex.ru TLS connections use direct DNS/direct egress even when the VPN endpoint is unavailable. All test traffic stayed on localhost.')
        finally:
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            for service in [dns, server]:
                service.shutdown()
                service.server_close()


if __name__ == '__main__':
    main()
