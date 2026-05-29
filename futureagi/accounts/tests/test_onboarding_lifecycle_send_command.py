import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from accounts.models import (
    OnboardingLifecycleEvaluationLog,
    OnboardingLifecycleSendAllowlist,
    OnboardingLifecycleSendLog,
    User,
)
from accounts.models.workspace import Workspace
from accounts.services.onboarding.lifecycle_preview_approval import (
    APPROVAL_METADATA_KEY,
    PREVIEW_APPROVAL_MISSING_REASON,
)
from accounts.services.onboarding.lifecycle_preview_snapshots import (
    write_lifecycle_preview_snapshots,
)
from accounts.services.onboarding.lifecycle_registry import lifecycle_campaign_by_key


@pytest.fixture(autouse=True)
def _cloud_lifecycle_delivery_enabled():
    with patch(
        "accounts.services.onboarding.lifecycle_sender._cloud_lifecycle_delivery_enabled",
        return_value=True,
    ):
        yield


def _flags(**overrides):
    flags = {
        "onboarding_activation_state_api": True,
        "onboarding_goal_picker": True,
        "onboarding_path_cards": True,
        "onboarding_sample_project": False,
        "onboarding_daily_quality_home": False,
        "onboarding_lifecycle_email_dry_run": True,
        "onboarding_email_welcome_enabled": True,
        "onboarding_email_first_action_recovery_enabled": True,
        "onboarding_email_first_signal_enabled": True,
        "onboarding_email_next_loop_enabled": True,
        "onboarding_email_sample_bridge_enabled": False,
        "onboarding_email_daily_digest_enabled": False,
        "onboarding_lifecycle_send_enabled": True,
    }
    flags.update(overrides)
    return flags


def _eligible_log(user, organization, workspace):
    now = timezone.now()
    Workspace.no_workspace_objects.filter(id=workspace.id).update(
        created_at=now - timedelta(minutes=30)
    )
    campaign = lifecycle_campaign_by_key("welcome_resume_goal")
    return OnboardingLifecycleEvaluationLog.no_workspace_objects.create(
        run_id="00000000-0000-0000-0000-000000000314",
        user=user,
        organization=organization,
        workspace=workspace,
        campaign_key=campaign["campaign_key"],
        campaign_group=campaign["campaign_group"],
        template_key=campaign["template_key"],
        template_version=campaign["template_version"],
        activation_stage=campaign["entry_stages"][0],
        target_success_event=campaign["target_success_event"],
        target_url="/dashboard/home?source=test",
        status=OnboardingLifecycleEvaluationLog.STATUS_ELIGIBLE,
        eligible_at=now - timedelta(minutes=15),
        evaluated_at=now - timedelta(minutes=1),
        registry_snapshot=campaign,
    )


def _eligible_campaign_log(user, organization, workspace, campaign_key):
    now = timezone.now()
    Workspace.no_workspace_objects.filter(id=workspace.id).update(
        created_at=now - timedelta(minutes=30)
    )
    campaign = lifecycle_campaign_by_key(campaign_key)
    return OnboardingLifecycleEvaluationLog.no_workspace_objects.create(
        run_id=f"00000000-0000-0000-0000-000000000{len(campaign_key):03d}",
        user=user,
        organization=organization,
        workspace=workspace,
        campaign_key=campaign["campaign_key"],
        campaign_group=campaign["campaign_group"],
        template_key=campaign["template_key"],
        template_version=campaign["template_version"],
        activation_stage=campaign["entry_stages"][0],
        target_success_event=campaign["target_success_event"],
        target_url="/dashboard/home?source=test",
        status=OnboardingLifecycleEvaluationLog.STATUS_ELIGIBLE,
        eligible_at=now - timedelta(minutes=15),
        evaluated_at=now - timedelta(minutes=1),
        registry_snapshot=campaign,
    )


def _approval_manifest_path(tmp_path, campaign_key="welcome_resume_goal"):
    output_dir = tmp_path / campaign_key
    write_lifecycle_preview_snapshots(
        output_dir=output_dir,
        campaign_key=campaign_key,
        now=timezone.now(),
    )
    return output_dir / "manifest.json"


