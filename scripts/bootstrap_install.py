"""Host bootstrap for the bundled installer, compatible with Ubuntu's Python 3.10+."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time

from public_ip import detect_public_ip, validate_ipv4

INSTALL = Path('/opt/reality-control')
BACKUPS = Path('/var/backups/reality-control-install')
CREDENTIALS = Path('/root/reality-control-admin.json')


def run(args, cwd=None, capture=False, input_text=None):
    env = {**os.environ, 'DEBIAN_FRONTEND': 'noninteractive', 'DOCKER_HOST': 'unix:///var/run/docker.sock'}
    env.pop('DOCKER_CONTEXT', None)
    return subprocess.run([str(x) for x in args], cwd=cwd, env=env, input=input_text,
                          text=True, capture_output=capture, check=True).stdout


def manifest(root):
    value = json.loads((root / 'BUNDLE-MANIFEST.json').read_text())
    if value.get('format') != 1 or value.get('project') != 'reality-control':
        raise ValueError('Неизвестный формат пакета')
    for entry in value['files']:
        name = PurePosixPath(entry['path'])
        if name.is_absolute() or '..' in name.parts or '\\' in entry['path']:
            raise ValueError('Недопустимый путь в manifest')
    return value


def check_existing(directory):
    if directory.is_symlink():
        raise ValueError('Каталог панели не должен быть symlink')
    if (directory / '.env').is_symlink() or (directory / 'data').is_symlink():
        raise ValueError('.env и data не должны быть symlink')
    if not directory.exists() or not any(directory.iterdir()):
        return []
    previous = directory / 'BUNDLE-MANIFEST.json'
    if previous.exists():
        entries = manifest(directory)['files']
        changed = [item['path'] for item in entries if not (directory / item['path']).is_file()
                   or (directory / item['path']).is_symlink()
                   or hashlib.sha256((directory / item['path']).read_bytes()).hexdigest() != item['sha256']]
        if changed:
            raise ValueError('Исходники изменены вручную; сохраните изменения перед обновлением: ' + ', '.join(changed))
        return [item['path'] for item in entries] + ['BUNDLE-MANIFEST.json']
    if (directory / '.git').is_dir():
        dirty = run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=directory, capture=True)
        if dirty.strip():
            raise ValueError('В Git-каталоге есть изменения. Установщик их не перезапишет')
        compose = directory / 'compose.yaml'
        if not compose.is_file() or 'name: reality-control' not in compose.read_text():
            raise ValueError('Каталог принадлежит другому приложению')
        tracked = run(['git', 'ls-files'], cwd=directory, capture=True).splitlines()
        return [name for name in tracked if (directory / name).is_file() and not (directory / name).is_symlink()]
    raise ValueError('Непустой /opt/reality-control не распознан как установка панели; перезапись запрещена')


def backup_existing(directory, names, destination=BACKUPS):
    if not directory.exists() or not any(directory.iterdir()):
        return None
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = str(time.time_ns())
    database = directory / 'data/panel.db'
    if database.exists():
        target = destination / f'panel-{stamp}.sqlite3'
        with sqlite3.connect(database) as source, sqlite3.connect(target) as saved:
            source.backup(saved)
            if saved.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Резервная копия SQLite не прошла проверку')
        target.chmod(0o600)
    archive = destination / f'source-{stamp}.tar.gz'
    with tarfile.open(archive, 'w:gz') as bundle:
        for name in sorted(set(names) | {'.env'}):
            path = directory / name
            if path.is_file() and not path.is_symlink():
                bundle.add(path, arcname=name, recursive=False)
    archive.chmod(0o600)
    return archive


def deploy_source(source, directory):
    value = manifest(source)
    directory.mkdir(parents=True, exist_ok=True)
    for entry in [*value['files'], {'path': 'BUNDLE-MANIFEST.json', 'mode': 0o644}]:
        name = entry['path']
        original = source / name
        target = directory / name
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != directory.parent):
            raise ValueError('Symlink в целевом пути: ' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.install-', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(original.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, entry['mode'])
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)


def configure_env(directory, ip):
    target = directory / '.env'
    text = target.read_text() if target.exists() else (directory / '.env.example').read_text()
    lines = [line for line in text.splitlines() if not line.startswith('PANEL_PUBLIC_IP=')]
    target.write_text('\n'.join([*lines, f'PANEL_PUBLIC_IP={validate_ipv4(ip)}']) + '\n')
    target.chmod(0o600)


def ensure_docker():
    if not shutil.which('docker'):
        run(['apt-get', 'install', '-y', 'ca-certificates', 'curl'])
        keys = Path('/etc/apt/keyrings')
        keys.mkdir(mode=0o755, parents=True, exist_ok=True)
        keys.chmod(0o755)
        existing = any('download.docker.com/linux/ubuntu' in path.read_text(errors='ignore')
                       for path in Path('/etc/apt/sources.list.d').glob('*') if path.is_file())
        if not existing:
            key = keys / 'reality-docker.asc'
            run(['curl', '--fail', '--silent', '--show-error', '--location',
                 'https://download.docker.com/linux/ubuntu/gpg', '--output', key])
            key.chmod(0o644)
            os_release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
            codename = os_release.get('UBUNTU_CODENAME', os_release.get('VERSION_CODENAME', '')).strip('"')
            if not re.fullmatch('[a-z]+', codename):
                raise ValueError('Неизвестный Ubuntu codename')
            architecture = run(['dpkg', '--print-architecture'], capture=True).strip()
            if architecture not in ('amd64', 'arm64', 'armhf', 's390x', 'ppc64el'):
                raise ValueError('Архитектура не поддерживается Docker-пакетом')
            source_list = Path('/etc/apt/sources.list.d/reality-docker.sources')
            source_list.write_text(
                f'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: {codename}\n'
                f'Components: stable\nArchitectures: {architecture}\nSigned-By: {key}\n')
            source_list.chmod(0o644)
        run(['apt-get', 'update', '-qq'])
        run(['apt-get', 'install', '-y', 'docker-ce', 'docker-ce-cli', 'containerd.io',
             'docker-buildx-plugin', 'docker-compose-plugin'])
    try:
        run(['docker', 'compose', 'version'], capture=True)
    except subprocess.CalledProcessError:
        raise RuntimeError('Docker уже установлен, но Compose plugin отсутствует. Установите plugin без замены работающего Docker Engine.') from None
    try:
        run(['docker', 'info'], capture=True)
    except subprocess.CalledProcessError:
        run(['systemctl', 'enable', '--now', 'docker'])
        run(['docker', 'info'], capture=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--ip')
    parser.add_argument('--https-port', type=int, default=8443)
    parser.add_argument('--local-only', action='store_true')
    parser.add_argument('--with-xray', action='store_true')
    parser.add_argument('--prepare-existing', action='store_true')
    parser.add_argument('--sni', default='www.wikipedia.org')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Запустите на Ubuntu-хосте от root')
    if not 1024 <= args.https_port <= 65535 or args.https_port in (8000, 10085):
        raise SystemExit('Нужен отдельный HTTPS-порт 1024–65535, кроме 8000/10085')
    if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', args.sni) or '.' not in args.sni or '..' in args.sni:
        raise SystemExit('Некорректный REALITY SNI')
    import fcntl
    with open('/run/reality-control-installer.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Другой установщик уже запущен') from None
        existing_files = check_existing(INSTALL)
        if args.local_only and (INSTALL / '.env').exists() and re.search(
                r'^PUBLIC_ORIGIN=https://', (INSTALL / '.env').read_text(), re.M):
            raise SystemExit('В этой установке уже есть HTTPS. --local-only не отключает существующий публичный доступ автоматически.')
        ip = validate_ipv4(args.ip) if args.ip else detect_public_ip()
        print('Публичный IPv4 этого VPS:', ip, flush=True)
        ensure_docker()
        saved = backup_existing(INSTALL, existing_files)
        if saved:
            print('Резервная копия предыдущей установки:', saved, flush=True)
        deploy_source(args.source, INSTALL)
        configure_env(INSTALL, ip)
        data = INSTALL / 'data'
        if data.is_symlink():
            raise ValueError('data не должен быть symlink')
        data.mkdir(mode=0o700, exist_ok=True)
        os.chown(data, 10001, 10001)
        data.chmod(0o700)
        run(['bash', 'scripts/install_agent.sh'], cwd=INSTALL)
        compose = ['docker', 'compose']
        run([*compose, 'config', '--quiet'], cwd=INSTALL)
        run([*compose, 'build'], cwd=INSTALL)
        run([*compose, 'stop', 'worker', 'web'], cwd=INSTALL)
        run([*compose, 'run', '--rm', '--no-deps', 'migrate'], cwd=INSTALL)
        run([*compose, 'up', '-d', '--no-deps', '--wait', 'web', 'worker'], cwd=INSTALL)
        admin = json.loads(run([*compose, 'exec', '-T', 'web', 'python', '-m', 'app.cli', 'bootstrap-admin'],
                               cwd=INSTALL, capture=True))
        if admin['created']:
            if CREDENTIALS.exists():
                credential_file = CREDENTIALS.with_name(f'reality-control-admin-{time.time_ns()}.json')
            else:
                credential_file = CREDENTIALS
            credential_file.write_text(json.dumps(admin, ensure_ascii=False, indent=2) + '\n')
            credential_file.chmod(0o600)
            print('Новый администратор:', admin['username'], flush=True)
            print('Пароль:', admin['password'], flush=True)
            print('Защищённый файл доступа:', credential_file, flush=True)
        else:
            print('Существующий администратор и его пароль сохранены.', flush=True)
        xray_config = Path('/usr/local/etc/xray/config.json')
        if args.with_xray and not xray_config.exists() and not shutil.which('xray'):
            run(['bash', '/opt/reality-agent/install_xray_reality.sh', '--yes', '--ip', ip, '--target', args.sni])
        elif args.with_xray and shutil.which('xray'):
            host = json.loads(run(['python3', '/opt/reality-agent/agent.py', 'status'], capture=True))
            if host['can_initialize']:
                print('Завершаем прежнюю установку: конфиг пустой, существующих учётных данных нет.', flush=True)
                run(['python3', '/opt/reality-agent/agent.py', 'initialize', '--ip', ip, '--sni', args.sni])
        state = json.loads(run([*compose, 'exec', '-T', 'web', 'python', '-m', 'app.cli', 'bootstrap-state'],
                              cwd=INSTALL, capture=True))
        if xray_config.exists() and not state['imported']:
            command = ['python3', 'scripts/bootstrap_onboarding.py', '--ip', ip]
            if args.prepare_existing:
                command += ['--prepare']
            try:
                metadata = run(command, cwd=INSTALL, capture=True)
            except subprocess.CalledProcessError as error:
                if error.returncode not in (3, 4):
                    raise
                print('Подключите существующий Xray через раздел Настройки → Установка и подключение.', flush=True)
            else:
                run([*compose, 'exec', '-T', 'web', 'python', '-m', 'app.cli', 'import'],
                    cwd=INSTALL, input_text=metadata)
        if args.local_only:
            print(f'Панель: ssh -N -L 8000:127.0.0.1:8000 root@{ip} → http://localhost:8000', flush=True)
        else:
            print('Получаем HTTPS-сертификат для IP. Порты 80 и HTTPS должны быть доступны у провайдера.', flush=True)
            run(['bash', 'scripts/enable_https.sh', ip, str(args.https_port)], cwd=INSTALL)
            print(f'Панель: https://{ip}:{args.https_port}', flush=True)
        print('Готово. Генерация VLESS/JSON: fingerprint=firefox. IPv4 уже подставлен в мастер Xray.', flush=True)


if __name__ == '__main__':
    main()
