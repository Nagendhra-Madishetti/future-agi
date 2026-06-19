"""Tests for ``evaluations.engine.normalize``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from evaluations.engine.normalize import (
    AXIS_KEYS,
    build_simulate_eval_payload,
    dedupe_preserve_order,
    empty_axes,
    eval_config_multi_choice,
    eval_config_output,
    extract_choice,
    extract_choices,
    extract_pass,
    extract_score,
    resolve_eval_axes,
)


def _custom_eval_config(*, stored_output=None, multi_choice=None):
    config = {"output": stored_output} if stored_output is not None else {}
    template = SimpleNamespace(config=config)
    if multi_choice is not None:
        template.multi_choice = multi_choice
    return SimpleNamespace(eval_template=template)


# ── dedupe_preserve_order ────────────────────────────────────────────────


def test_dedupe_preserves_first_seen_order():
    assert dedupe_preserve_order(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


def test_dedupe_handles_empty():
    assert dedupe_preserve_order([]) == []


# ── AXIS_KEYS + empty_axes ───────────────────────────────────────────────


def test_axis_keys_pinned():
    assert AXIS_KEYS == (
        "output_pass",
        "output_score",
        "output_choice",
        "output_choices",
    )


def test_empty_axes_returns_all_none():
    assert empty_axes() == {
        "output_pass": None,
        "output_score": None,
        "output_choice": None,
        "output_choices": None,
    }


def test_empty_axes_returns_fresh_dict_each_call():
    a = empty_axes()
    a["output_score"] = 1.0
    assert empty_axes()["output_score"] is None


# ── eval_config_output ───────────────────────────────────────────────────


def test_eval_config_output_reads_stored_value():
    assert eval_config_output(_custom_eval_config(stored_output="choices")) == "choices"


def test_eval_config_output_defaults_to_score_when_missing():
    assert eval_config_output(_custom_eval_config()) == "score"


def test_eval_config_output_defaults_when_no_template():
    assert eval_config_output(SimpleNamespace()) == "score"


# ── eval_config_multi_choice ─────────────────────────────────────────────


def test_eval_config_multi_choice_reads_flag():
    assert eval_config_multi_choice(_custom_eval_config(multi_choice=True)) is True
    assert eval_config_multi_choice(_custom_eval_config(multi_choice=False)) is False


def test_eval_config_multi_choice_defaults_false_when_missing():
    assert eval_config_multi_choice(_custom_eval_config()) is False


def test_eval_config_multi_choice_defaults_when_no_template():
    assert eval_config_multi_choice(SimpleNamespace()) is False


# ── extract_score ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        (0.7, 0.7),
        (1, 1.0),
        (0, 0.0),
        ({"score": 0.66, "choice": "always"}, 0.66),
        ({"score": 0, "choice": "x"}, 0.0),
    ],
)
def test_extract_score_extracts(value, expected):
    assert extract_score(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "0.7",
        True,
        False,
        {"choice": "always"},
        {"score": "not-a-number"},
        ["A"],
    ],
)
def test_extract_score_yields_none(value):
    assert extract_score(value) is None


# ── extract_choice ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("always", "always"),
        ({"score": 1.0, "choice": "always"}, "always"),
        ({"choice": "x"}, "x"),
    ],
)
def test_extract_choice_extracts(value, expected):
    assert extract_choice(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        0.7,
        True,
        {"score": 1.0, "choices": ["A", "B"]},
        ["A"],
    ],
)
def test_extract_choice_yields_none(value):
    assert extract_choice(value) is None


# ── extract_choices ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        (["A", "B"], ["A", "B"]),
        (["A", "B", "A"], ["A", "B"]),
        ({"score": 0.5, "choices": ["polite", "concise"]}, ["polite", "concise"]),
        ({"choices": ["A", "B", "A"]}, ["A", "B"]),
    ],
)
def test_extract_choices_extracts(value, expected):
    assert extract_choices(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "always",
        {"score": 1.0, "choice": "always"},
        [],
        {"choices": []},
    ],
)
def test_extract_choices_yields_none_for_unfilterable(value):
    assert extract_choices(value) is None


# ── extract_pass ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        ("Passed", True),
        ("Failed", False),
    ],
)
def test_extract_pass_extracts(value, expected):
    assert extract_pass(value) is expected


@pytest.mark.parametrize("value", [None, 0, 0.7, "yes", "no", ["A"]])
def test_extract_pass_yields_none(value):
    assert extract_pass(value) is None


# ── resolve_eval_axes ────────────────────────────────────────────────────


def test_resolve_axes_pass_fail_routes_to_output_pass_only():
    axes = resolve_eval_axes("Passed", "Pass/Fail")
    assert axes == {
        "output_pass": True,
        "output_score": None,
        "output_choice": None,
        "output_choices": None,
    }


def test_resolve_axes_score_plain_float():
    axes = resolve_eval_axes(0.7, "score")
    assert axes["output_score"] == pytest.approx(0.7)
    assert axes["output_pass"] is None
    assert axes["output_choice"] is None
    assert axes["output_choices"] is None


def test_resolve_axes_score_dict_with_choice_scores():
    """choice_scores templates emit both score and choice; both axes
    populate so the FE can render the choice bubble coloured by score."""
    axes = resolve_eval_axes({"score": 0.66, "choice": "frequently"}, "score")
    assert axes["output_score"] == pytest.approx(0.66)
    assert axes["output_choice"] == "frequently"
    assert axes["output_choices"] is None
    assert axes["output_pass"] is None


def test_resolve_axes_numeric_routes_to_output_score():
    axes = resolve_eval_axes(0.42, "numeric")
    assert axes["output_score"] == pytest.approx(0.42)


def test_resolve_axes_choices_single_plain_string():
    axes = resolve_eval_axes("always", "choices", multi_choice=False)
    assert axes["output_choice"] == "always"
    assert axes["output_choices"] is None
    assert axes["output_score"] is None


def test_resolve_axes_choices_single_dict():
    """Mirror case: choices-config dict carries both; both axes populate."""
    axes = resolve_eval_axes(
        {"score": 1.0, "choice": "always"}, "choices", multi_choice=False
    )
    assert axes["output_choice"] == "always"
    assert axes["output_score"] == pytest.approx(1.0)


def test_resolve_axes_choices_multi_plain_list():
    axes = resolve_eval_axes(["A", "B"], "choices", multi_choice=True)
    assert axes["output_choices"] == ["A", "B"]
    assert axes["output_choice"] is None


def test_resolve_axes_choices_multi_dict_shape():
    axes = resolve_eval_axes(
        {"score": 0.5, "choices": ["polite", "concise"]},
        "choices",
        multi_choice=True,
    )
    assert axes["output_choices"] == ["polite", "concise"]
    assert axes["output_score"] == pytest.approx(0.5)
    assert axes["output_choice"] is None


def test_resolve_axes_reason_yields_all_none():
    assert resolve_eval_axes("free-form text", "reason") == empty_axes()


def test_resolve_axes_none_value_yields_all_none():
    assert resolve_eval_axes(None, "score") == empty_axes()
    assert resolve_eval_axes(None, "choices", multi_choice=True) == empty_axes()


def test_resolve_axes_permissive_score_dict_populates_both_axes():
    """choice_scores: score-config dict carries both score and choice. Both
    populate so FE can colour the choice bubble by score."""
    axes = resolve_eval_axes({"score": 0.7, "choice": "always"}, "score")
    assert axes["output_score"] == pytest.approx(0.7)
    assert axes["output_choice"] == "always"
    assert axes["output_choices"] is None
    assert axes["output_pass"] is None


def test_resolve_axes_permissive_choices_dict_populates_both_axes():
    """choice_scores: choices-config dict carries both. Both populate."""
    axes = resolve_eval_axes(
        {"score": 0.7, "choice": "frequently"}, "choices", multi_choice=False
    )
    assert axes["output_score"] == pytest.approx(0.7)
    assert axes["output_choice"] == "frequently"


def test_resolve_axes_plain_score_does_not_invent_choice():
    """No dict means no choice — output_choice stays None."""
    axes = resolve_eval_axes(0.42, "score")
    assert axes["output_score"] == pytest.approx(0.42)
    assert axes["output_choice"] is None


def test_resolve_axes_plain_choice_does_not_invent_score():
    """No dict means no score — output_score stays None."""
    axes = resolve_eval_axes("always", "choices", multi_choice=False)
    assert axes["output_choice"] == "always"
    assert axes["output_score"] is None


# ── build_simulate_eval_payload ──────────────────────────────────────────


def test_payload_success_score():
    payload = build_simulate_eval_payload(
        value=0.75,
        config_output="score",
        reason="ok",
        name="eval-a",
        output_type="score",
    )
    assert payload["output"] == 0.75
    assert payload["output_score"] == pytest.approx(0.75)
    assert payload["output_pass"] is None
    assert payload["output_choice"] is None
    assert payload["output_choices"] is None
    assert payload["reason"] == "ok"
    assert payload["name"] == "eval-a"
    assert payload["output_type"] == "score"
    assert "error" not in payload
    assert "status" not in payload
    assert "skipped" not in payload


def test_payload_success_pass_fail():
    payload = build_simulate_eval_payload(
        value="Passed",
        config_output="Pass/Fail",
        name="eval-b",
        output_type="Pass/Fail",
    )
    assert payload["output_pass"] is True
    assert payload["output_score"] is None
    assert payload["output"] == "Passed"


def test_payload_success_choices_single_dict():
    payload = build_simulate_eval_payload(
        value={"score": 1.0, "choice": "always"},
        config_output="choices",
        multi_choice=False,
        name="eval-c",
        output_type="choices",
    )
    assert payload["output_choice"] == "always"
    assert payload["output_choices"] is None
    assert payload["output_score"] == pytest.approx(1.0)
    assert payload["output"] == {"score": 1.0, "choice": "always"}


def test_payload_success_choices_multi_dict():
    payload = build_simulate_eval_payload(
        value={"score": 0.5, "choices": ["polite", "concise"]},
        config_output="choices",
        multi_choice=True,
        name="eval-d",
        output_type="choices",
    )
    assert payload["output_choices"] == ["polite", "concise"]
    assert payload["output_choice"] is None
    assert payload["output_score"] == pytest.approx(0.5)


def test_payload_error_path_all_axes_none():
    payload = build_simulate_eval_payload(
        value=None,
        config_output="score",
        reason="boom",
        name="eval-e",
        output_type="score",
        error="error",
        timestamp="2026-06-19T00:00:00",
    )
    assert payload["output"] is None
    for key in AXIS_KEYS:
        assert payload[key] is None, key
    assert payload["error"] == "error"
    assert payload["timestamp"] == "2026-06-19T00:00:00"


def test_payload_skipped_path_emits_skipped_flag():
    payload = build_simulate_eval_payload(
        value=None,
        config_output="score",
        reason="processing skipped",
        name="eval-f",
        output_type=None,
        status="skipped",
        skipped=True,
    )
    assert payload["status"] == "skipped"
    assert payload["skipped"] is True
    for key in AXIS_KEYS:
        assert payload[key] is None, key


def test_payload_always_carries_canonical_keys():
    payload = build_simulate_eval_payload(
        value=None,
        config_output="score",
    )
    base_keys = {"output", "reason", "output_type", "name", *AXIS_KEYS}
    assert base_keys.issubset(payload.keys())


# ── edge cases: extract_score ────────────────────────────────────────────


def test_extract_score_zero():
    assert extract_score(0) == 0.0
    assert extract_score(0.0) == 0.0


def test_extract_score_negative():
    assert extract_score(-0.5) == pytest.approx(-0.5)


def test_extract_score_int_coerced_to_float():
    result = extract_score(1)
    assert isinstance(result, float)
    assert result == 1.0


def test_extract_score_bool_true_is_not_a_score():
    """``isinstance(True, int)`` is True in Python — must be excluded."""
    assert extract_score(True) is None
    assert extract_score(False) is None


def test_extract_score_string_numeric_not_coerced():
    """String '0.5' is a string, not a number. We do not silently coerce."""
    assert extract_score("0.5") is None


def test_extract_score_dict_with_string_score_field_returns_none():
    assert extract_score({"score": "0.5"}) is None


def test_extract_score_dict_with_bool_score_field_returns_none():
    assert extract_score({"score": True}) is None
    assert extract_score({"score": False}) is None


def test_extract_score_dict_with_none_score_returns_none():
    assert extract_score({"score": None, "choice": "x"}) is None


def test_extract_score_dict_missing_score_key_returns_none():
    assert extract_score({"choice": "always"}) is None


def test_extract_score_empty_dict_returns_none():
    assert extract_score({}) is None


def test_extract_score_nan_and_infinity_pass_through():
    """NaN / inf are valid floats; the helper does not validate ranges."""
    import math

    assert math.isnan(extract_score(float("nan")))
    assert math.isinf(extract_score(float("inf")))


def test_extract_score_does_not_extract_from_list():
    assert extract_score([0.5, 0.6]) is None


def test_extract_score_does_not_extract_from_none():
    assert extract_score(None) is None


# ── edge cases: extract_choice ───────────────────────────────────────────


def test_extract_choice_empty_string_preserved():
    """An empty string is still a string — filter UI may render it as
    'blank'. Caller decides; the helper does not censor."""
    assert extract_choice("") == ""


def test_extract_choice_whitespace_preserved():
    assert extract_choice("   ") == "   "


def test_extract_choice_unicode():
    assert extract_choice("你好") == "你好"


def test_extract_choice_dict_with_none_choice_returns_none():
    assert extract_choice({"choice": None, "score": 0.5}) is None


def test_extract_choice_dict_with_non_string_choice_returns_none():
    assert extract_choice({"choice": 42}) is None
    assert extract_choice({"choice": True}) is None
    assert extract_choice({"choice": ["A"]}) is None


def test_extract_choice_dict_missing_choice_key_returns_none():
    assert extract_choice({"score": 0.5}) is None


def test_extract_choice_does_not_extract_from_number():
    assert extract_choice(0.5) is None
    assert extract_choice(1) is None


def test_extract_choice_does_not_extract_from_list():
    assert extract_choice(["A"]) is None


# ── edge cases: extract_choices ──────────────────────────────────────────


def test_extract_choices_empty_list_returns_none():
    """An empty list has nothing to filter on — treat as unset."""
    assert extract_choices([]) is None


def test_extract_choices_single_element_list():
    assert extract_choices(["only"]) == ["only"]


def test_extract_choices_dedupes_preserving_order():
    assert extract_choices(["A", "B", "A", "C"]) == ["A", "B", "C"]


def test_extract_choices_filters_non_strings():
    """Mixed list: keep strings, drop the rest. None means strict_total
    of strings was empty."""
    assert extract_choices(["A", 1, "B", None]) == ["A", "B"]


def test_extract_choices_list_of_only_non_strings_returns_none():
    assert extract_choices([1, 2, 3]) is None
    assert extract_choices([None, None]) is None


def test_extract_choices_dict_with_empty_choices_list_returns_none():
    assert extract_choices({"choices": []}) is None


def test_extract_choices_dict_with_string_choices_not_a_list_returns_none():
    """choices key carrying a string — not the multi shape."""
    assert extract_choices({"choices": "polite"}) is None


def test_extract_choices_dict_missing_choices_key_returns_none():
    assert extract_choices({"choice": "polite"}) is None


def test_extract_choices_does_not_extract_from_plain_string():
    """A single chosen label is extract_choice's job, not extract_choices."""
    assert extract_choices("polite") is None


