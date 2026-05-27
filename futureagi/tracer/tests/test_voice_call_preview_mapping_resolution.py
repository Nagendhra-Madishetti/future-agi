"""End-to-end gap test: every attribute path the voice-call TaskLivePreview
surfaces to the user must also resolve at eval-task runtime.

Why this exists
---------------
``frontend/src/sections/tasks/components/TaskLivePreview.jsx`` renders rows for
``rowType === "voiceCalls"`` by merging the list endpoint row with the detail
endpoint payload (``{...listRow, ...detail}``), then walking that merged dict
recursively to populate both the field-name dropdown (``fieldNames``) and the
local resolver (``flatValueMap``). Anything that appears in that walker is a
legal mapping target the user can pick.

The eval-task that actually runs in prod dispatches voiceCalls through
``evaluate_observation_span_observe`` (see ``tracer/utils/eval_tasks.py:280``),
which feeds the saved mapping through ``_process_mapping(mapping, root_span,
…)``. That resolver only sees the **root conversation span's**
``span_attributes`` dict — plus ``_ATTRIBUTE_ALIASES`` shortcuts and the
``_SPAN_PUBLIC_FIELDS`` model fallback. If the UI offers a path the resolver
can't reach, the user picks it, the task runs, and the task fails with
``Required attribute X not found``.

This test:
  1. Loads the merged voice-call response captured from prod (list row + detail
     for trace ``4a6498c5-…`` on project ``586ea737-…``) and walks every
     reachable dotted path the same way the FE walker does.
  2. Seeds a ``Trace`` + root ``ObservationSpan`` whose ``span_attributes`` is
     the actual 79-key root attribute dict from that trace.
  3. Loops over every UI-mappable path and probes ``_process_mapping`` against
     the seeded span. Any path that the FE shows but the resolver can't reach
     is a real user-visible bug — collected and reported in the final assert.

The test is intentionally a single loop (not parametrised) so a CI failure
reports the entire gap surface in one message, not N independent failures.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from tracer.models.observation_span import ObservationSpan
from tracer.utils.eval import _process_mapping

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers — mirror the FE walker in TaskLivePreview.jsx (~:478-499, ~:552-575)
# ---------------------------------------------------------------------------

# Limits match the FE walker so paths claimed by the dropdown also get probed.
_ARRAY_PEEK = 500
_DICT_LIMIT = 5000


def _walk_paths(node, prefix: str = "") -> list[str]:
    """Recursively collect dotted paths from a JSON-ish tree.

    Mirrors the walker in ``TaskLivePreview.jsx`` (the one that powers both
    ``fieldNames`` and ``flatValueMap``). Skips ``_``-prefixed keys, bounded
    array peek + dict size to avoid pathological responses.
    """
    paths: list[str] = []
    if isinstance(node, list):
        for idx, item in enumerate(node[:_ARRAY_PEEK]):
            path = f"{prefix}.{idx}" if prefix else str(idx)
            paths.append(path)
            if isinstance(item, (dict, list)):
                paths.extend(_walk_paths(item, path))
        return paths
    if isinstance(node, dict):
        for key, value in node.items():
            if key.startswith("_"):
                continue
            path = f"{prefix}.{key}" if prefix else key
            paths.append(path)
            if isinstance(value, dict) and len(value) < _DICT_LIMIT:
                paths.extend(_walk_paths(value, path))
            elif isinstance(value, list):
                paths.extend(_walk_paths(value, path))
    return paths


def _strip_attribute_path_prefix(key: str) -> str:
    """Python port of ``stripAttributePathPrefix`` (frontend/src/utils/utils.js:1350).

    Strips ``observation_span.<n>.[span_attributes.]`` from the head and any
    ``span_attributes.`` segment from the middle/head. Saved mappings store
    paths in this stripped form, so the test compares against the same shape.
    """
    import re

    s = re.sub(r"^observation_span\.\d+\.(?:span_attributes\.)?", "", str(key or ""))
    s = re.sub(r"(^|\.)span_attributes\.", r"\1", s)
    return s


def _dedupe_preserving_top_level(paths: list[str]) -> list[str]:
    """Same dedupe semantics as the FE walker: first occurrence of the
    stripped form wins. Top-level keys naturally win because they're emitted
    before their nested duplicates."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in paths:
        short = _strip_attribute_path_prefix(raw)
        if short in seen:
            continue
        seen.add(short)
        out.append(short)
    return out


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def voice_root_span_attrs() -> dict:
    """The actual ``span_attributes`` dict on the conversation root span of
    a real prod voice trace (vapi provider, brewery-tour demo assistant).
    79 top-level keys including all ``call.*``, ``gen_ai.*``,
    ``cost_breakdown.*``, ``conversation.*``, ``workflow.*`` attrs."""
    with (FIXTURES_DIR / "voice_call_root_span_attrs.json").open() as f:
        return json.load(f)


