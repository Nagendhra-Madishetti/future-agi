"""Unit tests for the ground-truth retrieval service helpers.

These exercise the pure-Python helpers (mapping signatures, embedding
text shape, query-text construction, few-shot formatting, output-type
validation). They run without a database or external services.
"""

from __future__ import annotations

import pytest

from model_hub.utils.ground_truth_retrieval import (
    EMBED_MODEL_IMAGE_TEXT,
    EMBED_MODEL_TEXT,
    _collect_mapped_columns,
    _format_conversational,
    _format_structured,
    _format_xml,
    build_query_text,
    compute_query_embedding,
    compute_row_embedding,
    cosine_similarity,
    detect_row_modality,
    detect_value_modality,
    format_few_shot_examples,
    get_label_columns,
    prepare_embedding_text,
    validate_output_value,
)


# ============================================================================
# _collect_mapped_columns
# ============================================================================


def test_collect_mapped_columns_empty_returns_empty_list():
    assert _collect_mapped_columns(None) == []
    assert _collect_mapped_columns({}) == []


def test_collect_mapped_columns_single_value_per_variable():
    assert _collect_mapped_columns(
        {"question": "q_col", "answer": "a_col"}
    ) == ["q_col", "a_col"]


def test_collect_mapped_columns_list_value_explodes_into_columns():
    assert _collect_mapped_columns({"input": ["a", "b"], "ctx": "c"}) == [
        "a",
        "b",
        "c",
    ]


def test_collect_mapped_columns_deduplicates_repeated_columns():
    assert _collect_mapped_columns(
        {"v1": "shared", "v2": "shared", "v3": ["shared", "other"]}
    ) == ["shared", "other"]


# ============================================================================
# get_label_columns
# ============================================================================


def test_get_label_columns_returns_empty_when_no_mapping():
    assert get_label_columns(None) == ("", "")
    assert get_label_columns({}) == ("", "")


def test_get_label_columns_canonical_keys():
    out, expl = get_label_columns(
        {"output": "out_col", "explanation": "expl_col"}
    )
    assert out == "out_col"
    assert expl == "expl_col"


def test_get_label_columns_legacy_keys_accepted_for_back_compat():
    out, expl = get_label_columns(
        {"expected_output": "legacy_out", "reasoning": "legacy_expl"}
    )
    assert out == "legacy_out"
    assert expl == "legacy_expl"


def test_get_label_columns_canonical_wins_over_legacy():
    out, _ = get_label_columns(
        {"output": "new", "expected_output": "old"}
    )
    assert out == "new"


def test_get_label_columns_explanation_is_optional():
    out, expl = get_label_columns({"output": "col"})
    assert out == "col"
    assert expl == ""


def test_get_label_columns_list_value_picks_first():
    out, _ = get_label_columns({"output": ["primary", "secondary"]})
    assert out == "primary"


# ============================================================================
# prepare_embedding_text
# ============================================================================


def test_prepare_embedding_text_uses_only_mapped_input_columns():
    row = {
        "question": "What is 2+2?",
        "answer": "4",
        "score": 1.0,
        "explanation": "correct",
    }
    variable_mapping = {"q": "question", "a": "answer"}
    text = prepare_embedding_text(row, variable_mapping)
    assert "What is 2+2?" in text
    assert "4" in text
    # Labels never appear in the embedded text
    assert "1.0" not in text
    assert "correct" not in text


def test_prepare_embedding_text_falls_back_to_full_row_when_no_mapping():
    row = {"x": "a", "y": "b"}
    text = prepare_embedding_text(row, None)
    assert "x: a" in text
    assert "y: b" in text


def test_prepare_embedding_text_skips_empty_values():
    row = {"q": "alpha", "blank": "", "null": None, "whitespace": "   "}
    text = prepare_embedding_text(row, {"v1": "q", "v2": "blank", "v3": "null"})
    assert "alpha" in text
    assert "blank" not in text


def test_prepare_embedding_text_handles_multi_column_value():
    row = {"col_a": "alpha", "col_b": "beta"}
    text = prepare_embedding_text(row, {"combined": ["col_a", "col_b"]})
    assert "alpha" in text and "beta" in text


# ============================================================================
# build_query_text
# ============================================================================


def test_build_query_text_string_input_passes_through_trimmed():
    assert build_query_text("  hello  ", {"v": "col"}) == "hello"


