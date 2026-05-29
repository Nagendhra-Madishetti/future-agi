from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from accounts.services.onboarding.lifecycle_preview_snapshots import (
    MANIFEST_SCHEMA_VERSION,
    PREVIEW_SOURCE,
)
from accounts.services.onboarding.lifecycle_registry import lifecycle_campaign_by_key
from accounts.services.onboarding.lifecycle_template_contract import (
    required_context_keys_for_template,
)

APPROVAL_METADATA_KEY = "preview_approval"
PREVIEW_APPROVAL_MISSING_REASON = "preview_approval_missing"


@dataclass(frozen=True)
class LifecyclePreviewApproval:
    path: str
    manifest_sha256: str
    generated_at: str
    campaign_entries: dict

    @property
    def campaign_keys(self):
        return tuple(self.campaign_entries)

    def has_campaign(self, campaign_key):
        return campaign_key in self.campaign_entries

    def metadata_for_campaign(self, campaign_key):
        entry = self.campaign_entries[campaign_key]
        return {
            "manifest_path": self.path,
            "manifest_sha256": self.manifest_sha256,
            "manifest_generated_at": self.generated_at,
            "campaign_key": campaign_key,
            "html_file": entry["html_file"],
            "text_file": entry["text_file"],
            "html_sha256": entry["html_sha256"],
            "text_sha256": entry["text_sha256"],
        }


def _manifest_error(message):
    return ImproperlyConfigured(
        f"Invalid lifecycle preview approval manifest: {message}"
    )


def _require_keys(mapping, expected, path):
    if set(mapping) != expected:
        missing = sorted(expected - set(mapping))
        extra = sorted(set(mapping) - expected)
        parts = []
        if missing:
            parts.append(f"missing {', '.join(missing)}")
        if extra:
            parts.append(f"unexpected {', '.join(extra)}")
        raise _manifest_error(f"{path} has invalid fields ({'; '.join(parts)}).")


def _require_text(mapping, key, path):
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _manifest_error(f"{path}.{key} must be a non-empty string.")
    return value


def _require_sha(value, path):
    if not isinstance(value, str) or len(value) != 64:
        raise _manifest_error(f"{path} must be a SHA-256 hex digest.")
    try:
        int(value, 16)
    except ValueError as exc:
        raise _manifest_error(f"{path} must be a SHA-256 hex digest.") from exc
    return value


def _validate_campaign_entry(entry, index):
    path = f"campaigns.{index}"
    _require_keys(
        entry,
        {
            "campaign_key",
            "campaign_group",
            "template_key",
            "template_version",
            "primary_path",
            "activation_stage",
            "target_action_id",
            "target_success_event",
            "route_strategy",
            "subject",
            "preheader",
            "html_file",
            "text_file",
            "html_sha256",
            "text_sha256",
            "required_context_keys",
            "digest_preview_required",
            "generated_at",
        },
        path,
    )
    campaign_key = _require_text(entry, "campaign_key", path)
    campaign = lifecycle_campaign_by_key(campaign_key)
    if not campaign:
        raise _manifest_error(f"{path}.campaign_key is not configured.")

    expected_values = {
        "campaign_group": campaign["campaign_group"],
        "template_key": campaign["template_key"],
        "template_version": campaign["template_version"],
        "primary_path": campaign["primary_path"],
        "activation_stage": campaign["entry_stages"][0],
        "target_action_id": campaign["target_action_id"],
        "target_success_event": campaign["target_success_event"],
        "route_strategy": campaign["route_strategy"],
        "subject": campaign["email_subject"],
        "preheader": campaign["email_preheader"],
    }
    for key, expected in expected_values.items():
        if entry[key] != expected:
            raise _manifest_error(f"{path}.{key} does not match current registry.")

    expected_context_keys = sorted(
        required_context_keys_for_template(campaign["template_key"])
    )
    if entry["required_context_keys"] != expected_context_keys:
        raise _manifest_error(
            f"{path}.required_context_keys does not match template contract."
        )
    expected_digest_requirement = campaign.get("requires_digest_preview") is True
    if entry["digest_preview_required"] is not expected_digest_requirement:
        raise _manifest_error(
            f"{path}.digest_preview_required does not match current registry."
        )
    _require_text(entry, "html_file", path)
    _require_text(entry, "text_file", path)
    _require_sha(entry["html_sha256"], f"{path}.html_sha256")
    _require_sha(entry["text_sha256"], f"{path}.text_sha256")
    _require_text(entry, "generated_at", path)
    return campaign_key


def load_lifecycle_preview_approval_manifest(path):
    manifest_path = Path(path)
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _manifest_error(f"{manifest_path} could not be read.") from exc
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _manifest_error(f"{manifest_path} is not valid JSON.") from exc
    if not isinstance(manifest, dict):
        raise _manifest_error("manifest root must be a mapping.")

    _require_keys(
        manifest,
        {"schema_version", "generated_at", "source", "count", "campaigns"},
        "manifest",
    )
    if manifest["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise _manifest_error("schema_version is not supported.")
    if manifest["source"] != PREVIEW_SOURCE:
        raise _manifest_error("source is not lifecycle preview snapshot.")
    generated_at = _require_text(manifest, "generated_at", "manifest")
    campaigns = manifest["campaigns"]
    if not isinstance(campaigns, list) or not campaigns:
        raise _manifest_error("campaigns must be a non-empty list.")
    if manifest["count"] != len(campaigns):
        raise _manifest_error("count does not match campaigns.")

    entries = {}
    for index, entry in enumerate(campaigns):
        if not isinstance(entry, dict):
            raise _manifest_error(f"campaigns.{index} must be a mapping.")
        campaign_key = _validate_campaign_entry(entry, index)
        if campaign_key in entries:
            raise _manifest_error(f"campaigns.{index}.campaign_key is duplicated.")
        entries[campaign_key] = entry

    return LifecyclePreviewApproval(
        path=str(manifest_path),
        manifest_sha256=sha256(raw.encode("utf-8")).hexdigest(),
        generated_at=generated_at,
        campaign_entries=entries,
    )
