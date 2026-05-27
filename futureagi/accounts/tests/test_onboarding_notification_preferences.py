from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import (
    NotificationChannel,
    NotificationDeliveryLog,
    NotificationPreference,
)
from accounts.services.onboarding.notification_preferences import (
    notification_preference_decision,
    record_notification_delivery,
)


@pytest.mark.django_db
def test_notification_settings_get_returns_registered_families(auth_client):
    response = auth_client.get("/accounts/notification-preferences/")

    assert response.status_code == 200
    result = response.json()["result"]
    family_ids = {family["id"] for family in result["families"]}
    assert "product_onboarding" in family_ids
    assert "usage_budget" in family_ids
    assert result["can_manage_workspace"] is True


@pytest.mark.django_db
def test_user_can_disable_non_critical_onboarding_email(
    auth_client,
    organization,
    workspace,
    user,
):
    response = auth_client.patch(
        "/accounts/notification-preferences/",
        {
            "preferences": [
                {
                    "scope": "user_workspace",
                    "family": "product_onboarding",
                    "channel": "email",
                    "enabled": False,
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    decision = notification_preference_decision(
        organization=organization,
        workspace=workspace,
        user=user,
        family=NotificationPreference.FAMILY_PRODUCT_ONBOARDING,
        channel=NotificationPreference.CHANNEL_EMAIL,
    )
    assert decision.allowed is False
    assert decision.reason == "user_disabled_family"


@pytest.mark.django_db
def test_usage_budget_remains_owner_visible_when_user_disables_email(
    auth_client,
    organization,
    workspace,
    user,
):
    response = auth_client.patch(
        "/accounts/notification-preferences/",
        {
            "preferences": [
                {
                    "scope": "user_workspace",
                    "family": "usage_budget",
                    "channel": "email",
                    "enabled": False,
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    decision = notification_preference_decision(
        organization=organization,
        workspace=workspace,
        user=user,
        family=NotificationPreference.FAMILY_USAGE_BUDGET,
        channel=NotificationPreference.CHANNEL_EMAIL,
    )
    assert decision.allowed is True
    assert decision.reason == "critical_family_owner_visible"


@pytest.mark.django_db
def test_slack_channel_is_masked_and_testable(auth_client):
    response = auth_client.patch(
        "/accounts/notification-preferences/",
        {
            "channels": [
                {
                    "scope": "workspace",
                    "type": "slack_webhook",
                    "display_name": "Workspace alerts",
                    "config": {
                        "webhook_url": (
                            "https://hooks.slack.com/services/T000/B000/secret"
                        )
                    },
                    "is_active": True,
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    channel = NotificationChannel.no_workspace_objects.get()
    assert (
        "secret"
        not in response.json()["result"]["channels"][0]["config"]["webhook_url"]
    )

    test_response = auth_client.post(
        f"/accounts/notification-channels/{channel.id}/test/",
        {},
        format="json",
    )

    channel.refresh_from_db()
    assert test_response.status_code == 200
    assert channel.last_test_status == NotificationChannel.STATUS_READY
    assert NotificationDeliveryLog.no_workspace_objects.filter(
        source_id=str(channel.id),
        notification_key="notification_channel_test",
    ).exists()


@pytest.mark.django_db
def test_delivery_log_idempotency_updates_existing_row(organization, workspace, user):
    key = "usage_budget:test:2026-05:80:email"
    record_notification_delivery(
        organization=organization,
        workspace=workspace,
        user=user,
        family=NotificationPreference.FAMILY_USAGE_BUDGET,
        source_type="usage_budget",
        source_id="budget-1",
        channel=NotificationPreference.CHANNEL_EMAIL,
        status=NotificationDeliveryLog.STATUS_SUPPRESSED,
        suppressed_reason="frequency_cap",
        idempotency_key=key,
        stage="80",
        severity="warning",
        now=timezone.now() - timedelta(minutes=5),
    )
    record_notification_delivery(
        organization=organization,
        workspace=workspace,
        user=user,
        family=NotificationPreference.FAMILY_USAGE_BUDGET,
        source_type="usage_budget",
        source_id="budget-1",
        channel=NotificationPreference.CHANNEL_EMAIL,
        status=NotificationDeliveryLog.STATUS_SENT,
        idempotency_key=key,
        stage="80",
        severity="warning",
    )

    logs = NotificationDeliveryLog.no_workspace_objects.filter(idempotency_key=key)
    assert logs.count() == 1
    assert logs.get().status == NotificationDeliveryLog.STATUS_SENT
