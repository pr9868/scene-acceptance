"""Independent receipt/integrity checks over the finished private packet."""
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlparse
from PIL import Image
from scene_acceptance.engine import implementation_digest
from scene_acceptance.model import sha
from study import PALETTE, save

class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        for k,v in attrs:
            if k in ('href','src') and v:self.links.append(v)

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();r=a.root.resolve()
    frozen=json.loads((r/'freeze.json').read_text())
    assert implementation_digest()==frozen['checker_sha256']
    assert all(sha(r/name)==h for name,h in frozen['files'].items()),'Frozen input/runtime changed'
    assert sha(r/'controls/summary.json')==frozen['controls_receipt_sha256']
    control=json.loads((r/'controls/summary.json').read_text());assert len(control['cases'])==33 and all(c['matched'] for c in control['cases'])
    for case in control['cases']:
        source=r/'inputs'/case['task']/'briefs'
        for brief in source.iterdir():assert sha(brief)==sha(r/'controls/scenes'/f"{case['task']}-{case['control']}"/'briefs'/brief.name)
    schedule=json.loads((r/'inputs/schedule.json').read_text());runs=json.loads((r/'production/runs.json').read_text())
    assert len(runs)==24 and [x['id'] for x in runs]==[x['id'] for x in schedule]
    results=json.loads((r/'assessments/results.json').read_text());assert len(results['rows'])==24
    assert results['checker_sha256']==implementation_digest()
    thread_ids=[];delivered=0;parity=0;input_files=0
    for c in runs:
        case=r/'production'/c['id'];inputs=r/'inputs'/c['task']/'briefs'
        assert c==json.loads((case/'metrics.json').read_text())
        req=json.loads((case/'request.json').read_text());assert sha(case/'prompt.txt')==sha(inputs/f'{c["level"]}.md')==req['prompt_sha256']
        assert req['model_requested']=='gpt-6-astra' and req['effort']=='high'
        assert len(req['images'])==(1 if c['level']=='detailed' else 0)
        assert not c['unexpected_item_types']
        thread_ids+=c['thread_ids'];row=next(x for x in results['rows'] if x['id']==c['id'])
        if c['status']!='DELIVERED':assert row.get('unassessed');continue
        assert not c['native_event_parse_errors']
        delivered+=1;assert row['source_unchanged']
        native=json.loads((case/'response.json').read_text());bundle=case/'delivery'
        assert (bundle/'scene.usda').read_text()==native['scene_usda'],'USDA was changed'
        im=Image.open(bundle/'textures/label.png').convert('RGB');assert im.size==(64,64)
        assert list(im.getdata())==[PALETTE[native['texture_rows'][y//8][x//8]] for y in range(64) for x in range(64)],'Raster changed'
        for f,h in json.loads((case/'delivery-manifest.json').read_text())['files'].items():
            assert sha(bundle/f)==h;input_files+=1
        for f in inputs.iterdir():assert sha(f)==sha(bundle/'briefs'/f.name)
        default_report=json.loads((r/'assessments'/c['id']/'default/result.json').read_text())
        if row.get('inventory'):
            assert set(default_report['identity']['input_files'])=={'scene.usda','textures/label.png'},'Assessment-only briefs became scene dependencies'
            image_check=next(x for x in row['briefs']['full']['spec_checks'] if x['id']=='spec.image')
            assert image_check['evidence']['observations']['actual_image_sha256']==sha(bundle/'textures/label.png')
        supplied={v['id']:v['status'] for v in row['briefs']['provided']['spec_checks']}
        full={v['id']:v['status'] for v in row['briefs']['full']['spec_checks']}
        # Admission failures may prevent individual target measurements; don't manufacture scores.
        assert all(full.get(k)==v for k,v in supplied.items()),'Same mapped requirement disagrees between assessment modes'
        parity+=len(supplied)
        if c['level']=='detailed':assert supplied==full
        default_statuses={x['id']:x['status'] for x in row['default_evidence']}
        for mode in ('provided','full'):
            core=json.loads((r/'assessments'/c['id']/mode/'report/core-result.json').read_text())
            statuses={x['id']:x['status'] for x in core['checks']}
            # The core admission ID may differ between modes; compare each selected baseline rule.
            assert all(statuses.get(k)==v for k,v in default_statuses.items() if not k.startswith('core.'))
    assert len(thread_ids)==len(set(thread_ids)),'Contexts were reused'
    secondary=json.loads((r/'secondary-freeze.json').read_text())
    assert all(sha(r/'frozen-secondary'/name)==h for name,h in secondary['files'].items())
    assert sha(r/'secondary-controls/summary.json')==secondary['control_summary_sha256']
    secondary_rows=json.loads((r/'secondary/results.json').read_text())
    assert secondary_rows['checker_sha256']==implementation_digest()
    assert len(secondary_rows['rows'])==24
    report_manifests=0;report_files=0;local_links=0;view_images=0
    for evidence in r.rglob('view-evidence.json'):
        for view in json.loads(evidence.read_text())['views']:
            assert sha(evidence.parent/view['image'])==view['sha256'];view_images+=1
    for pth in r.rglob('manifest.json'):
        data=json.loads(pth.read_text())
        if 'files' not in data:continue
        for f,h in data['files'].items():
            target=(pth.parent/f).resolve();assert target.is_relative_to(r)
            assert sha(target)==h,(str(pth),f);report_files+=1
        report_manifests+=1
    broken=[]
    for html in r.rglob('*.html'):
        parser=Links();parser.feed(html.read_text())
        for value in parser.links:
            u=urlparse(value)
            if u.scheme or not u.path:continue
            target=(html.parent/unquote(u.path)).resolve();local_links+=1
            if not target.is_file():broken.append((str(html.relative_to(r)),value))
    assert not broken,broken[:30]
    receipt=dict(checker_sha256=implementation_digest(),frozen_files=len(frozen['files']),controls=33,planned=24,attempts=len(runs),delivered=delivered,
        unique_contexts=len(thread_ids),source_files_verified=input_files,supplied_full_comparisons_agree=parity,
        report_manifests=report_manifests,report_files_verified=report_files,local_links_checked=local_links,broken_links=broken,
        diagnostic_images_verified=view_images,
        trial_statuses=dict(Counter(c['status'] for c in runs)))
    save(r/'verification.json',receipt);print(json.dumps(receipt))

if __name__=='__main__':main()
