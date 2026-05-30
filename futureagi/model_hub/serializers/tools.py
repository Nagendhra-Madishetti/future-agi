from rest_framework import serializers

from model_hub.models.openai_tools import Tools


class ToolsSerializer(serializers.ModelSerializer):
    """A reusable, OpenAI-style function/tool definition (a name, a description, and a JSON parameter schema) that prompts and agents can call. Create one with create_tools, then list/read/edit/remove it via list_tools / get_tools / update_tools / delete_tools. The schema lives in `config`; `config_type` selects whether you submit that config as JSON or YAML."""

    class Meta:
        model = Tools
        fields = ["id", "name", "description", "config", "config_type", "organization"]
        read_only_fields = ["organization"]
        extra_kwargs = {
            "id": {"help_text": "UUID of this tool (from list_tools)."},
            "name": {
                "help_text": "Unique tool name (1-255 chars) used to invoke the function; must be unique across all tools.",
            },
            "description": {
                "help_text": "Short natural-language description of what the tool does (1-255 chars); shown to the model to help it decide when to call the tool.",
            },
            "config": {
                "help_text": (
                    "The tool's parameter schema as a JSON object. Must contain a 'parameters' object whose "
                    "'type' is 'object', with a 'properties' dict describing each argument and a 'required' list "
                    "of required argument names (OpenAI function-calling format)."
                ),
            },
            "config_type": {
                "help_text": (
                    "Format in which the `config` payload is provided: 'json' (default) or 'yaml'. When 'yaml', "
                    "the server parses the YAML string in `config` into JSON before saving; the stored config is "
                    "always JSON."
                ),
            },
            "organization": {
                "help_text": "UUID of the organization that owns this tool; set automatically from the request, not supplied by the caller.",
            },
        }
