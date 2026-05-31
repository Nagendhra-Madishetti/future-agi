import { describe, expect, it, vi } from "vitest";
import { renderWithRouter, screen, within } from "src/utils/test-utils";

import NewObserve from "./NewObserve";

const mocks = vi.hoisted(() => ({
  useQuery: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (args) => mocks.useQuery(args),
}));

vi.mock("src/utils/axios", () => ({
  default: {
    get: vi.fn(),
  },
  endpoints: {
    project: {
      getCodeBlockTracer: "/project/code-block-tracer",
    },
  },
}));

vi.mock("src/utils/Mixpanel", () => ({
  Events: {
    apikeys: "apikeys",
  },
  handleOnDocsClicked: vi.fn(),
  trackEvent: vi.fn(),
}));

vi.mock("./InstructionCodeCopy", () => ({
  default: ({ ariaLabel, language, text }) => (
    <pre
      aria-label={ariaLabel}
      data-language={language}
      data-testid="code-copy"
    >
      {text}
    </pre>
  ),
}));

vi.mock("./ObserveInstuments", () => ({
  default: () => <div>Instrumentation options</div>,
}));

const codeBlockFixture = {
  installationGuide: {
    Python: "pip install futureagi",
    TypeScript: "npm install @futureagi/tracer",
  },
  keys: {
    Python: "export FUTUREAGI_API_KEY=test",
    TypeScript: "process.env.FUTUREAGI_API_KEY = 'test'",
  },
  projectAddCode: {
    Python: "from futureagi import trace",
    TypeScript: "import { trace } from '@futureagi/tracer'",
  },
  instruments: [],
};

describe("NewObserve onboarding setup", () => {
  it("renders a compact first-trace guide before the full setup reference", () => {
    mocks.useQuery.mockReturnValue({
      data: codeBlockFixture,
      error: null,
      isLoading: false,
      isSuccess: true,
    });

    renderWithRouter(
      <NewObserve
        showFirstTraceGuide
        setupVerification={{
          description:
            "Keep this page open after running your app. We check every few seconds and move you forward when data arrives.",
          status: "waiting",
          title: "Checking for your first trace",
        }}
      />,
      { route: "/dashboard/observe?setup=true&source=onboarding" },
    );

    const guide = screen.getByTestId("observe-first-trace-guide");
    expect(guide).toBeVisible();
    expect(within(guide).getByText("Fastest path to Aha")).toBeVisible();
    expect(
      within(guide).getByText("Send one trace, then review it"),
    ).toBeVisible();
    expect(within(guide).getByText("Install")).toBeVisible();
    expect(within(guide).getByText("Instrument")).toBeVisible();
    expect(within(guide).getByText("Run")).toBeVisible();
    expect(within(guide).getByText("pip install futureagi")).toBeVisible();
    expect(
      within(guide).getByText("export FUTUREAGI_API_KEY=test"),
    ).toBeVisible();
    expect(
      within(guide).getByText(
        "Use a real API key and secret key before running the snippet.",
      ),
    ).toBeVisible();
    const apiKeysLink = within(guide).getByRole("link", {
      name: /Create API key/i,
    });
    expect(apiKeysLink).toBeVisible();
    expect(apiKeysLink).toHaveAttribute(
      "href",
      "/dashboard/settings/api_keys?source=onboarding&target=observe_first_trace&action=create&key_name=Observe+first+trace&return_to=%2Fdashboard%2Fobserve%3Fsetup%3Dtrue%26source%3Donboarding%26credential_step%3Ddone",
    );
    expect(
      within(guide).getByText("from futureagi import trace"),
    ).toBeVisible();
    expect(within(guide).getByLabelText("Copy install command")).toBeVisible();
    expect(within(guide).getByLabelText("Copy project keys")).toBeVisible();
    expect(within(guide).getByLabelText("Copy tracing setup")).toBeVisible();
    expect(
      within(guide).getByTestId("observe-setup-verification"),
    ).toHaveTextContent("Checking for your first trace");
    expect(screen.getByText("Full setup reference")).toBeVisible();
    expect(screen.getByText("Instrumentation options")).toBeVisible();
  });

  it("acknowledges copied credentials after returning from key creation", () => {
    mocks.useQuery.mockReturnValue({
      data: codeBlockFixture,
      error: null,
      isLoading: false,
      isSuccess: true,
    });

    renderWithRouter(
      <NewObserve
        showFirstTraceGuide
        setupVerification={{
          description: "Run one request after pasting the keys.",
          status: "waiting",
          title: "Checking for your first trace",
        }}
      />,
      {
        route:
          "/dashboard/observe?setup=true&source=onboarding&credential_step=done",
      },
    );

    const guide = screen.getByTestId("observe-first-trace-guide");
    expect(
      within(guide).getByText(
        "Credentials copied. Paste both values into the snippet, then run one request.",
      ),
    ).toBeVisible();
    expect(
      within(guide).getByRole("link", { name: /Create another key/i }),
    ).toBeVisible();
  });
});