def test_build_query_text_returns_empty_for_empty_inputs():
    assert build_query_text(None, {"v": "col"}) == ""
    assert build_query_text({}, {"v": "col"}) == ""


def test_build_query_text_aligns_runtime_keys_to_gt_columns():
    inputs = {"question": "what?", "context": "abc"}
    variable_mapping = {"question": "q_col", "context": "ctx_col"}
    text = build_query_text(inputs, variable_mapping)
    assert "q_col: what?" in text
    assert "ctx_col: abc" in text


def test_build_query_text_falls_back_to_column_key_when_runtime_uses_gt_columns():
    inputs = {"q_col": "what?"}
    variable_mapping = {"question": "q_col"}
    text = build_query_text(inputs, variable_mapping)
    assert "q_col: what?" in text


def test_build_query_text_no_mapping_uses_runtime_keys_as_labels():
    text = build_query_text({"raw": "value"}, None)
    assert "raw: value" in text


# ============================================================================
# format_few_shot_examples
# ============================================================================


@pytest.fixture
def example_row():
    return {"question": "Q1", "answer": "A1", "out": "Pass", "expl": "right"}


def test_format_structured_includes_inputs_output_and_explanation(example_row):
    out = format_few_shot_examples(
        [example_row],
        variable_mapping={"question": "question", "answer": "answer"},
        output_column="out",
        explanation_column="expl",
        injection_format="structured",
    )
    assert "Example 1:" in out
    assert "Question: Q1" in out
    assert "Answer: A1" in out
    assert "Eval Output: Pass" in out
    assert "Eval Output Explanation: right" in out


def test_format_structured_omits_explanation_when_not_mapped(example_row):
    out = format_few_shot_examples(
        [example_row],
        variable_mapping={"question": "question"},
        output_column="out",
        explanation_column="",
    )
    assert "Eval Output: Pass" in out
    assert "Explanation" not in out


def test_format_conversational_shape(example_row):
    out = format_few_shot_examples(
        [example_row],
        variable_mapping={"question": "question"},
        output_column="out",
        explanation_column="expl",
        injection_format="conversational",
    )
    assert "Example 1:" in out
    assert "Expert judgment:" in out
    assert "Pass" in out


def test_format_xml_shape(example_row):
    out = format_few_shot_examples(
        [example_row],
        variable_mapping={"question": "question"},
        output_column="out",
        explanation_column="expl",
        injection_format="xml",
    )
    assert "<reference_examples>" in out
    assert '<example eval_output="Pass">' in out
    assert "<question>Q1</question>" in out
    assert "<eval_output_explanation>right</eval_output_explanation>" in out


def test_format_few_shot_empty_returns_empty():
    assert format_few_shot_examples(
        [], variable_mapping={"v": "col"}, output_column="out"
    ) == ""


# ============================================================================
# validate_output_value
# ============================================================================


@pytest.mark.parametrize("value", ["pass", "Fail", "TRUE", "false", "1", "0", "yes", "No"])
def test_validate_output_pass_fail_accepts_canonical_values(value):
    ok, err = validate_output_value(value, "pass_fail")
    assert ok is True
    assert err is None


def test_validate_output_pass_fail_rejects_invalid():
    ok, err = validate_output_value("Maybe", "pass_fail")
    assert ok is False
    assert "Pass" in (err or "")


@pytest.mark.parametrize("value", [0, 0.0, 0.5, 1.0, "0.75", 1])
def test_validate_output_percentage_accepts_range_values(value):
    ok, err = validate_output_value(value, "percentage")
    assert ok is True, err


@pytest.mark.parametrize("value", [-0.1, 1.5, "abc", ""])
def test_validate_output_percentage_rejects_out_of_range_or_garbage(value):
    ok, _ = validate_output_value(value, "percentage")
    assert ok is False


def test_validate_output_deterministic_accepts_known_choice():
    ok, err = validate_output_value(
        "Yes", "deterministic", choice_scores={"Yes": 1.0, "No": 0.0}
    )
    assert ok is True
    assert err is None


def test_validate_output_deterministic_rejects_unknown_choice():
    ok, err = validate_output_value(
        "Maybe", "deterministic", choice_scores={"Yes": 1.0, "No": 0.0}
    )
    assert ok is False
    assert "Yes" in (err or "")


def test_validate_output_unknown_output_type_is_permissive():
    ok, err = validate_output_value("anything", "freeform")
    assert ok is True
    assert err is None


