from accounts.services.onboarding.constants import PRODUCT_PATHS


def route_entry(href, is_available=True, reason=None):
    return {
        "href": href,
        "is_available": is_available,
        "reason": None if is_available else reason,
    }


def _available_if(flag, href, reason="feature_disabled"):
    return route_entry(href, is_available=bool(flag), reason=reason)


def _sample_route(flags, sample_project):
    if not flags.get("onboarding_sample_project"):
        return _available_if(False, "/dashboard/home?sample=true")
    if not sample_project:
        return route_entry("/dashboard/home?sample=true")
    if sample_project.get("is_hidden"):
        return route_entry(
            sample_project.get("href") or "/dashboard/home?sample=true",
            is_available=False,
            reason=sample_project.get("blocked_reason") or "sample_hidden",
        )
    if not sample_project.get("available"):
        return route_entry(
            sample_project.get("href") or "/dashboard/home?sample=true",
            is_available=False,
            reason=sample_project.get("blocked_reason") or "sample_artifact_missing",
        )
    return route_entry(
        sample_project.get("entry_route")
        or sample_project.get("href")
        or "/dashboard/home?sample=true"
    )


def resolve_route_availability(*, context, flags, signals, sample_project=None):
    can_write = context.permissions["can_write"]
    first_observe_id = signals.first_observe_id
    first_trace_id = signals.first_trace_id

    routes = {
        "home": route_entry("/dashboard/home"),
        "get_started": route_entry("/dashboard/get-started"),
        "workspace_list": route_entry("/dashboard/settings/user-management"),
        "choose_goal": _available_if(
            flags.get("onboarding_goal_picker"),
            "/dashboard/home?mode=choose-goal",
        ),
        "observe_setup": route_entry(
            "/dashboard/observe?setup=true&source=onboarding",
            is_available=can_write,
            reason="missing_permission",
        ),
        "observe_project": route_entry(
            f"/dashboard/observe/{first_observe_id}"
            if first_observe_id
            else "/dashboard/observe",
            is_available=bool(first_observe_id),
            reason="missing_id",
        ),
        "observe_trace_detail": route_entry(
            (
                f"/dashboard/observe/{first_observe_id}/trace/{first_trace_id}"
                if first_observe_id and first_trace_id
                else "/dashboard/observe"
            ),
            is_available=bool(first_observe_id and first_trace_id),
            reason="missing_id",
        ),
        "observe_dashboard": route_entry(
            f"/dashboard/observe/{first_observe_id}"
            if first_observe_id
            else "/dashboard/observe",
            is_available=True,
        ),
        "sample_trace": _sample_route(flags, sample_project),
        "support": route_entry("/dashboard/get-started?support=true"),
        "daily_quality_home": _available_if(
            flags.get("onboarding_daily_quality_home"),
            "/dashboard/home?mode=daily-quality",
        ),
    }

    for path in PRODUCT_PATHS:
        routes[f"path_{path}"] = route_entry(
            f"/dashboard/home?path={path}",
            is_available=path in {"observe", "sample"}
            and not (
                path == "sample" and sample_project and sample_project["is_hidden"]
            ),
            reason=(
                sample_project.get("blocked_reason") or "sample_hidden"
                if path == "sample" and sample_project and sample_project["is_hidden"]
                else "route_not_implemented"
            ),
        )
    return routes
