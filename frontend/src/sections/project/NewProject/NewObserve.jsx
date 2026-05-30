import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  LinearProgress,
  Stack,
  Typography,
  useTheme,
} from "@mui/material";
import PropTypes from "prop-types";
import React, { useMemo, useState } from "react";
import { Events, handleOnDocsClicked, trackEvent } from "src/utils/Mixpanel";
import { useQuery } from "@tanstack/react-query";
import axios, { endpoints } from "src/utils/axios";

import InstructionTitle from "./InstructionTitle";
import InstructionCodeCopy from "./InstructionCodeCopy";
import ObserveInstruments from "./ObserveInstuments";
import {
  CustomTab,
  CustomTabs,
  TabWrapper,
} from "src/sections/develop/AddDatasetDrawer/AddDatasetStyle";

const CODE_SECTION_ALIASES = {
  installationGuide: "installation_guide",
  projectAddCode: "project_add_code",
};

const FIRST_TRACE_STEPS = [
  {
    id: "install",
    label: "Install",
    description: "Add the tracing package to the app you want to inspect.",
  },
  {
    id: "instrument",
    label: "Instrument",
    description: "Load the project keys before your app handles a request.",
  },
  {
    id: "run",
    label: "Run",
    description: "Trigger one real or test request and keep this page open.",
  },
];

const VerificationAlert = ({ setupVerification }) => {
  if (!setupVerification) return null;

  return (
    <Alert
      data-testid="observe-setup-verification"
      severity={setupVerification.status === "ready" ? "success" : "info"}
      icon={
        setupVerification.status === "waiting" ? (
          <CircularProgress size={18} />
        ) : undefined
      }
      action={
        setupVerification.primaryAction ? (
          <Button
            color="inherit"
            size="small"
            onClick={setupVerification.primaryAction.onClick}
            disabled={setupVerification.primaryAction.disabled}
          >
            {setupVerification.primaryAction.label}
          </Button>
        ) : null
      }
      sx={{ alignItems: "center" }}
    >
      <Stack spacing={0.25}>
        <Typography variant="subtitle2">{setupVerification.title}</Typography>
        <Typography variant="body2">{setupVerification.description}</Typography>
      </Stack>
    </Alert>
  );
};

VerificationAlert.propTypes = {
  setupVerification: PropTypes.shape({
    description: PropTypes.string.isRequired,
    primaryAction: PropTypes.shape({
      disabled: PropTypes.bool,
      label: PropTypes.string.isRequired,
      onClick: PropTypes.func.isRequired,
    }),
    status: PropTypes.oneOf(["ready", "waiting"]).isRequired,
    title: PropTypes.string.isRequired,
  }),
};

