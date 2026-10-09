"""Diagnose the frozen incline experiment without changing its acceptance policy."""

import argparse
from importlib.metadata import version
import json
import math
from pathlib import Path

import mujoco
import numpy as np
from scene_acceptance.followups.worker import read_bounded
from scene_acceptance.followups.incline_adapter import model_xml
from scene_acceptance.model import sha


def run(scene, *, dt, impratio, noslip, duration=5.0):
    fixture = read_bounded(scene)
    model = mujoco.MjModel.from_xml_string(model_xml(fixture, dt))
    model.opt.impratio = impratio
    model.opt.noslip_iterations = noslip
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    origin = data.qpos[:3].copy()
    angle = math.radians(fixture["ramp"]["angle_deg"])
    axis = np.array([math.cos(angle), 0, -math.sin(angle)])
    trace = []
    for i in range(round(duration / dt) + 1):
        trace.append([float(data.time), float(np.dot(data.qpos[:3] - origin, axis))])
        if i < round(duration / dt):
            mujoco.mj_step(model, data)
            mujoco.mj_forward(model, data)
    values = np.array(trace)
    if not np.isfinite(values).all():
        raise RuntimeError("Non-finite solver trajectory")
    tail = values[values[:, 0] >= duration - 1.0]
    slope = float(np.polyfit(tail[:, 0], tail[:, 1], 1)[0])
    return dict(
        dt_s=dt,
        impratio=impratio,
        noslip_iterations=noslip,
        duration_s=duration,
        friction=fixture["mu"],
        final_displacement_m=trace[-1][1],
        maximum_displacement_m=max(abs(row[1]) for row in trace),
        last_second_drift_m=float(tail[-1, 1] - tail[0, 1]),
        last_second_slope_m_s=slope,
        settled=abs(slope) <= 1e-5,
        settled_slope_limit_m_s=1e-5,
        warnings=sum(int(w.number) for w in data.warning),
        trace=trace,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    rows = []
    for name in ("high", "low"):
        source = (
            root
            / "evaluation/article-checks-v1/fixtures"
            / ("physics-" + name)
            / "scene.usda"
        )
        for dt in (0.002, 0.001):
            for label, ratio, noslip in [
                ("original", 1.0, 0),
                ("high-impratio", 100.0, 0),
                ("noslip", 1.0, 10),
            ]:
                result = run(source, dt=dt, impratio=ratio, noslip=noslip)
                key = f"{name}-{label}-{dt}"
                (out / (key + ".json")).write_text(json.dumps(result, indent=2) + "\n")
                rows.append(
                    dict(
                        case=key,
                        scene_sha256=sha(source),
                        **{k: v for k, v in result.items() if k != "trace"},
                    )
                )
    report = dict(
        schema_version="1.0",
        study="Fixed-scope solver sensitivity diagnostic",
        runs=rows,
        versions={name: version(name) for name in ("mujoco", "numpy", "usd-core")},
        limitation="Constructed two-box model only. Solver sensitivity is not validation of real material friction or PhysX. Original acceptance results and tolerances are unchanged. Settled means the predeclared last-second slope threshold only.",
    )
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "runs"}))


if __name__ == "__main__":
    main()
