# Codex review — tasks/utils chunk (HEAD~5..HEAD before fixups)

Reviewed five commits migrating Django ORM `ObservationSpan.objects` sites
in `tracer/tasks/`, `tracer/utils/`, `simulate/`, `tfc/`, and
`agent_playground/` to ClickHouse reads via `CHSpanReader.get_reader()`.

## Commits reviewed

```
421b4fc79 refactor(ch25): migrate imagine fetch_trace_data ORM → CHSpanReader
178243fc4 refactor(ch25): migrate fetch_voice_conversation_span ORM → CHSpanReader
778d8779c refactor(ch25): migrate replay_session voice-trace fetches ORM → CHSpanReader
7a28a8479 refactor(ch25): migrate dataset.process_spans_chunk_task ORM → CHSpanReader
1ca3d3168 refactor(ch25): migrate trace_to_graph convert_trace_to_graph ORM → CHSpanReader
```

## Findings

### P1

- **trace_to_graph.py:49, dataset.py:62** — `attributes_extra_as_dict()` can return a
  string under schema 013, so `.items()` / `.get()` reconstruction can
  crash. `span_reader` still selects `toJSONString(attributes_extra)`
  while schema 013 makes it a raw `String`; `json.loads('"{}"')` yields
  `"{}"`, not `{}`. Fix reader/helper before relying on it.

### P2

- **dataset.py:69, trace_to_graph.py:52** — typed-map merge does not restore PG
  JSON scalar types. `attrs_bool` comes back as `0/1`, and integer
  attrs from `attrs_number` come back as floats, so dataset
  `span_attributes` cells can change from `true`/`1` to `1`/`1.0`.

- **dataset.py:192** — missing CH spans are silently skipped. If PG selection
  found span IDs but CH is lagging/diverged, the task reports success
  with fewer rows/cells; this should fail/retry or explicitly surface
  missing IDs.

### P3

- **replay_session.py:589** — `_is_voice_trace_query` is a bounded N+1. It does
  up to 10 full `list_by_trace` reads; use one CH query or
  `list_by_trace_ids` with an observation-type filter to match the old
  single `.exists()` shape.

- **dataset.py:116** — `child_spans` ordering changed to CH ascending
  `start_time`. Old `_serialize_span_tree()` used `ObservationSpan`
  default `-start_time`, so child span JSON order can change even
  though top-level `Row.order` is preserved within a chunk.

No P0 found. Imports look intentional: remaining `ObservationSpan`
imports are still used, especially replay session ordering and simulate
session metrics.

## Resolution

All P1 / P2(dataset.py:192) / P3 findings addressed in follow-up
per-file commits (one commit per file per project rule):

```
91f85bb4c refactor(ch25): address codex review for tracer/tasks/dataset.py
b555d0318 refactor(ch25): address codex review for tracer/utils/replay_session.py
1d5a56203 refactor(ch25): address codex review for simulate/utils/session_comparison.py
f324ef38d refactor(ch25): address codex review for agent_playground/services/trace_to_graph.py
```

The remaining P2 (typed-map JSON scalar types) is a property of
`CHSpanReader` + adapter (DECISIONS #018) and affects every reader
consumer, not just these migrations. Fix belongs in the reader, not
per-call-site — flagged for the reader hardening track. See the chunk
report for the required reader extensions.
