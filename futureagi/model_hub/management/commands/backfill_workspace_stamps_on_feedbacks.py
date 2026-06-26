"""Stamp ``workspace_id`` on existing CH ``feedbacks`` rows that have
``organization_id`` but are missing the workspace stamp.

Why this exists
---------------
Until this PR, ``model_hub/views/separate_evals.py:EvalPlayGroundFeedbackAPIView``
wrote feedback embeddings with a hard-coded ``workspace_id=None``. After this
PR, ``model_hub/views/eval_runner.py:get_few_shot_examples`` filters reads by
the runner's ``workspace_id``. Historical rows that never got the workspace
stamp become invisible to those filtered reads.

This command repairs the existing rows so the new workspace-scoped reader
finds them. Other writers (dataset feedback, observe trace feedback) already
stamped workspace correctly; their rows are not affected by this command.

When to run
-----------
**Immediately after deploy** of this PR on the affected environment. The new
``eval_runner`` reader is workspace-scoped from the moment the code is live;
any minute the backfill is delayed is a minute of legitimate few-shot
exemplars being silently missed by the judge prompt.

On staging: run once. Data volume is tiny; less than a second.
On production: run once per region. US has ~5 affected rows (verified via
clusterAllReplicas during the analysis). EU has 0 (the table is empty there).

What must exist beforehand
--------------------------
1. CH ``default.feedbacks`` (or the table named via ``--source-table``) must
   exist. The command does not create it.
2. PG ``model_hub_feedback`` rows must exist for the source_ids the CH rows
   reference. Without them, the workspace cannot be resolved and the row is
   logged as unresolvable and skipped.

What the command does
---------------------
For each candidate CH row (``organization_id`` present, ``workspace_id``
absent) the command resolves the right workspace via this lookup chain
against PG, in order:
  1. ``Feedback.objects.filter(source_id=eval_id, organization_id=org)``
     - if found and ``feedback.workspace_id`` is set, use it
  2. ``Feedback.<above>.user_eval_metric.workspace_id`` if non-null
  3. ``Feedback.<above>.eval_template.workspace_id`` if non-null
  4. unresolvable -> log and skip (a manual fix is required for that row)

Then runs (per row, batched):
  ``ALTER TABLE <table> ON CLUSTER <cluster>
     UPDATE metadata.key = arrayPushBack(metadata.key, 'workspace_id'),
            metadata.value = arrayPushBack(metadata.value, <ws_id>)
     WHERE id = <row_id> SETTINGS mutations_sync = 2``

Idempotent: rows that already carry ``workspace_id`` are filtered out at the
SELECT step, never touched.

Usage
-----
    # Preview only; no mutations
    python manage.py backfill_workspace_stamps_on_feedbacks --dry-run

    # Apply
    python manage.py backfill_workspace_stamps_on_feedbacks

    # Restrict to one organization (e.g. for piloting before broad rollout)
    python manage.py backfill_workspace_stamps_on_feedbacks \\
        --organization-id <UUID>

    # Target a different CH table (after migrate_legacy_vectors_to_replicated)
    python manage.py backfill_workspace_stamps_on_feedbacks \\
        --source-database futureagi --source-table feedbacks
"""

from __future__ import annotations

import os
from typing import Iterator

import structlog
from django.core.management.base import BaseCommand, CommandError

from agentic_eval.core.database.ch_vector import ClickHouseVectorDB
from agentic_eval.core.embeddings.embedding_manager import FEEDBACK_TABLE_NAME
from model_hub.models.evals_metric import Feedback

logger = structlog.get_logger(__name__)


