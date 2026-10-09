"""Human-readable test discovery without invoking validators or models."""
from importlib.resources import files
import json
from .review_context import GENERAL_RUBRIC, VIEWS_SCHEMA, RUBRIC_SCHEMA


def test_catalog():
    result=json.loads(files('scene_acceptance').joinpath('profiles/test-catalog.json').read_text())
    result['advisory_rubric']=GENERAL_RUBRIC
    result['notes']=['Baseline rules are selected by default; configurable check types run only when selected by a contract or brief.',
                     'Catalog entries are capabilities, not proof they ran on a scene.',
                     'Model review requires explicit selection and suitable evidence; rubric items are not measured passes.']
    return result


def capabilities():
    from .engine import VERSION, implementation_digest
    from .model import schema
    from .preparation import RAW_BRIEF_SCHEMA, CAPABILITIES_SCHEMA, CAPTURE_OVERRIDES_SCHEMA, RECEIPT_SCHEMA
    from .skill_package import NAMES
    from .application_schemas import SCHEMAS
    from .environment import LIMITS,environment_identity
    from .judge import CONFIG_SCHEMA
    return dict(schema_version='1.0',version=VERSION,checker_sha256=implementation_digest(),
                modes=['checks','judge','both'],brief_optional=True,default_model_calls=False,
                artifact_format='usd-local-v1',evaluation_schema='1.0',judge_request_schema='2.0',
                legacy_interface_preserved=True,model_drivers=['codex','json-cli'],model_config_schema=CONFIG_SCHEMA,evaluation_result_schema=schema('evaluation-v1'),
                judge_exposure=['withheld','script-aware'],view_manifest_schema=VIEWS_SCHEMA,rubric_schema=RUBRIC_SCHEMA,
                limits=LIMITS,environment=environment_identity(),application_cli='check-3d-app',application_schemas=SCHEMAS,
                preparation={'schema_version':'1.0','cli':'check-3d-prepare','evaluate_cli':'check-3d-run-plan',
                    'raw_brief_schema':RAW_BRIEF_SCHEMA,'capture_capabilities_schema':CAPABILITIES_SCHEMA,
                    'capture_overrides_schema':CAPTURE_OVERRIDES_SCHEMA,'capture_receipt_schema':RECEIPT_SCHEMA,
                    'automatic_mapping_packs':['brief.measurements','motion.timing','motion.connection','materials','textures.decode'],'rendering':'caller-owned'},
                assumption_triage={'schema_version':'1.0','operation':'triage','cli':'check-3d-triage','opt_in':True,'input':'caller-pinned declared-scope assessment','automatic_assumption_discovery':False,'result_schema_version':'1.1','resolve_operation':'resolve-triage','human_review_required_for_mandatory_items':True},
                bundled_skills=list(NAMES),skill_export_cli='check-3d-skills --out NEW_DIRECTORY',
                discovery=['--list-tests','--capabilities'])
