"""Lossless provider evidence with a bounded, useful application projection."""


def status_of(rows):
    statuses = {r["status"] for r in rows}
    return next(
        (s for s in ("FAIL", "ERROR", "UNKNOWN") if s in statuses),
        "PASS" if rows else "UNKNOWN",
    )


def summarize(observations, limit=64):
    if not isinstance(observations, dict):
        return {}
    values = {
        k: v
        for k, v in observations.items()
        if k not in ("findings", "assessment", "intervals")
        and (
            v is None
            or isinstance(v, (str, int, float, bool))
            or isinstance(v, list)
            and len(v) <= 16
            and all(isinstance(x, (str, int, float, bool)) for x in v)
        )
    }
    rows = observations.get(
        "findings",
        observations.get("assessment", {}).get(
            "items", observations.get("intervals", [])
        ),
    )
    if isinstance(rows, list) and all(isinstance(r, dict) for r in rows):
        # Put failures/gaps first without changing the provider's complete evidence.
        ordered = sorted(
            enumerate(rows), key=lambda x: (x[1].get("status") == "PASS", x[0])
        )
        values.update(
            findings=[r for _, r in ordered[:limit]],
            observation_count=len(rows),
            omitted_observation_count=max(0, len(rows) - limit),
        )
    return values
