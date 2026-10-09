"""Refresh packaged application schemas and check discovery after source review."""
import json
from pathlib import Path
from scene_acceptance.application_schemas import SCHEMAS
from scene_acceptance.packs import default_registry

ROOT = Path(__file__).resolve().parents[1] / 'src/scene_acceptance'
for name, definition in SCHEMAS.items():
    (ROOT / 'schemas' / (name + '.schema.json')).write_text(json.dumps(definition, indent=2) + '\n')
path = ROOT / 'profiles/test-catalog.json'
catalog = json.loads(path.read_text())
catalog['configurable_checks'] = []
catalog['pack_versions'] = {}
for pack in default_registry().catalog():
    catalog['pack_versions'][pack['id']] = pack['version']
    for name, check in pack['checks'].items():
        catalog['configurable_checks'].append(dict(id=pack['id']+'.'+name, pack=pack['id'], check=name, **check))
path.write_text(json.dumps(catalog, indent=2) + '\n')
