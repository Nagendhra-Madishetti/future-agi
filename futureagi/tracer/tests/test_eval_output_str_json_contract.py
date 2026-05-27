"""
TH-4904 — assert ``output_str`` parses as valid JSON when a structured
(dict / list) eval result is routed through the dispatch composition.

This **complements** ``test_eval_dual_write.py`` (which exercises
``_dual_write_eval_value`` in isolation, passing ``config_output`` as a literal
string). It deliberately does NOT re-test the helper's type matrix. The gap
covered here is the dispatch's real composition:

    _dual_write_eval_value(value, _eval_config_output(custom_eval_config), kw)

i.e. ``_eval_config_output`` resolving the STORED output type off the
eval-template config — the exact value ``_execute_evaluation`` /
``_execute_composite_on_span`` (eval.py:823-824 / 936-937) feed into the helper
at call time. The helper-only tests pass the literal ``"score"`` / ``"choices"``
and never exercise this resolution.

Guards the TH-4903 regression: a dict result stored as a Python ``repr``
(single-quoted) instead of ``json.dumps`` makes ``json.loads`` raise.

Pure unit (no DB) — ``_eval_config_output`` only reads
``cfg.eval_template.config["output"]``, so a lightweight stub stands in for the
ORM object, same as ``test_eval_dual_write.py``. The persisted-row ("Bonus")
integration check belongs with the schema suite in ``test_eval_logger_schema.py``.
"""

import json
from types import SimpleNamespace

# Break the import cycle (tracer.utils.eval_tasks -> tracer.utils.eval ->
# model_hub.tasks.__init__ -> tracer.utils.eval_tasks). See
# test_eval_dual_write.py / test_eval_logger_schema.py for the canonical note.
import model_hub.tasks  # noqa: F401
from tracer.utils.eval import (  # noqa: E402
    _dual_write_eval_value,
    _eval_config_output,
)


def _cfg(output_type):
    """Minimal stand-in for a ``CustomEvalConfig``: ``_eval_config_output`` only
    reads ``.eval_template.config["output"]``."""
    return SimpleNamespace(
        eval_template=SimpleNamespace(config={"output": output_type})
    )


def _route(value, output_type):
    """Run the EXACT tail composition the dispatch functions use:
    ``_dual_write_eval_value(value, _eval_config_output(cfg), logger_kwargs)``."""
    logger_kwargs = {}
    _dual_write_eval_value(value, _eval_config_output(_cfg(output_type)), logger_kwargs)
    return logger_kwargs


# ── _eval_config_output resolves the stored type off a real config shape ─────


def test_eval_config_output_reads_stored_output_type():
    assert _eval_config_output(_cfg("choices")) == "choices"
    assert _eval_config_output(_cfg("score")) == "score"


def test_eval_config_output_defaults_to_score_when_missing():
    cfg = SimpleNamespace(eval_template=SimpleNamespace(config={}))
    assert _eval_config_output(cfg) == "score"


# ── dict / list result → output_str is valid JSON through the dispatch path ──


def test_score_dict_routes_to_valid_json_output_str():
    kw = _route({"score": 0.7, "choice": "Choice 1"}, "score")
    # TH-4903 bug class: a single-quoted Python repr would make json.loads raise.
    assert json.loads(kw["output_str"]) == {"score": 0.7, "choice": "Choice 1"}
    assert kw["output_float"] == 0.7


def test_choices_dict_routes_to_valid_json_output_str():
    kw = _route({"score": 0.7, "choice": "Choice 1"}, "choices")
    assert json.loads(kw["output_str"]) == {"score": 0.7, "choice": "Choice 1"}
    assert kw["output_str_list"] == ["Choice 1"]


def test_choices_list_of_dicts_routes_to_valid_json_output_str():
    kw = _route([{"choice": "A"}, {"choice": "B"}], "choices")
    assert json.loads(kw["output_str"]) == [{"choice": "A"}, {"choice": "B"}]
    assert kw["output_str_list"] == ["A", "B"]


# ── Cross-cutting bug-class guard ────────────────────────────────────────────


def test_structured_values_never_stored_as_python_repr():
    """Any dict/list routed on a structured output type yields an ``output_str``
    that ``json.loads`` can parse — never a Python repr."""
    cases = [
        ({"score": 0.1, "choice": "A"}, "choices"),
        ({"choices": ["A", "B"]}, "choices"),
        ([{"choice": "A"}, {"choice": "B"}], "choices"),
        ({"score": 0.5, "choice": "B"}, "score"),
    ]
    for value, output_type in cases:
        kw = _route(value, output_type)
        if "output_str" in kw:
            json.loads(kw["output_str"])  # must not raise
