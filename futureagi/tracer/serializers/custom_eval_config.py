from rest_framework import serializers

from model_hub.models.develop_dataset import KnowledgeBaseFile
from model_hub.models.evals_metric import EvalTemplate
from model_hub.utils.function_eval_params import normalize_eval_runtime_config
from tracer.models.custom_eval_config import CustomEvalConfig
from tracer.models.project import Project
from tracer.serializers.filters import StrictInputSerializer


class CustomEvalConfigSerializer(serializers.ModelSerializer):
    eval_template = serializers.PrimaryKeyRelatedField(
        queryset=EvalTemplate.objects.all(), many=False
    )
    project = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(), many=False
    )
    kb_id = serializers.PrimaryKeyRelatedField(
        queryset=KnowledgeBaseFile.objects.all(),
        many=False,
        required=False,
        allow_null=True,
    )

    eval_group = serializers.SerializerMethodField()

    # Explicit field so the help_text flows into the generated MCP tool schema
    # (auto-derived JSONFields render as a bare "Mapping" with an empty object,
    # which left Falcon unable to do eval variable mapping — TH-5442).
    mapping = serializers.JSONField(
        required=False,
        help_text=(
            "Variable mapping for the eval. JSON object whose KEYS are the eval "
            "template's input variables (call get_eval_template or "
            "get_eval_template_by_name to list its required_keys / optional_keys) "
            "and whose VALUES are span attribute paths that exist in this project "
            "(call get_project_eval_attributes for the available paths). "
            'Example: {"input": "llm.input", "output": "llm.output"}.'
        ),
    )

    class Meta:
        model = CustomEvalConfig
        fields = [
            "id",
            "eval_template",
            "name",
            "config",
            "mapping",
            "project",
            "filters",
            "error_localizer",
            "kb_id",
            "model",
            "eval_group",
        ]

    def get_eval_group(self, obj):
        if obj.eval_group:
            return obj.eval_group.name
        return None

    def validate(self, attrs):
        eval_template = attrs.get("eval_template") or getattr(
            self.instance, "eval_template", None
        )
        if eval_template:
            attrs["config"] = normalize_eval_runtime_config(
                eval_template.config,
                (
                    attrs.get("config")
                    if "config" in attrs
                    else getattr(self.instance, "config", {})
                ),
            )
        return attrs


class RunEvaluationSerializer(serializers.Serializer):
    custom_eval_config_id = serializers.UUIDField(required=True)
    project_version_id = serializers.UUIDField(required=True)


class GetCustomEvalTemplateSerializer(serializers.Serializer):
    eval_template_name = serializers.CharField(required=True)


class CustomEvalConfigListQuerySerializer(StrictInputSerializer):
    project_id = serializers.UUIDField(required=False)
    task_id = serializers.UUIDField(required=False)
