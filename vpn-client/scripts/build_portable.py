"""Create a single-file portable with a persistent, content-addressed unpack cache."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / 'windows'
RELEASE = ROOT / 'releases/windows'
APP = RELEASE / 'win-unpacked'


def main():
    version = json.loads((WINDOWS / 'package.json').read_text())['version']
    digest = hashlib.sha256()
    for file in sorted(APP.rglob('*')):
        if file.is_file():
            digest.update(file.relative_to(APP).as_posix().encode())
            with file.open('rb') as data:
                for chunk in iter(lambda: data.read(1024 * 1024), b''):
                    digest.update(chunk)
    build_key = version + '-' + digest.hexdigest()[:16]
    compiler = os.environ.get('MAKENSIS')
    if not compiler:
        cache = Path(os.environ['LOCALAPPDATA']) / 'electron-builder/Cache/nsis-3.0.4.1'
        compiler = str(next(file for file in cache.rglob('makensis.exe') if file.parent.name != 'Bin'))
    output = RELEASE / f'RealityVPN-{version}-portable.exe'
    subprocess.run([compiler, '/V2', f'/DVERSION={version}', f'/DBUILD_KEY={build_key}', f'/DOUTPUT_FILE={output}', f'/DAPP_DIR={APP}', f'/DICON_FILE={WINDOWS / "assets/icon.ico"}', str(WINDOWS / 'native/portable.nsi')], check=True)
    (RELEASE / 'portable-build.json').write_text(json.dumps({'version': version, 'buildKey': build_key, 'cache': f'%LOCALAPPDATA%/RealityVPNClient/portable/{build_key}'}, indent=2))
    print('Cached portable ready:', output)


if __name__ == '__main__':
    main()
