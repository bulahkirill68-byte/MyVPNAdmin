"""Download Android dependencies and optionally a portable local build toolchain."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def download(url, file, expected=None):
    file.parent.mkdir(parents=True, exist_ok=True)
    if not file.exists():
        print('Downloading', url, flush=True)
        request = urllib.request.Request(url, headers={'User-Agent': 'RealityVPN-build'})
        with urllib.request.urlopen(request, timeout=240) as source, open(str(file) + '.part', 'wb') as target:
            shutil.copyfileobj(source, target)
        Path(str(file) + '.part').replace(file)
    if expected and hashlib.sha256(file.read_bytes()).hexdigest() != expected:
        raise RuntimeError(f'SHA256 mismatch: {file}')
    return file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--toolchain', type=Path)
    args = parser.parse_args()
    jobs = [
        ('https://github.com/2dust/AndroidLibXrayLite/releases/download/v26.11.9/libv2ray.aar', ROOT / 'android/app/libs/libv2ray.aar', 'cdfef146218233a31a8b52c8b1016557730d3b63fc121d4c84cacea50e669155'),
        ('https://github.com/2dust/AndroidLibXrayLite/releases/download/v26.11.9/libv2ray-sources.jar', ROOT / 'android/app/libs/libv2ray-sources.jar', 'c6d5eda3d69739c7cdfa177f607b5549b6764062ed2ee9a65c600c2fc26e8ccf'),
    ]
    assets = ROOT / 'android/app/src/main/assets'
    assets.mkdir(parents=True, exist_ok=True)
    for name in ['geoip.dat', 'geosite.dat']:
        local = ROOT / 'windows/assets/engine' / name
        if local.exists():
            shutil.copy2(local, assets / name)
        else:
            jobs.append((f'https://github.com/XTLS/Xray-core/releases/download/v26.11.9/{name}', assets / name, None))
    if args.toolchain:
        cache = args.toolchain
        cache.mkdir(parents=True, exist_ok=True)
        jobs.extend([
            ('https://aka.ms/download-jdk/microsoft-jdk-17.0.17-windows-x64.zip', cache / 'jdk.zip', None),
            ('https://services.gradle.org/distributions/gradle-8.13-bin.zip', cache / 'gradle.zip', None),
            ('https://dl.google.com/android/repository/commandlinetools-win-13114758_latest.zip', cache / 'sdk.zip', None),
        ])
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda job: download(*job), jobs))
    if args.toolchain:
        for name, target in [('jdk', cache / 'java'), ('gradle', cache / 'gradle'), ('sdk', cache / 'sdk/cmdline-tools-bootstrap')]:
            if not target.exists():
                with zipfile.ZipFile(cache / f'{name}.zip') as archive:
                    archive.extractall(target)
        java = next((cache / 'java').iterdir())
        sdk = cache / 'sdk'
        commandline = sdk / 'cmdline-tools/latest'
        if not commandline.exists():
            commandline.parent.mkdir(exist_ok=True)
            shutil.move(str(sdk / 'cmdline-tools-bootstrap/cmdline-tools'), commandline)
        env = {**os.environ, 'JAVA_HOME': str(java), 'ANDROID_HOME': str(sdk)}
        sdkmanager = commandline / 'bin/sdkmanager.bat'
        subprocess.run([str(sdkmanager), f'--sdk_root={sdk}', '--licenses'], input='y\n' * 100, text=True, env=env, check=True)
        subprocess.run([str(sdkmanager), f'--sdk_root={sdk}', 'platforms;android-35', 'build-tools;35.0.0', 'platform-tools'], env=env, check=True)
        print('JAVA_HOME=' + str(java))
        print('ANDROID_HOME=' + str(sdk))
    print('Android dependencies ready')


if __name__ == '__main__':
    main()