def test_extract_choices_does_not_extract_from_number():
    assert extract_choices(0.5) is None


# ── edge cases: extract_pass ─────────────────────────────────────────────


def test_extract_pass_bool_true_false():
    assert extract_pass(True) is True
    assert extract_pass(False) is False


def test_extract_pass_passed_failed_strings():
    assert extract_pass("Passed") is True
    assert extract_pass("Failed") is False


def test_extract_pass_case_sensitive_only_canonical_form():
    """Only the exact canonical strings convert. Lowercase / uppercase
    variants stay None so callers can detect upstream label drift."""
    assert extract_pass("passed") is None
    assert extract_pass("PASSED") is None
    assert extract_pass("pass") is None
    assert extract_pass("fail") is None


def test_extract_pass_int_not_extracted():
    """Integer 1 / 0 are not auto-coerced to True / False."""
    assert extract_pass(1) is None
    assert extract_pass(0) is None


def test_extract_pass_dict_returns_none():
    """Pass/Fail surface emits a scalar, not a dict."""
    assert extract_pass({"output": "Passed"}) is None


def test_extract_pass_none_returns_none():
    assert extract_pass(None) is None


# ── edge cases: resolve_eval_axes ────────────────────────────────────────


def test_resolve_axes_unknown_config_output_yields_all_none():
    """Unknown / future output types must not panic and must not invent
    axes — strict no-op."""
    assert resolve_eval_axes(0.5, "future_type") == empty_axes()
    assert resolve_eval_axes({"score": 0.5}, "") == empty_axes()


