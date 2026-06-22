from django.apps import AppConfig


class DeploymentTelemetryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tfc.deployment_telemetry"
    verbose_name = "Deployment telemetry"

    def ready(self) -> None:
        from tfc.deployment_telemetry.config import is_self_hosted_deployment

        if is_self_hosted_deployment():
            from tfc.deployment_telemetry.sender import _log_disclosure

            _log_disclosure()
