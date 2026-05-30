import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { renderWithRouter, screen, waitFor } from "src/utils/test-utils";
import DestinationTourAnchor from "./DestinationTourAnchor";

const originalScrollIntoView = window.HTMLElement.prototype.scrollIntoView;
const scrollIntoView = vi.fn();

describe("DestinationTourAnchor", () => {
  beforeEach(() => {
    scrollIntoView.mockClear();
    window.HTMLElement.prototype.scrollIntoView = scrollIntoView;
  });

  afterAll(() => {
    window.HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
  });

  it("highlights and explains the current destination action", async () => {
    renderWithRouter(
      <>
        <button type="button" data-tour-anchor="gateway_request_button">
          Send test request
        </button>
        <DestinationTourAnchor maxAttempts={1} />
      </>,
      {
        route:
          "/dashboard/gateway?tour_anchor=gateway_request_button&journey_step=run_gateway_request",
      },
    );

    const target = screen.getByRole("button", { name: /send test request/i });
    expect(await screen.findByTestId("destination-tour-anchor")).toBeVisible();
    expect(screen.getByText("Send request")).toBeVisible();
    expect(target).toHaveAttribute("data-onboarding-tour-active", "true");
    expect(scrollIntoView).toHaveBeenCalledWith({
      block: "center",
      behavior: "smooth",
    });

    await userEvent.click(screen.getByRole("button", { name: /got it/i }));

    await waitFor(() =>
      expect(screen.queryByTestId("destination-tour-anchor")).toBeNull(),
    );
    expect(target).not.toHaveAttribute("data-onboarding-tour-active");
  });

  it("stays hidden when no tour anchor is present", () => {
    renderWithRouter(
      <>
        <button type="button" data-tour-anchor="gateway_request_button">
          Send test request
        </button>
        <DestinationTourAnchor maxAttempts={1} />
      </>,
      { route: "/dashboard/gateway" },
    );

    expect(screen.queryByTestId("destination-tour-anchor")).toBeNull();
  });
});
