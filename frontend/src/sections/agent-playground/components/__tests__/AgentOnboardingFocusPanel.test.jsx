import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen } from "src/utils/test-utils";
import AgentOnboardingFocusPanel from "../AgentOnboardingFocusPanel";

describe("AgentOnboardingFocusPanel", () => {
  it("does not render when hidden", () => {
    render(
      <AgentOnboardingFocusPanel
        hidden
        description="Hidden description"
        title="Hidden title"
      />,
    );

    expect(screen.queryByTestId("agent-onboarding-focus")).toBeNull();
  });

  it("renders agent setup steps and actions", async () => {
    const onPrimary = vi.fn();
    const onSecondary = vi.fn();

    render(
      <AgentOnboardingFocusPanel
        currentStep="Scenario"
        description="Run one agent scenario and inspect the output."
        primaryAction={{ label: "Run workflow", onClick: onPrimary }}
        secondaryAction={{ label: "Open executions", onClick: onSecondary }}
        steps={[
          { label: "Agent", complete: true },
          { label: "Scenario", complete: false },
          { label: "Review", complete: false },
        ]}
        title="Run the first agent workflow"
        tourAnchor="agent_run_scenario_button"
      />,
    );

    expect(screen.getByText("Agent onboarding")).toBeVisible();
    expect(screen.getByText("Run the first agent workflow")).toBeVisible();
    expect(screen.getByText("Agent")).toBeVisible();
    expect(screen.getAllByText("Scenario").length).toBeGreaterThan(0);
    expect(screen.getByText("Review")).toBeVisible();
    expect(
      screen.getByRole("button", { name: /run workflow/i }),
    ).toHaveAttribute("data-tour-anchor", "agent_run_scenario_button");

    await userEvent.click(
      screen.getByRole("button", { name: /open executions/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /run workflow/i }),
    );

    expect(onSecondary).toHaveBeenCalledTimes(1);
    expect(onPrimary).toHaveBeenCalledTimes(1);
  });

  it("shows a blocker chip when provided", () => {
    render(
      <AgentOnboardingFocusPanel
        blocker="Add one node first"
        currentStep="Scenario"
        description="The agent needs a runnable node before it can execute."
        title="Run the first agent workflow"
      />,
    );

    expect(screen.getByText("Add one node first")).toBeVisible();
  });
});
