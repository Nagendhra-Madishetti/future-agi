"""Canonical eval-output normalization shared across writer surfaces.

Lifted from ``tracer/utils/eval.py`` so every writer (tracer, simulate, and
follow-up dataset / experiment / billing surfaces) calls the same code with
the same gating contract on the **stored** ``eval_template.config["output"]``.

Public API:

* ``dedupe_preserve_order`` — stable de-dup for choice lists.
* ``eval_config_output`` — read the stored ``config["output"]`` off a custom
  eval config; defaults to ``"score"`` if missing.
* ``dual_write_eval_value`` — populates ``logger_kwargs`` with the typed
  ``output_float`` / ``output_str_list`` / ``output_bool`` columns alongside
  ``output_str``. Used by ``tracer_eval_logger``.
* ``coerce_to_legacy_scalar`` — projects any eval result into a FE-safe
  scalar (string / number / bool / ``None``) suitable for storing in a
  JSONB blob and querying with JSONB operators.
* ``build_simulate_eval_payload`` — assembles the canonical per-row payload
  written into ``CallExecution.eval_outputs[<eval_config_id>]``.
"""

from __future__ import annotations

import json
from typing import Any


def dedupe_preserve_order(items: list[Any]) -> list[Any]:
    """Return ``items`` with duplicates removed, keeping first-seen order."""
    seen: set[Any] = set()
    out: list[Any] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def eval_config_output(custom_eval_config: Any) -> str:
    """Read the stored ``output`` type off an eval template config.

    Never use the runtime-promoted value (``format_eval_value`` internally
    promotes ``score`` → ``choices`` when ``choice_scores`` exist); the gating
    rules below are keyed on the **stored** type.
    """
    try:
        return custom_eval_config.eval_template.config.get("output", "score")
    except (AttributeError, TypeError):
        return "score"


def dual_write_eval_value(
    value: Any,
    config_output: str,
    logger_kwargs: dict[str, Any],
) -> None:
    """Populate ``logger_kwargs`` with one eval result, dual-writing both the
    new (``output_str``) and legacy (``output_float`` / ``output_str_list``)
    shapes so FE readers that still consume the typed columns keep working.

    Gating:

    * ``output_float`` is (re-)populated only when ``config_output == "score"``.
    * ``output_str_list`` is (re-)populated only when ``config_output == "choices"``.
    * ``output_bool`` is set for raw booleans and ``"Passed"``/``"Failed"``.
    * Any other ``config_output`` (``Pass/Fail``, ``reason``, ``numeric``, …)
      keeps the original isinstance-chain behaviour.
    """
    if isinstance(value, bool):
        logger_kwargs["output_bool"] = value
        return
    if value in ("Passed", "Failed"):
        logger_kwargs["output_bool"] = value == "Passed"
        return

    if config_output == "score":
        if isinstance(value, dict):
            logger_kwargs["output_str"] = json.dumps(value)
            score = value.get("score")
            if isinstance(score, int | float) and not isinstance(score, bool):
                logger_kwargs["output_float"] = float(score)
        elif isinstance(value, int | float):
            logger_kwargs["output_float"] = float(value)
        elif isinstance(value, list):
            logger_kwargs["output_str"] = json.dumps(value)
            numerics: list[float] = []
            for v in value:
                if isinstance(v, bool):
                    continue
                if isinstance(v, int | float):
                    numerics.append(v)
                elif isinstance(v, dict):
                    s = v.get("score")
                    if isinstance(s, int | float) and not isinstance(s, bool):
                        numerics.append(s)
            if numerics:
                logger_kwargs["output_float"] = sum(numerics) / len(numerics)
        else:
            logger_kwargs["output_str"] = str(value)
        return

    if config_output == "choices":
        if isinstance(value, dict):
            logger_kwargs["output_str"] = json.dumps(value)
            choice = value.get("choice")
            choices = value.get("choices")
            if isinstance(choice, str):
                logger_kwargs["output_str_list"] = [choice]
            elif isinstance(choices, list):
                logger_kwargs["output_str_list"] = dedupe_preserve_order(choices)
        elif isinstance(value, str):
            logger_kwargs["output_str"] = value
            logger_kwargs["output_str_list"] = [value]
        elif isinstance(value, list):
            if any(isinstance(v, dict) for v in value):
                logger_kwargs["output_str"] = json.dumps(value)
            collected: list[str] = []
            for v in value:
                if isinstance(v, str):
                    collected.append(v)
                elif isinstance(v, dict):
                    inner_choice = v.get("choice")
                    inner_choices = v.get("choices")
                    if isinstance(inner_choice, str):
                        collected.append(inner_choice)
                    elif isinstance(inner_choices, list):
                        collected.extend(c for c in inner_choices if isinstance(c, str))
            logger_kwargs["output_str_list"] = dedupe_preserve_order(collected)
        elif isinstance(value, int | float):
            logger_kwargs["output_float"] = float(value)
        else:
            logger_kwargs["output_str"] = str(value)
        return

    if isinstance(value, int | float):
        logger_kwargs["output_float"] = float(value)
    elif isinstance(value, list):
        logger_kwargs["output_str_list"] = value
    else:
        logger_kwargs["output_str"] = str(value)


