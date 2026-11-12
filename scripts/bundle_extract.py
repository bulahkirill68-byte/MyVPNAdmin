"""Standalone safe extractor embedded into the single-file shell installer."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile

MANIFEST = 'BUNDLE-MANIFEST.json'


def safe_name(value):
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or '..' in path.parts or '\\' in value
            or ':' in value or str(path) != value):
        raise ValueError('Недопустимый путь в пакете')
    return path


def extract(archive, destination):
    destination = Path(destination)
    if destination.is_symlink() or (destination.exists() and any(destination.iterdir())):
        raise ValueError('Каталог распаковки должен быть пустым и не являться symlink')
    with tarfile.open(archive, 'r:gz') as bundle:
        members = bundle.getmembers()
        if len(members) > 5000 or sum(m.size for m in members) > 256 * 1024 * 1024:
            raise ValueError('Превышен допустимый размер пакета')
        names = [m.name for m in members]
        if len(names) != len(set(names)):
            raise ValueError('Дублирующиеся пути в пакете')
        for member in members:
            safe_name(member.name)
            if not member.isfile():
                raise ValueError('В пакете разрешены только обычные файлы')
        manifest_member = bundle.getmember(MANIFEST)
        if manifest_member.size > 2 * 1024 * 1024:
            raise ValueError('Некорректный manifest')
        manifest_bytes = bundle.extractfile(manifest_member).read()
        manifest = json.loads(manifest_bytes)
        entries = manifest['files']
        expected = {item['path']: item for item in entries}
        if manifest.get('format') != 1 or len(expected) != len(entries) or set(names) != set(expected) | {MANIFEST}:
            raise ValueError('Состав архива не совпадает с manifest')
        verified = {}
        for name, entry in expected.items():
            safe_name(name)
            if entry['mode'] not in (0o644, 0o755):
                raise ValueError('Недопустимые права файла')
            data = bundle.extractfile(name).read()
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('Хеш файла не совпадает: ' + name)
            verified[name] = data
        fingerprint = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if fingerprint != manifest['tree_sha256']:
            raise ValueError('Хеш дерева файлов не совпадает')
        destination.mkdir(parents=True, exist_ok=True)
        for name, data in {**verified, MANIFEST: manifest_bytes}.items():
            target = destination.joinpath(*safe_name(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            os.chmod(target, expected[name]['mode'] if name in expected else 0o644)
    return manifest


if __name__ == '__main__':
    extract(sys.argv[1], sys.argv[2])
