from __future__ import annotations

from datetime import timedelta

from django.db import transaction

from accounts.models import OnboardingQualityAction
from accounts.services.onboarding.activation_events import events_for_workspace

ACTION_OPEN_EVENTS = (
    "daily_quality_action_created",
    "daily_quality_action_opened",
    "daily_quality_action_assigned",
)
ACTION_CLOSE_EVENTS = (
    "daily_quality_action_completed",
    "daily_quality_action_dismissed",
)
ACTION_EVENTS = (*ACTION_OPEN_EVENTS, *ACTION_CLOSE_EVENTS)

DEFAULT_ACTION_LABEL = "Continue quality action"
DEFAULT_ACTION_BODY = "Return to unresolved quality work from a previous review."
DEFAULT_ACTION_ROUTE = "/dashboard/home"
DEFAULT_ACTION_FALLBACK_ROUTE = "/dashboard/get-started"


def internal_route(href):
    return isinstance(href, str) and href.startswith("/") and not href.startswith("//")


def safe_metadata_text(metadata, key, fallback, *, limit=180):
    value = (metadata or {}).get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()[:limit]
    return fallback


def action_identity_from_event(event):
    metadata = event.metadata or {}
    explicit_id = metadata.get("action_id") or metadata.get("quality_action_id")
    if explicit_id:
        return str(explicit_id)[:160]
    source_type = metadata.get("source_type") or metadata.get("artifact_type")
    source_id = metadata.get("source_id") or metadata.get("artifact_id")
    if source_type and source_id:
        return f"{source_type}:{source_id}"[:160]
    return str(event.id)


def compact_action_metadata(metadata):
    return {
        key: value
        for key, value in (metadata or {}).items()
        if value is not None and value != ""
    }


def _route_from_metadata(metadata, key, fallback):
    route = metadata.get(key)
    if key == "route":
        route = route or metadata.get("href")
    return route if internal_route(route) else fallback


def _assigned_user_id(metadata):
    assigned_to_user_id = metadata.get("assigned_to_user_id")
    if assigned_to_user_id:
        return assigned_to_user_id
    assigned_to = metadata.get("assigned_to")
    return assigned_to if assigned_to else None


def _action_defaults_from_event(event, action_key):
    metadata = compact_action_metadata(event.metadata)
    source_type = metadata.get("source_type") or metadata.get("artifact_type")
    source_id = metadata.get("source_id") or metadata.get("artifact_id")
    assigned_to_user_id = _assigned_user_id(metadata)
    return {
        "organization": event.organization,
        "workspace": event.workspace,
        "created_by": event.user,
        "assigned_to_id": assigned_to_user_id,
        "product_path": event.product_path,
        "action_key": action_key,
        "label": safe_metadata_text(metadata, "label", DEFAULT_ACTION_LABEL),
        "body": safe_metadata_text(
            metadata,
            "body",
            DEFAULT_ACTION_BODY,
            limit=300,
        ),
        "route": _route_from_metadata(metadata, "route", DEFAULT_ACTION_ROUTE),
        "fallback_route": _route_from_metadata(
            metadata,
            "fallback_route",
            DEFAULT_ACTION_FALLBACK_ROUTE,
        ),
        "source_type": str(source_type or "workspace")[:64],
        "source_id": str(source_id or event.workspace_id)[:128],
        "is_sample": event.is_sample,
        "last_event_at": event.occurred_at,
        "metadata": metadata,
    }


def _merged_defaults(record, defaults):
    metadata = {
        **(record.metadata or {}),
        **defaults["metadata"],
    }
    source_type = defaults["metadata"].get("source_type") or defaults["metadata"].get(
        "artifact_type"
    )
    source_id = defaults["metadata"].get("source_id") or defaults["metadata"].get(
        "artifact_id"
    )
    return {
        **defaults,
        "created_by": record.created_by or defaults["created_by"],
        "assigned_to_id": defaults["assigned_to_id"] or record.assigned_to_id,
        "label": defaults["label"]
        if defaults["label"] != DEFAULT_ACTION_LABEL
        else record.label,
        "body": defaults["body"]
        if defaults["body"] != DEFAULT_ACTION_BODY
        else record.body,
        "route": defaults["route"]
        if defaults["route"] != DEFAULT_ACTION_ROUTE
        else record.route,
        "fallback_route": defaults["fallback_route"]
        if defaults["fallback_route"] != DEFAULT_ACTION_FALLBACK_ROUTE
        else record.fallback_route,
        "source_type": defaults["source_type"] if source_type else record.source_type,
        "source_id": defaults["source_id"] if source_id else record.source_id,
        "metadata": metadata,
    }


def _apply_status_fields(record, event):
    if event.event_name in ACTION_OPEN_EVENTS:
        record.status = OnboardingQualityAction.STATUS_OPEN
        if event.event_name in {
            "daily_quality_action_created",
            "daily_quality_action_opened",
        }:
            record.opened_at = record.opened_at or event.occurred_at
        if event.event_name == "daily_quality_action_assigned":
            record.assigned_at = event.occurred_at
        record.completed_at = None
        record.dismissed_at = None
    elif event.event_name == "daily_quality_action_completed":
        record.status = OnboardingQualityAction.STATUS_COMPLETED
        record.completed_at = event.occurred_at
    elif event.event_name == "daily_quality_action_dismissed":
        record.status = OnboardingQualityAction.STATUS_DISMISSED
        record.dismissed_at = event.occurred_at


