import { describe, expect, it } from "vitest";
import {
  buildEvalCreateDraftHref,
  buildEvalRouteFocusPayload,
  buildEvalScorerCreatedPayload,
  EVAL_CREATE_ONBOARDING_STEPS,
  evalCreateOnboardingStage,
  getEvalCreateOnboardingCopy,
  getEvalCreateOnboardingParams,
} from "./evalCreateOnboarding";

describe("evalCreateOnboarding", () => {
  it("parses eval create onboarding query params", () => {
    expect(
      getEvalCreateOnboardingParams(
        "?source=onboarding&step=run&source_type=dataset&source_id=data-1&run_id=run-1",
      ),
    ).toEqual({
      isOnboarding: true,
      runId: "run-1",
      sourceId: "data-1",
      sourceType: "dataset",
      step: EVAL_CREATE_ONBOARDING_STEPS.RUN,
    });
  });

  it("preserves onboarding query params when moving to a draft route", () => {
    expect(
      buildEvalCreateDraftHref(
        "eval-1",
        "?source=onboarding&step=scorer&source_type=dataset&source_id=data-1",
      ),
    ).toBe(
      "/dashboard/evaluations/create/eval-1?source=onboarding&step=scorer&source_type=dataset&source_id=data-1",
    );
  });

  it("returns copy and stage for supported steps", () => {
    expect(
      getEvalCreateOnboardingCopy({
        step: EVAL_CREATE_ONBOARDING_STEPS.DATA,
      }),
    ).toMatchObject({
      currentStep: "Source",
      title: "Create the eval source",
    });
    expect(evalCreateOnboardingStage(EVAL_CREATE_ONBOARDING_STEPS.RUN)).toBe(
      "run_eval",
    );
  });

  it("builds a safe route focus payload", () => {
    expect(
      buildEvalRouteFocusPayload({
        draftId: "eval-1",
        sourceId: "data-1",
        sourceType: "dataset",
        step: EVAL_CREATE_ONBOARDING_STEPS.SCORER,
      }),
    ).toMatchObject({
      eventName: "onboarding_eval_route_focus_viewed",
      primaryPath: "evals",
      stage: "add_eval_scorer",
      source: "eval_create_onboarding",
      artifactType: "eval_route",
      artifactId: "data-1",
      metadata: {
        draft_id: "eval-1",
        source_id: "data-1",
        source_type: "dataset",
        step: "scorer",
      },
      idempotencyKey: "onboarding_eval_route_focus_viewed:scorer:data-1",
    });
  });

  it("builds a scorer-created payload without source content", () => {
    expect(
      buildEvalScorerCreatedPayload({
        evalId: "eval-1",
        evalType: "agent",
        sourceId: "data-1",
        sourceType: "dataset",
        step: EVAL_CREATE_ONBOARDING_STEPS.SCORER,
      }),
    ).toMatchObject({
      eventName: "eval_scorer_created",
      primaryPath: "evals",
      stage: "add_eval_scorer",
      source: "eval_create_onboarding",
      artifactType: "eval_scorer",
      artifactId: "eval-1",
      metadata: {
        eval_id: "eval-1",
        eval_type: "agent",
        is_composite: false,
        source_id: "data-1",
        source_type: "dataset",
        step: "scorer",
      },
      idempotencyKey: "eval_scorer_created:data-1:eval-1",
    });
  });
});
