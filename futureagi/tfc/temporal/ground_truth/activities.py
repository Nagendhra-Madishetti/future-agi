"""
Temporal activities for ground truth embedding generation.

Generates per-row embeddings for a ground truth dataset so they can be
used for similarity-based retrieval at eval time.
"""

import structlog
from django.db import close_old_connections
from temporalio import activity

from tfc.temporal.ground_truth.types import (
    GenerateEmbeddingsInput,
    GenerateEmbeddingsOutput,
)

logger = structlog.get_logger(__name__)


def _generate_embeddings_sync(ground_truth_id: str) -> dict:
    """
    Synchronous implementation of embedding generation.

    For each row in the ground truth dataset:
    1. Prepare text from role-mapped columns
    2. Generate embedding via serving client
    3. Store in EvalGroundTruthEmbedding
    4. Update progress on parent EvalGroundTruth
    """
    close_old_connections()

    from model_hub.models.evals_metric import EvalGroundTruth, EvalGroundTruthEmbedding
    from model_hub.utils.ground_truth_retrieval import (
        EMBED_MODEL_IMAGE_TEXT,
        EMBED_MODEL_TEXT,
        compute_row_embedding,
        detect_row_modality,
        prepare_embedding_text,
    )

    try:
        gt = EvalGroundTruth.objects.get(id=ground_truth_id, deleted=False)
    except EvalGroundTruth.DoesNotExist:
        return {
            "ground_truth_id": ground_truth_id,
            "rows_embedded": 0,
            "status": "failed",
            "error": "Ground truth not found",
        }

    gt.embedding_status = "processing"
    gt.embedded_row_count = 0
    gt.save(update_fields=["embedding_status", "embedded_row_count", "updated_at"])

    EvalGroundTruthEmbedding.objects.filter(ground_truth=gt).delete()

    data = gt.data or []
    variable_mapping = gt.variable_mapping
    rows_embedded = 0

    # Decide once which embedding model the whole dataset uses (per-row
    # mixing would put vectors in different spaces and break cosine
    # similarity between them). If any row has an image-shaped mapped
    # value the entire dataset embeds via the joint image-text model.
    dataset_modality = EMBED_MODEL_TEXT
    for row in data:
        if detect_row_modality(row, variable_mapping) == "image":
            dataset_modality = EMBED_MODEL_IMAGE_TEXT
            break

    for idx, row in enumerate(data):
        try:
            if dataset_modality == EMBED_MODEL_IMAGE_TEXT:
                model_used, embedding = compute_row_embedding(row, variable_mapping)
                text_for_storage = prepare_embedding_text(row, variable_mapping)
            else:
                text_for_storage = prepare_embedding_text(row, variable_mapping)
                if not text_for_storage.strip():
                    logger.warning(
                        "empty_embedding_text",
                        gt_id=ground_truth_id,
                        row_index=idx,
                    )
                    continue
                model_used, embedding = compute_row_embedding(row, variable_mapping)

            if embedding is None:
                logger.warning(
                    "row_embedding_returned_none",
                    gt_id=ground_truth_id,
                    row_index=idx,
                    model=model_used,
                )
                continue

            EvalGroundTruthEmbedding.objects.create(
                ground_truth=gt,
                row_index=idx,
                text_content=(text_for_storage or "")[:5000],
                embedding=embedding,
                row_data=row,
            )
            rows_embedded += 1

            if rows_embedded % 50 == 0:
                gt.embedded_row_count = rows_embedded
                gt.save(update_fields=["embedded_row_count", "updated_at"])

            activity.heartbeat(f"Embedded {rows_embedded}/{len(data)} rows")

        except Exception as e:
            logger.warning(
                "row_embedding_failed",
                gt_id=ground_truth_id,
                row_index=idx,
                error=str(e),
            )

    gt.embedded_row_count = rows_embedded
    gt.embedding_status = "completed" if rows_embedded > 0 else "failed"
    gt.embedding_model = dataset_modality
    gt.save(
        update_fields=[
            "embedding_status",
            "embedded_row_count",
            "embedding_model",
            "updated_at",
        ]
    )

    return {
        "ground_truth_id": ground_truth_id,
        "rows_embedded": rows_embedded,
        "status": gt.embedding_status,
        "error": None if rows_embedded > 0 else "No rows could be embedded",
    }


@activity.defn
async def generate_ground_truth_embeddings_activity(
    input: GenerateEmbeddingsInput,
) -> GenerateEmbeddingsOutput:
    """
    Temporal activity that generates embeddings for all rows in a ground truth dataset.
    Runs on tasks_xl queue (long-running, uses embedding model).
    """
    logger.info(
        "generate_ground_truth_embeddings_start",
        gt_id=input.ground_truth_id,
    )

    try:
        from tfc.telemetry import otel_sync_to_async

        result = await otel_sync_to_async(_generate_embeddings_sync)(
            input.ground_truth_id
        )

        logger.info(
            "generate_ground_truth_embeddings_done",
            gt_id=input.ground_truth_id,
            rows_embedded=result["rows_embedded"],
            status=result["status"],
        )

        return GenerateEmbeddingsOutput(**result)

    except Exception as e:
        logger.error(
            "generate_ground_truth_embeddings_error",
            gt_id=input.ground_truth_id,
            error=str(e),
        )

        # Mark as failed
        try:
            close_old_connections()
            from model_hub.models.evals_metric import EvalGroundTruth

            gt = EvalGroundTruth.objects.get(id=input.ground_truth_id)
            gt.embedding_status = "failed"
            gt.save(update_fields=["embedding_status", "updated_at"])
        except Exception:
            pass

        return GenerateEmbeddingsOutput(
            ground_truth_id=input.ground_truth_id,
            rows_embedded=0,
            status="failed",
            error=str(e),
        )
