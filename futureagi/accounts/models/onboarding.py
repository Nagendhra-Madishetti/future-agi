import uuid

from django.db import models
from django.utils import timezone

from tfc.utils.base_model import BaseModel


class OnboardingActivationEvent(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="onboarding_activation_events",
    )
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="onboarding_activation_events",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboarding_activation_events",
    )
    event_name = models.CharField(max_length=96, db_index=True)
    product_path = models.CharField(max_length=32, blank=True, default="")
    activation_stage = models.CharField(max_length=96, blank=True, default="")
    source = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    is_sample = models.BooleanField(default=False, db_index=True)
    idempotency_key = models.CharField(
        max_length=160,
        null=True,
        blank=True,
        db_index=True,
    )
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "accounts_onboarding_activation_event"
        ordering = ("-occurred_at", "-created_at")
        indexes = [
            models.Index(
                fields=["organization", "workspace", "event_name", "-occurred_at"],
                name="onb_evt_org_ws_name_ts",
            ),
            models.Index(
                fields=["organization", "workspace", "product_path", "-occurred_at"],
                name="onb_evt_org_ws_path_ts",
            ),
            models.Index(
                fields=["user", "event_name", "-occurred_at"],
                name="onb_evt_user_name_ts",
            ),
            models.Index(
                fields=["workspace", "is_sample", "event_name"],
                name="onb_evt_ws_sample_name",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "workspace", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False, deleted=False),
                name="onb_evt_unique_idempotency",
            )
        ]

    def __str__(self):
        return f"{self.event_name} for {self.workspace_id} at {self.occurred_at}"


class OnboardingGoal(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="onboarding_goals",
    )
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="onboarding_goals",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="selected_onboarding_goals",
    )
    goal = models.CharField(max_length=64)
    primary_path = models.CharField(max_length=32)
    source = models.CharField(max_length=64, blank=True, default="")
    reason = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    selected_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "accounts_onboarding_goal"
        ordering = ("-selected_at", "-created_at")
        indexes = [
            models.Index(
                fields=["organization", "workspace", "is_active"],
                name="onb_goal_org_ws_active",
            ),
            models.Index(
                fields=["organization", "workspace", "primary_path"],
                name="onb_goal_org_ws_path",
            ),
            models.Index(
                fields=["user", "-selected_at"],
                name="onb_goal_user_selected",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "workspace"],
                condition=models.Q(is_active=True, deleted=False),
                name="onb_goal_unique_active_workspace",
            )
        ]

    def __str__(self):
        return f"{self.goal} for {self.workspace_id}"


class OnboardingSampleProject(BaseModel):
    STATUS_NOT_CREATED = "not_created"
    STATUS_CREATING = "creating"
    STATUS_READY_FOR_OBSERVE = "ready_for_observe"
    STATUS_PARTIALLY_READY = "partially_ready"
    STATUS_READY = "ready"
    STATUS_HIDDEN = "hidden"
    STATUS_UNAVAILABLE = "unavailable"
    STATUS_REPAIR_FAILED = "repair_failed"

    STATUS_CHOICES = (
        (STATUS_NOT_CREATED, STATUS_NOT_CREATED),
        (STATUS_CREATING, STATUS_CREATING),
        (STATUS_READY_FOR_OBSERVE, STATUS_READY_FOR_OBSERVE),
        (STATUS_PARTIALLY_READY, STATUS_PARTIALLY_READY),
        (STATUS_READY, STATUS_READY),
        (STATUS_HIDDEN, STATUS_HIDDEN),
        (STATUS_UNAVAILABLE, STATUS_UNAVAILABLE),
        (STATUS_REPAIR_FAILED, STATUS_REPAIR_FAILED),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="onboarding_sample_projects",
    )
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="onboarding_sample_projects",
    )
    first_opened_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="first_opened_onboarding_sample_projects",
    )
    last_opened_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_opened_onboarding_sample_projects",
    )
    manifest_id = models.CharField(max_length=96)
    manifest_version = models.CharField(max_length=32)
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_NOT_CREATED,
        db_index=True,
    )
    artifact_refs = models.JSONField(default=dict, blank=True)
    missing_artifacts = models.JSONField(default=list, blank=True)
    health = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=180, db_index=True)
    repair_attempts = models.PositiveIntegerField(default=0)
    last_repair_attempt_at = models.DateTimeField(null=True, blank=True)
    last_opened_at = models.DateTimeField(null=True, blank=True)
    hidden_at = models.DateTimeField(null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "accounts_onboarding_sample_project"
        ordering = ("-last_opened_at", "-updated_at")
        indexes = [
            models.Index(
                fields=["organization", "workspace", "manifest_id"],
                name="onb_sample_org_ws_manifest",
            ),
            models.Index(fields=["workspace", "status"], name="onb_sample_ws_status"),
            models.Index(
                fields=["workspace", "hidden_at"], name="onb_sample_ws_hidden"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "manifest_id", "manifest_version"],
                condition=models.Q(deleted=False),
                name="onb_sample_unique_manifest",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=models.Q(deleted=False),
                name="onb_sample_unique_idempotency",
            ),
        ]

    def __str__(self):
        return f"{self.manifest_id}:{self.manifest_version} for {self.workspace_id}"
