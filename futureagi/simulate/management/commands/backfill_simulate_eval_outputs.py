"""Backfill ``output_scalar`` / ``output_dict`` on existing
``CallExecution.eval_outputs`` rows.

Forward-only, idempotent. Mirrors the flag surface of PR #618's
``backfill_eval_logger_dual_format`` so operators have one mental model:
``--dry-run``, ``--limit``, ``--batch-size``, ``--since``, plus scoped
``--test-execution-id`` / ``--eval-config-id`` filters.

Skips:

* Rows whose ``eval_outputs`` is empty.
* Per-eval entries that already carry the ``output_scalar`` key (idempotent
  on re-run).

For each repair-able entry, looks up the ``SimulateEvalConfig`` by id (cached
per command run) to read the **stored** ``eval_template.config["output"]``,
then re-derives ``output_scalar`` and ``output_dict`` via
``evaluations.engine.normalize.{coerce_to_legacy_scalar, eval_config_output}``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from evaluations.engine.normalize import (
    coerce_to_legacy_scalar,
    eval_config_output,
)
from simulate.models.eval_config import SimulateEvalConfig
from simulate.models.test_execution import CallExecution

logger = structlog.get_logger(__name__)


class Command(BaseCommand):
    help = (
        "Backfill output_scalar / output_dict on CallExecution.eval_outputs "
        "rows that pre-date TH-6044."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of CallExecution rows to process (0 = no limit).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Bulk-update batch size.",
        )
        parser.add_argument(
            "--since",
            type=str,
            default=None,
            help=(
                "Only consider call executions created on/after this date (YYYY-MM-DD)."
            ),
        )
        parser.add_argument(
            "--test-execution-id",
            type=str,
            default=None,
            help="Restrict to one test_execution_id.",
        )
        parser.add_argument(
            "--eval-config-id",
            type=str,
            default=None,
            help=(
                "Restrict to entries keyed by this eval_config_id. Other entries "
                "in the same CallExecution are left untouched."
            ),
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        limit: int = options["limit"]
        batch_size: int = options["batch_size"]
        since_raw: str | None = options.get("since")
        test_execution_id: str | None = options.get("test_execution_id")
        eval_config_filter: str | None = options.get("eval_config_id")

        since: datetime | None = None
        if since_raw:
            try:
                since = datetime.strptime(since_raw, "%Y-%m-%d").replace(
                    tzinfo=timezone.get_current_timezone()
                )
            except ValueError as exc:
                raise CommandError(
                    f"--since must be YYYY-MM-DD, got {since_raw!r}"
                ) from exc

        qs = CallExecution.objects.exclude(eval_outputs=None).exclude(eval_outputs={})
        if since is not None:
            qs = qs.filter(created_at__gte=since)
        if test_execution_id:
            qs = qs.filter(test_execution_id=test_execution_id)
        qs = qs.order_by("created_at", "id")
        if limit:
            qs = qs[:limit]

        config_output_cache: dict[str, str] = {}
        processed = 0
        updated_rows = 0
        updated_entries = 0
        skipped_entries = 0
        pending: list[CallExecution] = []

        for call in qs.iterator(chunk_size=batch_size):
            processed += 1
            blob: dict[str, Any] = call.eval_outputs or {}
            row_changed = False
            for eval_id, entry in list(blob.items()):
                if not isinstance(entry, dict):
                    continue
                if eval_config_filter and eval_id != eval_config_filter:
                    continue
                if "output_scalar" in entry:
                    skipped_entries += 1
                    continue

                config_output = self._resolve_config_output(
                    eval_id, config_output_cache
                )
                output_value = entry.get("output")
                entry["output_scalar"] = coerce_to_legacy_scalar(
                    output_value, config_output
                )
                entry["output_dict"] = (
                    output_value if isinstance(output_value, dict) else None
                )
                blob[eval_id] = entry
                row_changed = True
                updated_entries += 1

            if not row_changed:
                continue

            call.eval_outputs = blob
            updated_rows += 1
            pending.append(call)
            if len(pending) >= batch_size:
                self._flush(pending, dry_run=dry_run)
                pending.clear()

        if pending:
            self._flush(pending, dry_run=dry_run)
            pending.clear()

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
