"""Behavioural tests for ``backfill_workspace_stamps_on_feedbacks``.

We patch the CH client so no real CH is required and exercise:

  * The candidate-row iterator filters at the SQL layer
    (``has(metadata.key, 'organization_id')``).
  * Rows already carrying ``workspace_id`` are NOT stamped a second time.
  * Resolution chain: ``Feedback.workspace_id`` first, then
    ``Feedback.user_eval_metric.workspace_id``, then
    ``Feedback.eval_template.workspace_id``.
  * Unresolvable rows are logged and skipped, not stamped with garbage.
  * ``--dry-run`` issues no ``ALTER TABLE … UPDATE`` statement.
  * Per-row exceptions do not abort the whole run.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def _make_ch_row(*, row_id, eval_id, org_id, workspace_present):
    return (row_id, eval_id, org_id, 1 if workspace_present else 0)


def _patch_ch_client(rows_to_yield):
    """Patch ClickHouseVectorDB so the iterator returns rows_to_yield once
    then nothing (single-batch run), and ALTER calls are tracked.
    """
    db_client = MagicMock()
    page_state = {"served": False}

    def execute_side_effect(sql, params=None):
        if sql.lstrip().upper().startswith("ALTER"):
            return []
        if "FROM clusterAllReplicas" in sql and not page_state["served"]:
            page_state["served"] = True
            return rows_to_yield
        return []

    db_client.client.execute.side_effect = execute_side_effect
    return db_client


def _patch_feedback_lookup(feedback_obj):
    """Patch ``model_hub.models.evals_metric.Feedback.objects`` so the
    ``.filter().select_related().first()`` chain returns ``feedback_obj``.
    """
    chain = MagicMock()
    chain.select_related.return_value.first.return_value = feedback_obj
    return patch(
        "model_hub.management.commands.backfill_workspace_stamps_on_feedbacks.Feedback.objects.filter",
        return_value=chain,
    )


def _feedback_with(*, workspace_id=None, uem_workspace_id=None, template_workspace_id=None):
    """Build a fake Feedback object with just enough fields to drive the
    resolution chain.
    """
    fb = MagicMock()
    fb.workspace_id = workspace_id
    fb.user_eval_metric = (
        MagicMock(workspace_id=uem_workspace_id) if uem_workspace_id else None
    )
    fb.eval_template = (
        MagicMock(workspace_id=template_workspace_id) if template_workspace_id else None
    )
    return fb


def test_row_with_workspace_already_stamped_is_skipped(monkeypatch):
    rows = [_make_ch_row(
        row_id="r1", eval_id="ev1", org_id="org-A",
        workspace_present=True,
    )]
    db_client = _patch_ch_client(rows)

    out = StringIO()
    with patch(
        "model_hub.management.commands.backfill_workspace_stamps_on_feedbacks.ClickHouseVectorDB",
        return_value=db_client,
    ):
        call_command(
            "backfill_workspace_stamps_on_feedbacks",
            stdout=out,
        )

    sqls = [c.args[0] for c in db_client.client.execute.call_args_list]
    assert not any(s.lstrip().upper().startswith("ALTER") for s in sqls), (
        "rows already carrying workspace_id must not be re-stamped"
    )
    assert "already_stamped=1" in out.getvalue()


def test_dry_run_resolves_but_does_not_alter(monkeypatch):
    rows = [_make_ch_row(
        row_id="r1", eval_id="ev1", org_id="org-A",
        workspace_present=False,
    )]
    db_client = _patch_ch_client(rows)

    out = StringIO()
    with patch(
        "model_hub.management.commands.backfill_workspace_stamps_on_feedbacks.ClickHouseVectorDB",
        return_value=db_client,
    ), _patch_feedback_lookup(_feedback_with(workspace_id="ws-W1")):
        call_command(
            "backfill_workspace_stamps_on_feedbacks",
            "--dry-run",
            stdout=out,
        )

    sqls = [c.args[0] for c in db_client.client.execute.call_args_list]
    assert not any(s.lstrip().upper().startswith("ALTER") for s in sqls), (
        "dry-run must not emit ALTER"
    )
    assert "resolved=1" in out.getvalue()


def test_resolves_workspace_from_feedback_directly(monkeypatch):
    rows = [_make_ch_row(
        row_id="r1", eval_id="ev1", org_id="org-A",
        workspace_present=False,
    )]
    db_client = _patch_ch_client(rows)

    out = StringIO()
    with patch(
        "model_hub.management.commands.backfill_workspace_stamps_on_feedbacks.ClickHouseVectorDB",
        return_value=db_client,
    ), _patch_feedback_lookup(_feedback_with(workspace_id="ws-W1")):
        call_command(
            "backfill_workspace_stamps_on_feedbacks",
            stdout=out,
        )

    alter_sqls = [
        c for c in db_client.client.execute.call_args_list
        if c.args[0].lstrip().upper().startswith("ALTER")
    ]
    assert len(alter_sqls) == 1
    sql, params = alter_sqls[0].args[0], alter_sqls[0].args[1]
    assert "arrayPushBack(metadata.key, 'workspace_id')" in sql
    assert "arrayPushBack(metadata.value, %(ws)s)" in sql
    assert params == {"ws": "ws-W1", "rid": "r1"}
    assert "resolved=1" in out.getvalue()


def test_falls_back_to_user_eval_metric_workspace(monkeypatch):
    rows = [_make_ch_row(
        row_id="r1", eval_id="ev1", org_id="org-A",
        workspace_present=False,
    )]
    db_client = _patch_ch_client(rows)

    out = StringIO()
    with patch(
        "model_hub.management.commands.backfill_workspace_stamps_on_feedbacks.ClickHouseVectorDB",
        return_value=db_client,
    ), _patch_feedback_lookup(_feedback_with(uem_workspace_id="ws-uem")):
        call_command(
            "backfill_workspace_stamps_on_feedbacks",
            stdout=out,
        )

    alter_sqls = [
        c for c in db_client.client.execute.call_args_list
        if c.args[0].lstrip().upper().startswith("ALTER")
    ]
    assert len(alter_sqls) == 1
    assert alter_sqls[0].args[1]["ws"] == "ws-uem"


def test_falls_back_to_template_workspace(monkeypatch):
    rows = [_make_ch_row(
        row_id="r1", eval_id="ev1", org_id="org-A",
        workspace_present=False,
    )]
    db_client = _patch_ch_client(rows)

    out = StringIO()
    with patch(
        "model_hub.management.commands.backfill_workspace_stamps_on_feedbacks.ClickHouseVectorDB",
        return_value=db_client,
    ), _patch_feedback_lookup(_feedback_with(template_workspace_id="ws-tmpl")):
        call_command(
            "backfill_workspace_stamps_on_feedbacks",
            stdout=out,
        )

    alter_sqls = [
        c for c in db_client.client.execute.call_args_list
        if c.args[0].lstrip().upper().startswith("ALTER")
    ]
    assert len(alter_sqls) == 1
    assert alter_sqls[0].args[1]["ws"] == "ws-tmpl"


def test_unresolvable_row_is_skipped_not_stamped(monkeypatch):
    rows = [_make_ch_row(
        row_id="r1", eval_id="ev1", org_id="org-A",
        workspace_present=False,
    )]
    db_client = _patch_ch_client(rows)

    # No matching PG Feedback row -> first() returns None.
    out = StringIO()
    with patch(
        "model_hub.management.commands.backfill_workspace_stamps_on_feedbacks.ClickHouseVectorDB",
        return_value=db_client,
    ), _patch_feedback_lookup(None):
        call_command(
            "backfill_workspace_stamps_on_feedbacks",
            stdout=out,
        )

    sqls = [c.args[0] for c in db_client.client.execute.call_args_list]
    assert not any(s.lstrip().upper().startswith("ALTER") for s in sqls), (
        "unresolvable rows must not be stamped with a guess"
    )
    assert "unresolvable=1" in out.getvalue()


def test_resolver_failure_does_not_abort_run(monkeypatch):
    """One bad row should not take down the whole backfill."""
    rows = [
        _make_ch_row(row_id="r1", eval_id="ev1", org_id="org-A", workspace_present=False),
        _make_ch_row(row_id="r2", eval_id="ev2", org_id="org-A", workspace_present=False),
    ]
    db_client = _patch_ch_client(rows)

    # First lookup raises, second returns a workspace.
    chain = MagicMock()
    chain.select_related.return_value.first.side_effect = [
        RuntimeError("PG dropped the connection"),
        _feedback_with(workspace_id="ws-W2"),
    ]
    out = StringIO()
    with patch(
        "model_hub.management.commands.backfill_workspace_stamps_on_feedbacks.ClickHouseVectorDB",
        return_value=db_client,
    ), patch(
        "model_hub.management.commands.backfill_workspace_stamps_on_feedbacks.Feedback.objects.filter",
        return_value=chain,
    ):
        call_command(
            "backfill_workspace_stamps_on_feedbacks",
            stdout=out,
        )

    alter_sqls = [
        c for c in db_client.client.execute.call_args_list
        if c.args[0].lstrip().upper().startswith("ALTER")
    ]
    assert len(alter_sqls) == 1
    assert alter_sqls[0].args[1]["rid"] == "r2"
    out_text = out.getvalue()
    assert "failed=1" in out_text
    assert "resolved=1" in out_text


def test_organization_filter_is_applied_in_sql(monkeypatch):
    db_client = _patch_ch_client([])
    out = StringIO()
    with patch(
        "model_hub.management.commands.backfill_workspace_stamps_on_feedbacks.ClickHouseVectorDB",
        return_value=db_client,
    ):
        call_command(
            "backfill_workspace_stamps_on_feedbacks",
            "--organization-id=org-A",
            stdout=out,
        )

    candidate_sqls = [
        c for c in db_client.client.execute.call_args_list
        if "FROM clusterAllReplicas" in c.args[0]
    ]
    assert candidate_sqls, "expected at least one candidate-row query"
    sql, params = candidate_sqls[0].args[0], candidate_sqls[0].args[1]
    assert "indexOf(metadata.key, 'organization_id')" in sql
    assert params["org"] == "org-A"


def test_rejects_invalid_batch_size():
    out = StringIO()
    with pytest.raises(CommandError):
        call_command(
            "backfill_workspace_stamps_on_feedbacks",
            "--batch-size=0",
            stdout=out,
        )
