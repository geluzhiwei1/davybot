/**
 * SecurityPolicyForm — structured two-level (user / workspace) security policy editor.
 *
 * Phase 4 (P4) frontend. Covers the command + sandbox domains via the existing
 * backend APIs (securityApi for workspace, usersSecurityApi for user). override-or-inherit:
 * user level is the default; the workspace may freely override any field.
 *
 * Reused by:
 *  - WorkspaceSettingsDrawer → Security tab (scope="workspace")
 *  - UserSettingsDrawer      → Security tab (scope="user")
 *
 * Replaces the former "raw JSON dump" (workspace) and empty placeholder (user).
 */
import { useCallback, useEffect, useState } from "react";
import {
  RefreshCw,
  RotateCcw,
  Save,
  Plus,
  X,
  Zap,
  Loader2,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { securityApi, usersSecurityApi } from "@/lib/api/infra";
import { sandboxTestApi } from "@/lib/api/sandbox";
import type { ProviderType } from "@/lib/types/sandbox";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import type { UserSecuritySettings, WorkspaceSecuritySettings } from "@/lib/types/api";

type Scope = "user" | "workspace";
type SecuritySettings = UserSecuritySettings | WorkspaceSecuritySettings;

// ─── Platform-specific default blacklist ─────────────────────────────────────

type Platform = "linux" | "windows" | "macos";

/** Per-OS default dangerous commands — mutually exclusive sets. */
const PLATFORM_BLACKLISTS: Record<Platform, string[]> = {
  linux: [
    // 系统电源
    "reboot",
    "shutdown",
    "halt",
    "poweroff",
    "init",
    // 用户/权限管理
    "userdel",
    "useradd",
    "usermod",
    "passwd",
    "chpasswd",
    "visudo",
    // 磁盘分区
    "fdisk",
    "parted",
    "cfdisk",
    // 防火墙
    "iptables",
    "ufw",
    "firewall-cmd",
    // 持久化/定时任务
    "crontab",
    "at",
    "systemctl",
    // 内核模块
    "modprobe",
    "rmmod",
    "insmod",
  ],
  windows: [
    // 系统电源
    "shutdown",
    "restart",
    // 磁盘/文件系统
    "format",
    "diskpart",
    "chkdsk",
    "bcdedit",
    // 注册表
    "reg",
    "regedit",
    "regsvr32",
    // 服务/计划任务
    "sc",
    "schtasks",
    "net",
    "dism",
    // 权限/安全
    "takeown",
    "icacls",
    "cipher",
    // WMI / 系统管理
    "wmic",
    "powercfg",
    "runas",
  ],
  macos: [
    // 系统电源
    "shutdown",
    "halt",
    "reboot",
    // 用户/权限管理
    "dscl",
    "dseditgroup",
    "pwpolicy",
    // 磁盘
    "diskutil",
    // 防火墙
    "pfctl",
    // 持久化/定时任务
    "launchctl",
    "cron",
    "at",
    // 内核扩展
    "kextload",
    "kextunload",
    // 系统/固件
    "nvram",
    "csrutil",
  ],
};

const PLATFORM_LABELS: Record<Platform, string> = {
  linux: "Linux",
  windows: "Windows",
  macos: "macOS",
};

/** Detect current platform via navigator; fall back to "linux". */
function detectPlatform(): Platform {
  if (typeof navigator === "undefined") return "linux";
  const ua = (navigator.userAgent || "").toLowerCase();
  const platform = (navigator.platform || "").toLowerCase();
  if (ua.includes("win") || platform.includes("win")) return "windows";
  if (ua.includes("mac") || platform.includes("mac")) return "macos";
  return "linux";
}

const DETECTED_PLATFORM = detectPlatform();
const DEFAULT_BLACKLIST = PLATFORM_BLACKLISTS[DETECTED_PLATFORM];

/** Defaults shown before the server responds / after reset. camelCase to match the API. */
const DEFAULTS: SecuritySettings = {
  enableCommandWhitelist: false,
  allowedSources: ["system"],
  customAllowedCommands: [],
  customDeniedCommands: DEFAULT_BLACKLIST,
  allowShellCommands: false,
  allowBackgroundCommands: false,
  allowPipeCommands: false,
  commandExecutionTimeout: 30,
  enableSandbox: false,
  containerRuntime: "auto",
  sandboxDisableNetwork: true,
  dropAllCapabilities: true,
  noNewPrivileges: true,
  // approval (P2.2 human-in-the-loop)
  approvalEnabled: false,
  approvalRequiredForRisk: "critical",
  approvalTimeoutSeconds: 120,
  approvalNoChannelBehavior: "allow",
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function SectionTitle({ title, desc }: { title: string; desc: string }) {
  return (
    <div>
      <h3 className="text-sm font-medium">{title}</h3>
      <p className="text-[11px] text-muted-foreground mt-0.5">{desc}</p>
    </div>
  );
}

function FieldRow({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-1.5">
      <div className="min-w-0">
        <Label className="text-xs text-foreground">{label}</Label>
        {hint && <p className="text-[11px] text-muted-foreground mt-0.5">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

// ─── Command List Tag Editor ──────────────────────────────────────────────────

interface CommandListEditorProps {
  value: string[];
  onChange: (val: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
}

function CommandListEditor({ value, onChange, disabled, placeholder }: CommandListEditorProps) {
  const [input, setInput] = useState("");

  const add = useCallback(
    (cmd: string) => {
      const trimmed = cmd.trim();
      if (trimmed && !value.includes(trimmed)) {
        onChange([...value, trimmed]);
      }
      setInput("");
    },
    [value, onChange],
  );

  const remove = useCallback(
    (cmd: string) => {
      onChange(value.filter((c) => c !== cmd));
    },
    [value, onChange],
  );

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap gap-1 min-h-[24px]">
        {value.map((cmd) => (
          <span
            key={cmd}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted text-xs"
          >
            {cmd}
            {!disabled && (
              <button onClick={() => remove(cmd)} className="hover:text-destructive" type="button">
                <X className="w-3 h-3" />
              </button>
            )}
          </span>
        ))}
      </div>
      {!disabled && (
        <div className="flex gap-1">
          <Input
            className="h-7 text-xs"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add(input);
              }
            }}
            placeholder={placeholder}
          />
          <Button
            size="sm"
            variant="outline"
            className="h-7 px-2"
            onClick={() => add(input)}
            type="button"
          >
            <Plus className="w-3 h-3" />
          </Button>
        </div>
      )}
    </div>
  );
}

// ─── Main Form ────────────────────────────────────────────────────────────────

export interface SecurityPolicyFormProps {
  scope: Scope;
  /** Required when scope === "workspace". */
  workspaceId?: string;
}

export function SecurityPolicyForm({ scope, workspaceId }: SecurityPolicyFormProps) {
  const { t } = useTranslation("miscUi");
  const [settings, setSettings] = useState<SecuritySettings>({ ...DEFAULTS });
  const [loaded, setLoaded] = useState<SecuritySettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [apiUnavailable, setApiUnavailable] = useState(false);
  // Sandbox test state
  const [sandboxTestStatus, setSandboxTestStatus] = useState<
    "idle" | "testing" | "passed" | "failed"
  >("idle");
  const [sandboxTestError, setSandboxTestError] = useState<string | null>(null);
  const [sandboxTestLatency, setSandboxTestLatency] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (scope === "workspace" && !workspaceId) return;
    setLoading(true);
    try {
      const res =
        scope === "user"
          ? await usersSecurityApi.get()
          : await securityApi.get(workspaceId as string);
      const merged = { ...DEFAULTS, ...(res.settings ?? {}) } as SecuritySettings;
      setSettings(merged);
      setLoaded(merged);
      setApiUnavailable(false);
    } catch {
      if (scope === "user") {
        setApiUnavailable(true);
      } else {
        toast.error(t("security.loadFailed"));
      }
    } finally {
      setLoading(false);
    }
  }, [scope, workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  const set = (key: string, value: unknown) => setSettings((prev) => ({ ...prev, [key]: value }));

  // Sandbox test handlers — changing sandbox config resets test status
  const handleSandboxToggle = (v: boolean) => {
    set("enableSandbox", v);
    setSandboxTestStatus("idle");
  };

  const handleRuntimeChange = (v: string) => {
    set("containerRuntime", v);
    setSandboxTestStatus("idle");
  };

  const handleSandboxTest = async () => {
    setSandboxTestStatus("testing");
    setSandboxTestError(null);
    try {
      const provider = String(settings.containerRuntime ?? "auto") as ProviderType;
      const res = await sandboxTestApi.testConnection(provider);
      if (res.result.ok) {
        setSandboxTestStatus("passed");
        setSandboxTestLatency(res.result.latency_ms ?? null);
      } else {
        setSandboxTestStatus("failed");
        setSandboxTestError(res.result.error ?? t("security.unknownError"));
      }
    } catch (e) {
      setSandboxTestStatus("failed");
      setSandboxTestError(e instanceof Error ? e.message : t("security.testFailed"));
    }
  };

  const dirty = loaded ? JSON.stringify(loaded) !== JSON.stringify(settings) : false;
  // Save is blocked when sandbox is enabled but test hasn't passed
  const sandboxSaveBlocked = !!settings.enableSandbox && sandboxTestStatus !== "passed";

  const save = async () => {
    setSaving(true);
    try {
      const payload = settings as unknown as Record<string, unknown>;
      if (scope === "user") {
        await usersSecurityApi.update(payload);
      } else {
        await securityApi.update(workspaceId as string, payload);
      }
      setLoaded({ ...settings });
      toast.success(scope === "user" ? t("security.savedUser") : t("security.savedWorkspace"));
    } catch {
      toast.error(t("security.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    try {
      if (scope === "user") {
        await usersSecurityApi.reset();
      } else {
        await securityApi.reset(workspaceId as string);
      }
      toast.success(t("security.resetDone"));
      load();
    } catch {
      toast.error(t("security.resetFailed"));
    }
  };

  if (apiUnavailable) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
          <RefreshCw className="w-5 h-5 text-muted-foreground" />
        </div>
        <h3 className="text-sm font-medium text-foreground mb-1">{t("security.devTitle")}</h3>
        <p className="text-xs text-muted-foreground max-w-xs">{t("security.devDesc")}</p>
      </div>
    );
  }

  const enabled = !!settings.enableCommandWhitelist;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionTitle
          title={scope === "user" ? t("security.titleUser") : t("security.titleWorkspace")}
          desc={scope === "user" ? t("security.descUser") : t("security.descWorkspace")}
        />
        <Button size="sm" variant="ghost" onClick={load} disabled={loading} className="h-7">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>

      {/* Command execution */}
      <div className="rounded-lg border border-border/60 p-3 space-y-0.5">
        <div className="text-xs font-medium text-muted-foreground mb-1">
          {t("security.commandSection")}
        </div>

        <FieldRow label={t("security.whitelist")} hint={t("security.whitelistHint")}>
          <Switch
            checked={!!settings.enableCommandWhitelist}
            onCheckedChange={(v) => set("enableCommandWhitelist", v)}
          />
        </FieldRow>

        <FieldRow label={t("security.allowedSources")} hint={t("security.allowedSourcesHint")}>
          <div className="flex gap-2">
            <label className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={settings.allowedSources?.includes("system") ?? true}
                onChange={(e) => {
                  const sources = settings.allowedSources ?? ["system"];
                  const next = e.target.checked
                    ? [...sources.filter((s) => s !== "system"), "system"]
                    : sources.filter((s) => s !== "system");
                  set("allowedSources", next.length ? next : ["custom"]);
                }}
                disabled={!enabled}
              />
              {t("security.sourceSystem")}
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={settings.allowedSources?.includes("custom") ?? false}
                onChange={(e) => {
                  const sources = settings.allowedSources ?? ["system"];
                  const next = e.target.checked
                    ? [...sources.filter((s) => s !== "custom"), "custom"]
                    : sources.filter((s) => s !== "system");
                  set("allowedSources", next.length ? next : ["system"]);
                }}
                disabled={!enabled}
              />
              {t("security.sourceCustom")}
            </label>
          </div>
        </FieldRow>

        {settings.allowedSources?.includes("custom") && (
          <FieldRow label={t("security.customAllowed")} hint={t("security.customAllowedHint")}>
            <CommandListEditor
              value={settings.customAllowedCommands ?? []}
              onChange={(v) => set("customAllowedCommands", v)}
              disabled={!enabled}
              placeholder={t("security.cmdPlaceholder")}
            />
          </FieldRow>
        )}

        <div className="py-1.5">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <Label className="text-xs text-foreground">{t("security.customDenied")}</Label>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                {t("security.customDeniedHint", {
                  platform: PLATFORM_LABELS[DETECTED_PLATFORM],
                  count: DEFAULT_BLACKLIST.length,
                })}
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs shrink-0"
              disabled={!enabled}
              onClick={() => set("customDeniedCommands", [...DEFAULT_BLACKLIST])}
              type="button"
            >
              <RotateCcw className="w-3 h-3 mr-1" /> {t("security.restoreDefaults")}
            </Button>
          </div>
          <div className="mt-1.5">
            <CommandListEditor
              value={settings.customDeniedCommands ?? []}
              onChange={(v) => set("customDeniedCommands", v)}
              disabled={!enabled}
              placeholder={t("security.cmdPlaceholder")}
            />
          </div>
          {/* Collapsible default list reference */}
          <details className="mt-1.5">
            <summary className="text-[11px] text-muted-foreground cursor-pointer hover:text-foreground select-none">
              {t("security.viewDefaultList", {
                platform: PLATFORM_LABELS[DETECTED_PLATFORM],
                count: DEFAULT_BLACKLIST.length,
              })}
            </summary>
            <div className="flex flex-wrap gap-1 mt-1.5 p-2 rounded bg-muted/30">
              {DEFAULT_BLACKLIST.map((cmd) => (
                <span key={cmd} className="px-1.5 py-0.5 rounded bg-muted text-[11px] font-mono">
                  {cmd}
                </span>
              ))}
            </div>
          </details>
        </div>

        <FieldRow label={t("security.shellCommands")} hint={t("security.shellHint")}>
          <Switch
            checked={!!settings.allowShellCommands}
            onCheckedChange={(v) => set("allowShellCommands", v)}
          />
        </FieldRow>

        <FieldRow label={t("security.backgroundCommands")} hint={t("security.backgroundHint")}>
          <Switch
            checked={!!settings.allowBackgroundCommands}
            onCheckedChange={(v) => set("allowBackgroundCommands", v)}
          />
        </FieldRow>

        <FieldRow label={t("security.pipeCommands")} hint={t("security.pipeHint")}>
          <Switch
            checked={!!settings.allowPipeCommands}
            onCheckedChange={(v) => set("allowPipeCommands", v)}
          />
        </FieldRow>

        <FieldRow label={t("security.timeout")}>
          <Input
            type="number"
            min={1}
            max={3600}
            value={Number(settings.commandExecutionTimeout ?? 30)}
            onChange={(e) => set("commandExecutionTimeout", Number(e.target.value))}
            className="h-7 w-24 text-xs"
          />
        </FieldRow>
      </div>

      {/* Container sandbox */}
      <div className="rounded-lg border border-border/60 p-3 space-y-0.5">
        <div className="text-xs font-medium text-muted-foreground mb-1">
          {t("security.sandboxSection")}
        </div>
        <p className="text-[11px] text-muted-foreground mb-2">{t("security.sandboxDesc")}</p>
        <FieldRow label={t("security.enableSandbox")} hint={t("security.enableSandboxHint")}>
          <Switch checked={!!settings.enableSandbox} onCheckedChange={handleSandboxToggle} />
        </FieldRow>
        <FieldRow label={t("security.sandboxBackend")} hint={t("security.sandboxBackendHint")}>
          <Select
            value={String(settings.containerRuntime ?? "auto")}
            onValueChange={handleRuntimeChange}
          >
            <SelectTrigger className="h-7 w-32 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">auto</SelectItem>
              <SelectItem value="docker">docker</SelectItem>
              <SelectItem value="podman">podman</SelectItem>
              <SelectItem value="e2b">e2b (CubeSandbox)</SelectItem>
            </SelectContent>
          </Select>
        </FieldRow>
        {settings.enableSandbox && (
          <FieldRow
            label={t("security.sandboxTest")}
            hint={
              sandboxSaveBlocked
                ? t("security.sandboxTestBlockedHint")
                : sandboxTestStatus === "passed"
                  ? t("security.sandboxTestPassed", {
                      latency: sandboxTestLatency !== null ? ` (${sandboxTestLatency}ms)` : "",
                    })
                  : undefined
            }
          >
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={handleSandboxTest}
                disabled={sandboxTestStatus === "testing"}
                type="button"
              >
                {sandboxTestStatus === "testing" ? (
                  <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                ) : (
                  <Zap className="w-3 h-3 mr-1" />
                )}
                {t("security.testSandbox")}
              </Button>
              {sandboxTestStatus === "passed" && (
                <span className="flex items-center gap-1 text-xs text-green-600">
                  <CheckCircle2 className="w-3.5 h-3.5" /> {t("security.passed")}
                </span>
              )}
              {sandboxTestStatus === "failed" && (
                <span className="flex items-center gap-1 text-xs text-destructive">
                  <XCircle className="w-3.5 h-3.5" /> {sandboxTestError ?? t("security.failed")}
                </span>
              )}
            </div>
          </FieldRow>
        )}
        <FieldRow label={t("security.disableNetwork")}>
          <Switch
            checked={!!settings.sandboxDisableNetwork}
            onCheckedChange={(v) => set("sandboxDisableNetwork", v)}
          />
        </FieldRow>
        <FieldRow label={t("security.dropCaps")} hint="cap_drop ALL">
          <Switch
            checked={!!settings.dropAllCapabilities}
            onCheckedChange={(v) => set("dropAllCapabilities", v)}
          />
        </FieldRow>
        <FieldRow label={t("security.noPrivileges")} hint="no-new-privileges">
          <Switch
            checked={!!settings.noNewPrivileges}
            onCheckedChange={(v) => set("noNewPrivileges", v)}
          />
        </FieldRow>
      </div>

      {/* Approval (human-in-the-loop, P2.2) */}
      <div className="rounded-lg border border-border/60 p-3 space-y-0.5">
        <div className="text-xs font-medium text-muted-foreground mb-1">
          {t("security.approvalSection")}
        </div>
        <FieldRow label={t("security.enableApproval")} hint={t("security.enableApprovalHint")}>
          <Switch
            checked={!!settings.approvalEnabled}
            onCheckedChange={(v) => set("approvalEnabled", v)}
          />
        </FieldRow>
        <FieldRow label={t("security.approvalRisk")} hint={t("security.approvalRiskHint")}>
          <Select
            value={String(settings.approvalRequiredForRisk ?? "critical")}
            onValueChange={(v) => set("approvalRequiredForRisk", v)}
          >
            <SelectTrigger className="h-7 w-28 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="low">low</SelectItem>
              <SelectItem value="medium">medium</SelectItem>
              <SelectItem value="high">high</SelectItem>
              <SelectItem value="critical">critical</SelectItem>
              <SelectItem value="never">{t("security.approvalNever")}</SelectItem>
            </SelectContent>
          </Select>
        </FieldRow>
        <FieldRow label={t("security.approvalTimeout")} hint={t("security.approvalTimeoutHint")}>
          <Input
            type="number"
            min={1}
            max={3600}
            value={Number(settings.approvalTimeoutSeconds ?? 120)}
            onChange={(e) => set("approvalTimeoutSeconds", Number(e.target.value))}
            className="h-7 w-24 text-xs"
          />
        </FieldRow>
        <FieldRow label={t("security.noChannel")} hint={t("security.noChannelHint")}>
          <Select
            value={String(settings.approvalNoChannelBehavior ?? "allow")}
            onValueChange={(v) => set("approvalNoChannelBehavior", v)}
          >
            <SelectTrigger className="h-7 w-28 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="allow">{t("security.noChannelAllow")}</SelectItem>
              <SelectItem value="deny">{t("security.noChannelDeny")}</SelectItem>
            </SelectContent>
          </Select>
        </FieldRow>
      </div>

      <div className="flex items-center justify-between pt-1">
        <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={reset}>
          <RotateCcw className="w-3 h-3 mr-1" /> {t("security.resetDefaults")}
        </Button>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs"
            onClick={() => setShowRaw((v) => !v)}
          >
            {showRaw ? t("security.hideJson") : t("security.showJson")}
          </Button>
          <Button
            size="sm"
            className="h-7"
            onClick={save}
            disabled={!dirty || saving || sandboxSaveBlocked}
          >
            <Save className="w-3 h-3 mr-1" />{" "}
            {saving
              ? t("security.saving")
              : sandboxSaveBlocked
                ? t("security.testFirst")
                : t("security.save")}
          </Button>
        </div>
      </div>

      {showRaw && (
        <pre className="text-[11px] bg-muted/30 rounded-lg p-3 overflow-auto max-h-60 font-mono">
          {JSON.stringify(settings, null, 2)}
        </pre>
      )}
    </div>
  );
}
