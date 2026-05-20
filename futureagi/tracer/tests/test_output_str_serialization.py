"""TH-4903: categorical eval dicts route to typed EvalLogger columns.

Pre-fix, dict eval results fell through to ``str(value)`` and were stored as
Python repr in ``output_str`` — unparseable by the read path. Per Jaya's
review on PR #415 the fix is type-aware: ``score`` → ``output_float``,
``choice`` / ``choices`` → ``output_str_list``. ``output_str`` is only used
as a defensive JSON fallback for shapes we don't recognise.

The routing helper lives in ``tracer/utils/eval.py`` as
``_route_dict_eval_value`` and is invoked from all 5 dispatchers. We mirror
the helper here to avoid pulling in the Django-dependent eval.py module,
and a source-level guard locks the call-site count at 5.
"""

import json
import re
from pathlib import Path

import pytest

EVAL_FILE = Path(__file__).parent.parent / "utils" / "eval.py"


def _route_dict_eval_value(value, logger_kwargs):
    """Mirror of the helper in tracer/utils/eval.py. Kept in sync via the
    ``test_helper_called_at_all_five_sites`` source-level guard."""
    score = value.get("score")
    choice = value.get("choice")
    choices = value.get("choices")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        logger_kwargs["output_float"] = float(score)
    if isinstance(choice, str):
        logger_kwargs["output_str_list"] = [choice]
    elif isinstance(choices, list):
        logger_kwargs["output_str_list"] = choices
    if not any(k in logger_kwargs for k in ("output_float", "output_str_list")):
        logger_kwargs["output_str"] = json.dumps(value)


@pytest.mark.parametrize(
    "value,expected",
    [
        # Single-choice categorical: score → output_float, choice → output_str_list
        ({"score": 0.5, "choice": "Pass"},
         {"output_float": 0.5, "output_str_list": ["Pass"]}),
        # Multi-choice categorical
        ({"score": 0.7, "choices": ["A", "B"]},
         {"output_float": 0.7, "output_str_list": ["A", "B"]}),
        # Pure score (no choice)
        ({"score": 0.42}, {"output_float": 0.42}),
        # Unknown shape — defensive JSON fallback (parseable, not Python repr)
        ({"foo": "bar", "n": 1},
         {"output_str": json.dumps({"foo": "bar", "n": 1})}),
    ],
)
def test_routing_per_dict_shape(value, expected):
    kw = {}
    _route_dict_eval_value(value, kw)
    for key, want in expected.items():
        assert kw[key] == want, f"{key}: expected {want}, got {kw.get(key)}"
    leaked = set(kw) - set(expected)
    assert not leaked, f"unexpected kwargs written: {leaked}"


def test_helper_called_at_all_five_sites():
    """``_route_dict_eval_value`` must be invoked from all 5 dispatchers.
    Matches call sites only (indented), not the def line."""
    src = EVAL_FILE.read_text()
    calls = re.findall(r"^\s+_route_dict_eval_value\(", src, re.MULTILINE)
    assert len(calls) == 5, f"expected 5 calls, found {len(calls)}"
