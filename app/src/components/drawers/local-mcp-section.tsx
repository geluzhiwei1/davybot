/**
 * LocalMcpSection — 本机私有 MCP(light-app relay)管理区块。
 *
 * 仅运行于 Tauri 壳内渲染(demo 页面同源 fetch 经 inject.js shim 抵达
 * light_bridge 环回端点 /api/mcp-host/*);纯 web 环境返回 null 不渲染。
 * command/args/env 只落本机 ~/.normnomos/light-app/mcp-host.json,云端
 * relay 注册仅上报服务器名与超时 —— 与云端用户级 MCP(服务器侧执行)互补。
 */
import { useCallback, useEffect, useState } from "react";
import {
  Loader2,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Save,
  ToggleLeft,
  ToggleRight,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { localMcpApi, type LocalMcpHostStatus, type LocalMcpServer } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { apiErrorDetail } from "@/lib/api/client.js";

/** 运行时壳检测(非构建期 —— demo web 构建同样跑在壳里,对位 accounts.tsx)。 */
const IS_TAURI = typeof window !== "undefined" && !!(window as { __TAURI__?: unknown }).__TAURI__;

/** 测试结果里的 error 归一为可读文本(壳侧为字符串或 JSON-RPC error 对象)。 */
function testErrorText(err: unknown): string {
  if (err == null) return "";
  if (typeof err === "string") return err;
  if (typeof err === "object") {
    const e = err as { message?: unknown; error?: unknown };
    if (typeof e.message === "string") return e.message;
    try {
      return JSON.stringify(err);
    } catch {
      return String(err);
    }
  }
  return String(err);
}

// ── 表单模型 ────────────────────────────────────────────────────────

interface LocalMcpForm {
  name: string;
  command: string;
  argsText: string;
  envText: string;
  cwd: string;
  timeout: string;
  disabled: boolean;
}

const EMPTY_FORM: LocalMcpForm = {
  name: "",
  command: "",
  argsText: "",
  envText: "",
  cwd: "",
  timeout: "300",
  disabled: false,
};

function toForm(s: LocalMcpServer): LocalMcpForm {
  return {
    name: s.name,
    command: s.command,
    argsText: (s.args ?? []).join(", "),
    envText: Object.entries(s.env ?? {})
      .map(([k, v]) => `${k}=${v}`)
      .join("\n"),
    cwd: s.cwd ?? "",
    timeout: String(s.timeout ?? 300),
    disabled: !!s.disabled,
  };
}

/** 表单 → 提交体(与壳侧 UpsertRequest {name, ...spec} 扁平结构对齐)。 */
function fromForm(f: LocalMcpForm): LocalMcpServer {
  const args = f.argsText
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const env: Record<string, string> = {};
  f.envText.split("\n").forEach((line) => {
    const i = line.indexOf("=");
    if (i > 0) {
      const k = line.slice(0, i).trim();
      const v = line.slice(i + 1).trim();
      if (k) env[k] = v;
    }
  });
  const timeout = Number.parseInt(f.timeout, 10);
  return {
    name: f.name.trim(),
    command: f.command.trim(),
    args,
    env,
    cwd: f.cwd.trim() || undefined,
    timeout: Number.isFinite(timeout) && timeout > 0 ? timeout : 300,
    disabled: f.disabled,
  };
}

// ── 添加/编辑对话框 ─────────────────────────────────────────────────

function LocalMcpDialog({
  open,
  onOpenChange,
  onSaved,
  editServer,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
  editServer: LocalMcpServer | null;
}) {
  const { t } = useTranslation("drawersUi");
  const [form, setForm] = useState<LocalMcpForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const isEdit = !!editServer;

  useEffect(() => {
    if (open) setForm(editServer ? toForm(editServer) : EMPTY_FORM);
  }, [open, editServer]);

  const handleSave = async () => {
    if (!form.name.trim() || !form.command.trim()) {
      toast.error(t("user.mcp.toast.nameCommandRequired"));
      return;
    }
    setSaving(true);
    try {
      const res = await localMcpApi.upsertServer(fromForm(form));
      toast.success(t("user.mcp.local.toast.saved", { name: res.name }));
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error(t("user.mcp.local.toast.opFailed"), { description: apiErrorDetail(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? t("user.mcp.local.dialog.editTitle") : t("user.mcp.local.dialog.addTitle")}
          </DialogTitle>
          <DialogDescription>{t("user.mcp.local.dialog.desc")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("user.mcp.form.name")}</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder={t("user.mcp.form.namePlaceholder")}
                disabled={isEdit}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">
                {t("user.mcp.form.timeout")} {t("user.mcp.local.form.timeoutHint")}
              </Label>
              <Input
                type="number"
                min={1}
                value={form.timeout}
                onChange={(e) => setForm({ ...form, timeout: e.target.value })}
                className="h-8 text-xs"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">{t("user.mcp.form.command")}</Label>
            <Input
              value={form.command}
              onChange={(e) => setForm({ ...form, command: e.target.value })}
              placeholder={t("user.mcp.form.commandPlaceholder")}
              className="h-8 text-xs"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">
              {t("user.mcp.form.args")} {t("user.mcp.form.argsHint")}
            </Label>
            <Input
              value={form.argsText}
              onChange={(e) => setForm({ ...form, argsText: e.target.value })}
              placeholder={t("user.mcp.form.argsPlaceholder")}
              className="h-8 text-xs"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">
              {t("user.mcp.form.env")} {t("user.mcp.local.form.envHint")}
            </Label>
            <Textarea
              value={form.envText}
              onChange={(e) => setForm({ ...form, envText: e.target.value })}
              placeholder={"API_KEY=sk-xxx"}
              className="h-20 text-xs resize-none"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">{t("user.mcp.form.cwd")}</Label>
            <Input
              value={form.cwd}
              onChange={(e) => setForm({ ...form, cwd: e.target.value })}
              placeholder={t("user.mcp.form.cwdPlaceholder")}
              className="h-8 text-xs"
            />
          </div>
          <div className="flex items-center justify-between">
            <Label className="text-xs">
              {form.disabled ? t("user.mcp.form.disabled") : t("user.mcp.form.enabled")}
            </Label>
            <Switch
              checked={!form.disabled}
              onCheckedChange={(checked) => setForm({ ...form, disabled: !checked })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button size="sm" className="h-8 md:h-7 text-xs" onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 className="w-3 h-3 animate-spin mr-1" />
            ) : (
              <Save className="w-3 h-3 mr-1" />
            )}
            {isEdit ? t("user.mcp.action.saveChanges") : t("user.mcp.action.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── 区块主体 ────────────────────────────────────────────────────────

export function LocalMcpSection() {
  const { t } = useTranslation("drawersUi");
  const [servers, setServers] = useState<LocalMcpServer[]>([]);
  const [status, setStatus] = useState<LocalMcpHostStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<LocalMcpServer | null>(null);
  const [testingName, setTestingName] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [res, st] = await Promise.all([localMcpApi.listServers(), localMcpApi.status()]);
      setServers(res.servers ?? []);
      setStatus(st);
    } catch {
      // 桥接瞬断:静默降级为空区块(FAST FAIL,不打断云端 MCP Tab)。
      setServers([]);
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (IS_TAURI) void load();
  }, [load]);

  const handleToggle = async (server: LocalMcpServer) => {
    try {
      await localMcpApi.upsertServer({ ...server, disabled: !server.disabled });
      toast.success(
        server.disabled
          ? t("user.mcp.toast.enabled", { name: server.name })
          : t("user.mcp.toast.disabled", { name: server.name }),
      );
      load();
    } catch (e) {
      toast.error(t("user.mcp.local.toast.opFailed"), { description: apiErrorDetail(e) });
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await localMcpApi.deleteServer(name);
      toast.success(t("user.mcp.local.toast.deleted", { name }));
      load();
    } catch (e) {
      toast.error(t("user.mcp.local.toast.opFailed"), { description: apiErrorDetail(e) });
    }
  };

  const handleTest = async (name: string) => {
    setTestingName(name);
    try {
      const res = await localMcpApi.testServer(name);
      if (res.ok) {
        toast.success(
          t("user.mcp.local.toast.testSuccess", { name, count: res.tools?.length ?? 0 }),
        );
      } else {
        toast.error(
          t("user.mcp.local.toast.testFailure", { name, message: testErrorText(res.error) }),
        );
      }
    } catch (e) {
      toast.error(t("user.mcp.local.toast.testFailure", { name, message: apiErrorDetail(e) }));
    } finally {
      setTestingName(null);
    }
  };

  if (!IS_TAURI) return null;

  return (
    <div className="space-y-3 pt-2 border-t border-border">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-medium">{t("user.mcp.local.title")}</div>
          <div className="text-[11px] text-muted-foreground">{t("user.mcp.local.desc")}</div>
        </div>
        <div className="flex gap-1 shrink-0">
          <Button
            size="sm"
            variant="ghost"
            onClick={load}
            disabled={loading}
            className="h-8 md:h-7"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8 md:h-7 text-xs"
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
          >
            <Plus className="w-3 h-3 mr-1" /> {t("user.mcp.local.add")}
          </Button>
        </div>
      </div>

      {/* relay 状态行 */}
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${
            status?.running ? "bg-green-500" : "bg-muted-foreground/40"
          }`}
        />
        <span>
          {status?.running ? t("user.mcp.local.relay.on") : t("user.mcp.local.relay.off")}
        </span>
        {status?.running && status.servers_enabled > 0 && (
          <Badge variant="outline" className="text-[10px]">
            {status.servers_enabled}
          </Badge>
        )}
        {status?.last_error && (
          <span className="text-destructive truncate" title={status.last_error}>
            {status.last_error}
          </span>
        )}
      </div>

      {servers.length === 0 ? (
        <div className="text-center py-4 text-xs text-muted-foreground border border-dashed border-border rounded-lg">
          {t("user.mcp.local.empty")}
        </div>
      ) : (
        <div className="space-y-2">
          {servers.map((server) => (
            <div
              key={server.name}
              className="flex items-center gap-3 p-3 rounded-lg border border-border bg-card/50"
            >
              <div
                className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                  server.disabled ? "bg-muted-foreground/30" : "bg-green-500"
                }`}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate">{server.name}</span>
                  <Badge
                    variant={server.disabled ? "secondary" : "default"}
                    className="text-[10px]"
                  >
                    {server.disabled ? t("user.mcp.badge.disabled") : t("user.mcp.badge.enabled")}
                  </Badge>
                </div>
                <div className="text-[11px] text-muted-foreground truncate">
                  {server.command} {(server.args ?? []).join(" ")}
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => handleToggle(server)}
                  title={
                    server.disabled ? t("user.mcp.action.enable") : t("user.mcp.action.disable")
                  }
                >
                  {server.disabled ? (
                    <ToggleRight className="w-3.5 h-3.5" />
                  ) : (
                    <ToggleLeft className="w-3.5 h-3.5" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => handleTest(server.name)}
                  disabled={testingName === server.name}
                  title={t("user.mcp.action.test")}
                >
                  {testingName === server.name ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Play className="w-3.5 h-3.5" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => {
                    setEditing(server);
                    setDialogOpen(true);
                  }}
                  title={t("user.mcp.action.edit")}
                >
                  <Pencil className="w-3.5 h-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-destructive hover:text-destructive"
                  onClick={() => handleDelete(server.name)}
                  title={t("user.mcp.action.delete")}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <LocalMcpDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSaved={load}
        editServer={editing}
      />
    </div>
  );
}
