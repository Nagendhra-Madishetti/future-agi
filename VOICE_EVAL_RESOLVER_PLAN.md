# Plan: Resolve every voice-call attribute the picker shows

## Context

The pytest `tracer/tests/test_voice_call_preview_mapping_resolution.py::test_every_voice_preview_attribute_resolves_at_eval_runtime` enumerates every dotted path TaskLivePreview surfaces to the user for `rowType=voiceCalls` and probes `_process_mapping` against the real prod root conversation span. **102 of 2,531 paths fail** — every one of those is a path the user can pick in the eval mapping picker that will later raise `Required attribute X not found` when the scheduled `EvalTask` runs through `evaluate_observation_span_observe` → `_process_mapping` (`tracer/utils/eval.py:1722`).

The goal is to make that single test pass — every UI-mappable voice-call path must resolve at eval-task runtime — without breaking the alias-specific test or any of the existing resolver tests under `tracer/tests/test_process_mapping.py`.

The fix is additive: extend `_process_mapping` with three new fallback layers downstream of the current literal/dotted/alias resolution, and trim a small set of genuinely non-mappable infrastructural keys from the FE picker so the resolver isn't asked to invent values for them.

## Where the friendly names come from

The FE doesn't generate them — they're top-level keys in the BE response from list_voice_calls + voice_call_detail. Closed source set:

- **`populate_call_logs_result`** (`tracer/views/trace.py:1143-1158`): `id`, `trace_id`, `call_metadata`, `recording`, `observation_span`, `turn_count`, `talk_ratio`, `agent_talk_percentage`, `avg_agent_latency_ms`, `user_wpm`, `bot_wpm`, `user_interruption_count`, `ai_interruption_count`, `duration_seconds`.
- **`_process_vapi_logs`** (`tracer/services/observability_providers.py:332-496`) and **`_process_retell_logs`** (`:499-666`), spread into the result via `**processed_log`: `call_id`, `customer_name`, `phone_number`, `call_summary`, `call_type`, `assistant_id`, `assistant_phone_number`, `started_at`, `ended_at`, `ended_reason`, `recording_url`, `stereo_recording_url`, `cost_cents`, `cost_breakdown`, `recording_available`, `transcript_available`, `messages`, `message_count`, `overall_score`, `response_time_ms`, `response_time_seconds`, `created_at`, `status`.

The alias / synthesizer additions below cover this entire set.

## Resolution flow after the change

`_process_mapping(mapping, span, eval_template_id)` will probe each attribute through this ordered pipeline. First non-`_MISSING` wins; existing layers preserved.

```
1. EXISTING — Literal in span_attributes / "<attribute>.value"
2. EXISTING — _ATTRIBUTE_ALIASES candidates (each tried as literal and ".value")
              → expanded in this change to cover every derived friendly name
                that maps 1:1 to an existing span_attribute key
3. EXISTING — _SPAN_PUBLIC_FIELDS getattr fallback
              → expanded in this change with safe model fields
4. NEW      — _TRACE_FALLBACK_FIELDS: cross-entity fields from span.trace
              (trace_id, project_id, created_at — span.trace is the FK,
              already loaded by the dispatcher; no extra query in practice)
5. NEW      — Voice synthesizer dispatch (only when observation_type=="conversation")
              For derived values the BE response builder computes at API time
              but never persists (recording_available, messages from raw_log,
              cost_breakdown object reconstruction, etc.). Pure functions,
              no DB hits; some call ObservabilityService.process_raw_logs
              on span_attrs.raw_log (cached per _process_mapping invocation).
6. EXISTING — Missing-key handling (custom-eval → empty, system-eval → ValueError)
```

### Worked examples (one per category)

- `recording_url` → existing alias chain → `conversation.recording.stereo` (literal hit).
- `duration_seconds` → new alias → `call.duration` (literal hit).
- `start_time` → new `_SPAN_PUBLIC_FIELDS` entry → `getattr(span, "start_time")`.
- `trace_id` → new `_TRACE_FALLBACK_FIELDS` layer → `str(span.trace_id)`.
- `recording_available` → voice synthesizer → bool(any `conversation.recording.*` key in span_attrs).
- `messages.0.content` → voice synthesizer → re-runs `process_raw_logs(span_attrs.raw_log, span.provider)` and walks `[0].content`. **Not an alias** — `messages` is the full raw array (includes system prompt); `conversation.transcript.<n>.*` is the cleaned conversation. Different data.
- `eval_outputs.<id>.name` → filtered from FE picker (recursive eval result; not meaningful as eval input).

