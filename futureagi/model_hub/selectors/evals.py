from __future__ import annotations

from model_hub.models.evals_metric import EvalTemplate, UserEvalMetric


def resolve_eval_template_for_column_source_id(
    source_id: str | None,
) -> EvalTemplate | None:
    """Walk ``Column.source_id`` (a ``UserEvalMetric.id``) to its ``EvalTemplate``."""
    if not source_id:
        return None
    try:
        uem = UserEvalMetric.objects.only("template_id").get(id=source_id)
        return EvalTemplate.objects.only("id", "config", "multi_choice").get(
            id=uem.template_id
        )
    except (UserEvalMetric.DoesNotExist, EvalTemplate.DoesNotExist, ValueError):
        return None