@pytest.mark.django_db
@override_settings(ONBOARDING_FEATURE_FLAGS=_flags())
def test_send_command_dry_run_writes_no_send_logs(organization, workspace, user):
    _eligible_log(user, organization, workspace)
    output = StringIO()

    call_command(
        "run_onboarding_lifecycle_send",
        "--cohort",
        "internal",
        "--limit",
        "10",
        "--dry-run",
        stdout=output,
    )

    assert "evaluated=1" in output.getvalue()
    assert not OnboardingLifecycleSendLog.no_workspace_objects.exists()


@pytest.mark.django_db
@override_settings(ONBOARDING_FEATURE_FLAGS=_flags())
def test_send_command_respects_limit_and_sends_allowlisted(
    organization,
    workspace,
    user,
    tmp_path,
):
    _eligible_log(user, organization, workspace)
    approval_manifest = _approval_manifest_path(tmp_path)
    OnboardingLifecycleSendAllowlist.no_workspace_objects.create(
        scope_type=OnboardingLifecycleSendAllowlist.SCOPE_USER,
        scope_value=str(user.id),
        environment="local",
    )
    output = StringIO()

    with patch("accounts.services.onboarding.lifecycle_sender.email_helper"):
        call_command(
            "run_onboarding_lifecycle_send",
            "--cohort",
            "internal",
            "--limit",
            "1",
            "--approval-manifest",
            str(approval_manifest),
            stdout=output,
        )

    value = output.getvalue()
    assert "approval_manifest_sha256=" in value
    assert "sent=1" in value
    send_log = OnboardingLifecycleSendLog.no_workspace_objects.get(
        status=OnboardingLifecycleSendLog.STATUS_SENT
    )
    assert APPROVAL_METADATA_KEY in send_log.metadata
    assert send_log.metadata[APPROVAL_METADATA_KEY]["campaign_key"] == (
        "welcome_resume_goal"
    )
    assert len(send_log.metadata[APPROVAL_METADATA_KEY]["manifest_sha256"]) == 64


@pytest.mark.django_db
@override_settings(ONBOARDING_FEATURE_FLAGS=_flags())
def test_send_command_requires_approval_manifest_for_real_send(
    organization,
    workspace,
    user,
):
    _eligible_log(user, organization, workspace)
    output = StringIO()

    with pytest.raises(CommandError, match="--approval-manifest is required"):
        call_command(
            "run_onboarding_lifecycle_send",
            "--cohort",
            "internal",
            "--limit",
            "1",
            stdout=output,
        )

    assert not OnboardingLifecycleSendLog.no_workspace_objects.exists()


@pytest.mark.django_db
@override_settings(ONBOARDING_FEATURE_FLAGS=_flags())
def test_send_command_rejects_stale_approval_manifest(
    organization,
    workspace,
    user,
    tmp_path,
):
    _eligible_log(user, organization, workspace)
    approval_manifest = _approval_manifest_path(tmp_path)
    manifest = json.loads(approval_manifest.read_text())
    manifest["campaigns"][0]["subject"] = "Stale subject"
    approval_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    output = StringIO()

    with pytest.raises(CommandError, match="does not match current registry"):
        call_command(
            "run_onboarding_lifecycle_send",
            "--cohort",
            "internal",
            "--limit",
            "1",
            "--approval-manifest",
            str(approval_manifest),
            stdout=output,
        )

    assert not OnboardingLifecycleSendLog.no_workspace_objects.exists()