class Command(BaseCommand):
    help = (
        "Backfill workspace_id onto CH feedbacks rows that have organization_id "
        "stamped but lack workspace_id. See module docstring for sequencing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-database",
            default=os.getenv("CH_DATABASE") or "default",
            help="CH database holding the feedbacks table.",
        )
        parser.add_argument(
            "--source-table",
            default=FEEDBACK_TABLE_NAME,
            help="Table name. Defaults to 'feedbacks'.",
        )
        parser.add_argument(
            "--organization-id",
            default=None,
            help="Optional filter: only repair rows from this org.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of CH rows to scan per loop iteration.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print decisions, run no ALTER.",
        )

    def handle(self, *args, **opts):
        source_db = opts["source_database"]
        source_table = opts["source_table"]
        cluster = "cluster"
        org_filter = opts["organization_id"]
        batch_size = opts["batch_size"]
        dry_run = opts["dry_run"]

        if batch_size <= 0:
            raise CommandError("--batch-size must be positive")

        fq_table = f"{source_db}.{source_table}"

        logger.info(
            "backfill_workspace_stamps_started",
            table=fq_table,
            organization_filter=org_filter,
            batch_size=batch_size,
            dry_run=dry_run,
        )

        db_client = ClickHouseVectorDB()

        total_seen = 0
        total_resolved = 0
        total_unresolvable = 0
        total_already_stamped = 0
        total_failed = 0

        for ch_row in self._iter_candidate_rows(
            db_client=db_client,
            fq_table=fq_table,
            cluster=cluster,
            org_filter=org_filter,
            batch_size=batch_size,
        ):
            total_seen += 1
            row_id = ch_row["id"]
            eval_id = ch_row["eval_id"]
            org_id = ch_row["organization_id"]

            if ch_row["workspace_id_present"]:
                total_already_stamped += 1
                continue

            try:
                resolved_workspace = self._resolve_workspace_for_feedback_row(
                    eval_id=eval_id,
                    organization_id=org_id,
                )
            except Exception as exc:
                total_failed += 1
                logger.warning(
                    "backfill_workspace_resolve_failed",
                    row_id=row_id,
                    eval_id=eval_id,
                    organization_id=org_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue

            if not resolved_workspace:
                total_unresolvable += 1
                logger.warning(
                    "backfill_workspace_unresolvable",
                    row_id=row_id,
                    eval_id=eval_id,
                    organization_id=org_id,
                )
                continue

            if dry_run:
                logger.info(
                    "backfill_workspace_dry_run_would_stamp",
                    row_id=row_id,
                    eval_id=eval_id,
                    organization_id=org_id,
                    workspace_id=resolved_workspace,
                )
                total_resolved += 1
                continue

            try:
                self._stamp_workspace_on_row(
                    db_client=db_client,
                    fq_table=fq_table,
                    cluster=cluster,
                    row_id=row_id,
                    workspace_id=resolved_workspace,
                )
            except Exception as exc:
                total_failed += 1
                logger.warning(
                    "backfill_workspace_stamp_failed",
                    row_id=row_id,
                    eval_id=eval_id,
                    organization_id=org_id,
                    workspace_id=resolved_workspace,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue
            total_resolved += 1
            logger.info(
                "backfill_workspace_stamped",
                row_id=row_id,
                eval_id=eval_id,
                organization_id=org_id,
                workspace_id=resolved_workspace,
            )

        logger.info(
            "backfill_workspace_stamps_complete",
            total_seen=total_seen,
            total_resolved=total_resolved,
            total_unresolvable=total_unresolvable,
            total_already_stamped=total_already_stamped,
            total_failed=total_failed,
            dry_run=dry_run,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. seen={total_seen} resolved={total_resolved} "
                f"unresolvable={total_unresolvable} "
                f"already_stamped={total_already_stamped} "
                f"failed={total_failed} "
                f"(dry_run={dry_run})"
            )
        )

    def _iter_candidate_rows(
        self,
        *,
        db_client: ClickHouseVectorDB,
        fq_table: str,
        cluster: str,
        org_filter: str | None,
        batch_size: int,
    ) -> Iterator[dict]:
        """Yield CH rows that have organization_id stamped.

        We yield BOTH already-stamped and not-yet-stamped rows so the caller
        can report the breakdown; the actual ALTER targets only those whose
        ``workspace_id_present`` is False. The presence-flag is computed in
        SQL so we do not over-fetch metadata into Python.
        """
        # Use clusterAllReplicas so we see every row regardless of which
        # legacy replica it landed on. On a single-replica cluster this is
        # equivalent to a plain table read.
        where_clauses = [
            "has(metadata.key, 'organization_id')",
            "deleted = 0",
        ]
        params: dict[str, str] = {}
        if org_filter:
            where_clauses.append(
                "arrayElement(metadata.value, "
                "indexOf(metadata.key, 'organization_id')) = %(org)s"
            )
            params["org"] = str(org_filter)

        where_sql = " AND ".join(where_clauses)
        cursor_id = "00000000-0000-0000-0000-000000000000"
        while True:
            rows = db_client.client.execute(
                f"""
                SELECT
                    toString(id) AS id,
                    toString(eval_id) AS eval_id,
                    arrayElement(metadata.value, indexOf(metadata.key, 'organization_id')) AS organization_id,
                    has(metadata.key, 'workspace_id') AS workspace_id_present
                FROM clusterAllReplicas('{cluster}', {fq_table})
                WHERE {where_sql} AND toString(id) > %(cursor)s
                ORDER BY toString(id)
                LIMIT {int(batch_size)}
                """,
                {**params, "cursor": cursor_id},
            )
            if not rows:
                return
            for r in rows:
                yield {
                    "id": r[0],
                    "eval_id": r[1],
                    "organization_id": r[2],
                    "workspace_id_present": bool(r[3]),
                }
            cursor_id = rows[-1][0]

    def _resolve_workspace_for_feedback_row(
        self, *, eval_id: str, organization_id: str
    ) -> str | None:
        """Look up workspace_id via PG. Returns the str UUID or None."""
        feedback = (
            Feedback.objects.filter(
                source_id=eval_id,
                organization_id=organization_id,
            )
            .select_related("user_eval_metric", "eval_template")
            .first()
        )
        if not feedback:
            return None

        if feedback.workspace_id:
            return str(feedback.workspace_id)

        uem_workspace_id = getattr(feedback.user_eval_metric, "workspace_id", None)
        if uem_workspace_id:
            return str(uem_workspace_id)

        template_workspace_id = getattr(feedback.eval_template, "workspace_id", None)
        if template_workspace_id:
            return str(template_workspace_id)

        return None

    def _stamp_workspace_on_row(
        self,
        *,
        db_client: ClickHouseVectorDB,
        fq_table: str,
        cluster: str,
        row_id: str,
        workspace_id: str,
    ) -> None:
        db_client.client.execute(
            f"""
            ALTER TABLE {fq_table} ON CLUSTER '{cluster}'
            UPDATE
                metadata.key   = arrayPushBack(metadata.key, 'workspace_id'),
                metadata.value = arrayPushBack(metadata.value, %(ws)s)
            WHERE toString(id) = %(rid)s
            SETTINGS mutations_sync = 2
            """,
            {"ws": str(workspace_id), "rid": str(row_id)},
        )
