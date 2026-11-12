import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tarfile

import pytest
from sqlalchemy import select

from app.auth import hasher
from app.cli import bootstrap_admin
from app.db import Admin, Session
from test_api import client

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tools(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    import bootstrap_install
    import build_installer
    import bundle_extract
    import public_ip
    return bootstrap_install, build_installer, bundle_extract, public_ip


def test_public_ip_detection_quorum_nat_and_validation(tools):
    *_, ip = tools
    assert ip.detect_public_ip(fetch=lambda _: '1.1.1.1\n', interfaces=lambda: {'10.1.2.3'}) == '1.1.1.1'
    assert ip.detect_public_ip(fetch=lambda _: 'not an IP', interfaces=lambda: {'8.8.8.8'}) == '8.8.8.8'
    answers = iter(['8.8.8.8', '1.1.1.1', '9.9.9.9'])
    with pytest.raises(ValueError, match='--ip'):
        ip.detect_public_ip(fetch=lambda _: next(answers), interfaces=lambda: set())
    for value in ('127.0.0.1', '10.0.0.2', '192.0.2.5', '::1', 'garbage'):
        with pytest.raises(ValueError):
            ip.validate_ipv4(value)


def test_bundle_is_deterministic_complete_and_excludes_runtime_secrets(tools, tmp_path):
    _, builder, extractor, _ = tools
    script, value = builder.build()
    assert script == builder.build()[0]
    payload = base64.decodebytes(script.split(b'\n__REALITY_CONTROL_PAYLOAD__\n', 1)[1])
    archive = tmp_path / 'payload.tar.gz'
    archive.write_bytes(payload)
    target = tmp_path / 'source'
    unpacked = extractor.extract(archive, target)
    assert unpacked == value
    names = {x['path'] for x in value['files']}
    assert {'compose.yaml', 'backend/Dockerfile', 'frontend/package-lock.json', 'host/agent.py',
            'public/https_control.py', 'scripts/bootstrap_install.py', 'scripts/public_ip.py'} <= names
    assert not any(p.startswith(('data/', '.git/', '.venv/', 'frontend/node_modules/', 'frontend/dist/')) for p in names)
    assert '.env' not in names and 'install-reality-control.sh' not in names
    assert b'fp="firefox"' in (target / 'backend/app/domain.py').read_bytes()
    assert b'"fingerprint": "firefox"' in (target / 'backend/app/routing.py').read_bytes()
    assert not (target / 'data').exists()
    assert not (target / '.env').exists()


@pytest.mark.parametrize('attack', ['traversal', 'symlink', 'tampered'])
def test_bundle_rejects_path_escape_links_and_tampering_before_writing(tools, tmp_path, attack):
    _, builder, extractor, _ = tools
    original, _ = builder.build_payload()
    output = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(original), mode='r:gz') as source, tarfile.open(fileobj=output, mode='w:gz') as target:
        for member in source.getmembers():
            data = source.extractfile(member).read()
            if attack == 'tampered' and member.name == 'README.md':
                data += b'changed'
                member.size = len(data)
            target.addfile(member, io.BytesIO(data))
        if attack in ('traversal', 'symlink'):
            member = tarfile.TarInfo('../escape' if attack == 'traversal' else 'link')
            if attack == 'symlink':
                member.type = tarfile.SYMTYPE
                member.linkname = '/etc/passwd'
            target.addfile(member)
    archive = tmp_path / 'bad.tar.gz'
    archive.write_bytes(output.getvalue())
    destination = tmp_path / 'unpack'
    with pytest.raises(ValueError):
        extractor.extract(archive, destination)
    assert not destination.exists()
    assert not (tmp_path / 'escape').exists()


def test_repeat_install_preserves_data_env_custom_files_and_checks_edits(tools, tmp_path):
    bootstrap, builder, extractor, _ = tools
    payload, _ = builder.build_payload()
    archive = tmp_path / 'bundle.tgz'
    archive.write_bytes(payload)
    source, destination = tmp_path / 'source', tmp_path / 'installed'
    extractor.extract(archive, source)
    bootstrap.deploy_source(source, destination)
    bootstrap.configure_env(destination, '1.1.1.1')
    with (destination / '.env').open('a') as stream:
        stream.write('CUSTOM_VALUE=keep-this-value\n')
    (destination / 'custom-note.txt').write_text('user work')
    (destination / 'data').mkdir()
    database = destination / 'data/panel.db'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE state (value TEXT)')
        db.execute("INSERT INTO state VALUES ('preserved')")
    names = bootstrap.check_existing(destination)
    backup = bootstrap.backup_existing(destination, names, tmp_path / 'backups')
    bootstrap.deploy_source(source, destination)
    bootstrap.configure_env(destination, '8.8.8.8')
    assert 'PANEL_PUBLIC_IP=8.8.8.8' in (destination / '.env').read_text()
    assert 'CUSTOM_VALUE=keep-this-value' in (destination / '.env').read_text()
    assert (destination / 'custom-note.txt').read_text() == 'user work'
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT value FROM state').fetchone()[0] == 'preserved'
    saved_database = next((tmp_path / 'backups').glob('panel-*.sqlite3'))
    with sqlite3.connect(saved_database) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert backup.is_file()
    edited = destination / 'backend/app/domain.py'
    edited.write_text(edited.read_text() + '\n# user modification\n')
    with pytest.raises(ValueError, match='вручную'):
        bootstrap.check_existing(destination)


def test_bootstrap_admin_is_unique_and_does_not_reset_existing_password():
    first = bootstrap_admin()
    assert first['created'] and len(first['password']) >= 24
    with Session() as db:
        admin = db.scalar(select(Admin))
        digest = admin.password
        assert hasher.verify(digest, first['password'])
    second = bootstrap_admin()
    assert second == {'created': False, 'username': 'admin'}
    with Session() as db:
        assert db.scalar(select(Admin)).password == digest
        assert len(list(db.scalars(select(Admin)))) == 1


def test_setup_prefills_deployment_ip_without_importing_server(monkeypatch):
    import app.host_agent
    monkeypatch.setenv('PANEL_PUBLIC_IP', '1.1.1.1')
    monkeypatch.setattr(app.host_agent, 'request', lambda *args: {'installed': False, 'job': {'state': 'idle'}})
    result = client().get('/api/setup').json()
    assert result['public_ip'] == '1.1.1.1' and not result['imported']


def test_manifest_hashes_all_embedded_source_files(tools):
    _, builder, _, _ = tools
    files = dict(builder.source_files(ROOT))
    _, manifest = builder.build_payload()
    for entry in manifest['files']:
        assert hashlib.sha256(files[entry['path']]).hexdigest() == entry['sha256']
    assert json.dumps(manifest).count('tree_sha256') == 1


def test_bundle_source_check_accepts_other_gzip_encoders_but_not_stale_code(tools):
    _, builder, _, _ = tools
    original, value = builder.build_payload()
    repacked = gzip.compress(gzip.decompress(original), compresslevel=1, mtime=0)
    encoded = b''.join(b'#' + line + b'\n' for line in base64.encodebytes(repacked).splitlines())
    script = builder.render_header(repacked) + encoded
    assert builder.verify_current(script) == value
    with pytest.raises(ValueError):
        builder.verify_current(script.replace(b'set -Eeuo pipefail', b'set +e', 1))
