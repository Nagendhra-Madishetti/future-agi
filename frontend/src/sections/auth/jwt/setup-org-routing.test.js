import { describe, expect, it } from "vitest";

import { paths } from "src/routes/paths";

import {
  isSafeSetupReturnTo,
  resolveSetupCompletionHref,
  setupCompletionHomeHref,
} from "./setup-org-routing";

describe("setup org completion routing", () => {
  it("defaults new users to the first-run home", () => {
    expect(setupCompletionHomeHref()).toBe(
      `${paths.dashboard.home}?source=setup_org`,
    );
    expect(resolveSetupCompletionHref(null)).toBe(setupCompletionHomeHref());
  });

  it("preserves safe internal dashboard return targets", () => {
    expect(isSafeSetupReturnTo("/dashboard/observe?project=1")).toBe(true);
    expect(resolveSetupCompletionHref("/dashboard/observe?project=1")).toBe(
      "/dashboard/observe?project=1",
    );
  });

  it("rejects external, protocol-relative, and auth return targets", () => {
    expect(isSafeSetupReturnTo("https://example.com/dashboard")).toBe(false);
    expect(isSafeSetupReturnTo("//example.com/dashboard")).toBe(false);
    expect(isSafeSetupReturnTo("/auth/jwt/login")).toBe(false);
    expect(resolveSetupCompletionHref("/auth/jwt/login")).toBe(
      setupCompletionHomeHref(),
    );
  });
});
