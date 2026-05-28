"""Bridge registration for remaining ModelViewSets across multiple apps.

Covers dashboards, scores, optimisation, secrets, observability,
shared links, saved views, tts voices, api keys, tools, and feedback.
"""

from ai_tools.drf_bridge import expose_to_mcp
from model_hub.views.annotation_queues import (
    AutomationRuleViewSet,
    QueueItemViewSet,
)
from model_hub.views.dataset_optimization import DatasetOptimizationViewSet
from model_hub.views.develop_dataset import FeedbackViewSet
from model_hub.views.run_prompt import ApiKeyViewSet
from model_hub.views.scores import ScoreViewSet
from model_hub.views.secrets import SecretViewSet
from model_hub.views.tools import ToolsViewSet
from model_hub.views.tts_voices import TTSVoiceViewSet
from simulate.views.agent_prompt_optimiser import AgentPromptOptimiserRunViewSet
from tracer.views.custom_eval_config import CustomEvalConfigView
from tracer.views.dashboard import DashboardViewSet, DashboardWidgetViewSet
from tracer.views.observability_provider import ObservabilityProviderViewSet
from tracer.views.saved_view import SavedViewViewSet
from tracer.views.shared_link import SharedLinkViewSet

# Tracer
expose_to_mcp(category="tracing")(DashboardViewSet)
expose_to_mcp(category="tracing")(DashboardWidgetViewSet)
expose_to_mcp(category="tracing")(ObservabilityProviderViewSet)
expose_to_mcp(category="tracing")(SharedLinkViewSet)
expose_to_mcp(category="tracing")(SavedViewViewSet)
expose_to_mcp(
    category="evaluations",
    tools={
        "list": {"name": "list_custom_eval_configs"},
        "retrieve": {"name": "get_custom_eval_config"},
        "create": {"name": "create_custom_eval_config"},
        "update": {"name": "update_custom_eval_config"},
        "destroy": {"name": "delete_custom_eval_config"},
    },
)(CustomEvalConfigView)

# Model hub
expose_to_mcp(category="annotation_queues")(QueueItemViewSet)
expose_to_mcp(category="annotation_queues")(AutomationRuleViewSet)
expose_to_mcp(category="datasets")(FeedbackViewSet)
expose_to_mcp(category="datasets")(DatasetOptimizationViewSet)
expose_to_mcp(category="users")(ApiKeyViewSet)
expose_to_mcp(category="datasets")(SecretViewSet)
expose_to_mcp(category="prompts")(ToolsViewSet)
expose_to_mcp(category="simulation")(TTSVoiceViewSet)
expose_to_mcp(category="evaluations")(ScoreViewSet)

# Simulation
expose_to_mcp(category="optimization")(AgentPromptOptimiserRunViewSet)
