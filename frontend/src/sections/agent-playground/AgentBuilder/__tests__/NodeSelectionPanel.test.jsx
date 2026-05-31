import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import NodeSelectionPanel from "../NodeSelectionPanel";

const mockAddNode = vi.fn();
const mockSetCenter = vi.fn();

vi.mock("../hooks/useAddNodeOptimistic", () => ({
  default: () => ({ addNode: mockAddNode }),
}));

vi.mock("@xyflow/react", () => ({
  useReactFlow: () => ({
    getZoom: () => 1,
    setCenter: mockSetCenter,
  }),
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
  useAgentPlaygroundStoreShallow: () => ({ currentAgent: { id: "agent-1" } }),
}));

vi.mock("../../components/NodeCard", () => ({
  default: ({ node }) => (
    <div data-testid={`node-card-${node.id}`}>{node.title}</div>
  ),
}));

describe("NodeSelectionPanel onboarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAddNode.mockResolvedValue({ position: { x: 100, y: 200 } });
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