@pytest.fixture(scope="module")
def voice_list_row() -> dict:
    """One row from ``GET /tracer/trace/list_voice_calls/`` — what TaskLivePreview
    sees in ``listData.rows[currentRowIndex]`` before the detail fetch lands."""
    with (FIXTURES_DIR / "voice_call_list_row.json").open() as f:
        return json.load(f)


@pytest.fixture(scope="module")
def voice_detail() -> dict:
    """Response body of ``GET /tracer/trace/voice_call_detail/?trace_id=…``."""
    with (FIXTURES_DIR / "voice_call_detail.json").open() as f:
        return json.load(f)


@pytest.fixture(scope="module")
def merged_preview_dict(voice_list_row: dict, voice_detail: dict) -> dict:
    """Reproduce the merge ``{...currentRow, ...voiceResult}`` from
    ``TaskLivePreview.jsx:377`` — detail wins on key collision."""
    return {**voice_list_row, **voice_detail}


@pytest.fixture(scope="module")
def ui_mappable_paths(merged_preview_dict: dict) -> list[str]:
    """Every dotted path the FE walker emits for this voice call.

    ``spans`` is excluded because ``RowDetailTable`` filters that key out and
    routes spans through its own collapsible renderer. Voice responses don't
    carry a ``span_attributes`` top-level key (the BE pre-flattens), so the
    strip is a no-op here but kept defensive."""
    raw_paths = _walk_paths(
        {k: v for k, v in merged_preview_dict.items() if k != "spans"}
    )
    return _dedupe_preserving_top_level(raw_paths)


@pytest.fixture
def voice_root_span(db, project, trace, voice_root_span_attrs):
    """A conversation root span seeded with the real prod ``span_attributes``."""
    span_id = f"voice_root_{uuid.uuid4().hex[:16]}"
    return ObservationSpan.objects.create(
        id=span_id,
        project=project,
        trace=trace,
        name="conversation",
        observation_type="conversation",
        parent_span_id=None,
        start_time=timezone.now() - timedelta(seconds=5),
        end_time=timezone.now(),
        # Mirror the surface the BE actually persists for vapi conversation
        # roots: span_attributes carries every flattened key.
        span_attributes=voice_root_span_attrs,
        provider="vapi",
        status="OK",
    )


@pytest.fixture
def missing_eval_template_id() -> uuid.UUID:
    """A non-existent template id keeps ``_process_mapping`` on the strict
    (non-custom-eval) branch — missing attrs raise ValueError instead of
    being silently coerced to empty strings. That's the failure mode the
    test needs to surface."""
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

# Keys the FE walker emits whose values are intentionally null in this trace
# (``call_summary`` is null because the call was 3 seconds, ``user_wpm`` because
# only the bot spoke, etc.). The resolver returns a JSON-serialised value for
# non-strings, so a resolved-but-null value is ``"null"`` — a legitimate hit,
# not a failure. We don't penalise these.
_NULL_VALUED_ROOTS = {
    # Top-level keys in the merged response whose value is ``null`` here.
    # These are still mappable surfaces — the test verifies they resolve;
    # the runtime value just happens to be null for this particular trace.
}


