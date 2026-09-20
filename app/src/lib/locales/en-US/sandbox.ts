/** English (en-US) — sandbox module strings */
const enUS = {
  // Provider selector
  "provider.auto.label": "Auto-detect",
  "provider.auto.description": "Automatically choose the best provider for the environment",
  "provider.subprocess.label": "Process isolation (subprocess)",
  "provider.subprocess.description": "Runs as a child process — best performance but no isolation",
  "provider.docker.label": "Container isolation (Docker/Podman)",
  "provider.docker.description":
    "Docker/Podman container isolation, suited for local multi-user setups",
  "provider.e2b.label": "Hardware isolation (CubeSandbox KVM)",
  "provider.e2b.description":
    "CubeSandbox MicroVM hardware-level isolation, supports self-hosted and cloud",

  // Capabilities badge
  "capabilities.isolation.none": "No isolation",
  "capabilities.isolation.process": "Process-level",
  "capabilities.isolation.container": "Container-level",
  "capabilities.isolation.hardware": "Hardware-level (KVM)",
  "capabilities.coldStart": "Cold start {{ms}}ms",
  "capabilities.timeout": "Timeout {{seconds}}s",

  // Sandbox section
  "section.title": "Sandbox execution environment",
  "section.description": "Configure isolation level and mount policy for the command sandbox",
  "section.currentStatus": "Current status",
  "section.networkPolicy": "Network policy (read-only)",
  "section.advanced": "Advanced settings",
  "section.connectionTest": "Connection test",
  "section.mountMode": "Workspace mount mode",
  "section.detailedSettings": "Detailed sandbox settings →",

  // VirtioFS toggle
  "virtiofs.label": "VirtioFS mount",
  "virtiofs.unavailable":
    "VirtioFS requires the E2B provider; the current provider is incompatible.",
  "virtiofs.localNote":
    "In local deployment mode, VirtioFS is usually unavailable (requires KVM). It has been disabled automatically.",
  "virtiofs.cloudNote":
    "VirtioFS provides high-performance filesystem mounts and is recommended in E2B (KVM) environments.",

  // Provider health indicator
  "health.available": "Healthy",
  "health.unavailable": "Unhealthy",

  // Test button
  "test.button": "Test connection",
  "test.failed": "Test failed",
  "test.success": "Connected",
  "test.error": "Connection failed",

  // Status panel
  "status.uninitialized": "Uninitialized",
  "status.initializing": "Initializing",
  "status.active": "Running",
  "status.paused": "Paused",
  "status.queued": "Queued",
  "status.reconnecting": "Reconnecting",
  "status.destroyed": "Destroyed",
  "status.error": "Error",

  // Mount mode selector
  "mountMode.ro": "Read-only (ro)",
  "mountMode.rw": "Read-write (rw)",
  "mountMode.rwWarning":
    "Read-write mode allows the agent to modify workspace files, which poses security risks. Only enable it if you trust the current agent.",
  "mountMode.roNote":
    "Read-only mode: the agent can read workspace files but cannot modify them — safer.",

  // Command error modal
  "error.RO_MODE_WRITE_DENIED.title": "Workspace is mounted read-only",
  "error.QUOTA_EXCEEDED.title": "Quota exceeded",
  "error.PATH_OUT_OF_ALLOWLIST.title": "Path out of bounds",
  "error.TMPFS_MASK_FAILED.title": "Sandbox failed to start — security check did not pass",
  "error.TRUSTED_CONTEXT_EXPIRED.title": "Session expired, please sign in again",
  "error.NETWORK_DENIED.title": "Network request denied by policy",
  "error.SANDBOX_TIMEOUT.title": "Command execution timed out",
  "error.UNKNOWN.title": "Unknown error",
  "error.defaultTitle": "Error",
  "error.exitCode": "Exit code: {{code}}",
  "error.action.close": "Close",
  "error.action.open_settings": "Go to settings",
  "error.action.contact_admin": "Contact admin",
  "error.action.retry": "Retry",

  // Quota indicator
  "quota.loading": "Loading quota information...",
  "quota.region": "Sandbox quota",
  "quota.sessions": "Sandboxes",
  "quota.memory": "Memory",
  "quota.rate": "Rate (/min)",

  // Network policy viewer
  "policy.loading": "Loading network policy...",
  "policy.defaultDeny": "Deny by default",
  "policy.defaultAllow": "Allow by default",
  "policy.allowedDomains": "Allowed domains",
  "policy.deniedDomains": "Denied domains",

  // Reconnect banner
  "reconnect.expired": "The sandbox was destroyed due to timeout. Please re-run the command.",
  "reconnect.countdown":
    "Connection lost. Reconnect within <strong>{{seconds}}s</strong> to restore sandbox state",
};

export default enUS;
