const DEFAULT_ARTIFACT_ID = "eval-onboarding";
const EVAL_REVIEW_ARTIFACT_ID = "eval-review";
const EVAL_REVIEW_STEP = "review";
const EVAL_REVIEW_STAGE = "review_eval_failures";

export const EVAL_CREATE_ONBOARDING_STEPS = {
  DATA: "data",
  SCORER: "scorer",
  RUN: "run",
};

const STEP_TO_STAGE = {
  [EVAL_CREATE_ONBOARDING_STEPS.DATA]: "create_eval_dataset",
  [EVAL_CREATE_ONBOARDING_STEPS.SCORER]: "add_eval_scorer",
  [EVAL_CREATE_ONBOARDING_STEPS.RUN]: "run_eval",
};

const STEP_COPY = {
  [EVAL_CREATE_ONBOARDING_STEPS.DATA]: {
    currentStep: "Source",
    description: "Choose the data or trace source before adding the scorer.",
    title: "Create the eval source",
    steps: [
      { label: "Source", complete: false },
      { label: "Scorer", complete: false },
      { label: "Run", complete: false },
    ],
  },
  [EVAL_CREATE_ONBOARDING_STEPS.SCORER]: {
    currentStep: "Scorer",
    description: "Save one scorer so FutureAGI can evaluate this source.",
    title: "Add the eval scorer",
    steps: [
      { label: "Source", complete: true },
      { label: "Scorer", complete: false },
      { label: "Run", complete: false },
    ],
  },
  [EVAL_CREATE_ONBOARDING_STEPS.RUN]: {
    currentStep: "Run",
    description: "Run the scorer once so the first eval result is reviewable.",
    title: "Run the first eval",
    steps: [
      { label: "Source", complete: true },
      { label: "Scorer", complete: true },
      { label: "Run", complete: false },
    ],
  },
};

const EVAL_REVIEW_COPY = {
  currentStep: "Review",
  description: "Inspect failures or summary before deciding what to fix next.",
  title: "Review the eval result",
  steps: [
    { label: "Source", complete: true },
    { label: "Scorer", complete: true },
    { label: "Run", complete: true },
    { label: "Review", complete: false },
  ],
};

const validSteps = new Set(Object.values(EVAL_CREATE_ONBOARDING_STEPS));

const compactMetadata = (metadata = {}) =>
  Object.fromEntries(
    Object.entries(metadata).filter(
      ([, value]) => value !== undefined && value !== null && value !== "",
    ),
  );

const safeKeyPart = (value, fallback) =>
  String(value || fallback)
    .replace(/[^a-zA-Z0-9_-]/g, "-")
    .slice(0, 56);

const toSearchParams = (search = "") =>
  search instanceof URLSearchParams
    ? new URLSearchParams(search)
    : new URLSearchParams(search);

export const getEvalCreateOnboardingParams = (search = "") => {
  const params = toSearchParams(search);
  const rawStep = params.get("step");
  const step = validSteps.has(rawStep)
    ? rawStep
    : EVAL_CREATE_ONBOARDING_STEPS.SCORER;

  return {
    isOnboarding: params.get("source") === "onboarding",
    runId: params.get("run_id"),
    sourceId: params.get("source_id"),
    sourceType: params.get("source_type"),
    step,
  };
};

export const getEvalCreateOnboardingCopy = ({ step } = {}) =>
  STEP_COPY[step] || STEP_COPY[EVAL_CREATE_ONBOARDING_STEPS.SCORER];

export const buildEvalCreateDraftHref = (draftId, search = "") => {
  const query = toSearchParams(search).toString();
  return `/dashboard/evaluations/create/${draftId}${query ? `?${query}` : ""}`;
};

export const getEvalReviewOnboardingParams = (search = "") => {
  const params = toSearchParams(search);
  const step = params.get("step");
  const tab = params.get("tab") || "usage";

  return {
    isOnboarding:
      params.get("source") === "onboarding" && step === EVAL_REVIEW_STEP,
    runId: params.get("run_id"),
    step,
    tab,
  };
};

export const getEvalReviewOnboardingCopy = () => EVAL_REVIEW_COPY;

