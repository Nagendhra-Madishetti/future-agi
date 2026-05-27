from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from model_hub.models.ai_model import AIModel
from tracer.models.observation_span import ObservationSpan
from tracer.models.project import Project, ProjectSourceChoices
from tracer.models.trace import Trace
from tracer.models.trace_session import TraceSession

REQUIRED_ROUTE_KEYS = ("observe_project", "sample_trace")


def _default_tags(manifest):
    return list(
        (manifest.get("defaults") or {}).get("tags") or ["sample", "onboarding"]
    )


def _configured_span_keys(manifest):
    spans = ((manifest or {}).get("artifacts") or {}).get("spans") or {}
    return tuple(spans.keys())


def _manifest_for_sample(sample_project, manifest=None):
    if manifest is not None:
        return manifest
    from accounts.services.onboarding.sample_manifest import get_sample_manifest

    return get_sample_manifest(
        sample_project.manifest_id,
        sample_project.manifest_version,
    )


def sample_trace_route(project_id, trace_id):
    if not project_id or not trace_id:
        return None
    return (
        f"/dashboard/observe/{project_id}/trace/{trace_id}?sample=true&from=onboarding"
    )


def sample_project_route(project_id):
    if not project_id:
        return None
    return f"/dashboard/observe/{project_id}?sample=true&from=onboarding"


def sample_metadata(manifest, stable_key, *, artifact_type, extra=None):
    metadata = {
        "is_sample": True,
        "sample_manifest_id": manifest["manifest_id"],
        "sample_manifest_version": manifest["manifest_version"],
        "sample_stable_key": stable_key,
        "sample_label": manifest["sample_label"],
        "onboarding_path": "observe",
        "artifact_type": artifact_type,
    }
    if extra:
        metadata.update(extra)
    return metadata


def _artifact_id(refs, *keys):
    value = refs
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _safe_get(model, object_id, **scope):
    if not object_id:
        return None
    try:
        return model.no_workspace_objects.filter(id=object_id, **scope).first()
    except (TypeError, ValueError, ValidationError):
        return None


def _sample_project_query(sample_project, manifest, stable_key):
    return Project.no_workspace_objects.filter(
        organization=sample_project.organization,
        workspace=sample_project.workspace,
        trace_type="observe",
        metadata__is_sample=True,
        metadata__sample_manifest_id=manifest["manifest_id"],
        metadata__sample_manifest_version=manifest["manifest_version"],
        metadata__sample_stable_key=stable_key,
    )


def _ensure_project(sample_project, manifest, refs):
    config = manifest["artifacts"]["observe_project"]
    stable_key = config["stable_key"]
    project = _safe_get(
        Project,
        _artifact_id(refs, "observe_project", "id"),
        organization=sample_project.organization,
        workspace=sample_project.workspace,
        trace_type="observe",
    )
    if project is None:
        project = _sample_project_query(sample_project, manifest, stable_key).first()
    if project is None:
        try:
            with transaction.atomic():
                project = Project.no_workspace_objects.create(
                    name=config["display_name"],
                    organization=sample_project.organization,
                    workspace=sample_project.workspace,
                    user=sample_project.first_opened_by,
                    model_type=AIModel.ModelTypes.GENERATIVE_LLM,
                    trace_type="observe",
                    source=ProjectSourceChoices.DEMO.value,
                    metadata=sample_metadata(
                        manifest,
                        stable_key,
                        artifact_type="observe_project",
                        extra={
                            "domain": manifest["domain"],
                            **(config.get("metadata") or {}),
                        },
                    ),
                    tags=config.get("tags") or _default_tags(manifest),
                )
        except IntegrityError:
            project = Project.no_workspace_objects.get(
                name=config["display_name"],
                organization=sample_project.organization,
                workspace=sample_project.workspace,
                trace_type="observe",
            )
            if not (project.metadata or {}).get("is_sample"):
                raise
    refs["observe_project"] = {
        "id": str(project.id),
        "route": sample_project_route(project.id),
    }
    return project


def _ensure_session(project, manifest, refs):
    config = manifest["artifacts"]["trace_session"]
    session = _safe_get(
        TraceSession,
        _artifact_id(refs, "trace_session", "id"),
        project=project,
    )
    if session is None:
        session = TraceSession.no_workspace_objects.create(
            project=project,
            name=config["display_name"],
            bookmarked=config.get("bookmarked", True),
        )
    refs["trace_session"] = {"id": str(session.id)}
    return session


