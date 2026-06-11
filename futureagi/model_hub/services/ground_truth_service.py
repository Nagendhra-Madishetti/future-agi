"""Service layer for ground-truth operations.

Views in ``model_hub/views/separate_evals.py`` delegate here so they
stay thin: validate the request, call the service, map the result to a
typed error envelope or success response.

Mirrors the ``ServiceError`` shape used by ``dataset_service`` so the
view-side branching stays consistent across the app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from model_hub.models.evals_metric import EvalGroundTruth, EvalTemplate

logger = structlog.get_logger(__name__)


@dataclass
class ServiceError:
    message: str
    code: str = "ERROR"


class GroundTruthService:
    """Owns the business logic behind the GT REST endpoints.

    Each public method takes the resolved ``EvalGroundTruth`` (or
    ``EvalTemplate``) — the view is responsible for permission/workspace
    resolution via the existing ``_get_accessible_*`` helpers. This keeps
    the service free of DRF request plumbing and trivially unit-testable.
    """

    # ── variable mapping ──────────────────────────────────────────

    @staticmethod
    def update_variable_mapping(
        *,
        gt: EvalGroundTruth,
        variable_mapping: dict[str, Any],
    ) -> dict[str, Any] | ServiceError:
        """Persist ``variable_mapping`` and stale-flag embeddings if changed."""
        bad = _first_missing_column(variable_mapping, gt.columns or [])
        if bad is not None:
            col, key = bad
            return ServiceError(
                f"Column '{col}' (mapped to variable '{key}') not found in "
                f"dataset columns: {gt.columns}",
                code="INVALID_COLUMN",
            )

        mapping_changed = (gt.variable_mapping or {}) != (variable_mapping or {})
        update_fields = ["variable_mapping", "updated_at"]
        gt.variable_mapping = variable_mapping

        embeddings_stale = False
        if mapping_changed and gt.embedding_status == "completed":
            gt.embedding_status = "pending"
            update_fields.append("embedding_status")
            embeddings_stale = True

        gt.save(update_fields=update_fields)
        logger.info(
            "ground_truth_variable_mapping_updated",
            ground_truth_id=str(gt.id),
            embeddings_stale=embeddings_stale,
        )
        return {
            "id": str(gt.id),
            "variable_mapping": gt.variable_mapping,
            "embedding_status": gt.embedding_status,
            "embeddings_stale": embeddings_stale,
        }

    # ── role mapping ──────────────────────────────────────────────

    ALLOWED_ROLE_KEYS = frozenset(
        {"output", "explanation", "expected_output", "reasoning", "reason"}
    )

    @staticmethod
    def update_role_mapping(
        *,
        gt: EvalGroundTruth,
        role_mapping: dict[str, Any],
    ) -> dict[str, Any] | ServiceError:
        """Persist ``role_mapping`` without invalidating embeddings.

        Role-mapped columns (``output`` / ``explanation``) are NOT
        embedded — they're rendered verbatim as labels in the few-shot
        examples at prompt-build time. Changing the mapping just swaps
        which column supplies the label string; the per-row vectors
        produced by ``variable_mapping`` columns stay valid. Compare
        with :meth:`update_variable_mapping`, which DOES stale-flag
        embeddings because its columns drive the embedded text.

        Canonical keys are ``output`` (required at use time) and
        ``explanation`` (optional). Legacy ``expected_output`` /
        ``reasoning`` / ``reason`` keys are accepted for back-compat and
        normalized to the canonical pair at read time elsewhere.
        """
        invalid = {
            r for r in role_mapping if r not in GroundTruthService.ALLOWED_ROLE_KEYS
        }
        if invalid:
            return ServiceError(
                f"Invalid role keys: {sorted(invalid)}. "
                "Allowed keys: output, explanation.",
                code="INVALID_ROLE_KEY",
            )

        bad = _first_missing_column(role_mapping, gt.columns or [], label="role")
        if bad is not None:
            col, key = bad
            return ServiceError(
                f"Column '{col}' (mapped to role '{key}') not found in dataset "
                f"columns: {gt.columns}",
                code="INVALID_COLUMN",
            )

        gt.role_mapping = role_mapping
        gt.save(update_fields=["role_mapping", "updated_at"])
        logger.info(
            "ground_truth_role_mapping_updated",
            ground_truth_id=str(gt.id),
        )
        return {
            "id": str(gt.id),
            "role_mapping": gt.role_mapping,
            "embedding_status": gt.embedding_status,
            # Stale only if a prior variable_mapping change put the
            # dataset into a non-terminal state. Role-mapping changes
            # never set this themselves.
            "embeddings_stale": bool(
                gt.embedded_row_count > 0
                and gt.embedding_status != "completed"
            ),
        }

    # ── search ────────────────────────────────────────────────────

    @staticmethod
    def search(
        *,
        gt: EvalGroundTruth,
        inputs: dict[str, Any] | None,
        query: str | None,
        max_results: int,
        similarity_threshold: float,
    ) -> dict[str, Any] | ServiceError:
        from model_hub.utils.ground_truth_retrieval import (
            EMBED_MODEL_TEXT,
            build_query_text,
            compute_query_embedding,
            retrieve_similar_examples,
        )

        if gt.embedding_status != "completed":
            return ServiceError(
                f"Embeddings not ready. Status: {gt.embedding_status}. "
                "Wait for embedding generation to complete.",
                code="EMBEDDINGS_NOT_READY",
            )

        current_input: dict[str, Any] | str
        if isinstance(inputs, dict) and inputs:
            current_input = inputs
        else:
            stripped = (query or "").strip()
            if not stripped:
                return ServiceError(
                    "Provide either a non-empty `query` string or an `inputs` "
                    "dict matching the rule prompt's template variables.",
                    code="EMPTY_INPUT",
                )
            current_input = stripped

        query_embedding = compute_query_embedding(
            current_input,
            gt.variable_mapping,
            gt.embedding_model or EMBED_MODEL_TEXT,
        )
        if not query_embedding:
            return ServiceError(
                "Could not embed the query — no usable input values.",
                code="EMBED_FAILED",
            )

        results = retrieve_similar_examples(
            ground_truth_id=str(gt.id),
            query_embedding=query_embedding,
            max_examples=max_results,
            similarity_threshold=similarity_threshold,
        )

        preview_query = (
            build_query_text(inputs, gt.variable_mapping)
            if isinstance(inputs, dict) and inputs
            else (query or "").strip()
        )

        return {
            "query": preview_query,
            "inputs": inputs if isinstance(inputs, dict) else None,
            "results": results,
            "total": len(results),
        }

    # ── output validation ─────────────────────────────────────────

    @staticmethod
    def validate_output(
        *,
        template: EvalTemplate,
        value: Any,
    ) -> dict[str, Any]:
        from model_hub.utils.ground_truth_retrieval import validate_output_value

        ok, error = validate_output_value(
            value,
            output_type_normalized=getattr(template, "output_type_normalized", None),
            choice_scores=getattr(template, "choice_scores", None),
            pass_threshold=getattr(template, "pass_threshold", None),
        )
        return {"ok": ok, "error": error or ""}


def _first_missing_column(
    mapping: dict[str, Any],
    available_columns: list[str],
    label: str = "variable",
) -> tuple[str, str] | None:
    """Return the first (column, key) pair whose column isn't in the dataset.

    ``label`` is only used to disambiguate variable vs role in the
    error path; the (column, key) shape is identical either way.
    """
    available = set(available_columns)
    for key, col in (mapping or {}).items():
        for c in col if isinstance(col, list) else [col]:
            if c not in available:
                return c, key
    return None
