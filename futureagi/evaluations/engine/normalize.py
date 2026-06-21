"""Per-axis projection helpers for eval-row payloads."""

from __future__ import annotations

import ast
from typing import Any

AXIS_KEYS: tuple[str, ...] = (
    "output_bool",
    "output_float",
    "output_str_list",
)

AXIS_STORAGE_TO_API: tuple[tuple[str, str], ...] = (
    ("output_bool", "output_pass"),
    ("output_float", "output_score"),
    ("output_str_list", "output_choices"),
)


def empty_axes() -> dict[str, None]:
    return dict.fromkeys(AXIS_KEYS, None)


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


def resolve_eval_axes(
    value: Any, config_output: str, *, include_output_str: bool = False
) -> dict[str, Any]:
    """Project ``value`` into typed columns; missing keys default to None."""
    keys = AXIS_KEYS + (("output_str",) if include_output_str else ())
    axes: dict[str, Any] = dict.fromkeys(keys, None)
    if value is None:
        return axes
    from tracer.utils.eval import _dual_write_eval_value

    projected: dict[str, Any] = {}
    _dual_write_eval_value(
        value, config_output, projected, permissive_secondary_axis=True
    )
    for key in keys:
        if key in projected:
            axes[key] = projected[key]
    return axes


def project_storage_axes_to_api(eval_data: dict) -> dict[str, Any]:
    """Read storage-axis keys off ``eval_data``, return API-named dict."""
    return {api: eval_data.get(storage) for storage, api in AXIS_STORAGE_TO_API}


def parse_legacy_value(raw: Any) -> Any:
    """Decode legacy string-encoded eval values; pass non-strings through."""
    if raw is None or not isinstance(raw, str):
        return raw
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError, RecursionError, MemoryError, TypeError):
        return raw
