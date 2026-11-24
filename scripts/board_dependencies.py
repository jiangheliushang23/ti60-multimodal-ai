"""Check or restore the original v24 board dependencies from an authorized project copy."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path
import shutil


def sha256(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def project_path(root, item):
    path = (root / item['path']).resolve()
    if not path.is_relative_to(root):
        raise SystemExit(f"Path outside project: {item['path']}")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-project', type=Path, help='Root of the authorized v24 project copy')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'docs/build-dependencies.json').read_text(encoding='utf-8'))
    source_root = args.from_project.resolve() if args.from_project else None
    pending = []
    errors = []
    for item in manifest['files']:
        target = project_path(root, item)
        if target.is_file():
            if sha256(target) != item['sha256']:
                errors.append(f"Incorrect local SHA-256: {item['path']}")
            continue
        source = project_path(source_root, item) if source_root else None
        if not source or not source.is_file():
            errors.append(f"Missing: {item['path']}")
        elif sha256(source) != item['sha256']:
            errors.append(f"Incorrect source SHA-256: {item['path']}")
        else:
            pending.append((source, target))
    if errors:
        raise SystemExit('\n'.join(errors) + f'\n{len(errors)} dependency checks failed.')
    for source, target in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as src, target.open('xb') as dest:
            shutil.copyfileobj(src, dest)
    print(f"{manifest['version']}: {len(manifest['files'])} dependencies verified, {len(pending)} restored.")


if __name__ == '__main__':
    main()