const FirstTraceSetupGuide = ({
  getCodeBySection,
  languageTab,
  onLanguageChange,
  setupVerification,
  tabOptions,
  tabWrapperStyles,
  theme,
}) => {
  const statusLabel =
    setupVerification?.status === "ready"
      ? "Trace detected"
      : "Live check running";

  return (
    <Box
      data-testid="observe-first-trace-guide"
      sx={{
        border: "1px solid",
        borderColor: "primary.main",
        borderRadius: 1,
        bgcolor: "action.hover",
        p: 2,
      }}
    >
      <Stack spacing={2}>
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={1}
          justifyContent="space-between"
          alignItems={{ xs: "flex-start", md: "center" }}
        >
          <Stack spacing={0.5}>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              <Chip size="small" color="primary" label="Fastest path to Aha" />
              <Chip size="small" variant="outlined" label={statusLabel} />
            </Stack>
            <Typography variant="h6">Send one trace, then review it</Typography>
            <Typography variant="body2" color="text.secondary" maxWidth={720}>
              Use the minimal setup below, run one request, and FutureAGI will
              move you to trace review when the signal arrives.
            </Typography>
          </Stack>

          <TabWrapper sx={tabWrapperStyles}>
            <CustomTabs
              textColor="primary"
              value={languageTab}
              onChange={(e, value) => onLanguageChange(value)}
              TabIndicatorProps={{
                style: {
                  backgroundColor: theme.palette.primary.main,
                  opacity: 0.08,
                  height: "100%",
                  borderRadius: "8px",
                },
              }}
            >
              {tabOptions.map((tab) => (
                <CustomTab
                  key={`first-trace-${tab.value}`}
                  label={tab.label}
                  value={tab.value}
                  disabled={tab.disabled}
                />
              ))}
            </CustomTabs>
          </TabWrapper>
        </Stack>

        <Box
          data-testid="observe-first-trace-steps"
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" },
            gap: 1,
          }}
        >
          {FIRST_TRACE_STEPS.map((step, index) => (
            <Box
              key={step.id}
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
                bgcolor: "background.paper",
                p: 1.25,
                minHeight: 96,
              }}
            >
              <Stack spacing={0.75}>
                <Stack direction="row" spacing={0.75} alignItems="center">
                  <Chip size="small" label={index + 1} />
                  <Typography variant="subtitle2">{step.label}</Typography>
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  {step.description}
                </Typography>
              </Stack>
            </Box>
          ))}
        </Box>

        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", lg: "repeat(3, 1fr)" },
            gap: 1.5,
            minWidth: 0,
          }}
        >
          <Stack spacing={1} sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2">1. Install package</Typography>
            <InstructionCodeCopy
              ariaLabel="Copy install command"
              text={getCodeBySection("installationGuide")}
              language={languageTab}
            />
          </Stack>
          <Stack spacing={1} sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2">2. Load project keys</Typography>
            <InstructionCodeCopy
              ariaLabel="Copy project keys"
              text={getCodeBySection("keys")}
              language={languageTab}
            />
          </Stack>
          <Stack spacing={1} sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2">
              3. Add tracing before your app runs
            </Typography>
            <InstructionCodeCopy
              ariaLabel="Copy tracing setup"
              text={getCodeBySection("projectAddCode")}
              language={languageTab}
            />
          </Stack>
        </Box>

        <VerificationAlert setupVerification={setupVerification} />
      </Stack>
    </Box>
  );
};

FirstTraceSetupGuide.propTypes = {
  getCodeBySection: PropTypes.func.isRequired,
  languageTab: PropTypes.string.isRequired,
  onLanguageChange: PropTypes.func.isRequired,
  setupVerification: VerificationAlert.propTypes.setupVerification,
  tabOptions: PropTypes.arrayOf(
    PropTypes.shape({
      disabled: PropTypes.bool,
      label: PropTypes.string.isRequired,
      value: PropTypes.string.isRequired,
    }),
  ).isRequired,
  tabWrapperStyles: PropTypes.object.isRequired,
  theme: PropTypes.object.isRequired,
};

