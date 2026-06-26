"""Behavioural test: ``EvaluationRunner.get_few_shot_examples`` must pass
the runner's ``workspace_id`` through to
``EmbeddingManager.retrieve_avg_rag_based_examples``.

The bug we are guarding against: a regression to ``workspace_id=None`` would
silently widen the CH query to every workspace in the organization, leaking
feedback few-shots across workspace boundaries.

We assert the kwarg actually reached the embedding manager, not that any
particular line of code looks a certain way.
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def runner_factory():
    """Return a callable that builds an EvaluationRunner with the smallest
    surface needed to exercise get_few_shot_examples.

    We bypass ``EvaluationRunner.__init__`` because the real one pulls in a
    long initialisation chain (DB lookups for the template, serving client
    connections). For the workspace-plumbing test we only need the four
    attributes referenced inside ``get_few_shot_examples``.
    """
    from model_hub.views.eval_runner import EvaluationRunner

    def make(*, organization_id, workspace_id):
        runner = EvaluationRunner.__new__(EvaluationRunner)
        runner.organization_id = organization_id
        runner.workspace_id = workspace_id
        runner.eval_template = types.SimpleNamespace(id="tmpl-1")
        runner.dataset_feedback_groups = {}
        return runner

    return make


def test_workspace_id_is_forwarded_from_runner_to_embedding_manager(runner_factory):
    runner = runner_factory(
        organization_id="org-A",
        workspace_id="ws-W1",
    )

    fake_manager = MagicMock()
    fake_manager.retrieve_avg_rag_based_examples.return_value = []
    fake_manager.process_examples.return_value = []

    with patch(
        "model_hub.views.eval_runner.EmbeddingManager",
        return_value=fake_manager,
    ):
        runner.get_few_shot_examples(
            mapping=["how do I reset"],
            required_field=["input"],
        )

    fake_manager.retrieve_avg_rag_based_examples.assert_called_once()
    _, kwargs = fake_manager.retrieve_avg_rag_based_examples.call_args
    assert kwargs["organization_id"] == "org-A"
    assert kwargs["workspace_id"] == "ws-W1", (
        "workspace_id must propagate from the runner; passing None here is "
        "the regression that leaked feedback across workspaces."
    )


def test_no_organization_short_circuits_without_calling_ch(runner_factory):
    """Pre-existing guard: when there is no organization, the call returns
    early and never reaches CH. The fix must not regress this.
    """
    runner = runner_factory(
        organization_id=None,
        workspace_id="ws-W1",
    )

    fake_manager = MagicMock()

    with patch(
        "model_hub.views.eval_runner.EmbeddingManager",
        return_value=fake_manager,
    ):
        result = runner.get_few_shot_examples(
            mapping=["q"],
            required_field=["input"],
        )

    assert result == []
    fake_manager.retrieve_avg_rag_based_examples.assert_not_called()


def test_runner_with_no_workspace_still_calls_ch_with_explicit_none(runner_factory):
    """A runner with no workspace (org-only context) must pass ``None``
    explicitly rather than omit the kwarg. This keeps the CH-side semantics
    deterministic: ``None`` = org-scoped read.
    """
    runner = runner_factory(
        organization_id="org-A",
        workspace_id=None,
    )

    fake_manager = MagicMock()
    fake_manager.retrieve_avg_rag_based_examples.return_value = []
    fake_manager.process_examples.return_value = []

    with patch(
        "model_hub.views.eval_runner.EmbeddingManager",
        return_value=fake_manager,
    ):
        runner.get_few_shot_examples(
            mapping=["q"],
            required_field=["input"],
        )

    _, kwargs = fake_manager.retrieve_avg_rag_based_examples.call_args
    assert kwargs["workspace_id"] is None
