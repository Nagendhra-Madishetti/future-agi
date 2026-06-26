"""Copy the embedding-vector tables (`feedbacks`, `ground_truths`) from a
non-replicated ``default.<table>`` into a properly replicated home.

Why this exists
---------------
``ClickHouseVectorDB.create_table`` historically emitted
``ENGINE = MergeTree()`` for the vector tables. On a multi-replica cluster
(US production has 3 replicas) that means writes land on whichever pod the
k8s Service routed the connection to, and never reach the other two. Reads
also land on one pod and only see that pod's slice. The bug is silent: no
error, no Sentry event, ~2/3 of rows invisible to any given read.

The engine is now driven by ``CH_VECTOR_REPLICATED``; when set to "true"
``create_table`` emits ``ReplicatedReplacingMergeTree`` with ``ON CLUSTER``.
This command runs the one-time data migration from the legacy non-replicated
table to the new replicated one. See
``_product_docs/evals-end-to-end/33-ch-vector-tables-non-replicated.md``.

When to run
-----------
On staging (single-replica CH): replication has no effect; the command is a
no-op apart from creating the target table. Safe to run anytime.

On production: only after Nikhil's CH 25 cutover creates the ``futureagi``
database AND ``CH_VECTOR_REPLICATED=true`` is set on the deployment.
Otherwise the target table is created in the wrong DB or with the wrong
engine and the migration is wasted work.

What must exist beforehand
--------------------------
1. ``CH_VECTOR_REPLICATED=true`` on the backend deployment so that the
   target table is created with the replicated engine. Without this, the
   command refuses to run.
2. The target database (``--target-database``) must already exist. If it is
   ``default`` that is true on every cluster. If it is ``futureagi`` the
   CH25 cutover must have created it first.

What the command does
---------------------
For each table in ``--tables``:
  1. Verify the source table exists somewhere on the cluster.
  2. Use ``ClickHouseVectorDB.create_table`` to materialise the target
     (idempotent CREATE TABLE IF NOT EXISTS).
  3. ``INSERT INTO target.<table> SELECT * FROM clusterAllReplicas(
        '<cluster>', source.<table>) WHERE id NOT IN
        (SELECT id FROM target.<table>)``.
  4. Verify count parity: target rows >= source distinct-id rows.

Idempotent: a re-run does not duplicate. Resumable: a crash mid-run leaves
the partial INSERT and a follow-up run completes the rest.

Usage
-----
    # Staging dry-run (no engine env, so target is plain MergeTree):
    python manage.py migrate_legacy_vectors_to_replicated --dry-run

    # Production (after CH25 P0): copy default.* into futureagi.* as replicated.
    CH_VECTOR_REPLICATED=true \\
    python manage.py migrate_legacy_vectors_to_replicated \\
        --source-database default \\
        --target-database futureagi \\
        --tables feedbacks,ground_truths
"""

from __future__ import annotations

import os
import time

import structlog
from django.core.management.base import BaseCommand, CommandError

from agentic_eval.core.database.ch_vector import ClickHouseVectorDB
from agentic_eval.core.embeddings.embedding_manager import (
    FEEDBACK_TABLE_NAME,
    GROUND_TRUTH_TABLE_NAME,
)
from model_hub.utils.kb_indexer import KB_TABLE_NAME

logger = structlog.get_logger(__name__)


# All non-replicated vector tables that go through ClickHouseVectorDB.create_table:
# - feedbacks: dataset / observe trace feedback embeddings
# - ground_truths: GT exemplar embeddings (PR #871)
# - syn: knowledge-base chunk embeddings (consumed by agent_evaluator's
#        search_knowledge_base tool via ai_tools/tools/web/kb_search.py)
KNOWN_TABLES = (FEEDBACK_TABLE_NAME, GROUND_TRUTH_TABLE_NAME, KB_TABLE_NAME)


