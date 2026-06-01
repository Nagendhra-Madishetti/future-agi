import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import NodeSelectionPanel from "../NodeSelectionPanel";

const mockAddNode = vi.fn();
const mockSetCenter = vi.fn();
const mockSetSearchParams = vi.fn();
const mockRecordActivationEvent = vi.fn();

vi.mock("../hooks/useAddNodeOptimistic", () => ({
  default: () => ({ addNode: mockAddNode }),
}));

vi.mock("@xyflow/react", () => ({
  useReactFlow: () => ({
    getZoom: () => 1,
    setCenter: mockSetCenter,
  }),
}));

vi.mock("react-router-dom", () => ({
  useSearchParams: () => [
    new URLSearchParams(
      "quick_start_goal=build_ai_agent&quick_start_id=agent&quick_start_primary_path=agent",
    ),
    mockSetSearchParams,
  ],
}));

vi.mock("src/sections/onboarding-home/api/onboarding-home-api", () => ({
  recordActivationEvent: (...args) => mockRecordActivationEvent(...args),
}));

const mockTemplateNodes = [
  {
    id: "llm_prompt",
    node_template_id: "tpl-1",
    title: "LLM Prompt",
    description: "Run a prompt against an LLM",
  },
  {
    id: "eval",
    node_template_id: "tpl-2",
    title: "Eval Node",
    description: "Run an evaluation",
  },
];

vi.mock("src/api/agent-playground/agent-playground", () => ({
  useGetNodeTemplates: () => ({ data: mockTemplateNodes, isLoading: false }),
  useGetReferenceableGraphs: () => ({ data: [] }),
}));

vi.mock("../../store", () => ({
  useAgentPlaygroundStoreShallow: () => ({
    currentAgent: { id: "agent-1", version_id: "version-1" },
    nodes: [],
  }),
}));

vi.mock("../../components/NodeCard", () => ({
  default: ({ node }) => (
    <div data-testid={`node-card-${node.id}`}>{node.title}</div>
  ),
}));

describe("NodeSelectionPanel onboarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAddNode.mockResolvedValue({
      nodeId: "node-1",
      position: { x: 100, y: 200 },
    });
    mockRecordActivationEvent.mockResolvedValue({});
  });

  it("renders add-step guidance and advances to run-scenario after adding a prompt node", async () => {
    render(
      <NodeSelectionPanel
        width="240px"
        onboardingMode="run-scenario"
        tourAnchor="agent_add_node_button"
      />,
    );

    expect(screen.getByTestId("agent-onboarding-focus")).toBeVisible();
    expect(screen.getByText("Add the first agent step")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /add llm prompt/i }));

    await waitFor(() => {
      expect(mockAddNode).toHaveBeenCalledWith({
        type: "llm_prompt",
        position: undefined,
        node_template_id: "tpl-1",
      });
    });
    expect(mockRecordActivationEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        artifactId: "node-1",
        artifactType: "agent_node",
        eventName: "agent_node_added",
        primaryPath: "agent",
        stage: "add_agent_node",
        metadata: {
          agent_id: "agent-1",
          node_id: "node-1",
          version_id: "version-1",
        },
        quick_start_goal: "build_ai_agent",
        quick_start_id: "agent",
        quick_start_primary_path: "agent",
      }),
    );
    expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(Function), {
      replace: true,
    });
    const nextParams = mockSetSearchParams.mock.calls[0][0](
      new URLSearchParams(),
    );
    expect(nextParams.get("journey_step")).toBe("run_agent_scenario");
    expect(nextParams.get("tour_anchor")).toBe("agent_run_scenario_button");
  });

  it("renders eval coverage guidance and adds an eval node from the primary action", async () => {
    render(<NodeSelectionPanel width="240px" onboardingMode="add-eval" />);

    expect(screen.getByTestId("agent-onboarding-focus")).toBeVisible();
    expect(
      screen.getByText("Add coverage from the reviewed run"),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /add eval node/i }));

    await waitFor(() => {
      expect(mockAddNode).toHaveBeenCalledWith({
        type: "eval",
        position: undefined,
        node_template_id: "tpl-2",
      });
    });
    expect(mockSetCenter).toHaveBeenCalledWith(400, 200, {
      duration: 800,
      zoom: 1,
    });
  });

  it("keeps the panel hidden outside eval coverage onboarding", () => {
    render(<NodeSelectionPanel width="240px" />);

    expect(screen.queryByTestId("agent-onboarding-focus")).toBeNull();
  });
});
