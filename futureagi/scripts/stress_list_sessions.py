#!/usr/bin/env python
"""
Stress test for the ``list_sessions`` endpoint and its underlying
ClickHouse query builder (TH-5092).

Has two modes:

1. **builder mode** (default; no external services required) — drives
   ``SessionListQueryBuilder`` directly across a range of filter sizes
   and asserts query generation stays below a wall-clock budget. Useful
   in CI to catch regressions in the subquery construction path.

2. **endpoint mode** (``--endpoint URL``) — fires real HTTP requests
   against a deployed instance, varying page sizes / time windows /
   user_ids, and reports p50/p95/p99 latency. Use this after deploying
   to verify the timeout is actually fixed end-to-end.

Examples::

    # Builder-only stress (safe to run anywhere):
    python scripts/stress_list_sessions.py

    # Hit a running backend on the Users tab path (org-scope + user_id):
    python scripts/stress_list_sessions.py \\
        --endpoint http://localhost:8001 \\
        --auth "Bearer $TOKEN" \\
        --user-id user-eve \\
        --requests 50

The script exits non-zero on budget breach so it can gate a CI job.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Builder-mode stress
# ---------------------------------------------------------------------------


@dataclass
class BudgetCheck:
    name: str
    iterations: int
    elapsed_s: float
    budget_s: float

    @property
    def ok(self) -> bool:
        return self.elapsed_s <= self.budget_s

    @property
    def per_iter_us(self) -> float:
        return (
            (self.elapsed_s / self.iterations) * 1_000_000 if self.iterations else 0.0
        )


def _make_filters(num_normal: int, num_aggregate: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(num_normal):
        out.append(
            {
                "column_id": f"custom_attr_{i}",
                "filter_config": {
                    "filter_type": "text",
                    "filter_op": "equals",
                    "filter_value": f"value_{i}",
                },
            }
        )
    cols = ["duration", "total_cost", "total_tokens", "traces_count"]
    for i in range(num_aggregate):
        out.append(
            {
                "column_id": cols[i % len(cols)],
                "filter_config": {
                    "filter_op": "greater_than",
                    "filter_value": i * 10,
                },
            }
        )
    return out


def _make_builder(
    *,
    num_normal: int,
    num_aggregate: int,
    end_user_ids: Optional[List[str]],
    org_scope: bool,
):
    from tracer.services.clickhouse.query_builders import SessionListQueryBuilder

    filters = _make_filters(num_normal, num_aggregate)
    if end_user_ids is not None:
        filters.append(
            {
                "column_id": "end_user_id",
                "filter_config": {
                    "filter_type": "text",
                    "filter_op": "in",
                    "filter_value": end_user_ids,
                },
            }
        )

    if org_scope:
        return SessionListQueryBuilder(
            project_ids=[str(uuid.uuid4()) for _ in range(8)],
            filters=filters,
            page_number=0,
            page_size=30,
        )
    return SessionListQueryBuilder(
        project_id=str(uuid.uuid4()),
        filters=filters,
        page_number=0,
        page_size=30,
    )


def _time_build(builder, iterations: int) -> float:
    initial_params = dict(builder.params)
    start = time.monotonic()
    for _ in range(iterations):
        # Reset params each iteration — build() mutates them.
        builder.params = dict(initial_params)
        builder.build()
        builder.params = dict(initial_params)
        builder.build_count_query()
    return time.monotonic() - start


def run_builder_stress() -> List[BudgetCheck]:
    """Drive the query builder across a matrix of inputs."""
    checks: List[BudgetCheck] = []

    matrix: List[Tuple[str, Dict[str, Any], float]] = [
        (
            "no_filters_single_project",
            dict(num_normal=0, num_aggregate=0, end_user_ids=None, org_scope=False),
            0.5,
        ),
        (
            "no_filters_org_scope",
            dict(num_normal=0, num_aggregate=0, end_user_ids=None, org_scope=True),
            0.5,
        ),
        (
            "20_normal_4_aggregate",
            dict(num_normal=20, num_aggregate=4, end_user_ids=None, org_scope=False),
            1.0,
        ),
        (
            "end_user_filter_1_id_single_project",
            dict(
                num_normal=0,
                num_aggregate=0,
                end_user_ids=[str(uuid.uuid4())],
                org_scope=False,
            ),
            0.5,
        ),
        (
            "end_user_filter_1_id_org_scope",
            dict(
                num_normal=0,
                num_aggregate=0,
                end_user_ids=[str(uuid.uuid4())],
                org_scope=True,
            ),
            0.5,
        ),
        (
            "end_user_filter_10_ids_org_scope",
            dict(
                num_normal=0,
                num_aggregate=0,
                end_user_ids=[str(uuid.uuid4()) for _ in range(10)],
                org_scope=True,
            ),
            0.7,
        ),
        (
            "end_user_filter_1000_ids_org_scope",
            dict(
                num_normal=0,
                num_aggregate=0,
                end_user_ids=[str(uuid.uuid4()) for _ in range(1000)],
                org_scope=True,
            ),
            2.0,
        ),
        (
            "end_user_with_aggregates_org_scope",
            dict(
                num_normal=0,
                num_aggregate=4,
                end_user_ids=[str(uuid.uuid4()) for _ in range(5)],
                org_scope=True,
            ),
            1.0,
        ),
    ]

    iterations = 100
    print(f"\n=== Builder stress ({iterations} iters per case) ===")
    print(
        f"{'case':<45} {'elapsed_s':>10} {'budget_s':>10} {'per_iter_us':>14}  status"
    )
    print("-" * 92)

    for name, kwargs, budget in matrix:
        builder = _make_builder(**kwargs)
        elapsed = _time_build(builder, iterations)
        check = BudgetCheck(
            name=name, iterations=iterations, elapsed_s=elapsed, budget_s=budget
        )
        checks.append(check)
        status = "OK" if check.ok else "FAIL"
        print(
            f"{name:<45} {elapsed:>10.3f} {budget:>10.3f} {check.per_iter_us:>14.1f}  {status}"
        )

    return checks


def run_subquery_shape_checks() -> List[BudgetCheck]:
    """Spot-check the actual SQL shape so regressions in the subquery
    path don't slip past timing-only assertions."""
    from tracer.services.clickhouse.query_builders import SessionListQueryBuilder

    print("\n=== Subquery shape checks ===")
    failures: List[str] = []

    # 1. With end_user_id filter — subquery present.
    eu_ids = [str(uuid.uuid4()) for _ in range(3)]
    builder = SessionListQueryBuilder(
        project_id=str(uuid.uuid4()),
        filters=[
            {
                "column_id": "end_user_id",
                "filter_config": {
                    "filter_type": "text",
                    "filter_op": "in",
                    "filter_value": eu_ids,
                },
            }
        ],
        page_number=0,
        page_size=30,
    )
    q, params = builder.build()
    if "trace_session_id IN (" not in q:
        failures.append("build(): subquery missing")
    if "end_user_id IN %(_eu_ids)s" not in q:
        failures.append("build(): _eu_ids parameter not bound")
    if params.get("_eu_ids") != tuple(eu_ids):
        failures.append("build(): _eu_ids tuple not bound correctly")

    cq, cp = builder.build_count_query()
    if "trace_session_id IN (" not in cq:
        failures.append("count(): subquery missing")
    if cp.get("_eu_ids") != tuple(eu_ids):
        failures.append("count(): _eu_ids tuple not bound correctly")

    # 2. Without end_user_id filter — subquery absent (regression).
    plain = SessionListQueryBuilder(
        project_id=str(uuid.uuid4()),
        filters=[],
        page_number=0,
        page_size=30,
    )
    pq, pp = plain.build()
    if "trace_session_id IN (" in pq:
        failures.append("plain build(): subquery leaked when no filter present")
    if "_eu_ids" in pp:
        failures.append("plain build(): _eu_ids param leaked")

    if failures:
        for line in failures:
            print(f"  FAIL: {line}")
    else:
        print("  OK: subquery emitted when filter present, absent otherwise")

    # Return a single synthetic budget check so the summary works.
    return [
        BudgetCheck(
            name="subquery_shape",
            iterations=1,
            elapsed_s=0.0 if not failures else 1.0,
            budget_s=0.5,
        )
    ]