class Command(BaseCommand):
    help = (
        "Migrate non-replicated CH vector tables (feedbacks, ground_truths) "
        "into a replicated target. See module docstring for sequencing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-database",
            default=os.getenv("CH_DATABASE") or "default",
            help="CH database holding the legacy non-replicated table.",
        )
        parser.add_argument(
            "--target-database",
            default=None,
            help=(
                "CH database that will hold the replicated copy. "
                "Defaults to source-database (in-place rename pattern)."
            ),
        )
        parser.add_argument(
            "--tables",
            default=",".join(KNOWN_TABLES),
            help=(
                "Comma-separated subset of "
                f"{', '.join(KNOWN_TABLES)}. Default: all."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would happen without inserting any rows.",
        )

    def handle(self, *args, **opts):
        source_db = opts["source_database"]
        target_db = opts["target_database"] or source_db
        cluster = "cluster"
        dry_run = opts["dry_run"]
        tables = [t.strip() for t in opts["tables"].split(",") if t.strip()]

        unknown = [t for t in tables if t not in KNOWN_TABLES]
        if unknown:
            raise CommandError(
                f"--tables contains unknown entries {unknown}. "
                f"Allowed: {', '.join(KNOWN_TABLES)}."
            )

        if source_db == target_db:
            raise CommandError(
                "--source-database and --target-database resolve to the same "
                f"value ({source_db!r}). The target must be a different "
                "database, otherwise the CREATE TABLE IF NOT EXISTS picks up "
                "the existing non-replicated table and no migration happens."
            )

        replicated_env = (os.getenv("CH_VECTOR_REPLICATED") or "").strip().lower()
        if replicated_env != "true" and not dry_run:
            raise CommandError(
                "CH_VECTOR_REPLICATED must be set to 'true' on this process "
                "or the new target tables would be created as plain MergeTree "
                "and the migration would re-create the bug it is meant to fix."
            )

        logger.info(
            "migrate_legacy_vectors_to_replicated_started",
            source_database=source_db,
            target_database=target_db,
            tables=tables,
            dry_run=dry_run,
        )

        db_client = ClickHouseVectorDB()
        total_copied = 0
        for table in tables:
            copied = self._migrate_one_table(
                db_client=db_client,
                table=table,
                source_db=source_db,
                target_db=target_db,
                cluster=cluster,
                dry_run=dry_run,
            )
            total_copied += copied

        logger.info(
            "migrate_legacy_vectors_to_replicated_complete",
            tables=tables,
            total_rows_copied=total_copied,
            dry_run=dry_run,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Tables processed: {tables}. "
                f"Total rows copied: {total_copied}."
            )
        )

    def _migrate_one_table(
        self,
        *,
        db_client: ClickHouseVectorDB,
        table: str,
        source_db: str,
        target_db: str,
        cluster: str,
        dry_run: bool,
    ) -> int:
        source_qualified = f"{source_db}.{table}"
        target_qualified = f"{target_db}.{table}"

        source_exists = db_client.client.execute(
            "SELECT count() FROM system.tables "
            "WHERE database = %(db)s AND name = %(t)s",
            {"db": source_db, "t": table},
        )[0][0]
        if not source_exists:
            logger.info(
                "migrate_skipped_source_missing",
                source=source_qualified,
            )
            self.stdout.write(
                f"  skipped {source_qualified}: source table does not exist"
            )
            return 0

        source_count_row = db_client.client.execute(
            f"SELECT uniqExact(id) FROM clusterAllReplicas("
            f"'{cluster}', {source_qualified})"
        )
        source_distinct_count = source_count_row[0][0] if source_count_row else 0

        if dry_run:
            logger.info(
                "migrate_dry_run_only",
                source=source_qualified,
                target=target_qualified,
                source_distinct_count=source_distinct_count,
            )
            self.stdout.write(
                f"  dry-run: would copy {source_distinct_count} rows from "
                f"{source_qualified} -> {target_qualified}"
            )
            return 0

        original_db = db_client.client.connection.database
        try:
            db_client.client.connection.database = target_db
            db_client.create_table(table)
        finally:
            db_client.client.connection.database = original_db

        target_qualified_for_insert = f"{target_db}.{table}"
        existing_target_count = db_client.client.execute(
            f"SELECT count() FROM {target_qualified_for_insert}"
        )[0][0]

        insert_started = time.monotonic()
        db_client.client.execute(
            f"INSERT INTO {target_qualified_for_insert} "
            f"SELECT * FROM clusterAllReplicas("
            f"'{cluster}', {source_qualified}) "
            f"WHERE id NOT IN (SELECT id FROM {target_qualified_for_insert})"
        )
        insert_elapsed = time.monotonic() - insert_started

        after_target_count = db_client.client.execute(
            f"SELECT count() FROM {target_qualified_for_insert}"
        )[0][0]
        newly_copied = after_target_count - existing_target_count

        parity_ok = after_target_count >= source_distinct_count

        logger.info(
            "migrate_table_complete",
            source=source_qualified,
            target=target_qualified,
            source_distinct_count=source_distinct_count,
            target_count_before=existing_target_count,
            target_count_after=after_target_count,
            newly_copied=newly_copied,
            insert_elapsed_sec=round(insert_elapsed, 3),
            parity_ok=parity_ok,
        )
        if not parity_ok:
            self.stderr.write(
                self.style.WARNING(
                    f"  parity mismatch on {table}: target now has "
                    f"{after_target_count}, source distinct = "
                    f"{source_distinct_count}"
                )
            )
        else:
            self.stdout.write(
                f"  {table}: copied {newly_copied} rows; "
                f"target now {after_target_count}"
            )
        return newly_copied
