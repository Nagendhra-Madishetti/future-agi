"""Tests for ``evaluations.engine.normalize`` — the helpers shared across
every dual-write writer surface.

``dual_write_eval_value`` is exercised exhaustively by
``tracer/tests/test_eval_dual_write.py``; here we focus on the
simulate-facing helpers (``coerce_to_legacy_scalar`` /
``build_simulate_eval_payload``) plus accessor / dedup utility coverage.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from evaluations.engine.normalize import (
    build_simulate_eval_payload,
    coerce_to_legacy_scalar,
    dedupe_preserve_order,
    eval_config_output,
)

# ── dedupe_preserve_order ────────────────────────────────────────────────


def test_dedupe_preserves_first_seen_order():
    assert dedupe_preserve_order(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


def test_dedupe_handles_empty():
    assert dedupe_preserve_order([]) == []


# ── eval_config_output ───────────────────────────────────────────────────


def _custom_eval_config(stored_output: str | None):
    config = {"output": stored_output} if stored_output is not None else {}
    return SimpleNamespace(eval_template=SimpleNamespace(config=config))


def test_eval_config_output_reads_stored_value():
    cfg = _custom_eval_config("choices")
    assert eval_config_output(cfg) == "choices"


def test_eval_config_output_defaults_to_score_when_missing():
    assert eval_config_output(_custom_eval_config(None)) == "score"


def test_eval_config_output_defaults_when_no_template():
    assert eval_config_output(SimpleNamespace()) == "score"


# ── coerce_to_legacy_scalar — scalar passthrough ─────────────────────────


@pytest.mark.parametrize(
    "value,config_output,expected",
    [
        (None, "score", None),
        (None, "choices", None),
        (True, "Pass/Fail", True),
        (False, "Pass/Fail", False),
        (0.7, "score", 0.7),
        (3, "score", 3),
        ("Choice 1", "choices", "Choice 1"),
        ("Passed", "Pass/Fail", "Passed"),
    ],
)
def test_coerce_passes_scalars_through(value, config_output, expected):
    assert coerce_to_legacy_scalar(value, config_output) == expected


# ── coerce_to_legacy_scalar — score path ─────────────────────────────────


def test_coerce_score_dict_extracts_score_field():
    assert coerce_to_legacy_scalar(
        {"score": 0.7, "choice": "Good"}, "score"
    ) == pytest.approx(0.7)


def test_coerce_score_dict_without_numeric_score_yields_none():
    assert coerce_to_legacy_scalar({"choice": "Good"}, "score") is None


def test_coerce_score_dict_with_zero_is_preserved():
    assert coerce_to_legacy_scalar({"score": 0}, "score") == 0.0


def test_coerce_score_list_averages_numerics():
    assert coerce_to_legacy_scalar([0.4, 0.6, 0.8], "score") == pytest.approx(0.6)


def test_coerce_score_list_of_dicts_averages_score_fields():
    assert coerce_to_legacy_scalar(
        [{"score": 0.4}, {"score": 0.8}], "score"
    ) == pytest.approx(0.6)


def test_coerce_score_empty_list_yields_none():
    assert coerce_to_legacy_scalar([], "score") is None


def test_coerce_score_list_of_bools_excluded_from_mean():
    assert coerce_to_legacy_scalar([True, False, 0.5], "score") == pytest.approx(0.5)


# ── coerce_to_legacy_scalar — choices path ───────────────────────────────


def test_coerce_choices_dict_single_returns_choice_string():
    assert coerce_to_legacy_scalar({"choice": "Good"}, "choices") == "Good"


def test_coerce_choices_dict_multi_returns_json_list():
    assert json.loads(coerce_to_legacy_scalar({"choices": ["A", "B"]}, "choices")) == [
        "A",
        "B",
    ]


def test_coerce_choices_dict_multi_dedupes_before_json_dump():
    assert json.loads(
        coerce_to_legacy_scalar({"choices": ["A", "B", "A"]}, "choices")
    ) == ["A", "B"]


def test_coerce_choices_list_of_strings_returns_json_list():
    assert json.loads(coerce_to_legacy_scalar(["A", "B"], "choices")) == ["A", "B"]


def test_coerce_choices_list_of_dicts_flattens_and_dedupes():
    raw = [{"choice": "A"}, {"choice": "B"}, {"choice": "A"}]
    assert json.loads(coerce_to_legacy_scalar(raw, "choices")) == ["A", "B"]


def test_coerce_choices_dict_neither_field_present_yields_none():
    assert coerce_to_legacy_scalar({"foo": "bar"}, "choices") is None


# ── coerce_to_legacy_scalar — other config_output fallback ───────────────


def test_coerce_other_config_dict_round_trips_as_json():
    assert json.loads(coerce_to_legacy_scalar({"reason": "ok"}, "reason")) == {
        "reason": "ok"
    }


def test_coerce_other_config_list_round_trips_as_json():
    assert json.loads(coerce_to_legacy_scalar([1, 2, 3], "numeric")) == [1, 2, 3]


# ── build_simulate_eval_payload ──────────────────────────────────────────


def test_build_payload_success_score_dict():
    payload = build_simulate_eval_payload(
        value={"score": 0.7, "choice": "Good"},
        config_output="score",
        reason="ok",
        name="my-eval",
        output_type="score",
    )
    assert payload["output"] == {"score": 0.7, "choice": "Good"}
    assert payload["output_scalar"] == pytest.approx(0.7)
    assert payload["output_dict"] == {"score": 0.7, "choice": "Good"}
    assert payload["output_type"] == "score"
    assert payload["reason"] == "ok"
    assert payload["name"] == "my-eval"
    assert "error" not in payload
    assert "status" not in payload
    assert "skipped" not in payload
    assert "timestamp" not in payload


def test_build_payload_success_choices_multi():
    payload = build_simulate_eval_payload(
        value={"choices": ["A", "B"]},
        config_output="choices",
        reason="multi",
        name="categories",
        output_type="choices",
    )
    assert payload["output"] == {"choices": ["A", "B"]}
    assert json.loads(payload["output_scalar"]) == ["A", "B"]
    assert payload["output_dict"] == {"choices": ["A", "B"]}


def test_build_payload_success_choices_single_string():
    payload = build_simulate_eval_payload(
        value="Good",
        config_output="choices",
        reason="single",
        name="category",
        output_type="choices",
    )
    assert payload["output"] == "Good"
    assert payload["output_scalar"] == "Good"
    assert payload["output_dict"] is None


def test_build_payload_error_path_emits_none_scalars():
    payload = build_simulate_eval_payload(
        value=None,
        config_output="score",
        reason="boom",
        name="my-eval",
        output_type="score",
        error="error",
        timestamp="2026-06-19T00:00:00",
    )
    assert payload["output"] is None
    assert payload["output_scalar"] is None
    assert payload["output_dict"] is None
    assert payload["error"] == "error"
    assert payload["timestamp"] == "2026-06-19T00:00:00"


def test_build_payload_skipped_path_emits_skipped_flag():
    payload = build_simulate_eval_payload(
        value=None,
        config_output="score",
        reason="processing skipped",
        name="my-eval",
        output_type=None,
        status="skipped",
        skipped=True,
    )
    assert payload["status"] == "skipped"
    assert payload["skipped"] is True
    assert payload["output_scalar"] is None
    assert payload["output_dict"] is None


def test_build_payload_no_transcript_path_minimal_shape():
    payload = build_simulate_eval_payload(
        value=None,
        config_output="score",
        reason="No transcript data available",
        name="my-eval",
        output_type="score",
    )
    assert payload["output"] is None
    assert payload["output_scalar"] is None
    assert payload["output_dict"] is None
    assert "error" not in payload
    assert "status" not in payload


def test_build_payload_always_carries_canonical_keys():
    payload = build_simulate_eval_payload(
        value=None,
        config_output="score",
        reason="",
        name="",
        output_type=None,
    )
    for key in (
        "output",
        "output_scalar",
        "output_dict",
        "reason",
        "output_type",
        "name",
    ):
        assert key in payload, f"{key} missing"