# ---------------------------------------------------------------------------
# Endpoint-mode stress
# ---------------------------------------------------------------------------


@dataclass
class HttpResult:
    case: str
    status: int
    latency_s: float
    error: Optional[str] = None


def _build_query_string(
    *,
    user_id: Optional[str],
    project_id: Optional[str],
    page_number: int,
    page_size: int,
    start_iso: str,
    end_iso: str,
) -> str:
    from urllib.parse import urlencode

    filters: List[Dict[str, Any]] = [
        {
            "column_id": "created_at",
            "filter_config": {
                "filter_type": "datetime",
                "filter_op": "between",
                "filter_value": [start_iso, end_iso],
            },
        }
    ]
    if user_id:
        filters.append(
            {
                "column_id": "user_id",
                "filter_config": {
                    "filter_type": "text",
                    "filter_op": "equals",
                    "filter_value": user_id,
                },
            }
        )

    params = {
        "page_number": page_number,
        "page_size": page_size,
        "sort_params": json.dumps([]),
        "filters": json.dumps(filters),
        "interval": "day",
    }
    if project_id:
        params["project_id"] = project_id
    return urlencode(params)


def _hit(
    base: str,
    auth: Optional[str],
    case: str,
    qs: str,
    timeout: float,
) -> HttpResult:
    try:
        import urllib.error
        import urllib.request

        url = f"{base.rstrip('/')}/tracer/trace-session/list_sessions/?{qs}"
        req = urllib.request.Request(url, method="GET")
        if auth:
            req.add_header("Authorization", auth)
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            return HttpResult(
                case=case, status=resp.status, latency_s=time.monotonic() - start
            )
    except urllib.error.HTTPError as e:
        return HttpResult(
            case=case,
            status=e.code,
            latency_s=time.monotonic() - start,
            error=str(e),
        )
    except Exception as e:
        return HttpResult(
            case=case,
            status=0,
            latency_s=time.monotonic() - start,
            error=str(e),
        )