## Critical files

### Backend
- **`futureagi/tracer/utils/eval.py`** — expand `_ATTRIBUTE_ALIASES`, extend `_SPAN_PUBLIC_FIELDS`, add `_TRACE_FALLBACK_FIELDS` + resolver, wire synthesizer dispatch into `_process_mapping`.
- **`futureagi/tracer/utils/voice_attribute_synthesizer.py`** (NEW) — pure-function synthesizers mirroring `populate_call_logs_result`/`_process_vapi_logs`/`_process_retell_logs`. Single entrypoint `synthesize_voice_field(span, span_attrs, attribute) -> _MISSING | value`.

### Frontend
- **`frontend/src/sections/tasks/components/TaskLivePreview.jsx`** — call a new shared `shouldSkipFieldPath` from both walkers (`fieldNames` `useMemo` at ~:478 and `walkValues` inside `handleRunTest` at ~:552).
- **`frontend/src/utils/utils.js`** — export `NON_MAPPABLE_VOICE_HEADS` and `shouldSkipFieldPath(key)`.

### Test (already exists; will become the verification surface)
- **`futureagi/tracer/tests/test_voice_call_preview_mapping_resolution.py`** — mirror the same blocklist in the Python `_walk_paths` so the test probes the same surface the picker exposes.

## Detailed changes

### 1. Expand `_ATTRIBUTE_ALIASES` (`tracer/utils/eval.py:128`)

Cover **every friendly name from `populate_call_logs_result` + `_process_vapi_logs` + `_process_retell_logs`** that maps 1:1 to an existing flat span_attribute key. Future-proofs against BE renaming the underlying key.

```python
_ATTRIBUTE_ALIASES.update({
    # Vapi/conversation derived names → flat span_attribute keys
    "duration_seconds":      ["call.duration"],
    "turn_count":            ["call.total_turns"],
    "talk_ratio":            ["call.talk_ratio"],
    "bot_wpm":               ["call.bot_wpm"],
    "user_wpm":              ["call.user_wpm"],
    "customer_name":         ["call.participant_phone_number"],
    "phone_number":          ["call.participant_phone_number"],
    "call_id":               ["vapi.call_id"],
    "provider_call_id":      ["vapi.call_id"],
    "agent_talk_percentage": ["call.agent_talk_percentage"],
    "avg_agent_latency_ms":  ["avg_agent_latency_ms"],
    "user_interruption_count":  ["user_interruption_count"],
    "ai_interruption_count":    ["ai_interruption_count"],
    "user_interruption_rate":   ["user_interruption_rate"],
    "ai_interruption_rate":     ["ai_interruption_rate"],
    "ended_reason":          ["ended_reason"],
    # Recording paths (object-shape from detail → flat keys in span_attrs)
    "recording.mono.combined_url":  ["conversation.recording.mono.combined"],
    "recording.mono.customer_url":  ["conversation.recording.mono.customer"],
    "recording.mono.assistant_url": ["conversation.recording.mono.assistant"],
    "recording.stereo_url":         ["conversation.recording.stereo"],
    # id is the trace UUID in the voice-call response; route to trace fallback
    "id": ["trace_id"],
})
```

### 2. Extend `_SPAN_PUBLIC_FIELDS` (`tracer/utils/eval.py:2216`)

The FE walker's `stripAttributePathPrefix` collapses `observation_span.0.<field>` → `<field>`, exposing these `ObservationSpan` model fields bare. They're already safe model accesses — just need to be on the allow-list:

```python
_SPAN_PUBLIC_FIELDS = frozenset({
    # existing entries unchanged
    ...,
    # NEW
    "start_time", "end_time", "parent_span_id",
    "tags", "metadata", "span_events",
})
```

`span_attributes` (the whole bag) is intentionally NOT added — picking the entire JSON blob as an eval input is virtually never useful, and the alias/literal dropdown covers any specific sub-key.

