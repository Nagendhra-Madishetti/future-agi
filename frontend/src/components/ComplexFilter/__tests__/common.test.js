import { describe, expect, it } from "vitest";

import { getComplexFilterValidation } from "../common";
import { AdvanceNumberFilterOperators } from "src/utils/constants";
import {
  FILTER_COLUMN_TYPES,
  FILTER_TYPE_ALLOWED_OPS,
} from "src/api/contracts/filter-contract.generated";

describe("ComplexFilter contract wiring", () => {
  it("uses canonical not_between for numeric range filters", () => {
    expect(AdvanceNumberFilterOperators).toContainEqual({
      label: "Not Between",
      value: "not_between",
    });
    expect(AdvanceNumberFilterOperators.map((op) => op.value)).not.toContain(
      "not_in_between",
    );

    const schema = getComplexFilterValidation();
    const parsed = schema.safeParse({
      column_id: "latency_ms",
      _meta: { parentProperty: "System Metrics" },
      filter_config: {
        col_type: "SYSTEM_METRIC",
        filter_type: "number",
        filter_op: "not_between",
        filter_value: ["10", "20"],
      },
    });

    expect(parsed.success).toBe(true);
    expect(parsed.data.filter_config.filter_op).toBe("not_between");
    expect(parsed.data.filter_config.filter_value).toEqual([10, 20]);
  });

  it("validates every generated filter type instead of a local subset", () => {
    const schema = getComplexFilterValidation();

    for (const filterType of Object.keys(FILTER_TYPE_ALLOWED_OPS)) {
      const parsed = schema.safeParse({
        column_id: `${filterType}_field`,
        _meta: { parentProperty: "System Metrics" },
        filter_config: {
          col_type: "SYSTEM_METRIC",
          filter_type: filterType,
          filter_op: "is_null",
        },
      });

      expect(parsed.success, filterType).toBe(true);
      expect(parsed.data.filter_config.filter_value).toBeNull();
    }
  });

  it("validates every generated column type instead of a local subset", () => {
    const schema = getComplexFilterValidation();

    for (const colType of FILTER_COLUMN_TYPES) {
      const parsed = schema.safeParse({
        column_id: `${colType.toLowerCase()}_field`,
        _meta: { parentProperty: "System Metrics" },
        filter_config: {
          col_type: colType,
          filter_type: "text",
          filter_op: "equals",
          filter_value: "ok",
        },
      });

      expect(parsed.success, colType).toBe(true);
    }
  });
});
