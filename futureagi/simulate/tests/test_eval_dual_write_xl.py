"""Source-level regression guard for the simulate dual-write writer sites.

Mirrors the pattern from ``tracer/tests/test_eval_dual_write.py``: every
assignment into ``call_execution.eval_outputs[<eval_config_id>]`` inside the
simulate temporal activity MUST flow through
``evaluations.engine.normalize.build_simulate_eval_payload``. Pending
placeholders that only need shape symmetry are explicitly carved out below.
"""

from __future__ import annotations

import re
from pathlib import Path

XL_PY = (
    Path(__file__).resolve().parents[1] / "temporal" / "activities" / "xl.py"
).read_text()


# ── writer-site count guard ──────────────────────────────────────────────


def test_every_eval_outputs_write_uses_canonical_builder():
    """Every ``eval_outputs[<id>] = ...`` assignment in xl.py must resolve to
    a ``build_simulate_eval_payload(...)`` call. Bare dict literals are how
    the un-canonical shape leaks back in.

    The right-hand side may wrap across lines after the ``= (`` open paren,
    so we inspect a small forward window per match rather than the line.
    """
    lines = XL_PY.splitlines()
    offending = []
    found = 0
    for idx, line in enumerate(lines):
        if not re.search(r"call_execution\.eval_outputs\[[^\]]+\]\s*=", line):
            continue
        found += 1
        window = "\n".join(lines[idx : idx + 6])
        if "build_simulate_eval_payload(" not in window:
            offending.append(f"line {idx + 1}: {line.strip()}")
    assert found, (
        "No eval_outputs writes found in xl.py — either the writer sites moved "
        "or the locator regex needs an update."
    )
    assert not offending, (
        "eval_outputs assignments not going through build_simulate_eval_payload:\n  "
        + "\n  ".join(offending)
    )


def test_canonical_builder_called_at_each_writer_site():
    """4 writer sites: success / mapping-error / exception / no-transcript.
    Pins the call-site count so a future edit can't silently drop one."""
    calls = re.findall(r"build_simulate_eval_payload\(", XL_PY)
    assert len(calls) == 4, (
        f"Expected 4 build_simulate_eval_payload call sites in xl.py "
        f"(success / mapping-error / exception / no-transcript), found {len(calls)}"
    )
