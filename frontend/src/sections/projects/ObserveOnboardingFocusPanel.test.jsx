import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen } from "src/utils/test-utils";
import ObserveOnboardingFocusPanel from "./ObserveOnboardingFocusPanel";

describe("ObserveOnboardingFocusPanel", () => {
  it("does not render when hidden", () => {
    render(
      <ObserveOnboardingFocusPanel
        hidden
        description="Hidden description"
        title="Hidden title"
      />,
    );

    expect(screen.queryByTestId("observe-onboarding-focus")).toBeNull();
  });

  it("renders observe steps and actions", async () => {
    const onPrimary = vi.fn();
    const onSecondary = vi.fn();

    render(
      <ObserveOnboardingFocusPanel
        currentStep="First trace"
        description="Send one trace to unlock review."
        primaryAction={{ label: "Open setup", onClick: onPrimary }}
        secondaryAction={{ label: "Refresh traces", onClick: onSecondary }}
        steps={[
          { label: "Project", complete: true },
          { label: "Trace", complete: false },
          { label: "Review", complete: false },
        ]}
        title="Send the first trace"
        tourAnchor="observe_send_trace_button"
      />,
    );

    expect(screen.getByRole("button", { name: /open setup/i })).toHaveAttribute(
      "data-tour-anchor",
      "observe_send_trace_button",
    );
    expect(screen.getByText("Observe onboarding")).toBeVisible();
    expect(screen.getByText("Send the first trace")).toBeVisible();
    expect(screen.getByText("Project")).toBeVisible();
    expect(screen.getAllByText("First trace").length).toBeGreaterThan(0);
    expect(screen.getByText("Review")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: /open setup/i }));
    await userEvent.click(
      screen.getByRole("button", { name: /refresh traces/i }),
    );

    expect(onSecondary).toHaveBeenCalledTimes(1);
    expect(onPrimary).toHaveBeenCalledTimes(1);
  });
});
