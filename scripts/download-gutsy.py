"""Download the pinned Gutsy v0.4 runtime/model on Linux or Windows; stdlib only."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import urllib.request

REVISION = 'bb1dde4c571b2588801c27d155da005a87d05285'
ROOT = Path(__file__).resolve().parents[1]/'.cache/gutsy'


def main():
    with urllib.request.urlopen(f'https://huggingface.co/api/models/kouhxp/gutsy/revision/{REVISION}',timeout=60) as response:
        metadata=json.load(response)
    assert metadata['sha']==REVISION
    files=[s['rfilename'] for s in metadata['siblings'] if re.fullmatch(r'gutsy-inference/(gutsy_inference/[^/]+\.py|pyproject\.toml|README\.md)',s['rfilename'])]
    files+=['gutsy-0.8b-v04-q8_0.gguf','gutsy-0.8b-v04.calibration.json']
    for name in files:
        relative='runtime/'+name.removeprefix('gutsy-inference/') if name.startswith('gutsy-inference/') else 'models/'+name
        target=ROOT/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            print(f'Downloading {name}',flush=True)
            partial=target.with_name(target.name+'.partial')
            with urllib.request.urlopen(f'https://huggingface.co/kouhxp/gutsy/resolve/{REVISION}/{name}',timeout=120) as response, partial.open('wb') as output:
                shutil.copyfileobj(response,output)
            partial.replace(target)
    hashes={}
    for path in ROOT.rglob('*'):
        if path.is_file() and path.name!='provenance.json' and not path.name.endswith('.partial'):
            with path.open('rb') as data:
                hashes[path.relative_to(ROOT).as_posix()]=hashlib.file_digest(data,'sha256').hexdigest()
    (ROOT/'provenance.json').write_text(json.dumps({'repository':'kouhxp/gutsy','revision':REVISION,'sha256':hashes},indent=2),encoding='utf-8')
    print('Pinned runtime and Q8_0 model ready; provenance saved.')


if __name__=='__main__':
    main()
