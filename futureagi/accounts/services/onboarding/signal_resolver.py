from dataclasses import dataclass

from django.db.models import Q

from accounts.services.onboarding.activation_events import (
    first_quality_loop_completed,
    has_event,
    latest_event,
)


@dataclass(frozen=True)
class OnboardingSignals:
    first_checks: dict
    provider_keys: int = 0
    datasets: int = 0
    evals: int = 0
    eval_runs: int = 0
    prompt_templates: int = 0
    prompt_versions: int = 0
    prompt_comparisons: int = 0
    agents: int = 0
    agent_prototype_runs: int = 0
    observe_projects: int = 0
    traces: int = 0
    trace_reviews: int = 0
    gateway_keys: int = 0
    gateway_requests: int = 0
    gateway_policies: int = 0
    voice_agents: int = 0
    voice_simulations: int = 0
    voice_calls: int = 0
    voice_reviews: int = 0
    team_invites: int = 0
    dashboards: int = 0
    alerts: int = 0
    first_trace_id: str | None = None
    first_observe_id: str | None = None
    observe_project_exists: bool = False
    trace_exists: bool = False
    trace_reviewed: bool = False
    sample_trace_reviewed: bool = False
    evaluator_exists: bool = False
    dashboard_exists: bool = False
    alert_exists: bool = False
    saved_view_exists: bool = False
    first_loop_completed: bool = False
    useful_daily_signal: bool = False
    last_meaningful_event: object | None = None

    def to_payload(self):
        return {
            "provider_keys": self.provider_keys,
            "datasets": self.datasets,
            "evals": self.evals,
            "eval_runs": self.eval_runs,
            "prompt_templates": self.prompt_templates,
            "prompt_versions": self.prompt_versions,
            "prompt_comparisons": self.prompt_comparisons,
            "agents": self.agents,
            "agent_prototype_runs": self.agent_prototype_runs,
            "observe_projects": self.observe_projects,
            "traces": self.traces,
            "trace_reviews": self.trace_reviews,
            "gateway_keys": self.gateway_keys,
            "gateway_requests": self.gateway_requests,
            "gateway_policies": self.gateway_policies,
            "voice_agents": self.voice_agents,
            "voice_simulations": self.voice_simulations,
            "voice_calls": self.voice_calls,
            "voice_reviews": self.voice_reviews,
            "team_invites": self.team_invites,
            "dashboards": self.dashboards,
            "alerts": self.alerts,
            "first_trace_id": self.first_trace_id,
            "first_observe_id": self.first_observe_id,
        }


def _compatibility_checks(user, organization, workspace):
    from accounts.views.user import get_user_checks

    return get_user_checks(user, organization=organization, workspace=workspace)


def _observe_project_queryset(organization, workspace):
    from tracer.models.project import Project

    return (
        Project.no_workspace_objects.filter(
            organization=organization,
            workspace=workspace,
            trace_type="observe",
        )
        .exclude(source="sample")
        .filter(Q(metadata__is_sample__isnull=True) | Q(metadata__is_sample=False))
    )


def _trace_queryset(organization, workspace):
    from tracer.models.trace import Trace

    return (
        Trace.no_workspace_objects.filter(
            project__organization=organization,
            project__workspace=workspace,
            project__trace_type="observe",
        )
        .exclude(project__source="sample")
        .filter(
            Q(project__metadata__is_sample__isnull=True)
            | Q(project__metadata__is_sample=False)
        )
        .filter(Q(metadata__is_sample__isnull=True) | Q(metadata__is_sample=False))
    )


def _custom_eval_exists(project_ids):
    if not project_ids:
        return False
    from tracer.models.custom_eval_config import CustomEvalConfig

    return CustomEvalConfig.no_workspace_objects.filter(
        project_id__in=project_ids,
    ).exists()


def _dashboard_exists(workspace):
    from tracer.models.dashboard import Dashboard

    return Dashboard.no_workspace_objects.filter(workspace=workspace).exists()


def _alert_exists(organization, workspace, project_ids):
    from tracer.models.monitor import UserAlertMonitor

    queryset = UserAlertMonitor.no_workspace_objects.filter(
        organization=organization,
        workspace=workspace,
    )
    if project_ids:
        queryset = queryset.filter(project_id__in=project_ids)
    return queryset.exists()


def _saved_view_exists(workspace, project_ids):
    from tracer.models.saved_view import SavedView

    queryset = SavedView.no_workspace_objects.filter(workspace=workspace)
    if project_ids:
        queryset = queryset.filter(project_id__in=project_ids)
    return queryset.exists()


def _as_count(value):
    return 1 if value else 0


def collect_onboarding_signals(*, user, organization, workspace):
    if not organization or not workspace:
        return OnboardingSignals(first_checks={})

    first_checks = _compatibility_checks(user, organization, workspace)

    observe_projects = _observe_project_queryset(organization, workspace)
    observe_project_ids = list(observe_projects.values_list("id", flat=True)[:20])
    first_observe_id = str(observe_project_ids[0]) if observe_project_ids else None

    traces = _trace_queryset(organization, workspace)
    first_trace = traces.only("id", "project_id").order_by("created_at").first()
    first_trace_id = str(first_trace.id) if first_trace else None

    trace_reviewed = has_event(
        organization=organization,
        workspace=workspace,
        event_name="trace_reviewed",
        is_sample=False,
    )
    sample_trace_reviewed = has_event(
        organization=organization,
        workspace=workspace,
        event_name="trace_reviewed",
        is_sample=True,
    ) or has_event(
        organization=organization,
        workspace=workspace,
        event_name="sample_signal_viewed",
        is_sample=True,
    )

    evaluator_exists = _custom_eval_exists(observe_project_ids)
    dashboard_exists = _dashboard_exists(workspace)
    alert_exists = _alert_exists(organization, workspace, observe_project_ids)
    saved_view_exists = _saved_view_exists(workspace, observe_project_ids)
    improvement_exists = (
        evaluator_exists or dashboard_exists or alert_exists or saved_view_exists
    )
    real_loop_completed = first_quality_loop_completed(
        organization=organization,
        workspace=workspace,
        product_path="observe",
    ) or (trace_reviewed and improvement_exists)
    last_event = latest_event(
        organization=organization,
        workspace=workspace,
        is_sample=False,
    )

    return OnboardingSignals(
        first_checks=first_checks,
        provider_keys=_as_count(first_checks.get("keys")),
        datasets=_as_count(first_checks.get("dataset")),
        evals=_as_count(first_checks.get("evaluation")),
        eval_runs=_as_count(first_checks.get("experiment")),
        observe_projects=_as_count(bool(observe_project_ids)),
        traces=_as_count(first_trace is not None),
        trace_reviews=_as_count(trace_reviewed),
        team_invites=_as_count(first_checks.get("invite")),
        dashboards=_as_count(dashboard_exists),
        alerts=_as_count(alert_exists),
        first_trace_id=first_trace_id,
        first_observe_id=first_observe_id,
        observe_project_exists=bool(observe_project_ids),
        trace_exists=first_trace is not None,
        trace_reviewed=trace_reviewed,
        sample_trace_reviewed=sample_trace_reviewed,
        evaluator_exists=evaluator_exists,
        dashboard_exists=dashboard_exists,
        alert_exists=alert_exists,
        saved_view_exists=saved_view_exists,
        first_loop_completed=real_loop_completed,
        useful_daily_signal=real_loop_completed and first_trace is not None,
        last_meaningful_event=last_event,
    )
