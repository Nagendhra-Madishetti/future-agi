import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen } from "src/utils/test-utils";
import PromptOnboardingFocusPanel from "../PromptOnboardingFocusPanel";

describe("PromptOnboardingFocusPanel", () => {
  it("does not render outside onboarding route context", () => {
    render(<PromptOnboardingFocusPanel currentTab="Playground" />);

    expect(screen.queryByTestId("prompt-onboarding-focus")).toBeNull();
  });

  it("runs the prompt when the run-test mode is already on Playground", async () => {
    const onRunPrompt = vi.fn();

    render(
      <PromptOnboardingFocusPanel
        currentTab="Playground"
        mode="run-test"
        onRunPrompt={onRunPrompt}
        tourAnchor="prompt_run_button"
      />,
    );

    expect(screen.getByText("Run one prompt test")).toBeVisible();
    expect(screen.getByRole("button", { name: /run prompt/i })).toHaveAttribute(
      "data-tour-anchor",
      "prompt_run_button",
    );

    await userEvent.click(screen.getByRole("button", { name: /run prompt/i }));

    expect(onRunPrompt).toHaveBeenCalledTimes(1);
  });

  it("moves the user back to Playground before running a prompt test", async () => {
    const onOpenPlayground = vi.fn();

    render(
      <PromptOnboardingFocusPanel
        currentTab="Metrics"
        mode="run-test"
        onOpenPlayground={onOpenPlayground}
      />,
    );

    expect(screen.getByText("Run one prompt test")).toBeVisible();

    await userEvent.click(
      screen.getByRole("button", { name: /open playground/i }),
    );

    expect(onOpenPlayground).toHaveBeenCalledTimes(1);
  });

  it("opens the save-version action from the save-version mode", async () => {
    const onOpenSaveVersion = vi.fn();

    render(
      <PromptOnboardingFocusPanel
        currentTab="Playground"
        mode="save-version"
        onOpenSaveVersion={onOpenSaveVersion}
      />,
    );

    expect(screen.getByText("Save the prompt baseline")).toBeVisible();

    await userEvent.click(
      screen.getByRole("button", { name: /save version/i }),
    );

    expect(onOpenSaveVersion).toHaveBeenCalledTimes(1);
  });

  it("shows the onboarding source default prompt guidance", () => {
    render(
      <PromptOnboardingFocusPanel
        currentTab="Playground"
        source="onboarding"
      />,
    );

    expect(screen.getByText("Create the first prompt")).toBeVisible();
  });
});
