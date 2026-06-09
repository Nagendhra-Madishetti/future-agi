import { describe, expect, it } from "vitest";

import { buildApiFilterArray } from "../TaskLivePreview";

const attrRow = (filterOp, filterValue) => ({
  property: "attributes",
  propertyId: "customer_tier",
  fieldCategory: "attribute",
  filterConfig: { filterType: "text", filterOp, filterValue },
});

describe("buildApiFilterArray — task live-preview wire builder", () => {
  it("does not merge same-column rows — two not_contains stay two entries", () => {
    const out = buildApiFilterArray([
      attrRow("not_contains", "enterprise"),
      attrRow("not_contains", "startup"),
    ]);

    expect(out).toHaveLength(2);
    expect(
      out.every((f) => f.filter_config.filter_op === "not_contains"),
    ).toBe(true);
    expect(out.map((f) => f.filter_config.filter_value)).toEqual([
      "enterprise",
      "startup",
    ]);
  });

  it("coerces a scalar in value to a list so filter_value survives", () => {
    const out = buildApiFilterArray([attrRow("in", "enterprise")]);

    expect(out[0].filter_config.filter_op).toBe("in");
    expect(out[0].filter_config.filter_value).toEqual(["enterprise"]);
  });

  it("emits an empty-string filter_value for null-ops", () => {
    const out = buildApiFilterArray([attrRow("is_null", undefined)]);

    expect(out[0].filter_config.filter_op).toBe("is_null");
    expect(out[0].filter_config.filter_value).toBe("");
  });

  it("keeps a range op as a two-element array (no scalar coercion)", () => {
    const out = buildApiFilterArray([attrRow("between", [10, 20])]);

    expect(out[0].filter_config.filter_op).toBe("between");
    expect(out[0].filter_config.filter_value).toEqual([10, 20]);
  });
});
