import { describe, expect, it } from "vitest";
import { SETUP_ORG_PRODUCT_LOOP_QUICK_STARTS } from "./setup-org-quick-starts";

describe("setup org product-loop quick starts", () => {
  it("covers each first-run product path with a canonical goal", () => {
    expect(
      SETUP_ORG_PRODUCT_LOOP_QUICK_STARTS.map((option) => [
        option.id,
        option.goal,
        option.goalLabel,
        option.primaryPath,
      ]),
    ).toEqual([
      [
        "sample_preview",
        "explore_sample_data",
        "Explore with sample data",
        "sample",
      ],
      [
        "observe",
        "monitor_production_ai_app",
        "Monitor a production AI app",
        "observe",
      ],
      ["prompt", "improve_prompts", "Test and improve prompts", "prompt"],
      ["agent", "build_ai_agent", "Build or prototype an AI agent", "agent"],
      [
        "gateway",
        "control_model_traffic",
        "Route LLM traffic safely",
        "gateway",
      ],
      [
        "evals",
        "evaluate_quality",
        "Evaluate quality on data or traces",
        "evals",
      ],
      ["voice", "connect_voice_ai_agent", "Connect a voice AI agent", "voice"],
    ]);
  });
});
