# Explicit state and process checks

These two packs run only when selected by a contract. Both produce measured observations and subject counts. Neither is added to the general 27-rule baseline, because each needs job-specific reference information.

## State between events

`behavior.state.agreement` compares two authored USD token, string or boolean attributes over a declared interval in elapsed seconds. It unions every transition in the observed, reference and optional activation attributes, compares each held interval and checks the final endpoint. This catches a brief wrong-state interval even when the start and end look correct.

```json
{
  "observed_attribute": "/World/Junction.indicator",
  "expected_attribute": "/World/Junction.route",
  "active_attribute": "/World/Junction.occupied",
  "start_s": 0,
  "end_s": 10
}
```

The stage must author its time range and clock rate, including a supported `framesPerSecond` fallback. Values are held discrete states; interpolated numeric values are outside this check. Missing state, unsupported types or no active interval returns unknown. At most 10,000 combined transition boundaries are evaluated.

For a diverter, the caller must map the indicator's saved state and a justified route/occupancy reference into these attributes. This check does not infer parcel occupancy from meshes, inspect pixels on a rendered sign, or prove that an external controller implements the saved state. A producer-authored reference can agree with a wrong indicator; the owner must review its provenance and scope. The contract names the reference attributes, and scene hashes bind their values along with the delivery.

The constructed control changes the indicator for 0.001 seconds between two otherwise correct events. The check identifies that interval. This demonstrates the algorithm on saved USD; it is not a new replay of the original distribution-centre scene.

## Directed process connections

`process.connections.match` compares a supplied equipment/port list and directed edges against named static USD metadata and relationships.

```json
{
  "assets": [
    {"path": "/World/Tank", "tag": "T-101", "ports": [
      {"path": "/World/Tank/Outlet", "name": "outlet", "direction": "out"}
    ]},
    {"path": "/World/Pump", "tag": "P-101", "ports": [
      {"path": "/World/Pump/Inlet", "name": "inlet", "direction": "in"}
    ]}
  ],
  "connections": [{"from": "/World/Tank/Outlet", "to": "/World/Pump/Inlet"}],
  "tag_attribute": "process:tag",
  "port_name_attribute": "process:port",
  "direction_attribute": "process:direction",
  "connection_relationship": "process:connectsTo",
  "allow_extra_connections": false
}
```

Equipment tags and paths must be unique. Ports need unique paths and names within each equipment item. Reference edges must join declared ports and respect out/in/bidirectional roles. The report counts equipment, ports, reference edges and observed edges, and shows each metadata/edge comparison.

Absent equipment, wrong metadata, missing required edges and forbidden extra edges fail. Missing authored metadata is unknown. Invalid or contradictory reference lists are evaluator/contract errors, not producer failures. If extra connections are permitted, the report discloses them; it does not validate equipment outside the declared list or establish their engineering suitability.

A domain owner may transcribe this list from a P&ID and review it. Automatic drawing interpretation is not included. Graph agreement does not establish that pipe geometry meets a nozzle, a valve is correctly sized, fluids behave correctly, or the plant is safe to operate.

## Try the controls

```sh
python examples/semantic-checks/build.py --out /tmp/semantic-controls
check-3d --bundle-root /tmp/semantic-controls/state-gap \
  --candidate scene.usda --contract contract.json --out /tmp/state-gap-report
```

The generator creates passing and failing state/topology bundles. Each contract pins the installed pack implementation. Use new output directories. These are explicitly synthetic examples; change their names and policy to match a real delivery only after reviewing the mapping.
