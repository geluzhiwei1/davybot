/** English (en-US) — chat UI strings */
const enUS = {
  // Follow-up dialog
  "followup.title": "Agent needs confirmation",
  "followup.suggested": "Suggested replies",
  "followup.custom": "Custom reply",
  "followup.placeholder": "Type your reply…",
  "followup.cancel": "Cancel",

  // Message actions
  "messageActions.copied": "Copied",
  "messageActions.copyFailed": "Copy failed",
  "messageActions.mdExported": "Markdown exported",
  "messageActions.exportFailed": "Export failed",
  "messageActions.pdfFailed": "Failed to prepare PDF",
  "messageActions.copyTitle": "Copy",
  "messageActions.exportMd": "Export Markdown",
  "messageActions.exportPdf": "Export PDF",

  // Resource mention picker
  "mention.tab.files": "Files",
  "mention.tab.experts": "Experts",
  "mention.tab.recent": "Recent",
  "mention.search.files": "Search files…",
  "mention.search.experts": "Search experts…",
  "mention.search.recent": "Search recent…",
  "mention.empty.files": "No matching files",
  "mention.empty.experts": "No matching experts",
  "mention.empty.recent": "No recent items",
  "mention.footer.navigate": "↑↓ Navigate",
  "mention.footer.switchTab": "Tab Switch category",
  "mention.footer.select": "↵ Select",
  "mention.footer.close": "Esc Close",
  "mention.file.aiGenerated": "AI generated",
  "mention.file.userUploaded": "User uploaded",
  "mention.time.justNow": "Just now",
  "mention.time.minutesAgo": "{{count}} min ago",
  "mention.time.hoursAgo": "{{count}} hr ago",
  "mention.time.daysAgo": "{{count}} days ago",

  // Slash commands
  "slash.searchPlaceholder": "Search commands…",
  "slash.count": "{{count}} items",
  "slash.noMatch": "No matching commands",
  "slash.footer.navigate": "↑↓ Navigate",
  "slash.footer.select": "↵ Select",
  "slash.footer.close": "Esc Close",
  "slash.cmd.clear": "Clear the current conversation",
  "slash.cmd.reset": "Reset the conversation and start over",
  "slash.cmd.help": "View help and shortcuts",
  "slash.cmd.expert": "Choose a legal expert",
  "slash.cmd.model": "Switch AI model",
  "slash.cmd.summarize": "Summarize the current conversation",
  "slash.cmd.analyze": "Deep-analyze a file or contract",
  "slash.cmd.task": "Create a complex task workflow",
  "slash.cmd.chat": "Switch to chat mode",
  "slash.cmd.review.run": "Start the review pipeline (7 stages / 2 gates)",
  "slash.cmd.paper.status": "Show the paper pipeline tracker",
  "slash.cmd.paper.switch": "Switch paper pipeline stage",
  "slash.cmd.lens.run": "Read a paper PDF (parse → understand → present)",
  "slash.cmd.lens.critique": "Critique a paper PDF (S08)",
  "slash.tag.system": "System",
  "slash.tag.chat": "Chat",
  "slash.tag.settings": "Settings",
  "slash.tag.analysis": "Analysis",
  "slash.tag.advanced": "Advanced",
  "slash.tag.research": "Research",

  // Message component
  "message.exec.status.started": "Starting",
  "message.exec.status.validating": "Validating",
  "message.exec.status.executing": "Executing",
  "message.exec.status.completed": "Completed",
  "message.exec.status.failed": "Failed",
  "message.exec.status.timeout": "Timed out",
  "message.subtask.title": "Subtask",
  "message.subtask.delegate.blocking": "Blocking",
  "message.subtask.delegate.async": "Async delegate",
  "message.subtask.status.pending": "Pending",
  "message.subtask.status.running": "Running",
  "message.subtask.status.completed": "Completed",
  "message.subtask.status.failed": "Failed",
  "message.subtask.status.aborted": "Aborted",
  "message.subtask.viewThread": "View subagent thread",
  "message.subtask.standaloneSession": "Separate session",
  "message.subtaskBatch.title": "Batch subtasks",
  "message.subtaskBatch.count": "{{count}} items",
  "message.subtaskBatch.failed": "{{count}} failed",
  "message.subtaskBatch.allDone": "All done",
  "message.subtaskBatch.partial": "Partially created {{created}}/{{total}} (duplicates/failures in tool result)",
  "message.subtaskReport.title": "Subtask Execution Report",
  "message.subtaskReport.count": "{{count}} subtasks",
  "message.subtaskReport.acceptance": "Acceptance",
  "message.subtaskReport.result": "Result",
  "message.subtaskReport.verdictHint": "Verdict hint",
  "message.agent.default": "Agent",
  "message.thinking": "Thinking...",

  // File upload dialog
  "upload.title": "Upload files",
  "upload.dropzone": "Drag and drop files here to upload",
  "upload.dropzoneHint": "or click to browse · Supports PDF, DOCX, TXT, images, etc.",
  "upload.selectFolder": "Select folder",
  "upload.done": "Done",
  "upload.cancel": "Cancel",
  "upload.uploading": "Uploading…",
  "upload.uploadCount": "Upload {{count}} files",
  "upload.uploaded": "Uploaded {{n}} files",
  "upload.retry": "Retry",
  "upload.refreshFailed": "Failed to refresh file list",

  // Mention text
  "mentionText.fileChip": "File: {{name}}",

  // List page renderer
  "listPage.showing": "Showing {{shown}} of {{total}} items",
  "listPage.nextPage": "offset={{offset}} for next page",
  "listPage.more": "More results available",

  // Blob window renderer
  "blobWindow.omitted": "⸻ {{count}} lines omitted ⸻",
  "blobWindow.showing": "Showing {{shown}} of {{total}} lines",

  // Reasoning content
  "reasoning.title": "Reasoning",
  "reasoning.raw": "Raw",

  // Thinking content
  "thinking.title": "Thinking ({{completed}}/{{total}})",
  "thinking.status.inProgress": "In progress",
  "thinking.status.completed": "Completed",
  "thinking.status.failed": "Failed",

  // Tool call content
  "toolCall.status.started": "Starting",
  "toolCall.status.inProgress": "Running",
  "toolCall.status.completed": "Completed",
  "toolCall.status.failed": "Failed",
  "toolCall.input": "Input",
  "toolCall.output": "Output",
  "toolCall.error": "Error",
  "toolCall.duration": "Took {{seconds}}s",

  // Tool result content
  "toolResult.failed": "Execution failed",
  "toolResult.success": "Execution succeeded",
  "toolResult.expandFull": "Expand full result",
  "toolResult.fullResult": "Full result",
  "toolResult.collapse": "Collapse",
};

export default enUS;