@pytest.mark.django_db
@override_settings(ONBOARDING_FEATURE_FLAGS=_flags())
def test_send_command_suppresses_campaign_missing_from_approval_manifest(
    organization,
    workspace,
    user,
    tmp_path,
):
    _eligible_log(user, organization, workspace)
    approval_manifest = _approval_manifest_path(tmp_path, "prompt_create_first")
    OnboardingLifecycleSendAllowlist.no_workspace_objects.create(
        scope_type=OnboardingLifecycleSendAllowlist.SCOPE_USER,
        scope_value=str(user.id),
        environment="local",
    )
    output = StringIO()

    with patch("accounts.services.onboarding.lifecycle_sender.email_helper") as helper:
        call_command(
            "run_onboarding_lifecycle_send",
            "--cohort",
            "internal",
            "--limit",
            "1",
            "--approval-manifest",
            str(approval_manifest),
            stdout=output,
        )

    value = output.getvalue()
    assert "sent=0" in value
    assert "suppressed=1" in value
    assert PREVIEW_APPROVAL_MISSING_REASON in value
    helper.assert_not_called()
    assert OnboardingLifecycleSendLog.no_workspace_objects.filter(
        status=OnboardingLifecycleSendLog.STATUS_SUPPRESSED,
        suppression_reason=PREVIEW_APPROVAL_MISSING_REASON,
    ).exists()


@pytest.mark.django_db
@override_settings(ONBOARDING_FEATURE_FLAGS=_flags())
def test_send_command_suppresses_real_send_when_not_cloud(
    organization,
    workspace,
    user,
    tmp_path,
):
    _eligible_log(user, organization, workspace)
    approval_manifest = _approval_manifest_path(tmp_path)
    OnboardingLifecycleSendAllowlist.no_workspace_objects.create(
        scope_type=OnboardingLifecycleSendAllowlist.SCOPE_USER,
        scope_value=str(user.id),
        environment="local",
    )
    output = StringIO()

    with (
        patch(
            "accounts.services.onboarding.lifecycle_sender._cloud_lifecycle_delivery_enabled",
            return_value=False,
        ),
        patch("accounts.services.onboarding.lifecycle_sender.email_helper") as helper,
    ):
        call_command(
            "run_onboarding_lifecycle_send",
            "--cohort",
            "internal",
            "--limit",
            "1",
            "--approval-manifest",
            str(approval_manifest),
            stdout=output,
        )

    value = output.getvalue()
    assert "sent=0" in value
    assert "suppressed=1" in value
    assert "cloud_deployment_required" in value
    helper.assert_not_called()
    assert OnboardingLifecycleSendLog.no_workspace_objects.filter(
        status=OnboardingLifecycleSendLog.STATUS_SUPPRESSED,
        suppression_reason="cloud_deployment_required",
    ).exists()


@pytest.mark.django_db
@override_settings(ONBOARDING_FEATURE_FLAGS=_flags())
def test_welcome_email_beta_defaults_to_dry_run_and_welcome_group(
    organization,
    workspace,
    user,
):
    _eligible_campaign_log(user, organization, workspace, "welcome_resume_goal")
    _eligible_campaign_log(user, organization, workspace, "prompt_create_first")
    output = StringIO()

    call_command(
        "run_onboarding_welcome_email_beta",
        "--limit",
        "10",
        stdout=output,
    )

    value = output.getvalue()
    assert "mode=dry_run" in value
    assert "campaign_group=welcome" in value
    assert "cohort=beta" in value
    assert "evaluated=1" in value
    assert "sent=0" in value
    assert not OnboardingLifecycleSendLog.no_workspace_objects.exists()


@pytest.mark.django_db
@override_settings(ONBOARDING_FEATURE_FLAGS=_flags())
def test_welcome_email_beta_send_requires_explicit_flag_and_allowlist(
    organization,
    workspace,
    user,
    tmp_path,
):
    _eligible_campaign_log(user, organization, workspace, "welcome_resume_goal")
    approval_manifest = _approval_manifest_path(tmp_path)
    OnboardingLifecycleSendAllowlist.no_workspace_objects.create(
        scope_type=OnboardingLifecycleSendAllowlist.SCOPE_USER,
        scope_value=str(user.id),
        environment="local",
        campaign_group="welcome",
    )
    output = StringIO()

    with patch("accounts.services.onboarding.lifecycle_sender.email_helper"):
        call_command(
            "run_onboarding_welcome_email_beta",
            "--send",
            "--limit",
            "1",
            "--approval-manifest",
            str(approval_manifest),
            stdout=output,
        )

    value = output.getvalue()
    assert "mode=send" in value
    assert "cohort=beta" in value
    assert "sent=1" in value
    send_log = OnboardingLifecycleSendLog.no_workspace_objects.get(
        campaign_group="welcome",
        campaign_key="welcome_resume_goal",
        status=OnboardingLifecycleSendLog.STATUS_SENT,
    )
    assert send_log.metadata["cohort"] == "beta"


