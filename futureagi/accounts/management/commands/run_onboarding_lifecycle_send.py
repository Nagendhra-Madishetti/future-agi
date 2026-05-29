from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from accounts.services.onboarding.lifecycle_preview_approval import (
    load_lifecycle_preview_approval,
)
from accounts.services.onboarding.lifecycle_sender import (
    send_limited_onboarding_lifecycle_batch,
)


class Command(BaseCommand):
    help = "Send tightly gated onboarding lifecycle emails to an allowlisted cohort."

    def add_arguments(self, parser):
        parser.add_argument("--cohort", choices=["internal", "beta"], required=True)
        parser.add_argument("--limit", type=int, required=True)
        parser.add_argument("--campaign-family")
        parser.add_argument("--workspace-id")
        parser.add_argument("--user-id")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--approval-manifest")
        parser.add_argument("--approval-record")
        parser.add_argument("--now")

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("--limit must be greater than zero.")
        now = None
        if options.get("now"):
            now = parse_datetime(options["now"])
            if now is None:
                raise CommandError("--now must be an ISO datetime.")
        preview_approval = None
        if options.get("approval_manifest"):
            try:
                preview_approval = load_lifecycle_preview_approval(
                    options["approval_manifest"],
                    approval_record_path=options.get("approval_record"),
                )
            except ImproperlyConfigured as exc:
                raise CommandError(str(exc)) from exc
        elif options.get("approval_record"):
            raise CommandError(
                "--approval-manifest is required with --approval-record."
            )
        elif not options["dry_run"]:
            raise CommandError("--approval-manifest is required for sends.")
        if not options["dry_run"] and not options.get("approval_record"):
            raise CommandError("--approval-record is required for sends.")

        result = send_limited_onboarding_lifecycle_batch(
            cohort=options["cohort"],
            limit=options["limit"],
            campaign_group=options.get("campaign_family"),
            workspace_id=options.get("workspace_id"),
            user_id=options.get("user_id"),
            dry_run=options["dry_run"],
            now=now,
            preview_approval=preview_approval,
        )
        payload = result.to_payload()
        if payload["approval_manifest_sha256"]:
            self.stdout.write(
                f"approval_manifest_sha256={payload['approval_manifest_sha256']}"
            )
        if payload["approval_record_sha256"]:
            self.stdout.write(
                f"approval_record_sha256={payload['approval_record_sha256']}"
            )
        self.stdout.write(f"run_id={payload['run_id']}")
        self.stdout.write(f"evaluated={payload['evaluated']}")
        self.stdout.write(f"sent={payload['sent']}")
        self.stdout.write(f"suppressed={payload['suppressed']}")
        self.stdout.write(f"failed={payload['failed']}")
        self.stdout.write(f"skipped={payload['skipped']}")
        self.stdout.write(f"status_counts={payload['status_counts']}")
        self.stdout.write(f"suppression_counts={payload['suppression_counts']}")
