import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "src/utils/test-utils";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock("src/utils/axios", () => ({
  default: {
    get: (...args) => mockGet(...args),
    post: (...args) => mockPost(...args),
    put: (...args) => mockPut(...args),
    delete: (...args) => mockDelete(...args),
  },
  endpoints: {
    settings: {
      v2: {
        budgets: "/usage/v2/budgets/",
        budgetDetail: (id) => `/usage/v2/budgets/${id}/`,
      },
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

describe("BudgetManager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPost.mockResolvedValue({ data: { result: {} } });
    mockPut.mockResolvedValue({ data: { result: {} } });
    mockDelete.mockResolvedValue({ data: { result: {} } });
  });

  it("renders staged threshold state for existing budgets", async () => {
    mockGet.mockResolvedValue({
      data: {
        result: {
          budgets: [
            {
              id: 7,
              name: "AI Credits cap",
              scope: "ai_credits",
              threshold_value: "5000",
              action: "warn",
              notify_emails: ["ops@example.com"],
              thresholds: [
                { percent: 50, enabled: true, severity: "info" },
                { percent: 80, enabled: false, severity: "warning" },
                { percent: 100, enabled: true, severity: "critical" },
              ],
            },
          ],
        },
      },
    });

    const { default: BudgetManager } = await import("../BudgetManager");
    renderWithQuery(<BudgetManager />);

    expect(await screen.findByText("AI Credits cap")).toBeInTheDocument();
    expect(screen.getByText("50% Early warning")).toBeInTheDocument();
    expect(screen.getByText("80% Off")).toBeInTheDocument();
    expect(screen.getByText("100% Limit reached")).toBeInTheDocument();
  });

  it("submits threshold stages and recipient emails when creating a budget", async () => {
    const user = userEvent.setup();
    mockGet.mockResolvedValue({ data: { result: { budgets: [] } } });

    const { default: BudgetManager } = await import("../BudgetManager");
    renderWithQuery(<BudgetManager />);

    await screen.findByText(/No budgets set/i);

    await user.click(screen.getByRole("button", { name: /add budget/i }));
    await user.type(
      screen.getByLabelText(/budget name/i),
      "AI Credits guardrail",
    );
    await user.type(screen.getByLabelText(/^threshold$/i), "5000");
    await user.type(
      screen.getByLabelText(/notification emails/i),
      "ops@example.com, finance@example.com",
    );
    await user.click(screen.getByLabelText("Alert at 80%"));
    await user.click(screen.getByRole("button", { name: /create budget/i }));

    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
    expect(mockPost).toHaveBeenCalledWith("/usage/v2/budgets/", {
      name: "AI Credits guardrail",
      scope: "ai_credits",
      threshold_value: "5000",
      action: "notify",
      notify_emails: ["ops@example.com", "finance@example.com"],
      thresholds: [
        { percent: 50, enabled: true, severity: "info" },
        { percent: 80, enabled: false, severity: "warning" },
        { percent: 100, enabled: true, severity: "critical" },
      ],
    });
  });
});
