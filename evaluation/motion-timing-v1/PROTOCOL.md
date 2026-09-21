# Motion timing acceptance controls

Recorded before execution on 20 September 2026. These are constructed evaluator tests. No agent performance or independent validation is implied.

Brief: the panel origin moves from x=0 to x=1 metre over a two-second authored stage interval, with x=0.5 at one elapsed second. Clock and position comparisons are separate required checks; positions depend on a usable, conforming clock. No continuous path or occupied-shape claim is made.

A rate-only change must reject. Rescaling both the time range and keyframes preserves the brief and must accept, including a nonzero stage start. Extending the range alone must not hide early motion completion. Missing or unusable clock/range evidence remains unresolved. Valid but conflicting duration, rate or sampled positions reject. Schema-invalid instructions return an evaluation error. The old time-code-only pack retains its declared semantics.

Fixture manifest records expected verdicts and input hashes before running the evaluator. Retain first reports and subsequent fixes; do not rewrite historical v0.3.0 inputs or reports.
