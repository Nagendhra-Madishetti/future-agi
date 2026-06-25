"""Backfill axis keys inside ``Cell.value_infos`` for eval cells.

Covers all three cell sources that hold eval-row payloads:
``evaluation`` (dataset eval grid), ``experiment_evaluation`` (experiment
eval grid), ``optimisation_evaluation`` (optimisation eval grid).
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from django.core.management.base import BaseCommand
from django.db import transaction

from evaluations.engine.normalize import (
    AXIS_KEYS,
    parse_legacy_value,
    resolve_eval_axes,
)
from model_hub.models.develop_dataset import Cell
from model_hub.models.evals_metric import EvalTemplate, UserEvalMetric

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 500
_SAMPLE_COUNT = 5
_EVAL_CELL_SOURCES = (
    "evaluation",
    "experiment_evaluation",
    "optimisation_evaluation",
)


def _resolve_user_eval_metric_id(source_id: str) -> str:
    """Strip the ``{prefix}-sourceid-`` envelope on experiment / optimisation columns."""
    if "-sourceid-" in source_id:
        return source_id.rsplit("-sourceid-", 1)[-1]
    return source_id


class Command(BaseCommand):
    help = (
        "Backfill axis keys (output_pass / output_score / output_choices) "
        "inside Cell.value_infos for dataset, experiment, and optimisation "
        "eval cells."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        limit: int = options["limit"]
        samples: list[dict[str, Any]] = []

        qs = (
            Cell.objects.exclude(value_infos__isnull=True)
            .exclude(value_infos="")
            .exclude(deleted=True)
            .filter(column__source__in=_EVAL_CELL_SOURCES)
            .select_related("column")
            .order_by("created_at", "id")
        )
        if limit:
            qs = qs[:limit]

        template_cache: dict[str, EvalTemplate | None] = {}

        def _resolve_template(source_id: str | None) -> EvalTemplate | None:
            if not source_id:
                return None
            if source_id in template_cache:
                return template_cache[source_id]
            metric_id = _resolve_user_eval_metric_id(source_id)
            try:
                tpl = (
                    UserEvalMetric.objects.select_related("template")
                    .only("template__id", "template__config", "template__multi_choice")
                    .get(id=metric_id)
                    .template
                )
            except (UserEvalMetric.DoesNotExist, EvalTemplate.DoesNotExist, ValueError):
                tpl = None
            template_cache[source_id] = tpl
            return tpl

        processed = 0
        updated_rows = 0
        skipped_rows = 0
        pending: list[Cell] = []

        for cell in qs.iterator(chunk_size=_BATCH_SIZE):
            processed += 1

            try:
                infos = (
                    json.loads(cell.value_infos)
                    if isinstance(cell.value_infos, str)
                    else dict(cell.value_infos or {})
                )
            except (json.JSONDecodeError, TypeError):
                skipped_rows += 1
                continue
            if not isinstance(infos, dict):
                skipped_rows += 1
                continue
            if all(k in infos for k in AXIS_KEYS):
                skipped_rows += 1
                continue

            tpl = _resolve_template(getattr(cell.column, "source_id", None))
            if tpl is None:
                skipped_rows += 1
                continue
            template_config = tpl.config or {}
            config_output = template_config.get("output") or "score"

            parsed_value = parse_legacy_value(cell.value)
            axes = resolve_eval_axes(parsed_value, config_output)
            before_axes = {k: infos.get(k) for k in AXIS_KEYS}
            for key, axis_value in axes.items():
                infos.setdefault(key, axis_value)
            after_axes = {k: infos.get(k) for k in AXIS_KEYS}

            if len(samples) < _SAMPLE_COUNT:
                samples.append(
                    {
                        "cell_id": str(cell.id),
                        "column_id": str(cell.column_id),
                        "column_source": getattr(cell.column, "source", None),
                        "eval_template_id": str(tpl.id),
                        "config_output": config_output,
                        "value": parsed_value,
                        "before_axes": before_axes,
                        "after_axes": after_axes,
                    }
                )

            cell.value_infos = json.dumps(infos, default=str)
            updated_rows += 1
            pending.append(cell)
            if len(pending) >= _BATCH_SIZE:
                self._flush(pending, dry_run=dry_run)
                pending.clear()

        if pending:
            self._flush(pending, dry_run=dry_run)
            pending.clear()

        if samples:
            self.stdout.write(f">>> --- Sample conversions ({len(samples)}) ---")
            for i, s in enumerate(samples, 1):
                self.stdout.write(f">>> [{i}] cell_id         ={s['cell_id']}")
                self.stdout.write(f">>>     column_id       ={s['column_id']}")
                self.stdout.write(f">>>     column_source   ={s['column_source']}")
                self.stdout.write(f">>>     eval_template_id={s['eval_template_id']}")
                self.stdout.write(f">>>     config_output   ={s['config_output']!r}")
                self.stdout.write(f">>>     value           ={json.dumps(s['value'], default=str)}")
                self.stdout.write(f">>>     before_axes     ={json.dumps(s['before_axes'])}")
                self.stdout.write(f">>>     after_axes      ={json.dumps(s['after_axes'])}")

        self.stdout.write(
            self.style.SUCCESS(
                f"processed={processed} updated_rows={updated_rows} "
                f"skipped_rows={skipped_rows} dry_run={dry_run}"
            )
        )
        logger.info(
            "backfill_cell_eval_axes_done",
            processed=processed,
            updated_rows=updated_rows,
            skipped_rows=skipped_rows,
            dry_run=dry_run,
        )

    @staticmethod
    def _flush(rows: list[Cell], *, dry_run: bool) -> None:
        if dry_run or not rows:
            return
        with transaction.atomic():
            Cell.objects.bulk_update(rows, ["value_infos"])