### 3. Add `_TRACE_FALLBACK_FIELDS` (`tracer/utils/eval.py`)

```python
_TRACE_FALLBACK_FIELDS = frozenset({"trace_id", "project_id", "created_at"})

def _resolve_trace_fallback(span, attribute):
    if attribute not in _TRACE_FALLBACK_FIELDS:
        return _MISSING
    if attribute == "trace_id":
        return str(span.trace_id) if span.trace_id else _MISSING
    if attribute == "project_id":
        return str(span.project_id) if span.project_id else _MISSING
    if attribute == "created_at":
        return getattr(span.trace, "created_at", _MISSING)
    return _MISSING
```

### 4. New `voice_attribute_synthesizer.py`

```python
def synthesize_voice_field(
    span: ObservationSpan,
    span_attrs: dict,
    attribute: str,
    *,
    _processed_log_cache: dict | None = None,
) -> Any | _MISSING:
    if span.observation_type != "conversation":
        return _MISSING

    # Route attribute heads to handlers
    head = attribute.split(".", 1)[0]
    handler = _VOICE_SYNTHESIZER_HEADS.get(head) or _VOICE_SYNTHESIZER_EXACT.get(attribute)
    if not handler:
        return _MISSING
    return handler(span, span_attrs, attribute, _processed_log_cache)
```

Concrete synthesizers (mirror `_process_vapi_logs`/`_process_retell_logs` derivation):

| Attribute pattern | Implementation |
|---|---|
| `recording_available` | `bool(any(span_attrs.get(k) for k in CONVERSATION_RECORDING_KEYS))` |
| `transcript_available` | `bool(span_attrs.get("provider_transcript") or _has_transcript_keys(span_attrs))` |
| `recording`, `recording.mono` | reuse `_build_recording_dict(span_attrs)` from `tracer/views/trace.py:1054` |
| `started_at` | `span.start_time.isoformat()` |
| `ended_at` | `span.end_time.isoformat() if span.end_time else _MISSING` |
| `cost_breakdown` (object form) | reconstruct dict from `cost_breakdown.*` flat keys in span_attrs |
| `cost_cents` | `(span_attrs.get("cost_breakdown.total") or 0) * 100` |
| `assistant_id` | extract from raw_log (vapi: `assistantId`, retell: `agent_id`) |
| `assistant_phone_number` | extract from raw_log (vapi: `phoneNumber.number`, retell: `from_number`) |
| `call_summary` | raw_log path: vapi `summary`, retell `call_analysis.call_summary` |
| `error_message` | `span.status_message if span.status == "ERROR" else _MISSING` |
| `overall_score` | `span_attrs.get("raw_log", {}).get("overallScore")` |
| `response_time_ms`, `response_time_seconds` | raw_log keys with same names |
| `message_count` | `len(synthesize(messages))` |
| **`messages` and `messages.<n>.<field>` (NEW per user feedback)** | Re-run `ObservabilityService.process_raw_logs(span_attrs["raw_log"], span.provider, span_attributes=span_attrs)` and walk `processed["messages"]`. Caches the processed_log per `_process_mapping` call so multiple `messages.*` lookups share one normalization pass. **This is the full raw array including system prompt — different data from the cleaned `conversation.transcript.<n>.*` keys.** |

Imports the BE helpers directly so derivation logic stays single-sourced:
- `_build_recording_dict` from `tracer/views/trace.py`
- `ObservabilityService.process_raw_logs` from `tracer/services/observability_providers.py`
- `CallAttributes`, `ConversationAttributes` from `tracer/utils/otel.py:563-586`

### 5. Wire new layers into `_process_mapping`

In `tracer/utils/eval.py:424-465`, after the existing alias loop and `_SPAN_PUBLIC_FIELDS` check, add:

```python
if resolved_value is _MISSING:
    trace_fallback = _resolve_trace_fallback(span, attribute)
    if trace_fallback is not _MISSING:
        resolved_value = trace_fallback

if resolved_value is _MISSING:
    from tracer.utils.voice_attribute_synthesizer import synthesize_voice_field
    synth = synthesize_voice_field(
        span, span_attrs, attribute,
        _processed_log_cache=_processed_log_cache,
    )
    if synth is not _MISSING:
        resolved_value = synth
```

