"""Backfill the typed output columns on ``Evaluation`` rows."""

from __future__ import annotations

import json
from typing import Any

import structlog
from django.core.management.base import BaseCommand
from django.db import transaction

from evaluations.engine.normalize import parse_legacy_value, resolve_eval_axes
from model_hub.models.evaluation import Evaluation

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 500
_SAMPLE_COUNT = 5
_UPDATE_FIELDS = ["output_bool", "output_float", "output_str_list", "output_str"]


class Command(BaseCommand):
    help = "Backfill output_bool / output_float / output_str_list on Evaluation rows."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        limit: int = options["limit"]
        samples: list[dict[str, Any]] = []

        qs = (
            Evaluation.objects.exclude(value__isnull=True)
            .exclude(value="")
            .select_related("eval_template")
            .order_by("created_at", "id")
        )
        if limit:
            qs = qs[:limit]

        processed = 0
        updated_rows = 0
        skipped_rows = 0
        pending: list[Evaluation] = []

        for ev in qs.iterator(chunk_size=_BATCH_SIZE):
            processed += 1
            tpl = ev.eval_template
            template_config = tpl.config if tpl else {}
            config_output = template_config.get("output") or ev.output_type or "score"

            parsed_value = parse_legacy_value(ev.value)
            projected = resolve_eval_axes(
                parsed_value, config_output, include_output_str=True
            )

            before = {
                "output_bool": ev.output_bool,
                "output_float": ev.output_float,
                "output_str_list": list(ev.output_str_list) if ev.output_str_list else ev.output_str_list,
                "output_str": ev.output_str,
            }
            changed = False
            for col, projected_value in projected.items():
                if projected_value is not None and getattr(ev, col) is None:
                    setattr(ev, col, projected_value)
                    changed = True

            if not changed:
                skipped_rows += 1
                continue

            if len(samples) < _SAMPLE_COUNT:
                samples.append(
                    {
                        "evaluation_id": str(ev.id),
                        "eval_template_id": str(tpl.id) if tpl else None,
                        "config_output": config_output,
                        "value": parsed_value,
                        "before": before,
                        "after": {
                            "output_bool": ev.output_bool,
                            "output_float": ev.output_float,
                            "output_str_list": ev.output_str_list,
                            "output_str": ev.output_str,
                        },
                        "projected": projected,
                    }
                )

            updated_rows += 1
            pending.append(ev)
            if len(pending) >= _BATCH_SIZE:
                self._flush(pending, dry_run=dry_run)
                pending.clear()

        if pending:
            self._flush(pending, dry_run=dry_run)
            pending.clear()

        if samples:
            self.stdout.write(f">>> --- Sample conversions ({len(samples)}) ---")
            for i, s in enumerate(samples, 1):
                self.stdout.write(f">>> [{i}] evaluation_id   ={s['evaluation_id']}")
                self.stdout.write(f">>>     eval_template_id={s['eval_template_id']}")
                self.stdout.write(f">>>     config_output   ={s['config_output']!r}")
                self.stdout.write(f">>>     value           ={json.dumps(s['value'], default=str)}")
                self.stdout.write(f">>>     projected       ={json.dumps(s['projected'], default=str)}")
                self.stdout.write(f">>>     before_columns  ={json.dumps(s['before'], default=str)}")
                self.stdout.write(f">>>     after_columns   ={json.dumps(s['after'], default=str)}")

        self.stdout.write(
            self.style.SUCCESS(
                f"processed={processed} updated_rows={updated_rows} "
                f"skipped_rows={skipped_rows} dry_run={dry_run}"
            )
        )
        logger.info(
            "backfill_evaluation_dual_format_done",
            processed=processed,
            updated_rows=updated_rows,
            skipped_rows=skipped_rows,
            dry_run=dry_run,
        )

    @staticmethod
    def _flush(rows: list[Evaluation], *, dry_run: bool) -> None:
        if dry_run or not rows:
            return
        with transaction.atomic():
            Evaluation.objects.bulk_update(rows, _UPDATE_FIELDS)
