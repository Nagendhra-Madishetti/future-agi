import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import PropTypes from "prop-types";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import GlobalStyles from "@mui/material/GlobalStyles";
import Paper from "@mui/material/Paper";
import Popper from "@mui/material/Popper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import Iconify from "src/components/iconify";

const STEP_COPY = {
  add_eval_scorer: {
    label: "Add scorer",
    description:
      "Use the highlighted action to define the signal this eval measures.",
  },
  add_gateway_policy: {
    label: "Add policy",
    description: "Use the highlighted action to add the first gateway control.",
  },
  add_voice_success_criteria: {
    label: "Add criteria",
    description: "Use the highlighted action to define what a good call means.",
  },
  compare_prompt_versions: {
    label: "Compare versions",
    description:
      "Use the highlighted action to compare this prompt against a baseline.",
  },
  configure_gateway_provider: {
    label: "Add provider",
    description:
      "Use the highlighted action to connect the first model provider.",
  },
  connect_observability: {
    label: "Connect observability",
    description:
      "Use the highlighted action to create or review the observe setup.",
  },
  create_eval_dataset: {
    label: "Create dataset",
    description: "Use the highlighted action to start the eval source.",
  },
  create_gateway_key: {
    label: "Create key",
    description: "Use the highlighted action to create the first gateway key.",
  },
  create_prompt: {
    label: "Create prompt",
    description: "Use the highlighted action to start the prompt loop.",
  },
  create_trace_evaluator: {
    label: "Create check",
    description:
      "Use the highlighted action to turn this trace into a repeatable check.",
  },
  create_voice_agent: {
    label: "Create agent",
    description: "Use the highlighted action to start the voice workflow.",
  },
  eval_next_loop: {
    label: "Improve source",
    description:
      "Use the highlighted action to turn the failure into the next fix.",
  },
  fix_gateway_failure: {
    label: "Fix issue",
    description:
      "Use the highlighted action to resolve the first gateway failure.",
  },
  prompt_next_loop: {
    label: "Capture example",
    description:
      "Use the highlighted action to save one concrete failure example.",
  },
  review_eval_failures: {
    label: "Review failure",
    description:
      "Use the highlighted action to inspect the first useful eval failure.",
  },
  review_first_trace: {
    label: "Review signal",
    description:
      "Use the highlighted action to inspect the first trace signal.",
  },
  review_gateway_log: {
    label: "Review log",
    description:
      "Use the highlighted action to inspect status, latency, cost, and routing.",
  },
  review_voice_call: {
    label: "Review call",
    description:
      "Use the highlighted action to inspect the transcript and outcome.",
  },
  run_eval: {
    label: "Run eval",
    description: "Use the highlighted action to run the first eval.",
  },
  run_gateway_request: {
    label: "Send request",
    description:
      "Use the highlighted action to send one request through the gateway.",
  },
  run_prompt_test: {
    label: "Run test",
    description:
      "Use the highlighted action to generate the first prompt result.",
  },
  run_voice_test_call: {
    label: "Run call",
    description:
      "Use the highlighted action to collect the first voice signal.",
  },
  save_prompt_version: {
    label: "Save version",
    description:
      "Use the highlighted action to save the tested prompt baseline.",
  },
  send_first_trace: {
    label: "Send trace",
    description:
      "Use the highlighted action to send or inspect the first trace.",
  },
  start_prompt: {
    label: "Create prompt",
    description: "Use the highlighted action to start the prompt loop.",
  },
  voice_monitor_calls: {
    label: "Monitor calls",
    description:
      "Use the highlighted action to keep watching live calls after setup.",
  },
};

const DEFAULT_COPY = {
  label: "Next step",
  description: "Use the highlighted action to continue setup.",
};

const findTourTarget = (anchor) => {
  if (!anchor) return null;
  const byTourAnchor = Array.from(
    document.querySelectorAll("[data-tour-anchor]"),
  ).find((item) => item.getAttribute("data-tour-anchor") === anchor);
  if (byTourAnchor) return byTourAnchor;

  const byTestId = Array.from(document.querySelectorAll("[data-testid]")).find(
    (item) => item.getAttribute("data-testid") === anchor,
  );
  if (byTestId) return byTestId;

  return document.getElementById(anchor);
};

export default function DestinationTourAnchor({ maxAttempts = 12 }) {
  const [searchParams] = useSearchParams();
  const tourAnchor = searchParams.get("tour_anchor");
  const journeyStep = searchParams.get("journey_step");
  const [targetEl, setTargetEl] = useState(null);
  const [dismissedAnchor, setDismissedAnchor] = useState(null);

  const copy = useMemo(
    () => STEP_COPY[journeyStep] || DEFAULT_COPY,
    [journeyStep],
  );
  const hidden = !tourAnchor || dismissedAnchor === tourAnchor;

  useEffect(() => {
    setTargetEl(null);
    if (hidden) return undefined;

    let cancelled = false;
    let attempt = 0;
    let timeoutId;

    const resolveTarget = () => {
      if (cancelled) return;
      const nextTarget = findTourTarget(tourAnchor);
      if (nextTarget) {
        setTargetEl(nextTarget);
        nextTarget.scrollIntoView?.({ block: "center", behavior: "smooth" });
        return;
      }
      attempt += 1;
      if (attempt < maxAttempts) {
        timeoutId = window.setTimeout(resolveTarget, 150);
      }
    };

    resolveTarget();

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [hidden, maxAttempts, tourAnchor]);

  useEffect(() => {
    if (!targetEl || hidden) return undefined;
    targetEl.setAttribute("data-onboarding-tour-active", "true");
    return () => {
      targetEl.removeAttribute("data-onboarding-tour-active");
    };
  }, [hidden, targetEl]);

  if (hidden || !targetEl) {
    return null;
  }

  return (
    <>
      <GlobalStyles
        styles={(theme) => ({
          '[data-onboarding-tour-active="true"]': {
            position: "relative",
            outline: `2px solid ${theme.palette.primary.main}`,
            outlineOffset: 4,
            boxShadow: `0 0 0 6px ${alpha(theme.palette.primary.main, 0.14)}`,
            borderRadius: 8,
            zIndex: theme.zIndex.drawer + 1,
          },
        })}
      />
      <Popper
        open
        anchorEl={targetEl}
        placement="bottom-start"
        modifiers={[
          { name: "offset", options: { offset: [0, 10] } },
          { name: "preventOverflow", options: { padding: 12 } },
        ]}
        sx={{ zIndex: (theme) => theme.zIndex.modal + 1 }}
      >
        <Paper
          data-testid="destination-tour-anchor"
          elevation={6}
          sx={{
            border: "1px solid",
            borderColor: "primary.main",
            borderRadius: 1,
            maxWidth: 320,
            p: 1.25,
          }}
        >
          <Stack spacing={1}>
            <Stack direction="row" spacing={0.75} alignItems="center">
              <Chip size="small" color="primary" label="Current step" />
              <Typography variant="subtitle2">{copy.label}</Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              {copy.description}
            </Typography>
            <Box>
              <Button
                size="small"
                variant="text"
                onClick={() => setDismissedAnchor(tourAnchor)}
                startIcon={<Iconify icon="mdi:check" width={16} />}
              >
                Got it
              </Button>
            </Box>
          </Stack>
        </Paper>
      </Popper>
    </>
  );
}

DestinationTourAnchor.propTypes = {
  maxAttempts: PropTypes.number,
};
