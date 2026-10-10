# JSON CLI adapter boundary

`adapter.py` is a provider-neutral transport example. It reads `request["model_protocol"]["response_schema"]`; it never imports private harness schemas. Supply a caller-owned provider configuration:

```json
{
  "identity": {"model": "your-pinned-model", "effort": "your-setting", "adapter_version": "1"},
  "command": ["/absolute/path/to/python", "/absolute/path/to/your_provider.py"],
  "timeout_seconds": 120
}
```

Your provider reads `{request, response_schema, provider_identity}` from stdin and returns one JSON object. Map those fields to your provider's API. Attach only the `image_path` files named in the request, in their evidence order; preserve evidence IDs. Text-only forwarding does not supply visual evidence. The harness does not send images through this generic adapter for you. Keep authentication in the provider's normal credential store/environment. Configure the same model in the provider and harness; a requested model name does not prove the resolved snapshot.

Configure the harness `json-cli` executable as Python, with arguments pointing to this adapter and `--provider` config. The enclosing harness enforces its own timeout, byte limits, exact response identity and role-specific validation. The example's `--record` writes a new explicit file. Records contain the provider's response; review them before sharing.

## Three different identities

| Identity | Purpose |
|---|---|
| `request_sha256` | Exact transport request; the response must echo it. Local evidence locations can differ between runs. |
| `semantic_input_sha256` | Full supplied context, role and schema, with admitted file locations replaced by content hashes. This survives relocation of those files. |
| `projected_context_sha256` | The context actually sent after bounded projection. A smaller inventory budget can change this even when the full semantic input is unchanged. |

The example also binds the complete provider configuration to its reuse key. Change that identity when model snapshot, reasoning settings, adapter behavior or other result-affecting settings change. Do not use the semantic hash alone as a cache key.

`--replay previous-record.json` is explicit and labelled `adapter_mode=replay` in stderr and in the new record. It verifies all these identities before rebinding the old answer to the new transport hash. This tests transport/workflow compatibility. It is **not a fresh model run** and must not count towards model-quality evidence. There is no automatic cache lookup or fallback from a failed fresh call to an old answer.
