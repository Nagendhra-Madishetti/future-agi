import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, waitFor } from "src/utils/test-utils";

import ObservePage from "./ObservePage";
import {
  buildObserveTraceReviewHref,
  OBSERVE_FIRST_TRACE_LOADED_EVENT,
} from "./observeOnboardingRoute";

const mocks = vi.hoisted(() => ({
  activationState: null,
  axiosGet: vi.fn(),
  navigate: vi.fn(),
  observeId: "observe-1",
  recordActivationEvent: vi.fn(),
  search: "?source=onboarding&onboarding=send-first-trace&selectedTab=trace",
  setActiveTab: vi.fn(),
}));

vi.mock("react-router", () => ({
  Outlet: () => <div>Trace table</div>,
  useLocation: () => ({
    pathname: `/dashboard/observe/${mocks.observeId}/llm-tracing`,
    search: mocks.search,
  }),
  useNavigate: () => mocks.navigate,
  useParams: () => ({
    observeId: mocks.observeId,
  }),
}));

vi.mock("react-helmet-async", () => ({
  Helmet: ({ children }) => children,
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({
    getQueryData: vi.fn(),
  }),
}));

vi.mock("src/api/project/project-detail", () => ({
  useGetProjectDetails: () => ({
    data: { source: "sdk" },
  }),
}));

vi.mock("src/api/project/saved-views", () => ({
  SAVED_VIEWS_KEY: "saved-views",
  useGetSavedViews: () => ({
    data: { custom_views: [] },
  }),
}));

vi.mock("src/components/observe-tabs", () => ({
  ObserveTabBar: () => <div>Observe tabs</div>,
  TabContextMenu: () => null,
  ViewConfigModal: () => null,
}));

vi.mock("src/routes/hooks/use-url-state", () => ({
  useUrlState: () => ["traces", mocks.setActiveTab],
}));

vi.mock("../project/context/ObserveHeaderContext", () => ({
  useObserveHeader: () => ({
    headerConfig: {
      filterSession: vi.fn(),
      filterSpan: vi.fn(),
      filterTrace: vi.fn(),
      gridApi: null,
      refreshData: vi.fn(),
      resetFilters: vi.fn(),
      selectedTab: "trace",
      text: "Observe",
    },
    setActiveViewConfig: vi.fn(),
  }),
}));

vi.mock("./ObserveHeader", () => ({
  default: () => <div>Observe header</div>,
}));

vi.mock("./ObserveTabs", () => ({
  default: () => <div>Legacy observe tabs</div>,
}));

vi.mock("./ObserveOnboardingFocusPanel", () => ({
  default: ({ title }) => <div data-testid="observe-focus">{title}</div>,
}));

vi.mock("./ReplayDrawer/ReplayDrawer", () => ({
  default: () => null,
}));

vi.mock("./SessionsView/ReplaySessions/store", () => ({
  resetReplaySessionsStore: vi.fn(),
  resetSessionsGridStore: vi.fn(),
}));

vi.mock("./LLMTracing/states", () => ({
  resetTraceGridStore: vi.fn(),
}));

vi.mock("./LLMTracing/tabStore", () => ({
  resetTabStore: vi.fn(),
  useTabStoreShallow: (selector) =>
    selector({
      closeContextMenu: vi.fn(),
      closeCreateModal: vi.fn(),
      contextMenuAnchor: null,
      createModalOpen: false,
      editModalView: null,
      startRenaming: vi.fn(),
    }),
}));

vi.mock("src/utils/axios", () => ({
  default: {
    get: (...args) => mocks.axiosGet(...args),
  },
  endpoints: {
    project: {
      getTracesForObserveProject: () => "/project/traces",
    },
  },
}));

vi.mock("src/sections/onboarding-home/hooks/useRecordActivationEvent", () => ({
  useRecordActivationEvent: () => ({
    data: mocks.activationState,
    mutate: (...args) => mocks.recordActivationEvent(...args),
  }),
}));

vi.mock("src/sections/onboarding-home/api/onboarding-home-api", () => ({
  recordActivationEvent: vi.fn(),
}));

vi.mock("src/sections/evals/components/evalCreateOnboarding", () => ({
  buildEvalRunStepHref: vi.fn(),
  buildEvalSourceFixRerunClickedPayload: vi.fn(),
  buildEvalSourceFixRouteFocusPayload: vi.fn(),
  evalSetupQuickStartAttributionFromSearch: vi.fn(() => ({})),
  EVAL_FIX_RERUN_ORIGINS: {
    SOURCE_FIX: "source_fix",
  },
  getEvalSourceFixOnboardingCopy: () => ({
    description: "Fix eval source",
  }),
  getEvalSourceFixOnboardingParams: () => ({
    isOnboarding: false,
  }),
}));

describe("ObservePage onboarding first-trace handoff", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.activationState = null;
    mocks.observeId = "observe-1";
    mocks.search =
      "?source=onboarding&onboarding=send-first-trace&selectedTab=trace";
    mocks.axiosGet.mockResolvedValue({
      data: {
        result: {
          table: [],
        },
      },
    });
  });

  it("auto-opens trace review when activation state already has the first trace", async () => {
    mocks.activationState = {
      signals: {
        firstObserveId: "observe-1",
        firstTraceId: "trace-1",
      },
    };

    render(<ObservePage />);

    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith(
        buildObserveTraceReviewHref({
          observeId: "observe-1",
          traceId: "trace-1",
        }),
        { replace: true },
      ),
    );
  });

  it("auto-opens trace review when the trace table reports the first trace", async () => {
    render(<ObservePage />);

    act(() => {
      window.dispatchEvent(
        new CustomEvent(OBSERVE_FIRST_TRACE_LOADED_EVENT, {
          detail: {
            projectId: "observe-1",
            traceId: "trace-2",
          },
        }),
      );
    });

    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith(
        buildObserveTraceReviewHref({
          observeId: "observe-1",
          traceId: "trace-2",
        }),
        { replace: true },
      ),
    );
  });

  it("auto-opens trace review when the polling request finds the first trace", async () => {
    mocks.axiosGet.mockResolvedValue({
      data: {
        result: {
          table: [{ trace_id: "trace-polled" }],
        },
      },
    });

    render(<ObservePage />);

    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith(
        buildObserveTraceReviewHref({
          observeId: "observe-1",
          traceId: "trace-polled",
        }),
        { replace: true },
      ),
    );
  });

  it("does not auto-open trace review for another observe project", async () => {
    render(<ObservePage />);

    act(() => {
      window.dispatchEvent(
        new CustomEvent(OBSERVE_FIRST_TRACE_LOADED_EVENT, {
          detail: {
            projectId: "other-observe",
            traceId: "trace-3",
          },
        }),
      );
    });

    await waitFor(() => expect(mocks.recordActivationEvent).toHaveBeenCalled());
    expect(mocks.navigate).not.toHaveBeenCalledWith(
      buildObserveTraceReviewHref({
        observeId: "observe-1",
        traceId: "trace-3",
      }),
      { replace: true },
    );
  });

  it("does not auto-open trace review on normal observe routes", async () => {
    mocks.search = "?selectedTab=trace";
    mocks.activationState = {
      signals: {
        firstObserveId: "observe-1",
        firstTraceId: "trace-4",
      },
    };

    render(<ObservePage />);

    await waitFor(() => expect(mocks.setActiveTab).toHaveBeenCalled());
    expect(mocks.navigate).not.toHaveBeenCalledWith(
      buildObserveTraceReviewHref({
        observeId: "observe-1",
        traceId: "trace-4",
      }),
      { replace: true },
    );
  });
});
