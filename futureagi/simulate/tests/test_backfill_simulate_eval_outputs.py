"""Integration tests for the ``backfill_simulate_eval_outputs`` command.

Each test creates real ``SimulateEvalConfig`` + ``CallExecution`` rows with a
pre-canonicalization ``eval_outputs`` blob, runs the command, and asserts on
the resulting JSONB shape.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from model_hub.models.evals_metric import EvalTemplate
from simulate.models.eval_config import SimulateEvalConfig
from simulate.models.run_test import RunTest
from simulate.models.test_execution import CallExecution, TestExecution


@pytest.fixture
def score_template(db, organization):
    return EvalTemplate.objects.create(
        name="bf score template",
        config={"output": "score"},
        organization=organization,
    )


@pytest.fixture
def choices_template(db, organization):
    return EvalTemplate.objects.create(
        name="bf choices template",
        config={"output": "choices"},
        organization=organization,
    )


@pytest.fixture
def run_test(db, organization, workspace):
    return RunTest.objects.create(
        name="bf run test",
        description="",
        organization=organization,
        workspace=workspace,
    )


@pytest.fixture
def test_execution(db, run_test):
    return TestExecution.objects.create(
        run_test=run_test,
        status=TestExecution.ExecutionStatus.RUNNING,
    )


def _eval_config(template, run_test, name="bf cfg"):
    return SimulateEvalConfig.objects.create(
        name=name,
        eval_template=template,
        run_test=run_test,
        config={},
        mapping={},
    )


def _call(test_execution, eval_outputs):
    return CallExecution.objects.create(
        test_execution=test_execution,
        eval_outputs=eval_outputs,
    )


def _run(**flags) -> str:
    out = StringIO()
    call_command("backfill_simulate_eval_outputs", stdout=out, **flags)
    return out.getvalue()


def test_score_dict_recovers_output_scalar(
    db, score_template, run_test, test_execution
):
    cfg = _eval_config(score_template, run_test, "score cfg")
    call = _call(
        test_execution,
        {
            str(cfg.id): {
                "output": {"score": 0.7, "choice": "Good"},
                "reason": "",
                "output_type": "score",
                "name": "score cfg",
            },
        },
    )

    _run()
    call.refresh_from_db()
    entry = call.eval_outputs[str(cfg.id)]
    assert entry["output_scalar"] == pytest.approx(0.7)
    assert entry["output_dict"] == {"score": 0.7, "choice": "Good"}
    assert entry["output"] == {"score": 0.7, "choice": "Good"}


def test_choices_dict_multi_recovers_json_list_scalar(
    db, choices_template, run_test, test_execution
):
    cfg = _eval_config(choices_template, run_test, "choices cfg")
    call = _call(
        test_execution,
        {
            str(cfg.id): {
                "output": {"choices": ["A", "B"]},
                "reason": "",
                "output_type": "choices",
                "name": "choices cfg",
            },
        },
    )

    _run()
    call.refresh_from_db()
    entry = call.eval_outputs[str(cfg.id)]
    assert json.loads(entry["output_scalar"]) == ["A", "B"]
    assert entry["output_dict"] == {"choices": ["A", "B"]}


def test_choices_single_string_recovers_scalar(
    db, choices_template, run_test, test_execution
):
    cfg = _eval_config(choices_template, run_test, "single cfg")
    call = _call(
        test_execution,
        {
            str(cfg.id): {
                "output": "Good",
                "reason": "",
                "output_type": "choices",
                "name": "single cfg",
            },
        },
    )

    _run()
    call.refresh_from_db()
    entry = call.eval_outputs[str(cfg.id)]
    assert entry["output_scalar"] == "Good"
    assert entry["output_dict"] is None


def test_dry_run_writes_nothing(db, score_template, run_test, test_execution):
    cfg = _eval_config(score_template, run_test, "dry cfg")
    call = _call(
        test_execution,
        {
            str(cfg.id): {
                "output": 0.5,
                "reason": "",
                "output_type": "score",
                "name": "dry cfg",
            },
        },
    )

    _run(dry_run=True)
    call.refresh_from_db()
    assert "output_scalar" not in call.eval_outputs[str(cfg.id)]


def test_rerun_is_idempotent(db, score_template, run_test, test_execution):
    cfg = _eval_config(score_template, run_test, "idem cfg")
    _call(
        test_execution,
        {
            str(cfg.id): {
                "output": 0.5,
                "reason": "",
                "output_type": "score",
                "name": "idem cfg",
            },
        },
    )

    _run()
    second = _run()
    assert "updated_rows=0" in second


def test_entries_already_canonical_are_skipped(
    db, score_template, run_test, test_execution
):
    cfg = _eval_config(score_template, run_test, "already cfg")
    call = _call(
        test_execution,
        {
            str(cfg.id): {
                "output": 0.5,
                "output_scalar": 999.0,
                "output_dict": None,
                "reason": "",
                "output_type": "score",
                "name": "already cfg",
            },
        },
    )

    _run()
    call.refresh_from_db()
    assert call.eval_outputs[str(cfg.id)]["output_scalar"] == 999.0


def test_pending_placeholder_gets_none_scalars(
    db, score_template, run_test, test_execution
):
    cfg = _eval_config(score_template, run_test, "pending cfg")
    call = _call(
        test_execution,
        {str(cfg.id): {"status": "pending"}},
    )

    _run()
    call.refresh_from_db()
    entry = call.eval_outputs[str(cfg.id)]
    assert entry["output_scalar"] is None
    assert entry["output_dict"] is None
    assert entry["status"] == "pending"


def test_eval_config_id_flag_scopes_to_one_entry(
    db, score_template, run_test, test_execution
):
    cfg_a = _eval_config(score_template, run_test, "a cfg")
    cfg_b = _eval_config(score_template, run_test, "b cfg")
    call = _call(
        test_execution,
        {
            str(cfg_a.id): {
                "output": 0.1,
                "reason": "",
                "output_type": "score",
                "name": "a",
            },
            str(cfg_b.id): {
                "output": 0.2,
                "reason": "",
                "output_type": "score",
                "name": "b",
            },
        },
    )

    _run(eval_config_id=str(cfg_a.id))
    call.refresh_from_db()
    assert "output_scalar" in call.eval_outputs[str(cfg_a.id)]
    assert "output_scalar" not in call.eval_outputs[str(cfg_b.id)]