def test_resolve_axes_pass_fail_ignores_dict_score_and_choice():
    """Pass/Fail surface only emits Pass/Fail. Even if a dict arrives,
    score/choice must NOT bleed through."""
    axes = resolve_eval_axes({"score": 0.7, "choice": "x"}, "Pass/Fail")
    assert axes["output_pass"] is None
    assert axes["output_score"] is None
    assert axes["output_choice"] is None


def test_resolve_axes_score_dict_choice_only_no_score():
    """Dict carries only choice. Score is None; choice fills the secondary
    axis — FE renders the bubble uncoloured."""
    axes = resolve_eval_axes({"choice": "always"}, "score")
    assert axes["output_score"] is None
    assert axes["output_choice"] == "always"
    assert axes["output_choices"] is None


def test_resolve_axes_choices_dict_score_only_no_choice():
    """Dict carries only score; choice stays None."""
    axes = resolve_eval_axes({"score": 0.7}, "choices", multi_choice=False)
    assert axes["output_score"] == pytest.approx(0.7)
    assert axes["output_choice"] is None


def test_resolve_axes_multi_choices_dict_with_score_populates_both():
    axes = resolve_eval_axes(
        {"score": 0.5, "choices": ["a", "b"]}, "choices", multi_choice=True
    )
    assert axes["output_choices"] == ["a", "b"]
    assert axes["output_score"] == pytest.approx(0.5)
    assert axes["output_choice"] is None


