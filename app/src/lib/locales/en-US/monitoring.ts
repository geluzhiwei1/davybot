/** English (en-US) — monitoring module strings */
const enUS = {
  // System health
  "systemHealth.title": "System Health",
  "systemHealth.waiting": "Waiting for connection...",
  "systemHealth.memory": "Memory",
  "systemHealth.disk": "Disk",
  "systemHealth.networkLatency": "Network Latency",

  // Cost tracker
  "cost.title": "Token & Cost Tracking",
  "cost.waiting": "Waiting for data...",
  "cost.totalTokens": "Total Tokens",
  "cost.totalCost": "Total Cost",
  "cost.inputTokens": "Input Tokens",
  "cost.outputTokens": "Output Tokens",
  "cost.modelBreakdown": "Model Breakdown",

  // Subtask tree
  "subtask.title": "Subtask Delegation",
  "subtask.completedOf": "{{completed}}/{{total}} done",
  "subtask.empty": "No subtasks yet (waiting for new_task delegation…)",
  "subtask.status.pending": "Pending",
  "subtask.status.running": "Running",
  "subtask.status.completed": "Completed",
  "subtask.status.failed": "Failed",
  "subtask.status.aborted": "Aborted",
  "subtask.standaloneThread": "Standalone thread",
  "subtask.viewThread": "View sub-agent thread",
  "subtask.sendSteer": "Send steer command",
  "subtask.confirmAbortTitle": "Click again to confirm abort (cascades to whole subtree)",
  "subtask.confirmAbortShort": "Confirm abort?",
  "subtask.abortTitle": "Abort subtask (cascades to whole subtree)",
  "subtask.abortFailed": "Abort failed",
  "subtask.rerunTitle": "Rerun in place (reset to pending, previous result archived)",
  "subtask.rerunFailed": "Rerun failed",

  // Trace waterfall
  "trace.empty": "No trace data",
  "trace.emptyHint": "Full execution traces will appear here after the agent runs",
  "trace.start": "Start:",
  "trace.end": "End:",
  "trace.input": "Input:",
  "trace.output": "Output:",
  "trace.legend": "Legend:",

  // Todos panel
  "todos.title": "Task List",
  "todos.stats": "{{completed}}/{{total}} done ({{rate}}%)",
  "todos.filter.all": "All",
  "todos.filter.PENDING": "To Do",
  "todos.filter.IN_PROGRESS": "In Progress",
  "todos.filter.COMPLETED": "Completed",
  "todos.empty": "No tasks",

  // Task graph
  "taskGraph.empty": "Select an execution to view the task graph",
  "taskGraph.completedOf": "{{completed}}/{{total}} done",
  "taskGraph.done": "Done",
  "taskGraph.failed": "Failed",

  // Alert system
  "alert.title": "Alerts",
  "alert.unacknowledged": "({{count}} unacknowledged)",
  "alert.empty": "No alerts",

  // Agent profiles
  "profile.title": "Agent Profile Registry",
  "profile.counts": "Built-in {{builtin}} · Custom {{custom}}",
  "profile.refresh": "Refresh",
  "profile.refreshTitle": "Refresh the profile registry",
  "profile.noWorkspace": "Not connected to a workspace",
  "profile.loading": "Loading profiles…",
  "profile.empty":
    "No agent profiles in this workspace (built-in default/worker/explorer should be visible)",
  "profile.loadFailed": "Failed to load the profile registry",
  "profile.builtin": "Built-in",
  "profile.custom": "Custom",
  "profile.subtasks": "Subtasks ×{{count}}",

  // Log viewer
  "log.title": "Logs",
  "log.autoScroll": "Auto Scroll",
  "log.manual": "Manual",
  "log.all": "All",
  "log.empty": "No logs",

  // Agents overview
  "agents.title": "Parallel Tasks",
  "agents.active": "Active: {{count}}",
  "agents.completed": "Completed: {{count}}",
  "agents.failed": "Failed: {{count}}",
  "agents.empty": "No active tasks",
};

export default enUS;