def test_every_voice_preview_attribute_resolves_at_eval_runtime(
    voice_root_span,
    ui_mappable_paths,
    missing_eval_template_id,
):
    """Every path TaskLivePreview surfaces as mappable for voiceCalls must be
    resolvable by ``_process_mapping`` against the real root-span
    ``span_attributes``.

    Failures surface as a single ``AssertionError`` listing every unresolvable
    path so the gap-fix work has the full inventory in one place.
    """
    # Sanity: the walker must produce a non-trivial surface, otherwise the
    # test silently passes by enumerating zero paths.
    assert len(ui_mappable_paths) >= 50, (
        f"Walker produced only {len(ui_mappable_paths)} paths — fixture or "
        "walker regressed (expected ~120+ for a vapi voice call)."
    )

    unresolved: list[tuple[str, str]] = []
    resolved_count = 0

    for path in ui_mappable_paths:
        # Skip empty strings just in case the walker emits one for an empty
        # array index. ``_process_mapping`` would treat "" as a missing key
        # anyway.
        if not path:
            continue
        try:
            out = _process_mapping(
                {"v": path},
                voice_root_span,
                eval_template_id=missing_eval_template_id,
            )
        except ValueError as exc:
            # ``_process_mapping`` raises with the exact text below when the
            # candidate, ``<candidate>.value``, every alias, every aliased
            # ``.value``, the dotted-path walk, AND the JSON-parented walk all
            # miss — i.e. the resolver genuinely can't reach this path.
            unresolved.append((path, str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001
            # Anything else (KeyError, AttributeError, …) is also a failure
            # surface — record the type so the gap report is useful.
            unresolved.append((path, f"{type(exc).__name__}: {exc}"))
            continue

        # Resolved key present → counts as success even if the resolved value
        # is the literal string "null" (BE behaviour: non-string values are
        # JSON-dumped, including ``None`` → ``"null"``).
        if "v" not in out:
            unresolved.append((path, "_process_mapping returned no 'v' key"))
            continue
        resolved_count += 1

    if unresolved:
        # Sort for stable diff-friendly output. Truncate the error message per
        # path so the assertion text stays readable even when 50+ paths fail.
        pretty = "\n".join(
            f"  - {p}  →  {err.splitlines()[0][:160]}" for p, err in sorted(unresolved)
        )
        total = len(ui_mappable_paths)
        raise AssertionError(
            f"\n{len(unresolved)} of {total} UI-mappable voice-call paths fail "
            f"to resolve at eval-task runtime ({resolved_count} resolved):\n"
            f"{pretty}\n\n"
            "Either remove these from the TaskLivePreview surface, add them to "
            "_ATTRIBUTE_ALIASES, or extend _process_mapping to derive them the "
            "same way populate_call_logs_result does. Every entry above is a "
            "path a user can pick in the eval mapping picker that will raise "
            "'Required attribute X not found' when the task runs."
        )


def test_voice_alias_shortcuts_resolve_against_real_root_span(
    voice_root_span,
    missing_eval_template_id,
):
    """The friendly shortcuts in ``_ATTRIBUTE_ALIASES`` (recording_url,
    stereo_recording_url, customer_recording_url, assistant_recording_url,
    transcript) must resolve against this real vapi root span so the
    user-facing voice variable picker keeps working.

    This is a defence-in-depth test: it would catch a regression in the
    aliases table that the main loop above might mask if the underlying
    literal also happens to resolve.
    """
    alias_expected_value_keys = {
        # alias → one of the literal span_attribute keys it must redirect to
        "recording_url": "conversation.recording.stereo",
        "stereo_recording_url": "conversation.recording.stereo",
        "customer_recording_url": "conversation.recording.mono.customer",
        "assistant_recording_url": "conversation.recording.mono.assistant",
        # ``transcript`` falls through ``conversation.transcript`` (a list of
        # turns) which is not a single literal key on this vapi root span,
        # then to ``provider_transcript`` which IS present.
        "transcript": "provider_transcript",
    }
    for alias, source_key in alias_expected_value_keys.items():
        expected = voice_root_span.span_attributes.get(source_key)
        if expected is None:
            pytest.fail(
                f"Fixture missing the source key {source_key!r} that alias "
                f"{alias!r} is supposed to fall through to — fixture drift."
            )
        out = _process_mapping(
            {"v": alias},
            voice_root_span,
            eval_template_id=missing_eval_template_id,
        )
        # The resolver JSON-dumps non-string values; ``provider_transcript`` is
        # a stringified payload on this trace, the recording URLs are strings,
        # so a direct equality check is correct for all five aliases.
        assert out["v"] == (
            expected if isinstance(expected, str) else json.dumps(expected)
        ), (
            f"Alias {alias!r} resolved to {out['v']!r} but the source key "
            f"{source_key!r} holds {expected!r}."
        )
