"""Supervise native USD work in a separate, resource-bounded process group."""

import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid


def supervise(
    command: list[str],
    *,
    wall_seconds: float,
    memory_mib: int,
    cpu_seconds: float,
    max_output_bytes: int,
    stdin: bytes = b"",
    control=None,
) -> dict:
    """Run a caller-owned command. Resource limits do not make it a security sandbox."""
    import psutil
    from scene_acceptance.execution import controlled, checkpoint

    values = (wall_seconds, memory_mib, cpu_seconds, max_output_bytes)
    if any(
        type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values
    ):
        raise ValueError("Resource limits must be finite and positive")
    if os.name != "posix":
        raise ValueError("Supervised process-group execution currently requires POSIX")
    started = time.monotonic()
    peak = 0
    reason = None
    proc = None
    known = {}
    with (
        controlled(control),
        tempfile.TemporaryDirectory(prefix="scene-supervisor-") as temp,
    ):
        checkpoint()
        root = Path(temp)
        (root / "input").write_bytes(stdin)
        try:
            with (
                (root / "input").open("rb") as source,
                (root / "stdout").open("wb") as stdout,
                (root / "stderr").open("wb") as stderr,
            ):
                proc = subprocess.Popen(
                    command,
                    stdin=source,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=True,
                )
                monitor = psutil.Process(proc.pid)
                while proc.poll() is None:
                    checkpoint()
                    try:
                        children = [monitor, *monitor.children(recursive=True)]
                        memory = 0
                        cpu = 0.0
                        for child in children:
                            try:
                                known[child.pid] = child
                                memory += child.memory_info().rss
                                usage = child.cpu_times()
                                cpu += usage.user + usage.system
                            except psutil.NoSuchProcess:
                                continue
                        peak = max(peak, memory)
                    except psutil.NoSuchProcess:
                        continue
                    except (psutil.AccessDenied, PermissionError):
                        reason = "resource_monitor_unavailable"
                        break
                    if time.monotonic() - started > wall_seconds:
                        reason = "wall_time_limit"
                    elif memory > memory_mib * 1024 * 1024:
                        reason = "resident_memory_limit"
                    elif cpu > cpu_seconds:
                        reason = "cpu_time_limit"
                    elif any(
                        (root / name).stat().st_size > max_output_bytes
                        for name in ("stdout", "stderr")
                    ):
                        reason = "output_limit"
                    if reason:
                        break
                    time.sleep(0.02)
            if reason is None and any(
                (root / name).stat().st_size > max_output_bytes
                for name in ("stdout", "stderr")
            ):
                reason = "output_limit"
        finally:
            if proc is not None:
                # Kill the process group even when the leader already exited.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                for child in known.values():
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                proc.wait(timeout=5)

        def read(name):
            with (root / name).open("rb") as stream:
                return stream.read(max_output_bytes).decode("utf-8", errors="replace")

        return dict(
            returncode=proc.returncode,
            limit_reason=reason,
            stdout=read("stdout"),
            stderr=read("stderr"),
            peak_observed_rss_bytes=peak,
            elapsed_seconds=time.monotonic() - started,
            limitation="POSIX process group plus sampled process-tree RSS/CPU; brief spikes or escaped processes may evade sampling. Arbitrary engine commands do not receive hard allocator or CPU limits from this supervisor. This is resource containment, not filesystem/network isolation.",
        )


def invoke_isolated(
    operation: str,
    *,
    wall_seconds=120.0,
    memory_mib=2048,
    cpu_seconds=120.0,
    max_output_bytes=8388608,
    deadline_seconds=None,
    cancel_file=None,
    progress=False,
    **parameters,
) -> dict:
    from .execution import RunControl, Cancelled, DeadlineExceeded

    control = RunControl(deadline_seconds=deadline_seconds, cancel_file=cancel_file)
    packet = dict(
        operation=operation,
        parameters=parameters,
        memory_mib=memory_mib,
        cpu_seconds=cpu_seconds,
        progress=bool(progress),
    )
    output = {}
    try:
        output = supervise(
            [sys.executable, str(Path(__file__).resolve()), "--worker"],
            wall_seconds=wall_seconds,
            memory_mib=memory_mib,
            cpu_seconds=cpu_seconds,
            max_output_bytes=max_output_bytes,
            stdin=json.dumps(packet, allow_nan=False, default=str).encode(),
            control=control,
        )
        if output["limit_reason"] or output["returncode"] not in (0, 2, 3, 4):
            raise ValueError("Worker did not complete")
        response = json.loads(output["stdout"])
        from jsonschema import Draft202012Validator
        from .application_schemas import ENVELOPE_SCHEMA

        Draft202012Validator(ENVELOPE_SCHEMA).validate(response)
        if response["exit_code"] != output["returncode"]:
            raise ValueError("Worker exit and envelope disagree")
    except Exception as exc:
        response = dict(
            schema_version="1.0",
            operation=operation,
            run_id=str(uuid.uuid4()),
            status=(
                "cancelled"
                if isinstance(exc, Cancelled)
                else (
                    "timed_out"
                    if isinstance(exc, DeadlineExceeded)
                    or output.get("limit_reason") == "wall_time_limit"
                    else "failed"
                )
            ),
            exit_code=4,
            reused=False,
            data=None,
            events=[],
            errors=[
                dict(
                    code=output.get("limit_reason") or type(exc).__name__,
                    phase="isolated_worker",
                    message=str(exc)
                    or "Native worker did not return a complete bounded response.",
                    retryable=False,
                )
            ],
        )
    response["isolation"] = {k: v for k, v in output.items() if k != "stdout"}
    if sys.platform.startswith("linux"):
        response["isolation"][
            "worker_limits"
        ] = "The harness worker additionally installs per-process RLIMIT_AS and RLIMIT_CPU before opening inputs."
    return response


def worker():
    packet = json.load(sys.stdin)
    if sys.platform.startswith("linux"):
        import resource

        memory = int(packet["memory_mib"] * 1024 * 1024)
        cpu = math.ceil(packet["cpu_seconds"])
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    from scene_acceptance.application import invoke

    from scene_acceptance.execution import RunControl

    control = RunControl(
        progress=(
            (lambda event: print(json.dumps(event), file=sys.stderr, flush=True))
            if packet.get("progress")
            else None
        )
    )
    result = invoke(packet["operation"], control=control, **packet["parameters"])
    print(json.dumps(result, allow_nan=False))
    return result["exit_code"]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run check-3d-app in a supervised native worker"
    )
    parser.add_argument("--wall-seconds", type=float, default=120.0)
    parser.add_argument("--memory-mib", type=int, default=2048)
    parser.add_argument("--cpu-seconds", type=float, default=120.0)
    parser.add_argument("application_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    from .application import parser as app_parser

    values = vars(app_parser().parse_args(args.application_args))
    operation = values.pop("operation")
    result = invoke_isolated(
        operation,
        wall_seconds=args.wall_seconds,
        memory_mib=args.memory_mib,
        cpu_seconds=args.cpu_seconds,
        **values,
    )
    if values.get("progress") and result.get("isolation", {}).get("stderr"):
        print(result["isolation"]["stderr"], file=sys.stderr, end="")
    print(json.dumps(result, allow_nan=False))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(worker() if sys.argv[1:] == ["--worker"] else main())