export const buildEvalReviewDetailHref = (evalId, search = "") => {
  const reviewParams = getEvalReviewOnboardingParams(search);
  const basePath = `/dashboard/evaluations/${evalId}`;

  if (!reviewParams.isOnboarding) return basePath;

  const params = new URLSearchParams();
  params.set("tab", "usage");
  params.set("source", "onboarding");
  params.set("step", EVAL_REVIEW_STEP);
  if (reviewParams.runId) params.set("run_id", reviewParams.runId);

  return `${basePath}?${params.toString()}`;
};

export const evalCreateOnboardingStage = (step) =>
  STEP_TO_STAGE[step] || STEP_TO_STAGE[EVAL_CREATE_ONBOARDING_STEPS.SCORER];

export const buildEvalRouteFocusPayload = ({
  draftId,
  runId,
  sourceId,
  sourceType,
  step,
} = {}) => {
  const normalizedStep = validSteps.has(step)
    ? step
    : EVAL_CREATE_ONBOARDING_STEPS.SCORER;
  const artifactId = safeKeyPart(
    sourceId || draftId || normalizedStep,
    DEFAULT_ARTIFACT_ID,
  );

  return {
    eventName: "onboarding_eval_route_focus_viewed",
    primaryPath: "evals",
    stage: evalCreateOnboardingStage(normalizedStep),
    source: "eval_create_onboarding",
    artifactType: "eval_route",
    artifactId,
    metadata: compactMetadata({
      draft_id: draftId,
      run_id: runId,
      source_id: sourceId,
      source_type: sourceType,
      step: normalizedStep,
    }),
    idempotencyKey: [
      "onboarding_eval_route_focus_viewed",
      safeKeyPart(normalizedStep, "step"),
      artifactId,
    ].join(":"),
    isSample: false,
  };
};

export const buildEvalScorerCreatedPayload = ({
  evalId,
  evalType,
  isComposite = false,
  sourceId,
  sourceType,
  step,
} = {}) => {
  const artifactId = safeKeyPart(evalId || sourceId, "eval-scorer");

  return {
    eventName: "eval_scorer_created",
    primaryPath: "evals",
    stage: "add_eval_scorer",
    source: "eval_create_onboarding",
    artifactType: "eval_scorer",
    artifactId,
    metadata: compactMetadata({
      eval_id: evalId,
      eval_type: evalType,
      is_composite: Boolean(isComposite),
      source_id: sourceId,
      source_type: sourceType,
      step,
    }),
    idempotencyKey: [
      "eval_scorer_created",
      safeKeyPart(sourceId, "no-source"),
      artifactId,
    ].join(":"),
    isSample: false,
  };
};

export const buildEvalReviewRouteFocusPayload = ({
  evalId,
  route = "eval_detail",
  runId,
} = {}) => {
  const artifactId = safeKeyPart(runId || evalId, EVAL_REVIEW_ARTIFACT_ID);

  return {
    eventName: "onboarding_eval_route_focus_viewed",
    primaryPath: "evals",
    stage: EVAL_REVIEW_STAGE,
    source: "eval_review_onboarding",
    artifactType: "eval_review_route",
    artifactId,
    metadata: compactMetadata({
      eval_id: evalId,
      route,
      run_id: runId,
      step: EVAL_REVIEW_STEP,
      tab: "usage",
    }),
    idempotencyKey: [
      "onboarding_eval_route_focus_viewed",
      EVAL_REVIEW_STEP,
      artifactId,
    ].join(":"),
    isSample: false,
  };
};

export const buildEvalFailuresReviewedPayload = ({ evalId, runId } = {}) => {
  const artifactId = safeKeyPart(runId || evalId, EVAL_REVIEW_ARTIFACT_ID);

  return {
    eventName: "eval_failures_reviewed",
    primaryPath: "evals",
    stage: EVAL_REVIEW_STAGE,
    source: "eval_review_onboarding",
    artifactType: "eval_run",
    artifactId,
    metadata: compactMetadata({
      eval_id: evalId,
      run_id: runId,
      step: EVAL_REVIEW_STEP,
      tab: "usage",
    }),
    idempotencyKey: [
      "eval_failures_reviewed",
      safeKeyPart(runId, "no-run"),
      safeKeyPart(evalId, "no-eval"),
    ].join(":"),
    isSample: false,
  };
};
