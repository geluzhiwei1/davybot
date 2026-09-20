/** English (en-US) — socialAgent module strings(SocialAgent, mirrors marketAgent) */
const enUS = {
  // Redirect shell(routes/social/agent.tsx)
  "shell.entering": "Entering SocialAgent…",
  "shell.initFailed": "Failed to initialize SocialAgent workspace",

  // Dock(social-agent-dock.tsx)
  "dock.open": "Open SocialAgent",
  "dock.title": "SocialAgent — social orchestration",
  "dock.contextCurrent": "Context: {{summary}}",
  "dock.defaultDesc": "Social orchestration hub · 6 specialist agents",
  "dock.preparing": "Preparing SocialAgent workspace…",
  "dock.loadFailed": "Load failed: {{error}}",

  // Fleet badge(social-agent-fleet-badge.tsx)
  "fleet.ariaLabel": "SocialAgent fleet status",
  "fleet.title": "SocialAgent fleet · {{count}} agents",
  "fleet.dotTitle": "{{name}} · {{status}}",
  "fleet.lastAction": "Last: {{action}}",
  "fleet.summary.thinking": "{{count}} thinking",
  "fleet.summary.online": "{{active}}/{{total}} online",
  "fleet.summary.ready": "Fleet ready",
  "fleet.status.idle": "Idle",
  "fleet.status.online": "Online",
  "fleet.status.thinking": "Thinking",
  "fleet.status.tool": "Tool call",
  "fleet.dev.simulateTitle":
    "Emit social_agent_status via event-bus to verify monitoring-ws → store → UI chain",
  "fleet.dev.demo": "Demo",
  "fleet.dev.reset": "Reset",
  "fleet.agent.soc-trending-agent.name": "Trending",
  "fleet.agent.soc-trending-agent.role": "Daily trends & topic calls",
  "fleet.agent.soc-geo-agent.name": "GEO Scout",
  "fleet.agent.soc-geo-agent.role": "Social content GEO visibility",
  "fleet.agent.soc-analytics-agent.name": "Analytics",
  "fleet.agent.soc-analytics-agent.role": "Content & account performance",
  "fleet.agent.soc-drafter-agent.name": "Drafter",
  "fleet.agent.soc-drafter-agent.role": "One-source multi-platform drafts",
  "fleet.agent.soc-schedule-agent.name": "Scheduler",
  "fleet.agent.soc-schedule-agent.role": "Calendar & publishing cadence",
  "fleet.agent.soc-approvals-agent.name": "Approver",
  "fleet.agent.soc-approvals-agent.role": "Approval queue & compliance",

  "chips.srLabel": "Ask SocialAgent",

  // ChatView(social-agent-chat-view.tsx)
  "chat.orchLabel": "Orchestration",
  "chat.inputPlaceholder": "Command SocialAgent…",

  // E2 panel(social-agent-orchestration-panel.tsx)
  "panel.nodes.title": "Task nodes",
  "panel.nodes.empty": "No running tasks",
  "panel.nodes.running": "Running",
  "panel.context.title": "Social context",
  "panel.context.brand": "Current brand: {{name}}",
  "panel.context.allBrands": "All brands",
  "panel.context.brandHint":
    "Creation & queries filter by the current brand; switch it in the sidebar Brands row.",
  "panel.llm.title": "Model",
  "panel.llm.gatewayNote":
    "Chat model runs via the platform gateway (llm-pricing catalog, user credits) — no local LLM setup. Terminal actions (publish/approve) go through the social control-plane pages; the human is the merger.",

  // Artifact card(social-agent-message-renderer.tsx)
  "artifact.kind.trending": "Trending",
  "artifact.kind.geo": "GEO",
  "artifact.kind.insight": "Insight",
  "artifact.kind.draft": "Draft",
  "artifact.kind.content": "Content",
  "artifact.kind.schedule": "Schedule",
  "artifact.kind.approval": "Approval",
  "artifact.kind.account": "Account",
  "artifact.kind.other": "Artifact",
  "artifact.producedBy": "By {{name}}",
  "artifact.needsReview": "needs review",

  // Empty state(social-agent-empty-state.tsx)
  "empty.subtitle":
    "Your AI social-media partner — state a goal; it decomposes, routes the fleet, calls module tools, and delivers",
  "empty.quick.trending.label": "Today's trends",
  "empty.quick.trending.hint": "Topics & whether to join",
  "empty.quick.trending.prompt":
    "What platform trends relate to our brand today? Which are worth joining, and from what angle?",
  "empty.quick.geo.label": "GEO check",
  "empty.quick.geo.hint": "Content visibility",
  "empty.quick.geo.prompt":
    "How is the GEO visibility of our social content? Which topics get cited in AI answers, which don't?",
  "empty.quick.analytics.label": "Performance",
  "empty.quick.analytics.hint": "Data insights",
  "empty.quick.analytics.prompt":
    "How did our recent posts perform? Give me insights and improvements by platform and content type.",
  "empty.quick.draft.label": "Multi-platform",
  "empty.quick.draft.hint": "One source, many drafts",
  "empty.quick.draft.prompt":
    "Draft posts for Xiaohongshu, WeChat MP and Weibo around a recent brand topic.",
  "empty.quick.calendar.label": "Calendar",
  "empty.quick.calendar.hint": "Publishing schedule",
  "empty.quick.calendar.prompt":
    "How does the publishing calendar look? Any gaps or conflicts? Give me cadence advice.",
  "empty.quick.approvals.label": "Approvals",
  "empty.quick.approvals.hint": "Alignment & risk",
  "empty.quick.approvals.prompt":
    "What's pending in the approval center? Which items carry compliance risk? Suggest handling.",
};

export default enUS;