`_processed_log_cache` is a dict-local-to-the-call so repeated `messages.0.*`, `messages.1.*`, `message_count` lookups in one mapping share the same `process_raw_logs` result.

### 6. FE blocklist (`frontend/src/utils/utils.js`)

`messages` is **NOT** in the blocklist — it's a distinct data source (full raw conversation including system prompt) and is handled by the synthesizer.

```javascript
export const NON_MAPPABLE_VOICE_HEADS = new Set([
  // Recursive eval / infrastructural surfaces
  "eval_outputs", "evaluation_data", "observation_span",
  // ObservationSpan model infrastructure (FKs, tenancy, execution state)
  "custom_eval_config", "eval_id", "eval_status", "model_parameters",
  "prompt_version", "provider_logo", "org_id", "org_user_id",
  "project", "project_version", "trace", "span_attributes",
  // Redundant alt-shapes of canonical flat keys
  // - transcript: re-shape of conversation.transcript.<n>.* (no extra info)
  // - call_metadata: just {provider, provider_log_id}, covered by span.provider + vapi.call_id
  // - analysis_data: vapi-specific {summary, success_evaluation}, mostly null;
  //   underlying values reachable via raw_log.analysis.* flat keys when present
  "transcript", "call_metadata", "analysis_data",
]);

export const shouldSkipFieldPath = (key) => {
  if (!key) return true;
  if (key.startsWith("_")) return true;
  const head = key.split(".")[0];
  return NON_MAPPABLE_VOICE_HEADS.has(head);
};
```

Both walkers in `TaskLivePreview.jsx` change `if (k.startsWith("_")) continue;` → `if (shouldSkipFieldPath(k)) continue;` (at `:490` and `:567`).

### 7. Python test mirror

In `tracer/tests/test_voice_call_preview_mapping_resolution.py`, mirror the same blocklist in `_walk_paths` so the test enumerates the same surface the picker exposes:

```python
_NON_MAPPABLE_HEADS = frozenset({
    "eval_outputs", "evaluation_data", "observation_span",
    "custom_eval_config", "eval_id", "eval_status", "model_parameters",
    "prompt_version", "provider_logo", "org_id", "org_user_id",
    "project", "project_version", "trace", "span_attributes",
    "transcript", "call_metadata", "analysis_data",
})
```

No other test changes; the single looping test stays the verification entry point.

## Verification

1. **The single looping test must report 0 unresolved paths.**
   ```
   docker compose -f docker-compose.test.yml -p futureagi-test up -d
   PGPASSWORD=test_password /opt/homebrew/opt/libpq/bin/psql \
     "host=localhost port=15432 user=test_user dbname=test_tfc_test" \
     -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
   set -a && source /Users/atharva/FutureAGI/core-backend/.env.test.local && set +a
   cd futureagi
   uv run pytest tracer/tests/test_voice_call_preview_mapping_resolution.py -v --no-migrations
   ```
   Expected: both `test_every_voice_preview_attribute_resolves_at_eval_runtime` and `test_voice_alias_shortcuts_resolve_against_real_root_span` pass.

2. **Regression sweep**: existing resolver tests stay green.
   ```
   uv run pytest tracer/tests/test_process_mapping.py tracer/tests/test_eval_task_runtime.py -v --no-migrations
   ```

3. **Manual smoke** (optional): in the local app, Task Create → voice calls → live preview → mapping picker.
   - Picker no longer offers `eval_outputs.*`, `evaluation_data`, `transcript.*`, `analysis_data.*`, `call_metadata.*`, model-infra fields.
   - Picker DOES offer `messages.0.content`, `messages.0.role`, etc. (synthesizer-backed).
   - Picking any remaining attribute and hitting "Test" returns a resolved value (no "Required attribute … not found" error).

## Out of scope (separate follow-up PRs)

- **Centralizing all four resolver families** (span / trace / session / dataset) into one module. The alias/synthesizer additions here are prerequisites that make centralization tractable; doing both in one PR conflates the changes.
- **Vapi/retell provider-specific synthesizers extracted into a provider adapter** — the synthesizer currently calls `process_raw_logs` which already branches on provider. Cleaner long-term but small surface for now.
