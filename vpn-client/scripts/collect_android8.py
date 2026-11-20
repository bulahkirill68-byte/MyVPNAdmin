"""Collect the independent API-26 compatibility build and per-ABI APKs."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1] / 'android-8'
outputs = ROOT / 'app/build/outputs/apk/release'
metadata = json.loads((outputs / 'output-metadata.json').read_text(encoding='utf-8'))
destination = ROOT / 'releases'
destination.mkdir(parents=True, exist_ok=True)
manifest = {}
for item in metadata['elements']:
    source = outputs / item['outputFile']
    if 'unsigned' in source.name:
        raise RuntimeError('Android 8 release APK must be signed')
    version = item['versionName'].removesuffix('-android8')
    abi = next((f['value'] for f in item['filters'] if f['filterType'] == 'ABI'), '')
    name = f'RealityVPN-Android8-{version}' + (f'-{abi}' if abi else '') + '.apk'
    target = destination / name
    shutil.copy2(source, target)
    manifest[name] = {'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'bytes': target.stat().st_size}
(destination / 'checksums.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
