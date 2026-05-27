import { describe, expect, it } from "vitest";
import {
  activationStateFixtureList,
  getActivationStateFixture,
} from "../fixtures/activation-state.fixtures";
import {
  hasOnePrimaryAction,
  isInternalHref,
  makeActivationStateErrorFallback,
  normalizeActivationState,
  normalizeProductPath,
  validateActivationStateFixture,
} from "../activation-state-utils";

describe("activation-state utilities", () => {
  it.each(activationStateFixtureList)(
    "normalizes the $name fixture",
    ({ state }) => {
      const normalized = normalizeActivationState(state);

      expect(normalized.schemaVersion).toBe("activation-state-2026-05-26.v1");
      expect(normalized.stage).toBeTruthy();
      expect(normalized.fallbackAction.href).toMatch(/^\//);
      expect(hasOnePrimaryAction(normalized)).toBe(true);
      expect(validateActivationStateFixture(state)).toBe(true);
    },
  );

  it("rejects an unknown stage", () => {
    const fixture = getActivationStateFixture("observeNoSetup");

    expect(() =>
      normalizeActivationState({ ...fixture, stage: "unknown_stage" }),
    ).toThrow(/Unsupported activation stage/);
  });

  it("rejects a missing fallback action", () => {
    const fixture = getActivationStateFixture("observeNoSetup");

    expect(() =>
      normalizeActivationState({ ...fixture, fallback_action: null }),
    ).toThrow(/fallback action/);
  });

  it("rejects external action hrefs", () => {
    const fixture = getActivationStateFixture("observeNoSetup");

    expect(() =>
      normalizeActivationState({
        ...fixture,
        recommended_action: {
          ...fixture.recommended_action,
          href: "https://example.com/phishing",
        },
      }),
    ).toThrow(/external href/);
    expect(isInternalHref("/dashboard/get-started")).toBe(true);
    expect(isInternalHref("https://example.com")).toBe(false);
  });

  it("preserves sample action markers", () => {
    const normalized = normalizeActivationState(
      getActivationStateFixture("sampleTraceReady"),
    );

    expect(normalized.recommendedAction.isSample).toBe(true);
    expect(normalized.recommendedAction.completionEvent).toBe(
      "sample_signal_viewed",
    );
  });

  it("normalizes accepted product path aliases", () => {
    expect(normalizeProductPath("observability")).toBe("observe");
    expect(normalizeProductPath("sample_project")).toBe("sample");
  });

  it("creates a renderable local fallback for hard API failures", () => {
    const fallback = makeActivationStateErrorFallback({
      message: "Network error",
    });

    expect(fallback.stage).toBe("feature_disabled");
    expect(fallback.fallbackAction.href).toBe("/dashboard/get-started");
    expect(fallback.warnings).toContain("activation_state_request_failed");
  });

  it("requires a route match or blocked reason for the primary action", () => {
    const fixture = getActivationStateFixture("observeNoSetup");

    expect(() =>
      normalizeActivationState({
        ...fixture,
        recommended_action: {
          ...fixture.recommended_action,
          href: "/dashboard/not-in-route-map",
        },
      }),
    ).toThrow(/route availability/);

    const blocked = normalizeActivationState({
      ...fixture,
      recommended_action: {
        ...fixture.recommended_action,
        href: null,
        blocked: true,
        blocked_reason: "route_not_implemented",
        route_available: false,
      },
    });
    expect(blocked.recommendedAction.blockedReason).toBe(
      "route_not_implemented",
    );
  });
});
