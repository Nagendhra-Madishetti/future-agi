export const ACTIVATION_STATE_SCHEMA_VERSION = "activation-state-2026-05-26.v1";

const DEFAULT_PROGRESS = Object.freeze({
  build: "not_started",
  test: "not_started",
  observe: "not_started",
  ship: "not_started",
  improve: "not_started",
});

const PATH_ALIASES = Object.freeze({
  prompts: "prompt",
  workbench: "prompt",
  agents: "agent",
  simulate_agent: "agent",
  observability: "observe",
  traces: "observe",
  model_gateway: "gateway",
  voice_ai: "voice",
  eval: "evals",
  evaluations: "evals",
  dashboard: "dashboards",
  sample_project: "sample",
});

const PRODUCT_PATHS = new Set([
  "prompt",
  "agent",
  "observe",
  "gateway",
  "voice",
  "evals",
  "dashboards",
  "sample",
]);

const ACTIVATION_STAGES = new Set([
  "feature_disabled",
  "workspace_missing",
  "permission_limited",
  "choose_goal",
  "selected_path_unavailable",
  "activated",
  "daily_review",
  "start_prompt",
  "run_prompt_test",
  "save_prompt_version",
  "compare_prompt_versions",
  "prompt_next_loop",
  "create_agent",
  "run_agent_scenario",
  "review_agent_trace",
  "save_agent_eval",
  "agent_create_eval",
  "connect_observability",
  "waiting_for_first_trace",
  "waiting_for_first_trace_sample_available",
  "review_first_trace",
  "create_trace_evaluator",
  "create_trace_dashboard",
  "create_trace_alert",
  "configure_gateway_provider",
  "create_gateway_key",
  "run_gateway_request",
  "review_gateway_log",
  "fix_gateway_failure",
  "add_gateway_policy",
  "create_voice_agent",
  "run_voice_test_call",
  "review_voice_call",
  "add_voice_success_criteria",
  "voice_monitor_calls",
  "create_eval_dataset",
  "add_eval_scorer",
  "run_eval",
  "review_eval_failures",
  "eval_next_loop",
  "open_sample_project",
  "review_sample_signal",
  "connect_real_data",
]);

const isObject = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);

export const normalizeProductPath = (path) => {
  if (path === null || path === undefined || path === "") return null;
  const normalized = PATH_ALIASES[path] || path;
  if (!PRODUCT_PATHS.has(normalized)) {
    throw new Error(`Unsupported onboarding product path: ${path}`);
  }
  return normalized;
};

export const isInternalHref = (href) => {
  if (href === null || href === undefined || href === "") return true;
  if (typeof href !== "string") return false;
  return href.startsWith("/") && !href.startsWith("//");
};

const normalizeAnalytics = (raw = {}) => ({
  eventName: raw.event_name || raw.eventName || null,
  source: raw.source || null,
  targetPath: normalizeProductPath(raw.target_path || raw.targetPath || null),
});

export const normalizeActivationAction = (raw) => {
  if (!raw) return null;
  const href = raw.href ?? null;
  const fallbackHref = raw.fallback_href ?? raw.fallbackHref ?? null;
  if (!isInternalHref(href)) {
    throw new Error(`Onboarding action has external href: ${href}`);
  }
  if (!isInternalHref(fallbackHref)) {
    throw new Error(
      `Onboarding action has external fallback href: ${fallbackHref}`,
    );
  }
  return {
    id: raw.id,
    kind: raw.kind,
    title: raw.title,
    description: raw.description,
    href,
    ctaLabel: raw.cta_label ?? raw.ctaLabel ?? "",
    estimatedMinutes: raw.estimated_minutes ?? raw.estimatedMinutes ?? null,
    priority: raw.priority ?? 0,
    blocked: Boolean(raw.blocked),
    blockedReason: raw.blocked_reason ?? raw.blockedReason ?? null,
    requiresPermission:
      raw.requires_permission ?? raw.requiresPermission ?? null,
    completionEvent: raw.completion_event ?? raw.completionEvent ?? null,
    isSample: Boolean(raw.is_sample ?? raw.isSample),
    routeAvailable: Boolean(raw.route_available ?? raw.routeAvailable),
    fallbackHref,
    analytics: normalizeAnalytics(raw.analytics),
  };
};

