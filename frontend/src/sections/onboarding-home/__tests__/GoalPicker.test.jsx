import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen } from "src/utils/test-utils";
import GoalPicker from "../components/GoalPicker";
import { ONBOARDING_GOAL_OPTIONS } from "../onboarding-home.constants";

describe("GoalPicker", () => {
  it("selects a goal and saves the selected option", async () => {
    const onSelectGoal = vi.fn();
    const onSaveGoal = vi.fn();

    render(
      <GoalPicker
        goals={ONBOARDING_GOAL_OPTIONS.slice(0, 2)}
        selectedGoal="monitor_production_ai_app"
        onSelectGoal={onSelectGoal}
        onSaveGoal={onSaveGoal}
        skipHref="/dashboard/observe?setup=true&source=onboarding"
        skipLabel="Start with observe"
      />,
    );

    await userEvent.click(screen.getByLabelText("Test and improve prompts"));
    expect(onSelectGoal).toHaveBeenCalledWith(
      expect.objectContaining({ goal: "test_and_improve_prompts" }),
    );

    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onSaveGoal).toHaveBeenCalledWith(
      expect.objectContaining({ goal: "monitor_production_ai_app" }),
    );
    expect(
      screen.getByRole("link", { name: /start with observe/i }),
    ).toHaveAttribute(
      "href",
      "/dashboard/observe?setup=true&source=onboarding",
    );
  });

  it("blocks disabled goals and explains the reason", async () => {
    const onSelectGoal = vi.fn();

    render(
      <GoalPicker
        goals={[
          {
            ...ONBOARDING_GOAL_OPTIONS[0],
            disabled: true,
            disabledReason: "path unavailable",
          },
        ]}
        selectedGoal=""
        onSelectGoal={onSelectGoal}
        onSaveGoal={vi.fn()}
      />,
    );

    expect(screen.getByText("path unavailable")).toBeVisible();
    expect(screen.getByLabelText("Monitor a production AI app")).toBeDisabled();
    expect(onSelectGoal).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
  });

  it("shows save errors without clearing the selected goal", () => {
    render(
      <GoalPicker
        goals={ONBOARDING_GOAL_OPTIONS.slice(0, 1)}
        selectedGoal="monitor_production_ai_app"
        onSelectGoal={vi.fn()}
        onSaveGoal={vi.fn()}
        error={{ message: "Goal could not be saved" }}
      />,
    );

    expect(screen.getByText("Goal could not be saved")).toBeVisible();
    expect(screen.getByLabelText("Monitor a production AI app")).toBeChecked();
  });
});
