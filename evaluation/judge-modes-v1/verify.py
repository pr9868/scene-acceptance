"""Verify retained study inputs, output integrity, model contexts and scripted parity."""
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
from scene_acceptance.model import digest_json,sha
from scene_acceptance.judge import validate_response


def read(p):return json.loads(p.read_text())


class Links(HTMLParser):
    def __init__(self):super().__init__();self.targets=[]
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in ('href','src') and value:self.targets.append(value)


def verify(root):
    freeze=read(root/'freeze.json');old=Path(freeze['original_packet']);plan=read(root/'plan.json');results=read(root/'results.json')
    assert len(plan)==len(results['rows'])==29
    assert all(sha(root/p)==h for p,h in freeze['files'].items())
    assert all(sha(p)==h for p,h in freeze['original_files'].items())
    assert sha(old/'PACKET_MANIFEST.json')==freeze['original_packet_seal_sha256']
    original_seal=read(old/'PACKET_MANIFEST.json');assert all(sha(old/p)==h for p,h in original_seal['files'].items())
    contexts=[];rows=[];all_requests={};usage=Counter()
    for job in plan:
        folder=root/'runs'/job['id'];r=read(folder/'evaluation/evaluation.json');jr=read(folder/'evaluation/judge/judge-result.json');req=read(folder/'evaluation/judge/request.json');all_requests[job['id']]=req
        assert r['checker_sha256']==freeze['checker_sha256'] and r['source_unchanged']
        config=read(folder/'evaluation/judge/config.json');assert config==read(root/'judge-config.json')
        assert r['judge']['evidence_exposure']==job['exposure']==req['evidence_exposure']
        assert all(sha(p)==h for p,h in jr['input_hashes'].items())
        assert digest_json({k:v for k,v in req.items() if k!='request_sha256'})==req['request_sha256']==jr['request_sha256']
        measurements=[e for e in req['evidence'] if e['id'].startswith('check:')]
        if job['exposure']=='withheld':assert req['script_verdict'] is None and not measurements
        else:assert measurements and req['script_verdict']=='REJECT'
        if job['brief'] is None:assert len(req['requirements'])==5 and not any(e['id'].startswith('brief:') for e in req['evidence'])
        else:assert len(req['requirements'])==18
        assert len([e for e in req['evidence'] if e['id'].startswith('view:')])==3
        folder_core=folder/'evaluation/script';folder_core=folder_core/'report' if job['brief'] else folder_core
        core=read(folder_core/('core-result.json' if job['brief'] else 'result.json'))
        previous=old/'assessments'/job['scene_id'];previous=previous/'full/report/core-result.json' if job['brief'] else previous/'default/result.json';before=read(previous)
        assert core['verdict']==before['verdict'] and {c['id']:c['status'] for c in core['checks']}=={c['id']:c['status'] for c in before['checks']}
        events=[]
        for line in (folder/'evaluation/judge/stdout.log').read_text().splitlines():
            try:events.append(json.loads(line))
            except ValueError:pass
        thread_ids=[e['thread_id'] for e in events if e.get('type')=='thread.started'];contexts+=thread_ids
        unexpected=[e for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type') not in ('agent_message','reasoning')]
        assert not unexpected
        if r['judge']['status']=='completed':
            assert len(thread_ids)==1;validate_response(read(folder/'evaluation/judge/response.json'),req)
            assert sum(e.get('type')=='turn.completed' for e in events)==1
        usage.update(jr.get('usage') or {})
        rows.append(dict(id=job['id'],judge_status=r['judge']['status'],native_contexts=thread_ids,source_unchanged=True,script_outcomes_match=True,known_request_and_citations=True))
    assert len(contexts)==len(set(contexts))
    repeats=[]
    for job in plan:
        if job['phase']!='repeat':continue
        def normalized(ident):
            x={k:v for k,v in all_requests[ident].items() if k!='request_sha256'}
            return json.dumps(x,sort_keys=True).replace(str(root/'runs'/ident/'evaluation'),'<same-review-output>')
        assert normalized(job['id'])==normalized(job['scene_id']),job['id']
        repeats.append(job['id'])
    manifests=0;manifest_files=0
    for p in (root/'runs').rglob('manifest.json'):
        m=read(p)
        if 'files' not in m:continue
        for name,h in m['files'].items():
            f=p.parent/name;assert f.is_file() and sha(f)==h,(str(p),name);manifest_files+=1
        manifests+=1
    links=0
    for p in root.rglob('*.html'):
        parser=Links();parser.feed(p.read_text())
        for target in parser.targets:
            url=urlsplit(target)
            if url.scheme or url.netloc or not url.path:continue
            f=(p.parent/unquote(url.path)).resolve()
            if f==root/'verification.json':continue
            assert f.exists(),(str(p),target);links+=1
    result=dict(original_packet_files_verified=len(original_seal['files']),original_source_files_verified=len(freeze['original_files']),frozen_files_verified=len(freeze['files']),
                reviews=len(rows),unique_native_contexts=len(contexts),all_script_outcomes_match=True,all_original_sources_unchanged=True,
                repeated_evidence_content_matches=repeats,output_manifests=manifests,manifest_files_checked=manifest_files,local_links=links,
                usage=usage,model_snapshot_verified=False,model_opinion_truth_verified=False,rows=rows)
    (root/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='rows'}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();verify(a.root.resolve())
