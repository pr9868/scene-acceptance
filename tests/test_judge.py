"""External model output cannot silently become acceptance or ungrounded evidence."""
import json
from pathlib import Path
import sys
import pytest
from scene_acceptance.briefs import evaluate_brief
from scene_acceptance.judge import run_judge, request_for, validate_response
from scene_acceptance.model import ContractError, sha
from test_briefs import prepare

@pytest.fixture
def report(tmp_path):
    samples=prepare.prepare(tmp_path/'samples')
    evaluate_brief('briefs/image-b.json','scene.usda',bundle_root=samples/'panel',out=tmp_path/'evaluation')
    return tmp_path/'evaluation/report'

def adapter(tmp_path,mode='normal'):
    script=tmp_path/f'adapter-{mode}.py'
    script.write_text('''import json,sys,time
r=json.load(sys.stdin)
mode=sys.argv[1]
if mode=='timeout': time.sleep(10)
items=[dict(requirement_id=x['id'],assessment='consistent',explanation='Mock only; deliberately disagrees with the script.',evidence_ids=['brief:0']) for x in r['requirements']]
if mode=='unknown-id': items[0]['evidence_ids']=['made-up']
if mode=='missing': items.pop()
if mode=='malformed': print('not json');sys.exit(0)
print(json.dumps(dict(request_sha256='0'*64 if mode=='stale' else r['request_sha256'],items=items,limitations=['Mock software control, not an actual model judgment.'])))
''')
    config=tmp_path/f'config-{mode}.json'
    config.write_text(json.dumps(dict(driver='json-cli',executable=sys.executable,args=[str(script),mode],model='deterministic-test-double',effort='none',timeout_seconds=1)))
    return config

def test_judge_is_separate_and_cannot_override_failure(report,tmp_path):
    before=sha(report/'core-result.json')
    r=run_judge(report,adapter(tmp_path),tmp_path/'judge')
    assert r['status']=='ADVISORY_REVIEW_COMPLETE'
    assert r['script_verdict_unchanged']=='REJECT'
    assert all(x['assessment']=='consistent' for x in r['response']['items'])
    assert sha(report/'core-result.json')==before
    assert r['resolved_model'] is None
    request=json.loads((tmp_path/'judge/request.json').read_text())
    assert request['model_requested']=='deterministic-test-double' and request['effort_requested']=='none'

@pytest.mark.parametrize('mode',['unknown-id','missing','malformed','stale','timeout'])
def test_judge_errors_retained_not_passes(report,tmp_path,mode):
    out=tmp_path/'judge';r=run_judge(report,adapter(tmp_path,mode),out)
    assert r['status']=='ERROR' and r['response'] is None and r['error']
    assert r['script_verdict_unchanged']=='REJECT'
    assert (out/'request.json').is_file() and (out/'stderr.log').is_file()

def test_judge_rejects_modified_source_file(report,tmp_path):
    (report/'brief-sources/00.txt').write_text('Changed brief')
    with pytest.raises(ContractError): request_for(report)

def test_judge_requires_all_items_and_real_evidence(report):
    request,_,_=request_for(report)
    response=dict(request_sha256=request['request_sha256'],items=[dict(requirement_id=x['id'],assessment='unknown',explanation='Insufficient evidence',evidence_ids=[]) for x in request['requirements']],limitations=['Not a physical proof'])
    assert validate_response(response,request)==response
    response['items'][0]['assessment']='consistent'
    with pytest.raises(ContractError): validate_response(response,request)
