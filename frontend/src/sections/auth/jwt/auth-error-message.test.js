import { describe, expect, it } from "vitest";

import { getAuthErrorMessage } from "./auth-error-message";

describe("getAuthErrorMessage", () => {
  it("extracts structured auth block errors as text", () => {
    expect(
      getAuthErrorMessage({
        status: false,
        result: {
          error:
            "IP address temporarily blocked due to multiple failed attempts",
          error_code: "LOGIN_IP_BLOCKED",
          blocked: true,
        },
      }),
    ).toBe("IP address temporarily blocked due to multiple failed attempts");
  });

  it("does not return nested objects to the UI", () => {
    expect(
      getAuthErrorMessage({
        result: {
          blocked: true,
        },
      }),
    ).toBe("Something went wrong. Please try again.");
  });
});
