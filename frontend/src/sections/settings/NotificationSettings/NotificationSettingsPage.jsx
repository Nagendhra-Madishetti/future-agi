import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  FormControlLabel,
  IconButton,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { enqueueSnackbar } from "notistack";
import Iconify from "src/components/iconify";
import axios, { endpoints } from "src/utils/axios";

const CHANNEL_LABELS = {
  email: "Email",
  in_app: "In-app",
  slack: "Slack",
  webhook: "Webhook",
};

const CHANNEL_ICONS = {
  email: "mdi:email-outline",
  in_app: "mdi:bell-outline",
  slack: "mdi:slack",
  webhook: "mdi:webhook",
};

const FAMILY_ORDER = [
  "product_onboarding",
  "daily_quality_digest",
  "usage_budget",
  "gateway_alert",
  "observe_monitor",
  "eval_quality_alert",
  "workspace_admin",
];

function decisionKey(family, channel) {
  return `${family}:${channel}`;
}

function preferencePayload({ family, channel, enabled }) {
  return {
    preferences: [
      {
        scope: "user_workspace",
        family,
        channel,
        enabled,
      },
    ],
  };
}

export default function NotificationSettingsPage() {
  const queryClient = useQueryClient();
  const [slackName, setSlackName] = useState("");
  const [slackWebhook, setSlackWebhook] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["notification-preferences"],
    queryFn: () => axios.get(endpoints.settings.notifications),
    select: (res) => res.data?.result,
  });

  const patchMutation = useMutation({
    mutationFn: (payload) =>
      axios.patch(endpoints.settings.notifications, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notification-preferences"] });
    },
    onError: () =>
      enqueueSnackbar("Failed to update notification settings", {
        variant: "error",
      }),
  });

  const testMutation = useMutation({
    mutationFn: (channelId) =>
      axios.post(endpoints.settings.notificationChannelTest(channelId), {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notification-preferences"] });
      enqueueSnackbar("Channel test recorded", { variant: "success" });
    },
    onError: () => enqueueSnackbar("Channel test failed", { variant: "error" }),
  });

  const decisions = useMemo(() => {
    const map = new Map();
    (data?.decisions || []).forEach((decision) => {
      map.set(decisionKey(decision.family, decision.channel), decision);
    });
    return map;
  }, [data]);

  const families = useMemo(() => {
    const byId = new Map(
      (data?.families || []).map((family) => [family.id, family]),
    );
    return FAMILY_ORDER.map((id) => byId.get(id)).filter(Boolean);
  }, [data]);

  const channels = data?.channels || [];
  const canManageWorkspace = Boolean(data?.can_manage_workspace);

  const handleToggle = (family, channel, checked) => {
    patchMutation.mutate(
      preferencePayload({ family, channel, enabled: checked }),
    );
  };

  const handleAddSlack = () => {
    patchMutation.mutate(
      {
        channels: [
          {
            scope: "workspace",
            type: "slack_webhook",
            display_name: slackName || "Workspace Slack alerts",
            config: { webhook_url: slackWebhook },
            is_active: true,
          },
        ],
      },
      {
        onSuccess: () => {
          setSlackName("");
          setSlackWebhook("");
          enqueueSnackbar("Slack channel saved", { variant: "success" });
          queryClient.invalidateQueries({
            queryKey: ["notification-preferences"],
          });
        },
      },
    );
  };

  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error">Notification settings could not be loaded.</Alert>
    );
  }

  return (
    <Box sx={{ maxWidth: 1120, mx: "auto", py: 1 }}>
      <Stack spacing={3}>
        <Stack
          direction={{ xs: "column", md: "row" }}
          justifyContent="space-between"
          alignItems={{ xs: "flex-start", md: "center" }}
          spacing={2}
        >
          <Box>
            <Typography variant="h4">Notifications</Typography>
            <Typography variant="body2" color="text.secondary">
              Manage onboarding, quality, usage, and workspace alert routing.
            </Typography>
          </Box>
          <Chip
            icon={<Iconify icon="mdi:shield-check-outline" width={18} />}
            label={canManageWorkspace ? "Workspace admin" : "Personal settings"}
            variant="outlined"
          />
        </Stack>

        <Paper variant="outlined" sx={{ borderRadius: 1 }}>
          <Stack spacing={0} divider={<Divider />}>
            {families.map((family) => (
              <Box key={family.id} sx={{ p: 2.25 }}>
                <Stack
                  direction={{ xs: "column", md: "row" }}
                  spacing={2}
                  justifyContent="space-between"
                >
                  <Box sx={{ minWidth: 260 }}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography variant="subtitle2">
                        {family.label}
                      </Typography>
                      {!family.non_critical && (
                        <Chip
                          label="Operational"
                          size="small"
                          variant="outlined"
                        />
                      )}
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      {family.description}
                    </Typography>
                  </Box>
                  <Stack
                    direction={{ xs: "column", sm: "row" }}
                    spacing={2}
                    flexWrap="wrap"
                  >
                    {family.default_channels.map((channel) => {
                      const decision = decisions.get(
                        decisionKey(family.id, channel),
                      );
                      const checked = decision?.allowed !== false;
                      return (
                        <FormControlLabel
                          key={channel}
                          control={
                            <Switch
                              checked={checked}
                              onChange={(event) =>
                                handleToggle(
                                  family.id,
                                  channel,
                                  event.target.checked,
                                )
                              }
                              disabled={
                                patchMutation.isPending ||
                                !family.user_controllable
                              }
                            />
                          }
                          label={
                            <Stack
                              direction="row"
                              spacing={0.75}
                              alignItems="center"
                            >
                              <Iconify
                                icon={CHANNEL_ICONS[channel]}
                                width={18}
                              />
                              <Typography variant="body2">
                                {CHANNEL_LABELS[channel]}
                              </Typography>
                            </Stack>
                          }
                        />
                      );
                    })}
                  </Stack>
                </Stack>
              </Box>
            ))}
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: 2.25, borderRadius: 1 }}>
          <Stack spacing={2}>
            <Stack
              direction={{ xs: "column", md: "row" }}
              justifyContent="space-between"
              spacing={2}
            >
              <Box>
                <Typography variant="subtitle1">Workspace channels</Typography>
                <Typography variant="body2" color="text.secondary">
                  Add opt-in Slack or webhook routing for operational alerts.
                </Typography>
              </Box>
              {!canManageWorkspace && (
                <Chip label="Read only" size="small" variant="outlined" />
              )}
            </Stack>

            {channels.length > 0 && (
              <Stack spacing={1}>
                {channels.map((channel) => (
                  <Box
                    key={channel.id}
                    sx={{
                      p: 1.5,
                      border: (theme) => `1px solid ${theme.palette.divider}`,
                      borderRadius: 1,
                    }}
                  >
                    <Stack
                      direction={{ xs: "column", sm: "row" }}
                      justifyContent="space-between"
                      spacing={1.5}
                      alignItems={{ xs: "flex-start", sm: "center" }}
                    >
                      <Stack direction="row" spacing={1.25} alignItems="center">
                        <Iconify
                          icon={
                            channel.type === "slack_webhook"
                              ? "mdi:slack"
                              : "mdi:webhook"
                          }
                          width={20}
                        />
                        <Box>
                          <Typography variant="body2" fontWeight={600}>
                            {channel.display_name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {channel.target_identifier || channel.type}
                          </Typography>
                        </Box>
                      </Stack>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Chip
                          label={channel.is_active ? "Active" : "Disabled"}
                          color={channel.is_active ? "success" : "default"}
                          size="small"
                          variant="outlined"
                        />
                        <IconButton
                          size="small"
                          disabled={
                            !canManageWorkspace || testMutation.isPending
                          }
                          onClick={() => testMutation.mutate(channel.id)}
                          title="Test channel"
                        >
                          <Iconify icon="mdi:send-outline" width={18} />
                        </IconButton>
                      </Stack>
                    </Stack>
                  </Box>
                ))}
              </Stack>
            )}

            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
              <TextField
                label="Slack channel name"
                value={slackName}
                onChange={(event) => setSlackName(event.target.value)}
                size="small"
                fullWidth
                disabled={!canManageWorkspace}
              />
              <TextField
                label="Slack webhook URL"
                value={slackWebhook}
                onChange={(event) => setSlackWebhook(event.target.value)}
                size="small"
                fullWidth
                disabled={!canManageWorkspace}
                type="password"
              />
              <Button
                variant="contained"
                startIcon={<Iconify icon="mdi:plus" />}
                onClick={handleAddSlack}
                disabled={
                  !canManageWorkspace ||
                  !slackWebhook ||
                  patchMutation.isPending
                }
                sx={{ whiteSpace: "nowrap" }}
              >
                Add Slack
              </Button>
            </Stack>
          </Stack>
        </Paper>
      </Stack>
    </Box>
  );
}