def test_validate_output_empty_value_rejected_for_any_type():
    for out_type in ("pass_fail", "percentage", "deterministic"):
        ok, _ = validate_output_value(None, out_type)
        assert ok is False


# ============================================================================
# cosine_similarity (sanity)
# ============================================================================


def test_cosine_similarity_identical_vectors_returns_one():
    assert cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_returns_zero():
    assert cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)


def test_cosine_similarity_zero_norm_returns_zero():
    assert cosine_similarity([0, 0, 0], [1, 1, 1]) == 0.0


# ============================================================================
# Modality detection
# ============================================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        ("hello world", "text"),
        ("12345", "text"),
        (None, "text"),
        (42, "text"),
        ([1, 2, 3], "text"),
        ("https://example.com/cat.png", "image"),
        ("https://example.com/CAT.JPG?token=abc", "image"),
        ("http://example.com/foo.gif", "image"),
        ("data:image/png;base64,abc", "image"),
        ("https://example.com/song.mp3", "audio"),
        ("data:audio/wav;base64,abc", "audio"),
        ("https://example.com/doc.pdf", "pdf"),
        ("data:application/pdf;base64,abc", "pdf"),
        ("https://example.com/file.unknownext", "text"),
    ],
)
def test_detect_value_modality(value, expected):
    assert detect_value_modality(value) == expected


def test_detect_row_modality_text_only_returns_text():
    row = {"q": "what?", "a": "answer"}
    assert detect_row_modality(row, {"q": "q", "a": "a"}) == "text"


def test_detect_row_modality_image_promotes_whole_row():
    row = {"q": "what?", "image_col": "https://example.com/x.png"}
    assert (
        detect_row_modality(row, {"q": "q", "image": "image_col"}) == "image"
    )


def test_detect_row_modality_audio_falls_back_to_text():
    # Audio is detected but the row routes through the text path today.
    row = {"audio_col": "https://example.com/x.mp3"}
    assert detect_row_modality(row, {"v": "audio_col"}) == "text"


# ============================================================================
# Multimodal embedding dispatch (with mocked serving client)
# ============================================================================


def test_compute_row_embedding_text_path(monkeypatch):
    calls = []

    def fake_generate_embedding(text):
        calls.append(text)
        return [1.0, 0.0, 0.0]

    monkeypatch.setattr(
        "model_hub.utils.ground_truth_retrieval.generate_embedding",
        fake_generate_embedding,
    )

    row = {"q": "what is 2+2?"}
    model, vec = compute_row_embedding(row, {"question": "q"})
    assert model == EMBED_MODEL_TEXT
    assert vec == [1.0, 0.0, 0.0]
    assert "what is 2+2?" in calls[0]


def test_compute_row_embedding_image_path_averages_per_column(monkeypatch):
    captured = []

    def fake_multi(value):
        captured.append(value)
        # Produce orthogonal vectors so the average is non-trivial
        if "png" in value:
            return [1.0, 0.0]
        return [0.0, 1.0]

    monkeypatch.setattr(
        "model_hub.utils.ground_truth_retrieval._embed_one_value_multimodal",
        fake_multi,
    )

    row = {
        "question": "describe this image",
        "image_col": "https://example.com/cat.png",
    }
    model, vec = compute_row_embedding(
        row, {"question": "question", "image": "image_col"}
    )
    assert model == EMBED_MODEL_IMAGE_TEXT
    assert vec == [0.5, 0.5]
    assert any("describe" in c for c in captured)
    assert any("cat.png" in c for c in captured)


def test_compute_row_embedding_empty_row_returns_none():
    row = {"q": ""}
    _, vec = compute_row_embedding(row, {"v": "q"})
    assert vec is None


def test_compute_query_embedding_text_model(monkeypatch):
    monkeypatch.setattr(
        "model_hub.utils.ground_truth_retrieval.generate_embedding",
        lambda text: [0.5, 0.5, 0.5],
    )
    vec = compute_query_embedding(
        {"question": "hello"},
        {"question": "q_col"},
        EMBED_MODEL_TEXT,
    )
    assert vec == [0.5, 0.5, 0.5]


def test_compute_query_embedding_multimodal_aligns_by_runtime_keys(monkeypatch):
    monkeypatch.setattr(
        "model_hub.utils.ground_truth_retrieval._embed_one_value_multimodal",
        lambda val: [1.0] if "png" in val else [0.0],
    )
    vec = compute_query_embedding(
        {"question": "describe", "image": "https://x.com/c.png"},
        {"question": "q_col", "image": "img_col"},
        EMBED_MODEL_IMAGE_TEXT,
    )
    assert vec == [0.5]


