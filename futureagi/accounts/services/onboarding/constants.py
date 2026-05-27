from accounts.services.onboarding.flow_config import (
    configured_action_kinds,
    configured_activation_event_aliases,
    configured_activation_events,
    configured_goal_aliases,
    configured_goal_ids,
    configured_path_aliases,
    configured_product_paths,
    configured_stage_ids,
)

ACTIVATION_SCHEMA_VERSION = "activation-state-2026-05-26.v1"

ONBOARDING_GOALS = configured_goal_ids()
ONBOARDING_GOAL_ALIASES = configured_goal_aliases()

PRODUCT_PATHS = configured_product_paths()
PRODUCT_PATH_ALIASES = configured_path_aliases()

ACTIVATION_STAGES = configured_stage_ids()

HOME_MODES = (
    "first_run",
    "daily_quality",
    "fallback",
)

ACTION_KINDS = configured_action_kinds()

PROGRESS_KEYS = (
    "build",
    "test",
    "observe",
    "ship",
    "improve",
)

PROGRESS_STATES = (
    "not_started",
    "available",
    "selected",
    "in_progress",
    "blocked",
    "complete",
    "sample_only",
)

SAMPLE_PROJECT_STATUSES = (
    "not_created",
    "unavailable",
    "available",
    "creating",
    "ready_for_observe",
    "partially_ready",
    "ready",
    "partial",
    "hidden",
    "stale_manifest",
    "repair_required",
    "repair_failed",
)

LIFECYCLE_ELIGIBILITY_STATES = (
    "eligible",
    "suppressed",
    "skipped",
    "error",
)

LIFECYCLE_SUPPRESSION_REASONS = (
    "activated",
    "target_event_complete",
    "frequency_cap",
    "workspace_suppressed",
    "user_unsubscribed",
    "sample_hidden",
    "route_unavailable",
    "permission_limited",
    "feature_disabled",
    "recent_goal_change",
    "manual_pause",
)

ROUTE_AVAILABILITY_STATES = (
    "available",
    "unavailable",
)

ROUTE_UNAVAILABLE_REASONS = (
    "feature_disabled",
    "missing_id",
    "missing_permission",
    "plan_blocked",
    "route_not_implemented",
    "sample_artifact_missing",
    "sample_hidden",
    "target_event_complete",
    "workspace_missing",
)

EMAIL_CONTEXT_STATUSES = (
    "current",
    "stale",
    "expired",
    "invalid",
    "complete",
    "route_unavailable",
)

AVAILABLE_PATH_STATUSES = (
    "available",
    "selected",
    "in_progress",
    "blocked",
    "complete",
    "sample_only",
    "hidden",
)

ONBOARDING_ACTIVATION_EVENTS = configured_activation_events()
ONBOARDING_ACTIVATION_EVENT_ALIASES = configured_activation_event_aliases()


def choices(values):
    return tuple((value, value) for value in values)


def canonical_goal(value):
    return ONBOARDING_GOAL_ALIASES.get(value, value)


def canonical_path(value):
    return PRODUCT_PATH_ALIASES.get(value, value)


def canonical_activation_event(value):
    return ONBOARDING_ACTIVATION_EVENT_ALIASES.get(value, value)
