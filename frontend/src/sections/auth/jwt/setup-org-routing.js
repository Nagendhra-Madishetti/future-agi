import { paths } from "src/routes/paths";

export const SETUP_COMPLETION_SOURCE = "setup_org";

export const setupCompletionHomeHref = () =>
  `${paths.dashboard.home}?source=${SETUP_COMPLETION_SOURCE}`;

export const isSafeSetupReturnTo = (returnTo) =>
  typeof returnTo === "string" &&
  returnTo.startsWith("/") &&
  !returnTo.startsWith("//") &&
  !returnTo.startsWith("/auth");

export const resolveSetupCompletionHref = (returnTo) =>
  isSafeSetupReturnTo(returnTo) ? returnTo : setupCompletionHomeHref();