def _ensure_trace(project, session, manifest, refs):
    config = manifest["artifacts"]["sample_trace"]
    stable_key = config["stable_key"]
    trace = _safe_get(
        Trace,
        _artifact_id(refs, "sample_trace", "id"),
        project=project,
    )
    if trace is None:
        trace = (
            Trace.no_workspace_objects.filter(
                project=project,
                external_id=config["external_id"],
                metadata__is_sample=True,
                metadata__sample_stable_key=stable_key,
            )
            .order_by("created_at")
            .first()
        )
    if trace is None:
        trace = Trace.no_workspace_objects.create(
            project=project,
            session=session,
            name=config["display_name"],
            external_id=config["external_id"],
            input=config["input"],
            output=config["output"],
            metadata=sample_metadata(
                manifest,
                stable_key,
                artifact_type="trace",
                extra=config.get("metadata") or {},
            ),
            tags=config.get("tags") or _default_tags(manifest),
        )
    elif trace.session_id != session.id:
        trace.session = session
        trace.save(update_fields=["session", "updated_at"])
    refs["sample_trace"] = {
        "id": str(trace.id),
        "route": sample_trace_route(project.id, trace.id),
    }
    return trace


def _span_id(sample_project, span_key):
    return f"sample-{sample_project.id.hex}-{span_key}"


def _span_defaults(project, trace, manifest, span_config, *, now, parent_id=None):
    stable_key = span_config["stable_key"]
    defaults = manifest.get("defaults") or {}
    timing = span_config["timing_ms"]
    span_attributes = {
        **(defaults.get("span_attributes") or {}),
        "futureagi.sample_stable_key": stable_key,
        **(span_config.get("span_attributes") or {}),
    }
    base = {
        "project": project,
        "trace": trace,
        "parent_span_id": parent_id,
        "metadata": sample_metadata(
            manifest,
            stable_key,
            artifact_type="span",
            extra=span_config.get("metadata") or {},
        ),
        "tags": span_config.get("tags") or _default_tags(manifest),
        "status": span_config.get("status", "OK"),
        "span_attributes": span_attributes,
        "resource_attributes": span_config.get("resource_attributes")
        or defaults.get("resource_attributes")
        or {},
        "semconv_source": span_config.get("semconv_source")
        or defaults.get("semconv_source"),
        "name": span_config["name"],
        "observation_type": span_config["observation_type"],
        "start_time": now + timedelta(milliseconds=timing["start"]),
        "end_time": now + timedelta(milliseconds=timing["end"]),
        "latency_ms": timing["latency"],
        "input": span_config["input"],
        "output": span_config["output"],
    }
    for key in (
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost",
    ):
        if key in span_config:
            base[key] = span_config[key]
    return base


def _ensure_spans(sample_project, project, trace, manifest, refs):
    span_configs = manifest["artifacts"]["spans"]
    now = timezone.now() - timedelta(minutes=5)
    spans = refs.setdefault("spans", {})
    created = {}

    for key, span_config in span_configs.items():
        span_id = _span_id(sample_project, key)
        parent_key = span_config.get("parent")
        parent_id = created.get(parent_key) or spans.get(parent_key)
        ObservationSpan.no_workspace_objects.update_or_create(
            id=span_id,
            defaults=_span_defaults(
                project,
                trace,
                manifest,
                span_config,
                now=now,
                parent_id=parent_id,
            ),
        )
        spans[key] = span_id
        created[key] = span_id

    refs["spans"] = spans
    return span_configs


def validate_sample_artifacts(sample_project, manifest=None):
    manifest = _manifest_for_sample(sample_project, manifest)
    refs = sample_project.artifact_refs or {}
    missing = []
    project = _safe_get(
        Project,
        _artifact_id(refs, "observe_project", "id"),
        organization=sample_project.organization,
        workspace=sample_project.workspace,
        trace_type="observe",
    )
    if project is None:
        missing.append("observe_project")

    trace = None
    if project is not None:
        trace = _safe_get(
            Trace,
            _artifact_id(refs, "sample_trace", "id"),
            project=project,
        )
    if trace is None:
        missing.append("sample_trace")

    if project is not None:
        session = _safe_get(
            TraceSession,
            _artifact_id(refs, "trace_session", "id"),
            project=project,
        )
        if session is None:
            missing.append("trace_session")

    spans = refs.get("spans") or {}
    for span_key in _configured_span_keys(manifest):
        span_id = spans.get(span_key)
        if (
            not span_id
            or not ObservationSpan.no_workspace_objects.filter(
                id=span_id,
                project=project,
                trace=trace,
            ).exists()
        ):
            missing.append(f"span:{span_key}")

    entry_route = None
    if project is not None and trace is not None:
        entry_route = sample_trace_route(project.id, trace.id)
    return {
        "missing_artifacts": missing,
        "entry_route": entry_route,
        "route_ready": bool(entry_route),
        "project": project,
        "trace": trace,
    }


def ensure_observe_sample_artifacts(sample_project, manifest):
    refs = dict(sample_project.artifact_refs or {})
    project = _ensure_project(sample_project, manifest, refs)
    session = _ensure_session(project, manifest, refs)
    trace = _ensure_trace(project, session, manifest, refs)
    _ensure_spans(sample_project, project, trace, manifest, refs)
    sample_project.artifact_refs = refs
    validation = validate_sample_artifacts(sample_project, manifest)
    return {
        "artifact_refs": refs,
        **validation,
    }
