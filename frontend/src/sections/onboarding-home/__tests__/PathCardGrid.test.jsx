import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen } from "src/utils/test-utils";
import { getActivationStateFixture } from "../fixtures/activation-state.fixtures";
import { normalizeActivationState } from "../activation-state-utils";
import PathCardGrid from "../components/PathCardGrid";

const pathsFixture = () =>
  normalizeActivationState(getActivationStateFixture("observeNoSetup"))
    .availablePaths;

describe("PathCardGrid", () => {
  it("renders path options and tracks available path clicks", async () => {
    const onPathClick = vi.fn();
    render(<PathCardGrid paths={pathsFixture()} onPathClick={onPathClick} />);

    expect(screen.getByText("Connect your agent")).toBeVisible();
    expect(screen.getByRole("button", { name: /current/i })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /focus/i }));

    expect(onPathClick).toHaveBeenCalledWith(
      expect.objectContaining({ id: "sample" }),
    );
  });

  it("disables unavailable paths", () => {
    render(
      <PathCardGrid
        paths={[
          {
            ...pathsFixture()[1],
            isAvailable: false,
            blockedReason: "route_not_implemented",
          },
        ]}
      />,
    );

    expect(screen.getByText("route not implemented")).toBeVisible();
    expect(screen.getByRole("button", { name: /unavailable/i })).toBeDisabled();
  });
});
