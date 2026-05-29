import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "src/utils/test-utils";

const mockGet = vi.fn();
const mockPatch = vi.fn();
const mockPost = vi.fn();

vi.mock("src/utils/axios", () => ({
  default: {
    get: (...args) => mockGet(...args),
    patch: (...args) => mockPatch(...args),
    post: (...args) => mockPost(...args),
  },
  endpoints: {
    settings: {
      notifications: "/accounts/notification-preferences/",
      notificationChannelTest: (id) =>
        `/accounts/notification-channels/${id}/test/`,
    },
  },
}));

vi.mock("notistack", () => ({
  enqueueSnackbar: vi.fn(),
}));

function renderWithQuery(ui) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

const family = (overrides) => ({
  id: "daily_quality_digest",
  label: "Daily quality digest",
  description: "Return-loop summaries for activated workspaces.",
  default_channels: ["email", "in_app"],
  non_critical: true,
  user_controllable: true,
  workspace_controllable: true,
  ...overrides,
});

const decision = ({ family: familyId, channel, allowed, reason = null }) => ({
  family: familyId,
  channel,
  allowed,
  reason,
  source: "default",
  preference_id: null,
});

function settingsResult(overrides = {}) {
  return {
    families: [
      family({ id: "daily_quality_digest" }),
      family({
        id: "usage_budget",
        label: "Usage and budget alerts",
        description: "Budget thresholds, warnings, and blocking usage states.",
        default_channels: ["email", "in_app"],
        non_critical: false,
        user_controllable: false,
        workspace_controllable: true,
      }),
    ],
    channels: [],
    preferences: [],
    decisions: [
      decision({
        family: "daily_quality_digest",
        channel: "email",
        allowed: true,
      }),
      decision({
        family: "daily_quality_digest",
        channel: "in_app",
        allowed: true,
      }),
      decision({
        family: "daily_quality_digest",
        channel: "slack",
        allowed: false,
        reason: "channel_not_enabled",
      }),
      decision({
        family: "usage_budget",
        channel: "email",
        allowed: true,
      }),
      decision({
        family: "usage_budget",
        channel: "in_app",
        allowed: true,
      }),
    ],
    delivery_logs: [],
    can_manage_workspace: true,
    ...overrides,
  };
}

describe("NotificationSettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPatch.mockResolvedValue({ data: { result: settingsResult() } });
    mockPost.mockResolvedValue({ data: { result: {} } });
  });

  it("shows Slack as an opt-in delivery channel after a workspace Slack channel exists", async () => {
    const user = userEvent.setup();
    mockGet.mockResolvedValue({
      data: {
        result: settingsResult({
          channels: [
            {
              id: "slack-channel-1",
              type: "slack_webhook",
              display_name: "Daily quality Slack",
              target_identifier: "Slack webhook",
              is_active: true,
            },
          ],
        }),
      },
    });

    const { default: NotificationSettingsPage } = await import(
      "../NotificationSettingsPage"
    );
    renderWithQuery(<NotificationSettingsPage />);

    const dailyQuality = await screen.findByTestId(
      "notification-family-daily_quality_digest",
    );

    expect(within(dailyQuality).getByText("Slack")).toBeInTheDocument();
    expect(within(dailyQuality).getByText("Opt-in")).toBeInTheDocument();

    await user.click(
      within(dailyQuality).getByRole("checkbox", {
        name: "Daily quality digest Slack",
      }),
    );

    await waitFor(() => expect(mockPatch).toHaveBeenCalledTimes(1));
    expect(mockPatch).toHaveBeenCalledWith(
      "/accounts/notification-preferences/",
      {
        preferences: [
          {
            scope: "user_workspace",
            family: "daily_quality_digest",
            channel: "slack",
            enabled: true,
          },
        ],
      },
    );
  });

  it("uses workspace scope when admins configure operational notification families", async () => {
    const user = userEvent.setup();
    mockGet.mockResolvedValue({
      data: {
        result: settingsResult(),
      },
    });

    const { default: NotificationSettingsPage } = await import(
      "../NotificationSettingsPage"
    );
    renderWithQuery(<NotificationSettingsPage />);

    const usageBudget = await screen.findByTestId(
      "notification-family-usage_budget",
    );

    await user.click(
      within(usageBudget).getByRole("checkbox", {
        name: "Usage and budget alerts Email",
      }),
    );

    await waitFor(() => expect(mockPatch).toHaveBeenCalledTimes(1));
    expect(mockPatch).toHaveBeenCalledWith(
      "/accounts/notification-preferences/",
      {
        preferences: [
          {
            scope: "workspace",
            family: "usage_budget",
            channel: "email",
            enabled: false,
          },
        ],
      },
    );
  });
});
