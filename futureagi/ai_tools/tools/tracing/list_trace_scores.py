from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field

from ai_tools.base import BaseTool, ToolContext, ToolResult
from ai_tools.formatting import (
    format_datetime,
    format_number,
    markdown_table,
    section,
    truncate,
)
from ai_tools.registry import register_tool


class ListTraceScoresInput(PydanticBaseModel):
    trace_id: Optional[UUID] = Field(
        default=None,
        description="The UUID of the trace to list annotations/scores for",
    )
    observation_span_id: Optional[str] = Field(
        default=None,
        description="Filter by observation span ID",
    )
    annotators: Optional[List[UUID]] = Field(
        default=None,
        description="Include only annotations from these annotator user IDs",
    )
    exclude_annotators: Optional[List[UUID]] = Field(
        default=None,
        description="Exclude annotations from these annotator user IDs",
    )


@register_tool
class ListTraceScoresTool(BaseTool):
    name = "list_trace_scores"
    description = (
        "Lists all annotations/scores for a specific trace, including the annotation "
        "label name, type, value, observation span, and who created it."
    )
    category = "tracing"
    input_model = ListTraceScoresInput

    def execute(self, params: ListTraceScoresInput, context: ToolContext) -> ToolResult:
        # Reads from the unified ``Score`` model (one row per (source, label,
        # annotator) tuple, with a JSON ``value`` field). Pre-deprecation
        # this tool read ``TraceAnnotation``; once Phase 2 deletes the
        # dual-write, that path returns nothing.
        from model_hub.models.score import Score
        from tracer.models.trace import Trace

        if not params.trace_id and not params.observation_span_id:
            return ToolResult.error(
                "Provide at least one of trace_id or observation_span_id.",
                error_code="VALIDATION_ERROR",
            )

        filters = {"deleted": False}
        if params.trace_id:
            try:
                trace = Trace.objects.get(
                    id=params.trace_id,
                    project__organization=context.organization,
                )
            except Trace.DoesNotExist:
                return ToolResult.not_found("Trace", str(params.trace_id))
            # Match scores attached either directly to the trace OR to one
            # of its observation_spans (Score has both source FKs).
            from django.db.models import Q

            org_scope = Q(
                trace=trace, organization=context.organization
            ) | Q(
                observation_span__trace=trace,
                observation_span__project__organization=context.organization,
            )
            scores = Score.objects.filter(org_scope, **filters)
        else:
            scores = Score.objects.none()

        if params.observation_span_id:
            # If both trace_id and observation_span_id are provided, the user
            # means "scores for this specific span on this specific trace" —
            # intersect, don't OR. ORing would surface scores for spans
            # belonging to a DIFFERENT trace under the requested trace's
            # title (codex review finding).
            if params.trace_id:
                scores = scores.filter(
                    observation_span_id=params.observation_span_id,
                )
            else:
                scores = Score.objects.filter(
                    observation_span_id=params.observation_span_id,
                    observation_span__project__organization=context.organization,
                    deleted=False,
                )

        scores = scores.select_related("label", "annotator", "observation_span").order_by(
            "-created_at"
        )

        if params.annotators:
            scores = scores.filter(annotator_id__in=params.annotators)
        if params.exclude_annotators:
            scores = scores.exclude(annotator_id__in=params.exclude_annotators)

        total = scores.count()

        # submit_trace_scores stores trace-level scores as a TraceErrorAnalysis
        # record (the source read by get_trace_error_analysis), NOT as Score
        # rows — so they were invisible here, making list_trace_scores return
        # "No annotations found" right after a successful submit (TH-5405).
        # Surface the latest analysis's per-category scores too.
        analysis_rows = []
        analysis_data = []
        if params.trace_id:
            from tracer.models.trace_error_analysis import TraceErrorAnalysis

            analysis = (
                TraceErrorAnalysis.objects.filter(
                    trace=trace, project__organization=context.organization
                )
                .order_by("-analysis_date")
                .first()
            )
            if analysis:
                _analysis_fields = [
                    ("overall", "overall_score", None),
                    (
                        "factual_grounding",
                        "factual_grounding_score",
                        "factual_grounding_reason",
                    ),
                    (
                        "privacy_and_safety",
                        "privacy_and_safety_score",
                        "privacy_and_safety_reason",
                    ),
                    (
                        "instruction_adherence",
                        "instruction_adherence_score",
                        "instruction_adherence_reason",
                    ),
                    (
                        "optimal_plan_execution",
                        "optimal_plan_execution_score",
                        "optimal_plan_execution_reason",
                    ),
                ]
                for label_name, score_field, reason_field in _analysis_fields:
                    val = getattr(analysis, score_field, None)
                    if val is None:
                        continue
                    reason = (
                        getattr(analysis, reason_field, None) if reason_field else None
                    )
                    analysis_rows.append(
                        [
                            f"`analysis-{label_name}`",
                            label_name,
                            "numeric",
                            format_number(val),
                            "—",
                            "falcon (analysis)",
                            format_datetime(analysis.analysis_date),
                        ]
                    )
                    analysis_data.append(
                        {
                            "id": f"analysis-{analysis.id}-{label_name}",
                            "label_name": label_name,
                            "label_type": "numeric",
                            "value": {"value": val},
                            "reason": reason,
                            "source": "trace_error_analysis",
                            "observation_span_id": None,
                            "annotation_label_id": None,
                        }
                    )

        if not scores and not analysis_data:
            return ToolResult(
                content=section(
                    "Trace Annotations",
                    f"No annotations found for trace `{params.trace_id}`.",
                ),
                data={"annotations": [], "total": 0},
            )

        def _render_value(score):
            """Convert Score.value JSON to the legacy display string."""
            v = score.value or {}
            if not isinstance(v, dict):
                return str(v)
            label_type = score.label.type if score.label else None
            if label_type == "numeric":
                return format_number(v.get("value")) if v.get("value") is not None else "—"
            if label_type == "star":
                return format_number(v.get("rating")) if v.get("rating") is not None else "—"
            if label_type == "thumbs_up_down":
                inner = v.get("value")
                if inner == "up":
                    return "True"
                if inner == "down":
                    return "False"
                return "—"
            if label_type == "categorical":
                sel = v.get("selected") or []
                if not isinstance(sel, list):
                    sel = [sel]
                return ", ".join(str(s) for s in sel[:3]) if sel else "—"
            if label_type == "text":
                return v.get("text") or "—"
            return str(v)

        rows = []
        data_list = []
        for score in scores[:50]:
            label_name = score.label.name if score.label else "—"
            label_type = score.label.type if score.label else "—"

            value = _render_value(score)
            span_id = (
                f"`{str(score.observation_span_id)[:12]}...`"
                if score.observation_span_id
                else "—"
            )
            user_name = (
                score.annotator.email
                if score.annotator
                else (score.score_source or "—")
            )

            rows.append(
                [
                    f"`{score.id}`",
                    label_name,
                    label_type,
                    truncate(str(value), 40),
                    span_id,
                    user_name,
                    format_datetime(score.created_at),
                ]
            )
            data_list.append(
                {
                    "id": str(score.id),
                    "label_name": label_name,
                    "label_type": label_type,
                    "value": score.value,
                    "observation_span_id": (
                        str(score.observation_span_id)
                        if score.observation_span_id
                        else None
                    ),
                    "annotation_label_id": (
                        str(score.label_id) if score.label_id else None
                    ),
                }
            )

        # Append the trace-level analysis scores (submit_trace_scores source).
        rows.extend(analysis_rows)
        data_list.extend(analysis_data)
        combined_total = total + len(analysis_data)

        table = markdown_table(
            ["ID", "Label", "Type", "Value", "Span", "By", "Created"], rows
        )

        content = section(
            f"Annotations for Trace `{str(params.trace_id)}` ({combined_total})",
            table,
        )

        if total > 50:
            content += f"\n\n_Showing 50 of {total} annotations (plus analysis scores)._"

        return ToolResult(
            content=content,
            data={"annotations": data_list, "total": combined_total},
        )
