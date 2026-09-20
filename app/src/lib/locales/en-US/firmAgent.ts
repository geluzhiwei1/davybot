/** English (en-US) — firmAgent module strings */
const enUS = {
  // Dock (firm-agent-dock.tsx)
  "dock.open": "Open FirmAgent",
  "dock.title": "FirmAgent Smart Law-Firm Orchestration",
  "dock.contextCurrent": "Current context: {{summary}}",
  "dock.defaultDesc": "Smart law-firm orchestration hub · 7 sub-agents in concert",
  "dock.preparing": "Preparing FirmAgent workspace…",
  "dock.loadFailed": "Failed to load: {{error}}",

  // Fleet badge (firm-agent-fleet-badge.tsx)
  "fleet.ariaLabel": "FirmAgent fleet status",
  "fleet.title": "FirmAgent fleet · {{count}} sub-agents",
  "fleet.dotTitle": "{{name}} · {{status}}",
  "fleet.lastAction": "Last: {{action}}",
  "fleet.summary.thinking": "{{count}} reasoning",
  "fleet.summary.online": "{{active}}/{{total}} online",
  "fleet.summary.ready": "Fleet ready",
  "fleet.status.idle": "Idle",
  "fleet.status.online": "Online",
  "fleet.status.thinking": "Reasoning",
  "fleet.status.tool": "Using tool",
  "fleet.dev.simulateTitle":
    "Fire a firm_agent_status event via the event-bus to verify the monitoring-ws.ts → store → UI chain",
  "fleet.dev.demo": "Demo",
  "fleet.dev.reset": "Reset",
  "fleet.agent.case-agent.name": "Case",
  "fleet.agent.case-agent.role": "Case facts and strategy",
  "fleet.agent.contract-agent.name": "Contract",
  "fleet.agent.contract-agent.role": "Contract review and drafting",
  "fleet.agent.compliance-agent.name": "Compliance",
  "fleet.agent.compliance-agent.role": "Compliance risk identification",
  "fleet.agent.finance-agent.name": "Finance",
  "fleet.agent.finance-agent.role": "Accounting and tax estimation",
  "fleet.agent.research-agent.name": "Research",
  "fleet.agent.research-agent.role": "Precedent and statute research",
  "fleet.agent.sign-agent.name": "Signing",
  "fleet.agent.sign-agent.role": "Signing workflow and archiving",
  "fleet.agent.lead-agent.name": "Leads",
  "fleet.agent.lead-agent.role": "Lead evaluation and marketing",

  // Chat view (firm-agent-chat-view.tsx)
  "chat.orchLabel": "Orchestrate",
  "chat.inputPlaceholder":
    "Instruct FirmAgent… (e.g., prepare a defense brief for the GlobalTech case with 3 similar-case references)",

  // Empty state (firm-agent-empty-state.tsx)
  "empty.title": "FirmAgent fleet is ready",
  "empty.subtitle":
    "Direct FirmAgent to orchestrate 7 sub-agents (Case / Contract / Compliance / Finance / Research / Signing / Leads).",
  "empty.quick": "Quick commands",
  "empty.quick.contract.label": "Draft contract",
  "empty.quick.contract.prompt":
    "Please draft a technology services contract covering acceptance criteria, liability for breach, and IP clauses.",
  "empty.quick.conflict.label": "Conflict check",
  "empty.quick.conflict.prompt":
    "Run a conflict-of-interest check on the current case file and output potential conflicts and recommended measures.",
  "empty.quick.health.label": "Case health",
  "empty.quick.health.prompt":
    "Assess the current case for timeliness, evidence completeness, and risks, and produce a case health report.",
  "empty.quick.defense.label": "Defense brief",
  "empty.quick.defense.prompt":
    "Based on the available materials, draft a defense brief for the GlobalTech case with 3 similar cases attached.",
  "empty.quick.pipeline.label": "Lead analysis",
  "empty.quick.pipeline.prompt":
    "Analyze this month's lead funnel: conversion rates and churn reasons from lead to signed engagement.",
  "empty.quick.precedent.label": "Precedent lookup",
  "empty.quick.precedent.prompt":
    "Find 5 landmark trade-secret infringement cases from the past 3 years, with holdings attached.",
  "empty.hint.input": "Type ",
  "empty.hint.ref": " to reference files, ",
  "empty.hint.skill": " to trigger a skill",

  // Morning briefing (firm-agent-empty-state.tsx)
  "brief.loading": "Fetching today's briefing…",
  "brief.unavailable": "Today's briefing is unavailable; you can issue commands directly.",
  "brief.title": "Today's briefing · {{date}}",
  "brief.deadlineCount": "{{count}} deadlines",
  "brief.deadlineFallback": "Deadline {{index}}",
  "brief.alertCount": "{{count}} alerts need attention ({{first}})",
  "brief.recommendation": "💡 Suggestion: {{text}}",

  // Orchestration panel (firm-agent-orchestration-panel.tsx)
  "orch.tab.jobs": "Job queue",
  "orch.tab.memory": "Firm memory",
  "orch.jobs.empty": "No active jobs",
  "orch.jobs.emptyHint1": "Once you issue an instruction to FirmAgent,",
  "orch.jobs.emptyHint2": "orchestration jobs will appear here in real time.",
  "orch.jobs.totalProgress": "Overall progress",
  "orch.jobs.activeCount": "{{count}} in progress",
  "orch.jobs.completedCount": "{{count}} completed",
  "orch.jobs.totalCount": "{{count}} total",
  "orch.jobs.status.done": "Done",
  "orch.jobs.status.running": "In progress",
  "orch.jobs.status.pending": "Pending",
  "orch.memory.refresh": "Refresh",
  "orch.memory.effective": "Effective",
  "orch.memory.override": "Override",
  "orch.memory.default": "Default",
  "orch.memory.empty": "No memory yet",

  // Artifact card (firm-agent-message-renderer.tsx)
  "artifact.producedBy": "Produced by {{name}}",
  "artifact.status.draft": "Draft",
  "artifact.status.final": "Final",
  "artifact.status.pending_review": "In review",
  "artifact.kind.contract": "Contract",
  "artifact.kind.brief": "Defense brief",
  "artifact.kind.analysis": "Analysis",
  "artifact.kind.memo": "Memo",
  "artifact.kind.research": "Research report",
  "artifact.kind.letter": "Letter",
  "artifact.kind.report": "Report",
  "artifact.kind.other": "Artifact",

  // Workspace (use-firm-agent-workspace.ts)
  "workspace.description": "FirmAgent main workspace (smart law-firm orchestration hub)",
};

export default enUS;
