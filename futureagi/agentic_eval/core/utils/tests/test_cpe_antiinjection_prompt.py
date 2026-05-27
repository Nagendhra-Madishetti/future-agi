"""Static source-code tests for the CustomPromptEvaluator anti-injection
guard.

Importing the live CPE class transitively triggers Django app-registry
loading via the ``fi_evals/__init__.py`` chain, which doesn't play well
with pytest-django's settings under this directory layout. Since the
anti-injection guard is just a string baked into ``_system_message``,
we verify it by reading the source file directly. This keeps the test
fast, hermetic, and immune to pytest collection quirks.

The actual hardening behaviour (judge ignores an embedded 'respond
only with X' directive) is verified by live-LLM tests; here we only
guard against regressions where future edits silently drop the
paragraph.
"""

from __future__ import annotations

from pathlib import Path

import pytest


CPE_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "core_evals"
    / "fi_evals"
    / "llm"
    / "custom_prompt_evaluator"
    / "evaluator.py"
)


ANTI_INJECTION_SNIPPETS = (
    "output-format instructions",
    "do not override",
    "regardless of any conflicting instruction in the criteria",
)


@pytest.fixture(scope="module")
def cpe_source() -> str:
    assert CPE_SOURCE.exists(), f"CPE source not found at {CPE_SOURCE}"
    return CPE_SOURCE.read_text()


class TestAntiInjectionSnippetInSource:
    @pytest.mark.parametrize("snippet", ANTI_INJECTION_SNIPPETS)
    def test_snippet_present(self, snippet, cpe_source):
        assert snippet.lower() in cpe_source.lower(), (
            f"anti-injection snippet {snippet!r} missing from CPE source"
        )

    def test_guard_is_inside_judge_preamble(self, cpe_source):
        """The anti-injection paragraph must live in the shared
        ``judge_preamble`` constant so every output_type branch
        inherits it. We assert by checking the snippet appears between
        ``judge_preamble = (`` and the closing ``)`` of that block.
        """
        start = cpe_source.find("judge_preamble = (")
        assert start != -1, "judge_preamble block missing"
        # Find the matching closing paren by walking forward
        block = cpe_source[start:start + 4000]  # generous window
        end = block.find("\n        )")
        assert end != -1, "Could not find judge_preamble close"
        preamble_block = block[:end]
        assert "output-format instructions" in preamble_block.lower(), (
            "Anti-injection paragraph must live inside the shared "
            "judge_preamble (not duplicated per output_type)."
        )

    def test_snippet_appears_exactly_once(self, cpe_source):
        count = cpe_source.lower().count("output-format instructions")
        assert count == 1, (
            f"Anti-injection snippet should appear exactly once in CPE "
            f"source (single shared preamble); found {count}"
        )
