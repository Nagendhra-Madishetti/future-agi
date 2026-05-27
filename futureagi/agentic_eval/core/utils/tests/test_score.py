"""Unit tests for ``agentic_eval.core.utils.score.clamp_unit_score``.

The helper is used by CustomPromptEvaluator and AgentEvaluator only;
non-LLM-judge evaluators (function / deterministic / code /
similarity) never call it, so their numeric outputs are never
clamped. These tests verify the pure clamp behaviour. Eval-type
gating is enforced by the call sites (the evaluators themselves)
and verified in their own test files.
"""

from __future__ import annotations

import math

import pytest

from agentic_eval.core.utils.score import clamp_unit_score


class TestInRange:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0.0, 0.0),
            (0.5, 0.5),
            (1.0, 1.0),
            (0.0001, 0.0001),
            (0.9999, 0.9999),
            (0.123456789, 0.123456789),
        ],
    )
    def test_in_range_passes_through(self, value, expected):
        assert clamp_unit_score(value) == expected


class TestClampAboveOne:
    @pytest.mark.parametrize(
        "value",
        [1.0001, 1.5, 2.0, 5.0, 7.0, 10.0, 100.0, 1e6, float("inf")],
    )
    def test_above_one_clamped_to_one(self, value):
        assert clamp_unit_score(value) == 1.0


class TestClampBelowZero:
    @pytest.mark.parametrize(
        "value",
        [-0.0001, -0.5, -1.0, -100.0, -1e6, float("-inf")],
    )
    def test_below_zero_clamped_to_zero(self, value):
        assert clamp_unit_score(value) == 0.0


class TestIntegerValues:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, 0.0),
            (1, 1.0),
            (2, 1.0),
            (5, 1.0),  # 1-5 scale invitation
            (10, 1.0),  # 1-10 scale invitation
            (-1, 0.0),
            (-100, 0.0),
        ],
    )
    def test_int_coerced_and_clamped(self, value, expected):
        assert clamp_unit_score(value) == expected


class TestStringNumeric:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("0.5", 0.5),
            ("1.0", 1.0),
            ("0", 0.0),
            ("1", 1.0),
            ("0.7", 0.7),
            ("1.5", 1.0),
            ("-0.5", 0.0),
            ("10", 1.0),
        ],
    )
    def test_string_numeric_parsed_and_clamped(self, value, expected):
        assert clamp_unit_score(value) == expected


class TestNone:
    def test_none_passes_through(self):
        assert clamp_unit_score(None) is None


class TestUnparseable:
    @pytest.mark.parametrize(
        "value",
        ["abc", "not a number", "", "1.2.3", "[]", "0,5"],
    )
    def test_unparseable_returns_raw(self, value):
        assert clamp_unit_score(value) == value

    @pytest.mark.parametrize("value", [[], {}, object()])
    def test_non_numeric_objects_returned_raw(self, value):
        assert clamp_unit_score(value) is value


class TestNaN:
    def test_nan_does_not_raise(self):
        result = clamp_unit_score(float("nan"))
        assert result is not None
        assert math.isnan(result) or 0.0 <= result <= 1.0


class TestBool:
    def test_true_becomes_one(self):
        assert clamp_unit_score(True) == 1.0

    def test_false_becomes_zero(self):
        assert clamp_unit_score(False) == 0.0
