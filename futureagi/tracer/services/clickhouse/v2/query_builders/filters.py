"""
v2 ClickHouse filter compiler — targets the new CH 25.3 `spans` schema.

Strategy: SUBCLASS the legacy `ClickHouseFilterBuilder` so we inherit all
~1500 lines of frontend-filter-JSON parsing logic AND the shared canonical
filter contract (the operator/type/column-id rules pulled from
`api_contracts/filter_contract.json`). Then rewrite the COLUMN REFERENCES in
the compiled SQL output.

Why this works:
  - Filter operator/type/value contract is identical between v1 and v2. The
    only thing that changes is which CH column the SQL references.
  - Legacy column identifiers (`_peerdb_is_deleted`, `span_attr_str`, etc.)
    are unique tokens; word-boundary substitution is safe.
  - Typed-JSON access syntax (`attributes_extra.path.:Type`) replaces
    `JSONExtractString(span_attributes_raw, 'path')`; a few targeted regex
    rewrites cover the JSONExtract* calls v1 emits.

Why not refactor v1 to use overridable constants:
  - 41 column references across 1657 lines. Touching each line is high-risk
    on a hot dashboard path. The post-rewrite approach keeps v1 unchanged
    and isolates v2 risk to the rewrite + the parity-shadow harness.

Risk mitigations:
  - The parity-shadow harness (tracer/services/clickhouse/v2/shadow.py) runs
    v1 and v2 in parallel and logs diffs. Any v1 emission pattern the
    rewriter doesn't anticipate surfaces as a shadow diff long before any
    query type is flipped to v2-primary.
  - Tests in `tracer/tests/test_ch25_filter_compiler.py` cover every
    column-rewrite case + every JSONExtract* pattern v1 currently emits.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Tuple

from tracer.services.clickhouse.query_builders.filters import (
    ClickHouseFilterBuilder,
    _coerce_strict_bool,
    _sanitize_key,
)
from tracer.services.clickhouse.v2.query_builders import columns as cols


# ─── Simple column-name renames ───────────────────────────────────────────────
# These are tokens; word-boundary regex substitutes them safely.
_COL_RENAMES: Dict[str, str] = {
    "_peerdb_is_deleted": cols.IS_DELETED,
    "_peerdb_version":    cols.VERSION,
    "span_attr_str":      cols.ATTRS_STRING,
    "span_attr_num":      cols.ATTRS_NUMBER,
    "span_attr_bool":     cols.ATTRS_BOOL,
}

# Pre-compile a single regex that matches any legacy column name as a whole word.
_COL_RENAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _COL_RENAMES.keys()) + r")\b"
)


# ─── JSON-overflow access rewrites ────────────────────────────────────────────
# v1 emits `JSONExtractType(span_attributes_raw, 'path.with.dots')`; v2 uses
# CH 25.x typed JSON path access `attributes_extra.path.with.dots.:Type`.
# Same translation applies to `metadata_map` (v1 Map) → `metadata` (v2 typed JSON).
_JSON_EXTRACT_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"JSONExtractString\(\s*span_attributes_raw\s*,\s*'([^']+)'\s*\)"),
     cols.ATTRIBUTES_EXTRA, "String"),
    (re.compile(r"JSONExtractFloat\(\s*span_attributes_raw\s*,\s*'([^']+)'\s*\)"),
     cols.ATTRIBUTES_EXTRA, "Float64"),
    (re.compile(r"JSONExtractInt\(\s*span_attributes_raw\s*,\s*'([^']+)'\s*\)"),
     cols.ATTRIBUTES_EXTRA, "Int64"),
    (re.compile(r"JSONExtractBool\(\s*span_attributes_raw\s*,\s*'([^']+)'\s*\)"),
     cols.ATTRIBUTES_EXTRA, "Bool"),
    (re.compile(r"JSONExtractString\(\s*resource_attributes_raw\s*,\s*'([^']+)'\s*\)"),
     cols.RESOURCE_ATTRS, "String"),
    (re.compile(r"JSONExtractString\(\s*metadata_map\s*,\s*'([^']+)'\s*\)"),
     cols.METADATA_JSON, "String"),
]

# `JSONHas(span_attributes_raw, 'path')` → `(attributes_extra.path.:String IS NOT NULL)`
_JSON_HAS_PATTERN = re.compile(
    r"JSONHas\(\s*(span_attributes_raw|resource_attributes_raw|metadata_map)\s*,\s*'([^']+)'\s*\)"
)
_JSON_HAS_TARGET = {
    "span_attributes_raw":     (cols.ATTRIBUTES_EXTRA, "String"),
    "resource_attributes_raw": (cols.RESOURCE_ATTRS,   "String"),
    "metadata_map":            (cols.METADATA_JSON,    "String"),
}


# ─── v2 attribute-type meta (same shape as v1 module-level constant, retargeted) ─
_SPAN_ATTR_TYPE_META_V2: Dict[str, Tuple[str, Callable[[Any], Any]]] = {
    "text":    (cols.ATTRS_STRING, lambda v: v if isinstance(v, str) else str(v)),
    "number":  (cols.ATTRS_NUMBER, lambda v: float(v)),
    "boolean": (cols.ATTRS_BOOL,   _coerce_strict_bool),
}


def rewrite_v1_sql_to_v2(sql: str) -> str:
    """Translate a v1-compiled SQL string to v2 column references.

    Public so tests can pin every rewrite case directly without going through
    the full filter compiler.

    Order matters:
      1. JSON path access rewrites FIRST — these wrap whole expressions
         containing legacy column names inside `JSONExtract*(...)` calls. We
         must rewrite those expressions before any naked column-name
         substitution would otherwise hit them.
      2. Naked column-name renames SECOND — word-boundary substitution
         catches the remaining direct references (`WHERE _peerdb_is_deleted = 0`).
    """
    # 1. JSON path access
    for pat, target_col, ch_type in _JSON_EXTRACT_PATTERNS:
        sql = pat.sub(
            lambda m, c=target_col, t=ch_type: cols.json_path(c, m.group(1), t),
            sql,
        )

    def _has_repl(m):
        col, ch_type = _JSON_HAS_TARGET[m.group(1)]
        return f"({cols.json_path(col, m.group(2), ch_type)} IS NOT NULL)"
    sql = _JSON_HAS_PATTERN.sub(_has_repl, sql)

    # 2. Naked column-name renames
    sql = _COL_RENAME_RE.sub(lambda m: _COL_RENAMES[m.group(1)], sql)
    return sql


class ClickHouseFilterBuilderV2(ClickHouseFilterBuilder):
    """Filter compiler for the new CH 25.3 spans schema.

    Drop-in replacement for the v1 builder:
      v1: from tracer.services.clickhouse.query_builders.filters import ClickHouseFilterBuilder
      v2: from tracer.services.clickhouse.v2.query_builders.filters import ClickHouseFilterBuilderV2

    Call sites swap one import line; everything else works.
    """

    # Expose the v2 attribute-type meta on the instance.
    SPAN_ATTR_TYPE_META = _SPAN_ATTR_TYPE_META_V2

    def translate(self, filters):  # type: ignore[override]
        sql, params = super().translate(filters)
        return rewrite_v1_sql_to_v2(sql), params

    def translate_sort(self, sort_params):  # type: ignore[override]
        result = super().translate_sort(sort_params)
        # translate_sort may return tuple (sql, params) or bare sql depending
        # on the v1 signature — handle both.
        if isinstance(result, tuple):
            sql, *rest = result
            return (rewrite_v1_sql_to_v2(sql), *rest)
        return rewrite_v1_sql_to_v2(result)


__all__ = ["ClickHouseFilterBuilderV2", "rewrite_v1_sql_to_v2"]
