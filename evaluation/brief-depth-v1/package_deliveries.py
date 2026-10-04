"""Portable copies of complete scene bundles, with byte-for-byte verification."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from scene_acceptance.model import sha
from study import save

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root
    runs=json.loads((root/'production/runs.json').read_text());assert len(runs)==24
    destination=root/'scene-deliveries.zip';files={};bundles=0
    with ZipFile(destination,'x',compression=ZIP_DEFLATED) as archive:
        archive.writestr('README.txt','Private synthetic scene study. Each trial folder contains unchanged model USDA, its texture, and the frozen assessment briefs copied after generation. Only the exact prompt and optional image in _provenance/request.json were supplied during creation; simpler producers did not receive the detailed brief. All original logs and reports remain in the full experiment packet. These are illustrations, not engineering-certified machines. No source has been repaired.\n')
        for run in runs:
            if run['status']!='DELIVERED':continue
            folder=root/'production'/run['id'];bundles+=1
            for path,h in json.loads((folder/'delivery-manifest.json').read_text())['files'].items():
                source=folder/'delivery'/path;assert sha(source)==h
                name=run['id']+'/'+path;archive.write(source,name);files[name]=h
            for name in ('metrics.json','request.json','prompt.txt','producer-notes.txt','delivery-manifest.json'):
                source=folder/name;target=run['id']+'/_provenance/'+name;archive.write(source,target);files[target]=sha(source)
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert all(hashlib.sha256(archive.read(name)).hexdigest()==h for name,h in files.items())
    receipt=dict(bundles=bundles,files=len(files)+1,archive_sha256=sha(destination),source_files=files)
    save(root/'scene-archive-verification.json',receipt);print(json.dumps({k:v for k,v in receipt.items() if k!='source_files'}))

if __name__=='__main__':main()