const normalizeProgress = (raw = {}) => ({
  ...DEFAULT_PROGRESS,
  ...raw,
});

const normalizeStageCopy = (raw) => {
  if (!raw) return null;
  return {
    eyebrow: raw.eyebrow || "Setup",
    title: raw.title || "Open Get Started",
    description:
      raw.description || "The existing setup checklist is available.",
  };
};

const normalizeSignals = (raw = {}) => ({
  providerKeys: raw.provider_keys ?? raw.providerKeys ?? 0,
  datasets: raw.datasets ?? 0,
  evals: raw.evals ?? 0,
  evalRuns: raw.eval_runs ?? raw.evalRuns ?? 0,
  promptTemplates: raw.prompt_templates ?? raw.promptTemplates ?? 0,
  promptVersions: raw.prompt_versions ?? raw.promptVersions ?? 0,
  promptComparisons: raw.prompt_comparisons ?? raw.promptComparisons ?? 0,
  agents: raw.agents ?? 0,
  agentPrototypeRuns: raw.agent_prototype_runs ?? raw.agentPrototypeRuns ?? 0,
  observeProjects: raw.observe_projects ?? raw.observeProjects ?? 0,
  traces: raw.traces ?? 0,
  traceReviews: raw.trace_reviews ?? raw.traceReviews ?? 0,
  gatewayKeys: raw.gateway_keys ?? raw.gatewayKeys ?? 0,
  gatewayRequests: raw.gateway_requests ?? raw.gatewayRequests ?? 0,
  gatewayPolicies: raw.gateway_policies ?? raw.gatewayPolicies ?? 0,
  voiceAgents: raw.voice_agents ?? raw.voiceAgents ?? 0,
  voiceSimulations: raw.voice_simulations ?? raw.voiceSimulations ?? 0,
  voiceCalls: raw.voice_calls ?? raw.voiceCalls ?? 0,
  voiceReviews: raw.voice_reviews ?? raw.voiceReviews ?? 0,
  teamInvites: raw.team_invites ?? raw.teamInvites ?? 0,
  dashboards: raw.dashboards ?? 0,
  alerts: raw.alerts ?? 0,
  firstTraceId: raw.first_trace_id ?? raw.firstTraceId ?? null,
  firstObserveId: raw.first_observe_id ?? raw.firstObserveId ?? null,
});

const normalizeAvailablePath = (raw) => {
  const href = raw.href || "";
  if (!isInternalHref(href)) {
    throw new Error(`Onboarding path has external href: ${href}`);
  }
  return {
    id: normalizeProductPath(raw.id),
    label: raw.label,
    description: raw.description,
    status: raw.status,
    href,
    isAvailable: Boolean(raw.is_available ?? raw.isAvailable),
    blockedReason: raw.blocked_reason ?? raw.blockedReason ?? null,
    requiresPermission:
      raw.requires_permission ?? raw.requiresPermission ?? null,
    firstActionId: raw.first_action_id ?? raw.firstActionId ?? null,
  };
};

const normalizeAvailableGoal = (raw) => ({
  id: raw.id || raw.goal,
  goal: raw.goal,
  primaryPath: normalizeProductPath(raw.primary_path ?? raw.primaryPath),
  label: raw.label,
  description: raw.description,
  estimatedMinutes: raw.estimated_minutes ?? raw.estimatedMinutes ?? null,
  disabled: Boolean(raw.disabled),
  disabledReason: raw.disabled_reason ?? raw.disabledReason ?? null,
});

