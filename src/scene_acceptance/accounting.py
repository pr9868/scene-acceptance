"""Observed invocation costs, with explicit caller estimates and unknown values."""
from pathlib import Path
import math

from jsonschema import Draft202012Validator

from .model import ContractError, strict_json
from .review.schemas import obj, TEXT, nullable, array

NONNEGATIVE = {'type': 'number', 'minimum': 0}
COST_CONTEXT_SCHEMA = obj({
    'schema_version': {'const': '1.0'}, 'delivery_id': TEXT, 'revision_id': TEXT,
    'human_minutes': nullable(NONNEGATIVE), 'compute_cost': nullable(NONNEGATIVE),
    'currency': nullable({'type': 'string', 'pattern': '^[A-Z]{3}$'}),
    'source': TEXT,
})


METRICS_SCHEMA = obj({
    'schema_version': {'const': '1.0'}, 'elapsed_seconds': NONNEGATIVE,
    'model_calls': array(obj({'role': TEXT, 'model': TEXT, 'elapsed_seconds': NONNEGATIVE,
                             'usage': {'type': ['object', 'null']}, 'status': TEXT, 'record': TEXT})),
    'caller_costs': nullable(COST_CONTEXT_SCHEMA), 'limitation': TEXT,
})


def read_cost_context(path):
    if path is None:
        return None
    path = Path(path)
    if path.stat().st_size > 65536:
        raise ContractError('Cost context exceeds 64 KiB')
    data = strict_json(path)
    Draft202012Validator(COST_CONTEXT_SCHEMA).validate(data)
    if data['compute_cost'] is not None and data['currency'] is None:
        raise ContractError('Recorded compute cost requires a currency')
    for key in ('human_minutes', 'compute_cost'):
        if data[key] is not None and not math.isfinite(data[key]):
            raise ContractError('Costs must be finite or null')
    return data


def metrics(elapsed, output, context, operation):
    # Only output locations owned by this operation count. Copied brief/scene
    # inputs may contain similarly named files but are not invocation records.
    locations = {
        'prepare': ('interpreter/interpreter-result.json',),
        'check': ('judge/judge-result.json',),
        'evaluate': ('evaluation/judge/judge-result.json',),
        'triage': ('model/triage-model-result.json',),
    }
    calls = []
    if output and output.is_dir():
        for relative in locations.get(operation, ()):
            path = output / relative
            if not path.is_file() or path.stat().st_size > 8388608:
                continue
            try:
                data = strict_json(path)
                calls.append(dict(role=data['role'], model=data['model_requested'],
                                  elapsed_seconds=data['elapsed_seconds'],
                                  usage=data['usage'] if isinstance(data['usage'], dict) else None,
                                  status=data['status'], record=relative))
            except (OSError, ValueError, KeyError, TypeError):
                continue
    return dict(schema_version='1.0', elapsed_seconds=round(elapsed, 6), model_calls=calls,
                caller_costs=context,
                limitation='Wall time is measured for this invocation. Provider usage is reported as supplied. '
                           'Human effort and billed compute are caller records; absent values are unknown. '
                           'Do not add overlapping invocation times or count a reused receipt twice.')


def summarize(receipts):
    """Group original invocation receipts; do not infer a final release decision."""
    deliveries = {}
    seen = set()
    for path in receipts:
        receipt = strict_json(Path(path))
        result = receipt['envelope']
        run_id = result['run_id']
        if run_id in seen:
            raise ContractError('Duplicate invocation receipt: ' + run_id)
        seen.add(run_id)
        observed = result.get('metrics')
        context = observed and observed.get('caller_costs')
        if not context:
            raise ContractError('Each summarized receipt needs a delivery cost context')
        group = deliveries.setdefault(context['delivery_id'], [])
        group.append(dict(run_id=run_id, revision_id=context['revision_id'], operation=result['operation'],
                          exit_code=result['exit_code'], metrics=observed))
    summaries = []
    for delivery, rows in deliveries.items():
        costs = [r['metrics']['caller_costs'] for r in rows]
        currencies = {c['currency'] for c in costs if c['compute_cost'] is not None}
        if len(currencies) > 1:
            raise ContractError('Mixed currencies in one delivery; convert explicitly before aggregation')
        def total(key):
            values = [c[key] for c in costs]
            return sum(values) if all(v is not None for v in values) else None
        summaries.append(dict(delivery_id=delivery, invocations=len(rows), revisions=len({r['revision_id'] for r in rows}),
                              elapsed_seconds_sum=sum(r['metrics']['elapsed_seconds'] for r in rows),
                              human_minutes=total('human_minutes'), compute_cost=total('compute_cost'),
                              currency=next(iter(currencies), None), runs=rows))
    return dict(schema_version='1.0', deliveries=summaries,
                limitation='Totals cover the supplied receipts only, including failed attempts. Record each cost once. '
                           'A successful preparation or triage call is not delivery acceptance. '
                           'The owner must record the final scoped acceptance separately.')
