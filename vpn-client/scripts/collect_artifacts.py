"""Copy validated Android release APK and write an artifact SHA256 manifest."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
release = ROOT / 'releases'
android = release / 'android'
android.mkdir(parents=True, exist_ok=True)
source = ROOT / 'android/app/build/outputs/apk/release/app-release.apk'
if not source.exists():
    raise RuntimeError('Signed release APK missing. Run assembleRelease with a signing identity first.')
metadata = json.loads((source.parent / 'output-metadata.json').read_text(encoding='utf-8'))
version = metadata['elements'][0]['versionName']
shutil.copy2(source, android / f'RealityVPN-{version}.apk')
manifest = {}
for folder, pattern in [(release / 'windows', '*.exe'), (android, '*.apk')]:
    for file in folder.glob(pattern):
        manifest[str(file.relative_to(release)).replace('\\', '/')] = {'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'bytes': file.stat().st_size}
(release / 'checksums.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
