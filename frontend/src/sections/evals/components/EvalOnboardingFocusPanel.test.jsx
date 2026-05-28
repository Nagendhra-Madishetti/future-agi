import { describe, expect, it } from "vitest";
import { render, screen } from "src/utils/test-utils";
import EvalOnboardingFocusPanel from "./EvalOnboardingFocusPanel";

describe("EvalOnboardingFocusPanel", () => {
  it("does not render when hidden", () => {
    render(
      <EvalOnboardingFocusPanel
        hidden
        description="Hidden copy"
        title="Hidden title"
      />,
    );

    expect(screen.queryByTestId("eval-onboarding-focus")).toBeNull();
  });

  it("renders the current eval onboarding step", () => {
    render(
      <EvalOnboardingFocusPanel
        currentStep="Scorer"
        description="Save one scorer so this source can be evaluated."
        sourceSummary={{
          description: "The next scorer you save will evaluate this source.",
          label: "Dataset ready",
        }}
        steps={[
          { label: "Source", complete: true },
          { label: "Scorer", complete: false },
          { label: "Run", complete: false },
        ]}
        title="Add the eval scorer"
      />,
    );

    expect(screen.getByText("Eval onboarding")).toBeVisible();
    expect(screen.getByText("Add the eval scorer")).toBeVisible();
    expect(
      screen.getByText("Save one scorer so this source can be evaluated."),
    ).toBeVisible();
    expect(screen.getByText("Dataset ready")).toBeVisible();
    expect(
      screen.getByText("The next scorer you save will evaluate this source."),
    ).toBeVisible();
    expect(screen.getByText("Source")).toBeVisible();
    expect(screen.getAllByText("Scorer").length).toBeGreaterThan(0);
    expect(screen.getByText("Run")).toBeVisible();
  });
});
