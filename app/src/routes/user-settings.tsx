/**
 * User Settings Route — 用户级全局配置页面(原抽屉改为 tab 页卡,布局对齐 memory.tsx)。
 * 左导航 + 内容区布局,
 * 管理 LLM / MCP / Skills / Memory / Knowledge / Security / Preferences / About。
 */
import { useState, useEffect, useCallback, type ReactNode } from "react";
import { createFileRoute } from "@tanstack/react-router";
import {
  User,
  Palette,
  Bell,
  Shield,
  Info,
  Cpu,
  Plug,
  Zap,
  Brain,
  Database,
  Plus,
  RefreshCw,
  Play,
  Pencil,
  Trash2,
  Save,
  Loader2,
  ToggleLeft,
  ToggleRight,
  Lock,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LocalMcpSection } from "@/components/drawers/local-mcp-section";
import { isSectionVisible, type SectionKey } from "@/lib/caps";
import { useCaps } from "@/lib/stores/runtime-store";
import { SecurityPolicyForm } from "@/components/security/security-policy-form";
import { SandboxSection } from "@/components/sandbox";
import { useChatStore } from "@/lib/chat-store";
import { useStore } from "@/lib/store";
import {
  API_PROVIDERS,
  resolveBaseUrlOnProviderChange,
  fetchProviderPresets,
  type ApiProviderPreset,
} from "@/lib/llm-providers";
import {
  userMcpApi,
  llmApi,
  workspaceApi,
  type WsMcpServerConfig,
  type LLMProviderItem,
  type LLMProviderCreatePayload,
  type LLMProviderConfig,
} from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { apiErrorDetail, toastError } from "@/lib/api/client.js";
import { listGatewayModels, getCreditsBalance } from "@/lib/llm-gateway-service";
import { IS_DESKTOP } from "@/lib/platform";
import { cn } from "@/lib/utils";

// ── Tab trigger style（对齐 WorkspaceSettingsDrawer）─────────────────
const tabCls =
  "text-xs justify-start text-muted-foreground data-[state=active]:bg-brand/10 data-[state=active]:text-brand data-[state=active]:font-medium rounded-md px-2.5 py-1.5 text-left font-normal";

// ── 导航分组（label/text 为 i18n key，渲染时经 t() 翻译）─────────────
const NAV_GROUPS: { label: string; items: { value: string; icon: ReactNode; text: string }[] }[] = [
  {
    label: "user.nav.groupModels",
    items: [
      { value: "llm", icon: <Cpu className="w-3.5 h-3.5" />, text: "user.nav.llm" },
      { value: "mcp", icon: <Plug className="w-3.5 h-3.5" />, text: "user.nav.mcp" },
      { value: "skills", icon: <Zap className="w-3.5 h-3.5" />, text: "user.nav.skills" },
    ],
  },
  {
    label: "user.nav.groupRuntime",
    items: [
      { value: "memory", icon: <Brain className="w-3.5 h-3.5" />, text: "user.nav.memory" },
      {
        value: "knowledge",
        icon: <Database className="w-3.5 h-3.5" />,
        text: "user.nav.knowledge",
      },
    ],
  },
  {
    label: "user.nav.groupSecurity",
    items: [
      { value: "security", icon: <Shield className="w-3.5 h-3.5" />, text: "user.nav.security" },
      {
        value: "preferences",
        icon: <Palette className="w-3.5 h-3.5" />,
        text: "user.nav.preferences",
      },
      { value: "about", icon: <Info className="w-3.5 h-3.5" />, text: "user.nav.about" },
    ],
  },
];

// API provider 预设（含官方默认 base_url）见 @/lib/llm-providers

// ── 自定义 Header 客户端预设（模拟 Roo Code / Claude Code 等客户端请求头）──
const HEADER_PRESETS: { label: string; headers: Record<string, string> }[] = [
  {
    label: "Claude Code",
    headers: {
      "User-Agent": "claude-cli/1.0.44 (external, cli)",
      "x-app": "cli",
      "anthropic-version": "2023-06-01",
      "anthropic-beta": "claude-code-20250219",
    },
  },
  {
    label: "Roo Code",
    headers: {
      "User-Agent": "RooCode/3.21.0",
      "X-Title": "Roo Code",
      "HTTP-Referer": "https://roocode.com",
    },
  },
  {
    label: "Cline",
    headers: {
      "User-Agent": "cline/3.9.0",
      "X-Title": "Cline",
      "HTTP-Referer": "https://cline.bot",
    },
  },
  {
    label: "Cursor",
    headers: {
      "User-Agent": "cursor/0.50.7",
      "x-cursor-checksum":
        "10istratorcursor(loader/Coq7mDNJcn4jWqkH7OEvCLlf1Ejs2dWUwRpRLCXWsQJfgELIWABA3mLX0tBnoC77+dtD+H2ACa2O4uTtinWB1A==)",
    },
  },
];

type HeaderRow = { key: string; value: string };

function headerRowsFromRecord(headers?: Record<string, string>): HeaderRow[] {
  return Object.entries(headers ?? {}).map(([key, value]) => ({ key, value }));
}

function recordFromHeaderRows(rows: HeaderRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of rows) {
    const k = r.key.trim();
    if (k) out[k] = r.value;
  }
  return out;
}

const emptyLLMForm: LLMProviderCreatePayload = {
  name: "",
  apiProvider: "openai",
  openAiBaseUrl: "https://api.openai.com/v1",
  openAiApiKey: "",
  openAiModelId: "",
  openAiHeaders: {},
  temperature: 0.7,
  timeout: 600,
  maxRetries: 3,
  retryDelay: 2,
  saveLocation: "user",
};

// ── MCP empty form ────────────────────────────────────────────────────
const emptyMCPForm: WsMcpServerConfig = {
  name: "",
  command: "",
  args: [],
  cwd: "",
  env: {},
  transport: "stdio",
  url: "",
  headers: {},
  always_allow: [],
  timeout: 300,
  disabled: false,
};

// ── User Knowledge defaults ───────────────────────────────────────────
const KNOWLEDGE_DEFAULTS: Record<string, unknown> = {
  enabled: true,
  vector_store_type: "sqlite-vec",
  embedding_model: "Qwen/Qwen3-Embedding-0.6B",
  dimension: 1024,
  chunk_size: 500,
  chunk_overlap: 50,
  default_top_k: 5,
  retrieval_mode: "hybrid",
  rag_context_length: 2000,
};

// ── User Memory defaults ──────────────────────────────────────────────
const MEMORY_DEFAULTS: Record<string, unknown> = {
  enabled: true,
  virtual_page_size: 2000,
  max_active_pages: 5,
  default_energy: 1.0,
  energy_decay_rate: 0.95,
  min_energy_threshold: 0.2,
  consolidation_enabled: false,
};

