# Codex review — wave-3 misc-utils chunk (HEAD~10..HEAD, my commits)

Reviewed the wave-3 misc-utils CH25 ORM migration commits authored
in this chunk (excludes `23ffc05c8` and `f02e7e00a`, which are by a
different agent on `project_version.py` and `trace.py`).

## Commits reviewed

```
5feb1e27d refactor(ch25): migrate error_analysis tool/retrieval patterns ORM → CHSpanReader
51bce2e5f refactor(ch25): replay_session — Subquery+OuterRef → CHSpanReader 2-step
043eda448 refactor(ch25): session_comparison fetch_base_session_metrics ORM → CHSpanReader
6a4246102 chore(ch25): observability_provider — annotate 3 ORM sites as KEEP-PG
85e33a9a7 chore(ch25): backfill_call_logs — annotate as KEEP-PG
b0ae7ea9d chore(ch25): user_onboard — annotate ObservationSpan.bulk_create as KEEP-PG
36f4d4972 chore(ch25): migration 0032 — annotate as KEEP-PG (data migration)
0f3ba2528 chore(ch25): seed_dummy_data — annotate module as KEEP-PG (dev seed)
765f390f3 chore(ch25): create_otel_span — annotate module as KEEP-PG (write path)
```

## Findings

### P0

None found.

### P1

- **tracer/utils/replay_session.py:578,582** — `_sort_key()` returns CH
  `start_time` (naive UTC per the repo's CH DateTime64 convention) when
  present and PG `created_at` (timezone-aware per `USE_TZ=True` in
  `tfc/settings/settings.py:331`) as fallback. A partial CH miss
  (mixed CH-present / CH-missing in the same trace list) leads to
  `traces.sort()` comparing naive vs aware datetimes — `TypeError:
  can't compare offset-naive and offset-aware datetimes`. Normalize
  before sorting.

### P2

- **tracer/queries/error_analysis.py:272,542** — `get_tool_usage_patterns`
  and `get_retrieval_patterns` now silently truncate to 50 names via
  the reader's `limit=50` default. The old ORM queries were unbounded
  and consumers call `list(...)`. Projects with more than 50
  tools/retrievers lose tail patterns. Either bump the limit or
  document the product cap and surface the truncation.

- **tracer/queries/error_analysis.py:260,276 +
  tracer/services/clickhouse/v2/span_reader.py:726** — Tool-pattern
  recency now uses span `start_time` rather than PG
  `Trace.created_at`. The docstring documents this, but the semantic
  shift is load-bearing for backfilled / imported traces or delayed
  ingestion: recently ingested traces with old event timestamps drop
  out of the memory window. If accepted, keep as an explicit
  product-level semantic change. Otherwise this needs either a PG
  trace-id prefilter or a CH trace-created-at field.

### P3

- **tracer/utils/observability_provider.py:247–263** —
  `_update_observation_span()` is a fourth PG-write site in this
  module (the `.save(update_fields=[...])`). The three marked sites
  are valid KEEP-PG, but this save shares the same dual-write
  upsert rationale and should get the same annotation.

- **tfc/management/commands/seed_dummy_data.py:9** — the KEEP-PG
  module-level comment says "No reads in this file" and only mentions
  creates, but `_flush()` (around L251) does read/delete
  ObservationSpan rows. Still appropriately KEEP-PG (dev seed/delete);
  the rationale text should mention flush deletes.

- **tracer/tests/test_replay_session_utils.py:611,699** — the unit
  tests still mock the old `.annotate(...).order_by("span_start_time")`
  flow. They no longer exercise the CH lookup or Python sort. Tests
  need a refresh in a follow-up to cover the new path.

`session_comparison` looks structurally OK: two CH reads for one
session, no N+1, missing CH spans fail loudly (ValueError) rather
than dropping rows. Error-analysis tenant scope looks OK at project
scope; empty CH results return `[]`.

Tests not run; static review only.

## Resolution

- P1 (replay_session datetime mix): fix by normalizing both sides
  (tz-aware UTC) before sorting.
- P2 (50-row limit): bump the limit at the call sites or expose
  `limit` via the wrapper's signature. Stronger: bubble the cap up
  to the consumer.
- P2 (start_time vs created_at): documented; accept as explicit
  semantic change, but call out in reader-extension requests that a
  trace-created-at projection on the CH side would resolve the
  drift cleanly.
- P3 observability_provider save: add CH25-TODO above
  `existing_span.save(...)`.
- P3 seed_dummy_data flush: extend module docstring to include reads
  in `_flush()`.
- P3 stale tests: out of scope for this chunk; flagged for follow-
  up.