@pytest.mark.django_db
@override_settings(ONBOARDING_FEATURE_FLAGS=_flags())
def test_welcome_email_beta_requires_welcome_specific_allowlist(
    organization,
    workspace,
    user,
    tmp_path,
):
    _eligible_campaign_log(user, organization, workspace, "welcome_resume_goal")
    approval_manifest = _approval_manifest_path(tmp_path)
    OnboardingLifecycleSendAllowlist.no_workspace_objects.create(
        scope_type=OnboardingLifecycleSendAllowlist.SCOPE_USER,
        scope_value=str(user.id),
        environment="local",
    )
    output = StringIO()

    with patch("accounts.services.onboarding.lifecycle_sender.email_helper"):
        call_command(
            "run_onboarding_welcome_email_beta",
            "--send",
            "--limit",
            "1",
            "--approval-manifest",
            str(approval_manifest),
            stdout=output,
        )

    value = output.getvalue()
    assert "mode=send" in value
    assert "sent=0" in value
    assert "suppressed=1" in value
    assert "not_in_send_cohort" in value
    assert OnboardingLifecycleSendLog.no_workspace_objects.filter(
        campaign_group="welcome",
        status=OnboardingLifecycleSendLog.STATUS_SUPPRESSED,
        suppression_reason="not_in_send_cohort",
    ).exists()


@pytest.mark.django_db
@override_settings(ONBOARDING_FEATURE_FLAGS=_flags())
def test_welcome_email_beta_filters_by_user_id(organization, workspace, user):
    _eligible_campaign_log(user, organization, workspace, "welcome_resume_goal")
    other_user = User.objects.create_user(
        email="welcome-filter-other@example.com",
        name="Welcome Filter Other",
        organization=organization,
    )
    _eligible_campaign_log(
        other_user,
        organization,
        workspace,
        "welcome_resume_goal",
    )
    output = StringIO()

    call_command(
        "run_onboarding_welcome_email_beta",
        "--user-id",
        str(user.id),
        "--limit",
        "10",
        stdout=output,
    )

    value = output.getvalue()
    assert "mode=dry_run" in value
    assert "campaign_group=welcome" in value
    assert "evaluated=1" in value
    assert "sent=0" in value
    assert not OnboardingLifecycleSendLog.no_workspace_objects.exists()


@pytest.mark.django_db
@override_settings(ONBOARDING_FEATURE_FLAGS=_flags())
def test_welcome_email_beta_filters_by_workspace_id(organization, workspace, user):
    _eligible_campaign_log(user, organization, workspace, "welcome_resume_goal")
    other_workspace = Workspace.no_workspace_objects.create(
        name="Welcome Filter Other Workspace",
        organization=organization,
        created_by=user,
    )
    _eligible_campaign_log(
        user,
        organization,
        other_workspace,
        "welcome_resume_goal",
    )
    output = StringIO()

    call_command(
        "run_onboarding_welcome_email_beta",
        "--workspace-id",
        str(workspace.id),
        "--limit",
        "10",
        stdout=output,
    )

    value = output.getvalue()
    assert "mode=dry_run" in value
    assert "campaign_group=welcome" in value
    assert "evaluated=1" in value
    assert "sent=0" in value
    assert not OnboardingLifecycleSendLog.no_workspace_objects.exists()


@pytest.mark.django_db
def test_welcome_email_beta_rejects_unbounded_limit():
    output = StringIO()

    with pytest.raises(CommandError, match="--limit must be 100 or lower"):
        call_command(
            "run_onboarding_welcome_email_beta",
            "--limit",
            "101",
            stdout=output,
        )


def test_welcome_email_beta_rejects_invalid_now():
    output = StringIO()

    with pytest.raises(CommandError, match="--now must be an ISO datetime"):
        call_command(
            "run_onboarding_welcome_email_beta",
            "--limit",
            "1",
            "--now",
            "not-a-date",
            stdout=output,
        )