const normalizeSampleProject = (raw = {}) => {
  const href = raw.href ?? null;
  if (!isInternalHref(href)) {
    throw new Error(`Sample project has external href: ${href}`);
  }
  const entryRoute = raw.entry_route ?? raw.entryRoute ?? null;
  if (!isInternalHref(entryRoute)) {
    throw new Error(`Sample project has external entry route: ${entryRoute}`);
  }
  const entryRoutes = Array.isArray(raw.entry_routes)
    ? raw.entry_routes
    : raw.entryRoutes || [];
  entryRoutes.forEach((route) => {
    if (!isInternalHref(route)) {
      throw new Error(`Sample project has external entry route: ${route}`);
    }
  });
  const realSetupHref =
    raw.real_setup_href ?? raw.realSetupHref ?? "/dashboard/observe";
  if (!isInternalHref(realSetupHref)) {
    throw new Error(`Sample project has external setup href: ${realSetupHref}`);
  }
  return {
    available: Boolean(raw.available),
    created: Boolean(raw.created),
    status: raw.status || "not_created",
    href,
    version: raw.version ?? null,
    manifestId: raw.manifest_id ?? raw.manifestId ?? null,
    manifestVersion: raw.manifest_version ?? raw.manifestVersion ?? null,
    label: raw.label || "Sample",
    entryRoute,
    isRepairable: Boolean(raw.is_repairable ?? raw.isRepairable),
    blockedReason: raw.blocked_reason ?? raw.blockedReason ?? null,
    artifactRefs: raw.artifact_refs ?? raw.artifactRefs ?? {},
    health: raw.health ?? {},
    realSetupHref,
    isHidden: Boolean(raw.is_hidden ?? raw.isHidden),
    hiddenReason: raw.hidden_reason ?? raw.hiddenReason ?? null,
    entryRoutes,
    missingArtifacts: Array.isArray(raw.missing_artifacts)
      ? raw.missing_artifacts
      : raw.missingArtifacts || [],
    lastOpenedAt: raw.last_opened_at ?? raw.lastOpenedAt ?? null,
  };
};

export const hasSampleRoute = (sampleProject) =>
  Boolean(
    sampleProject &&
      !sampleProject.isHidden &&
      (sampleProject.entryRoute || sampleProject.entryRoutes?.length),
  );

export const isSampleHidden = (sampleProject) =>
  Boolean(sampleProject?.isHidden || sampleProject?.status === "hidden");

export const canOpenSample = (sampleProject) =>
  Boolean(
    sampleProject?.available &&
      !isSampleHidden(sampleProject) &&
      !["unavailable", "repair_failed"].includes(sampleProject.status),
  );

export const shouldShowSampleAsPrimary = (state) =>
  Boolean(
    state?.primaryPath === "sample" ||
      (state?.recommendedAction?.blocked &&
        hasSampleRoute(state.sampleProject)),
  );

const normalizeEmailEligibility = (raw = {}) => ({
  eligible: Boolean(raw.eligible),
  suppressed: Boolean(raw.suppressed),
  suppressionReason: raw.suppression_reason ?? raw.suppressionReason ?? null,
  nextEmailKey: raw.next_email_key ?? raw.nextEmailKey ?? null,
  nextEmailAfter: raw.next_email_after ?? raw.nextEmailAfter ?? null,
  digestEligible: Boolean(raw.digest_eligible ?? raw.digestEligible),
  lastEmailSentAt: raw.last_email_sent_at ?? raw.lastEmailSentAt ?? null,
  frequencyCapRemaining:
    raw.frequency_cap_remaining ?? raw.frequencyCapRemaining ?? 0,
  dryRunOnly: Boolean(raw.dry_run_only ?? raw.dryRunOnly),
});

const normalizePermissions = (raw = {}) => ({
  role: raw.role ?? null,
  canRead: Boolean(raw.can_read ?? raw.canRead),
  canWrite: Boolean(raw.can_write ?? raw.canWrite),
  canManageWorkspace: Boolean(
    raw.can_manage_workspace ?? raw.canManageWorkspace,
  ),
  missingPermissions: Array.isArray(raw.missing_permissions)
    ? raw.missing_permissions
    : raw.missingPermissions || [],
  requestAccessHref: raw.request_access_href ?? raw.requestAccessHref ?? null,
  permissionLimited: Boolean(raw.permission_limited ?? raw.permissionLimited),
});

