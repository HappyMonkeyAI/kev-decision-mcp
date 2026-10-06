"""Download and verify the pinned Gutsy v0.4 runtime/model; stdlib only."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]/'.cache/gutsy'
LOCK_PATH = Path(__file__).with_name('gutsy-lock.json')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    lock = json.loads(LOCK_PATH.read_text(encoding='utf-8'))
    revision = lock['revision']
    expected = lock['sha256']
    try:
        with urllib.request.urlopen(f'https://huggingface.co/api/models/kouhxp/gutsy/revision/{revision}', timeout=60) as response:
            metadata = json.load(response)
    except urllib.error.URLError as exc:
        raise RuntimeError(f'Could not retrieve pinned Gutsy revision metadata: {exc}') from exc
    if metadata.get('sha') != revision:
        raise RuntimeError(f"Hugging Face returned revision {metadata.get('sha')!r}, expected {revision}")
    files = [s['rfilename'] for s in metadata['siblings']
             if re.fullmatch(r'gutsy-inference/(gutsy_inference/[^/]+\.py|pyproject\.toml|README\.md)', s['rfilename'])]
    files += ['gutsy-0.8b-v04-q8_0.gguf', 'gutsy-0.8b-v04.calibration.json']
    paths = {
        name: ('runtime/' + name.removeprefix('gutsy-inference/')
               if name.startswith('gutsy-inference/') else 'models/' + name)
        for name in files
    }
    if set(paths.values()) != set(expected):
        raise RuntimeError('Pinned file list does not match the locked SHA-256 manifest')
    for name, relative in paths.items():
        target=ROOT/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            print(f'Downloading {name}',flush=True)
            partial=target.with_name(target.name+'.partial')
            try:
                try:
                    with urllib.request.urlopen(f'https://huggingface.co/kouhxp/gutsy/resolve/{revision}/{name}', timeout=120) as response, partial.open('wb') as output:
                        shutil.copyfileobj(response, output)
                except urllib.error.URLError as exc:
                    raise RuntimeError(f'Could not download pinned Gutsy file {name}: {exc}') from exc
                actual = digest(partial)
                if actual != expected[relative]:
                    raise RuntimeError(f'SHA-256 mismatch for {name}: expected {expected[relative]}, got {actual}')
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        actual = digest(target)
        if actual != expected[relative]:
            raise RuntimeError(f'SHA-256 mismatch for cached {name}: expected {expected[relative]}, got {actual}')
    provenance = {'repository': lock['repository'], 'revision': revision, 'sha256': expected}
    (ROOT/'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    print('Pinned runtime and Q8_0 model verified; provenance saved.')


if __name__=='__main__':
    main()
