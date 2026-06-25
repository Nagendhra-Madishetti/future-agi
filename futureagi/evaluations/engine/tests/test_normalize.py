"""Tests for ``evaluations.engine.normalize``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from evaluations.engine.normalize import (
    AXIS_KEYS,
    empty_axes,
    eval_config_output,
    resolve_eval_axes,
)
from simulate.utils.processing_outcomes import build_simulate_eval_payload


def _custom_eval_config(*, stored_output=None):
    config = {"output": stored_output} if stored_output is not None else {}
    return SimpleNamespace(eval_template=SimpleNamespace(config=config))


def test_empty_axes_returns_fresh_dict_each_call():
    a = empty_axes()
    a["output_float"] = 1.0
    assert empty_axes()["output_float"] is None


# eval_config_output

@pytest.mark.parametrize(
    "cfg,expected",
    [
        (_custom_eval_config(stored_output="choices"), "choices"),
        (_custom_eval_config(), "score"),
        (SimpleNamespace(), "score"),
    ],
)
def test_eval_config_output(cfg, expected):
    assert eval_config_output(cfg) == expected


# resolve_eval_axes: primary axis routing

@pytest.mark.parametrize(
    "value,config_output,axis,expected",
    [
        ("Passed", "Pass/Fail", "output_bool", True),
        (0.7, "score", "output_float", 0.7),
        (0.42, "numeric", "output_float", 0.42),
        ("always", "choices", "output_str_list", ["always"]),
        (["A", "B"], "choices", "output_str_list", ["A", "B"]),
        (["frequently"], "choices", "output_str_list", ["frequently"]),
    ],
)
def test_resolve_axes_routes_to_primary(value, config_output, axis, expected):
    axes = resolve_eval_axes(value, config_output)
    assert axes[axis] == expected
    for other in set(AXIS_KEYS) - {axis}:
        assert axes[other] is None


# resolve_eval_axes: permissive secondary axis (choice_scores templates)

@pytest.mark.parametrize(
    "value,config_output,expected_float,expected_list",
    [
        ({"score": 0.7, "choice": "always"}, "score", 0.7, ["always"]),
        ({"score": 0.7, "choices": ["a", "b"]}, "score", 0.7, ["a", "b"]),
        ({"choice": "always"}, "score", None, ["always"]),
    ],
)
def test_resolve_axes_permissive_dict_populates_both_axes(
    value, config_output, expected_float, expected_list
):
    axes = resolve_eval_axes(value, config_output)
    assert axes["output_float"] == (
        pytest.approx(expected_float) if expected_float is not None else None
    )
    assert axes["output_str_list"] == expected_list


# resolve_eval_axes: edge cases

def test_resolve_axes_reason_yields_all_none():
    assert resolve_eval_axes("free-form text", "reason") == empty_axes()


def test_resolve_axes_pass_fail_does_not_bleed_score_or_choice():
    axes = resolve_eval_axes({"score": 0.7, "choice": "x"}, "Pass/Fail")
    assert axes["output_bool"] is None
    assert axes["output_float"] is None
    assert axes["output_str_list"] is None


@pytest.mark.parametrize("value", [None, {}])
@pytest.mark.parametrize("config_output", ["score", "choices"])
def test_resolve_axes_empty_or_none_value_yields_all_none(value, config_output):
    assert resolve_eval_axes(value, config_output) == empty_axes()


def test_resolve_axes_score_zero_distinguishable_from_none():
    axes = resolve_eval_axes(0.0, "score")
    assert axes["output_float"] == 0.0
    assert axes["output_float"] is not None


# build_simulate_eval_payload

def test_payload_threads_value_reason_name_and_resolved_axes():
    payload = build_simulate_eval_payload(
        value=0.75,
        config_output="score",
        reason="ok",
        name="eval-a",
        output_type="score",
    )
    assert payload["output"] == 0.75
    assert payload["output_float"] == pytest.approx(0.75)
    assert payload["reason"] == "ok"
    assert payload["name"] == "eval-a"
    assert payload["output_type"] == "score"


def test_payload_error_path_all_axes_none():
    payload = build_simulate_eval_payload(
        value=None,
        config_output="score",
        reason="boom",
        name="eval-e",
        output_type="score",
        error="something failed",
        status="error",
    )
    assert payload["error"] == "something failed"
    assert payload["status"] == "error"
    for key in AXIS_KEYS:
        assert payload[key] is None, key


def test_payload_skipped_path_carries_skipped_flag_and_null_axes():
    payload = build_simulate_eval_payload(
        value=None,
        config_output="choices",
        skipped=True,
    )
    assert payload["skipped"] is True
    for key in AXIS_KEYS:
        assert key in payload
        assert payload[key] is None


def test_payload_default_shape_carries_canonical_keys_omits_optional():
    payload = build_simulate_eval_payload(value=0.5, config_output="score")
    assert {"output", "reason", "output_type", "name", *AXIS_KEYS}.issubset(payload.keys())
    assert "error" not in payload
    assert "status" not in payload
    assert "skipped" not in payload
    assert "timestamp" not in payload


def test_payload_does_not_mutate_input_value():
    value = {"score": 0.5, "choice": "x"}
    snapshot = dict(value)
    build_simulate_eval_payload(value=value, config_output="score")
    assert value == snapshot
