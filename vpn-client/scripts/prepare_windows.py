"""Prepare pinned Windows engine and native helper. Run from any directory."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import urllib.request
import zipfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'windows' / 'assets'
VERSION = '26.11.9'


def download(url, destination):
    request = urllib.request.Request(url, headers={'User-Agent': 'RealityVPN-build'})
    with urllib.request.urlopen(request, timeout=180) as response, open(destination, 'wb') as output:
        shutil.copyfileobj(response, output)


def main():
    engine = ASSETS / 'engine'
    native = ASSETS / 'native'
    engine.mkdir(parents=True, exist_ok=True)
    native.mkdir(parents=True, exist_ok=True)
    local = os.environ.get('XRAY_WINDOWS_DIR')
    with tempfile.TemporaryDirectory() as temp:
        if local:
            source = Path(local)
        else:
            archive = Path(temp) / 'xray.zip'
            download(f'https://github.com/XTLS/Xray-core/releases/download/v{VERSION}/Xray-windows-64.zip', archive)
            # Release digest is obtained separately and checked before extraction.
            digest = Path(temp) / 'digest'
            download(f'https://github.com/XTLS/Xray-core/releases/download/v{VERSION}/Xray-windows-64.zip.dgst', digest)
            sha = hashlib.sha256(archive.read_bytes()).hexdigest()
            if sha.lower() not in digest.read_text().lower():
                raise RuntimeError('Xray archive SHA256 mismatch')
            source = Path(temp) / 'engine'
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(source)
        for name in ['xray.exe', 'wintun.dll', 'geoip.dat', 'geosite.dat', 'LICENSE']:
            if (source / name).exists():
                shutil.copy2(source / name, engine / name)
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64', f'/out:{native / "StopConsole.exe"}', str(ROOT / 'windows/native/StopConsole.cs')], check=True)
    subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64', '/reference:System.Web.Extensions.dll', f'/out:{native / "RuntimeControl.exe"}', str(ROOT / 'windows/native/RuntimeControl.cs')], check=True)
    manifest = {name: hashlib.sha256(file.read_bytes()).hexdigest() for name, file in [('xray.exe', engine / 'xray.exe'), ('StopConsole.exe', native / 'StopConsole.exe'), ('RuntimeControl.exe', native / 'RuntimeControl.exe')]}
    (engine / 'integrity.json').write_text(json.dumps(manifest, indent=2))
    # Original shield icon, a 32-bit ICO with a Windows-compatible DIB image.
    size = 256
    pixels = bytearray()
    for y in reversed(range(size)):
        for x in range(size):
            sx, sy = x / 4, y / 4
            inside = 13 <= sx <= 50 and 10 <= sy <= 36 or (36 < sy < 56 and abs(sx - 31.5) < (56 - sy) * .95)
            pixels.extend((239, 157, 166, 255) if inside else (28, 19, 16, 255))
    dib = struct.pack('<IiiHHIIiiII', 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0) + pixels + bytes(size * size // 8)
    (ASSETS / 'icon.ico').write_bytes(struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', 0, 0, 0, 0, 1, 32, len(dib), 22) + dib)
    print('Windows resources ready:', ASSETS)


if __name__ == '__main__':
    main()
