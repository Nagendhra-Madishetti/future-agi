"""Bridge registration for PersonaViewSet (simulate)."""

from ai_tools.drf_bridge import expose_to_mcp
from simulate.views.persona import PersonaViewSet

expose_to_mcp(category="simulation")(PersonaViewSet)
