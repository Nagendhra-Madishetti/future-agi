export const ROLE_OPTIONS = [
  { label: "Owner", value: "Owner" },
  { label: "Admin", value: "Admin" },
  { label: "Member", value: "Member" },
  {
    label: "Viewer",
    value: "Viewer",
  },
  {
    label: "Workspace Admin",
    value: "workspace_admin",
  },
  {
    label: "Workspace Member",
    value: "workspace_member",
  },
  {
    label: "Workspace Viewer",
    value: "workspace_viewer",
  },
];

export const AVAILABLE_ROLES = [
  {
    label: "Data Scientist / ML Engineer",
    value: "Data Scientist / ML Engineer",
  },
  {
    label: "Backend / Platform Engineer / DevOps",
    value: "Backend / Platform Engineer / DevOps",
  },
  { label: "Subject Matter Expert", value: "Subject Matter Expert" },
  { label: "Product Manager / Analyst", value: "Product Manager / Analyst" },
  {
    label: "Customer Success / Business / Operations Manager",
    value: "Customer Success / Business / Operations Manager",
  },
];

export const GOALS_LIST = [
  {
    id: "explore_sample_data",
    label: "Explore with sample data",
    aliases: ["sample_project"],
    description: "Review a sample quality signal before connecting real data.",
  },
  {
    id: "monitor_production_ai_app",
    label: "Monitor a production AI app",
    aliases: ["Monitor LLMs and Agents", "Analyze System Health"],
    description:
      "Connect traces and review latency, cost, failures, and quality signals.",
  },
  {
    id: "improve_prompts",
    label: "Test and improve prompts",
    aliases: ["test_and_improve_prompts"],
    description: "Create a prompt test loop and compare output changes.",
  },
  {
    id: "build_ai_agent",
    label: "Build or prototype an AI agent",
    aliases: ["build_or_prototype_agent", "Optimize AI Agents"],
    description: "Run a first scenario and inspect the agent trace.",
  },
  {
    id: "control_model_traffic",
    label: "Route LLM traffic safely",
    aliases: ["route_llm_traffic_safely"],
    description: "Send a gateway request and review the first log.",
  },
  {
    id: "evaluate_quality",
    label: "Evaluate quality on data or traces",
    aliases: [
      "evaluate_quality_on_data_or_traces",
      "Run Evaluations",
      "Annotate and Improve Data",
    ],
    description: "Create a small eval and review the first failure.",
  },
  {
    id: "connect_voice_ai_agent",
    label: "Connect a voice AI agent",
    aliases: ["Simulate Voice or Chat Interactions"],
    description: "Run or review a call with clear success criteria.",
  },
];
export const DEFAULT_ROLES = [
  "Data Scientist / ML Engineer",
  "Backend / Platform Engineer / DevOps",
  "Subject Matter Expert",
  "Product Manager / Analyst",
  "Customer Success / Business / Operations Manager",
];