def test_resolve_axes_multi_choices_plain_list_no_score_invented():
    axes = resolve_eval_axes(["a", "b"], "choices", multi_choice=True)
    assert axes["output_choices"] == ["a", "b"]
    assert axes["output_score"] is None


def test_resolve_axes_score_zero_distinguishable_from_none():
    """A score of exactly 0.0 must surface as 0.0, not None — filter UI
    treats them differently (`score >= 0` includes vs excludes the row)."""
    axes = resolve_eval_axes(0.0, "score")
    assert axes["output_score"] == 0.0
    assert axes["output_score"] is not None


def test_resolve_axes_choices_bool_choice_in_dict_does_not_pollute_choice():
    axes = resolve_eval_axes(
        {"choice": True, "score": 0.5}, "choices", multi_choice=False
    )
    assert axes["output_choice"] is None
    assert axes["output_score"] == pytest.approx(0.5)


def test_resolve_axes_idempotent():
    """Running resolve twice with the same inputs gives the same dict —
    the helper has no hidden state."""
    value = {"score": 0.7, "choice": "x"}
    assert resolve_eval_axes(value, "score") == resolve_eval_axes(value, "score")


def test_resolve_axes_empty_dict_value():
    """Dict carrying neither score nor choice nor choices — all axes
    null. No exception."""
    assert resolve_eval_axes({}, "score") == empty_axes()
    assert resolve_eval_axes({}, "choices", multi_choice=True) == empty_axes()
    assert resolve_eval_axes({}, "choices", multi_choice=False) == empty_axes()


# ── edge cases: build_simulate_eval_payload ──────────────────────────────


def test_payload_does_not_mutate_input_value():
    value = {"score": 0.5, "choice": "x"}
    snapshot = dict(value)
    build_simulate_eval_payload(value=value, config_output="score")
    assert value == snapshot


def test_payload_carries_timestamp_when_supplied():
    payload = build_simulate_eval_payload(
        value=0.5,
        config_output="score",
        timestamp="2026-06-19T12:00:00Z",
    )
    assert payload["timestamp"] == "2026-06-19T12:00:00Z"


def test_payload_omits_optional_fields_when_unset():
    payload = build_simulate_eval_payload(value=0.5, config_output="score")
    assert "error" not in payload
    assert "status" not in payload
    assert "skipped" not in payload
    assert "timestamp" not in payload


def test_payload_skipped_path_carries_all_axis_keys():
    payload = build_simulate_eval_payload(
        value=None,
        config_output="choices",
        multi_choice=True,
        skipped=True,
    )
    assert payload["skipped"] is True
    for key in AXIS_KEYS:
        assert key in payload
        assert payload[key] is None
