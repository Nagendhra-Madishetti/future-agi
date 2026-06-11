"""Unit tests for GroundTruthService.

Covers the business logic moved out of the GT views into the service
layer per the dev-branch "thin view, fat service" rule. Views are now
just request validation + service dispatch, so this is where the rules
that used to live in the views earn their keep.

The tests use a lightweight stand-in for ``EvalGroundTruth`` / ``EvalTemplate``
so they stay pure unit tests — no DB, no fixtures, no service
container. Anything that actually touches the ORM belongs in the
contract-level test (see test_ground_truth_endpoints).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from model_hub.services.ground_truth_service import (
    GroundTruthService,
    ServiceError,
)


@dataclass
class _FakeGT:
    """Stand-in for ``EvalGroundTruth`` honoring the fields the service touches."""

    id: str = "gt-1"
    columns: list[str] = field(default_factory=list)
    variable_mapping: dict[str, Any] = field(default_factory=dict)
    role_mapping: dict[str, Any] = field(default_factory=dict)
    embedding_status: str = "pending"
    embedding_model: str | None = None
    embedded_row_count: int = 0
    save_calls: list[list[str]] = field(default_factory=list)

    def save(self, update_fields=None):
        self.save_calls.append(list(update_fields or []))


@dataclass
class _FakeTemplate:
    output_type_normalized: str | None = None
    choice_scores: dict[str, float] | None = None
    pass_threshold: float | None = None


# ── update_variable_mapping ──────────────────────────────────────


def test_update_variable_mapping_persists_and_flags_no_stale_when_unembedded():
    gt = _FakeGT(columns=["question", "answer"], embedding_status="pending")

    result = GroundTruthService.update_variable_mapping(
        gt=gt, variable_mapping={"q": "question"}
    )

    assert result == {
        "id": "gt-1",
        "variable_mapping": {"q": "question"},
        "embedding_status": "pending",
        "embeddings_stale": False,
    }
    assert gt.variable_mapping == {"q": "question"}
    # No stale flip when nothing has been embedded yet
    assert "embedding_status" not in gt.save_calls[0]


def test_update_variable_mapping_flips_completed_to_pending_when_changed():
    gt = _FakeGT(
        columns=["a", "b"],
        variable_mapping={"x": "a"},
        embedding_status="completed",
    )

    result = GroundTruthService.update_variable_mapping(
        gt=gt, variable_mapping={"x": "b"}
    )

    assert result["embeddings_stale"] is True
    assert gt.embedding_status == "pending"
    assert "embedding_status" in gt.save_calls[0]


def test_update_variable_mapping_idempotent_save_does_not_flag_stale():
    gt = _FakeGT(
        columns=["a"],
        variable_mapping={"x": "a"},
        embedding_status="completed",
    )

    result = GroundTruthService.update_variable_mapping(
        gt=gt, variable_mapping={"x": "a"}
    )

    assert result["embeddings_stale"] is False
    assert gt.embedding_status == "completed"


def test_update_variable_mapping_rejects_unknown_column():
    gt = _FakeGT(columns=["question", "answer"])

    result = GroundTruthService.update_variable_mapping(
        gt=gt, variable_mapping={"q": "nope"}
    )

    assert isinstance(result, ServiceError)
    assert "nope" in result.message
    assert result.code == "INVALID_COLUMN"
    # Nothing should be persisted on the failure path
    assert not gt.save_calls


def test_update_variable_mapping_supports_list_of_columns():
    gt = _FakeGT(columns=["a", "b", "c"])

    result = GroundTruthService.update_variable_mapping(
        gt=gt, variable_mapping={"x": ["a", "b"]}
    )

    assert result["variable_mapping"] == {"x": ["a", "b"]}


def test_update_variable_mapping_rejects_unknown_column_inside_list():
    gt = _FakeGT(columns=["a"])

    result = GroundTruthService.update_variable_mapping(
        gt=gt, variable_mapping={"x": ["a", "missing"]}
    )

    assert isinstance(result, ServiceError)
    assert "missing" in result.message


# ── update_role_mapping ──────────────────────────────────────────


def test_update_role_mapping_canonical_keys_persist():
    gt = _FakeGT(columns=["label", "why"])

    result = GroundTruthService.update_role_mapping(
        gt=gt, role_mapping={"output": "label", "explanation": "why"}
    )

    assert result["role_mapping"] == {"output": "label", "explanation": "why"}
    assert result["embeddings_stale"] is False


def test_update_role_mapping_accepts_legacy_keys():
    gt = _FakeGT(columns=["truth", "reason"])

    result = GroundTruthService.update_role_mapping(
        gt=gt, role_mapping={"expected_output": "truth", "reasoning": "reason"}
    )

    assert not isinstance(result, ServiceError)
    assert gt.role_mapping["expected_output"] == "truth"


def test_update_role_mapping_rejects_unknown_role_key():
    gt = _FakeGT(columns=["a"])

    result = GroundTruthService.update_role_mapping(
        gt=gt, role_mapping={"score": "a"}
    )

    assert isinstance(result, ServiceError)
    assert "score" in result.message
    assert result.code == "INVALID_ROLE_KEY"


def test_update_role_mapping_rejects_unknown_column():
    gt = _FakeGT(columns=["truth"])

    result = GroundTruthService.update_role_mapping(
        gt=gt, role_mapping={"output": "missing"}
    )

    assert isinstance(result, ServiceError)
    assert "missing" in result.message


def test_update_role_mapping_does_not_invalidate_embeddings():
    """Role-mapped columns (output / explanation) feed the prompt as
    labels, not the embedding text. Swapping which column supplies the
    label should NOT force a re-embed of an already-embedded dataset."""
    gt = _FakeGT(
        columns=["a", "b"],
        role_mapping={"output": "a"},
        embedding_status="completed",
    )

    result = GroundTruthService.update_role_mapping(
        gt=gt, role_mapping={"output": "b"}
    )

    assert result["embeddings_stale"] is False
    assert gt.embedding_status == "completed"


# ── search ───────────────────────────────────────────────────────


def test_search_rejects_when_embeddings_not_ready():
    gt = _FakeGT(embedding_status="processing")

    result = GroundTruthService.search(
        gt=gt,
        inputs={"q": "hello"},
        query=None,
        max_results=3,
        similarity_threshold=0.0,
    )

    assert isinstance(result, ServiceError)
    assert result.code == "EMBEDDINGS_NOT_READY"


def test_search_rejects_empty_input():
    gt = _FakeGT(embedding_status="completed", variable_mapping={"q": "col"})

    result = GroundTruthService.search(
        gt=gt, inputs=None, query="   ", max_results=3, similarity_threshold=0.0
    )

    assert isinstance(result, ServiceError)
    assert result.code == "EMPTY_INPUT"


def test_search_dispatches_inputs_path_and_returns_results():
    gt = _FakeGT(
        embedding_status="completed",
        variable_mapping={"q": "question"},
        embedding_model="text_embedding",
    )

    with (
        patch(
            "model_hub.utils.ground_truth_retrieval.compute_query_embedding",
            return_value=[0.1, 0.2],
        ) as mock_embed,
        patch(
            "model_hub.utils.ground_truth_retrieval.retrieve_similar_examples",
            return_value=[{"similarity": 0.9, "row_data": {"question": "x"}}],
        ) as mock_retrieve,
    ):
        result = GroundTruthService.search(
            gt=gt,
            inputs={"q": "hello"},
            query=None,
            max_results=2,
            similarity_threshold=0.5,
        )

    mock_embed.assert_called_once()
    mock_retrieve.assert_called_once()
    assert result["total"] == 1
    assert result["inputs"] == {"q": "hello"}


def test_search_falls_back_to_query_string_when_no_inputs():
    gt = _FakeGT(
        embedding_status="completed",
        variable_mapping={"q": "question"},
        embedding_model="text_embedding",
    )

    with (
        patch(
            "model_hub.utils.ground_truth_retrieval.compute_query_embedding",
            return_value=[0.1],
        ),
        patch(
            "model_hub.utils.ground_truth_retrieval.retrieve_similar_examples",
            return_value=[],
        ),
    ):
        result = GroundTruthService.search(
            gt=gt,
            inputs=None,
            query="hello world",
            max_results=3,
            similarity_threshold=0.0,
        )

    assert result["query"] == "hello world"
    assert result["inputs"] is None


def test_search_returns_error_when_embed_fails():
    gt = _FakeGT(
        embedding_status="completed",
        variable_mapping={"q": "question"},
        embedding_model="text_embedding",
    )

    with patch(
        "model_hub.utils.ground_truth_retrieval.compute_query_embedding",
        return_value=None,
    ):
        result = GroundTruthService.search(
            gt=gt,
            inputs={"q": "hello"},
            query=None,
            max_results=3,
            similarity_threshold=0.0,
        )

    assert isinstance(result, ServiceError)
    assert result.code == "EMBED_FAILED"


# ── validate_output ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected_ok",
    [
        ("Pass", True),
        ("FAIL", True),
        ("garbage", False),
    ],
)
def test_validate_output_uses_template_output_type(value, expected_ok):
    template = _FakeTemplate(output_type_normalized="pass_fail")

    result = GroundTruthService.validate_output(template=template, value=value)

    assert result["ok"] is expected_ok
    assert isinstance(result["error"], str)
