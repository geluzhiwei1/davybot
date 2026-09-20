/** English (en-US) — IP module strings */
const enUS = {
  // Module labels
  "module.ideaVault": "Idea Vault",
  "module.disclosure": "Disclosure",
  "module.draft": "Patent Drafting",
  "module.application": "Patent Application",
  "module.filing": "Filing Manager",
  "module.oaReply": "OA Reply",
  "module.reverseDetection": "Reverse Infringement Detection",
  "module.portfolio": "Portfolio Dashboard",
  "module.trademark": "Trademark Registration",

  // Short labels (extra panel toggle)
  "shortLabel.oaReply": "Strategy",
  "shortLabel.reverseDetection": "Detection",
  "shortLabel.trademark": "Workflow",

  // Input placeholders per module
  "placeholder.ip-idea-vault":
    "Describe your technical solution — the AI will assess novelty and patentability...",
  "placeholder.ip-disclosure":
    "Enter the invention title and technical field, or upload materials provided by the inventor...",
  "placeholder.ip-draft":
    "Describe the technical features to protect, or paste the disclosure content...",
  "placeholder.ip-application":
    "Select the filing country/region to generate patent application documents from an existing draft...",
  "placeholder.ip-filing":
    "Enter the target filing countries/regions — the AI will generate a filing checklist and timeline...",
  "placeholder.ip-oa-reply":
    "Upload the Office Action — the AI will parse the grounds for rejection and draft response strategies...",
  "placeholder.ip-reverse-detection":
    "Enter your patent number or technical description to detect potential infringement in the market...",
  "placeholder.ip-portfolio":
    "Enter a company name or patent number — the AI will analyze the patent portfolio...",
  "placeholder.ip-trademark":
    "Enter the trademark name and goods/services class — the AI will generate a registration plan...",

  // PDCA phases
  "phase.idle": "Idle",
  "phase.plan": "Plan",
  "phase.do": "Do",
  "phase.check": "Check",
  "phase.act": "Act",
  "phase.completed": "Completed",
  "phase.error": "Error",

  // PDCA progress ring
  "pdca.plan": "Strategic Planning",
  "pdca.do": "Drafting",
  "pdca.check": "Compliance Check",
  "pdca.act": "Refinement",
  "pdca.plan.short": "Plan",
  "pdca.do.short": "Do",
  "pdca.check.short": "Check",
  "pdca.act.short": "Act",
  "pdca.waiting": "Waiting to start",

  // Workspace list
  "list.searchPlaceholder": "Enter search keywords...",
  "list.loadFailed": "Failed to load",
  "list.createFailed": "Failed to create",
  "list.newName": "{{module}} — New",
  "list.refresh": "Refresh",
  "list.new": "New {{module}}",
  "list.selectTemplate": "Select a {{module}} template",
  "list.reuseParams": "Copy parameters from an existing workspace",
  "list.cancel": "Cancel",
  "list.reuseLoaded":
    "Reused parameters loaded ({{count}} fields) — you can edit them after selecting a template",
  "list.noTemplates": "No templates available",
  "list.retry": "Retry",
  "list.noWorkspaces": "No {{module}} workspaces yet",
  "list.createFirst": "Create your first",
  "list.deleteTitle": "Delete workspace?",
  "list.deleteDesc": 'You are about to delete "{{name}}". This action cannot be undone.',
  "list.deleteConfirm": "Delete workspace",
  "list.filesCount": "{{count}} files",
  "list.createdAt": "Created {{date}}",
  "list.remaining": "{{hours}}h left",
  "list.score": "{{score}} pts",
  "list.open": "Open",
  "list.archive": "Archive",
  "list.delete": "Delete",

  // Template form
  "form.selectPlaceholder": "Please select",
  "form.inheritUpstream": "Inherit from upstream draft",
  "form.selectUpstreamPlaceholder": "Select an upstream patent draft workspace...",
  "form.optionalFields": "Optional fields ({{count}})",
  "form.genericCountry": "Generic",
  "form.creating": "Creating...",
  "form.createWorkspace": "Create workspace",
  "form.skipping": "Redirecting...",
  "form.skipToChat": "Skip and chat directly",

  // Cross-module dashboard
  "dash.title": "IP Workspace",
  "dash.subtitle": "Cross-module summary",
  "dash.refresh": "Refresh",
  "dash.loadFailed": "Failed to load",
  "dash.total": "Total workspaces",
  "dash.completed": "Completed",
  "dash.running": "In progress",
  "dash.errors": "Errors",
  "dash.pending": "{{count}} pending",
  "dash.noWorkspaces": "No workspaces",

  // Portfolio dashboard
  "portfolio.loading": "Loading asset data...",
  "portfolio.title": "Portfolio Dashboard",
  "portfolio.dataFrom": "Aggregated from {{count}} workspaces",
  "portfolio.refresh": "Refresh",
  "portfolio.patentTotal": "Total patents",
  "portfolio.granted": "Granted",
  "portfolio.trademarkTotal": "Total trademarks",
  "portfolio.newThisYear": "New this year",
  "portfolio.health": "Portfolio health",
  "portfolio.modules": "Module distribution",
  "portfolio.recent": "Recently active workspaces ({{count}})",
  "portfolio.empty": "No IP asset data yet",
  "portfolio.emptyDesc": "Create tasks in the IP modules and their data will be aggregated here",

  // Reverse detection page
  "reverse.patent": "Patent",
  "reverse.trademark": "Trademark",
  "reverse.newName": "Reverse Infringement Detection — {{type}}",
  "reverse.title": "Reverse Infringement Detection",
  "reverse.refresh": "Refresh",
  "reverse.newDetection": "New detection",
  "reverse.tab.reverse": "Reverse Detection",
  "reverse.tab.trademark": "Trademark Enforcement",
  "reverse.tab.alerts": "Alert Center",
  "reverse.noPatent": "No reverse detection tasks yet",
  "reverse.noPatentDesc":
    "Enter your patent number or technical description to detect infringing products on the market",
  "reverse.newPatent": "New reverse detection",
  "reverse.noTrademark": "No trademark enforcement tasks yet",
  "reverse.noTrademarkDesc":
    "Enter your trademark name to monitor the market for similar or infringing marks",
  "reverse.newTrademark": "New trademark monitoring",
  "reverse.noAlerts": "No alerts",
  "reverse.noAlertsDesc": "Infringement alerts will appear here once detection tasks run",
  "reverse.createdAt": "Created {{date}}",
  "reverse.score": "{{score}} pts",
  "reverse.viewDetail": "View details",
  "reverse.highRisk": "High risk",
  "reverse.mediumRisk": "Medium risk",

  // Special panel
  "panel.defaultTitle": "{{module}} details panel",
  "panel.defaultDesc": "Data will be generated after the task runs",
  "panel.innovationTitle": "Innovation Assessment",
  "panel.innovationEmpty": "Innovation points will appear here after you start the conversation",
  "panel.priorArt": "Prior Art Comparison",
  "panel.relevance.high": "Highly relevant",
  "panel.relevance.medium": "Moderately relevant",
  "panel.relevance.low": "Marginally relevant",
  "panel.sectionsTitle": "Disclosure Sections",
  "panel.sectionsDone": "{{done}}/{{total}} completed",
  "panel.section.title": "Title of Invention",
  "panel.section.field": "Technical Field",
  "panel.section.background": "Background",
  "panel.section.summary": "Summary of Invention",
  "panel.section.figures": "Brief Description of Drawings",
  "panel.section.embodiments": "Detailed Embodiments",
  "panel.claimsTree": "Claims Tree",
  "panel.claimsEmpty": "Claims will appear here once drafting begins",
  "panel.complianceIssues": "Compliance Issues",
  "panel.severity.high": "Critical",
  "panel.severity.warning": "Warning",
  "panel.strategyTitle": "Strategy Comparison",
  "panel.strategyEmpty": "Response strategies will appear here after the OA is analyzed",
  "panel.strategyName": "Option {{letter}}: {{name}}",
  "panel.successRate": "{{rate}}% success rate",
  "panel.scope": "Scope {{stars}}",
  "panel.contrastDocs": "Contrasting Document Summaries",
  "panel.monitorTitle": "Monitoring Dashboard",
  "panel.monitorTasks": "Monitor tasks ({{count}})",
  "panel.active": "Active",
  "panel.paused": "Paused",
  "panel.patentMonitor": "Patent monitoring",
  "panel.trademarkMonitor": "Trademark monitoring",
  "panel.alertsTitle": "Alerts ({{count}})",
  "panel.monitorEmpty": "Data will appear here after monitor tasks are created",
  "panel.trademarkTitle": "Trademark Registration Process",
  "panel.trademarkStep.search": "Trademark Search",
  "panel.trademarkStep.classify": "Class Selection",
  "panel.trademarkStep.draft": "Application Preparation",
  "panel.trademarkStep.file": "File Application",
  "panel.trademarkStep.review": "Formality Examination",
  "panel.trademarkStep.publish": "Publication Period",
  "panel.trademarkStep.register": "Registered",

  // Message renderer cards
  "msg.innovation": "Innovation Assessment",
  "msg.evaluating": "Evaluating...",
  "msg.claimsTree": "Claims Tree",
  "msg.complianceIssues": "Compliance Issues ({{count}})",
  "msg.severity.high": "High",
  "msg.severity.medium": "Med",
  "msg.severity.low": "Low",
  "msg.strategy": "Strategy Comparison",
  "msg.strategyName": "Option {{letter}}: {{name}}",
  "msg.successRate": "{{rate}}% success rate",
  "msg.scope": "Scope {{stars}}",
  "msg.classification": "Classification Results",
  "msg.unknownSection": "Unknown section",
  "msg.disclosureSection": "Disclosure · {{section}}",
  "msg.monitorAlerts": "Monitor Alerts ({{count}})",

  // Agent progress
  "agent.errorTitle": "Task execution failed",
  "agent.retry": "Retry",
  "agent.running": "Agent running",
  "agent.done": "Agent completed",
  "agent.phase": "Phase: {{phase}}",
  "agent.toolCalls": "Tool calls",

  // Claims tree
  "claims.empty": "No claims yet",

  // Compliance issue list
  "compliance.allPassed": "All compliance checks passed",
  "compliance.error": "Error",
  "compliance.warning": "Warning",
  "compliance.claim": "Claim {{number}}",
  "compliance.suggestion": "Suggestion: {{suggestion}}",

  // Checkpoint list
  "workspace.checkpoints": "Checkpoints",
  "checkpoint.empty": "No checkpoints yet",
  "checkpoint.progress": "Progress",

  // Resume dialog
  "resume.title": "Resume task",
  "resume.desc": "This task has unsaved progress from its last interruption.",
  "resume.module": "Module:",
  "resume.task": "Task:",
  "resume.phase": "Phase:",
  "resume.progress": "Progress:",
  "resume.lastCheckpoint": "Last saved checkpoint",
  "resume.discard": "Discard and start over",
  "resume.continue": "Continue from last checkpoint",

  // Status badges
  "status.draft": "Draft",
  "status.evaluating": "Evaluating",
  "status.evaluated": "Evaluated",
  "status.patentable": "Patentable",
  "status.notPatentable": "Not patentable",
  "status.generating": "Generating",
  "status.review": "Pending review",
  "status.complete": "Complete",
  "status.generatingClaims": "Drafting claims",
  "status.generatingSpec": "Drafting specification",
  "status.complianceCheck": "Compliance check",
};

export default enUS;
