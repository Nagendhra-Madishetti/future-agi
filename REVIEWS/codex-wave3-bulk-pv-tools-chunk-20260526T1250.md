# Codex review — wave-3 bulk_selection / project_version / AI tools chunk

**Date:** 2026-05-26T12:50 UTC
**Branch:** feat/ch25-spans-migration
**Tip:** ba48449a8 (before P1 #1 fix); fix commit lands after.
**Scope:** wave-3 ORM-to-CHSpanReader migration covering:
  - `tracer/views/project_version.py` (outlier scan migration + 3 metric sites deferred)
  - `ai_tools/tools/tracing/get_trace_analytics.py` (main aggregate migrated; group-by KEEP-PG)
  - `model_hub/services/bulk_selection.py` (KEEP-PG comment refresh — wave-3 readers exist but FilterEngine fusion gates)
  - `model_hub/queries/prompt/prompt_metrics.py` (KEEP-PG comment refresh — wave-3 didn't add the needed reader)
  - `model_hub/views/annotation_queues.py` (KEEP-PG comment refresh on 3 Prefetch sites)

## Commits under review

```
23ffc05c8 refactor(ch25): migrate project_version.py outlier scan ORM → CHSpanReader
3956b6c37 refactor(ch25): migrate get_trace_analytics.py main aggregate ORM → CHSpanReader
eaf80aad6 docs(ch25): refresh bulk_selection.py CH25-TODOs to reflect wave-3 readers
a26074214 docs(ch25): note wave-3 left prompt_metrics.py reader extension outstanding
ba48449a8 docs(ch25): note wave-3 left annotation_queues.py Prefetch sites deferred
```

## Codex findings (verbatim summary)

### P0
None found.

### P1
1. **project_version.py:1282** — `statistics.stdev()` vs Django default `StdDev(...)`. Django 5.1 `StdDev(sample=False)` (the bare-form default used at the legacy sites) maps to `STDDEV_POP` (population stddev), not sample. `statistics.stdev` is sample (n-1). The mismatch can silently shift z-score outlier counts.
   - **Status:** REAL BUG. Fixed in follow-up commit by switching both `latency_std` and `cost_std` to `statistics.pstdev` and updating the comment that claimed sample-stddev parity. Verified the Django source at `.venv/lib/python3.13/site-packages/django/db/models/aggregates.py:191`:
     ```
     def __init__(self, expression, sample=False, **extra):
         self.function = "STDDEV_SAMP" if sample else "STDDEV_POP"
     ```
     The legacy call sites used the bare-form `StdDev("latency_ms", filter=...)` (no `sample=True`), so `STDDEV_POP` is what shipped in production.

2. **project_version.py:1265 / 1268 / 1311** — root span detection accepts only `parent_span_id == ""`; Codex claimed CH schema has `parent_span_id Nullable(String)` so NULL-root spans could be dropped.
   - **Status:** FALSE POSITIVE against the CH contract. Schema 002 (`002_spans_v2.sql:60`) declares:
     ```
     parent_span_id      String  DEFAULT '',
     ```
     Non-nullable, defaults to empty string. The CHSpan dataclass field is `str` (not Optional). `_row_to_chspan` does not normalize parent_span_id to None — only the seven listed UUID fields get that treatment. Every other wave-2/wave-3 reader method uses `parent_span_id = ''` consistently (span_reader.py:474, 945, 1024, 1059, 1101). The migration here matches the established CH reader contract.
   - Schema 012 line 91 uses `parent_span_id = '' OR parent_span_id IS NULL` defensively for the materialised view, but the underlying `spans` table never produces NULL. No code change.

3. **get_trace_analytics.py:126** — `avg_latency` reconstruction `sum(latency_ms) / span_count` differs from legacy `Avg("latency_ms")` when PG had null-latency rows.
   - **Status:** SYSTEM-WIDE CH ADAPTER PROPERTY, not a regression of this migration. The CH adapter (`tracer/services/clickhouse/v2/adapter.py:376`) coerces PG-null `latency_ms` to 0 at write time. Every wave-2/wave-3 reader method that computes latency averages uses plain `avg(latency_ms)` (span_reader.py:616, 738, 851, 910, 1060, 1105) which counts those zeros in the denominator. The reconstruction `sum/count` here is arithmetically identical to `avg(latency_ms)` over the same row set, so it matches the system-wide CH semantic. Codex's PG-vs-CH drift complaint applies to the CH-as-canonical-store choice that predates this PR.
   - **Action:** Added a comment in get_trace_analytics.py citing the adapter coercion and the system-wide pattern, so future readers don't re-litigate. No reader extension added (would create per-call drift across the codebase).

### P2
- **project_version.py:1249** — `list_by_trace_ids()` returns full CHSpan rows for the outlier scan; the old `.values(...)` selected only 7 fields. Memory/payload regression for very large project versions but no correctness gap.
  - **Status:** ACKNOWLEDGED. The reader's only per-trace-list endpoint that returns row-level data is `list_by_trace_ids`; trimming the column set would require a dedicated method (e.g. `list_by_trace_ids_minimal(trace_ids, *, fields=[])`). Not adding because:
    - (a) per the rules in this chunk, no new reader methods unless proposed-and-approved;
    - (b) the outlier scan is already gated on a single project_version's trace set (typically a few hundred traces, not millions);
    - (c) it's the same pattern wave-1 / wave-2 used in tracer/tasks/session.py and tracer/utils/replay_session.py.
  - If memory becomes an issue, propose `list_by_trace_ids_minimal` in a future reader extension wave.

### P3 / Verified
- Tenant scope preserved in both migrations:
  - project_version.py:1216 — `ProjectVersion.objects.get(... project__organization=...)` org-gates the outer scope.
  - project_version.py:1223 — `Trace.objects.filter(project=project_version.project, project_version=project_version).values_list("id", flat=True)` is org-scoped via project FK.
  - get_trace_analytics.py:72 — `trace_qs` filters `project__organization=context.organization`.
  - get_trace_analytics.py:116 — pre-fetched trace_ids inherit the org filter.
- The three project_version.py metric sites are correctly deferred and still PG:
  - project_version.py:209 (winner rollup)
  - project_version.py:498 (export rollup)
  - project_version.py:1513 (list_runs rollup)
  Each comment was refreshed to cite wave-3 `per_project_version_metric_aggregate` exists but the EvalLogger `metric_<config.id>` JSON-shape reproduction is the cross-cutting refactor.
- bulk_selection.py avoided the anti-patterns: no ad-hoc CH SQL, no Subquery+OuterRef → dict-reader swaps. Module docstring at line 21 documents the FilterEngine-fusion gap clearly.
- The three annotation_queues.py Prefetch sites are correctly deferred per the wave-1 (4c734e9cc) decision.
- `StdDev` import was removed from project_version.py imports (line 8-22) since the only remaining references are inside comments and `statistics.pstdev` does the work now.

## Reader extension requests surfaced

1. **`window_aggregate_with_stddev(trace_ids, *, parent_only)`** — single-dict variant of `trace_aggregate_with_stddev` for the project_version outlier scan, returning `{avg_latency_ms, stddev_latency_ms, avg_cost, stddev_cost, span_count, ...}`. Would let the outlier scan run as one CH GROUP BY query instead of fetching all rows + Python aggregating. Not added in this chunk (rule: no new readers without prior approval) — the Python aggregate path works.

2. **`aggregate_by_organization(org_id, *, since, until, trace_ids=None)`** — would route the no-project_id branch of get_trace_analytics.py through CH. Today it KEEP-PG with the legacy `trace__created_at__gte=since` join.

3. **`per_project_group_by(project_id, *, group_by_field, observation_type=None, since=None, until=None, status_filter=None, limit=50)`** — generalised group-by for the model/status branches of get_trace_analytics.py. Today those KEEP-PG.

4. **`list_spans_for_prompt_template(prompt_template_id, *, prompt_version_ids, filters, search_term, page_number, page_size)`** — would unblock prompt_metrics.py via the ClickHouseFilterBuilder.

5. **`list_spans_by_project_with_filters(project_id, *, filters, ...)`** — would unblock the span filter-mode branch of bulk_selection.py.

6. **`first_last_messages_by_session_ids(session_ids, *, project_id)`** — would unblock the `first_message` / `last_message` Subqueries in bulk_selection.py::_apply_session_filters.

7. **`list_by_trace_ids_minimal(trace_ids, *, fields=[])`** — narrow column-list variant for memory-constrained per-trace scans (motivated by the P2 finding above).

## Notes for next reviewer

- The `statistics.pstdev` decision was verified against the actual Django source (not Codex's initial claim). If anyone proposes to switch back to `statistics.stdev`, point them at the linked aggregates.py line.
- The `parent_span_id == ''` convention is now used in 7+ places across the reader and call sites. If you ever see Codex flag this in a future review, point it at schema 002 line 60.
- The PG-null-latency-coerced-to-0 semantic is system-wide. Don't add per-call workarounds — fix it once at the adapter level if it ever needs reversing.
