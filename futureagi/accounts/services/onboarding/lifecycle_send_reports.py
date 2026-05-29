from __future__ import annotations

import json
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

DRY_RUN_REPORT_SCHEMA_VERSION = "onboarding-lifecycle-send-dry-run-report-2026-05-29.v1"
DRY_RUN_REPORT_SOURCE = "onboarding_lifecycle_send_dry_run_report"


def lifecycle_send_dry_run_report_payload(
    *,
    command_name,
    result,
    cohort,
    limit,
    campaign_group=None,
    user_id=None,
    workspace_id=None,
    require_campaign_group_allowlist=False,
):
    payload = result.to_payload()
    if not payload["dry_run"]:
        raise ImproperlyConfigured("Lifecycle send reports require dry-run mode.")
    return {
        "schema_version": DRY_RUN_REPORT_SCHEMA_VERSION,
        "source": DRY_RUN_REPORT_SOURCE,
        "generated_at": payload["generated_at"],
        "command": command_name,
        "parameters": {
            "cohort": cohort,
            "limit": limit,
            "campaign_group": campaign_group,
            "user_id": str(user_id) if user_id else None,
            "workspace_id": str(workspace_id) if workspace_id else None,
            "require_campaign_group_allowlist": bool(require_campaign_group_allowlist),
        },
        "approval": {
            "manifest_sha256": payload["approval_manifest_sha256"],
            "record_sha256": payload["approval_record_sha256"],
        },
        "summary": {
            "run_id": payload["run_id"],
            "evaluated": payload["evaluated"],
            "sent": payload["sent"],
            "suppressed": payload["suppressed"],
            "failed": payload["failed"],
            "skipped": payload["skipped"],
            "status_counts": payload["status_counts"],
            "suppression_counts": payload["suppression_counts"],
        },
        "candidates": payload["candidates"],
    }


def write_lifecycle_send_dry_run_report(
    *,
    output_path,
    force=False,
    **payload_kwargs,
):
    path = Path(output_path)
    if path.exists() and not force:
        raise ImproperlyConfigured(
            f"{path} already exists. Use --report-force to overwrite."
        )
    report = lifecycle_send_dry_run_report_payload(**payload_kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(path)
