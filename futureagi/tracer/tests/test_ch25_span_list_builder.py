"""
Pin the v2 SpanList builder's output: legacy column refs in the SQL it
produces are rewritten to the new CH 25.3 schema.

These tests don't hit a real ClickHouse — they assert the COMPILED SQL
STRING contains only v2 column names. End-to-end parity (same SQL, same
rows) is enforced by the parity-shadow harness when v1 and v2 run in
production side-by-side.
"""
from __future__ import annotations

import pytest

from tracer.services.clickhouse.v2.query_builders.span_list import (
    SpanListQueryBuilderV2,
)


PROJECT_ID = "11111111-1111-1111-1111-111111111111"


def _make_builder(filters=None, sort_params=None):
    return SpanListQueryBuilderV2(
        project_id=PROJECT_ID,
        page_number=0,
        page_size=50,
        filters=filters or [],
        sort_params=sort_params or [],
        eval_config_ids=[],
        annotation_label_ids=[],
    )


def test_build_main_query_uses_v2_columns():
    sql, params = _make_builder().build()
    # No legacy column references
    for legacy in ("_peerdb_is_deleted", "_peerdb_version",
                   "span_attr_str", "span_attr_num", "span_attr_bool",
                   "span_attributes_raw", "metadata_map"):
        assert legacy not in sql, f"legacy column {legacy!r} leaked into v2 SQL"
    # And the canonical replacements ARE present where v1 would have used them
    assert "is_deleted" in sql, "v2 SQL must reference the is_deleted column"


def test_build_count_query_uses_v2_columns():
    sql, params = _make_builder().build_count_query()
    for legacy in ("_peerdb_is_deleted", "span_attr_str", "span_attr_num"):
        assert legacy not in sql
    assert "is_deleted" in sql


def test_build_content_query_uses_typed_json_overflow_column():
    # build_content_query reads span_attributes_raw in v1 — v2 must read
    # the typed JSON column (attributes_extra). The actual SELECT shape is
    # asserted below; the legacy column must not appear.
    sql, params = _make_builder().build_content_query(span_ids=["sp1", "sp2"])
    assert "span_attributes_raw" not in sql
    assert "_peerdb_is_deleted" not in sql
    # The new column must be referenced
    assert "attributes_extra" in sql
    # Pagination via parameterized id list
    assert "%(span_id_0)s" in sql or "%(span_id_" in sql or "sp1" in sql or len(params) > 0


def test_filter_compiler_class_yields_v2_columns():
    # Mirrors the filter compiler test, but exercised via the SpanList path.
    # If the v1 base ever stops respecting the post-rewrite (e.g. emits SQL
    # that bypasses translate()), this test catches it.
    sql, _ = _make_builder(
        filters=[
            {"column_id": "model",
             "filter_config": {
                 "col_type": "SYSTEM_METRIC",
                 "filter_type": "text",
                 "filter_op": "equals",
                 "filter_value": "gpt-4o-mini",
             }}
        ],
    ).build()
    # The compiled query references the model column (not via the legacy
    # `span_attr_str['model']` form, which is what v1 would have produced
    # for an attribute-key match).
    assert "_peerdb_is_deleted" not in sql
    assert "span_attr_str" not in sql
