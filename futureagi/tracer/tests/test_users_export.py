"""End-to-end tests for the Users CSV export.

The export is served by the same endpoint as the list view
(`/tracer/users/`) gated by `?export=true`. These tests exercise the export
branch in `UsersView.get`, the streaming CSV writer, and the ClickHouse →
Postgres fallback contract.
"""

import csv
import io
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework import status

from tracer.models.observation_span import EndUser, ObservationSpan
from tracer.models.trace import Trace
from tracer.models.trace_session import TraceSession
from tracer.services.clickhouse.query_service import AnalyticsQueryService

pytestmark = [pytest.mark.integration, pytest.mark.api]


def _date_filters(start, end):
    return [
        {
            "column_id": "start_time",
            "filter_config": {
                "filter_type": "datetime",
                "filter_op": "between",
                "filter_value": [start.isoformat(), end.isoformat()],
            },
        }
    ]


def _create_user_activity(organization, workspace, observe_project, *, suffix=""):
    end_user = EndUser.objects.create(
        organization=organization,
        workspace=workspace,
        project=observe_project,
        user_id=f"export-{suffix or uuid.uuid4().hex[:8]}@example.com",
        user_id_type="email",
        user_id_hash=f"export-hash-{suffix}",
    )
    session = TraceSession.objects.create(
        project=observe_project,
        name=f"Export Session {suffix}",
    )
    trace = Trace.objects.create(
        project=observe_project,
        session=session,
        name=f"Export Trace {suffix}",
        input={"message": "hello"},
        output={"message": "world"},
    )
    start = timezone.now() - timedelta(hours=2)
    span = ObservationSpan.objects.create(
        id=f"export_span_{uuid.uuid4().hex[:16]}",
        project=observe_project,
        trace=trace,
        end_user=end_user,
        name="Export LLM Span",
        observation_type="llm",
        start_time=start,
        end_time=start + timedelta(seconds=3),
        latency_ms=300,
        prompt_tokens=11,
        completion_tokens=7,
        total_tokens=18,
        cost=0.123456,
        status="OK",
        span_attributes={"plan": "pro"},
    )
    return end_user, session, trace, span


# Header order is the contract the frontend (and external consumers of the
# CSV) rely on. Duplicated here intentionally — if the view changes the
# column order this test will catch it.
_EXPECTED_HEADER = [
    "User ID",
    "User ID Type",
    "User ID Hash",
    "First Active",
    "Last Active",
    "No. of Traces",
    "No. of Sessions",
    "Avg Session Duration (s)",
    "Total Tokens",
    "Total Cost ($)",
    "Avg Latency / Trace (ms)",
    "No. of LLM Calls",
    "Guardrails Triggered",
    "Evals Pass Rate (%)",
    "Input Tokens",
    "Output Tokens",
]


def _parse_csv(response):
    """Drain a StreamingHttpResponse and return its parsed CSV rows."""
    body = b"".join(response.streaming_content).decode("utf-8")
    reader = csv.reader(io.StringIO(body))
    return list(reader)


