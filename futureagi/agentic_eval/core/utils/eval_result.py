"""Builder for the standard ``EvalResult`` envelope."""

from __future__ import annotations

from typing import Any

from agentic_eval.core_evals.fi_utils.evals_result import EvalResult


def build_eval_result(
    *,
    name: str,
    display_name: str,
    result_value: Any,
    failure: bool,
    explanation: str,
    runtime_ms: int,
    model: str | None,
    metric_id: str,
    metadata: str,
    datapoint_field_annotations: Any = None,
) -> EvalResult:
    """Build the standard ``EvalResult`` dict produced by every evaluator."""
    return {
        "name": name,
        "display_name": display_name,
        "data": {"result": result_value},
        "failure": failure,
        "metadata": metadata,
        "reason": explanation,
        "runtime": runtime_ms,
        "model": model,
        "metrics": [{"id": metric_id, "value": result_value}],
        "datapoint_field_annotations": datapoint_field_annotations,
    }


__all__ = ["build_eval_result"]
