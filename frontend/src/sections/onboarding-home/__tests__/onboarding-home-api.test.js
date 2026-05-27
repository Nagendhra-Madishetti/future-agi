import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("src/utils/axios", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  endpoints: {
    onboarding: {
      activationState: "/accounts/activation-state/",
      goal: "/accounts/onboarding/goal/",
    },
  },
}));

import axios from "src/utils/axios";
import { getActivationStateFixture } from "../fixtures/activation-state.fixtures";
import { useActivationState } from "../hooks/useActivationState";
import {
  fetchActivationState,
  hideSampleProject,
  onboardingHomeQueryKeys,
  OnboardingEndpointUnavailableError,
  openSampleProject,
  saveOnboardingGoal,
} from "../api/onboarding-home-api";

const renderWithQueryClient = (hook) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
      },
    },
  });
  const wrapper = ({ children }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return renderHook(hook, { wrapper });
};

describe("onboarding home API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches activation state from the onboarding endpoint", async () => {
    const fixture = getActivationStateFixture("observeNoSetup");
    axios.get.mockResolvedValueOnce({ data: { result: fixture } });

    const state = await fetchActivationState();

    expect(axios.get).toHaveBeenCalledWith("/accounts/activation-state/", {
      params: {},
    });
    expect(state.stage).toBe("connect_observability");
    expect(state.primaryPath).toBe("observe");
  });

  it("passes email and campaign query params", async () => {
    axios.get.mockResolvedValueOnce({
      data: { result: getActivationStateFixture("staleEmailLink") },
    });

    await fetchActivationState({
      source: "email",
      campaignKey: "observe_waiting",
      emailKey: "observe_waiting_1",
      targetStage: "waiting_for_first_trace",
      targetEvent: "trace_ingested",
      targetRoute: "/dashboard/observe/observe-1",
      linkIssuedAt: "2026-05-26T15:00:00Z",
      mode: "email",
    });

    expect(axios.get).toHaveBeenCalledWith("/accounts/activation-state/", {
      params: {
        source: "email",
        campaign_key: "observe_waiting",
        email_key: "observe_waiting_1",
        target_stage: "waiting_for_first_trace",
        target_event: "trace_ingested",
        target_route: "/dashboard/observe/observe-1",
        link_issued_at: "2026-05-26T15:00:00Z",
        mode: "email",
      },
    });
  });

  it("normalizes direct fixture payloads in tests", async () => {
    axios.get.mockResolvedValueOnce({
      data: getActivationStateFixture("featureDisabled"),
    });

    const state = await fetchActivationState();

    expect(state.stage).toBe("feature_disabled");
    expect(state.fallbackAction.href).toBe("/dashboard/get-started");
  });

  it("saves the onboarding goal through the goal endpoint", async () => {
    axios.post.mockResolvedValueOnce({
      data: { result: getActivationStateFixture("observeNoSetup") },
    });

    const state = await saveOnboardingGoal({
      goal: "monitor_production_ai_app",
      primaryPath: "observability",
      source: "goal_picker",
      campaignKey: "welcome",
      expectedStage: "choose_goal",
      knownGoalId: "goal-1",
    });

    expect(axios.post).toHaveBeenCalledWith("/accounts/onboarding/goal/", {
      goal: "monitor_production_ai_app",
      primary_path: "observe",
      source: "goal_picker",
      campaign_key: "welcome",
      expected_stage: "choose_goal",
      known_goal_id: "goal-1",
    });
    expect(state.stage).toBe("connect_observability");
  });

  it("exposes goal conflict responses to the caller", async () => {
    const conflict = {
      statusCode: 409,
      result: {
        reason: "known_goal_mismatch",
        current_goal_id: "goal-current",
      },
    };
    axios.post.mockRejectedValueOnce(conflict);

    await expect(saveOnboardingGoal({ goal: "improve_prompts" })).rejects.toBe(
      conflict,
    );
  });

  it("returns a renderable feature-disabled state", async () => {
    axios.get.mockResolvedValueOnce({
      data: { result: getActivationStateFixture("featureDisabled") },
    });

    const state = await fetchActivationState();

    expect(state.stage).toBe("feature_disabled");
    expect(state.recommendedAction.href).toBe("/dashboard/get-started");
  });

  it("uses stable activation-state query keys", () => {
    expect(
      onboardingHomeQueryKeys.activationState({
        organizationId: "org-1",
        workspaceId: "wrk-1",
        source: "email",
      }),
    ).toEqual([
      "onboarding-home",
      "activation-state",
      {
        organizationId: "org-1",
        workspaceId: "wrk-1",
        source: "email",
      },
    ]);
  });

  it("lets the hook render a local fallback on hard failures", async () => {
    axios.get.mockRejectedValueOnce({ message: "offline" });

    const { result } = renderWithQueryClient(() =>
      useActivationState({
        organizationId: "org-1",
        workspaceId: "wrk-1",
      }),
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.state.stage).toBe("feature_disabled");
    expect(result.current.state.fallbackAction.href).toBe(
      "/dashboard/get-started",
    );
  });

  it("keeps sample project mutations unavailable until backend endpoints exist", async () => {
    await expect(openSampleProject()).rejects.toBeInstanceOf(
      OnboardingEndpointUnavailableError,
    );
    await expect(hideSampleProject()).rejects.toBeInstanceOf(
      OnboardingEndpointUnavailableError,
    );
  });
});
