"""Prepare an explicitly synthetic assumption-review handoff; no model call."""
import argparse
import json
from pathlib import Path
import shlex
import shutil
from scene_acceptance.contract_upgrade import upgrade_copied_contracts
from scene_acceptance.model import sha
from scene_acceptance.review import assess
from scene_acceptance.review.__main__ import write_report
from scene_acceptance.review.schemas import LAYERS


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def prepare(out):
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    bundle, owner = root / 'delivery', root / 'review'
    source = Path(__file__).resolve().parents[2] / 'evaluation/packs-v1/fixtures/material_correct'
    shutil.copytree(source, bundle)
    upgrade_copied_contracts(bundle)
    owner.mkdir()
    brief = owner / 'brief.txt'
    brief.write_text('Synthetic handoff exercise, not an engineering brief or human approval.\n'
                     'The visualization may use the delivered surface material; no exact color is required.\n'
                     'Before any prediction of contact behavior, physical material parameters need measured evidence and domain review.\n')
    decisions = dict(schema_version='1.0', decisions=[dict(
        id='physical-material', choice='Use the visual material as a physical reference',
        reason='Deliberately unsupported choice for the example', alternatives=['Obtain measured parameters'],
        assumptions=['A visually plausible material provides evidence of contact friction.'],
        affected_paths=['/World/Panel'], evidence=['scene.usda'])])
    save(bundle / 'decisions.json', decisions)
    common = dict(basis='Synthetic caller policy; software demonstration only',
                  required=True, inference_authorization=None)
    plan = dict(schema_version='1.0', id='triage-example',
                intended_use='Illustrative delivery review before considering physical prediction; no calibration is established',
                contract='contract.json', contract_sha256=sha(bundle/'contract.json'),
                candidate='scene.usda', baseline=None,
                mapping_review=dict(status='reviewed', reviewer='Synthetic control policy',
                                    reason='Known fixture mapping, not a human assessment'),
                layers={x:dict(scope='included' if x in ('explicit','decisions') else 'excluded',
                               reason='Selected synthetic demonstration scope') for x in LAYERS},
                items=[dict(common,id='visual-material',layer='explicit',statement='Delivered surface material is allowed for visualization',
                            check_ids=['appearance.delivery'],review_required=False,decision_id=None),
                       dict(common,id='physical-basis',layer='decisions',statement='Physical use needs grounded material parameters',
                            check_ids=[],review_required=True,decision_id='physical-material')])
    save(owner / 'plan.json', plan)
    result = assess('plan.json', review_root=owner, bundle_root=bundle,
                    expected_plan_sha256=sha(owner/'plan.json'), decision_record='decisions.json')
    write_report(result, root / 'assessment')
    policy = dict(schema_version='1.1', id='synthetic-triage-policy', version='1.1',
        review_risk_rubric={
            'low': 'Limited and reversible impact; a brief owner check can settle the choice.',
            'medium': 'Could invalidate the intended use or require substantial rework; review the basis.',
            'high': 'Could have serious consequences for physical operation or a consequential decision; require qualified domain review.'},
        items=[
        dict(item_id='visual-material', allow_routine_handling=True, mandatory_human_review=False,
             reason='Styling is discretionary when the delivered material binding passes.',
             review_guidance='Do not invent an exact color requirement for this visualization.', evidence_ids=['brief']),
        dict(item_id='physical-basis', allow_routine_handling=False, mandatory_human_review=True,
             minimum_review_risk='high',
             reason='Physical-calibration assumptions require domain review.',
             review_guidance='Appearance cannot establish physical contact parameters. Request evidence and review.', evidence_ids=['brief'])],
        evidence=[dict(id='brief',path='brief.txt',sha256=sha(brief),kind='text',description='Synthetic caller brief')])
    save(owner / 'triage-policy.json', policy)
    args = dict(assessment=str(root/'assessment/assessment.json'),
                expected_assessment_sha256=sha(root/'assessment/assessment.json'),
                policy=str(owner/'triage-policy.json'), expected_policy_sha256=sha(owner/'triage-policy.json'),
                bundle_root=str(bundle), review_root=str(owner))
    save(root/'invocation-inputs.json',args)
    return args


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    inputs=prepare(args.out)
    command=['check-3d-app','triage']
    for key,value in inputs.items():command.extend(['--'+key.replace('_','-'),value])
    command.extend(['--triage-config','YOUR_MODEL_CONFIG.json','--out',str(Path(args.out).resolve()/'triage')])
    print(shlex.join(command))
