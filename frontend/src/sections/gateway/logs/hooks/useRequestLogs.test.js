import { describe, expect, it } from "vitest";
import { buildFilterParams } from "./useRequestLogs";

describe("buildFilterParams", () => {
  it("maps request-log filter drawer values and omits URL-only onboarding params", () => {
    expect(
      buildFilterParams({
        statusCodeMin: "400",
        statusCodeMax: "499",
        minLatency: "100",
        maxLatency: "900",
        isError: "true",
        guardrailTriggered: "true",
        requestId: "req-1",
        journeyStep: "review_gateway_log",
        onboarding: "review-request",
        source: "onboarding",
        tourAnchor: "gateway_request_button",
        campaignKey: "gateway_review_request",
      }),
    ).toEqual({
      min_status_code: "400",
      max_status_code: "499",
      min_latency: "100",
      max_latency: "900",
      is_error: "true",
      guardrail_triggered: "true",
      request_id: "req-1",
    });
  });
});
