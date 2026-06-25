"""Backfill the per-axis filter keys on ``CallExecution.eval_outputs`` rows."""

from __future__ import annotations

import json
from typing import Any

import structlog
from django.core.management.base import BaseCommand
from django.db import transaction

from evaluations.engine.normalize import (
    AXIS_KEYS,
    eval_config_output,
    resolve_eval_axes,
)
from simulate.models.eval_config import SimulateEvalConfig
from simulate.models.test_execution import CallExecution

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 500
_SAMPLE_COUNT = 5


class Command(BaseCommand):
    help = (
        "Backfill output_pass / output_score / output_choices "
        "on CallExecution.eval_outputs rows."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        limit: int = options["limit"]
        samples: list[dict[str, Any]] = []

        qs = (
            CallExecution.objects.exclude(eval_outputs=None)
            .exclude(eval_outputs={})
            .order_by("created_at", "id")
        )
        if limit:
            qs = qs[:limit]

        eval_cfg_cache: dict[str, str] = {}
        processed = 0
        updated_rows = 0
        updated_entries = 0
        skipped_entries = 0
        pending: list[CallExecution] = []

        for call in qs.iterator(chunk_size=_BATCH_SIZE):
            processed += 1
            blob: dict[str, Any] = call.eval_outputs or {}
            row_changed = False
            for eval_id, entry in list(blob.items()):
                if not isinstance(entry, dict):
                    continue
                if all(k in entry for k in AXIS_KEYS):
                    skipped_entries += 1
                    continue

                config_output = self._resolve_config_output(eval_id, eval_cfg_cache)
                axes = resolve_eval_axes(entry.get("output"), config_output)
                if (
                    len(samples) < _SAMPLE_COUNT
                    and entry.get("output") is not None
                    and any(v is not None for v in axes.values())
                ):
                    samples.append(
                        {
                            "call_execution_id": str(call.id),
                            "eval_config_id": eval_id,
                            "config_output": config_output,
                            "output_value": entry.get("output"),
                            "before_axes": {k: entry.get(k) for k in AXIS_KEYS},
                            "after_axes": axes,
                        }
                    )
                entry_changed = False
                for key, axis_value in axes.items():
                    if key not in entry:
                        entry[key] = axis_value
                        entry_changed = True
                if not entry_changed:
                    skipped_entries += 1
                    continue
                blob[eval_id] = entry
                row_changed = True
                updated_entries += 1

            if not row_changed:
                continue

            call.eval_outputs = blob
            updated_rows += 1
            pending.append(call)
            if len(pending) >= _BATCH_SIZE:
                self._flush(pending, dry_run=dry_run)
                pending.clear()

        if pending:
            self._flush(pending, dry_run=dry_run)
            pending.clear()

        if samples:
            self.stdout.write(f">>> --- Sample conversions ({len(samples)}) ---")
            for i, s in enumerate(samples, 1):
                self.stdout.write(f">>> [{i}] call_execution_id={s['call_execution_id']}")
                self.stdout.write(f">>>     eval_config_id   ={s['eval_config_id']}")
                self.stdout.write(f">>>     config_output    ={s['config_output']!r}")
                self.stdout.write(f">>>     runner_output    ={json.dumps(s['output_value'])}")
                self.stdout.write(f">>>     before_axes      ={json.dumps(s['before_axes'])}")
                self.stdout.write(f">>>     after_axes       ={json.dumps(s['after_axes'])}")

        self.stdout.write(
            self.style.SUCCESS(
                f"processed={processed} updated_rows={updated_rows} "
                f"updated_entries={updated_entries} skipped_entries={skipped_entries} "
                f"dry_run={dry_run}"
            )
        )
        logger.info(
            "backfill_simulate_eval_outputs_done",
            processed=processed,
            updated_rows=updated_rows,
            updated_entries=updated_entries,
            skipped_entries=skipped_entries,
            dry_run=dry_run,
        )

    @staticmethod
    def _resolve_config_output(eval_id: str, cache: dict[str, str]) -> str:
        cached = cache.get(eval_id)
        if cached is not None:
            return cached
        try:
            cfg = (
                SimulateEvalConfig.objects.select_related("eval_template")
                .only("id", "eval_template__config")
                .get(id=eval_id)
            )
        except SimulateEvalConfig.DoesNotExist:
            resolved = "score"
        else:
            resolved = eval_config_output(cfg)
        cache[eval_id] = resolved
        return resolved

    @staticmethod
    def _flush(rows: list[CallExecution], *, dry_run: bool) -> None:
        if dry_run or not rows:
            return
        with transaction.atomic():
            CallExecution.objects.bulk_update(rows, ["eval_outputs"])
