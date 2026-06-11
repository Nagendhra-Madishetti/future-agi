"""
Ground Truth Search tool for AI agent evaluators.

Searches a ground truth dataset using embedding similarity to find
relevant reference examples. Used by AgentEvaluator to access
human-annotated examples during evaluation.
"""

from typing import Any

import structlog
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field

from ai_tools.base import BaseTool, ToolContext, ToolResult
from ai_tools.registry import register_tool

logger = structlog.get_logger(__name__)


class GroundTruthSearchInput(PydanticBaseModel):
    ground_truth_id: str = Field(description="Ground truth dataset ID to search in")
    inputs: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Multi-variable inputs matching the rule prompt's template "
            "variables. Preferred when the rule prompt has more than a single "
            "input variable."
        ),
    )
    query: str = Field(
        default="",
        description=(
            "Free-form text query. Kept as a fallback for single-variable "
            "prompts; prefer ``inputs`` when the rule prompt is multi-variable."
        ),
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of examples to return (default 5)",
    )


@register_tool
class GroundTruthSearchTool(BaseTool):
    name = "search_ground_truth"
    description = (
        "Search the ground truth dataset for relevant reference examples that "
        "have been evaluated by human experts. Returns similar cases with their "
        "labelled eval outputs and explanations. Use this to find calibration "
        "examples when evaluating similar inputs. Prefer the ``inputs`` "
        "parameter (a dict of template variables) for multi-variable prompts."
    )
    category = "web"
    input_model = GroundTruthSearchInput

    def execute(
        self, params: GroundTruthSearchInput, context: ToolContext
    ) -> ToolResult:
        try:
            from model_hub.models.evals_metric import EvalGroundTruth
            from model_hub.utils.ground_truth_retrieval import (
                _log_gt_injection,
                build_query_text,
                compute_query_embedding,
                EMBED_MODEL_TEXT,
                retrieve_similar_examples,
            )

            try:
                gt = EvalGroundTruth.objects.get(
                    id=params.ground_truth_id, deleted=False
                )
            except EvalGroundTruth.DoesNotExist:
                return ToolResult.error(
                    f"Ground truth dataset {params.ground_truth_id} not found."
                )

            current_input = (
                params.inputs
                if params.inputs
                else (params.query or "").strip()
            )

            if not current_input:
                return ToolResult.error(
                    "Provide either a non-empty `query` string or an `inputs` "
                    "dict matching the rule prompt's template variables."
                )

            # Route through the modality-aware embedder so query and
            # stored vectors share the same space (text-only datasets
            # use embed_text; image_text datasets use CLIP joint space).
            query_embedding = compute_query_embedding(
                current_input,
                gt.variable_mapping,
                gt.embedding_model or EMBED_MODEL_TEXT,
            )
            if not query_embedding:
                return ToolResult.error(
                    "Could not embed the query — no usable input values."
                )

            results = retrieve_similar_examples(
                ground_truth_id=params.ground_truth_id,
                query_embedding=query_embedding,
                max_examples=params.max_results,
                similarity_threshold=0.3,
            )

            preview_query = (
                build_query_text(params.inputs, gt.variable_mapping)
                if params.inputs
                else (params.query or "").strip()
            )

            if not results:
                _log_gt_injection(
                    "ground_truth_search_tool_no_results",
                    gt_id=params.ground_truth_id,
                    variable_mapping=gt.variable_mapping,
                    role_mapping=gt.role_mapping,
                    embedding_model=gt.embedding_model,
                    agent_inputs=params.inputs,
                    agent_query=params.query,
                    resolved_query_text=preview_query,
                )
                return ToolResult(
                    output="No relevant ground truth examples found for this query.",
                    metadata={"total_results": 0},
                )

            formatted_parts = [
                f"Found {len(results)} relevant ground truth examples:\n"
            ]
            for i, result in enumerate(results, 1):
                formatted_parts.append(
                    f"--- Example {i} (similarity: {result['similarity']}) ---"
                )
                row_data = result["row_data"]
                for key, value in row_data.items():
                    val_str = str(value)
                    if len(val_str) > 500:
                        val_str = val_str[:500] + "..."
                    formatted_parts.append(f"  {key}: {val_str}")
                formatted_parts.append("")

            output_text = "\n".join(formatted_parts)
            _log_gt_injection(
                "ground_truth_search_tool_invoked",
                gt_id=params.ground_truth_id,
                variable_mapping=gt.variable_mapping,
                role_mapping=gt.role_mapping,
                embedding_model=gt.embedding_model,
                agent_inputs=params.inputs,
                agent_query=params.query,
                resolved_query_text=preview_query,
                total_results=len(results),
                results_preview=results[:3],
                rendered_tool_output=output_text,
            )
            return ToolResult(
                output=output_text,
                metadata={"total_results": len(results)},
            )

        except Exception as e:
            logger.error("ground_truth_search_failed", error=str(e))
            return ToolResult.error(f"Ground truth search failed: {e}")