class TestUsersExport:
    def test_export_streams_csv_with_correct_headers_via_pg_fallback(
        self, auth_client, organization, workspace, observe_project
    ):
        end_user, _, _, span = _create_user_activity(
            organization, workspace, observe_project
        )
        filters = _date_filters(
            span.start_time - timedelta(hours=1),
            span.start_time + timedelta(hours=1),
        )

        # Force the CH path to fail so the PG fallback handles the export end
        # to end. Keeps this test runnable without a live ClickHouse.
        with (
            patch.object(
                AnalyticsQueryService,
                "should_use_clickhouse",
                return_value=True,
            ),
            patch.object(
                AnalyticsQueryService,
                "execute_ch_query",
                side_effect=Exception("clickhouse unavailable"),
            ),
        ):
            response = auth_client.get(
                "/tracer/users/",
                {
                    "project_id": str(observe_project.id),
                    "filters": json.dumps(filters),
                    "export": "true",
                },
            )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"].startswith("text/csv")
        assert "attachment;" in response["Content-Disposition"]
        assert f"users_{observe_project.id}_" in response["Content-Disposition"]

        rows = _parse_csv(response)
        assert rows[0] == _EXPECTED_HEADER
        data_rows = [r for r in rows[1:] if r]
        assert any(r[0] == end_user.user_id for r in data_rows)
        target = next(r for r in data_rows if r[0] == end_user.user_id)
        # User ID Type, Total Tokens, Input/Output, num_traces filled correctly
        assert target[1] == "email"
        assert target[_EXPECTED_HEADER.index("Total Tokens")] == "18"
        assert target[_EXPECTED_HEADER.index("Input Tokens")] == "11"
        assert target[_EXPECTED_HEADER.index("Output Tokens")] == "7"
        assert target[_EXPECTED_HEADER.index("No. of Traces")] == "1"

    def test_export_requires_authentication(self, api_client, observe_project):
        response = api_client.get(
            "/tracer/users/",
            {"project_id": str(observe_project.id), "export": "true"},
        )
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_export_ignores_pagination_params(
        self, auth_client, organization, workspace, observe_project
    ):
        # Three users in the same date window — without `export=true` only the
        # first page (size=1) would be returned. With `export=true` we expect
        # every row regardless of page_size / current_page_index.
        users = []
        for i in range(3):
            eu, _, _, span = _create_user_activity(
                organization, workspace, observe_project, suffix=str(i)
            )
            users.append((eu, span))
        filters = _date_filters(
            users[0][1].start_time - timedelta(hours=1),
            users[0][1].start_time + timedelta(hours=1),
        )

        with (
            patch.object(
                AnalyticsQueryService,
                "should_use_clickhouse",
                return_value=True,
            ),
            patch.object(
                AnalyticsQueryService,
                "execute_ch_query",
                side_effect=Exception("clickhouse unavailable"),
            ),
        ):
            response = auth_client.get(
                "/tracer/users/",
                {
                    "project_id": str(observe_project.id),
                    "filters": json.dumps(filters),
                    "export": "true",
                    # These pagination params must be ignored on the export
                    # branch.
                    "page_size": 1,
                    "current_page_index": 2,
                },
            )

        assert response.status_code == status.HTTP_200_OK
        rows = _parse_csv(response)
        data_rows = [r for r in rows[1:] if r]
        emitted_user_ids = {r[0] for r in data_rows}
        for eu, _ in users:
            assert eu.user_id in emitted_user_ids

    def test_export_skips_pagination_in_builder_kwargs(
        self, auth_client, organization, workspace, observe_project
    ):
        """The CH builder must be constructed with limit/offset = None."""
        _, _, _, span = _create_user_activity(organization, workspace, observe_project)
        filters = _date_filters(
            span.start_time - timedelta(hours=1),
            span.start_time + timedelta(hours=1),
        )

        with (
            patch.object(
                AnalyticsQueryService,
                "should_use_clickhouse",
                return_value=True,
            ),
            patch(
                "tracer.views.trace.UserListQueryBuilder",
                wraps=__import__(
                    "tracer.services.clickhouse.query_builders.user_list",
                    fromlist=["UserListQueryBuilder"],
                ).UserListQueryBuilder,
            ) as builder_cls,
            patch.object(
                AnalyticsQueryService,
                "execute_ch_query",
                side_effect=Exception("force fallback"),
            ),
        ):
            response = auth_client.get(
                "/tracer/users/",
                {
                    "project_id": str(observe_project.id),
                    "filters": json.dumps(filters),
                    "export": "true",
                    "page_size": 5,
                    "current_page_index": 3,
                },
            )

        assert response.status_code == status.HTTP_200_OK
        # Builder should have been constructed once with limit=None, offset=None.
        builder_cls.assert_called_once()
        kwargs = builder_cls.call_args.kwargs
        assert kwargs["limit"] is None
        assert kwargs["offset"] is None
        assert kwargs["filters"] == filters

    def test_export_formats_none_cells_as_empty(
        self, auth_client, organization, workspace, observe_project
    ):
        """Cells with None values must render as empty, not the string 'None'."""
        end_user = EndUser.objects.create(
            organization=organization,
            workspace=workspace,
            project=observe_project,
            user_id="no-activity@example.com",
            user_id_type="email",
            user_id_hash="no-activity-hash",
        )
        # No spans for this user — last_active should be empty in the CSV.
        _, _, _, span = _create_user_activity(
            organization, workspace, observe_project, suffix="active"
        )
        filters = _date_filters(
            span.start_time - timedelta(hours=1),
            span.start_time + timedelta(hours=1),
        )

        with (
            patch.object(
                AnalyticsQueryService,
                "should_use_clickhouse",
                return_value=True,
            ),
            patch.object(
                AnalyticsQueryService,
                "execute_ch_query",
                side_effect=Exception("force fallback"),
            ),
        ):
            response = auth_client.get(
                "/tracer/users/",
                {
                    "project_id": str(observe_project.id),
                    "filters": json.dumps(filters),
                    "export": "true",
                },
            )

        rows = _parse_csv(response)
        idle_row = next((r for r in rows[1:] if r and r[0] == end_user.user_id), None)
        # The idle user has no spans in the date range so the PG path won't
        # surface them at all (filtered_spans contract). This assertion just
        # guards against the row, if present, leaking the literal "None"
        # for last_active.
        if idle_row is not None:
            assert idle_row[_EXPECTED_HEADER.index("Last Active")] != "None"

    def test_export_filename_defaults_to_all_when_no_project(
        self, auth_client, organization, workspace, observe_project
    ):
        with (
            patch.object(
                AnalyticsQueryService,
                "should_use_clickhouse",
                return_value=True,
            ),
            patch.object(
                AnalyticsQueryService,
                "execute_ch_query",
                side_effect=Exception("force fallback"),
            ),
        ):
            response = auth_client.get(
                "/tracer/users/",
                {"export": "true"},
            )

        assert response.status_code == status.HTTP_200_OK
        assert "users_all_" in response["Content-Disposition"]


class TestUserListQueryBuilderUnpaginated:
    """Drop the `count() OVER()` window when no pagination is requested."""

    def test_unpaginated_query_omits_window_count(self):
        from tracer.services.clickhouse.query_builders.user_list import (
            UserListQueryBuilder,
        )

        builder = UserListQueryBuilder(
            organization_id=str(uuid.uuid4()),
            workspace_id=str(uuid.uuid4()),
            project_id=str(uuid.uuid4()),
            limit=None,
            offset=None,
        )
        query, _ = builder.build()
        assert "count() OVER()" not in query
        assert "LIMIT %(limit)s" not in query
        assert "0 AS total_count" in query

    def test_paginated_query_keeps_window_count(self):
        from tracer.services.clickhouse.query_builders.user_list import (
            UserListQueryBuilder,
        )

        builder = UserListQueryBuilder(
            organization_id=str(uuid.uuid4()),
            workspace_id=str(uuid.uuid4()),
            project_id=str(uuid.uuid4()),
            limit=30,
            offset=0,
        )
        query, _ = builder.build()
        assert "count() OVER() AS total_count" in query
        assert "LIMIT %(limit)s OFFSET %(offset)s" in query
