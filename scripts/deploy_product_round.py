"""Deploy only the reviewed personal pages, product page and paiche static build.

Run on the server with a prepared tar.gz and manifest. No service restart or
database mutation; previous directories and replaced personal files are retained.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    archive, stamp = sys.argv[1:]
    if not stamp.isdigit():
        raise ValueError("Invalid release stamp")
    stage = Path('/tmp') / ('plate-round-' + stamp)
    stage.mkdir(exist_ok=False)
    with tarfile.open(archive) as tar:
        for item in tar.getmembers():
            if item.name.startswith('/') or '..' in Path(item.name).parts or not item.isfile():
                raise ValueError('Unsafe archive member: ' + item.name)
        tar.extractall(stage)
    manifest = json.loads((stage / 'manifest.json').read_text())
    for name, sha in manifest['files'].items():
        if digest(stage / name) != sha:
            raise ValueError('Package mismatch: ' + name)
    targets = {
        'personal': Path('/var/www/me-site'),
        'product': Path('/var/www/fangdian-products/remove-number-plate'),
        'web': Path('/var/www/paiche-web/dist'),
    }
    for target in targets.values():
        if target.is_symlink() or not target.is_dir():
            raise ValueError('Unexpected production target: ' + str(target))
    backup = Path('/opt/sitewide-visual-backups') / ('plate-round-' + stamp)
    backup.mkdir(parents=True, exist_ok=False)
    personal = [n.split('/', 1)[1] for n in manifest['files'] if n.startswith('personal/')]
    for name in personal:
        source = targets['personal'] / name
        if source.is_symlink():
            raise ValueError('Unexpected symlink: ' + name)
        if source.exists():
            dest = backup / 'personal' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            if digest(source) != digest(dest):
                raise ValueError('Backup mismatch: ' + name)
    switched = []
    written = []
    try:
        # Retain old hashed resources for already-open pages; overwrite from build.
        for group in ['product', 'web']:
            target = targets[group]
            candidate = target.with_name(target.name + '.plate-candidate-' + stamp)
            previous = target.with_name(target.name + '.plate-before-' + stamp)
            if candidate.exists() or previous.exists():
                raise ValueError('Release directory exists')
            shutil.copytree(target, candidate)
            shutil.copytree(stage / group, candidate, dirs_exist_ok=True)
            for name, sha in manifest['files'].items():
                if name.startswith(group + '/') and digest(candidate / name.split('/', 1)[1]) != sha:
                    raise ValueError('Candidate mismatch: ' + name)
            os.rename(target, previous)
            try:
                os.rename(candidate, target)
            except Exception:
                os.rename(previous, target)
                raise
            switched.append((target, previous))
        # Shared dependencies first, then HTML; only explicitly listed paths.
        for name in sorted(personal, key=lambda n: (n.endswith('.html'), n)):
            target = targets['personal'] / name
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + '.plate-new-' + stamp)
            shutil.copy2(stage / 'personal' / name, temporary)
            os.replace(temporary, target)
            written.append(name)
        for name, sha in manifest['files'].items():
            group, relative = name.split('/', 1)
            if digest(targets[group] / relative) != sha:
                raise ValueError('Production mismatch: ' + name)
    except Exception:
        for name in written:
            saved = backup / 'personal' / name
            if saved.exists():
                shutil.copy2(saved, targets['personal'] / name)
        for target, previous in reversed(switched):
            os.rename(target, target.with_name(target.name + '.plate-failed-' + stamp))
            os.rename(previous, target)
        raise
    record = dict(manifest, stamp=stamp, personal_backup=str(backup),
                  directory_backups=[str(p) for _, p in switched])
    (backup / 'release.json').write_text(json.dumps(record, indent=2))
    print(json.dumps({'status': 'deployed', 'files': len(manifest['files']),
                      'backup': str(backup), 'directory_backups': record['directory_backups']}))


if __name__ == '__main__':
    main()
