"""Example consumer policy: a polygon budget, not a frame-rate prediction."""

from pathlib import Path
from pxr import UsdGeom, Sdf
from scene_acceptance.packs import Pack, CheckSpec, Outcome
from scene_acceptance.model import ContractError


def count_faces(ctx, params):
    observations = []
    failed = False
    for path in params["paths"]:
        p = Sdf.Path(path)
        if not p.IsAbsolutePath() or not p.IsPrimPath():
            raise ContractError("Expected an absolute prim path")
        mesh = UsdGeom.Mesh(ctx.artifact.stage.GetPrimAtPath(p))
        if not mesh:
            return Outcome("FAIL", "Required mesh absent", {"object": path})
        counts_attr = mesh.GetFaceVertexCountsAttr()
        if counts_attr.ValueMightBeTimeVarying():
            return Outcome(
                "UNKNOWN",
                "This budget check covers static topology only",
                {"object": path},
            )
        counts = counts_attr.Get()
        if counts is None:
            return Outcome("UNKNOWN", "Face counts unavailable", {"object": path})
        count = len(counts)
        failed |= count > params["max_faces_per_mesh"]
        observations.append(
            {
                "object": path,
                "observed_faces": count,
                "maximum_faces": params["max_faces_per_mesh"],
            }
        )
    return Outcome(
        "FAIL" if failed else "PASS",
        "Compared polygon face counts to the consumer's budget.",
        {
            "findings": observations,
            "coverage": "Polygon counts only, not topology validity, triangulation cost or frame rate.",
        },
    )


def get_pack():
    return Pack(
        id="studio.mesh-budget",
        version="0.1.0",
        description="Example third-party polygon budget policy",
        checks={
            "faces": CheckSpec(
                run=count_faces,
                parameters={
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 256,
                            "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "max_faces_per_mesh": {"type": "integer", "minimum": 0},
                    },
                    "required": ["paths", "max_faces_per_mesh"],
                    "additionalProperties": False,
                },
                description="Require each selected static mesh to fit a polygon budget",
                coverage="Named meshes at default time",
                limitations=(
                    "No mesh validity or measured rendering performance claim",
                ),
            )
        },
        source_files=(str(Path(__file__)),),
        dependencies=("usd-core",),
    )