// ── User Skills defaults ──────────────────────────────────────────────
const SKILLS_DEFAULTS: Record<string, unknown> = {
  enabled: true,
  auto_discovery: true,
};

// ═══════════════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════════════

export const Route = createFileRoute("/user-settings")({
  component: UserSettingsPage,
});

function UserSettingsPage() {
  const { t } = useTranslation("drawersUi");
  // 运行期能力 (多模式统一方案 §L4): NAV 按 SECTIONS 表过滤, 不按 mode 字符串分支
  const { caps, mode } = useCaps();
  // SaaS: 大模型/安全 由平台统一管理 → 界面只读并明示 (后端守卫仍是权威)
  const saasReadonly = mode === "saas";
  const navGroups = NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((it) => isSectionVisible(it.value as SectionKey, caps)),
  })).filter((g) => g.items.length > 0);
  return (
    <div className="flex flex-col h-full">
      {/* Header — matches memory.tsx layout */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border/60 shrink-0">
        <User className="w-5 h-5 text-brand" />
        <h1 className="text-base font-semibold flex-1">{t("user.drawer.title")}</h1>
      </div>
      <Tabs defaultValue="llm" className="flex-1 flex flex-row min-h-0">
        <TabsList className="flex flex-col w-44 shrink-0 items-stretch justify-start rounded-none border-r border-border/60 bg-transparent p-2 gap-0.5 overflow-y-auto scrollbar-thin h-auto">
          {navGroups.flatMap((g) => [
            <div
              key={`lbl-${g.label}`}
              className="text-[10px] uppercase tracking-wide text-muted-foreground/70 px-2.5 pt-2.5 pb-1"
            >
              {t(g.label)}
            </div>,
            ...g.items.map((it) => (
              <TabsTrigger key={it.value} value={it.value} className={tabCls}>
                <span className="mr-1.5 flex items-center">{it.icon}</span>
                {t(it.text)}
              </TabsTrigger>
            )),
          ])}
        </TabsList>

        <div className="flex-1 overflow-y-auto scrollbar-thin">
          <TabsContent value="llm" className="p-4 mt-0">
            {saasReadonly ? (
              <SaasReadonly>
                <UserLLMTab />
              </SaasReadonly>
            ) : (
              <UserLLMTab />
            )}
          </TabsContent>
          <TabsContent value="mcp" className="p-4 mt-0">
            <UserMCPTab />
          </TabsContent>
          <TabsContent value="skills" className="p-4 mt-0">
            <UserSkillsTab />
          </TabsContent>
          <TabsContent value="memory" className="p-4 mt-0">
            <UserMemoryTab />
          </TabsContent>
          <TabsContent value="knowledge" className="p-4 mt-0">
            <UserKnowledgeTab />
          </TabsContent>
          <TabsContent value="security" className="p-4 mt-0">
            {saasReadonly ? (
              <SaasReadonly>
                <div className="space-y-4">
                  <SecurityPolicyForm scope="user" />
                  {/* 沙箱执行环境(安全族归位:原 /settings 页卡迁入;无 sandbox cap 的模式整体隐藏) */}
                  {isSectionVisible("sandbox", caps) && <SandboxSection />}
                </div>
              </SaasReadonly>
            ) : (
              <div className="space-y-4">
                <SecurityPolicyForm scope="user" />
                {/* 沙箱执行环境(安全族归位:原 /settings 页卡迁入;无 sandbox cap 的模式整体隐藏) */}
                {isSectionVisible("sandbox", caps) && <SandboxSection />}
              </div>
            )}
          </TabsContent>
          <TabsContent value="preferences" className="p-4 mt-0">
            <PreferencesTab />
          </TabsContent>
          <TabsContent value="about" className="p-4 mt-0">
            <AboutTab />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Helper Components
// ═══════════════════════════════════════════════════════════════════════

// SaaS 平台托管只读容器: 锁形横幅明示原因 + inert 屏蔽交互 (含键盘焦点)。
// 仅 UI 层约束; 后端守卫仍是权威 (前端隐藏/禁用 ≠ 安全)。
function SaasReadonly({ children }: { children: ReactNode }) {
  const { t } = useTranslation("drawersUi");
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
        <Lock className="w-4 h-4 mt-0.5 shrink-0 text-amber-600" />
        <div className="min-w-0">
          <p className="text-xs font-medium text-amber-700 dark:text-amber-400">
            {t("user.saasManaged.title")}
          </p>
          <p className="text-[11px] text-muted-foreground">{t("user.saasManaged.desc")}</p>
        </div>
      </div>
      <div inert className="pointer-events-none select-none opacity-70">
        {children}
      </div>
    </div>
  );
}

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

// ═══════════════════════════════════════════════════════════════════════
// LLM Tab — 用户级 LLM 提供商
// ═══════════════════════════════════════════════════════════════════════

function LLMProviderDialog({
  open,
  onOpenChange,
  workspaceId,
  onSaved,
  editProvider,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  workspaceId: string;
  onSaved: () => void;
  editProvider?: LLMProviderItem | null;
}) {
  const { t } = useTranslation("drawersUi");
  const isEdit = !!editProvider;
  const [form, setForm] = useState<LLMProviderCreatePayload>(emptyLLMForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [testMode, setTestMode] = useState<"stream" | "non-stream">("non-stream");
  // 自定义 Header 编辑行（键可临时为空，保存时过滤）
  const [headerRows, setHeaderRows] = useState<HeaderRow[]>([]);
  // Provider 下拉预设：优先后端目录，静态列表兜底
  const [providerPresets, setProviderPresets] = useState<ApiProviderPreset[]>(API_PROVIDERS);

  useEffect(() => {
    if (open) {
      fetchProviderPresets(workspaceId)
        .then(setProviderPresets)
        .catch(() => setProviderPresets(API_PROVIDERS));
      if (editProvider) {
        const cfg = (editProvider.config?.config ?? {}) as LLMProviderConfig;
        setForm({
          name: editProvider.name,
          apiProvider: cfg.apiProvider ?? "openai",
          openAiBaseUrl: cfg.openAiBaseUrl ?? "",
          openAiApiKey: cfg.openAiApiKey ?? "",
          openAiModelId: cfg.openAiModelId ?? "",
          openAiHeaders: cfg.openAiHeaders ?? {},
          temperature: cfg.temperature ?? 0.7,
          timeout: cfg.timeout ?? 600,
          maxRetries: cfg.maxRetries ?? 3,
          retryDelay: cfg.retryDelay ?? 2,
          toolChoice: cfg.toolChoice ?? undefined,
          saveLocation: "user",
        });
        setHeaderRows(headerRowsFromRecord(cfg.openAiHeaders));
      } else {
        setForm(emptyLLMForm);
        setHeaderRows([]);
      }
      setTestResult(null);
    }
  }, [open, editProvider]);

  const update = (patch: Partial<LLMProviderCreatePayload>) => setForm((f) => ({ ...f, ...patch }));

  // 同步 Header 行 → form.openAiHeaders（空键行保存时被过滤）
  const updateHeaderRows = (rows: HeaderRow[]) => {
    setHeaderRows(rows);
    update({ openAiHeaders: recordFromHeaderRows(rows) });
  };

  const handleSave = async () => {
    if (!form.name.trim() || !form.apiProvider) {
      toast.error(t("user.llm.toast.nameProviderRequired"));
      return;
    }
    setSaving(true);
    try {
      if (isEdit) {
        if (workspaceId) {
          await llmApi.updateProvider(workspaceId, editProvider!.name, {
            ...form,
            saveLocation: undefined,
          });
        } else {
          await llmApi.updateUserProvider(editProvider!.name, { ...form, saveLocation: undefined });
        }
        toast.success(t("user.llm.toast.updated", { name: form.name }));
      } else {
        if (workspaceId) {
          await llmApi.createProvider(workspaceId, form);
        } else {
          await llmApi.createUserProvider(form);
        }
        toast.success(t("user.llm.toast.created", { name: form.name }));
      }
      onSaved();
      onOpenChange(false);
    } catch {
      toast.error(isEdit ? t("user.llm.toast.updateFailed") : t("user.llm.toast.createFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await llmApi.testUserProvider(form, testMode);
      setTestResult(
        res.supported
          ? { ok: true, text: t("user.llm.test.supported", { model: res.model || "—" }) }
          : {
              ok: false,
              text: t("user.llm.test.unsupported", {
                message: res.message || t("user.llm.test.unknown"),
              }),
            },
      );
      toast.success(res.supported ? t("user.llm.test.ok") : t("user.llm.test.notPassed"));
    } catch (e) {
      const detail = apiErrorDetail(e);
      setTestResult({ ok: false, text: t("user.llm.test.requestFailed", { detail }) });
      toast.error(t("user.llm.test.toastFailed"), { description: detail });
    } finally {
      setTesting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto scrollbar-thin">
        <DialogHeader>
          <DialogTitle className="text-sm">
            {isEdit ? t("user.llm.dialog.editTitle") : t("user.llm.dialog.addTitle")}
          </DialogTitle>
          <DialogDescription className="text-xs">
            {isEdit ? t("user.llm.dialog.editDesc") : t("user.llm.dialog.addDesc")}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("user.llm.form.name")}</Label>
              <Input
                placeholder={t("user.llm.form.namePlaceholder")}
                value={form.name}
                onChange={(e) => update({ name: e.target.value })}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t("user.llm.form.provider")}</Label>
              <Select
                value={form.apiProvider}
                onValueChange={(v) =>
                  update({
                    apiProvider: v,
                    openAiBaseUrl: resolveBaseUrlOnProviderChange(
                      v,
                      form.openAiBaseUrl,
                      providerPresets,
                    ),
                  })
                }
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {providerPresets.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Base URL</Label>
            <Input
              placeholder="https://api.openai.com/v1"
              value={form.openAiBaseUrl ?? ""}
              onChange={(e) => update({ openAiBaseUrl: e.target.value || undefined })}
              className="h-8 text-xs"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">API Key</Label>
              <Input
                type="password"
                placeholder={isEdit ? t("user.llm.form.keepKey") : "sk-..."}
                value={form.openAiApiKey ?? ""}
                onChange={(e) => update({ openAiApiKey: e.target.value || undefined })}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t("user.llm.form.modelId")}</Label>
              <Input
                placeholder={t("user.llm.form.modelPlaceholder")}
                value={form.openAiModelId ?? ""}
                onChange={(e) => update({ openAiModelId: e.target.value || undefined })}
                className="h-8 text-xs"
              />
            </div>
          </div>
          <Separator />
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label className="text-xs">{t("user.llm.form.customHeaders")}</Label>
              <div className="flex flex-wrap gap-1 justify-end">
                {HEADER_PRESETS.map((p) => (
                  <Button
                    key={p.label}
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-6 text-[10px] px-2"
                    onClick={() => updateHeaderRows(headerRowsFromRecord(p.headers))}
                  >
                    {p.label}
                  </Button>
                ))}
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {t("user.llm.form.customHeadersHint")}
            </p>
            {headerRows.map((row, idx) => (
              <div key={idx} className="flex items-center gap-1.5">
                <Input
                  placeholder={t("user.llm.form.headerName")}
                  value={row.key}
                  onChange={(e) => {
                    const rows = headerRows.map((r, i) =>
                      i === idx ? { ...r, key: e.target.value } : r,
                    );
                    updateHeaderRows(rows);
                  }}
                  className="h-8 text-xs flex-[4]"
                />
                <Input
                  placeholder={t("user.llm.form.headerValue")}
                  value={row.value}
                  onChange={(e) => {
                    const rows = headerRows.map((r, i) =>
                      i === idx ? { ...r, value: e.target.value } : r,
                    );
                    updateHeaderRows(rows);
                  }}
                  className="h-8 text-xs flex-[6]"
                />
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="w-6 h-6 shrink-0"
                  onClick={() => updateHeaderRows(headerRows.filter((_, i) => i !== idx))}
                >
                  <Trash2 className="w-3 h-3" />
                </Button>
              </div>
            ))}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 text-xs text-muted-foreground"
              onClick={() => updateHeaderRows([...headerRows, { key: "", value: "" }])}
            >
              <Plus className="w-3 h-3 mr-1" />
              {t("user.llm.form.addHeader")}
            </Button>
          </div>
          <Separator />
          <p className="text-[11px] text-muted-foreground">{t("user.llm.form.advanced")}</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Temperature</Label>
              <Input
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={form.temperature ?? 0.7}
                onChange={(e) => update({ temperature: parseFloat(e.target.value) || 0.7 })}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Tool Choice</Label>
              <Select
                value={form.toolChoice ?? "default"}
                onValueChange={(v) => update({ toolChoice: v === "default" ? undefined : v })}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder={t("user.llm.form.default")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">{t("user.llm.form.default")}</SelectItem>
                  <SelectItem value="auto">auto</SelectItem>
                  <SelectItem value="required">required</SelectItem>
                  <SelectItem value="none">none</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("user.llm.form.timeout")}</Label>
              <Input
                type="number"
                min={10}
                max={3600}
                value={form.timeout ?? 600}
                onChange={(e) => update({ timeout: parseInt(e.target.value) || 600 })}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t("user.llm.form.maxRetries")}</Label>
              <Input
                type="number"
                min={0}
                max={10}
                value={form.maxRetries ?? 3}
                onChange={(e) => update({ maxRetries: parseInt(e.target.value) || 3 })}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t("user.llm.form.retryDelay")}</Label>
              <Input
                type="number"
                min={0.5}
                max={60}
                step={0.5}
                value={form.retryDelay ?? 2}
                onChange={(e) => update({ retryDelay: parseFloat(e.target.value) || 2 })}
                className="h-8 text-xs"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">{t("user.llm.form.testMode")}</Label>
            <Select
              value={testMode}
              onValueChange={(v) => setTestMode(v as "stream" | "non-stream")}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="non-stream">{t("user.llm.form.nonStream")}</SelectItem>
                <SelectItem value="stream">{t("user.llm.form.stream")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {testResult && (
            <div
              className={cn(
                "text-xs p-2 rounded",
                testResult.ok
                  ? "bg-green-500/10 text-green-600"
                  : "bg-yellow-500/10 text-yellow-600",
              )}
            >
              {testResult.text}
            </div>
          )}
        </div>
        <DialogFooter className="gap-2">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={handleTest}
            disabled={testing}
          >
            {testing ? (
              <Loader2 className="w-3 h-3 animate-spin mr-1" />
            ) : (
              <Play className="w-3 h-3 mr-1" />
            )}
            {t("user.llm.test.connection")}
          </Button>
          <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 className="w-3 h-3 animate-spin mr-1" />
            ) : (
              <Save className="w-3 h-3 mr-1" />
            )}
            {isEdit ? t("user.llm.action.saveChanges") : t("user.llm.action.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function UserLLMTab() {
  const { t } = useTranslation("drawersUi");
  const workspaces = useStore((s) => s.workspaces);
  const filesDrawerFor = useStore((s) => s.filesDrawerFor);
  // LLM API 需要 workspaceId 作为路由网关；取首个可用工作区
  const wsId = filesDrawerFor || workspaces[0]?.id || "";

  const [providers, setProviders] = useState<LLMProviderItem[]>([]);
  // 其他来源配置（如 LLM 网关注入），只读展示，保持与能力 tab 一致
  const [otherProviders, setOtherProviders] = useState<LLMProviderItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<LLMProviderItem | null>(null);
  const [gatewayModelCount, setGatewayModelCount] = useState<number | null>(null);
  const [credits, setCredits] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      let userList: LLMProviderItem[] = [];
      let otherList: LLMProviderItem[] = [];
      if (wsId) {
        // 有工作区：走 workspace 级 API 读取 user 段（保持与之前一致）
        const res = await llmApi.listSettingsAll(wsId);
        userList = res.settings?.user ?? [];
        otherList = res.settings?.other ?? [];
      } else {
        // 无工作区：直接调用用户级 API
        const res = await llmApi.listUserProviders();
        userList = res.settings?.user ?? [];
      }
      const mapped: LLMProviderItem[] = userList.map((e) => ({
        name: e.name,
        source: "user" as const,
        config: {
          config: (e.config?.config ?? e.config ?? {}) as LLMProviderConfig,
          source: "user",
        },
      }));
      setProviders(mapped);
      setOtherProviders(
        otherList.map((e) => ({
          name: e.name,
          source: e.source ?? "other",
          config: {
            config: (e.config?.config ?? e.config ?? {}) as LLMProviderConfig,
            source: e.source ?? "other",
          },
        })),
      );
    } catch (e) {
      toastError(t("user.llm.toast.loadFailed"), e);
    } finally {
      setLoading(false);
    }
  }, [wsId, t]);

  const loadGateway = useCallback(async () => {
    try {
      const [models, bal] = await Promise.all([listGatewayModels(), getCreditsBalance()]);
      setGatewayModelCount(Array.isArray(models) ? models.length : 0);
      setCredits(bal?.balance ?? null);
    } catch {
      setGatewayModelCount(null);
      setCredits(null);
    }
  }, []);

  useEffect(() => {
    load();
    loadGateway();
  }, [load, loadGateway]);

  const handleDelete = async (name: string) => {
    try {
      if (wsId) {
        await llmApi.deleteProvider(wsId, name);
      } else {
        await llmApi.deleteUserProvider(name);
      }
      toast.success(t("user.llm.toast.deleted", { name }));
      load();
    } catch {
      toast.error(t("user.llm.toast.deleteFailed"));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionTitle title={t("user.llm.tab.title")} desc={t("user.llm.tab.desc")} />
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={load} disabled={loading} className="h-7">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => {
              setEditingProvider(null);
              setDialogOpen(true);
            }}
          >
            <Plus className="w-3 h-3 mr-1" /> {t("user.llm.tab.add")}
          </Button>
        </div>
      </div>

      {/* 网关模型 */}
      <div className="rounded-lg border border-border bg-card/40 p-3 space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium">{t("user.llm.gateway.title")}</span>
          <Badge variant="outline" className="text-[10px]">
            {gatewayModelCount === null
              ? t("user.llm.gateway.unavailable")
              : t("user.llm.gateway.modelsCount", { count: gatewayModelCount })}
          </Badge>
        </div>
        <p className="text-[11px] text-muted-foreground">
          {t("user.llm.gateway.note")}
          {credits !== null ? t("user.llm.gateway.creditsBalance", { credits }) : ""}
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : providers.length === 0 ? (
        <div className="text-center py-8 text-xs text-muted-foreground border border-dashed border-border rounded-lg">
          {t("user.llm.empty")}
        </div>
      ) : (
        <div className="space-y-2">
          {providers.map((p) => {
            const cfg = p.config?.config;
            return (
              <div
                key={p.name}
                className="flex items-center gap-3 p-3 rounded-lg border border-border bg-card/50"
              >
                <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center">
                  <Cpu className="w-4 h-4 text-brand" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{p.name}</span>
                    <Badge className="text-[10px] bg-blue-500/10 text-blue-500">
                      {t("user.llm.badge.user")}
                    </Badge>
                  </div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {cfg?.openAiModelId ?? cfg?.apiProvider ?? "—"}
                    {cfg?.openAiBaseUrl ? ` · ${cfg.openAiBaseUrl}` : ""}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0"
                  onClick={() => {
                    setEditingProvider(p);
                    setDialogOpen(true);
                  }}
                  title={t("user.llm.action.edit")}
                >
                  <Pencil className="w-3 h-3" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0"
                  onClick={() => handleDelete(p.name)}
                  title={t("user.llm.action.delete")}
                >
                  <Trash2 className="w-3 h-3 text-destructive" />
                </Button>
              </div>
            );
          })}
        </div>
      )}

      {/* 其他来源（网关注入等）— 只读，与对话模型选择器所见一致 */}
      {!loading && otherProviders.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 pt-2">
            <span className="text-xs font-medium">{t("user.llm.other.title")}</span>
            <Badge variant="outline" className="text-[10px]">
              {t("user.llm.other.count", { count: otherProviders.length })}
            </Badge>
          </div>
          {otherProviders.map((p) => {
            const cfg = p.config?.config;
            return (
              <div
                key={p.name}
                className="flex items-center gap-3 p-3 rounded-lg border border-border/60 bg-muted/20"
              >
                <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center">
                  <Cpu className="w-4 h-4 text-muted-foreground" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{p.name}</span>
                    <Badge className="text-[10px] bg-slate-500/10 text-slate-500">
                      {p.source === "gateway"
                        ? t("user.llm.other.badge.gateway")
                        : p.source === "default_user"
                          ? t("user.llm.other.badge.defaultUser")
                          : p.source}
                    </Badge>
                  </div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {cfg?.openAiModelId ?? cfg?.apiProvider ?? "—"}
                    {cfg?.openAiBaseUrl ? ` · ${cfg.openAiBaseUrl}` : ""}
                  </div>
                </div>
              </div>
            );
          })}
          <p className="text-[11px] text-muted-foreground">{t("user.llm.other.note")}</p>
        </div>
      )}

      <LLMProviderDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        workspaceId={wsId}
        onSaved={load}
        editProvider={editingProvider}
      />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// MCP Tab — 用户级 MCP 服务器
