"""Small, versioned extension API. Installed plugins load only with caller approval."""

from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
import re
from types import MappingProxyType
from typing import Callable
from jsonschema import Draft202012Validator
from .model import ContractError, digest_json, sha

API_VERSION = "1.0"
ENTRY_POINT_GROUP = "scene_acceptance.packs"
NAME = re.compile(r"^[a-z][a-z0-9_.-]*$")


@dataclass(frozen=True)
class Outcome:
    status: str
    reason: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CheckSpec:
    run: Callable
    parameters: dict
    description: str
    coverage: str
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pack:
    id: str
    version: str
    description: str
    checks: dict[str, CheckSpec]
    source_files: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    api_version: str = API_VERSION

    def __post_init__(self):
        if not NAME.fullmatch(self.id) or self.api_version != API_VERSION:
            raise ContractError("Invalid pack name or incompatible pack API")
        if not re.fullmatch(r"\d+\.\d+\.\d+", self.version):
            raise ContractError(
                "Pack versions must be exact major.minor.patch versions"
            )
        if not self.checks or not self.source_files:
            raise ContractError("A pack needs checks and explicit implementation files")
        for name, spec in self.checks.items():
            if not NAME.fullmatch(name) or not isinstance(spec, CheckSpec):
                raise ContractError("Invalid check declaration")
            if not callable(spec.run) or not spec.description or not spec.coverage:
                raise ContractError(
                    "A check needs a callable, description and coverage"
                )
            Draft202012Validator.check_schema(spec.parameters)
        object.__setattr__(self, "checks", MappingProxyType(dict(self.checks)))

    def describe(self):
        deps = {}
        for name in self.dependencies:
            try:
                dist = metadata.distribution(name)
                deps[name] = {
                    "version": dist.version,
                    "record_sha256": digest_json(dist.read_text("RECORD")),
                }
            except metadata.PackageNotFoundError:
                deps[name] = {"available": False}
        files = {
            str(i) + ":" + Path(p).name: sha(p) for i, p in enumerate(self.source_files)
        }
        description = {
            "id": self.id,
            "version": self.version,
            "api_version": self.api_version,
            "description": self.description,
            "checks": {
                name: {
                    "description": s.description,
                    "coverage": s.coverage,
                    "limitations": list(s.limitations),
                    "parameters": s.parameters,
                }
                for name, s in self.checks.items()
            },
            "source_sha256": files,
            "dependencies": deps,
        }
        description["implementation_sha256"] = digest_json(description)
        return description


class PackRegistry:
    def __init__(self, packs=()):
        self._packs = {}
        for pack in packs:
            self.add(pack)

    def add(self, pack):
        if not isinstance(pack, Pack):
            raise ContractError("Entry point must return a Pack")
        if pack.id in self._packs:
            raise ContractError(
                "Duplicate pack cannot replace an existing provider: " + pack.id
            )
        self._packs[pack.id] = pack

    def get(self, name):
        if name not in self._packs:
            raise ContractError("Pack unavailable or not approved: " + name)
        return self._packs[name]

    def catalog(self):
        return [p.describe() for p in self._packs.values()]

    def load_approved(self, names):
        entries = metadata.entry_points(group=ENTRY_POINT_GROUP)
        for name in names:
            matches = [ep for ep in entries if ep.name == name]
            if len(matches) != 1:
                raise ContractError("Expected one installed entry point for: " + name)
            pack = matches[0].load()()
            if not isinstance(pack, Pack) or pack.id != name:
                raise ContractError("Entry-point name must match the returned pack ID")
            self.add(pack)
        return self


def default_registry(approved=()):
    from .builtin_packs import builtin_packs
    from .motion_timing import timing_pack

    return PackRegistry([*builtin_packs(), timing_pack()]).load_approved(approved)


def installed_pack_names():
    """Metadata only: discovery never imports third-party code."""
    return sorted(ep.name for ep in metadata.entry_points(group=ENTRY_POINT_GROUP))
