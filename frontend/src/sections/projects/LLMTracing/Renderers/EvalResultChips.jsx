import React from "react";
import PropTypes from "prop-types";
import { Box, Typography } from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
import {
  EVAL_KIND,
  adaptEvalCell,
  choiceTone,
} from "../evalCellModel";

const TONE_TO_PALETTE = {
  pass: "success",
  fail: "error",
  neutral: "warning",
  errored: "warning",
};

const ResultChip = ({ label, tone }) => {
  const theme = useTheme();
  const palette =
    theme.palette[TONE_TO_PALETTE[tone] || "info"] || theme.palette.info;
  const color = tone === "errored" ? theme.palette.warning.dark : palette.main;
  return (
    <Box
      component="span"
      sx={{
        display: "inline-flex",
        alignItems: "center",
        flexShrink: 0,
        px: "8px",
        py: "1px",
        borderRadius: "12px",
        border: `1px solid ${alpha(color, 0.5)}`,
        backgroundColor: alpha(color, 0.08),
        color,
        fontSize: "12px",
        fontWeight: 600,
        lineHeight: "18px",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </Box>
  );
};

ResultChip.propTypes = {
  label: PropTypes.string,
  tone: PropTypes.oneOf(["pass", "fail", "neutral", "errored", "plain"]),
};

const Annotation = ({ text }) => (
  <Typography
    component="span"
    title={text}
    sx={{
      fontSize: "12px",
      fontStyle: "italic",
      color: "text.secondary",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis",
      flexShrink: 1,
      minWidth: 0,
    }}
  >
    {text}
  </Typography>
);

Annotation.propTypes = { text: PropTypes.string };

const trimNum = (n) =>
  typeof n === "number" ? `${Number(n.toFixed(2))}` : `${n}`;

const spanLevelChips = (model, col) => {
  const { kind } = model;
  const { outcomes, evaluated, errored, mean, notEvaluated } = model.spanLevel;
  const chips = [];
  const denom =
    evaluated ?? (Object.values(outcomes).reduce((a, b) => a + b, 0) || null);

  if (kind === EVAL_KIND.PASS_FAIL) {
    if (outcomes.fail) chips.push({ label: `Fail ${outcomes.fail}`, tone: "fail" });
    if (errored) chips.push({ label: `Errored ${errored}`, tone: "errored" });
    if (outcomes.pass) chips.push({ label: `Pass ${outcomes.pass}`, tone: "pass" });
  } else if (kind === EVAL_KIND.CHOICE) {
    Object.entries(outcomes)
      .sort((a, b) => b[1] - a[1])
      .forEach(([label, count]) => {
        const pct = denom ? Math.round((count / denom) * 100) : null;
        chips.push({
          label: pct != null ? `${label} ${pct}%` : `${label} ${count}`,
          tone: choiceTone(label, col),
        });
      });
    if (errored) chips.push({ label: `Errored ${errored}`, tone: "errored" });
  } else {
    if (mean != null) chips.push({ label: trimNum(mean), tone: "plain" });
    if (errored) chips.push({ label: `Errored ${errored}`, tone: "errored" });
  }
  return { chips, notEvaluated };
};

const traceLevelChip = (model, col) => {
  const { outcome, value } = model.traceLevel;
  if (model.kind === EVAL_KIND.NUMERIC || (outcome == null && value != null))
    return { label: trimNum(value), tone: "plain" };
  if (outcome === "pass" || outcome === "fail")
    return { label: outcome === "pass" ? "Pass" : "Fail", tone: outcome };
  if (outcome === "errored") return { label: "Errored", tone: "errored" };
  if (outcome) return { label: outcome, tone: choiceTone(outcome, col) };
  return null;
};

const legacyChip = (model, col) => {
  const value = model.legacy;
  if (model.kind === EVAL_KIND.PASS_FAIL)
    return value >= 50
      ? { label: "Pass", tone: "pass" }
      : { label: "Fail", tone: "fail" };
  if (model.kind === EVAL_KIND.CHOICE) {
    const label = String(col?.id || "").split("**")[1] || col?.name || "";
    return { label: `${label} ${trimNum(value)}%`, tone: choiceTone(label, col) };
  }
  return { label: trimNum(value), tone: "plain" };
};

const EvalResultChips = (params) => {
  const col = params?.colDef?.context?.sourceColumn;
  const raw = params?.data?.eval_results?.[col?.id] ?? params?.value;
  const model = adaptEvalCell(raw, col);
  if (!model) return null;

  let chips = [];
  let notEvaluated = 0;
  if (model.spanLevel) {
    ({ chips, notEvaluated } = spanLevelChips(model, col));
  } else if (model.traceLevel) {
    const chip = traceLevelChip(model, col);
    if (chip) chips = [chip];
  } else if (model.legacy != null) {
    const chip = legacyChip(model, col);
    if (chip) chips = [chip];
  }

  const nothingRan = chips.length === 0;
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-start",
        flexWrap: "nowrap",
        gap: "4px",
        px: "12px",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        minWidth: 0,
      }}
    >
      {chips.map((c) => (
        <ResultChip key={c.label} label={c.label} tone={c.tone} />
      ))}
      {nothingRan && notEvaluated === 0 && <Annotation text="Not evaluated" />}
      {notEvaluated > 0 && (
        <Annotation
          text={nothingRan ? "Not evaluated" : `+ ${notEvaluated} not evaluated`}
        />
      )}
    </Box>
  );
};

export default EvalResultChips;
