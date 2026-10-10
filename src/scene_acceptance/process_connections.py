"""Check explicitly tagged ports against a caller-supplied directed connection list."""

from pathlib import Path

from pxr import Sdf

from .builtin_packs import obj, TEXT
from .model import ContractError
from .packs import CheckSpec, Outcome, Pack


def connections(ctx, params):
    stage = ctx.artifact.stage
    assets, ports, tags = {}, {}, set()
    for asset in params["assets"]:
        asset_path = Sdf.Path(asset["path"])
        if not asset_path.IsAbsolutePath() or not asset_path.IsPrimPath():
            raise ContractError("Equipment must use absolute USD prim paths")
        names = set()
        if asset["path"] in assets or asset["tag"] in tags:
            raise ContractError("Asset paths and reference tags must be unique")
        assets[asset["path"]] = asset
        tags.add(asset["tag"])
        for port in asset["ports"]:
            port_path = Sdf.Path(port["path"])
            if (
                not port_path.IsAbsolutePath()
                or not port_path.IsPrimPath()
                or port["name"] in names
            ):
                raise ContractError(
                    "Ports need absolute prim paths and unique names within equipment"
                )
            names.add(port["name"])
            if (
                port["path"] in ports
                or not Sdf.Path(port["path"]).HasPrefix(Sdf.Path(asset["path"]))
                or port["path"] == asset["path"]
            ):
                raise ContractError(
                    "Ports must be unique descendants of their named equipment"
                )
            ports[port["path"]] = port
    expected = set()
    for connection in params["connections"]:
        source, target = connection["from"], connection["to"]
        if (
            source not in ports
            or target not in ports
            or source == target
            or (source, target) in expected
        ):
            raise ContractError(
                "Connections must be unique and join two declared ports"
            )
        if ports[source]["direction"] not in ("out", "bidirectional") or ports[target][
            "direction"
        ] not in ("in", "bidirectional"):
            raise ContractError(
                "Reference connection conflicts with its declared port directions"
            )
        expected.add((source, target))
    findings = []
    observed = set()

    def compare(path, attribute_name, desired):
        prim = stage.GetPrimAtPath(path)
        if not prim:
            findings.append(
                dict(
                    object=path,
                    property=attribute_name,
                    expected=desired,
                    observed=None,
                    status="FAIL",
                )
            )
            return False
        attribute = prim.GetAttribute(attribute_name)
        if not attribute or not attribute.HasAuthoredValueOpinion():
            findings.append(
                dict(
                    object=path,
                    property=attribute_name,
                    expected=desired,
                    observed=None,
                    status="UNKNOWN",
                    reason="Missing authored process metadata",
                )
            )
            return True
        if (
            attribute.GetTypeName()
            not in (Sdf.ValueTypeNames.String, Sdf.ValueTypeNames.Token)
            or attribute.GetNumTimeSamples()
        ):
            findings.append(
                dict(
                    object=path,
                    property=attribute_name,
                    expected=desired,
                    observed=None,
                    status="UNKNOWN",
                    reason="Process topology requires static string/token metadata",
                )
            )
            return True
        value = attribute.Get()
        normalized = (
            params.get("direction_aliases", {}).get(value, value)
            if attribute_name == params["direction_attribute"]
            else value
        )
        findings.append(
            dict(
                object=path,
                property=attribute_name,
                expected=desired,
                observed=value,
                normalized=normalized,
                status="PASS" if normalized == desired else "FAIL",
            )
        )
        return True

    for asset in assets.values():
        compare(asset["path"], params["tag_attribute"], asset["tag"])
    for path, port in ports.items():
        if not compare(path, params["port_name_attribute"], port["name"]):
            continue
        compare(path, params["direction_attribute"], port["direction"])
        relationship = stage.GetPrimAtPath(path).GetRelationship(
            params["connection_relationship"]
        )
        if relationship:
            observed.update((path, str(target)) for target in relationship.GetTargets())
    for source, target in sorted(expected | observed):
        if (source, target) in expected:
            status = "PASS" if (source, target) in observed else "FAIL"
            reason = (
                "Required connection exists"
                if status == "PASS"
                else "Required connection is missing"
            )
        else:
            status = "PASS" if params["allow_extra_connections"] else "FAIL"
            reason = (
                "Additional connection permitted by policy"
                if status == "PASS"
                else "Undeclared connection"
            )
        findings.append(
            dict(object=source, target=target, status=status, reason=reason)
        )
    statuses = {row["status"] for row in findings}
    status = (
        "FAIL" if "FAIL" in statuses else "UNKNOWN" if "UNKNOWN" in statuses else "PASS"
    )
    return Outcome(
        status,
        "Compared named equipment, port identities, directions and saved directed relationships with the reference list.",
        {
            "findings": findings,
            "equipment_count": len(assets),
            "port_count": len(ports),
            "expected_connection_count": len(expected),
            "observed_connection_count": len(observed),
            "coverage": "Only the caller-declared equipment and ports. No P&ID extraction, pipe geometry, "
            "hydraulics, valve-state simulation, safety or whole-plant engineering validation.",
        },
    )


def process_pack():
    direction = {"enum": ["in", "out", "bidirectional"]}
    port = obj({"path": TEXT, "name": TEXT, "direction": direction})
    asset = obj(
        {
            "path": TEXT,
            "tag": TEXT,
            "ports": {"type": "array", "items": port, "minItems": 1, "maxItems": 64},
        }
    )
    parameters = obj(
        {
            "assets": {"type": "array", "items": asset, "minItems": 1, "maxItems": 256},
            "connections": {
                "type": "array",
                "items": obj({"from": TEXT, "to": TEXT}),
                "maxItems": 4096,
            },
            "tag_attribute": TEXT,
            "port_name_attribute": TEXT,
            "direction_attribute": TEXT,
            "connection_relationship": TEXT,
            "allow_extra_connections": {"type": "boolean"},
        }
    )
    parameters["properties"]["direction_aliases"] = {
        "type": "object",
        "additionalProperties": direction,
        "maxProperties": 32,
    }
    return Pack(
        "process.connections",
        "1.1.0",
        "Directed port topology against a structured reference",
        {
            "match": CheckSpec(
                connections,
                parameters,
                "Compare tagged equipment and directed port relationships",
                "Declared static equipment/port metadata and connection-list agreement",
                (
                    "A correct graph is not process fitness or physical connectivity proof",
                ),
            ),
        },
        (str(Path(__file__)),),
        ("usd-core",),
    )
