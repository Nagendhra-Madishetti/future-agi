import { trackPostHogEvent } from "src/utils/PostHog";

export const SetupOrgEvents = {
  profileSaved: "setup_org_profile_saved",
  invitesSaved: "setup_org_invites_saved",
};

const compactProperties = (properties) =>
  Object.entries(properties).reduce((result, [key, value]) => {
    if (value === undefined || value === null || value === "") {
      return result;
    }
    if (Array.isArray(value) && value.length === 0) {
      return result;
    }
    result[key] = value;
    return result;
  }, {});

const selectedGoals = (goals) =>
  Array.isArray(goals) ? goals.filter((goal) => Boolean(goal)) : [];

const newInviteMembers = (members) =>
  Array.isArray(members)
    ? members.filter((member) => !member?.disabled && member?.email?.trim())
    : [];

export const buildSetupOrgProfileSavedProperties = ({
  goals,
  provider,
  quickStartRequested,
  role,
} = {}) => {
  const goalsList = selectedGoals(goals);

  return compactProperties({
    role,
    primary_goal: goalsList[0],
    goal_count: goalsList.length,
    method: provider,
    quick_start_requested: Boolean(quickStartRequested),
  });
};

export const buildSetupOrgInvitesSavedProperties = ({ members } = {}) => {
  const membersToTrack = newInviteMembers(members);
  const roles = [
    ...new Set(
      membersToTrack
        .map((member) => member?.organization_role)
        .filter((role) => Boolean(role)),
    ),
  ];

  return compactProperties({
    invited_member_count: membersToTrack.length,
    roles_assigned: roles,
  });
};

export const trackSetupOrgProfileSaved = (properties) => {
  trackPostHogEvent(
    SetupOrgEvents.profileSaved,
    buildSetupOrgProfileSavedProperties(properties),
  );
};

export const trackSetupOrgInvitesSaved = (properties) => {
  trackPostHogEvent(
    SetupOrgEvents.invitesSaved,
    buildSetupOrgInvitesSavedProperties(properties),
  );
};