const normalizeRouteAvailability = (raw = {}) =>
  Object.fromEntries(
    Object.entries(raw).map(([key, value]) => {
      const href = value?.href || "";
      if (!isInternalHref(href)) {
        throw new Error(`Route availability has external href: ${href}`);
      }
      return [
        key,
        {
          href,
          isAvailable: Boolean(value?.is_available ?? value?.isAvailable),
          reason: value?.reason ?? null,
        },
      ];
    }),
  );

const normalizeEmailContext = (raw) => {
  if (!raw) return null;
  return {
    campaignKey: raw.campaign_key ?? raw.campaignKey ?? null,
    emailKey: raw.email_key ?? raw.emailKey ?? null,
    targetStage: raw.target_stage ?? raw.targetStage ?? null,
    targetEvent: raw.target_event ?? raw.targetEvent ?? null,
    targetRoute: raw.target_route ?? raw.targetRoute ?? null,
    contextStatus: raw.context_status ?? raw.contextStatus ?? null,
    staleReason: raw.stale_reason ?? raw.staleReason ?? null,
    resolvedHref: raw.resolved_href ?? raw.resolvedHref ?? null,
  };
};

const normalizeLastMeaningfulEvent = (raw) => {
  if (!raw) return null;
  return {
    name: raw.name,
    occurredAt: raw.occurred_at ?? raw.occurredAt ?? null,
    isSample: Boolean(raw.is_sample ?? raw.isSample),
    path: normalizeProductPath(raw.path),
    metadata: raw.metadata || {},
  };
};

const normalizeDiagnostics = (raw) => {
  if (!raw) return null;
  return {
    resolverVersion: raw.resolver_version ?? raw.resolverVersion ?? null,
    decisionReason: raw.decision_reason ?? raw.decisionReason ?? null,
    matchedRule: raw.matched_rule ?? raw.matchedRule ?? null,
    candidateActions: raw.candidate_actions ?? raw.candidateActions ?? [],
    suppressedActions:
      raw.suppressed_actions?.map((item) => ({
        id: item.id,
        reason: item.reason,
      })) ??
      raw.suppressedActions ??
      [],
    evaluatedAt: raw.evaluated_at ?? raw.evaluatedAt ?? null,
  };
};

const routeHrefs = (routeAvailability) =>
  new Set(Object.values(routeAvailability).map((route) => route.href));

const assertActionRoute = (action, routeAvailability, label) => {
  if (!action) return;
  if (action.routeAvailable && action.href) {
    const hrefs = routeHrefs(routeAvailability);
    if (!hrefs.has(action.href)) {
      throw new Error(`${label} href is missing from route availability`);
    }
  }
  if (action.blocked && !action.blockedReason) {
    throw new Error(`${label} is blocked without a blocked reason`);
  }
};

export const hasOnePrimaryAction = (state) => {
  if (!state?.recommendedAction) return false;
  if (!state?.fallbackAction) return false;
  return (
    state.recommendedAction.id !== state.fallbackAction.id ||
    state.stage === "feature_disabled"
  );
};

