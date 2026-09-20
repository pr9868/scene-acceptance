"""Record reviewed distribution files; this does not validate their correctness."""

from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
manifest_path = ROOT / 'MANIFEST.json'
manifest = json.loads(manifest_path.read_text())
names = subprocess.check_output(
    ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT
).decode().split('\0')
files = {}
for name in sorted(set(names)):
    if not name or name == 'MANIFEST.json':
        continue
    path = ROOT / name
    if path.is_symlink():
        raise ValueError(f'Distribution symlink requires review: {name}')
    if path.is_file():
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
manifest['files'] = files
source = ROOT / 'src/scene_acceptance'
implementation = {
    str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(source.rglob('*'))
    if path.is_file() and path.suffix in ('.py', '.json')
}
manifest['checker_sha256'] = hashlib.sha256(
    json.dumps(implementation, sort_keys=True, separators=(',', ':')).encode()
).hexdigest()
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
print(f'Recorded {len(files)} files. Review the diff and run reproduce.py.')
