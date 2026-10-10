"""Public-protocol adapter skeleton. Provider code owns API/image transport."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from jsonschema import Draft202012Validator


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def reuse_key(request, provider_identity):
    p = request["model_protocol"]
    # Model snapshot/effort/adapter settings and actual projected context all
    # matter. Never strip paths by basename or rewrite an arbitrary old answer.
    return digest(
        dict(
            role=p["role"],
            protocol_version=p["version"],
            protocol_instruction=p["instruction"],
            schema=p["response_schema_sha256"],
            semantic_input=p["semantic_input_sha256"],
            projection=p["projected_context_sha256"],
            provider=provider_identity,
        )
    )


def exchange(request, provider, *, replay=None):
    schema = request["model_protocol"]["response_schema"]
    key = reuse_key(request, provider)
    if replay is not None:
        if replay["reuse_key"] != key:
            raise ValueError("Replay context or model configuration does not match")
        response = deepcopy(replay["response"])
        if response["request_sha256"] != replay["request_sha256"]:
            raise ValueError("Stored response has a different transport identity")
        response["request_sha256"] = request["request_sha256"]
        mode = "replay"
    else:
        # The configured provider must attach ONLY the explicitly named images,
        # use response_schema and return one JSON object. It owns credentials,
        # model selection, provider-specific payloads and timeouts.
        payload = dict(
            request=request,
            response_schema=schema,
            provider_identity=provider["identity"],
        )
        result = subprocess.run(
            provider["command"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
            timeout=provider["timeout_seconds"],
        )
        response = json.loads(result.stdout)
        mode = "fresh"
    Draft202012Validator(schema).validate(response)
    if response["request_sha256"] != request["request_sha256"]:
        raise ValueError("Provider response belongs to another request")
    record = dict(
        mode=mode,
        reuse_key=key,
        request_sha256=request["request_sha256"],
        response=response,
        provider_identity=provider["identity"],
    )
    return response, record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, type=Path)
    parser.add_argument(
        "--replay",
        type=Path,
        help="Explicit protocol replay; never fresh model evidence",
    )
    parser.add_argument("--record", type=Path, help="New caller-owned JSON file")
    args = parser.parse_args()
    request = json.load(sys.stdin)
    provider = json.loads(args.provider.read_text())
    replay = json.loads(args.replay.read_text()) if args.replay else None
    response, record = exchange(request, provider, replay=replay)
    if args.record:
        with args.record.open("x") as stream:
            json.dump(record, stream, indent=2)
    print("adapter_mode=" + record["mode"], file=sys.stderr)
    print(json.dumps(response))


if __name__ == "__main__":
    main()