export const normalizeActivationState = (raw) => {
  if (!isObject(raw)) {
    throw new Error("Activation state must be an object");
  }
  if (raw.schema_version !== ACTIVATION_STATE_SCHEMA_VERSION) {
    throw new Error("Unsupported activation-state schema version");
  }
  if (!ACTIVATION_STAGES.has(raw.stage)) {
    throw new Error(`Unsupported activation stage: ${raw.stage}`);
  }

  const routeAvailability = normalizeRouteAvailability(raw.route_availability);
  const recommendedAction = normalizeActivationAction(raw.recommended_action);
  const fallbackAction = normalizeActivationAction(raw.fallback_action);
  const primaryPath = normalizeProductPath(raw.primary_path);

  const state = {
    schemaVersion: raw.schema_version,
    requestId: raw.request_id,
    serverTime: raw.server_time,
    workspaceId: raw.workspace_id ?? null,
    organizationId: raw.organization_id ?? null,
    userId: raw.user_id,
    goal: raw.goal ?? null,
    persona: raw.persona ?? null,
    primaryPath,
    stage: raw.stage,
    stageCopy: normalizeStageCopy(raw.stage_copy ?? raw.stageCopy),
    homeMode: raw.home_mode,
    isActivated: Boolean(raw.is_activated),
    activatedAt: raw.activated_at ?? null,
    recommendedAction,
    fallbackAction,
    progress: normalizeProgress(raw.progress),
    signals: normalizeSignals(raw.signals),
    availableGoals: (raw.available_goals || raw.availableGoals || []).map(
      normalizeAvailableGoal,
    ),
    availablePaths: (raw.available_paths || []).map(normalizeAvailablePath),
    sampleProject: normalizeSampleProject(raw.sample_project),
    emailEligibility: normalizeEmailEligibility(raw.email_eligibility),
    permissions: normalizePermissions(raw.permissions),
    featureFlags: raw.feature_flags || {},
    routeAvailability,
    emailContext: normalizeEmailContext(raw.email_context),
    lastMeaningfulEvent: normalizeLastMeaningfulEvent(
      raw.last_meaningful_event,
    ),
    diagnostics: normalizeDiagnostics(raw.diagnostics),
    warnings: raw.warnings || [],
  };

  if (state.stage !== "workspace_missing" && !state.recommendedAction) {
    throw new Error(
      "Renderable activation state requires a recommended action",
    );
  }
  if (!state.fallbackAction) {
    throw new Error("Activation state requires a fallback action");
  }
  if (!hasOnePrimaryAction(state)) {
    throw new Error("Activation state must expose one primary action");
  }

  assertActionRoute(
    state.recommendedAction,
    routeAvailability,
    "Primary action",
  );
  assertActionRoute(state.fallbackAction, routeAvailability, "Fallback action");

  return state;
};

export const validateActivationStateFixture = (state) => {
  normalizeActivationState(state);
  return true;
};

export const makeActivationStateErrorFallback = (error) => {
  const message =
    error?.result?.message ||
    error?.message ||
    error?.detail ||
    "Activation state could not be loaded";
  const getStartedRoute = {
    href: "/dashboard/get-started",
    is_available: true,
    reason: null,
  };
  const action = {
    id: "open_get_started",
    kind: "fallback",
    title: "Open Get Started",
    description: "Use the existing setup checklist.",
    href: "/dashboard/get-started",
    cta_label: "Open Get Started",
    estimated_minutes: null,
    priority: 10,
    blocked: false,
    blocked_reason: null,
    requires_permission: null,
    completion_event: null,
    is_sample: false,
    route_available: true,
    fallback_href: "/dashboard/get-started",
    analytics: {
      event_name: "onboarding_recommended_action_clicked",
      source: "api_error",
      target_path: null,
    },
  };
  return normalizeActivationState({
    schema_version: ACTIVATION_STATE_SCHEMA_VERSION,
    request_id: "local_api_error_fallback",
    server_time: new Date(0).toISOString(),
    workspace_id: null,
    organization_id: null,
    user_id: "unknown",
    goal: null,
    persona: null,
    primary_path: null,
    stage: "feature_disabled",
    home_mode: "fallback",
    is_activated: false,
    activated_at: null,
    recommended_action: action,
    fallback_action: action,
    progress: DEFAULT_PROGRESS,
    signals: {},
    available_paths: [],
    sample_project: {
      available: false,
      created: false,
      status: "unavailable",
      href: null,
      version: null,
      is_hidden: true,
      hidden_reason: "api_error",
      entry_routes: [],
      missing_artifacts: [],
      last_opened_at: null,
    },
    email_eligibility: {
      eligible: false,
      suppressed: true,
      suppression_reason: "feature_disabled",
      next_email_key: null,
      next_email_after: null,
      digest_eligible: false,
      last_email_sent_at: null,
      frequency_cap_remaining: 0,
      dry_run_only: true,
    },
    permissions: {
      role: null,
      can_read: false,
      can_write: false,
      can_manage_workspace: false,
      missing_permissions: [],
      request_access_href: "/dashboard/settings/user-management",
      permission_limited: false,
    },
    feature_flags: {
      onboarding_activation_state_api: false,
    },
    route_availability: {
      get_started: getStartedRoute,
    },
    email_context: null,
    last_meaningful_event: null,
    diagnostics: null,
    warnings: ["activation_state_request_failed", message],
  });
};
