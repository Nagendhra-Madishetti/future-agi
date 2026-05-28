const DEFAULT_ARTIFACT_ID = "eval-onboarding";

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

export const getEvalCreateOnboardingParams = (search = "") => {
  const params = new URLSearchParams(search);
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
  const query = new URLSearchParams(search).toString();
  return `/dashboard/evaluations/create/${draftId}${query ? `?${query}` : ""}`;
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
