"""Unit tests for trace-detail eval-score grouping.

``build_task_grouped_eval_scores`` groups span-level EvalLogger rows into
``eval_task -> eval -> {aggregate, spans}``:
  * root span  -> aggregate + span-wise data across ALL trace spans
  * child span -> same structure scoped to that span only

Per output type the ``aggregate`` is avg% (score), ``{"pass","fail"}`` counts
(Pass/Fail), or ``{label: count}`` zero-filled (Choices); the per-span ``value``
is the raw score / "pass"|"fail" / [labels].
"""

from tracer.utils.helper import build_task_grouped_eval_scores

CONFIG_LOOKUP = {
    "cfg1": {"name": "Eval1", "output": "score", "choices": []},
    "cfg2": {"name": "Eval2", "output": "Pass/Fail", "choices": []},
    "cfg3": {
        "name": "Eval3",
        "output": "choices",
        "choices": ["Pass", "Fail", "Unknown"],
    },
}
TASK_LOOKUP = {"task1": "Eval task1", "task2": "Eval task2"}
SPAN_NAMES = {"SPAN1": "s1", "SPAN2": "s2", "SPAN3": "s3"}


def _row(span, cid, tid, **kw):
    base = {
        "span_id": span,
        "eval_config_id": cid,
        "eval_task_id": tid,
        "output_float": None,
        "output_bool": None,
        "output_str": None,
        "output_str_list": "[]",
        "error": 0,
        "explanation": None,
    }
    base.update(kw)
    return base


def _three_span_rows():
    return [
        _row("SPAN1", "cfg1", "task1", output_float=0.6),
        _row("SPAN2", "cfg1", "task1", output_float=0.8),
        _row("SPAN3", "cfg1", "task1", output_float=0.9),
        _row("SPAN1", "cfg2", "task1", output_bool=0),
        _row("SPAN2", "cfg2", "task1", output_bool=1),
        _row("SPAN3", "cfg2", "task1", output_bool=0),
        _row("SPAN1", "cfg3", "task1", output_str_list='["Pass"]'),
        _row("SPAN2", "cfg3", "task1", output_str_list='["Pass"]'),
        _row("SPAN3", "cfg3", "task1", output_str_list='["Fail"]'),
    ]


def _evals_by_cid(result, task_index=0):
    return {e["eval_config_id"]: e for e in result["eval_tasks"][task_index]["evals"]}


def test_root_aggregates_across_all_spans():
    out = build_task_grouped_eval_scores(
        _three_span_rows(), CONFIG_LOOKUP, TASK_LOOKUP, SPAN_NAMES, "trace"
    )
    assert out["scope"] == "trace"
    assert out["eval_tasks"][0]["eval_task_id"] == "task1"
    assert out["eval_tasks"][0]["eval_task_name"] == "Eval task1"
    evals = _evals_by_cid(out)

    # score -> avg %
    assert evals["cfg1"]["output_type"] == "score"
    assert evals["cfg1"]["aggregate"] == round((0.6 + 0.8 + 0.9) / 3 * 100, 2)
    # pass/fail -> counts
    assert evals["cfg2"]["aggregate"] == {"pass": 1, "fail": 2}
    # choices -> zero-filled counts
    assert evals["cfg3"]["aggregate"] == {"Pass": 2, "Fail": 1, "Unknown": 0}
    # span-wise data covers all three spans
    assert {s["span_id"] for s in evals["cfg1"]["spans"]} == {"SPAN1", "SPAN2", "SPAN3"}


def test_root_span_wise_values_are_raw():
    out = build_task_grouped_eval_scores(
        _three_span_rows(), CONFIG_LOOKUP, TASK_LOOKUP, SPAN_NAMES, "trace"
    )
    evals = _evals_by_cid(out)
    by_span = {s["span_id"]: s for s in evals["cfg2"]["spans"]}
    assert by_span["SPAN1"]["value"] == "fail"
    assert by_span["SPAN2"]["value"] == "pass"
    assert by_span["SPAN2"]["span_name"] == "s2"
    choice_by_span = {s["span_id"]: s["value"] for s in evals["cfg3"]["spans"]}
    assert choice_by_span["SPAN1"] == ["Pass"]
    assert choice_by_span["SPAN3"] == ["Fail"]


def test_child_span_scope_only_that_span():
    rows = [r for r in _three_span_rows() if r["span_id"] == "SPAN1"]
    out = build_task_grouped_eval_scores(
        rows, CONFIG_LOOKUP, TASK_LOOKUP, SPAN_NAMES, "span"
    )
    assert out["scope"] == "span"
    evals = _evals_by_cid(out)
    # Single-span aggregate + single span entry.
    assert evals["cfg2"]["aggregate"] == {"pass": 0, "fail": 1}
    assert len(evals["cfg2"]["spans"]) == 1
    assert evals["cfg2"]["spans"][0]["span_id"] == "SPAN1"
    assert evals["cfg1"]["aggregate"] == 60.0


def test_grouping_separates_eval_tasks():
    rows = [
        _row("SPAN1", "cfg1", "task1", output_float=0.6),
        _row("SPAN1", "cfg1", "task2", output_float=0.9),
    ]
    out = build_task_grouped_eval_scores(
        rows, CONFIG_LOOKUP, TASK_LOOKUP, SPAN_NAMES, "trace"
    )
    tasks = {t["eval_task_id"]: t for t in out["eval_tasks"]}
    assert set(tasks) == {"task1", "task2"}
    assert tasks["task1"]["evals"][0]["aggregate"] == 60.0
    assert tasks["task2"]["evals"][0]["aggregate"] == 90.0


def test_null_eval_task_buckets_under_ungrouped():
    rows = [_row("SPAN1", "cfg1", None, output_float=0.5)]
    out = build_task_grouped_eval_scores(
        rows, CONFIG_LOOKUP, TASK_LOOKUP, SPAN_NAMES, "span"
    )
    assert out["eval_tasks"][0]["eval_task_id"] is None
    assert out["eval_tasks"][0]["eval_task_name"] == "Ungrouped"


def test_errored_rows_excluded_from_aggregate():
    rows = [
        _row("SPAN1", "cfg2", "task1", output_bool=1),
        _row("SPAN2", "cfg2", "task1", output_bool=0, error=1),
        _row("SPAN3", "cfg2", "task1", output_str="ERROR"),
    ]
    out = build_task_grouped_eval_scores(
        rows, CONFIG_LOOKUP, TASK_LOOKUP, SPAN_NAMES, "trace"
    )
    evals = _evals_by_cid(out)
    # Only SPAN1 (pass) counts; the error rows are excluded from the aggregate.
    assert evals["cfg2"]["aggregate"] == {"pass": 1, "fail": 0}
    by_span = {s["span_id"]: s for s in evals["cfg2"]["spans"]}
    assert by_span["SPAN2"]["error"] is True
    assert by_span["SPAN2"]["value"] is None


def test_unknown_config_rows_skipped():
    rows = [_row("SPAN1", "missing_cfg", "task1", output_float=0.5)]
    out = build_task_grouped_eval_scores(
        rows, CONFIG_LOOKUP, TASK_LOOKUP, SPAN_NAMES, "trace"
    )
    assert out["eval_tasks"] == []
