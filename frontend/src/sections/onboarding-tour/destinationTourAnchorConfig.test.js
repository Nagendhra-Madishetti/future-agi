import { readFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import {
  DESTINATION_TOUR_ANCHORS,
  DESTINATION_TOUR_STEP_COPY,
} from "./destinationTourAnchorConfig";

const activationFlowPath = path.resolve(
  process.cwd(),
  "../futureagi/accounts/services/onboarding/activation_flow.yml",
);
const activationFlow = parse(readFileSync(activationFlowPath, "utf8"));

const journeySteps = Object.values(activationFlow.journeys).flatMap(
  (journey) => journey.steps,
);

describe("destinationTourAnchorConfig", () => {
  it("has focused copy for every configured journey step", () => {
    const configuredStepIds = journeySteps.map((step) => step.id);
    const missingCopy = configuredStepIds.filter(
      (stepId) => !DESTINATION_TOUR_STEP_COPY[stepId],
    );

    expect(missingCopy).toEqual([]);
  });

  it("tracks the configured journey anchor contract", () => {
    const configuredAnchors = activationFlow.tour_anchors;
    const supportedAnchors = new Set(DESTINATION_TOUR_ANCHORS);
    const configuredAnchorSet = new Set(configuredAnchors);

    const missingAnchors = configuredAnchors.filter(
      (anchor) => !supportedAnchors.has(anchor),
    );
    const staleAnchors = DESTINATION_TOUR_ANCHORS.filter(
      (anchor) => !configuredAnchorSet.has(anchor),
    );

    expect(missingAnchors).toEqual([]);
    expect(staleAnchors).toEqual([]);
  });
});
