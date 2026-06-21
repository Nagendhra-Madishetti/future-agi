from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from model_hub.models.evaluation import Evaluation, StatusChoices
from model_hub.models.evals_metric import EvalTemplate


def _template(name: str, organization, *, output: str, multi_choice: bool = False):
    return EvalTemplate.objects.create(
        name=name,
        config={"output": output},
        organization=organization,
        multi_choice=multi_choice,
    )


def _legacy_eval(
    *,
    user,
    organization,
    workspace,
    template,
    value: str,
    output_type: str | None = None,
) -> Evaluation:
    ev = Evaluation.objects.create(
        user=user,
        organization=organization,
        workspace=workspace,
        eval_template=template,
        status=StatusChoices.COMPLETED,
    )
    Evaluation.objects.filter(id=ev.id).update(
        value=value,
        output_type=output_type,
        output_bool=None,
        output_float=None,
        output_str_list=None,
        output_str=None,
    )
    ev.refresh_from_db()
    return ev


def _run(**flags) -> str:
    out = StringIO()
    call_command("backfill_evaluation_dual_format", stdout=out, **flags)
    return out.getvalue()


@pytest.fixture
def tpl_score(db, organization):
    return _template("score tpl", organization, output="score")


@pytest.fixture
def tpl_choices(db, organization):
    return _template("choices tpl", organization, output="choices")


@pytest.fixture
def tpl_passfail(db, organization):
    return _template("passfail tpl", organization, output="Pass/Fail")


class TestAxisRouting:
    def test_score_value_populates_output_float(
        self, db, user, organization, workspace, tpl_score
    ):
        ev = _legacy_eval(
            user=user,
            organization=organization,
            workspace=workspace,
            template=tpl_score,
            value="0.7",
        )
        _run()
        ev.refresh_from_db()
        assert ev.output_float == pytest.approx(0.7)
        assert ev.output_bool is None
        assert ev.output_str_list is None

    def test_choices_value_populates_output_str_list(
        self, db, user, organization, workspace, tpl_choices
    ):
        ev = _legacy_eval(
            user=user,
            organization=organization,
            workspace=workspace,
            template=tpl_choices,
            value="frequently",
        )
        _run()
        ev.refresh_from_db()
        assert ev.output_str_list == ["frequently"]
        assert ev.output_float is None

    def test_passfail_value_populates_output_bool(
        self, db, user, organization, workspace, tpl_passfail
    ):
        ev = _legacy_eval(
            user=user,
            organization=organization,
            workspace=workspace,
            template=tpl_passfail,
            value="Passed",
        )
        _run()
        ev.refresh_from_db()
        assert ev.output_bool is True
        assert ev.output_float is None

    def test_choice_scores_dict_populates_both_axes(
        self, db, user, organization, workspace, tpl_score
    ):
        ev = _legacy_eval(
            user=user,
            organization=organization,
            workspace=workspace,
            template=tpl_score,
            value="{'score': 0.8, 'choice': 'good'}",
        )
        _run()
        ev.refresh_from_db()
        assert ev.output_float == pytest.approx(0.8)
        assert ev.output_str_list == ["good"]


class TestOperationalSafety:
    def test_dry_run_does_not_mutate(
        self, db, user, organization, workspace, tpl_score
    ):
        ev = _legacy_eval(
            user=user,
            organization=organization,
            workspace=workspace,
            template=tpl_score,
            value="0.7",
        )
        out = _run(dry_run=True)
        ev.refresh_from_db()
        assert ev.output_float is None
        assert "dry_run=True" in out

    def test_rerun_is_idempotent(
        self, db, user, organization, workspace, tpl_score
    ):
        ev = _legacy_eval(
            user=user,
            organization=organization,
            workspace=workspace,
            template=tpl_score,
            value="0.7",
        )
        _run()
        first = (
            Evaluation.objects.filter(id=ev.id)
            .values_list("output_float", flat=True)
            .first()
        )
        out = _run()
        ev.refresh_from_db()
        assert ev.output_float == first
        assert "updated_rows=0" in out

    def test_already_populated_row_is_skipped(
        self, db, user, organization, workspace, tpl_score
    ):
        ev = _legacy_eval(
            user=user,
            organization=organization,
            workspace=workspace,
            template=tpl_score,
            value="0.7",
        )
        Evaluation.objects.filter(id=ev.id).update(output_float=0.1)
        out = _run()
        ev.refresh_from_db()
        assert ev.output_float == pytest.approx(0.1)
        assert "skipped_rows=1" in out


class TestFiltering:
    def test_eval_template_id_scopes_to_one_template(
        self, db, user, organization, workspace, tpl_score, tpl_choices
    ):
        scoped = _legacy_eval(
            user=user,
            organization=organization,
            workspace=workspace,
            template=tpl_score,
            value="0.7",
        )
        unscoped = _legacy_eval(
            user=user,
            organization=organization,
            workspace=workspace,
            template=tpl_choices,
            value="frequently",
        )
        _run(eval_template_id=str(tpl_score.id))
        scoped.refresh_from_db()
        unscoped.refresh_from_db()
        assert scoped.output_float == pytest.approx(0.7)
        assert unscoped.output_str_list is None

    def test_evaluation_id_scopes_to_one_row(
        self, db, user, organization, workspace, tpl_score
    ):
        a = _legacy_eval(
            user=user,
            organization=organization,
            workspace=workspace,
            template=tpl_score,
            value="0.7",
        )
        b = _legacy_eval(
            user=user,
            organization=organization,
            workspace=workspace,
            template=tpl_score,
            value="0.5",
        )
        _run(evaluation_id=str(a.id))
        a.refresh_from_db()
        b.refresh_from_db()
        assert a.output_float == pytest.approx(0.7)
        assert b.output_float is None
