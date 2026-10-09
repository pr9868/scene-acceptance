"""Caller-controlled deadlines, cancellation and structured progress; no scheduler."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
import os
import math
import signal
import threading
import time
import uuid
from .model import ContractError


class Cancelled(ContractError):
    pass


class DeadlineExceeded(ContractError):
    pass


@dataclass
class RunControl:
    deadline_seconds: float | None = None
    cancel_file: str | None = None
    progress: object = None
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cancelled: bool = False
    timed_out: bool = False
    events: list = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)

    def checkpoint(self, phase=None, **details):
        if self.cancelled or (self.cancel_file and Path(self.cancel_file).exists()):
            self.cancelled = True
            raise Cancelled("Caller cancelled the run")
        if (
            self.deadline_seconds is not None
            and time.monotonic() - self.started > self.deadline_seconds
        ):
            self.timed_out = True
            raise DeadlineExceeded("Caller deadline exceeded")
        if phase:
            event = dict(
                schema_version="1.0",
                run_id=self.run_id,
                sequence=len(self.events),
                phase=phase,
                elapsed_seconds=round(time.monotonic() - self.started, 3),
                **details,
            )
            self.events.append(event)
            if self.progress:
                self.progress(event)


_CURRENT = ContextVar("scene_acceptance_run_control", default=None)


def current():
    return _CURRENT.get()


def checkpoint(phase=None, **details):
    control = current()
    if control:
        control.checkpoint(phase, **details)


@contextmanager
def controlled(control=None):
    control = control or current() or RunControl()
    if control.deadline_seconds is not None and (
        not math.isfinite(control.deadline_seconds) or control.deadline_seconds <= 0
    ):
        raise ContractError("Deadline must be positive")
    token = _CURRENT.set(control)
    previous = {}

    def cancel(signum, frame):
        control.cancelled = True
        raise Cancelled("Caller cancelled the run with signal " + str(signum))

    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, cancel)
    try:
        yield control
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        _CURRENT.reset(token)


def stop_process(proc):
    """Clean up the group we created, including descendants after its leader exits."""
    if proc is None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        elif proc.poll() is None:
            proc.kill()
    except ProcessLookupError:
        pass
    finally:
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
