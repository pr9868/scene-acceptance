# Infrastructure recovery, before the first model response

The first assigned CLI launch, ordinary_edit-1/initial, failed in 0.668 seconds because local Codex state was read-only and its in-process app-server could not initialize. It produced no response, usage record or model event. The failed request, stderr and empty event log remain unchanged.

A separately named recovery-1 launch uses the exact same frozen prompt and settings, with filesystem approval for the CLI runtime. It is not recorded as a successful initial launch. The other seven initial assignments remain unchanged. Report 8 assigned briefs/repetitions, the original infrastructure failure, and any subsequent response separately. Model-level correctness and artifact acceptance denominators include actual responses; end-to-end initial-launch success includes the failed launch. No expected answer, requirement, checker or selection rule changed.
