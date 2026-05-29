"""Bridge registration for tracer ViewSets — traces, spans, sessions,
eval tasks, alert monitors. Tool names auto-derived.
"""

from ai_tools.drf_bridge import expose_to_mcp
from tracer.views.eval_task import EvalTaskView
from tracer.views.monitor import UserAlertMonitorLogView, UserAlertMonitorView
from tracer.views.observation_span import ObservationSpanView
from tracer.views.project_version import ProjectVersionView
from tracer.views.trace import TraceView
from tracer.views.trace_session import TraceSessionView

# entity 'trace' -> list_traces, get_trace, etc.
expose_to_mcp(category="tracing")(TraceView)

# export_traces_csv -> TraceView.get_trace_export_data (custom @action,
# detail=False, GET): the same trace CSV export the Observe UI offers (TH-5415).
# It returns a FileResponse (text/csv) / HttpResponse, surfaced as CSV text by
# the bridge's _unwrap_response. project_id is required; filters is the optional
# JSON filter list the UI passes (omit it to export all traces in the project).
expose_to_mcp(
    category="tracing",
    tools={
        "get_trace_export_data": {
            "name": "export_traces_csv",
            "method": "GET",
            "description": (
                "Export a trace project's traces as CSV (the same export the "
                "Observe UI offers). Provide `project_id`; omit `filters` to "
                "export all traces. Returns CSV text."
            ),
            "query_params": {
                "project_id": {
                    "type": str,
                    "required": True,
                    "description": "UUID of the trace project to export.",
                },
                "filters": {
                    "type": str,
                    "required": False,
                    "description": (
                        "Optional JSON-encoded filter list (same shape the "
                        "Observe UI sends); omit to export all traces."
                    ),
                },
            },
        }
    },
)(TraceView)

# entity 'observation_span' -> list_observation_spans, get_observation_span
# but existing tools call them 'list_spans', 'get_span' — override the names.
expose_to_mcp(
    category="tracing",
    tools={
        "list": {"name": "list_spans"},
        "retrieve": {"name": "get_span"},
    },
)(ObservationSpanView)

# Trace sessions: list_sessions, get_session (get_session was deleted as
# composite — bridge gives us a clean REST replacement)
expose_to_mcp(
    category="tracing",
    tools={
        "list": {"name": "list_sessions"},
        "retrieve": {"name": "get_session"},
    },
)(TraceSessionView)

# Eval tasks: list_eval_tasks, get_eval_task, update_eval_task
expose_to_mcp(
    category="tracing",
    tools={
        "list": {"name": "list_eval_tasks"},
        "retrieve": {"name": "get_eval_task"},
        "create": {"name": "create_eval_task"},
        "update": {"name": "update_eval_task"},
        "destroy": {"name": "delete_eval_task"},
    },
)(EvalTaskView)

# Alert monitors: list_alert_monitors, create_alert_monitor, etc.
expose_to_mcp(
    category="tracing",
    tools={
        "list": {"name": "list_alert_monitors"},
        "retrieve": {"name": "get_alert_monitor"},
        "create": {"name": "create_alert_monitor"},
        "update": {"name": "update_alert_monitor"},
        "destroy": {"name": "delete_alert_monitor"},
    },
)(UserAlertMonitorView)

expose_to_mcp(
    category="tracing",
    tools={
        "list": {"name": "list_alert_monitor_logs"},
        "retrieve": {"name": "get_alert_monitor_log"},
    },
)(UserAlertMonitorLogView)

# Project versions (experiments use these)
expose_to_mcp(category="experiments")(ProjectVersionView)
