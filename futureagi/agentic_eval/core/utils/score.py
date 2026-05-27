"""Helpers for LLM-judge score handling.

Used by ``CustomPromptEvaluator`` and ``AgentEvaluator`` only. Function
/ deterministic / code / similarity evaluators compute their own scores
deterministically and must NEVER call into this module — their values
should pass through unchanged.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def clamp_unit_score(raw: Any) -> Any:
    """Coerce an LLM-judge score into the unit range [0, 1].

    Weaker judges occasionally return values outside the requested
    range (e.g. ``3.5`` for a 0-1 score, or ``7`` when the criterion
    phrased the scale as 1-10). Clamping keeps the eval usable rather
    than surfacing the raw out-of-range value or failing the whole run.

    Pass-through semantics:
    - ``None`` returns ``None``.
    - Non-numeric (e.g. ``"abc"``, ``[]``) returns the raw value
      unchanged — the caller is responsible for deciding what to do
      with a result the judge produced in an unparseable shape.
    - Booleans are coerced via ``float()`` (``True`` -> 1.0,
      ``False`` -> 0.0).

    A ``warning`` log is emitted on every clamp so out-of-range judge
    behaviour stays observable.
    """
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return raw
    if v < 0.0 or v > 1.0:
        logger.warning(
            "eval_score_out_of_range_clamped",
            raw_value=v,
            clamped_to=max(0.0, min(1.0, v)),
        )
    return max(0.0, min(1.0, v))


__all__ = ["clamp_unit_score"]
