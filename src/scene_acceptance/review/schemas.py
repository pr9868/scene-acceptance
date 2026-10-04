"""Closed schemas; origin, enforcement, evidence and judgment remain separate."""

LAYERS = ("explicit", "inferred", "decisions", "delivery", "use_evidence")
TEXT = {"type": "string", "minLength": 1, "pattern": r"\S"}
ID = {"type": "string", "pattern": "^[a-z][a-z0-9_.-]*$"}
HASH = {"type": "string", "pattern": "^[a-f0-9]{64}$"}


def obj(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def array(items, minimum=0):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": 256}


def nullable(item):
    return {"anyOf": [item, {"type": "null"}]}


def enum(*items):
    return {"enum": list(items)}


AUTHORIZATION = obj({"status": enum("approved", "proposed"), "by": TEXT, "reason": TEXT})
PLAN = obj({
    "schema_version": {"const": "1.0"}, "id": ID,
    "intended_use": TEXT, "contract": TEXT, "contract_sha256": HASH,
    "candidate": TEXT, "baseline": nullable(TEXT),
    "mapping_review": obj({"status": enum("reviewed", "pending"),
                           "reviewer": TEXT, "reason": TEXT}),
    "layers": obj({layer: obj({"scope": enum("included", "excluded"), "reason": TEXT})
                   for layer in LAYERS}),
    "items": array(obj({
        "id": ID, "layer": enum(*LAYERS), "statement": TEXT,
        "basis": TEXT, "required": {"type": "boolean"},
        "check_ids": {**array(ID), "uniqueItems": True},
        "review_required": {"type": "boolean"},
        "decision_id": nullable(ID), "inference_authorization": nullable(AUTHORIZATION),
    }), 1),
})

# Optional reporting declarations are identity-bound; they do not replace check evidence or approval.
PLAN['properties']['report_context'] = {'type':'object','properties':{'scene_name':TEXT},'additionalProperties':False}
ITEM = PLAN['properties']['items']['items']
ITEM['properties']['specification_source'] = obj({'provided_by':enum('human','application','agent','preset','unrecorded'),'reference':TEXT})
ITEM['properties']['areas'] = {**array(enum('geometry','materials','textures','uv','motion','physics','simulation','appearance','delivery','other'),1),'uniqueItems':True}
ITEM['properties']['coverage_declaration'] = obj({'extent':enum('full','partial','unreviewed'),'reason':TEXT})
ITEM['properties']['evaluation_route'] = enum('script','visual','both','unresolved','unsupported')
ITEM['properties']['review_evidence_kind'] = enum('scene_view','textured_view','motion_frames','measurements','physical_validation')
ITEM['properties']['review_statement'] = TEXT

PRODUCER = obj({
    "schema_version": {"const": "1.0"},
    "decisions": array(obj({
        "id": ID, "choice": TEXT, "reason": TEXT,
        "alternatives": array(TEXT), "assumptions": array(TEXT),
        "affected_paths": array(TEXT), "evidence": array(TEXT),
    })),
})

REVIEW = obj({
    "schema_version": {"const": "1.0"}, "snapshot_sha256": HASH,
    "reviews": array(obj({
        "item_id": ID, "status": enum("approved", "rejected", "needs_review"),
        "reviewer": TEXT, "reason": TEXT,
        "evidence": array(obj({"path": TEXT, "sha256": HASH}), 1),
    })),
})

ITEM['properties']['mapping_author'] = obj({'kind':TEXT,'reference':TEXT})
