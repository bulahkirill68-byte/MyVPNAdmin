#!/usr/bin/env python3
"""Reproducibly embed the complete allowlisted source tree into one self-extracting .sh."""
import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
MARKER = b'\n__REALITY_CONTROL_PAYLOAD__\n'
TOP = ('.dockerignore', '.env.example', '.gitattributes', '.gitignore', '.prettierrc.json', 'ruff.toml',
       'README.md', 'compose.yaml', 'compose.dev.yaml', 'backend/Dockerfile', 'backend/pyproject.toml',
       'backend/alembic.ini', 'frontend/package.json', 'frontend/package-lock.json', 'frontend/tsconfig.json',
       'frontend/vite.config.ts', 'frontend/playwright.config.ts', 'frontend/index.html')
TREES = ('backend/app', 'backend/alembic', 'backend/tests', 'frontend/src', 'frontend/tests',
         'host', 'public', 'scripts', 'docs', '.github/workflows')
EXCLUDED = {'__pycache__', '.pytest_cache', '.ruff_cache', 'node_modules', '.git', 'dist', 'data'}


def source_files(root):
    paths = {root / name for name in TOP}
    for folder in TREES:
        paths.update((root / folder).rglob('*'))
    result = []
    for path in sorted(paths, key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        if any(part in EXCLUDED for part in relative.parts):
            continue
        if path.name == '.env' or path.suffix in ('.pyc', '.pyo', '.log', '.db', '.sqlite3'):
            continue
        if path.is_symlink():
            raise ValueError('Symlink in source tree: ' + str(relative))
        if path.is_file():
            result.append((relative.as_posix(), path.read_bytes()))
    for required in TOP:
        if required not in {name for name, _ in result}:
            raise ValueError('Missing source file: ' + required)
    return result


def build_payload(root=ROOT):
    files = source_files(root)
    entries = [{'path': name, 'sha256': hashlib.sha256(data).hexdigest(),
                'mode': 0o755 if name.endswith('.sh') or data.startswith(b'#!') else 0o644}
               for name, data in files]
    tree_hash = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    manifest = {'format': 1, 'project': 'reality-control', 'tree_sha256': tree_hash, 'files': entries}
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode='w', format=tarfile.USTAR_FORMAT) as bundle:
        for name, data in [*files, ('BUNDLE-MANIFEST.json', json.dumps(manifest, indent=2).encode() + b'\n')]:
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = next((e['mode'] for e in entries if e['path'] == name), 0o644)
            entry.mtime = 0
            bundle.addfile(entry, io.BytesIO(data))
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode='wb', filename='', compresslevel=9, mtime=0) as output:
        output.write(content.getvalue())
    return compressed.getvalue(), manifest


def render_header(payload, root=ROOT):
    header = (root / 'scripts/installer_header.sh').read_text(encoding='utf-8')
    extractor = (root / 'scripts/bundle_extract.py').read_text(encoding='utf-8')
    header = header.replace('@@PAYLOAD_SHA256@@', hashlib.sha256(payload).hexdigest())
    header = header.replace('@@EXTRACTOR@@', extractor.rstrip())
    return header.encode()


def build(root=ROOT):
    payload, manifest = build_payload(root)
    encoded = b''.join(b'#' + line + b'\n' for line in base64.encodebytes(payload).splitlines())
    result = render_header(payload, root) + encoded
    return result, manifest


def verify_current(contents, root=ROOT):
    """Compare shell code and every source byte; compression may differ between zlib versions."""
    prefix, encoded = contents.split(MARKER, 1)
    lines = encoded.splitlines()
    if not lines or any(not line.startswith(b'#') for line in lines):
        raise ValueError('Invalid payload encoding')
    payload = base64.b64decode(b''.join(line[1:] for line in lines), validate=True)
    if prefix + MARKER != render_header(payload, root):
        raise ValueError('Installer shell code or payload digest differs')
    expected_files = dict(source_files(root))
    _, expected_manifest = build_payload(root)
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as bundle:
        members = bundle.getmembers()
        expected_names = set(expected_files) | {'BUNDLE-MANIFEST.json'}
        if len(members) != len(expected_names) or {m.name for m in members} != expected_names:
            raise ValueError('Installer source inventory differs')
        for member in members:
            if not member.isfile():
                raise ValueError('Non-file source member')
            data = bundle.extractfile(member).read()
            if member.name == 'BUNDLE-MANIFEST.json':
                if json.loads(data) != expected_manifest:
                    raise ValueError('Installer manifest differs')
            elif data != expected_files[member.name]:
                raise ValueError('Installer source differs: ' + member.name)
    return expected_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'install-reality-control.sh')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        try:
            contents = args.output.read_bytes()
            manifest = verify_current(contents)
        except (OSError, ValueError, KeyError, tarfile.TarError):
            raise SystemExit('Installer is stale or damaged. Run: python scripts/build_installer.py') from None
    else:
        contents, manifest = build()
        args.output.write_bytes(contents)
        args.output.chmod(0o755)
    print(f'{args.output.name}: {len(contents)} bytes, {len(manifest["files"])} source files, tree={manifest["tree_sha256"]}')


if __name__ == '__main__':
    main()