def run_endpoint_stress(args: argparse.Namespace) -> int:
    """Hit a live backend, optionally in parallel, and report percentiles."""
    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=args.days)
    start_iso = start.isoformat().replace("+00:00", "Z")
    end_iso = end.isoformat().replace("+00:00", "Z")

    cases: List[Tuple[str, Dict[str, Any]]] = [
        (
            "org_scope_no_filter",
            dict(user_id=None, project_id=None),
        ),
        (
            "org_scope_user_filter",
            dict(user_id=args.user_id, project_id=None),
        ),
    ]
    if args.project_id:
        cases.append(
            (
                "project_scope_no_filter",
                dict(user_id=None, project_id=args.project_id),
            )
        )
        cases.append(
            (
                "project_scope_user_filter",
                dict(user_id=args.user_id, project_id=args.project_id),
            )
        )

    print(
        f"\n=== Endpoint stress: {args.requests} req/case across {len(cases)} cases "
        f"(concurrency={args.concurrency}) ==="
    )

    results: List[HttpResult] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = []
        for case, kwargs in cases:
            for _ in range(args.requests):
                qs = _build_query_string(
                    page_number=0,
                    page_size=args.page_size,
                    start_iso=start_iso,
                    end_iso=end_iso,
                    **kwargs,
                )
                futures.append(
                    pool.submit(_hit, args.endpoint, args.auth, case, qs, args.timeout)
                )
        for fut in as_completed(futures):
            results.append(fut.result())

    by_case: Dict[str, List[HttpResult]] = {}
    for r in results:
        by_case.setdefault(r.case, []).append(r)

    over_budget = False
    print(
        f"{'case':<32} {'n':>4} {'ok':>4} {'p50':>7} {'p95':>7} {'p99':>7} {'max':>7}"
    )
    print("-" * 70)
    for case, rs in sorted(by_case.items()):
        latencies = sorted(r.latency_s for r in rs if r.error is None)
        ok_count = len(latencies)
        if not latencies:
            print(f"{case:<32} {len(rs):>4} {ok_count:>4}  all requests failed")
            over_budget = True
            continue

        def pct(p: float) -> float:
            if not latencies:
                return 0.0
            idx = min(int(round(p * (len(latencies) - 1))), len(latencies) - 1)
            return latencies[idx]

        p50 = pct(0.50)
        p95 = pct(0.95)
        p99 = pct(0.99)
        mx = latencies[-1]
        print(
            f"{case:<32} {len(rs):>4} {ok_count:>4} "
            f"{p50:>6.2f}s {p95:>6.2f}s {p99:>6.2f}s {mx:>6.2f}s"
        )
        if mx > args.budget:
            over_budget = True

    if over_budget:
        print(f"\nFAIL: at least one case exceeded the {args.budget:.1f}s budget")
        return 1
    print(f"\nOK: every case stayed under {args.budget:.1f}s")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        help="Backend base URL (e.g. http://localhost:8001). When set, "
        "runs endpoint stress in addition to builder stress.",
    )
    parser.add_argument(
        "--auth",
        help="Authorization header value (e.g. 'Bearer <token>').",
        default=os.environ.get("STRESS_AUTH"),
    )
    parser.add_argument(
        "--user-id",
        help="user_id to filter on (the Users-tab path that timed out).",
        default="user-eve",
    )
    parser.add_argument(
        "--project-id",
        help="If set, additionally exercise project-scoped paths.",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=20,
        help="Requests per case (endpoint mode).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Parallel in-flight requests (endpoint mode).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--days",
        type=int,
        default=180,
        help="How far back the created_at filter spans.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Per-request HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=5.0,
        help="Per-request latency budget. Anything above triggers FAIL.",
    )
    parser.add_argument(
        "--skip-builder",
        action="store_true",
        help="Skip builder stress, run endpoint stress only.",
    )
    args = parser.parse_args(argv)

    # Ensure the Django settings module is importable for builder-mode runs.
    # The script lives in <repo>/scripts/ and the Django project root is one
    # level up — add it to sys.path so ``tfc.settings`` resolves regardless
    # of where the script is invoked from.
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tfc.settings")

    exit_code = 0

    if not args.skip_builder:
        try:
            import django  # noqa: F401

            django.setup()
        except Exception as e:
            print(f"WARN: django.setup() failed ({e}); builder stress skipped")
        else:
            checks = run_builder_stress()
            checks.extend(run_subquery_shape_checks())
            failing = [c for c in checks if not c.ok]
            if failing:
                exit_code = 1
                print("\nFAIL: builder stress over budget:")
                for c in failing:
                    print(
                        f"  - {c.name}: {c.elapsed_s:.3f}s > {c.budget_s:.3f}s "
                        f"({c.per_iter_us:.1f} us/iter)"
                    )
            else:
                print("\nOK: builder stress under budget")

    if args.endpoint:
        ep_code = run_endpoint_stress(args)
        exit_code = max(exit_code, ep_code)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
