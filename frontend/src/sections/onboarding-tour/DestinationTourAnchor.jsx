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
import { destinationTourCopyForStep } from "./destinationTourAnchorConfig";

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
    () => destinationTourCopyForStep(journeyStep),
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
