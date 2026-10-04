"""Bounded caller attestations for renderer-provided MDL source dependencies.

These receipts are caller statements, not independent resolver or shader tests.
Only an explicitly selected target environment can use them. Original missing
files and upstream validation messages remain in the report.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import re

from jsonschema import Draft202012Validator
from .model import ContractError, digest_bytes, pairs
from .review.schemas import HASH, obj

TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 2048, 'pattern': r'\S'}
IDENTITY = obj({'name': TEXT, 'version': TEXT})
REFERENCE = obj({'layer': TEXT, 'attribute': TEXT, 'identifier': TEXT,
                 'source_type': {'const': 'mdl'}, 'resolved_identifier': TEXT,
                 'library_sha256': HASH})
RUNTIME_DEPENDENCY_RECEIPT_SCHEMA = obj({
    'schema_version': {'const': '1.0'},
    'kind': {'const': 'renderer-mdl-dependency-attestation'},
    'scene_sha256': HASH,
    'environment_sha256': HASH,
    'renderer': IDENTITY,
    'runtime': IDENTITY,
    'provenance': obj({'attested_by': TEXT, 'source': TEXT,
                       'observed_at_utc': TEXT, 'expires_at_utc': TEXT}),
    'dependencies': {'type': 'array', 'items': REFERENCE, 'minItems': 1, 'maxItems': 256},
})
LIMITATION = ('Caller-attested dependency availability in the named target environment; '
              'the harness did not resolve, compile, render, or independently verify the MDL library.')


def validate_runtime_policy(policy, environment_sha256):
    if policy not in ('local-only', 'caller-attested'):
        raise ContractError('Unknown runtime dependency policy')
    if policy == 'caller-attested':
        if not isinstance(environment_sha256, str) or not re.fullmatch('[a-f0-9]{64}', environment_sha256):
            raise ContractError('Caller-attested dependencies require a pinned runtime environment SHA256')
    elif environment_sha256 is not None:
        raise ContractError('A runtime environment pin requires caller-attested dependency policy')


def validate_freshness(data):
    def instant(value):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (TypeError, ValueError):
            raise ContractError('Runtime dependency receipt needs valid UTC observation and expiry times') from None
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            raise ContractError('Runtime dependency receipt times must include UTC timezone')
        return parsed
    observed = instant(data['provenance']['observed_at_utc'])
    expiry = instant(data['provenance']['expires_at_utc'])
    now = datetime.now(timezone.utc)
    if observed > now or expiry <= observed or expiry <= now:
        raise ContractError('Runtime dependency receipt is stale, expired, or future-dated')


def _bounded_bytes(path):
    if not path.is_file() or path.stat().st_size > 262144:
        raise ContractError('Runtime dependency receipt must be a regular file no larger than 256 KiB')
    with path.open('rb') as stream:
        payload = stream.read(262145)
    if len(payload) > 262144:
        raise ContractError('Runtime dependency receipt exceeds 256 KiB')
    return payload


def read_receipt(path):
    """Strict bounded reader also used before a completed invocation can be reused."""
    path = Path(path).resolve()
    payload = _bounded_bytes(path)
    before = digest_bytes(payload)
    def reject_constant(value):
        raise ContractError('Non-finite value in runtime dependency receipt: ' + value)
    data = json.loads(payload, object_pairs_hook=pairs, parse_constant=reject_constant)
    Draft202012Validator(RUNTIME_DEPENDENCY_RECEIPT_SCHEMA).validate(data)
    if digest_bytes(_bounded_bytes(path)) != before:
        raise ContractError('Runtime dependency receipt changed while being read')
    validate_freshness(data)
    keys = [tuple(row[k] for k in ('layer', 'attribute', 'identifier', 'source_type'))
            for row in data['dependencies']]
    if len(keys) != len(set(keys)):
        raise ContractError('Duplicate runtime dependency attestation')
    return path, before, data


class RuntimeDependencies:
    def __init__(self, artifact, *, policy='local-only', environment_sha256=None, evidence=None):
        validate_runtime_policy(policy, environment_sha256)
        if evidence is not None and policy != 'caller-attested':
            raise ContractError('Runtime dependency evidence requires explicit caller-attested policy')
        self.policy, self.environment_sha256 = policy, environment_sha256
        self.path = self.digest = self.receipt = None
        self.accepted = {}
        if evidence is None:
            return
        self.path, self.digest, self.receipt = read_receipt(evidence)
        data = self.receipt
        if data['scene_sha256'] != artifact.artifact_set_sha256:
            raise ContractError('Runtime dependency receipt belongs to a different scene')
        if data['environment_sha256'] != environment_sha256:
            raise ContractError('Runtime dependency receipt belongs to a different target environment')
        expected = {}
        for path, refs in artifact.runtime_assets.items():
            if artifact.assets[path] is not None:
                continue
            for ref in refs:
                key = tuple(ref[k] for k in ('layer', 'attribute', 'identifier', 'source_type'))
                expected[key] = path
        covered = {}
        for row in data['dependencies']:
            key = tuple(row[k] for k in ('layer', 'attribute', 'identifier', 'source_type'))
            if key not in expected:
                raise ContractError('Receipt names no matching unresolved authored MDL source: ' + row['attribute'])
            covered.setdefault(expected[key], []).append(deepcopy(row))
        for path, rows in covered.items():
            if len({(row['resolved_identifier'], row['library_sha256']) for row in rows}) != 1:
                raise ContractError('Conflicting runtime identities for one MDL dependency')
            if len(rows) == len({tuple(ref[k] for k in ("layer", "attribute", "identifier", "source_type"))
                                 for ref in artifact.runtime_assets[path]}):
                self.accepted[path] = rows
        self.assert_unchanged()

    def assert_unchanged(self):
        if self.path is not None:
            if not self.path.is_file() or digest_bytes(_bounded_bytes(self.path)) != self.digest:
                raise ContractError('Runtime dependency receipt changed during evaluation')
            validate_freshness(self.receipt)

    def for_path(self, path):
        self.assert_unchanged()
        if path not in self.accepted:
            return None
        return dict(basis='caller_attestation', policy=self.policy, receipt_sha256=self.digest,
                    environment_sha256=self.environment_sha256,
                    renderer=deepcopy(self.receipt['renderer']), runtime=deepcopy(self.receipt['runtime']),
                    provenance=deepcopy(self.receipt['provenance']),
                    dependencies=deepcopy(self.accepted[path]), limitation=LIMITATION)

    def report(self):
        return dict(policy=self.policy, environment_sha256=self.environment_sha256,
                    supplied=self.receipt is not None, receipt_sha256=self.digest,
                    receipt=deepcopy(self.receipt),
                    accepted_dependency_count=len(self.accepted), limitation=LIMITATION)


def evidence_for(ctx, path):
    runtime = getattr(ctx, 'runtime_dependencies', None)
    return runtime.for_path(path) if runtime else None
