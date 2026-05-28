"""Bridge registration for AgentDefinitionOperationsViewSet (simulate)."""

from ai_tools.drf_bridge import expose_to_mcp
from simulate.views.agent_definition import AgentDefinitionOperationsViewSet

# entity override: derived class name would be 'agent_definition_operations' which is ugly.
expose_to_mcp(
    category="agents",
    tools={
        "list": {"name": "list_agents"},
        "retrieve": {"name": "get_agent"},
        "create": {"name": "create_agent"},
        "update": {"name": "update_agent"},
        "destroy": {"name": "delete_agent"},
    },
)(AgentDefinitionOperationsViewSet)
