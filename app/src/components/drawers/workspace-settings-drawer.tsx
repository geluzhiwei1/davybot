/**
 * WorkspaceSettingsDrawer — Tabbed workspace configuration panel.
 * Tabs: LLM, MCP, Agent, Memory, Knowledge, Skills, Tools, ACP, Channels, Security, General.
 * Each tab calls workspace-scoped backend APIs.
 */
import { useEffect, useState, useCallback, type ReactNode } from "react";
import {
  Settings,
  Trash2,
  Loader2,
  Save,
  RotateCcw,
  Bot,
  Brain,
  Database,
  Zap,
  Wrench,
  FolderOpen,
  Cpu,
  Plug,
  Shield,
  Radio,
  Plus,
  RefreshCw,
  Search,
  Play,
  Pencil,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { AppDrawer } from "./app-drawer";
import { SecurityPolicyForm } from "@/components/security/security-policy-form";
import { useStore } from "@/lib/store";
import {
  API_PROVIDERS,
  resolveBaseUrlOnProviderChange,
  fetchProviderPresets,
  type ApiProviderPreset,
} from "@/lib/llm-providers";
import {
  workspaceApi,
  llmApi,
  wsMcpApi,
  acpAgentApi,
  channelApi,
  type WorkspaceConfig,
  type LLMProviderItem,
  type LLMProviderCreatePayload,
  type WsMcpServerConfig,
  type AcpAgentInfo,
  type ChannelInfo,
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

// ── Tab trigger style ────────────────────────────────────────────────
const tabCls =
  "text-xs justify-start text-muted-foreground data-[state=active]:bg-brand/10 data-[state=active]:text-brand data-[state=active]:font-medium rounded-md px-2.5 py-1.5 text-left font-normal";

// 分组导航结构：11 tab 按域分组（label/text 为 i18n key，渲染时经 t() 翻译）
const NAV_GROUPS: { label: string; items: { value: string; icon: ReactNode; text: string }[] }[] = [
  {
    label: "ws.nav.groupModels",
    items: [
      { value: "llm", icon: <Cpu className="w-3.5 h-3.5" />, text: "ws.nav.llm" },
      { value: "mcp", icon: <Plug className="w-3.5 h-3.5" />, text: "ws.nav.mcp" },
      { value: "skills", icon: <Zap className="w-3.5 h-3.5" />, text: "ws.nav.skills" },
      { value: "tools", icon: <Wrench className="w-3.5 h-3.5" />, text: "ws.nav.tools" },
    ],
  },
  {
    label: "ws.nav.groupRuntime",
    items: [
      { value: "agent", icon: <Bot className="w-3.5 h-3.5" />, text: "ws.nav.agent" },
      { value: "memory", icon: <Brain className="w-3.5 h-3.5" />, text: "ws.nav.memory" },
    ],
  },
  {
    label: "ws.nav.groupKnowledge",
    items: [
      { value: "knowledge", icon: <Database className="w-3.5 h-3.5" />, text: "ws.nav.knowledge" },
    ],
  },
  {
    label: "ws.nav.groupIntegration",
    items: [
      { value: "acp", icon: <Bot className="w-3.5 h-3.5" />, text: "ACP" },
      { value: "channels", icon: <Radio className="w-3.5 h-3.5" />, text: "Channels" },
    ],
  },
  {
    label: "ws.nav.groupSecurity",
    items: [
      { value: "security", icon: <Shield className="w-3.5 h-3.5" />, text: "ws.nav.security" },
      { value: "general", icon: <FolderOpen className="w-3.5 h-3.5" />, text: "ws.nav.general" },
    ],
  },
];

export function WorkspaceSettingsDrawer() {
  const { t } = useTranslation("drawersUi");
  const workspaces = useStore((s) => s.workspaces);
  const filesDrawerFor = useStore((s) => s.filesDrawerFor);
  const renameWorkspace = useStore((s) => s.renameWorkspace);
  const deleteWorkspace = useStore((s) => s.deleteWorkspace);
  const activeDrawer = useStore((s) => s.activeDrawer);

  const ws = filesDrawerFor ? workspaces.find((w) => w.id === filesDrawerFor) : undefined;

  const [config, setConfig] = useState<WorkspaceConfig | null>(null);
  const [userSkillsTools, setUserSkillsTools] = useState<{
    skills: Record<string, unknown>;
    tools: Record<string, unknown>;
  }>({ skills: {}, tools: {} });
  const [userMemory, setUserMemory] = useState<Record<string, unknown>>({});
  const [userKnowledge, setUserKnowledge] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Fetch config when drawer opens
  useEffect(() => {
    if (activeDrawer === "workspace-settings" && ws?.id) {
      setLoading(true);
      setDirty(false);
      workspaceApi
        .getConfig(ws.id)
        .then((res) => setConfig(res.config ?? {}))
        .catch((e) => {
          toastError(t("ws.toast.loadFailed"), e);
          setConfig({});
        })
        .finally(() => setLoading(false));
      // 加载用户级 Skills/Tools 默认（override-or-inherit 来源标注用）
      workspaceApi
        .getUserSkillsTools()
        .then((res) => setUserSkillsTools({ skills: res.skills ?? {}, tools: res.tools ?? {} }))
        .catch(() => {});
      // 加载用户级 Memory/Knowledge 默认（override-or-inherit，C 阶段新增）
      workspaceApi
        .getUserMemory()
        .then((r) => setUserMemory(r ?? {}))
        .catch(() => {});
      workspaceApi
        .getUserKnowledge()
        .then((r) => setUserKnowledge(r ?? {}))
        .catch(() => {});
    }
  }, [activeDrawer, ws?.id, t]);

  const updateSection = useCallback(
    <K extends keyof WorkspaceConfig>(
      section: K,
      patch: Partial<NonNullable<WorkspaceConfig[K]>>,
    ) => {
      setConfig((prev) => {
        if (!prev) return prev;
        const current = prev[section] ?? {};
        return { ...prev, [section]: { ...current, ...patch } };
      });
      setDirty(true);
    },
    [],
  );

  // override-or-inherit 来源标注：对比 workspace config 值与 user 默认值，返回彩色 Badge
  const srcBadge = (section: string, field: string) => {
    const userMap: Record<string, Record<string, unknown>> = {
      skills: (userSkillsTools.skills ?? {}) as Record<string, unknown>,
      tools: (userSkillsTools.tools ?? {}) as Record<string, unknown>,
      memory: userMemory ?? {},
      knowledge: userKnowledge ?? {},
    };
    const wsVal = (config as Record<string, Record<string, unknown>> | null)?.[section]?.[field];
    const userVal = userMap[section]?.[field];
    if (userVal === undefined) return null;
    if (wsVal !== userVal) {
      return (
        <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-600 ml-2">
          {t("ws.badge.overridden")}
        </Badge>
      );
    }
    return (
      <Badge variant="outline" className="text-[10px] bg-blue-500/10 text-blue-600 ml-2">
        {t("ws.badge.inherited")}
      </Badge>
    );
  };

  const handleSave = async () => {
    if (!ws?.id || !config) return;
    setSaving(true);
    try {
      const res = await workspaceApi.updateConfig(ws.id, config);
      setConfig(res.config ?? config);
      setDirty(false);
      // 运行参数类设置（大模型/MCP/记忆/技能/工具等）在 Agent 创建时读取——Agent 按
      // 任务缓存，故新设置在「下一个任务/会话」生效，非即时。前端不再假装即时生效。
      toast.success(t("ws.save.success"));
    } catch (err) {
      console.error("[WsSettings] save failed:", err);
      toastError(t("ws.save.failed"), err);
    } finally {
      setSaving(false);
    }
  };

  // No workspace context
  if (!ws) {
    return (
      <AppDrawer
        id="workspace-settings"
        title={t("ws.drawer.titleNoWs")}
        description={t("ws.drawer.descNoWs")}
        icon={Settings}
        width="w-full sm:w-[520px] sm:max-w-[560px]"
      >
        <div className="p-6 text-center text-sm text-muted-foreground">
          {t("ws.drawer.noWsPrompt")}
        </div>
      </AppDrawer>
    );
  }

  return (
    <AppDrawer
      id="workspace-settings"
      title={t("ws.drawer.title", { name: ws.name })}
      description={t("ws.drawer.description")}
      icon={Settings}
      width="w-full sm:w-[760px] sm:max-w-[800px]"
    >
      <div className="flex flex-col h-full">
        {/* Save bar */}
        {dirty && (
          <div className="flex items-center gap-2 px-4 py-2 border-b border-border/60 bg-brand/5">
            <span className="text-xs text-muted-foreground flex-1">{t("ws.savebar.dirty")}</span>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs gap-1"
              onClick={() => {
                setDirty(false);
                workspaceApi.getConfig(ws.id).then((res) => setConfig(res.config ?? {}));
              }}
            >
              <RotateCcw className="w-3 h-3" /> {t("ws.savebar.reset")}
            </Button>
            <Button size="sm" className="h-7 text-xs gap-1" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}{" "}
              {t("ws.savebar.save")}
            </Button>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <Tabs defaultValue="llm" className="flex-1 flex flex-row min-h-0">
            <TabsList className="flex flex-col w-44 shrink-0 items-stretch justify-start rounded-none border-r border-border/60 bg-transparent p-2 gap-0.5 overflow-y-auto scrollbar-thin h-auto">
              {NAV_GROUPS.flatMap((g) => [
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
                <LLMTab workspaceId={ws.id} />
              </TabsContent>
              <TabsContent value="mcp" className="p-4 mt-0">
                <MCPTab workspaceId={ws.id} />
              </TabsContent>
              <TabsContent value="agent" className="p-4 space-y-4 mt-0">
                <SectionTitle title={t("ws.agent.title")} desc={t("ws.agent.desc")} />
                {/* Agent 模式 (orchestrator/pdca) 已改为系统内部自动管理，用户无需手动选择。
                    专家 (Expert) 通过聊天输入框 @ 选择，或由 LLM 自动匹配。 */}
                <FieldRow label={t("ws.agent.confirmBeforeExec")}>
                  <Switch
                    checked={config?.agent?.plan_mode_confirm_required ?? true}
                    onCheckedChange={(v) =>
                      updateSection("agent", { plan_mode_confirm_required: v })
                    }
                  />
                </FieldRow>
                {/* 自动模式切换已隐藏：mode 为系统内部概念，由 LLM 自主决策 */}
                {/* 「自动批准工具调用」已移除：原字段写而不读，真正的工具审批由安全策略
                    ApprovalGate 控制——见 apps/工作区设置升级方案.md §6/附录B。 */}
                <FieldRow label={t("ws.agent.maxConcurrent")}>
                  <Input
                    type="number"
                    min={1}
                    max={10}
                    value={config?.agent?.max_concurrent_subtasks ?? 3}
                    onChange={(e) =>
                      updateSection("agent", {
                        max_concurrent_subtasks: parseInt(e.target.value) || 3,
                      })
                    }
                    className="h-8 text-xs w-24"
                  />
                </FieldRow>
              </TabsContent>

              {/* ── Memory Tab ──────────────────────────── */}
              <TabsContent value="memory" className="p-4 space-y-4 mt-0">
                <SectionTitle title={t("ws.memory.title")} desc={t("ws.memory.desc")} />
                <FieldRow
                  label={
                    <>
                      {t("ws.memory.enable")}
                      {srcBadge("memory", "enabled")}
                    </>
                  }
                >
                  <Switch
                    checked={config?.memory?.enabled ?? true}
                    onCheckedChange={(v) => updateSection("memory", { enabled: v })}
                  />
                </FieldRow>
                <Separator />
                <FieldRow label={t("ws.memory.pageSize")}>
                  <Input
                    type="number"
                    min={500}
                    max={10000}
                    value={config?.memory?.virtual_page_size ?? 2000}
                    onChange={(e) =>
                      updateSection("memory", {
                        virtual_page_size: parseInt(e.target.value) || 2000,
                      })
                    }
                    className="h-8 text-xs w-28"
                  />
                </FieldRow>
                <FieldRow label={t("ws.memory.maxPages")}>
                  <Input
                    type="number"
                    min={1}
                    max={20}
                    value={config?.memory?.max_active_pages ?? 5}
                    onChange={(e) =>
                      updateSection("memory", { max_active_pages: parseInt(e.target.value) || 5 })
                    }
                    className="h-8 text-xs w-28"
                  />
                </FieldRow>
                <FieldRow label={t("ws.memory.defaultEnergy")}>
                  <Input
                    type="number"
                    min={0}
                    max={2}
                    step={0.1}
                    value={config?.memory?.default_energy ?? 1.0}
                    onChange={(e) =>
                      updateSection("memory", { default_energy: parseFloat(e.target.value) || 1.0 })
                    }
                    className="h-8 text-xs w-28"
                  />
                </FieldRow>
                <FieldRow label={t("ws.memory.decayRate")}>
                  <Input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={config?.memory?.energy_decay_rate ?? 0.95}
                    onChange={(e) =>
                      updateSection("memory", {
                        energy_decay_rate: parseFloat(e.target.value) || 0.95,
                      })
                    }
                    className="h-8 text-xs w-28"
                  />
                </FieldRow>
                <FieldRow label={t("ws.memory.minEnergy")}>
                  <Input
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={config?.memory?.min_energy_threshold ?? 0.2}
                    onChange={(e) =>
                      updateSection("memory", {
                        min_energy_threshold: parseFloat(e.target.value) || 0.2,
                      })
                    }
                    className="h-8 text-xs w-28"
                  />
                </FieldRow>
              </TabsContent>

              {/* ── Knowledge Tab ───────────────────────── */}
              <TabsContent value="knowledge" className="p-4 space-y-4 mt-0">
                <SectionTitle title={t("ws.knowledge.title")} desc={t("ws.knowledge.desc")} />
                <FieldRow
                  label={
                    <>
                      {t("ws.knowledge.enable")}
                      {srcBadge("knowledge", "enabled")}
                    </>
                  }
                >
                  <Switch
                    checked={config?.knowledge?.enabled ?? true}
                    onCheckedChange={(v) => updateSection("knowledge", { enabled: v })}
                  />
                </FieldRow>
                <Separator />
                {/* 引擎参数（嵌入模型/向量维度/分块/检索模式等）已移出工作区设置：运行时按每个
                    知识库实体自身的 kb.settings 工作，工作区 config.knowledge 段是写而不读的
                    第三套。请在「知识库」页面管理各 KB 的引擎参数。
                    见 apps/工作区设置升级方案.md 附录B。 */}
                <div className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground space-y-1">
                  <p className="font-medium text-foreground">{t("ws.knowledge.engineNoteTitle")}</p>
                  <p>{t("ws.knowledge.engineNote")}</p>
                </div>
              </TabsContent>

              {/* ── Skills Tab ──────────────────────────── */}
              <TabsContent value="skills" className="p-4 space-y-4 mt-0">
                <SectionTitle title={t("ws.skills.title")} desc={t("ws.skills.desc")} />
                <FieldRow
                  label={
                    <>
                      {t("ws.skills.enable")}
                      {srcBadge("skills", "enabled")}
                    </>
                  }
                >
                  <Switch
                    checked={config?.skills?.enabled ?? true}
                    onCheckedChange={(v) => updateSection("skills", { enabled: v })}
                  />
                </FieldRow>
                <FieldRow
                  label={
                    <>
                      {t("ws.skills.autoDiscovery")}
                      {srcBadge("skills", "auto_discovery")}
                    </>
                  }
                >
                  <Switch
                    checked={config?.skills?.auto_discovery ?? true}
                    onCheckedChange={(v) => updateSection("skills", { auto_discovery: v })}
                  />
                </FieldRow>
              </TabsContent>

              {/* ── Tools Tab ───────────────────────────── */}
              <TabsContent value="tools" className="p-4 space-y-4 mt-0">
                <SectionTitle title={t("ws.tools.title")} desc={t("ws.tools.desc")} />
                <FieldRow
                  label={
                    <>
                      {t("ws.tools.builtin")}
                      {srcBadge("tools", "builtin_tools_enabled")}
                    </>
                  }
                >
                  <Switch
                    checked={config?.tools?.builtin_tools_enabled ?? true}
                    onCheckedChange={(v) => updateSection("tools", { builtin_tools_enabled: v })}
                  />
                </FieldRow>
                <FieldRow
                  label={
                    <>
                      {t("ws.tools.system")}
                      {srcBadge("tools", "system_tools_enabled")}
                    </>
                  }
                >
                  <Switch
                    checked={config?.tools?.system_tools_enabled ?? true}
                    onCheckedChange={(v) => updateSection("tools", { system_tools_enabled: v })}
                  />
                </FieldRow>
              </TabsContent>

              <TabsContent value="acp" className="p-4 mt-0">
                <ACPTab workspaceId={ws.id} />
              </TabsContent>
              <TabsContent value="channels" className="p-4 mt-0">
                <ChannelsTab workspaceId={ws.id} />
              </TabsContent>
              <TabsContent value="security" className="p-4 mt-0">
                <SecurityTab workspaceId={ws.id} />
              </TabsContent>

              {/* ── General Tab ─────────────────────────── */}
              <TabsContent value="general" className="p-4 space-y-4 mt-0">
                <SectionTitle title={t("ws.general.title")} desc={t("ws.general.desc")} />
                <FieldRow label={t("ws.general.name")}>
                  <Input
                    value={ws.name}
                    onChange={(e) => renameWorkspace(ws.id, e.target.value)}
                    className="h-8 text-sm"
                  />
                </FieldRow>
                <div className="text-xs text-muted-foreground">
                  {t("ws.general.files", {
                    count: ws.files.length,
                    date: new Date(ws.createdAt).toLocaleDateString(),
                  })}
                </div>
                <Separator />
                <div className="flex justify-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs text-destructive hover:text-destructive gap-1.5"
                    onClick={() => {
                      if (confirm(t("ws.general.confirmDelete", { name: ws.name })))
                        deleteWorkspace(ws.id);
                    }}
                  >
                    <Trash2 className="w-3 h-3" /> {t("ws.general.deleteWorkspace")}
                  </Button>
                </div>
              </TabsContent>
            </div>
          </Tabs>
        )}
      </div>
    </AppDrawer>
  );
}

// ── LLM Tab (workspace-scoped providers) ────────────────────────────

// API provider 预设（含官方默认 base_url）见 @/lib/llm-providers

const emptyLLMForm: LLMProviderCreatePayload = {
  name: "",
  apiProvider: "openai",
  openAiBaseUrl: "https://api.openai.com/v1",
  openAiApiKey: "",
  openAiModelId: "",
  temperature: 0.7,
  timeout: 600,
  maxRetries: 3,
  retryDelay: 2,
  saveLocation: "workspace",
};

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
  // Provider 下拉预设：优先后端目录，静态列表兜底
  const [providerPresets, setProviderPresets] = useState<ApiProviderPreset[]>(API_PROVIDERS);

  useEffect(() => {
    if (open) {
      fetchProviderPresets(workspaceId)
        .then(setProviderPresets)
        .catch(() => setProviderPresets(API_PROVIDERS));
      if (editProvider) {
        const cfg = editProvider.config?.config ?? {};
        setForm({
          name: editProvider.name,
          apiProvider: cfg.apiProvider ?? "openai",
          openAiBaseUrl: cfg.openAiBaseUrl ?? "",
          openAiApiKey: cfg.openAiApiKey ?? "",
          openAiModelId: cfg.openAiModelId ?? "",
          temperature: cfg.temperature ?? 0.7,
          timeout: cfg.timeout ?? 600,
          maxRetries: cfg.maxRetries ?? 3,
          retryDelay: cfg.retryDelay ?? 2,
          toolChoice: cfg.toolChoice ?? undefined,
          saveLocation: (editProvider.source as "user" | "workspace") ?? "workspace",
        });
      } else {
        setForm(emptyLLMForm);
      }
      setTestResult(null);
    }
  }, [open, editProvider]);

  const update = (patch: Partial<LLMProviderCreatePayload>) => setForm((f) => ({ ...f, ...patch }));

  const handleSave = async () => {
    if (!form.name.trim() || !form.apiProvider) {
      toast.error(t("ws.llm.toast.nameProviderRequired"));
      return;
    }
    setSaving(true);
    try {
      if (isEdit) {
        await llmApi.updateProvider(workspaceId, editProvider!.name, {
          ...form,
          saveLocation: undefined,
        });
        toast.success(t("ws.llm.toast.updated", { name: form.name }));
      } else {
        await llmApi.createProvider(workspaceId, form);
        toast.success(t("ws.llm.toast.created", { name: form.name }));
      }
      onSaved();
      onOpenChange(false);
    } catch {
      toast.error(isEdit ? t("ws.llm.toast.updateFailed") : t("ws.llm.toast.createFailed"));
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
          ? { ok: true, text: t("ws.llm.test.supported", { model: res.model || "—" }) }
          : {
              ok: false,
              text: t("ws.llm.test.unsupported", {
                message: res.message || t("ws.llm.test.unknown"),
              }),
            },
      );
      toast.success(res.supported ? t("ws.llm.test.ok") : t("ws.llm.test.notPassed"));
    } catch (e) {
      const detail = apiErrorDetail(e);
      setTestResult({ ok: false, text: t("ws.llm.test.requestFailed", { detail }) });
      toast.error(t("ws.llm.test.toastFailed"), { description: detail });
    } finally {
      setTesting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto scrollbar-thin">
        <DialogHeader>
          <DialogTitle className="text-sm">
            {isEdit ? t("ws.llm.dialog.editTitle") : t("ws.llm.dialog.addTitle")}
          </DialogTitle>
          <DialogDescription className="text-xs">
            {isEdit ? t("ws.llm.dialog.editDesc") : t("ws.llm.dialog.addDesc")}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {/* Name + Provider type */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("ws.llm.form.name")}</Label>
              <Input
                placeholder={t("ws.llm.form.namePlaceholder")}
                value={form.name}
                onChange={(e) => update({ name: e.target.value })}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t("ws.llm.form.provider")}</Label>
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

          {/* Base URL */}
          <div className="space-y-1.5">
            <Label className="text-xs">Base URL</Label>
            <Input
              placeholder="https://api.openai.com/v1"
              value={form.openAiBaseUrl ?? ""}
              onChange={(e) => update({ openAiBaseUrl: e.target.value || undefined })}
              className="h-8 text-xs"
            />
          </div>

          {/* API Key + Model ID */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">API Key</Label>
              <Input
                type="password"
                placeholder={isEdit ? t("ws.llm.form.keepKey") : "sk-..."}
                value={form.openAiApiKey ?? ""}
                onChange={(e) => update({ openAiApiKey: e.target.value || undefined })}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t("ws.llm.form.modelId")}</Label>
              <Input
                placeholder={t("ws.llm.form.modelPlaceholder")}
                value={form.openAiModelId ?? ""}
                onChange={(e) => update({ openAiModelId: e.target.value || undefined })}
                className="h-8 text-xs"
              />
            </div>
          </div>

          {/* Advanced */}
          <Separator />
          <p className="text-[11px] text-muted-foreground">{t("ws.llm.form.advanced")}</p>
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
                  <SelectValue placeholder={t("ws.llm.form.default")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">{t("ws.llm.form.default")}</SelectItem>
                  <SelectItem value="auto">auto</SelectItem>
                  <SelectItem value="required">required</SelectItem>
                  <SelectItem value="none">none</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("ws.llm.form.timeout")}</Label>
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
              <Label className="text-xs">{t("ws.llm.form.maxRetries")}</Label>
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
              <Label className="text-xs">{t("ws.llm.form.retryDelay")}</Label>
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

          {/* Save location (create only) */}
          <Separator />
          <div className="space-y-1.5">
            <Label className="text-xs">{t("ws.llm.form.saveLocation")}</Label>
            <div className="flex gap-3">
              <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                <input
                  type="radio"
                  name="saveLocation"
                  value="workspace"
                  checked={form.saveLocation === "workspace"}
                  onChange={() => update({ saveLocation: "workspace" })}
                  className="accent-brand"
                />
                {t("ws.llm.form.workspaceLevel")}{" "}
                <span className="text-[10px] text-muted-foreground">
                  {t("ws.llm.form.workspaceLevelHint")}
                </span>
              </label>
              <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                <input
                  type="radio"
                  name="saveLocation"
                  value="user"
                  checked={form.saveLocation === "user"}
                  onChange={() => update({ saveLocation: "user" })}
                  className="accent-brand"
                />
                {t("ws.llm.form.userLevel")}{" "}
                <span className="text-[10px] text-muted-foreground">
                  {t("ws.llm.form.userLevelHint")}
                </span>
              </label>
            </div>
          </div>

          {/* Test mode */}
          <div className="space-y-1.5">
            <Label className="text-xs">{t("ws.llm.form.testMode")}</Label>
            <Select
              value={testMode}
              onValueChange={(v) => setTestMode(v as "stream" | "non-stream")}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="non-stream">{t("ws.llm.form.nonStream")}</SelectItem>
                <SelectItem value="stream">{t("ws.llm.form.stream")}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Test result */}
          {testResult && (
            <div
              className={`text-xs p-2 rounded ${testResult.ok ? "bg-green-500/10 text-green-600" : "bg-yellow-500/10 text-yellow-600"}`}
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
            {t("ws.llm.test.connection")}
          </Button>
          <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 className="w-3 h-3 animate-spin mr-1" />
            ) : (
              <Save className="w-3 h-3 mr-1" />
            )}
            {isEdit ? t("ws.llm.action.saveChanges") : t("ws.llm.action.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function LLMTab({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation("drawersUi");
  const [providers, setProviders] = useState<LLMProviderItem[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<LLMProviderItem | null>(null);
  // 网关（官方/积分）双轨合并：网关模型数 + 积分余额（网关不可达时为 null，优雅降级）
  const [gatewayModelCount, setGatewayModelCount] = useState<number | null>(null);
  const [credits, setCredits] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await llmApi.listEffective(workspaceId);
      // effective 已合并同名（workspace 覆盖 user）；映射回 LLMProviderItem 复用现有渲染
      const mapped: LLMProviderItem[] = (res.effective ?? []).map((e) => ({
        name: e.name,
        source: (e.source === "workspace" ? "workspace" : "user") as "user" | "workspace",
        config: { config: e.config, source: e.source },
      }));
      setProviders(mapped);
      setCurrent(res.current ?? null);
    } catch (e) {
      toastError(t("ws.llm.toast.loadFailed"), e);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, t]);

  // 网关双轨：best-effort 拉取（support 系统可能未联调，失败则降级为"不可用"）
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
      await llmApi.deleteProvider(workspaceId, name);
      toast.success(t("ws.llm.toast.deleted", { name }));
      load();
    } catch {
      toast.error(t("ws.llm.toast.deleteFailed"));
    }
  };

  const handleSetCurrent = async (name: string) => {
    try {
      await llmApi.updateSettings(workspaceId, { currentApiConfigName: name });
      setCurrent(name);
      toast.success(t("ws.llm.toast.switched", { name }));
    } catch {
      toast.error(t("ws.llm.toast.switchFailed"));
    }
  };

  const openAdd = () => {
    setEditingProvider(null);
    setDialogOpen(true);
  };
  const openEdit = (p: LLMProviderItem) => {
    setEditingProvider(p);
    setDialogOpen(true);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionTitle title={t("ws.llm.tab.title")} desc={t("ws.llm.tab.desc")} />
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={load} disabled={loading} className="h-7">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={openAdd}>
            <Plus className="w-3 h-3 mr-1" /> {t("ws.llm.tab.add")}
          </Button>
        </div>
      </div>

      {/* 网关模型（官方/积分）—— 双轨合并：与自带 Key 一处呈现 */}
      <div className="rounded-lg border border-border bg-card/40 p-3 space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium">{t("ws.llm.gateway.title")}</span>
          <Badge variant="outline" className="text-[10px]">
            {gatewayModelCount === null
              ? t("ws.llm.gateway.unavailable")
              : t("ws.llm.gateway.modelsCount", { count: gatewayModelCount })}
          </Badge>
        </div>
        <p className="text-[11px] text-muted-foreground">
          {t("ws.llm.gateway.note")}
          {credits !== null ? t("ws.llm.gateway.creditsBalance", { credits }) : ""}
        </p>
      </div>

      {providers.length === 0 ? (
        <div className="text-center py-8 text-xs text-muted-foreground border border-dashed border-border rounded-lg">
          {t("ws.llm.empty")}
        </div>
      ) : (
        <div className="space-y-2">
          <div className="text-[11px] text-muted-foreground px-1">
            {t("ws.llm.countSummary", { count: providers.length })}
            <span className="text-blue-600 ml-1">
              {t("ws.llm.userCount", {
                count: providers.filter((p) => p.source === "user").length,
              })}
            </span>
            {providers.filter((p) => p.source === "workspace").length > 0 && (
              <span className="text-green-600 ml-1">
                {t("ws.llm.wsCount", {
                  count: providers.filter((p) => p.source === "workspace").length,
                })}
              </span>
            )}
          </div>
          {providers.map((p) => {
            const isActive = p.name === current;
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
                    <Badge
                      variant={p.source === "user" ? "secondary" : "default"}
                      className={
                        p.source === "user"
                          ? "text-[10px] bg-blue-500/10 text-blue-500"
                          : "text-[10px] bg-brand/10 text-brand"
                      }
                    >
                      {p.source === "user" ? t("ws.llm.badge.user") : t("ws.llm.badge.workspace")}
                    </Badge>
                  </div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {cfg?.openAiModelId ?? cfg?.apiProvider ?? "—"}
                    {cfg?.openAiBaseUrl ? ` · ${cfg.openAiBaseUrl}` : ""}
                  </div>
                </div>
                <Badge
                  variant={isActive ? "default" : "outline"}
                  className={
                    isActive ? "bg-brand text-brand-foreground text-[10px]" : "text-[10px]"
                  }
                >
                  {isActive ? t("ws.llm.badge.current") : t("ws.llm.badge.available")}
                </Badge>
                {!isActive && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 text-xs"
                    onClick={() => handleSetCurrent(p.name)}
                  >
                    {t("ws.llm.action.switch")}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0"
                  onClick={() => openEdit(p)}
                  title={t("ws.llm.action.edit")}
                >
                  <Pencil className="w-3 h-3" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0"
                  onClick={() => handleDelete(p.name)}
                  title={t("ws.llm.action.delete")}
                >
                  <Trash2 className="w-3 h-3 text-destructive" />
                </Button>
              </div>
            );
          })}
        </div>
      )}

      <LLMProviderDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        workspaceId={workspaceId}
        onSaved={load}
        editProvider={editingProvider}
      />
    </div>
  );
}

// ── MCP Tab (workspace-scoped) ───────────────────────────────────────

const emptyMCPForm: WsMcpServerConfig = {
  name: "",
  command: "",
  args: [],
  cwd: "",
  env: {},
  transport: "stdio",
  url: "",
  headers: {},
  timeout: 300,
  always_allow: [],
  disabled: false,
};

function MCPServerDialog({
  open,
  onOpenChange,
  workspaceId,
  onSaved,
  editServer,
  override = false,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  workspaceId: string;
  onSaved: () => void;
  editServer?: WsMcpServerConfig | null;
  override?: boolean;
}) {
  const { t } = useTranslation("drawersUi");
  const isEdit = !!editServer && !override;
  const isOverride = override;
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
      toast.error(t("ws.mcp.toast.nameCommandRequired"));
      return;
    }
    setSaving(true);
    try {
      if (isOverride) {
        // 继承级 → 为本工作区创建同名覆盖
        await wsMcpApi.addServer(workspaceId, { ...form, name: editServer!.name });
        toast.success(t("ws.mcp.toast.overrideSaved", { name: form.name }));
      } else if (isEdit) {
        await wsMcpApi.updateServer(workspaceId, editServer!.name, { ...form, name: undefined });
        toast.success(t("ws.mcp.toast.updated", { name: form.name }));
      } else {
        await wsMcpApi.addServer(workspaceId, form);
        toast.success(t("ws.mcp.toast.created", { name: form.name }));
      }
      onSaved();
      onOpenChange(false);
    } catch {
      toast.error(
        isOverride
          ? t("ws.mcp.toast.overrideFailed")
          : isEdit
            ? t("ws.mcp.toast.updateFailed")
            : t("ws.mcp.toast.createFailed"),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!form.name.trim()) {
      toast.error(t("ws.mcp.toast.nameRequired"));
      return;
    }
    setTesting(true);
    try {
      // For new servers, save first then test; for existing, test directly
      if (!isEdit) {
        await wsMcpApi.addServer(workspaceId, form);
        onSaved();
      }
      const res = await wsMcpApi.testServer(workspaceId, form.name);
      toast.success(res.message || t("ws.mcp.toast.testPassed"));
    } catch {
      toast.error(t("ws.mcp.toast.testFailedConn"));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto scrollbar-thin">
        <DialogHeader>
          <DialogTitle className="text-sm">
            {isOverride
              ? t("ws.mcp.dialog.overrideTitle")
              : isEdit
                ? t("ws.mcp.dialog.editTitle")
                : t("ws.mcp.dialog.addTitle")}
          </DialogTitle>
          <DialogDescription className="text-xs">
            {isOverride ? t("ws.mcp.dialog.overrideDesc") : t("ws.mcp.dialog.desc")}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {/* Name */}
          <div className="space-y-1.5">
            <Label className="text-xs">{t("ws.mcp.form.name")}</Label>
            <Input
              placeholder={t("ws.mcp.form.namePlaceholder")}
              value={form.name}
              disabled={isEdit || isOverride}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="h-8 text-xs"
            />
          </div>

          {/* Transport */}
          <div className="space-y-1.5">
            <Label className="text-xs">{t("ws.mcp.form.transport")}</Label>
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
                <SelectItem value="stdio">{t("ws.mcp.form.stdioOption")}</SelectItem>
                <SelectItem value="sse">{t("ws.mcp.form.sseOption")}</SelectItem>
                <SelectItem value="http">{t("ws.mcp.form.httpOption")}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {form.transport === "sse" || form.transport === "http" ? (
            <div className="space-y-1.5">
              <Label className="text-xs">URL *</Label>
              <Input
                placeholder={
                  form.transport === "sse"
                    ? t("ws.mcp.form.sseUrlPlaceholder")
                    : t("ws.mcp.form.httpUrlPlaceholder")
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
                  <Label className="text-xs">{t("ws.mcp.form.command")}</Label>
                  <Input
                    placeholder={t("ws.mcp.form.commandPlaceholder")}
                    value={form.command ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{t("ws.mcp.form.cwd")}</Label>
                  <Input
                    placeholder={t("ws.mcp.form.cwdPlaceholder")}
                    value={form.cwd ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, cwd: e.target.value || undefined }))}
                    className="h-8 text-xs"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">
                  {t("ws.mcp.form.args")}{" "}
                  <span className="text-[10px] text-muted-foreground">
                    {t("ws.mcp.form.argsHint")}
                  </span>
                </Label>
                <Input
                  placeholder={t("ws.mcp.form.argsPlaceholder")}
                  value={argsText}
                  onChange={(e) => syncArgs(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
            </>
          )}

          {/* Env（每行 KEY=value） */}
          <div className="space-y-1.5">
            <Label className="text-xs">
              {t("ws.mcp.form.env")}{" "}
              <span className="text-[10px] text-muted-foreground">{t("ws.mcp.form.envHint")}</span>
            </Label>
            <Textarea
              placeholder={"API_KEY=sk-xxx\nANOTHER=value"}
              value={envText}
              onChange={(e) => syncEnv(e.target.value)}
              className="h-16 text-xs font-mono resize-none"
            />
          </div>

          {/* Timeout + Always Allow */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("ws.mcp.form.timeout")}</Label>
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
                  {form.disabled ? t("ws.mcp.form.disabled") : t("ws.mcp.form.enabled")}
                </span>
              </label>
            </div>
          </div>

          {/* Always Allow tools */}
          <div className="space-y-1.5">
            <Label className="text-xs">
              {t("ws.mcp.form.alwaysAllow")}{" "}
              <span className="text-[10px] text-muted-foreground">
                {t("ws.mcp.form.alwaysAllowHint")}
              </span>
            </Label>
            <Textarea
              placeholder={t("ws.mcp.form.alwaysAllowPlaceholder")}
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
            {t("ws.mcp.test.connection")}
          </Button>
          <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 className="w-3 h-3 animate-spin mr-1" />
            ) : (
              <Save className="w-3 h-3 mr-1" />
            )}
            {isOverride
              ? t("ws.mcp.action.createOverride")
              : isEdit
                ? t("ws.mcp.action.saveChanges")
                : t("ws.mcp.action.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MCPTab({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation("drawersUi");
  const [servers, setServers] = useState<
    Array<WsMcpServerConfig & { source?: string; user_overridden?: boolean }>
  >([]);
  const [userDefaults, setUserDefaults] = useState<Record<string, WsMcpServerConfig>>({});
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingServer, setEditingServer] = useState<WsMcpServerConfig | null>(null);
  const [overrideMode, setOverrideMode] = useState(false);
  const [serverStatus, setServerStatus] = useState<
    Record<
      string,
      { status: string; tools_count: number; resources_count: number; error: string | null }
    >
  >({});
  const [testingAll, setTestingAll] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await wsMcpApi.listEffective(workspaceId);
      setServers(res.effective ?? []);
      const dmap: Record<string, WsMcpServerConfig> = {};
      (res.default ?? []).forEach((d) => {
        dmap[d.name] = d;
      });
      setUserDefaults(dmap);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleToggle = async (s: WsMcpServerConfig & { source?: string }, disabled: boolean) => {
    try {
      if (s.source === "user") {
        // 继承级：为本工作区创建同名覆盖并改 disabled
        await wsMcpApi.addServer(workspaceId, {
          name: s.name,
          command: s.command ?? "",
          args: s.args ?? [],
          cwd: s.cwd,
          always_allow: s.always_allow ?? [],
          timeout: s.timeout ?? 300,
          disabled: !disabled,
        });
        toast.success(t("ws.mcp.toast.overrideSaved", { name: s.name }));
      } else {
        await wsMcpApi.updateServer(workspaceId, s.name, { disabled: !disabled });
      }
      load();
    } catch {
      toast.error(t("ws.mcp.toast.opFailed"));
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await wsMcpApi.deleteServer(workspaceId, name);
      toast.success(t("ws.mcp.toast.deleted", { name }));
      load();
    } catch {
      toast.error(t("ws.mcp.toast.deleteFailed"));
    }
  };

  const handleReset = async (name: string) => {
    try {
      await wsMcpApi.deleteServer(workspaceId, name);
      toast.success(t("ws.mcp.toast.resetDone", { name }));
      load();
    } catch {
      toast.error(t("ws.mcp.toast.resetFailed"));
    }
  };

  const openAdd = () => {
    setEditingServer(null);
    setOverrideMode(false);
    setDialogOpen(true);
  };
  const openEdit = (s: WsMcpServerConfig) => {
    setEditingServer(s);
    setOverrideMode(false);
    setDialogOpen(true);
  };
  const openOverride = (s: WsMcpServerConfig) => {
    setEditingServer(s);
    setOverrideMode(true);
    setDialogOpen(true);
  };

  const handleTestAll = async () => {
    if (servers.length === 0) return;
    setTestingAll(true);
    try {
      const res = await wsMcpApi.listStatus(workspaceId);
      const map: typeof serverStatus = {};
      (res.servers ?? []).forEach((s) => {
        map[s.name] = s;
      });
      setServerStatus(map);
      const ok = Object.values(map).filter((s) => s.status === "connected").length;
      toast.success(t("ws.mcp.toast.probeDone", { ok, total: Object.keys(map).length }));
    } catch {
      toast.error(t("ws.mcp.toast.probeFailed"));
    } finally {
      setTestingAll(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionTitle title={t("ws.mcp.tab.title")} desc={t("ws.mcp.tab.desc")} />
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={load} disabled={loading} className="h-7">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={handleTestAll}
            disabled={testingAll}
            className="h-7 text-xs"
            title={t("ws.mcp.tab.testAllTitle")}
          >
            <Play className={`w-3 h-3 mr-1 ${testingAll ? "opacity-50" : ""}`} />
            {testingAll ? t("ws.mcp.tab.testingAll") : t("ws.mcp.tab.testAll")}
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={openAdd}>
            <Plus className="w-3 h-3 mr-1" /> {t("ws.mcp.tab.add")}
          </Button>
        </div>
      </div>
      {servers.length > 0 && (
        <div className="text-[11px] text-muted-foreground px-1">
          {t("ws.mcp.countSummary", { count: servers.length })}
          <span className="text-blue-600 ml-1">
            {t("ws.mcp.inheritedCount", {
              count: servers.filter((s) => s.source === "user").length,
            })}
          </span>
          {servers.filter((s) => s.user_overridden).length > 0 && (
            <span className="text-amber-600 ml-1">
              {t("ws.mcp.overriddenCount", {
                count: servers.filter((s) => s.user_overridden).length,
              })}
            </span>
          )}
          {servers.filter((s) => s.source === "workspace" && !s.user_overridden).length > 0 && (
            <span className="text-green-600 ml-1">
              {t("ws.mcp.wsOnlyCount", {
                count: servers.filter((s) => s.source === "workspace" && !s.user_overridden).length,
              })}
            </span>
          )}
        </div>
      )}
      {servers.length === 0 ? (
        <div className="text-center py-8 text-xs text-muted-foreground border border-dashed border-border rounded-lg">
          {t("ws.mcp.empty")}
        </div>
      ) : (
        <div className="space-y-2">
          {servers.map((s) => {
            const isInherited = s.source === "user";
            const isOverride = s.source === "workspace" && !!s.user_overridden;
            const userDefault = isOverride ? userDefaults[s.name] : undefined;
            return (
              <div
                key={s.name}
                className="flex items-center gap-3 p-3 rounded-lg border border-border bg-card/50"
              >
                {(() => {
                  const st = serverStatus[s.name];
                  const color = !st
                    ? "bg-muted-foreground/30"
                    : st.status === "connected"
                      ? "bg-green-500"
                      : st.status === "error"
                        ? "bg-red-500"
                        : "bg-muted-foreground/30";
                  return (
                    <div
                      className="flex items-center gap-1.5 shrink-0"
                      title={
                        st
                          ? t("ws.mcp.statusTools", { status: st.status, count: st.tools_count })
                          : t("ws.mcp.notTested")
                      }
                    >
                      <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${color}`} />
                      {st && st.status === "connected" && (
                        <span className="text-[10px] text-muted-foreground font-mono">
                          {t("ws.mcp.toolsCount", { count: st.tools_count })}
                        </span>
                      )}
                    </div>
                  );
                })()}
                <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center">
                  <Plug className="w-4 h-4 text-brand" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{s.name}</span>
                    {s.source === "workspace" && (
                      <Badge variant="outline" className="text-[10px] text-brand">
                        {s.user_overridden
                          ? t("ws.mcp.badge.overrideUser")
                          : t("ws.mcp.badge.workspace")}
                      </Badge>
                    )}
                    {s.source === "user" && (
                      <Badge variant="outline" className="text-[10px] text-muted-foreground">
                        {t("ws.mcp.badge.inheritUser")}
                      </Badge>
                    )}
                    {s.disabled && (
                      <Badge variant="outline" className="text-[10px] text-muted-foreground">
                        {t("ws.mcp.badge.disabled")}
                      </Badge>
                    )}
                  </div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {s.command ?? "—"} {(s.args ?? []).join(" ")}
                    {s.always_allow && s.always_allow.length > 0 && (
                      <span className="text-brand/70 ml-1">
                        {t("ws.mcp.autoAllow", { tools: s.always_allow.join(", ") })}
                      </span>
                    )}
                  </div>
                  {userDefault && (
                    <div className="text-[10px] text-muted-foreground/70 truncate mt-0.5">
                      {t("ws.mcp.userDefault", { command: userDefault.command ?? "—" })}{" "}
                      {(userDefault.args ?? []).join(" ")}
                    </div>
                  )}
                </div>
                <Switch
                  checked={!s.disabled}
                  onCheckedChange={() => handleToggle(s, s.disabled ?? false)}
                  title={isInherited ? t("ws.mcp.overrideTitle") : undefined}
                />
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0"
                  onClick={() => (isInherited ? openOverride(s) : openEdit(s))}
                  title={isInherited ? t("ws.mcp.overrideShort") : t("ws.mcp.action.edit")}
                >
                  <Pencil className="w-3 h-3" />
                </Button>
                {isOverride ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={() => handleReset(s.name)}
                    title={t("ws.mcp.resetInherit")}
                  >
                    <RotateCcw className="w-3 h-3 text-muted-foreground" />
                  </Button>
                ) : isInherited ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0 opacity-40 cursor-not-allowed"
                    disabled
                    title={t("ws.mcp.userManaged")}
                  >
                    <Trash2 className="w-3 h-3 text-destructive" />
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={() => handleDelete(s.name)}
                    title={t("ws.mcp.action.delete")}
                  >
                    <Trash2 className="w-3 h-3 text-destructive" />
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}

      <MCPServerDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        workspaceId={workspaceId}
        onSaved={load}
        editServer={editingServer}
        override={overrideMode}
      />
    </div>
  );
}

// ── ACP Agents Tab ───────────────────────────────────────────────────

function ACPTab({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation("drawersUi");
  const [agents, setAgents] = useState<AcpAgentInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await acpAgentApi.list(workspaceId);
      setAgents(res.agents ?? []);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleScan = async () => {
    try {
      const res = await acpAgentApi.scan(workspaceId);
      toast.success(res.message || t("ws.acp.toast.scanDone"));
      load();
    } catch {
      toast.error(t("ws.acp.toast.scanFailed"));
    }
  };

  const handleToggle = async (cmd: string, disabled: boolean) => {
    try {
      await acpAgentApi.toggle(workspaceId, cmd, !disabled);
      load();
    } catch {
      toast.error(t("ws.acp.toast.opFailed"));
    }
  };

  const handleRemove = async (cmd: string) => {
    try {
      await acpAgentApi.remove(workspaceId, cmd);
      toast.success(t("ws.acp.toast.removed"));
      load();
    } catch {
      toast.error(t("ws.acp.toast.removeFailed"));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionTitle title={t("ws.acp.title")} desc={t("ws.acp.desc")} />
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={load} disabled={loading} className="h-7">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={handleScan}>
            <Search className="w-3 h-3 mr-1" /> {t("ws.acp.scan")}
          </Button>
        </div>
      </div>
      {agents.length === 0 ? (
        <div className="text-center py-8 text-xs text-muted-foreground border border-dashed border-border rounded-lg">
          {t("ws.acp.empty")}
        </div>
      ) : (
        <div className="space-y-2">
          {agents.map((a) => (
            <div
              key={a.command}
              className="flex items-center gap-3 p-3 rounded-lg border border-border bg-card/50"
            >
              <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center">
                <Bot className="w-4 h-4 text-brand" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{a.name}</div>
                <div className="text-[11px] text-muted-foreground">{a.command}</div>
              </div>
              <Switch
                checked={!a.disabled}
                onCheckedChange={() => handleToggle(a.command, a.disabled)}
              />
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0"
                onClick={() => handleRemove(a.command)}
              >
                <Trash2 className="w-3 h-3 text-destructive" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Channels Tab ─────────────────────────────────────────────────────

function ChannelsTab({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation("drawersUi");
  const [channels, setChannels] = useState<ChannelInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await channelApi.list(workspaceId);
      setChannels(res.channels ?? []);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleToggle = async (type: string, enabled: boolean) => {
    try {
      if (enabled) {
        await channelApi.disable(workspaceId, type);
      } else {
        await channelApi.enable(workspaceId, type);
      }
      load();
    } catch {
      toast.error(t("ws.channels.toast.opFailed"));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionTitle title={t("ws.channels.title")} desc={t("ws.channels.desc")} />
        <Button size="sm" variant="ghost" onClick={load} disabled={loading} className="h-7">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>
      {channels.length === 0 ? (
        <div className="text-center py-8 text-xs text-muted-foreground border border-dashed border-border rounded-lg">
          {t("ws.channels.empty")}
        </div>
      ) : (
        <div className="space-y-2">
          {channels.map((ch) => (
            <div
              key={ch.channel_type}
              className="flex items-center gap-3 p-3 rounded-lg border border-border bg-card/50"
            >
              <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center">
                <Radio className="w-4 h-4 text-brand" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate">{ch.channel_type}</span>
                  {ch.running && (
                    <Badge className="bg-green-500/20 text-green-500 text-[10px]">
                      {t("ws.channels.badge.running")}
                    </Badge>
                  )}
                  {!ch.registered && (
                    <Badge variant="outline" className="text-[10px]">
                      {t("ws.channels.badge.unregistered")}
                    </Badge>
                  )}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {ch.description ?? ch.channel_type}
                </div>
              </div>
              <Switch
                checked={ch.enabled}
                onCheckedChange={() => handleToggle(ch.channel_type, ch.enabled)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Security Tab ─────────────────────────────────────────────────────

function SecurityTab({ workspaceId }: { workspaceId: string }) {
  // Structured two-level form (replaces the former raw JSON dump).
  return <SecurityPolicyForm scope="workspace" workspaceId={workspaceId} />;
}

// ── Helper components ──────────────────────────────────────────────

function SectionTitle({ title, desc }: { title: string; desc: string }) {
  return (
    <div>
      <h3 className="text-sm font-medium">{title}</h3>
      <p className="text-[11px] text-muted-foreground mt-0.5">{desc}</p>
    </div>
  );
}

function FieldRow({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <Label className="text-xs text-muted-foreground shrink-0">{label}</Label>
      {children}
    </div>
  );
}