def sync_quality_action_for_event(event):
    if event.event_name not in ACTION_EVENTS:
        return None
    if event.is_sample or not event.product_path:
        return None

    action_key = action_identity_from_event(event)
    defaults = _action_defaults_from_event(event, action_key)
    with transaction.atomic():
        record, created = OnboardingQualityAction.no_workspace_objects.get_or_create(
            organization=event.organization,
            workspace=event.workspace,
            product_path=event.product_path,
            action_key=action_key,
            defaults={
                **defaults,
                "status": OnboardingQualityAction.STATUS_OPEN,
                "opened_at": event.occurred_at,
            },
        )
        if not created and record.last_event_at > event.occurred_at:
            return record
        if not created:
            for field, value in _merged_defaults(record, defaults).items():
                setattr(record, field, value)
        _apply_status_fields(record, event)
        record.last_event_at = event.occurred_at
        record.save()
        return record


def _action_dict_from_record(record):
    return {
        "id": record.action_key,
        "label": record.label or DEFAULT_ACTION_LABEL,
        "body": record.body or DEFAULT_ACTION_BODY,
        "route": record.route if internal_route(record.route) else DEFAULT_ACTION_ROUTE,
        "fallback_route": record.fallback_route
        if internal_route(record.fallback_route)
        else DEFAULT_ACTION_FALLBACK_ROUTE,
        "route_available": True,
        "source_type": record.source_type or "workspace",
        "source_id": record.source_id or str(record.workspace_id),
        "success_event": "daily_quality_action_completed",
        "is_primary": False,
        "is_sample": False,
        "requires_permission": None,
        "activation_kind": "daily_quality",
    }


def _action_dict_from_event(context, action_key, event, metadata):
    route = _route_from_metadata(metadata, "route", DEFAULT_ACTION_ROUTE)
    fallback_route = _route_from_metadata(
        metadata,
        "fallback_route",
        DEFAULT_ACTION_FALLBACK_ROUTE,
    )
    source_type = metadata.get("source_type") or metadata.get("artifact_type")
    source_id = metadata.get("source_id") or metadata.get("artifact_id")
    return {
        "id": action_key,
        "label": safe_metadata_text(metadata, "label", DEFAULT_ACTION_LABEL),
        "body": safe_metadata_text(
            metadata,
            "body",
            DEFAULT_ACTION_BODY,
            limit=300,
        ),
        "route": route,
        "fallback_route": fallback_route,
        "route_available": True,
        "source_type": str(source_type or "workspace"),
        "source_id": str(source_id) if source_id else str(context.workspace.id),
        "success_event": "daily_quality_action_completed",
        "is_primary": False,
        "is_sample": False,
        "requires_permission": None,
        "activation_kind": "daily_quality",
    }


def _event_derived_open_actions(context, now, *, lookback_days):
    events = events_for_workspace(
        organization=context.organization,
        workspace=context.workspace,
        event_names=ACTION_EVENTS,
        product_path=context.primary_path or "observe",
        is_sample=False,
        limit=500,
    )
    since = now - timedelta(days=lookback_days)
    latest_by_action = {}
    metadata_by_action = {}
    for event in reversed(events):
        if event.occurred_at < since:
            continue
        action_key = action_identity_from_event(event)
        metadata_by_action[action_key] = {
            **metadata_by_action.get(action_key, {}),
            **compact_action_metadata(event.metadata),
        }
        latest_by_action[action_key] = event

    actions = []
    for action_key, event in latest_by_action.items():
        if event.event_name in ACTION_CLOSE_EVENTS:
            continue
        actions.append(
            (
                event.occurred_at,
                _action_dict_from_event(
                    context,
                    action_key,
                    event,
                    metadata_by_action.get(action_key) or event.metadata or {},
                ),
            )
        )
    return actions


def open_quality_actions_for_context(context, now, *, limit=5, lookback_days=30):
    if not context.organization or not context.workspace:
        return []

    since = now - timedelta(days=lookback_days)
    path = context.primary_path or "observe"
    records = list(
        OnboardingQualityAction.no_workspace_objects.filter(
            organization=context.organization,
            workspace=context.workspace,
            product_path=path,
            status=OnboardingQualityAction.STATUS_OPEN,
            is_sample=False,
            last_event_at__gte=since,
        ).order_by("-last_event_at", "action_key")[:limit]
    )
    merged = [
        (record.last_event_at, _action_dict_from_record(record)) for record in records
    ]
    existing_ids = {action["id"] for _timestamp, action in merged}
    for timestamp, action in _event_derived_open_actions(
        context,
        now,
        lookback_days=lookback_days,
    ):
        if action["id"] in existing_ids:
            continue
        merged.append((timestamp, action))

    return [
        action
        for _timestamp, action in sorted(
            merged,
            key=lambda item: (item[0], item[1]["id"]),
            reverse=True,
        )[:limit]
    ]