def test_compute_query_embedding_multimodal_falls_back_to_column_keys(monkeypatch):
    """Runtime carries the GT column name (not template variable name)."""
    monkeypatch.setattr(
        "model_hub.utils.ground_truth_retrieval._embed_one_value_multimodal",
        lambda val: [1.0],
    )
    vec = compute_query_embedding(
        {"img_col": "https://x.com/c.png"},
        {"image": "img_col"},
        EMBED_MODEL_IMAGE_TEXT,
    )
    assert vec == [1.0]


def test_compute_query_embedding_returns_none_for_empty_inputs():
    assert (
        compute_query_embedding(None, {"q": "col"}, EMBED_MODEL_TEXT) is None
    )
    assert (
        compute_query_embedding({}, {"q": "col"}, EMBED_MODEL_IMAGE_TEXT)
        is None
    )


# =========================================================================
# has_usable_inputs_for_gt — the eval-runner skip rule
# =========================================================================

import pytest  # noqa: E402

from model_hub.utils.ground_truth_retrieval import (  # noqa: E402
    _is_empty_value,
    has_usable_inputs_for_gt,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),
        ("", True),
        ("   ", True),
        ("\n\t  ", True),
        ([], True),
        ({}, True),
        ((), True),
        (set(), True),
        # Falsy-but-legitimate scalars are NOT empty — they are valid eval inputs.
        (0, False),
        (0.0, False),
        (False, False),
        # Real content
        ("hello", False),
        ("  hello  ", False),
        ([1], False),
        ({"k": "v"}, False),
        (42, False),
    ],
)
def test_is_empty_value(value, expected):
    assert _is_empty_value(value) is expected


def test_has_usable_inputs_false_when_no_variable_mapping():
    """Eval has no variables mapped → skip GT entirely (per the rule: an
    eval that uses root_context / _explore trace and never declares a
    template variable should never get GT injection)."""
    assert has_usable_inputs_for_gt({}, {"question": "hi"}) is False
    assert has_usable_inputs_for_gt(None, {"question": "hi"}) is False


def test_has_usable_inputs_false_when_runtime_inputs_missing():
    assert has_usable_inputs_for_gt({"q": "col"}, None) is False
    assert has_usable_inputs_for_gt({"q": "col"}, {}) is False
    assert has_usable_inputs_for_gt({"q": "col"}, "not a dict") is False


def test_has_usable_inputs_false_when_every_mapped_value_is_empty():
    mapping = {"question": "q_col", "context": "ctx_col"}
    # All mapped vars present at runtime but every value is empty.
    assert (
        has_usable_inputs_for_gt(
            mapping, {"question": "", "context": "   "}
        )
        is False
    )
    assert (
        has_usable_inputs_for_gt(
            mapping, {"question": None, "context": []}
        )
        is False
    )


def test_has_usable_inputs_true_when_any_mapped_value_is_present():
    """One mapped var with a non-empty value is enough to run GT — the
    other unmapped or empty vars don't gate retrieval."""
    mapping = {"question": "q_col", "context": "ctx_col"}
    assert (
        has_usable_inputs_for_gt(
            mapping, {"question": "what time is it", "context": ""}
        )
        is True
    )
    # Falsy-but-legitimate scalars still count.
    assert has_usable_inputs_for_gt({"score": "s_col"}, {"score": 0}) is True
    assert (
        has_usable_inputs_for_gt({"flag": "f_col"}, {"flag": False}) is True
    )


def test_has_usable_inputs_accepts_runtime_keyed_by_gt_column():
    """Legacy callers sometimes pass the runtime inputs keyed by the GT
    column name rather than the template variable. We accept either so
    the gate doesn't mis-skip them."""
    mapping = {"question": "q_col"}
    assert (
        has_usable_inputs_for_gt(mapping, {"q_col": "hello"}) is True
    )


def test_has_usable_inputs_handles_list_mapping():
    """Multi-column mapping (multimodal): if ANY of the column names in
    the list has a non-empty runtime value, the gate opens."""
    mapping = {"input": ["text_col", "image_col"]}
    assert (
        has_usable_inputs_for_gt(
            mapping, {"text_col": "", "image_col": "https://x/y.png"}
        )
        is True
    )
    assert (
        has_usable_inputs_for_gt(
            mapping, {"text_col": "", "image_col": ""}
        )
        is False
    )
