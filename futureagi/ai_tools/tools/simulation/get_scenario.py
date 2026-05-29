from uuid import UUID

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field

from ai_tools.base import BaseTool, ToolContext, ToolResult
from ai_tools.formatting import (
    format_datetime,
    format_status,
    key_value_block,
    section,
    truncate,
)
from ai_tools.registry import register_tool


class GetScenarioInput(PydanticBaseModel):
    scenario_id: UUID = Field(description="The UUID of the scenario to retrieve")


@register_tool
class GetScenarioTool(BaseTool):
    name = "get_scenario"
    description = (
        "Returns detailed information about a specific test scenario, "
        "including name, type, source, dataset info, and associated agent."
    )
    category = "simulation"
    input_model = GetScenarioInput

    def execute(self, params: GetScenarioInput, context: ToolContext) -> ToolResult:

        from simulate.models.scenarios import Scenarios

        try:
            scenario = Scenarios.objects.select_related(
                "agent_definition", "dataset"
            ).get(
                id=params.scenario_id,
                organization=context.organization,
                deleted=False,
            )
        except Scenarios.DoesNotExist:
            return ToolResult.not_found("Scenario", str(params.scenario_id))

        agent_name = (
            scenario.agent_definition.agent_name if scenario.agent_definition else "—"
        )
        dataset_name = scenario.dataset.name if scenario.dataset else "—"
        dataset_id = str(scenario.dataset.id) if scenario.dataset else None

        info = key_value_block(
            [
                ("ID", f"`{scenario.id}`"),
                ("Name", scenario.name),
                ("Type", scenario.scenario_type),
                ("Status", format_status(scenario.status) if scenario.status else "—"),
                ("Agent", agent_name),
                ("Source Type", scenario.source_type or "—"),
                ("Source", truncate(scenario.source, 500) if scenario.source else "—"),
                (
                    "Dataset",
                    f"{dataset_name} (`{dataset_id}`)" if dataset_id else "—",
                ),
                (
                    "Description",
                    (
                        truncate(scenario.description, 300)
                        if scenario.description
                        else "—"
                    ),
                ),
                ("Created", format_datetime(scenario.created_at)),
                ("Updated", format_datetime(scenario.updated_at)),
            ]
        )

        content = section(f"Scenario: {scenario.name}", info)

        # Metadata
        if scenario.metadata:
            content += "\n\n### Metadata\n\n"
            content += f"```json\n{truncate(str(scenario.metadata), 500)}\n```"

        # Scenario graph: the node/branch structure lives in ScenarioGraph ->
        # cases (each case's `case_data` JSON holds nodes/branches). Surfacing
        # it here gives MCP a read path into the scenario graph so edits aren't
        # blind (TH-5375). The full case_data is returned in `data` for
        # programmatic use.
        graphs = list(scenario.graphs.filter(is_active=True).order_by("-created_at"))
        graph_data = []
        if graphs:
            content += "\n\n### Scenario Graph\n"
            for g in graphs:
                cfg = g.graph_config if isinstance(g.graph_config, dict) else {}
                gd = cfg.get("graph_data")
                gd = gd if isinstance(gd, dict) else {}
                nodes = gd.get("nodes") if isinstance(gd.get("nodes"), list) else []
                edges = gd.get("edges") if isinstance(gd.get("edges"), list) else []
                n_nodes = (
                    cfg.get("total_nodes")
                    if isinstance(cfg.get("total_nodes"), int)
                    else len(nodes)
                )
                n_edges = (
                    cfg.get("total_edges")
                    if isinstance(cfg.get("total_edges"), int)
                    else len(edges)
                )
                content += (
                    f"\n**{g.name}** (v{g.version}) — {n_nodes} nodes, "
                    f"{n_edges} edges\n"
                )
                graph_data.append(
                    {
                        "id": str(g.id),
                        "name": g.name,
                        "version": g.version,
                        "node_count": n_nodes,
                        "edge_count": n_edges,
                        # Full node/edge structure for programmatic reads/edits.
                        "graph_config": cfg,
                    }
                )

        data = {
            "id": str(scenario.id),
            "name": scenario.name,
            "type": scenario.scenario_type,
            "agent": agent_name,
            "source_type": scenario.source_type,
            "dataset_id": dataset_id,
            "graphs": graph_data,
        }

        return ToolResult(content=content, data=data)
