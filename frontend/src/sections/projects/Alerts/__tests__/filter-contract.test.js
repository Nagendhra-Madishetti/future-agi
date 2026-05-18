import { describe, expect, it } from "vitest";

import { convertFiltersToPayload, isSpanAttrFilterValid } from "../common";
import { transformFilterResponse } from "../components/validation";

describe("alert filter contract", () => {
  it("sends canonical span attribute filters to the API", () => {
    const payload = convertFiltersToPayload([
      {
        property: "observationType",
        filterConfig: { filterValue: "llm" },
      },
      {
        property: "attributes",
        propertyId: "customer_tier",
        filterConfig: {
          filterType: "text",
          filterOp: "equals",
          filterValue: "enterprise",
        },
      },
    ]);

    expect(payload).toEqual({
      observation_type: ["llm"],
      span_attributes_filters: [
        {
          column_id: "customer_tier",
          filter_config: {
            filter_type: "text",
            filter_op: "equals",
            filter_value: "enterprise",
            col_type: "SPAN_ATTRIBUTE",
          },
        },
      ],
    });
    expect(payload.span_attributes_filters[0]).not.toHaveProperty("columnId");
    expect(payload.span_attributes_filters[0]).not.toHaveProperty(
      "filterConfig",
    );
  });

  it("validates canonical span attribute filters before submit", () => {
    expect(
      isSpanAttrFilterValid([
        {
          column_id: "customer_tier",
          filter_config: {
            filter_type: "text",
            filter_op: "equals",
            filter_value: "enterprise",
          },
        },
      ]),
    ).toBe(true);
    expect(
      isSpanAttrFilterValid([
        {
          column_id: "customer_tier",
          filter_config: {
            filter_type: "text",
            filter_op: "equals",
            filter_value: "",
          },
        },
      ]),
    ).toBe(false);
  });

  it("hydrates canonical filters from the API into local form state", () => {
    const filters = transformFilterResponse({
      observation_type: ["llm"],
      span_attributes_filters: [
        {
          column_id: "customer_tier",
          filter_config: {
            filter_type: "text",
            filter_op: "equals",
            filter_value: "enterprise",
          },
        },
      ],
    });

    expect(filters).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          property: "observationType",
          filterConfig: expect.objectContaining({ filterValue: "llm" }),
        }),
        expect.objectContaining({
          propertyId: "customer_tier",
          property: "attributes",
          filterConfig: {
            filterType: "text",
            filterOp: "equals",
            filterValue: "enterprise",
          },
        }),
      ]),
    );
  });
});