// ═══════════════════════════════════════════════════════════════════════

function MCPServerDialog({
  open,
  onOpenChange,
  onSaved,
  editServer,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onSaved: () => void;
  editServer?: WsMcpServerConfig | null;
}) {
  const { t } = useTranslation("drawersUi");
  const isEdit = !!editServer;
  const [form, setForm] = useState<WsMcpServerConfig>(emptyMCPForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [argsText, setArgsText] = useState("");
  const [alwaysAllowText, setAlwaysAllowText] = useState("");
  const [envText, setEnvText] = useState("");

  useEffect(() => {
    if (open) {
      if (editServer) {
        setForm(editServer);
        setArgsText((editServer.args ?? []).join(", "));
        setAlwaysAllowText((editServer.always_allow ?? []).join(", "));
        setEnvText(
          Object.entries(editServer.env ?? {})
            .map(([k, v]) => `${k}=${v}`)
            .join("\n"),
        );
      } else {
        setForm(emptyMCPForm);
        setArgsText("");
        setAlwaysAllowText("");
        setEnvText("");
      }
    }
  }, [open, editServer]);

  const syncArgs = (text: string) => {
    setArgsText(text);
    setForm((f) => ({
      ...f,
      args: text
        ? text
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
        : [],
    }));
  };

  const syncEnv = (text: string) => {
    setEnvText(text);
    const env: Record<string, string> = {};
    text
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .forEach((line) => {
        const idx = line.indexOf("=");
        if (idx > 0) env[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
      });
    setForm((f) => ({ ...f, env }));
  };

  const syncAlwaysAllow = (text: string) => {
    setAlwaysAllowText(text);
    setForm((f) => ({
      ...f,
      always_allow: text
        ? text
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
        : [],
    }));
  };

  const handleSave = async () => {
    if (!form.name.trim() || !form.command?.trim()) {
      toast.error(t("user.mcp.toast.nameCommandRequired"));
      return;
    }
    setSaving(true);
    try {
      if (isEdit) {
        await userMcpApi.updateServer(editServer!.name, form);
        toast.success(t("user.mcp.toast.updated", { name: form.name }));
      } else {
        await userMcpApi.addServer(form);
        toast.success(t("user.mcp.toast.created", { name: form.name }));
      }
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error(
        (e as Error)?.message ??
          (isEdit ? t("user.mcp.toast.updateFailed") : t("user.mcp.toast.createFailed")),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!form.name.trim()) {
      toast.error(t("user.mcp.toast.nameRequired"));
      return;
    }
    setTesting(true);
    try {
      if (!isEdit) {
        await userMcpApi.addServer(form);
        onSaved();
      }
      const res = await userMcpApi.testServer(form.name);
      toast.success(res.message || t("user.mcp.toast.testPassed"));
    } catch (e) {
      toast.error((e as Error)?.message ?? t("user.mcp.toast.testFailedConn"));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto scrollbar-thin">
        <DialogHeader>
          <DialogTitle className="text-sm">
            {isEdit ? t("user.mcp.dialog.editTitle") : t("user.mcp.dialog.addTitle")}
          </DialogTitle>
          <DialogDescription className="text-xs">{t("user.mcp.dialog.desc")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-1.5">
            <Label className="text-xs">{t("user.mcp.form.name")}</Label>
            <Input
              placeholder={t("user.mcp.form.namePlaceholder")}
              value={form.name}
              disabled={isEdit}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="h-8 text-xs"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">{t("user.mcp.form.transport")}</Label>
            <Select
              value={form.transport ?? "stdio"}
              onValueChange={(v) =>
                setForm((f) => ({ ...f, transport: v as "stdio" | "sse" | "http" }))
              }
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="stdio">{t("user.mcp.form.stdioOption")}</SelectItem>
                <SelectItem value="sse">{t("user.mcp.form.sseOption")}</SelectItem>
                <SelectItem value="http">{t("user.mcp.form.httpOption")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {form.transport === "sse" || form.transport === "http" ? (
            <div className="space-y-1.5">
              <Label className="text-xs">URL *</Label>
              <Input
                placeholder={
                  form.transport === "sse"
                    ? t("user.mcp.form.sseUrlPlaceholder")
                    : t("user.mcp.form.httpUrlPlaceholder")
                }
                value={form.url ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
                className="h-8 text-xs"
              />
            </div>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2 space-y-1.5">
                  <Label className="text-xs">{t("user.mcp.form.command")}</Label>
                  <Input
                    placeholder={t("user.mcp.form.commandPlaceholder")}
                    value={form.command ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{t("user.mcp.form.cwd")}</Label>
                  <Input
                    placeholder={t("user.mcp.form.cwdPlaceholder")}
                    value={form.cwd ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, cwd: e.target.value || undefined }))}
                    className="h-8 text-xs"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">
                  {t("user.mcp.form.args")}{" "}
                  <span className="text-[10px] text-muted-foreground">
                    {t("user.mcp.form.argsHint")}
                  </span>
                </Label>
                <Input
                  placeholder={t("user.mcp.form.argsPlaceholder")}
                  value={argsText}
                  onChange={(e) => syncArgs(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
            </>
          )}
          <div className="space-y-1.5">
            <Label className="text-xs">
              {t("user.mcp.form.env")}{" "}
              <span className="text-[10px] text-muted-foreground">
                {t("user.mcp.form.envHint")}
              </span>
            </Label>
            <Textarea
              placeholder={"API_KEY=sk-xxx\nANOTHER=value"}
              value={envText}
              onChange={(e) => syncEnv(e.target.value)}
              className="h-16 text-xs font-mono resize-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("user.mcp.form.timeout")}</Label>
              <Input
                type="number"
                min={10}
                max={3600}
                value={form.timeout ?? 300}
                onChange={(e) =>
                  setForm((f) => ({ ...f, timeout: parseInt(e.target.value) || 300 }))
                }
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5 flex items-end">
              <label className="flex items-center gap-2 cursor-pointer">
                <Switch
                  checked={!form.disabled}
                  onCheckedChange={(v) => setForm((f) => ({ ...f, disabled: !v }))}
                />
                <span className="text-xs">
                  {form.disabled ? t("user.mcp.form.disabled") : t("user.mcp.form.enabled")}
                </span>
              </label>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">
              {t("user.mcp.form.alwaysAllow")}{" "}
              <span className="text-[10px] text-muted-foreground">
                {t("user.mcp.form.alwaysAllowHint")}
              </span>
            </Label>
            <Textarea
              placeholder={t("user.mcp.form.alwaysAllowPlaceholder")}
              value={alwaysAllowText}
              onChange={(e) => syncAlwaysAllow(e.target.value)}
              className="h-14 text-xs resize-none"
            />
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={handleTest}
            disabled={testing}
          >
            {testing ? (
              <Loader2 className="w-3 h-3 animate-spin mr-1" />
            ) : (
              <Play className="w-3 h-3 mr-1" />
            )}
            {t("user.mcp.test.connection")}
          </Button>
          <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving}>
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

function UserMCPTab() {
  // 本机私有 MCP 区块可见性走 SECTIONS 表 (构建期 desktop × 运行期 caps)
  const { caps } = useCaps();
  const { t } = useTranslation("drawersUi");
  const [servers, setServers] = useState<WsMcpServerConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingServer, setEditingServer] = useState<WsMcpServerConfig | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await userMcpApi.listServers();
      setServers(res.servers ?? []);
    } catch {
      toast.error(t("user.mcp.toast.loadFailed"));
      setServers([]);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const handleToggle = async (server: WsMcpServerConfig) => {
    try {
      await userMcpApi.updateServer(server.name, { disabled: !server.disabled });
      toast.success(
        server.disabled
          ? t("user.mcp.toast.enabled", { name: server.name })
          : t("user.mcp.toast.disabled", { name: server.name }),
      );
      load();
    } catch (e) {
      toast.error((e as Error)?.message ?? t("user.mcp.toast.opFailed"));
    }
  };

  const handleDelete = async (serverName: string) => {
    try {
      await userMcpApi.deleteServer(serverName);
      toast.success(t("user.mcp.toast.deleted", { name: serverName }));
      load();
    } catch (e) {
      toast.error((e as Error)?.message ?? t("user.mcp.toast.deleteFailed"));
    }
  };

  const handleTest = async (serverName: string) => {
    try {
      const res = await userMcpApi.testServer(serverName);
      if (res.success) {
        toast.success(t("user.mcp.toast.testSuccess", { name: serverName }));
      } else {
        toast.error(t("user.mcp.toast.testFailure", { name: serverName, message: res.message }));
      }
    } catch (e) {
      toast.error(t("user.mcp.toast.testError", { message: (e as Error)?.message }));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionTitle title={t("user.mcp.tab.title")} desc={t("user.mcp.tab.desc")} />
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={load} disabled={loading} className="h-7">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => {
              setEditingServer(null);
              setDialogOpen(true);
            }}
          >
            <Plus className="w-3 h-3 mr-1" /> {t("user.mcp.tab.add")}
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : servers.length === 0 ? (
        <div className="text-center py-8 text-xs text-muted-foreground border border-dashed border-border rounded-lg">
          {t("user.mcp.empty")}
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
                  {server.command ?? "—"} {(server.args ?? []).join(" ")}
                  {server.always_allow && server.always_allow.length > 0 && (
                    <span className="text-brand/70 ml-1">
                      · {t("user.mcp.autoAllow", { tools: server.always_allow.join(", ") })}
                    </span>
                  )}
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
                  title={t("user.mcp.action.test")}
                >
                  <Play className="w-3.5 h-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => {
                    setEditingServer(server);
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

      {/* 本机私有 MCP(SECTIONS 表判定 desktop 构建;组件内仍有 Tauri 自检兜底) */}
      {isSectionVisible("localMcp", caps) && <LocalMcpSection />}

      <MCPServerDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSaved={load}
        editServer={editingServer}
      />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Skills Tab — 用户级技能 & 工具默认
// ═══════════════════════════════════════════════════════════════════════

function UserSkillsTab() {
  const { t } = useTranslation("drawersUi");
  const [skills, setSkills] = useState<Record<string, unknown>>({ ...SKILLS_DEFAULTS });
  const [tools, setTools] = useState<Record<string, unknown>>({
    builtin_tools_enabled: true,
    user_tools_enabled: true,
    workspace_tools_enabled: true,
  });
  const [loadedSkills, setLoadedSkills] = useState<Record<string, unknown> | null>(null);
  const [loadedTools, setLoadedTools] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await workspaceApi.getUserSkillsTools();
      const s = { ...SKILLS_DEFAULTS, ...(res.skills ?? {}) };
      const t = {
        builtin_tools_enabled: true,
        user_tools_enabled: true,
        workspace_tools_enabled: true,
        ...(res.tools ?? {}),
      };
      setSkills(s);
      setTools(t);
      setLoadedSkills(s);
      setLoadedTools(t);
    } catch {
      // 静默降级
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const dirty =
    (loadedSkills ? JSON.stringify(loadedSkills) !== JSON.stringify(skills) : false) ||
    (loadedTools ? JSON.stringify(loadedTools) !== JSON.stringify(tools) : false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await workspaceApi.updateUserSkillsTools({ skills, tools });
      const s = { ...SKILLS_DEFAULTS, ...res.skills };
      const loadedTools = {
        builtin_tools_enabled: true,
        user_tools_enabled: true,
        workspace_tools_enabled: true,
        ...res.tools,
      };
      setSkills(s);
      setTools(loadedTools);
      setLoadedSkills(s);
      setLoadedTools(loadedTools);
      toast.success(t("user.skills.toast.saved"));
    } catch {
      toast.error(t("user.skills.toast.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const setS = (key: string, value: unknown) => setSkills((prev) => ({ ...prev, [key]: value }));
  const setT = (key: string, value: unknown) => setTools((prev) => ({ ...prev, [key]: value }));

  return (
    <div className="space-y-4">
      <SectionTitle title={t("user.skills.title")} desc={t("user.skills.desc")} />
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          {/* Skills */}
          <div className="rounded-lg border border-border/60 p-3 space-y-0.5">
            <div className="text-xs font-medium text-muted-foreground mb-1">
              {t("user.skills.skillsTitle")}
            </div>
            <FieldRow label={t("user.skills.enableSkill")} hint={t("user.skills.enableSkillHint")}>
              <Switch checked={!!skills.enabled} onCheckedChange={(v) => setS("enabled", v)} />
            </FieldRow>
            <FieldRow
              label={t("user.skills.autoDiscover")}
              hint={t("user.skills.autoDiscoverHint")}
            >
              <Switch
                checked={!!skills.auto_discovery}
                onCheckedChange={(v) => setS("auto_discovery", v)}
              />
            </FieldRow>
          </div>
          {/* Tools */}
          <div className="rounded-lg border border-border/60 p-3 space-y-0.5">
            <div className="text-xs font-medium text-muted-foreground mb-1">
              {t("user.skills.toolsTitle")}
            </div>
            <FieldRow label={t("user.skills.builtin")} hint={t("user.skills.builtinHint")}>
              <Switch
                checked={!!tools.builtin_tools_enabled}
                onCheckedChange={(v) => setT("builtin_tools_enabled", v)}
              />
            </FieldRow>
            <FieldRow label={t("user.skills.userTools")} hint={t("user.skills.userToolsHint")}>
              <Switch
                checked={!!tools.user_tools_enabled}
                onCheckedChange={(v) => setT("user_tools_enabled", v)}
              />
            </FieldRow>
            <FieldRow label={t("user.skills.wsTools")} hint={t("user.skills.wsToolsHint")}>
              <Switch
                checked={!!tools.workspace_tools_enabled}
                onCheckedChange={(v) => setT("workspace_tools_enabled", v)}
              />
            </FieldRow>
          </div>
        </>
      )}
      <div className="flex justify-end">
        <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={!dirty || saving}>
          {saving ? (
            <Loader2 className="w-3 h-3 animate-spin mr-1" />
          ) : (
            <Save className="w-3 h-3 mr-1" />
          )}
          {t("user.skills.save")}
        </Button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Memory Tab — 用户级记忆默认
// ═══════════════════════════════════════════════════════════════════════

function UserMemoryTab() {
  const { t } = useTranslation("drawersUi");
  const [memory, setMemory] = useState<Record<string, unknown>>({ ...MEMORY_DEFAULTS });
  const [loaded, setLoaded] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await workspaceApi.getUserMemory();
      const m = { ...MEMORY_DEFAULTS, ...res };
      setMemory(m);
      setLoaded(m);
    } catch {
      // 静默降级
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const dirty = loaded ? JSON.stringify(loaded) !== JSON.stringify(memory) : false;

  const handleSave = async () => {
    setSaving(true);
    try {
      await workspaceApi.updateUserMemory(memory);
      setLoaded({ ...memory });
      toast.success(t("user.memory.toast.saved"));
    } catch {
      toast.error(t("user.memory.toast.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const set = (key: string, value: unknown) => setMemory((prev) => ({ ...prev, [key]: value }));

  return (
    <div className="space-y-4">
      <SectionTitle title={t("user.memory.title")} desc={t("user.memory.desc")} />
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="rounded-lg border border-border/60 p-3 space-y-0.5">
          <FieldRow label={t("user.memory.enable")}>
            <Switch checked={!!memory.enabled} onCheckedChange={(v) => set("enabled", v)} />
          </FieldRow>
          <Separator className="my-2" />
          <FieldRow label={t("user.memory.pageSize")}>
            <Input
              type="number"
              min={500}
              max={10000}
              value={Number(memory.virtual_page_size ?? 2000)}
              onChange={(e) => set("virtual_page_size", parseInt(e.target.value) || 2000)}
              className="h-7 w-28 text-xs"
            />
          </FieldRow>
          <FieldRow label={t("user.memory.maxPages")}>
            <Input
              type="number"
              min={1}
              max={20}
              value={Number(memory.max_active_pages ?? 5)}
              onChange={(e) => set("max_active_pages", parseInt(e.target.value) || 5)}
              className="h-7 w-28 text-xs"
            />
          </FieldRow>
          <FieldRow label={t("user.memory.defaultEnergy")}>
            <Input
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={Number(memory.default_energy ?? 1.0)}
              onChange={(e) => set("default_energy", parseFloat(e.target.value) || 1.0)}
              className="h-7 w-28 text-xs"
            />
          </FieldRow>
          <FieldRow label={t("user.memory.decayRate")}>
            <Input
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={Number(memory.energy_decay_rate ?? 0.95)}
              onChange={(e) => set("energy_decay_rate", parseFloat(e.target.value) || 0.95)}
              className="h-7 w-28 text-xs"
            />
          </FieldRow>
          <FieldRow label={t("user.memory.minEnergy")}>
            <Input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={Number(memory.min_energy_threshold ?? 0.2)}
              onChange={(e) => set("min_energy_threshold", parseFloat(e.target.value) || 0.2)}
              className="h-7 w-28 text-xs"
            />
          </FieldRow>
          <FieldRow label={t("user.memory.consolidation")}>
            <Switch
              checked={!!memory.consolidation_enabled}
              onCheckedChange={(v) => set("consolidation_enabled", v)}
            />
          </FieldRow>
        </div>
      )}
      <div className="flex justify-end">
        <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={!dirty || saving}>
          {saving ? (
            <Loader2 className="w-3 h-3 animate-spin mr-1" />
          ) : (
            <Save className="w-3 h-3 mr-1" />
          )}
          {t("user.memory.save")}
        </Button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Knowledge Tab — 用户级知识库默认
// ═══════════════════════════════════════════════════════════════════════

function UserKnowledgeTab() {
  const { t } = useTranslation("drawersUi");
  const [knowledge, setKnowledge] = useState<Record<string, unknown>>({ ...KNOWLEDGE_DEFAULTS });
  const [loaded, setLoaded] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await workspaceApi.getUserKnowledge();
      const k = { ...KNOWLEDGE_DEFAULTS, ...res };
      setKnowledge(k);
      setLoaded(k);
    } catch {
      // 静默降级
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const dirty = loaded ? JSON.stringify(loaded) !== JSON.stringify(knowledge) : false;

  const handleSave = async () => {
    setSaving(true);
    try {
      await workspaceApi.updateUserKnowledge(knowledge);
      setLoaded({ ...knowledge });
      toast.success(t("user.knowledge.toast.saved"));
    } catch {
      toast.error(t("user.knowledge.toast.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const set = (key: string, value: unknown) => setKnowledge((prev) => ({ ...prev, [key]: value }));

  return (
    <div className="space-y-4">
      <SectionTitle title={t("user.knowledge.title")} desc={t("user.knowledge.desc")} />
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="rounded-lg border border-border/60 p-3 space-y-0.5">
          <FieldRow label={t("user.knowledge.enable")}>
            <Switch checked={!!knowledge.enabled} onCheckedChange={(v) => set("enabled", v)} />
          </FieldRow>
          <Separator className="my-2" />
          <div className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground space-y-1 mb-2">
            <p className="font-medium text-foreground">{t("user.knowledge.engineTitle")}</p>
            <p>{t("user.knowledge.engineNote")}</p>
          </div>
          <FieldRow label={t("user.knowledge.vectorStore")}>
            <Input
              value={String(knowledge.vector_store_type ?? "sqlite-vec")}
              onChange={(e) => set("vector_store_type", e.target.value)}
              className="h-7 w-40 text-xs"
            />
          </FieldRow>
          <FieldRow label={t("user.knowledge.embeddingModel")}>
            <Input
              value={String(knowledge.embedding_model ?? "")}
              onChange={(e) => set("embedding_model", e.target.value)}
              className="h-7 w-56 text-xs"
            />
          </FieldRow>
          <FieldRow label={t("user.knowledge.dimension")}>
            <Input
              type="number"
              min={64}
              max={8192}
              value={Number(knowledge.dimension ?? 1024)}
              onChange={(e) => set("dimension", parseInt(e.target.value) || 1024)}
              className="h-7 w-28 text-xs"
            />
          </FieldRow>
          <FieldRow label={t("user.knowledge.chunkSize")}>
            <Input
              type="number"
              min={100}
              max={5000}
              value={Number(knowledge.chunk_size ?? 500)}
              onChange={(e) => set("chunk_size", parseInt(e.target.value) || 500)}
              className="h-7 w-28 text-xs"
            />
          </FieldRow>
          <FieldRow label={t("user.knowledge.chunkOverlap")}>
            <Input
              type="number"
              min={0}
              max={1000}
              value={Number(knowledge.chunk_overlap ?? 50)}
              onChange={(e) => set("chunk_overlap", parseInt(e.target.value) || 50)}
              className="h-7 w-28 text-xs"
            />
          </FieldRow>
          <FieldRow label={t("user.knowledge.topK")}>
            <Input
              type="number"
              min={1}
              max={100}
              value={Number(knowledge.default_top_k ?? 5)}
              onChange={(e) => set("default_top_k", parseInt(e.target.value) || 5)}
              className="h-7 w-28 text-xs"
            />
          </FieldRow>
          <FieldRow label={t("user.knowledge.retrievalMode")}>
            <Select
              value={String(knowledge.retrieval_mode ?? "hybrid")}
              onValueChange={(v) => set("retrieval_mode", v)}
            >
              <SelectTrigger className="h-7 w-36 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="hybrid">{t("user.knowledge.retrieval.hybrid")}</SelectItem>
                <SelectItem value="vector">{t("user.knowledge.retrieval.vector")}</SelectItem>
                <SelectItem value="fulltext">{t("user.knowledge.retrieval.fulltext")}</SelectItem>
              </SelectContent>
            </Select>
          </FieldRow>
          <FieldRow label={t("user.knowledge.ragContext")}>
            <Input
              type="number"
              min={500}
              max={32000}
              value={Number(knowledge.rag_context_length ?? 2000)}
              onChange={(e) => set("rag_context_length", parseInt(e.target.value) || 2000)}
              className="h-7 w-28 text-xs"
            />
          </FieldRow>
        </div>
      )}
      <div className="flex justify-end">
        <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={!dirty || saving}>
          {saving ? (
            <Loader2 className="w-3 h-3 animate-spin mr-1" />
          ) : (
            <Save className="w-3 h-3 mr-1" />
          )}
          {t("user.knowledge.save")}
        </Button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Preferences Tab（保持原有）
// ═══════════════════════════════════════════════════════════════════════

function PreferencesTab() {
  const { t } = useTranslation("drawersUi");
  const [notifications, setNotifications] = useState(() => {
    try {
      return localStorage.getItem("nn-pref-notifications") !== "0";
    } catch {
      return true;
    }
  });
  const [autoScroll, setAutoScroll] = useState(() => {
    try {
      return localStorage.getItem("nn-pref-autoscroll") !== "0";
    } catch {
      return true;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem("nn-pref-notifications", notifications ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [notifications]);
  useEffect(() => {
    try {
      localStorage.setItem("nn-pref-autoscroll", autoScroll ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [autoScroll]);

  const compactMode = useChatStore((s) => s.compactMode);
  const setCompactMode = useChatStore((s) => s.setCompactMode);

  return (
    <div className="space-y-4">
      <SectionTitle title={t("user.prefs.title")} desc={t("user.prefs.desc")} />
      <div className="flex items-center justify-between py-2">
        <div>
          <div className="text-sm font-medium flex items-center gap-1.5">
            <Bell className="w-3.5 h-3.5" />
            {t("user.prefs.notifications")}
          </div>
          <div className="text-xs text-muted-foreground">{t("user.prefs.notificationsHint")}</div>
        </div>
        <Switch checked={notifications} onCheckedChange={setNotifications} />
      </div>
      <div className="flex items-center justify-between py-2">
        <div>
          <div className="text-sm font-medium">{t("user.prefs.autoScroll")}</div>
          <div className="text-xs text-muted-foreground">{t("user.prefs.autoScrollHint")}</div>
        </div>
        <Switch checked={autoScroll} onCheckedChange={setAutoScroll} />
      </div>
      <div className="flex items-center justify-between py-2">
        <div>
          <div className="text-sm font-medium">{t("user.prefs.compact")}</div>
          <div className="text-xs text-muted-foreground">{t("user.prefs.compactHint")}</div>
        </div>
        <Switch checked={compactMode} onCheckedChange={setCompactMode} />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// About Tab（保持原有）
// ═══════════════════════════════════════════════════════════════════════

function AboutTab() {
  const { t } = useTranslation("drawersUi");
  const [appVersion, setAppVersion] = useState("—");
  useEffect(() => {
    if (IS_DESKTOP) {
      import("@tauri-apps/api/app")
        .then(({ getVersion }) => getVersion())
        .then((v) => setAppVersion(v))
        .catch(() => setAppVersion("2.0.0"));
    } else {
      setAppVersion("1.0-beta");
    }
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 pb-4 border-b border-border/60">
        <div className="w-10 h-10 rounded-lg bg-gradient-brand flex items-center justify-center shadow-brand shrink-0">
          <Info className="w-5 h-5 text-[oklch(0.16_0.03_250)]" strokeWidth={2.5} />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-base font-semibold">NormNomos</span>
          <span className="text-xs text-muted-foreground">{t("user.about.tagline")}</span>
        </div>
      </div>
      <div className="space-y-2 text-sm">
        <div className="flex justify-between py-1.5 border-b border-border/50">
          <span className="text-muted-foreground">{t("user.about.version")}</span>
          <span className="font-mono">{appVersion}</span>
        </div>
        <div className="flex justify-between py-1.5 border-b border-border/50">
          <span className="text-muted-foreground">{t("user.about.product")}</span>
          <span>{t("user.about.productValue")}</span>
        </div>
        <div className="flex justify-between py-1.5 border-b border-border/50">
          <span className="text-muted-foreground">{t("user.about.architecture")}</span>
          <span>AI-Native Agent Engine</span>
        </div>
        <p className="text-xs text-muted-foreground pt-2 text-center">
          © {new Date().getFullYear()} NormNomos. All rights reserved.
        </p>
      </div>
    </div>
  );
}
