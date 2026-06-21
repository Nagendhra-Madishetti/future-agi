"""Per-axis projection of simulate eval-row payloads."""

from __future__ import annotations

from typing import Any

AXIS_KEYS: tuple[str, ...] = (
    "output_pass",
    "output_score",
    "output_choices",
)


def empty_axes() -> dict[str, None]:
    return dict.fromkeys(AXIS_KEYS, None)


def dedupe_preserve_order(items: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    out: list[Any] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def eval_config_output(custom_eval_config: Any) -> str:
    """Stored ``eval_template.config["output"]``; default ``"score"`` on miss."""
    try:
        return custom_eval_config.eval_template.config.get("output", "score")
    except (AttributeError, TypeError):
        return "score"


def eval_config_multi_choice(custom_eval_config: Any) -> bool:
    try:
        return bool(custom_eval_config.eval_template.multi_choice)
    except AttributeError:
        return False


def extract_score(value: Any) -> float | None:
    """Project ``value`` into a single float; lists collapse to the numeric mean."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
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
                numerics.append(float(v))
            elif isinstance(v, dict):
                inner = v.get("score")
                if isinstance(inner, int | float) and not isinstance(inner, bool):
                    numerics.append(float(inner))
        if numerics:
            return sum(numerics) / len(numerics)
    return None


def extract_choices(value: Any) -> list[str] | None:
    """Project ``value`` into a deduped list of chosen labels; single-pick yields one element."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        choice = value.get("choice")
        if isinstance(choice, str):
            return [choice]
        choices = value.get("choices")
        if isinstance(choices, list):
            strings = [v for v in choices if isinstance(v, str)]
            return dedupe_preserve_order(strings) if strings else None
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
        return dedupe_preserve_order(collected) if collected else None
    return None


def extract_pass(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value == "Passed":
        return True
    if value == "Failed":
        return False
    return None


def resolve_eval_axes(
    value: Any, config_output: str, multi_choice: bool = False
) -> dict[str, Any]:
    """Project ``value`` into the 3 axis keys; ``config_output`` anchors the primary axis."""
    axes: dict[str, Any] = empty_axes()
    if value is None:
        return axes
    if config_output == "Pass/Fail":
        axes["output_pass"] = extract_pass(value)
        return axes
    if config_output in ("score", "numeric"):
        axes["output_score"] = extract_score(value)
        axes["output_choices"] = extract_choices(value)
        return axes
    if config_output == "choices":
        axes["output_score"] = extract_score(value)
        axes["output_choices"] = extract_choices(value)
        return axes
    return axes


def build_simulate_eval_payload(
    *,
    value: Any,
    config_output: str,
    multi_choice: bool = False,
    reason: str = "",
    name: str = "",
    output_type: str | None = None,
    error: Any = None,
    status: str | None = None,
    skipped: bool = False,
    timestamp: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "output": value,
        **resolve_eval_axes(value, config_output, multi_choice),
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