def coerce_to_legacy_scalar(value: Any, config_output: str) -> Any:
    """Project ``value`` into a FE-safe scalar suitable for a JSONB column
    and for SQL filter predicates.

    Contract:

    * ``None`` → ``None``.
    * Plain scalars (``bool`` / ``int`` / ``float`` / ``str``) → passthrough.
    * Dicts on a ``score`` config → ``dict["score"]`` when numeric, else ``None``.
    * Dicts on a ``choices`` config → ``dict["choice"]`` when string,
      ``json.dumps(dict["choices"])`` when list, else ``None``.
    * Dicts on any other config → ``json.dumps(dict)`` (round-trippable).
    * Lists on a ``score`` config → mean of numeric / numeric-bearing dict
      entries, or ``None`` if no numerics are present.
    * Lists on a ``choices`` config → ``json.dumps([...])`` of the de-duped
      flattened choices.
    * Lists on any other config → ``json.dumps([...])``.
    * Anything else → ``json.dumps(value)`` (best-effort round-trip).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        return value

    if config_output == "score":
        if isinstance(value, dict):
            score = value.get("score")
            if isinstance(score, int | float) and not isinstance(score, bool):
                return float(score)
            return None
        if isinstance(value, list):
            numerics: list[float] = []
            for v in value:
                if isinstance(v, bool):
                    continue
                if isinstance(v, int | float):
                    numerics.append(v)
                elif isinstance(v, dict):
                    s = v.get("score")
                    if isinstance(s, int | float) and not isinstance(s, bool):
                        numerics.append(s)
            if numerics:
                return sum(numerics) / len(numerics)
            return None

    if config_output == "choices":
        if isinstance(value, dict):
            choice = value.get("choice")
            if isinstance(choice, str):
                return choice
            choices = value.get("choices")
            if isinstance(choices, list):
                return json.dumps(dedupe_preserve_order(choices))
            return None
        if isinstance(value, list):
            collected: list[str] = []
            for v in value:
                if isinstance(v, str):
                    collected.append(v)
                elif isinstance(v, dict):
                    inner_choice = v.get("choice")
                    inner_choices = v.get("choices")
                    if isinstance(inner_choice, str):
                        collected.append(inner_choice)
                    elif isinstance(inner_choices, list):
                        collected.extend(c for c in inner_choices if isinstance(c, str))
            return json.dumps(dedupe_preserve_order(collected))

    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return str(value)


def build_simulate_eval_payload(
    *,
    value: Any,
    config_output: str,
    reason: str = "",
    name: str = "",
    output_type: str | None = None,
    error: Any = None,
    status: str | None = None,
    skipped: bool = False,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Assemble the canonical eval-row dict written into
    ``CallExecution.eval_outputs[<eval_config_id>]``.

    Always emits the additive ``output_scalar`` and ``output_dict`` keys so
    every row in the JSONB blob has identical shape — filter predicates can
    rely on a key being present (with a ``None`` value) on every row.
    """
    payload: dict[str, Any] = {
        "output": value,
        "output_scalar": coerce_to_legacy_scalar(value, config_output),
        "output_dict": value if isinstance(value, dict) else None,
        "reason": reason,
        "output_type": output_type,
        "name": name,
    }
    if error is not None:
        payload["error"] = error
    if status is not None:
        payload["status"] = status
    if skipped:
        payload["skipped"] = True
    if timestamp is not None:
        payload["timestamp"] = timestamp
    return payload
