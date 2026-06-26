"""Behavioural tests for ``migrate_legacy_vectors_to_replicated``.

We patch ``ClickHouseVectorDB`` so no real CH is required and observe:
  * Which SQL statements get sent.
  * What the command writes to stdout.
  * Exit conditions (CommandError) for invalid configurations.

The point is to assert that the command issues the correct
``INSERT INTO target SELECT * FROM clusterAllReplicas(...) WHERE id NOT IN
target`` pattern, that it refuses to run with the wrong configuration,
and that ``--dry-run`` truly performs no mutation.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def _build_mock_db_client(*, source_distinct=14, target_count_before=0, table_exists=True):
    db_client = MagicMock()

    # ``execute`` returns rows: each query type returns a list of tuples.
    # We use side_effect to script returns in the order the command calls
    # them, but a simpler approach is to return based on substring match
    # of the query text.
    target_count_state = {"value": target_count_before}

    def execute_side_effect(sql, params=None):
        sql_lc = sql.lower()
        if "from system.tables" in sql_lc:
            return [(1 if table_exists else 0,)]
        if "uniqexact(id)" in sql_lc and "clusterallreplicas" in sql_lc:
            return [(source_distinct,)]
        if "select count() from" in sql_lc and "clusterallreplicas" not in sql_lc:
            return [(target_count_state["value"],)]
        if sql_lc.lstrip().startswith("insert into"):
            target_count_state["value"] = max(
                target_count_state["value"], source_distinct
            )
            return []
        return []

    db_client.client.execute.side_effect = execute_side_effect
    db_client.client.connection.database = "default"
    db_client.create_table = MagicMock()
    return db_client, target_count_state


def test_refuses_to_run_when_source_equals_target():
    out = StringIO()
    with pytest.raises(CommandError) as excinfo:
        call_command(
            "migrate_legacy_vectors_to_replicated",
            "--source-database=default",
            "--target-database=default",
            "--tables=feedbacks",
            stdout=out,
        )
    assert "same value" in str(excinfo.value).lower() or "same" in str(excinfo.value)


def test_refuses_to_run_when_replicated_env_not_set(monkeypatch):
    monkeypatch.delenv("CH_VECTOR_REPLICATED", raising=False)
    out = StringIO()
    with pytest.raises(CommandError) as excinfo:
        call_command(
            "migrate_legacy_vectors_to_replicated",
            "--source-database=default",
            "--target-database=futureagi",
            "--tables=feedbacks",
            stdout=out,
        )
    assert "CH_VECTOR_REPLICATED" in str(excinfo.value)


def test_dry_run_does_not_create_table_or_insert(monkeypatch):
    monkeypatch.delenv("CH_VECTOR_REPLICATED", raising=False)
    db_client, _ = _build_mock_db_client(source_distinct=14)
    out = StringIO()
    with patch(
        "model_hub.management.commands.migrate_legacy_vectors_to_replicated.ClickHouseVectorDB",
        return_value=db_client,
    ):
        call_command(
            "migrate_legacy_vectors_to_replicated",
            "--source-database=default",
            "--target-database=futureagi",
            "--tables=feedbacks",
            "--dry-run",
            stdout=out,
        )

    db_client.create_table.assert_not_called()
    executed_sqls = [c.args[0] for c in db_client.client.execute.call_args_list]
    assert not any(s.lower().lstrip().startswith("insert into") for s in executed_sqls), (
        "dry-run must not emit any INSERT statement"
    )
    assert "would copy" in out.getvalue().lower()


def test_actual_run_emits_insert_select_clusterallreplicas(monkeypatch):
    monkeypatch.setenv("CH_VECTOR_REPLICATED", "true")
    db_client, target_state = _build_mock_db_client(
        source_distinct=14, target_count_before=0
    )
    out = StringIO()
    with patch(
        "model_hub.management.commands.migrate_legacy_vectors_to_replicated.ClickHouseVectorDB",
        return_value=db_client,
    ):
        call_command(
            "migrate_legacy_vectors_to_replicated",
            "--source-database=default",
            "--target-database=futureagi",
            "--tables=feedbacks",
            stdout=out,
        )

    db_client.create_table.assert_called_once_with("feedbacks")
    executed_sqls = [c.args[0] for c in db_client.client.execute.call_args_list]
    insert_stmts = [s for s in executed_sqls if s.lower().lstrip().startswith("insert into")]
    assert len(insert_stmts) == 1
    insert_sql = insert_stmts[0]
    assert "INSERT INTO futureagi.feedbacks" in insert_sql
    assert "clusterAllReplicas('cluster', default.feedbacks)" in insert_sql
    assert "WHERE id NOT IN (SELECT id FROM futureagi.feedbacks)" in insert_sql
    # parity should be ok
    assert target_state["value"] == 14
    assert "copied 14 rows" in out.getvalue()


def test_skips_table_that_does_not_exist_in_source(monkeypatch):
    monkeypatch.setenv("CH_VECTOR_REPLICATED", "true")
    db_client, _ = _build_mock_db_client(table_exists=False)
    out = StringIO()
    with patch(
        "model_hub.management.commands.migrate_legacy_vectors_to_replicated.ClickHouseVectorDB",
        return_value=db_client,
    ):
        call_command(
            "migrate_legacy_vectors_to_replicated",
            "--source-database=default",
            "--target-database=futureagi",
            "--tables=feedbacks",
            stdout=out,
        )

    db_client.create_table.assert_not_called()
    executed_sqls = [c.args[0] for c in db_client.client.execute.call_args_list]
    assert not any(s.lower().lstrip().startswith("insert into") for s in executed_sqls)
    assert "skipped" in out.getvalue().lower()


def test_rejects_unknown_table():
    out = StringIO()
    with pytest.raises(CommandError) as excinfo:
        call_command(
            "migrate_legacy_vectors_to_replicated",
            "--source-database=default",
            "--target-database=futureagi",
            "--tables=feedbacks,not_a_real_table",
            stdout=out,
        )
    assert "not_a_real_table" in str(excinfo.value)


def test_idempotency_second_run_inserts_nothing_new(monkeypatch):
    """Second run should INSERT, but the row count is already at parity so
    nothing is actually copied. The command must not error out."""
    monkeypatch.setenv("CH_VECTOR_REPLICATED", "true")
    db_client, _ = _build_mock_db_client(
        source_distinct=14, target_count_before=14
    )
    out = StringIO()
    with patch(
        "model_hub.management.commands.migrate_legacy_vectors_to_replicated.ClickHouseVectorDB",
        return_value=db_client,
    ):
        call_command(
            "migrate_legacy_vectors_to_replicated",
            "--source-database=default",
            "--target-database=futureagi",
            "--tables=feedbacks",
            stdout=out,
        )

    assert "copied 0 rows" in out.getvalue()


def test_syn_is_a_recognised_table(monkeypatch):
    """Regression guard: ``syn`` (knowledge-base chunk embeddings) must remain
    in the migrate command's known-table set because ``agent_evaluator`` adds
    the ``search_knowledge_base`` tool whenever a kb_id is configured, and
    that tool reads from ``syn``. Dropping syn from the migration would leave
    legacy KB chunks scattered across replicas with no way to consolidate.
    """
    monkeypatch.setenv("CH_VECTOR_REPLICATED", "true")
    db_client, _ = _build_mock_db_client(source_distinct=4000)
    out = StringIO()
    with patch(
        "model_hub.management.commands.migrate_legacy_vectors_to_replicated.ClickHouseVectorDB",
        return_value=db_client,
    ):
        call_command(
            "migrate_legacy_vectors_to_replicated",
            "--source-database=default",
            "--target-database=futureagi",
            "--tables=syn",
            stdout=out,
        )

    db_client.create_table.assert_called_once_with("syn")
    insert_sqls = [
        c.args[0] for c in db_client.client.execute.call_args_list
        if c.args[0].lower().lstrip().startswith("insert into")
    ]
    assert len(insert_sqls) == 1
    assert "INSERT INTO futureagi.syn" in insert_sqls[0]
    assert "clusterAllReplicas('cluster', default.syn)" in insert_sqls[0]


def test_handles_both_tables_in_one_invocation(monkeypatch):
    monkeypatch.setenv("CH_VECTOR_REPLICATED", "true")
    db_client, _ = _build_mock_db_client(source_distinct=7)
    out = StringIO()
    with patch(
        "model_hub.management.commands.migrate_legacy_vectors_to_replicated.ClickHouseVectorDB",
        return_value=db_client,
    ):
        call_command(
            "migrate_legacy_vectors_to_replicated",
            "--source-database=default",
            "--target-database=futureagi",
            "--tables=feedbacks,ground_truths",
            stdout=out,
        )

    create_calls = [c.args[0] for c in db_client.create_table.call_args_list]
    assert create_calls == ["feedbacks", "ground_truths"]
