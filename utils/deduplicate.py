import hashlib
from pathlib import Path


def file_hash(path: Path):
    with path.open('rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def remove_duplicates(directory: str | Path):
    file_hashes = {}
    for path in Path(directory).rglob('*'):
        if path.is_file() and path.suffix in ('.png', '.jpg', '.jpeg', '.bmp', '.gif'):
            filehash = file_hash(path)
            if filehash not in file_hashes:
                file_hashes[filehash] = path
            else:
                print(f"Removing duplicate file: {path}")
                path.unlink()
