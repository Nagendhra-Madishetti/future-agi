import React from "react";
import PropTypes from "prop-types";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import {
  ObserveJourneyProgress,
  ObservePanelActions,
  ObservePanelHeader,
} from "./observe-panel-utils";
import { observeFallbackJourneyPlan } from "./observe-fallback-journey-plan";
import { journeyCurrentStep } from "./journey-guide-utils";

export default function WaitingForSignalPanel({
  action,
  fallbackAction,
  journeyPlan,
  signals,
  stage,
  onPrimaryClick,
  onFallbackClick,
  onCheckAgain,
  isChecking = false,
  singleActionFocus = false,
}) {
  const effectiveJourneyPlan = journeyPlan || observeFallbackJourneyPlan(stage);
  const currentStep = journeyCurrentStep(effectiveJourneyPlan, stage);
  const actionSlot = currentStep ? (
    <ObservePanelActions
      action={action}
      fallbackAction={fallbackAction}
      onPrimaryClick={onPrimaryClick}
      onFallbackClick={onFallbackClick}
      onCheckAgain={onCheckAgain}
      isChecking={isChecking}
      journeyStep={currentStep}
      singleActionFocus={singleActionFocus || Boolean(currentStep)}
    />
  ) : null;

  return (
    <Box
      data-testid="waiting-for-signal-panel"
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        p: 2,
        bgcolor: "background.paper",
      }}
    >
      <Stack spacing={2}>
        <ObservePanelHeader
          eyebrow="Waiting for trace"
          title="Send one real trace"
          description="The observe project exists. The next step unlocks after the first real trace arrives."
          chips={["observe", "waiting"]}
        />
        <ObserveJourneyProgress
          actionSlot={actionSlot}
          journeyPlan={effectiveJourneyPlan}
          singleActionFocus={singleActionFocus}
          stage={stage}
        />
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            p: 1.5,
          }}
        >
          <Typography variant="subtitle2">Current signal</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Projects: {signals?.observeProjects || 0} · Traces:{" "}
            {signals?.traces || 0}
          </Typography>
        </Box>
        {currentStep ? null : (
          <ObservePanelActions
            action={action}
            fallbackAction={fallbackAction}
            onPrimaryClick={onPrimaryClick}
            onFallbackClick={onFallbackClick}
            onCheckAgain={onCheckAgain}
            isChecking={isChecking}
            journeyStep={currentStep}
            singleActionFocus={singleActionFocus}
          />
        )}
      </Stack>
    </Box>
  );
}

WaitingForSignalPanel.propTypes = {
  action: PropTypes.object,
  fallbackAction: PropTypes.object,
  isChecking: PropTypes.bool,
  journeyPlan: PropTypes.object,
  onCheckAgain: PropTypes.func,
  onFallbackClick: PropTypes.func,
  onPrimaryClick: PropTypes.func,
  singleActionFocus: PropTypes.bool,
  signals: PropTypes.object,
  stage: PropTypes.string,
};
