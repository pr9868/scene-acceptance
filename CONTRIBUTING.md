# Contributing an evaluation pack

Start from `examples/studio-mesh-pack`. A pack can remain a separate Python distribution; it need not be merged into this core project. The caller explicitly enables installed entry points.

1. State the consuming task and the requirement you can evaluate. Name what your check cannot establish.
2. Reuse a suitable upstream validator or measurement before writing a new algorithm. Pin and record the tested dependency versions.
3. Give the pack a unique stable ID, exact version, compatible API version and complete implementation file declaration. Supply strict parameter schemas and reproducible dependency/setup instructions.
4. Return an `Outcome` with a status, reason and inspectable evidence. Include object/property, observed/expected values, units, time where applicable and coverage limits. Do not return an overall acceptance decision or edit submitted content.
5. Add compliant, violating, missing-evidence and unsupported cases. Check wrong or empty provider output, missing dependencies and changed revisions. Freeze expected decisions before judging the implementation, and retain failures.
6. Test the packaged install, not only imports from your development checkout. Pair native checks with consumer requirements where either alone is insufficient. Document when a native rule does nothing because its relevant API or objects are absent.

From the project root:

```sh
python -m pip install '.[test,nvidia]'
python -m pip install ./examples/studio-mesh-pack
python -m pytest -q
python evaluation/packs-v1/run.py --out /tmp/pack-review
```

The output path must be new. Without optional NVIDIA/example dependencies, their dedicated tests skip explicitly; the full release evidence uses both installed. Do not cite skipped checks as evaluated coverage.

Keep the evaluator/producer boundary intact. Expensive simulation, renderer or model-based checks should run in an explicitly managed environment with their own input identity, versions, timeout and reference protocol. The current core supports trusted local function packs; a worker protocol is future work. A package import is execution of trusted code, not a security boundary.

This project uses the MIT license. Include appropriate licenses and attribution for dependencies and separately distributed packs. Keep changes focused on a consuming requirement, with reproducible passing and failing examples.

For a release, preserve historical fixtures and reports, update the file manifest with `python scripts/update-manifest.py`, then run the full README replay from a fresh packaged install. This command records current files; it does not establish that changes are correct. Review the manifest diff and the corresponding evidence before committing it. CI verifies the committed manifest and retained observations. Do not rewrite old expected outcomes merely to make a new implementation pass.
