export const PROMPT_ONBOARDING_MODES = {
  CREATE_PROMPT: "create-prompt",
  RUN_TEST: "run-test",
  SAVE_VERSION: "save-version",
  COMPARE: "compare",
  ADD_FAILURE: "add-failure",
  METRICS: "metrics",
};

const VALID_PROMPT_ONBOARDING_MODES = new Set(
  Object.values(PROMPT_ONBOARDING_MODES),
);

const toSearchParams = (search = "") =>
  search instanceof URLSearchParams
    ? new URLSearchParams(search)
    : new URLSearchParams(search);

const safeKeyPart = (value, fallback) =>
  String(value || fallback)
    .replace(/[^a-zA-Z0-9_-]/g, "-")
    .slice(0, 56);

export const getPromptOnboardingRouteParams = (search = "") => {
  const params = toSearchParams(search);
  const mode = params.get("onboarding");

  return {
    action: params.get("action"),
    isOnboarding: params.get("source") === "onboarding",
    mode: VALID_PROMPT_ONBOARDING_MODES.has(mode) ? mode : null,
  };
};

export const buildPromptEditorHref = ({ mode, promptId } = {}) => {
  if (!promptId) return null;

  const params = new URLSearchParams();
  params.set("source", "onboarding");
  if (VALID_PROMPT_ONBOARDING_MODES.has(mode)) {
    params.set("onboarding", mode);
  }

  return `/dashboard/workbench/create/${promptId}?${params.toString()}`;
};

export const buildPromptCreatedHref = ({ promptId, search } = {}) => {
  if (!promptId) return "/dashboard/workbench/all";

  const { action, isOnboarding, mode } = getPromptOnboardingRouteParams(search);
  if (!isOnboarding && !mode) {
    return `/dashboard/workbench/create/${promptId}`;
  }

  const nextMode =
    action === PROMPT_ONBOARDING_MODES.CREATE_PROMPT ||
    mode === PROMPT_ONBOARDING_MODES.CREATE_PROMPT ||
    isOnboarding
      ? PROMPT_ONBOARDING_MODES.RUN_TEST
      : mode;

  return buildPromptEditorHref({ promptId, mode: nextMode });
};

export const shouldAdvancePromptRunOnboarding = ({
  isContentEmpty,
  isGenerating,
  loadingPrompt,
  mode,
  source,
} = {}) =>
  source === "onboarding" &&
  mode === PROMPT_ONBOARDING_MODES.RUN_TEST &&
  !loadingPrompt &&
  !isGenerating &&
  !isContentEmpty;

export const shouldAdvancePromptSaveOnboarding = ({ mode, source } = {}) =>
  source === "onboarding" && mode === PROMPT_ONBOARDING_MODES.SAVE_VERSION;

export const shouldAdvancePromptCompareOnboarding = ({
  mode,
  selectedVersionCount,
  source,
} = {}) =>
  source === "onboarding" &&
  mode === PROMPT_ONBOARDING_MODES.COMPARE &&
  selectedVersionCount > 1;

export const isPromptFailureCaptureOnboarding = ({ mode, source } = {}) =>
  source === "onboarding" && mode === PROMPT_ONBOARDING_MODES.ADD_FAILURE;

export const buildPromptComparisonCompletedPayload = ({
  promptId,
  versions = [],
} = {}) => {
  const safePromptId = safeKeyPart(promptId, "prompt");
  const safeVersions = versions.map((version, index) =>
    safeKeyPart(version, `version-${index + 1}`),
  );

  return {
    eventName: "prompt_comparison_completed",
    primaryPath: "prompt",
    stage: "compare_prompt_versions",
    source: "prompt_template",
    metadata: {
      step: PROMPT_ONBOARDING_MODES.COMPARE,
      template_id: promptId,
      version_count: versions.length,
    },
    idempotencyKey: [
      "prompt_onboarding",
      "prompt_comparison_completed",
      safePromptId,
      safeVersions.join("-"),
    ]
      .filter(Boolean)
      .join(":"),
  };
};
