from datetime import timedelta

from accounts.models import OnboardingLifecycleEvaluationLog


def frequency_cap_suppression(*, user, workspace, campaign, now):
    if not user or not workspace or not campaign:
        return None

    eligible_logs = OnboardingLifecycleEvaluationLog.no_workspace_objects.filter(
        status=OnboardingLifecycleEvaluationLog.STATUS_ELIGIBLE,
        evaluated_at__gte=now - timedelta(days=7),
    )

    user_week = eligible_logs.filter(user=user).count()
    if user_week >= 3:
        return "frequency_cap_user_7d"

    user_day = eligible_logs.filter(
        user=user,
        evaluated_at__gte=now - timedelta(hours=24),
    ).count()
    if user_day >= 1:
        return "frequency_cap_user_24h"

    workspace_day = eligible_logs.filter(
        workspace=workspace,
        evaluated_at__gte=now - timedelta(hours=24),
    ).count()
    if workspace_day >= 5:
        return "frequency_cap_workspace_24h"

    campaign_week = eligible_logs.filter(
        user=user,
        campaign_key=campaign["campaign_key"],
    ).count()
    if campaign_week >= 1:
        if campaign.get("frequency_cap_key") == "sample_bridge":
            return "frequency_cap_campaign_7d"
        return "frequency_cap_campaign_7d"

    return None
