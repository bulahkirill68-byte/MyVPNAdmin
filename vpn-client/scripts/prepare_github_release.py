"""Validate current client release files and prepare checksums for GitHub assets."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
windows_version = json.loads((ROOT / 'windows/package.json').read_text(encoding='utf-8'))['version']
android_metadata = json.loads((ROOT / 'android/app/build/outputs/apk/release/output-metadata.json').read_text(encoding='utf-8'))
android_version = android_metadata['elements'][0]['versionName']
android8_metadata = json.loads((ROOT / 'android-8/app/build/outputs/apk/release/output-metadata.json').read_text(encoding='utf-8'))
android8_version = android8_metadata['elements'][0]['versionName'].removesuffix('-android8')
files = [
    ROOT / f'releases/windows/RealityVPN-{windows_version}-portable.exe',
    ROOT / f'releases/windows/RealityVPN-{windows_version}-setup.exe',
    ROOT / f'releases/android/RealityVPN-{android_version}.apk',
    ROOT / f'android-8/releases/RealityVPN-Android8-{android8_version}.apk',
]
files += [ROOT / f'android-8/releases/RealityVPN-Android8-{android8_version}-{abi}.apk' for abi in ['arm64-v8a', 'armeabi-v7a', 'x86', 'x86_64']]
lines = []
for file in files:
    if not file.is_file():
        raise RuntimeError(f'Release asset missing: {file}')
    digest = hashlib.sha256()
    with file.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    lines.append(f'{digest.hexdigest()}  {file.name}')
    print(f'{file.name}: {file.stat().st_size} bytes')
output = ROOT / 'releases/github'
output.mkdir(parents=True, exist_ok=True)
(output / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('SHA256 checksums:', output / 'SHA256SUMS.txt')
