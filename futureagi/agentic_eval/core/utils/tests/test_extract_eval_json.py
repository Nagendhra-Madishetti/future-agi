"""Tests for ``extract_eval_json`` — the robust multi-stage JSON extractor."""

from __future__ import annotations

from agentic_eval.core.utils.json_utils import extract_eval_json


class TestDirectExtraction:
    def test_bare_json(self):
        assert extract_eval_json('{"result": "Pass", "explanation": "ok"}') == {
            "result": "Pass",
            "explanation": "ok",
        }

    def test_json_with_surrounding_whitespace(self):
        assert extract_eval_json('  \n  {"result": 0.7}  \n  ') == {"result": 0.7}

    def test_no_result_key_returns_none(self):
        assert extract_eval_json('{"foo": "bar"}') is None


class TestMarkdownFence:
    def test_markdown_json_fence(self):
        content = '```json\n{"result": "Fail", "explanation": "x"}\n```'
        assert extract_eval_json(content) == {"result": "Fail", "explanation": "x"}

    def test_markdown_plain_fence(self):
        content = '```\n{"result": "Pass"}\n```'
        assert extract_eval_json(content) == {"result": "Pass"}

    def test_prose_then_markdown_fence(self):
        content = (
            "Sure! Here is my evaluation:\n\n"
            '```json\n{"result": "Pass", "explanation": "looks good"}\n```\n'
            "Let me know if you need anything else."
        )
        out = extract_eval_json(content)
        assert out == {"result": "Pass", "explanation": "looks good"}


class TestInlineResultRegex:
    def test_inline_json_with_result(self):
        content = 'Analysis complete. {"result": "Pass"} done.'
        assert extract_eval_json(content) == {"result": "Pass"}

    def test_multi_choice_array_inline(self):
        content = 'Picked: {"result": ["joy", "fear"]}'
        out = extract_eval_json(content)
        assert out == {"result": ["joy", "fear"]}


class TestLastJsonFallback:
    def test_last_json_object_wins(self):
        content = (
            'First {"foo": 1} then {"bar": 2}. Final: {"result": "Pass"}'
        )
        assert extract_eval_json(content) == {"result": "Pass"}


class TestNonExtractable:
    def test_empty_string_returns_none(self):
        assert extract_eval_json("") is None

    def test_non_string_returns_none(self):
        assert extract_eval_json(None) is None  # type: ignore[arg-type]
        assert extract_eval_json(123) is None  # type: ignore[arg-type]

    def test_no_json_anywhere_returns_none(self):
        assert extract_eval_json("just some prose with no JSON") is None
