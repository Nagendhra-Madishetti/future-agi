"""Bridge registration for simulation detail APIViews.

Surfaces the FULL existing DRF responses through the bridge instead of
hand-written tools, so MCP and the UI share one source of truth:

- get_call_execution -> CallExecutionDetailView: full call detail including
  turn/latency/WPM/talk-ratio/interruption analytics (TH-5397).
- get_scenario -> ScenarioDetailView: full scenario detail including the
  scenario graph (nodes/edges) (TH-5375).
"""

from ai_tools.drf_bridge import expose_to_mcp
from simulate.views.run_test import CallExecutionDetailView, CSVExportView
from simulate.views.scenarios import ScenarioDetailView

# Detail GET handlers take the id as a named URL kwarg (call_execution_id /
# scenario_id), so the bridge needs pk_kwarg to route the id correctly.
# Use the "retrieve" action: it's a DETAIL action (so the bridge builds an `id`
# input param and routes it), and for an APIView it resolves to the `.get()`
# handler. pk_kwarg names the handler's URL kwarg (call_execution_id /
# scenario_id) so the id reaches `get(request, <kwarg>=id)`.
expose_to_mcp(
    category="agents",
    tools={"retrieve": {"name": "get_call_execution", "pk_kwarg": "call_execution_id"}},
)(CallExecutionDetailView)

expose_to_mcp(
    category="simulation",
    tools={"retrieve": {"name": "get_scenario", "pk_kwarg": "scenario_id"}},
)(ScenarioDetailView)

# export_test_execution_csv -> CSVExportView.get(request, item_id): the same
# "Export Data" CSV the Simulate UI offers (TH-5386). It's a detail GET keyed by
# item_id with a required `type` (runtest|testexecution) plus optional
# search/status. The bridge collects the id + those query params (detail +
# query_params), routes item_id to the URL kwarg, and the CSV body is returned
# as text via _unwrap_response.
expose_to_mcp(
    category="agents",
    tools={
        "retrieve": {
            "name": "export_test_execution_csv",
            "pk_kwarg": "item_id",
            "entity": "run test or test execution",
            "description": (
                "Export a run test's or test execution's call data as CSV "
                "(the same export the Simulate UI offers). Provide `id` (the "
                "run test id or test execution id) and `type` to say which it "
                "is. Returns CSV text."
            ),
            "query_params": {
                "type": {
                    "type": str,
                    "required": True,
                    "description": (
                        "Export source type: 'runtest' (id is a run test id) "
                        "or 'testexecution' (id is a test execution id)."
                    ),
                },
                "search": {
                    "type": str,
                    "required": False,
                    "description": "Optional call-execution search term.",
                },
                "status": {
                    "type": str,
                    "required": False,
                    "description": "Optional call-execution status filter.",
                },
            },
        }
    },
)(CSVExportView)
