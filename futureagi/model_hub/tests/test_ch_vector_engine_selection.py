"""Behavioural tests for ``ClickHouseVectorDB.create_table``.

We assert on the SQL that gets executed against the underlying CH client,
not on the source text of the module. Each test patches the CH client and
captures the actual statement that would be sent to the server. That is the
boundary between this layer and ClickHouse; everything above it is plumbing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def captured_sql_client():
    """Patch ``ClickHouseVectorDB.__init__`` so no real CH connection is made
    and ``self.client`` is a MagicMock whose ``execute`` we can inspect.
    """
    from agentic_eval.core.database import ch_vector

    def _no_init(self, *_args, **_kwargs):
        self.client = MagicMock()

    with patch.object(ch_vector.ClickHouseVectorDB, "__init__", _no_init):
        instance = ch_vector.ClickHouseVectorDB()
        yield instance


def _executed_sql(captured_sql_client) -> str:
    """Return the SQL string from the last execute call."""
    assert captured_sql_client.client.execute.called
    args, _ = captured_sql_client.client.execute.call_args
    return args[0]


def test_create_table_default_env_emits_plain_mergetree(captured_sql_client, monkeypatch):
    monkeypatch.delenv("CH_VECTOR_REPLICATED", raising=False)

    captured_sql_client.create_table("feedbacks")

    sql = _executed_sql(captured_sql_client)
    assert "ENGINE = MergeTree()" in sql
    assert "ReplicatedReplacingMergeTree" not in sql
    assert "ON CLUSTER" not in sql


def test_create_table_replicated_env_emits_replicated_engine_and_on_cluster(
    captured_sql_client, monkeypatch
):
    monkeypatch.setenv("CH_VECTOR_REPLICATED", "true")

    captured_sql_client.create_table("ground_truths")

    sql = _executed_sql(captured_sql_client)
    assert "ENGINE = ReplicatedReplacingMergeTree" in sql
    assert "MergeTree()" not in sql  # exact, not substring
    assert "ON CLUSTER 'cluster'" in sql
    assert (
        "ReplicatedReplacingMergeTree("
        "'/clickhouse/tables/{shard}/ground_truths', '{replica}'"
        ")"
    ) in sql


def test_create_table_replicated_env_false_falls_back_to_mergetree(
    captured_sql_client, monkeypatch
):
    # Anything other than the literal "true" must not flip the engine.
    monkeypatch.setenv("CH_VECTOR_REPLICATED", "false")

    captured_sql_client.create_table("feedbacks")

    sql = _executed_sql(captured_sql_client)
    assert "ENGINE = MergeTree()" in sql
    assert "ReplicatedReplacingMergeTree" not in sql


def test_create_table_table_name_substituted_into_zk_path(
    captured_sql_client, monkeypatch
):
    """Each table gets its own ZK path; otherwise two tables would coordinate
    on the same Keeper znode and corrupt each other's replication queue.
    """
    monkeypatch.setenv("CH_VECTOR_REPLICATED", "true")

    captured_sql_client.create_table("feedbacks")
    sql_fb = _executed_sql(captured_sql_client)
    assert "'/clickhouse/tables/{shard}/feedbacks'" in sql_fb

    captured_sql_client.client.execute.reset_mock()
    captured_sql_client.create_table("ground_truths")
    sql_gt = _executed_sql(captured_sql_client)
    assert "'/clickhouse/tables/{shard}/ground_truths'" in sql_gt
    assert "feedbacks" not in sql_gt


def test_create_table_replicated_keeps_required_columns(
    captured_sql_client, monkeypatch
):
    """Engine swap must not silently drop columns the rest of the codebase
    depends on (id, eval_id, vector, metadata, deleted).
    """
    monkeypatch.setenv("CH_VECTOR_REPLICATED", "true")

    captured_sql_client.create_table("feedbacks")

    sql = _executed_sql(captured_sql_client)
    for column_signature in (
        "id UUID",
        "eval_id UUID",
        "vector Array(Float32)",
        "metadata Nested",
        "key String",
        "value Nullable(String)",
        "deleted UInt8 DEFAULT 0",
    ):
        assert column_signature in sql, f"missing column in CREATE TABLE: {column_signature}"


def test_create_table_order_by_preserved(captured_sql_client, monkeypatch):
    """ReplacingMergeTree dedups by ORDER BY; if the key is wrong, replication
    semantics drift from the legacy table.
    """
    monkeypatch.setenv("CH_VECTOR_REPLICATED", "true")

    captured_sql_client.create_table("feedbacks")

    sql = _executed_sql(captured_sql_client)
    assert "ORDER BY id" in sql
