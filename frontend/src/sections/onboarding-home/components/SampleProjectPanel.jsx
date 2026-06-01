import React from "react";
import PropTypes from "prop-types";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Iconify from "src/components/iconify";
import { RouterLink } from "src/routes/components";
import {
  canOpenSample,
  hasSampleRoute,
  isSampleHidden,
} from "../activation-state-utils";
import { readableToken } from "../onboarding-home.constants";

export default function SampleProjectPanel({
  sampleProject,
  activationStage,
  selectedGoal,
  realSetupHref: realSetupHrefOverride,
  onOpenSample,
  onHideSample,
  onConnectRealData,
  isOpening = false,
  isHiding = false,
}) {
  if (
    !sampleProject ||
    isSampleHidden(sampleProject) ||
    sampleProject.status === "unavailable"
  ) {
    return null;
  }

  const hasRoute = hasSampleRoute(sampleProject);
  const canOpen = canOpenSample(sampleProject);
  const realSetupHref =
    realSetupHrefOverride ||
    sampleProject.realSetupHref ||
    "/dashboard/observe?setup=true&source=onboarding";
  const statusLabel =
    sampleProject.status === "not_created"
      ? "Ready to create"
      : readableToken(sampleProject.status);
  const isRealDataStep = activationStage === "connect_real_data";
  const title = isRealDataStep
    ? "Connect the same workflow to real data"
    : "Preview sample trace";
  const description = isRealDataStep
    ? "Use the sample trace as a reference, then connect real data so the workflow runs on your production traces."
    : "Optional sample trace is ready if you want to inspect the product. Connect real data to finish setup.";
  const openSampleTourAnchor =
    activationStage === "review_sample_signal" || isRealDataStep
      ? "sample_trace_link"
      : "sample_project_button";
  const proofPoints = [
    {
      label: "Trace context",
      value: "Input, output, latency, cost",
    },
    {
      label: "Issue to review",
      value: "A failure signal you can inspect",
    },
    {
      label: "Real setup",
      value: "Connect real data to create checks from your own traces",
    },
  ];
  const openSampleButton = (
    <Button
      variant={isRealDataStep ? "outlined" : "contained"}
      onClick={onOpenSample}
      disabled={!canOpen || isOpening}
      data-tour-anchor={openSampleTourAnchor}
      startIcon={<Iconify icon="mdi:flask-outline" width={18} />}
      sx={{ alignSelf: { xs: "stretch", sm: "flex-start" } }}
    >
      {isOpening ? "Opening..." : "Open sample trace"}
    </Button>
  );
  const realSetupButton = (
    <Button
      variant={isRealDataStep ? "contained" : "outlined"}
      component={RouterLink}
      href={realSetupHref}
      onClick={onConnectRealData}
      data-tour-anchor={
        isRealDataStep ? "sample_connect_real_data_button" : undefined
      }
      startIcon={<Iconify icon="mdi:connection" width={18} />}
      sx={{ alignSelf: { xs: "stretch", sm: "flex-start" } }}
    >
      Connect real data
    </Button>
  );

  return (
    <Box
      data-testid="sample-project-panel"
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        p: 2,
        bgcolor: "background.paper",
      }}
    >
      <Stack spacing={1.5}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          alignItems={{ xs: "flex-start", sm: "center" }}
          justifyContent="space-between"
        >
          <Stack direction="row" spacing={0.75} alignItems="center">
            <Chip size="small" variant="outlined" label="Sample trace" />
            <Chip size="small" label={sampleProject.label || "Sample"} />
            <Chip size="small" variant="outlined" label={statusLabel} />
          </Stack>
          <Typography variant="caption" color="text.secondary">
            {selectedGoal
              ? readableToken(selectedGoal)
              : readableToken(activationStage)}
          </Typography>
        </Stack>

        <Stack spacing={0.5}>
          <Typography variant="h6">{title}</Typography>
          <Typography variant="body2" color="text.secondary">
            {description}
          </Typography>
        </Stack>

        <Box
          data-testid="sample-project-preview-points"
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" },
            gap: 1,
          }}
        >
          {proofPoints.map((point) => (
            <Box
              key={point.label}
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
                bgcolor: "background.paper",
                p: 1,
                minHeight: 72,
              }}
            >
              <Typography variant="subtitle2">{point.label}</Typography>
              <Typography variant="caption" color="text.secondary">
                {point.value}
              </Typography>
            </Box>
          ))}
        </Box>

        {sampleProject.status === "partially_ready" && !hasRoute ? (
          <Typography variant="body2" color="text.secondary">
            The sample trace is not ready. Connect real data to continue.
          </Typography>
        ) : null}

        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          {isRealDataStep ? realSetupButton : openSampleButton}
          {isRealDataStep ? openSampleButton : realSetupButton}
          <Button
            variant="text"
            color="inherit"
            onClick={onHideSample}
            disabled={isHiding}
            startIcon={<Iconify icon="mdi:close" width={18} />}
            sx={{ alignSelf: { xs: "stretch", sm: "flex-start" } }}
          >
            Hide sample
          </Button>
        </Stack>
      </Stack>
    </Box>
  );
}

SampleProjectPanel.propTypes = {
  activationStage: PropTypes.string,
  isHiding: PropTypes.bool,
  isOpening: PropTypes.bool,
  onConnectRealData: PropTypes.func,
  onHideSample: PropTypes.func,
  onOpenSample: PropTypes.func,
  realSetupHref: PropTypes.string,
  sampleProject: PropTypes.object,
  selectedGoal: PropTypes.string,
};
