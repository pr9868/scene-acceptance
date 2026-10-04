"""Preserve new-run inputs and implementation before any producer call."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import scene_acceptance
from scene_acceptance.engine import implementation_digest
from scene_acceptance.model import sha
from study import save

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--cli');p.add_argument('--secondary',action='store_true');a=p.parse_args();root=a.root.resolve();src=Path(__file__).resolve().parent
    if a.secondary:
        target=root/'frozen-secondary';target.mkdir(exist_ok=False)
        for name in ('SECONDARY_SAMPLING.md','secondary_sampling.py','study.py'):shutil.copyfile(src/name,target/name)
        primary=root/'assessments/results.json';seen=[r['id'] for r in json.loads(primary.read_text())['rows']] if primary.exists() else []
        save(root/'secondary-freeze.json',dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),primary_results_seen=seen,
            note='Separately recorded follow-up. Never overwrite the original primary comparison.',
            files={p.name:sha(p) for p in target.iterdir()},control_summary_sha256=sha(root/'secondary-controls/summary.json')))
        return
    if not a.cli:p.error('--cli is required for the primary freeze')
    assert not (root/'production').exists(),'Freeze before generation'
    control=json.loads((root/'controls/summary.json').read_text())
    assert len(control['cases'])==33 and all(x['matched'] for x in control['cases'])
    assert control['checker_sha256']==implementation_digest()
    target=root/'frozen-study';target.mkdir(exist_ok=False)
    for source in src.iterdir():
        if source.is_file():shutil.copyfile(source,target/source.name)
    runtime=Path(scene_acceptance.__file__).parent
    shutil.copytree(runtime,root/'frozen-runtime/scene_acceptance',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    save(root/'freeze.json',dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=src,text=True).strip(),
        checker_sha256=implementation_digest(),runtime_path=str(runtime),
        cli_version=subprocess.check_output([a.cli,'--version'],text=True).strip(),model_requested='gpt-6-astra',model_snapshot=None,
        controls_cases=33,controls_all_expected=True,controls_receipt_sha256=sha(root/'controls/summary.json'),
        files={str(p.relative_to(root)):sha(p) for sub in ('inputs','frozen-study','frozen-runtime') for p in sorted((root/sub).rglob('*')) if p.is_file()}))

if __name__=='__main__':main()