const NewObserve = ({ setupVerification, showFirstTraceGuide = false }) => {
  const theme = useTheme();
  const [languageTab, setLanguageTab] = useState("python");
  const {
    data: keysData,
    isSuccess,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["keys"],
    queryFn: () =>
      axios.get(endpoints.project.getCodeBlockTracer, {
        params: {
          project_type: "observe",
        },
      }),
    select: (d) => d.data?.result,
  });

  const tabOptions = [
    { label: "Python", value: "python", disabled: false },
    { label: "Typescript", value: "typescript", disabled: false },
  ];

  const tabWrapperStyles = useMemo(
    () => ({
      marginBottom: 0,
      alignSelf: "flex-start",
    }),
    [],
  );

  const cleanCode = (code) => {
    if (typeof code !== "string") return "Code not available";
    return code.replace(/^\n+/, "").replace(/\n+$/, "");
  };

  // Helper functions to get the correct code based on active tabs
  const getCodeBySection = (section) => {
    const languageKey = languageTab === "python" ? "Python" : "TypeScript";
    const sectionData =
      keysData[section] || keysData[CODE_SECTION_ALIASES[section]];
    return cleanCode(sectionData?.[languageKey]);
  };

  return (
    <Box
      sx={{
        width: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 4, // 32px spacing between major sections
      }}
    >
      {setupVerification &&
      (!showFirstTraceGuide || !isSuccess || !keysData) ? (
        <VerificationAlert setupVerification={setupVerification} />
      ) : null}

      {!isSuccess || !keysData ? <LinearProgress /> : null}

      {isSuccess && keysData ? (
        <>
          {showFirstTraceGuide ? (
            <FirstTraceSetupGuide
              getCodeBySection={getCodeBySection}
              languageTab={languageTab}
              onLanguageChange={setLanguageTab}
              setupVerification={setupVerification}
              tabOptions={tabOptions}
              tabWrapperStyles={tabWrapperStyles}
              theme={theme}
            />
          ) : null}

          {showFirstTraceGuide ? (
            <Stack spacing={0.5}>
              <Divider />
              <Typography variant="subtitle2">Full setup reference</Typography>
            </Stack>
          ) : null}

          {/* Installation & Keys Section */}
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
            <InstructionTitle
              title="Install Dependencies"
              description="For more instructions, checkout our "
              url="https://docs.futureagi.com/docs/observe"
              urltext="Docs"
              onUrlClick={() => handleOnDocsClicked("observe_page")}
            />

            <InstructionTitle description="Configure your application to send traces to Future AGI" />

            {/* Tab selector for installation */}
            <TabWrapper sx={tabWrapperStyles}>
              <CustomTabs
                textColor="primary"
                value={languageTab}
                onChange={(e, value) => setLanguageTab(value)}
                TabIndicatorProps={{
                  style: {
                    backgroundColor: theme.palette.primary.main,
                    opacity: 0.08,
                    height: "100%",
                    borderRadius: "8px",
                  },
                }}
              >
                {tabOptions.map((tab) => (
                  <CustomTab
                    key={`config-${tab.value}`}
                    label={tab.label}
                    value={tab.value}
                    disabled={tab.disabled}
                  />
                ))}
              </CustomTabs>
            </TabWrapper>

            <InstructionCodeCopy
              ariaLabel="Copy install command"
              text={getCodeBySection("installationGuide")}
              language={languageTab}
              // onCopy={() => trackEvent(Events.installDependenciesCopied)}
            />

            {/* API Keys */}
            <Box sx={{ mt: 1.5 }}>
              <InstructionTitle
                title="Load API keys"
                description="load your API keys"
              />
            </Box>

            <InstructionCodeCopy
              ariaLabel="Copy API keys"
              text={getCodeBySection("keys")}
              language={languageTab}
              onCopy={() => trackEvent(Events.apikeys)}
            />
          </Box>

          {/* Telemetry Section with its own tab control */}
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
            <InstructionTitle
              title="Setup Telemetry"
              description="Register your application to send traces to this project. The code should be added BEFORE any code execution."
            />

            {/* Separate tab selector for telemetry */}
            <TabWrapper sx={tabWrapperStyles}>
              <CustomTabs
                textColor="primary"
                value={languageTab}
                onChange={(e, value) => setLanguageTab(value)}
                TabIndicatorProps={{
                  style: {
                    backgroundColor: theme.palette.primary.main,
                    opacity: 0.08,
                    height: "100%",
                    borderRadius: "8px",
                  },
                }}
              >
                {tabOptions.map((tab) => (
                  <CustomTab
                    key={`telemetry-${tab.value}`}
                    label={tab.label}
                    value={tab.value}
                    disabled={tab.disabled}
                  />
                ))}
              </CustomTabs>
            </TabWrapper>

            <InstructionCodeCopy
              ariaLabel="Copy telemetry setup"
              text={getCodeBySection("projectAddCode")}
              language={languageTab}
              // onCopy={() => trackEvent(Events.setupTelemetryCopied)}
            />
          </Box>

          {/* Instruments Section */}
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
            <InstructionTitle
              title="Setup Instrumentation"
              description="Add tracing instrumentation to give you observability into your application."
            />

            <ObserveInstruments
              data={keysData?.instruments}
              isLoading={isLoading}
              isSuccess={isSuccess}
              error={error}
              languageTab={languageTab}
              onLanguageChange={setLanguageTab}
            />
          </Box>
        </>
      ) : null}
    </Box>
  );
};

NewObserve.propTypes = {
  showFirstTraceGuide: PropTypes.bool,
  setupVerification: PropTypes.shape({
    description: PropTypes.string.isRequired,
    primaryAction: PropTypes.shape({
      disabled: PropTypes.bool,
      label: PropTypes.string.isRequired,
      onClick: PropTypes.func.isRequired,
    }),
    status: PropTypes.oneOf(["ready", "waiting"]).isRequired,
    title: PropTypes.string.isRequired,
  }),
};

export default NewObserve;
