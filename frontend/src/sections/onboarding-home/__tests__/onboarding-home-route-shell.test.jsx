import { describe, expect, it, vi } from "vitest";
import { paths } from "src/routes/paths";
import { dashboardRoutes } from "src/routes/sections/dashboard";

vi.mock("src/utils/Mixpanel", () => ({
  Events: {},
  getPageViewEvent: vi.fn(),
  trackEvent: vi.fn(),
}));

vi.mock("src/utils/analytics/currentFlow", () => ({
  buildCurrentFlowContext: vi.fn(() => ({})),
  CurrentFlowEvents: {},
  isProductRoute: vi.fn(() => false),
  trackCurrentFlow: vi.fn(),
}));

const dashboardChildren = () => dashboardRoutes(null, null)[0].children;

describe("onboarding home route shell", () => {
  it("exposes a stable dashboard home path constant", () => {
    expect(paths.dashboard.home).toBe("/dashboard/home");
  });

  it("registers the authenticated dashboard home child route", () => {
    const homeRoute = dashboardChildren().find(
      (route) => route.path === "home",
    );

    expect(homeRoute).toBeTruthy();
    expect(homeRoute.element).toBeTruthy();
  });

  it("routes the dashboard index to the first-run home and keeps Get Started available", () => {
    const children = dashboardChildren();
    const indexRoute = children.find((route) => route.index);
    const getStartedRoute = children.find(
      (route) => route.path === "/dashboard/get-started",
    );

    expect(indexRoute.element.props.to).toBe(paths.dashboard.home);
    expect(getStartedRoute.children[0].index).toBe(true);
    expect(paths.dashboard.getstarted).toBe("/dashboard/get-started");
  });
});
