import { describe, expect, it } from "vitest";
import {
  buildEvalCreateDraftHref,
  buildEvalFailuresReviewedPayload,
  buildEvalReviewDetailHref,
  buildEvalReviewRouteFocusPayload,
  buildEvalRouteFocusPayload,
  buildEvalRunCompletedPayload,
  buildEvalScorerCreatedPayload,
  EVAL_CREATE_ONBOARDING_STEPS,
  evalCreateOnboardingStage,
  getEvalCreateOnboardingCopy,
  getEvalCreateOnboardingParams,
  getEvalReviewOnboardingCopy,
  getEvalReviewOnboardingParams,
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

  it("builds a run-completed payload without result content", () => {
    const payload = buildEvalRunCompletedPayload({
      evalId: "eval-1",
      evalType: "agent",
      mode: "single",
      result: {
        log_id: "log-1",
        output: "Failed",
        reason: "Do not include result content",
      },
      sourceId: "data-1",
      sourceType: "dataset",
    });

    expect(payload).toMatchObject({
      eventName: "eval_run_completed",
      primaryPath: "evals",
      stage: "run_eval",
      source: "eval_create_onboarding",
      artifactType: "eval_run",
      artifactId: "log-1",
      metadata: {
        eval_id: "eval-1",
        eval_type: "agent",
        is_composite: false,
        log_id: "log-1",
        mode: "single",
        run_id: "log-1",
        source_id: "data-1",
        source_type: "dataset",
        status: "completed",
        step: "run",
      },
      idempotencyKey: "eval_run_completed:data-1:eval-1:log-1",
    });
    expect(payload.metadata).not.toHaveProperty("output");
    expect(payload.metadata).not.toHaveProperty("reason");
  });

  it("parses eval review onboarding query params", () => {
    expect(
      getEvalReviewOnboardingParams(
        "?tab=usage&source=onboarding&step=review&run_id=run-1",
      ),
    ).toEqual({
      isOnboarding: true,
      runId: "run-1",
      step: "review",
      tab: "usage",
    });
  });

  it("returns review copy for the review route focus panel", () => {
    expect(getEvalReviewOnboardingCopy()).toMatchObject({
      currentStep: "Review",
      title: "Review the eval result",
      steps: [
        { label: "Source", complete: true },
        { label: "Scorer", complete: true },
        { label: "Run", complete: true },
        { label: "Review", complete: false },
      ],
    });
  });

  it("preserves review onboarding params when moving from usage list to detail", () => {
    expect(
      buildEvalReviewDetailHref(
        "eval-1",
        "?tab=usage&source=onboarding&step=review&run_id=run-1",
      ),
    ).toBe(
      "/dashboard/evaluations/eval-1?tab=usage&source=onboarding&step=review&run_id=run-1",
    );

    expect(buildEvalReviewDetailHref("eval-1", "?tab=usage")).toBe(
      "/dashboard/evaluations/eval-1",
    );
  });

  it("builds a review route focus payload", () => {
    expect(
      buildEvalReviewRouteFocusPayload({
        evalId: "eval-1",
        route: "eval_detail",
        runId: "run-1",
      }),
    ).toMatchObject({
      eventName: "onboarding_eval_route_focus_viewed",
      primaryPath: "evals",
      stage: "review_eval_failures",
      source: "eval_review_onboarding",
      artifactType: "eval_review_route",
      artifactId: "run-1",
      metadata: {
        eval_id: "eval-1",
        route: "eval_detail",
        run_id: "run-1",
        step: "review",
        tab: "usage",
      },
      idempotencyKey: "onboarding_eval_route_focus_viewed:review:run-1",
    });
  });

  it("builds an eval failures reviewed payload without captured content", () => {
    expect(
      buildEvalFailuresReviewedPayload({
        evalId: "eval-1",
        runId: "run-1",
      }),
    ).toMatchObject({
      eventName: "eval_failures_reviewed",
      primaryPath: "evals",
      stage: "review_eval_failures",
      source: "eval_review_onboarding",
      artifactType: "eval_run",
      artifactId: "run-1",
      metadata: {
        eval_id: "eval-1",
        run_id: "run-1",
        step: "review",
        tab: "usage",
      },
      idempotencyKey: "eval_failures_reviewed:run-1:eval-1",
    });
  });
});
