/**
 * 工作区分享公开页（方案 §7）— /share/$shareId
 *
 * 免登录（__root.tsx 公共路径豁免）。两态：
 * - ShareGate: 提取码验证（防爆破锁定倒计时）；验证前不显示工作区名（防枚举）
 * - SharedWorkspaceView: 四 Tab 只读浏览（概览/文件/对话/任务）+ 复制到我的账号
 *
 * 凭证: X-Share-Token（sessionStorage，方案 §7.1）；任何 401/404 回落 Gate/失效页
 * （对应后端逐请求重查校验链 — 关闭/撤销/过期即时生效）。
 *
 * 公开页文案硬编码中文 — 与 shared-report.tsx 先例一致（匿名访客无 i18n 上下文依赖）。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createFileRoute, useNavigate, useParams } from "@tanstack/react-router";
import { toast } from "sonner";
import {
  CheckCircle2,
  Circle,
  Copy,
  Download,
  FileText,
  Folder,
  Loader2,
  Lock,
  MessageSquare,
  PlayCircle,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FileTreeNode, type FileTreeItem } from "@/components/files/file-tree-node";
import { renderMarkdown } from "@/components/chat/content/markdown";
import { useAuthStore } from "@/lib/auth-store";
import { getBasepath } from "@/router";
import { ApiError } from "@/lib/api/client";
import { BRAND_NAME } from "@/lib/brand";
import {
  ShareLockedError,
  clearShareToken,
  getStoredShareToken,
  shareViewerApi,
  storeShareToken,
  type SharedConversationSummary,
  type SharedFileNode,
  type SharedMessage,
  type SharedTaskGraph,
  type ShareMetaResponse,
} from "@/lib/api/share";

export const Route = createFileRoute("/share/$shareId")({
  head: () => ({ meta: [{ title: `工作区分享 · 只读 — ${BRAND_NAME}` }] }),
  component: SharePage,
});

type Phase = "checking" | "gate" | "view" | "invalid";

function SharePage() {
  const { shareId } = useParams({ from: "/share/$shareId" });
  const [phase, setPhase] = useState<Phase>("checking");
  const [meta, setMeta] = useState<ShareMetaResponse | null>(null);

  // 刷新恢复: sessionStorage 有 token → meta 探测；失效则回落 Gate
  useEffect(() => {
    if (!getStoredShareToken(shareId)) {
      setPhase("gate");
      return;
    }
    shareViewerApi
      .meta(shareId)
      .then((m) => {
        setMeta(m);
        setPhase("view");
      })
      .catch((e) => {
        clearShareToken(shareId);
        if (e instanceof ApiError && e.status === 404) setPhase("invalid");
        else setPhase("gate");
      });
  }, [shareId]);

  // 校验链逐请求重查: 浏览览中途被关闭/撤销 → 任一请求 404 → 失效页
  const onShareGone = useCallback(() => {
    clearShareToken(shareId);
    setPhase("invalid");
  }, [shareId]);

  if (phase === "checking") {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
      </div>
    );
  }

  if (phase === "invalid") return <ShareInvalid />;

  if (phase === "gate") {
    return (
      <ShareGate
        shareId={shareId}
        onVerified={(m, expiresAt) => {
          setMeta({ workspace: m.workspace, stats: m.stats });
          setPhase("view");
          void expiresAt;
        }}
      />
    );
  }

  return <SharedWorkspaceView shareId={shareId} initialMeta={meta} onShareGone={onShareGone} />;
}

// ── 失效页（不存在/已关闭/已撤销/已过期 — 统一文案，防枚举） ────────

function ShareInvalid() {
  return (
    <div className="h-screen flex items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-4xl font-bold text-gradient-brand">404</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          分享不存在或已失效（被关闭、撤销或已过期）
        </p>
        <p className="mt-1 text-xs text-muted-foreground">请联系分享者确认链接与有效期</p>
      </div>
    </div>
  );
}

// ── ShareGate: 提取码验证 ───────────────────────────────────────────

function ShareGate({
  shareId,
  onVerified,
}: {
  shareId: string;
  onVerified: (meta: Awaited<ReturnType<typeof shareViewerApi.verify>>, expiresAt: string) => void;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lockSeconds, setLockSeconds] = useState(0);

  useEffect(() => {
    if (lockSeconds <= 0) return;
    const timer = setInterval(() => setLockSeconds((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(timer);
  }, [lockSeconds]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading || lockSeconds > 0) return;
    setError("");
    setLoading(true);
    try {
      const data = await shareViewerApi.verify(shareId, password.trim());
      storeShareToken(shareId, data.share_token);
      onVerified(data, data.expires_at);
    } catch (err) {
      if (err instanceof ShareLockedError) {
        setLockSeconds(err.retryAfterSeconds || 600);
        setError(err.message);
      } else if (err instanceof ApiError && err.status === 404) {
        setError("分享不存在或已失效");
      } else if (err instanceof ApiError) {
        setError(err.body || "提取码错误或分享不存在");
      } else {
        setError("网络错误，请稍后重试");
      }
    } finally {
      setLoading(false);
    }
  }

  const mm = Math.floor(lockSeconds / 60);
  const ss = lockSeconds % 60;

  return (
    <div className="h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 w-12 h-12 rounded-xl bg-brand/10 flex items-center justify-center">
            <Lock className="w-6 h-6 text-brand" />
          </div>
          <h1 className="text-xl font-bold">工作区分享</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">输入提取码查看只读分享的工作区</p>
        </div>
        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-xl border border-border bg-card p-6 shadow-sm"
        >
          <Input
            type="text"
            inputMode="text"
            autoFocus
            placeholder="提取码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading || lockSeconds > 0}
            className="text-center text-lg tracking-[0.4em] h-12"
          />
          {error && <p className="text-sm text-destructive text-center">{error}</p>}
          {lockSeconds > 0 && (
            <p className="text-sm text-muted-foreground text-center">
              尝试次数过多，请 {mm} 分 {String(ss).padStart(2, "0")} 秒后再试
            </p>
          )}
          <Button
            type="submit"
            className="w-full bg-gradient-brand text-brand-foreground h-10"
            disabled={loading || lockSeconds > 0 || !password.trim()}
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "查看分享"}
          </Button>
        </form>
        <p className="mt-4 text-center text-xs text-muted-foreground">
          🔒 只读分享 · 有效期内可浏览
        </p>
      </div>
    </div>
  );
}

// ── SharedWorkspaceView: 四 Tab 只读浏览 ────────────────────────────

function SharedWorkspaceView({
  shareId,
  initialMeta,
  onShareGone,
}: {
  shareId: string;
  initialMeta: ShareMetaResponse | null;
  onShareGone: () => void;
}) {
  const navigate = useNavigate();
  const authenticated = useAuthStore((s) => s.authenticated);
  const [meta, setMeta] = useState<ShareMetaResponse | null>(initialMeta);
  const [cloning, setCloning] = useState(false);

  /** gate 之后刷新页面 → 从 JWT payload 读 exp（免签名，仅展示用） */
  const expiresAt = useMemo(() => {
    try {
      const payload = JSON.parse(atob(getStoredShareToken(shareId)!.split(".")[1]));
      return payload?.exp ? new Date(payload.exp * 1000).toLocaleString("zh-CN") : "";
    } catch {
      return "";
    }
  }, [shareId]);

  const refreshMeta = () => {
    shareViewerApi
      .meta(shareId)
      .then(setMeta)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) onShareGone();
      });
  };

  function loginAndClone() {
    const back = encodeURIComponent(`${getBasepath()}/share/${shareId}`);
    window.location.href = `${getBasepath()}/login?redirect=${back}`;
  }

  async function handleClone() {
    if (cloning) return;
    setCloning(true);
    try {
      const { workspace_id, name } = await shareViewerApi.clone(shareId);
      toast.success(`已复制「${name}」到我的账号`);
      navigate({ to: "/workspace/$workspaceId", params: { workspaceId: workspace_id } });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        toast.error("请先登录后再复制");
        loginAndClone();
      } else if (err instanceof ApiError && err.status === 404) {
        onShareGone();
      } else if (err instanceof ApiError && err.status === 413) {
        toast.error(err.body || "工作区过大，无法复制");
      } else {
        toast.error("复制失败，请稍后重试");
      }
    } finally {
      setCloning(false);
    }
  }

  const stats = meta?.stats;

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 sm:px-6 py-3 border-b border-border/50 shrink-0">
        <h1 className="text-base sm:text-lg font-bold tracking-tight truncate">
          {meta?.workspace.display_name || "工作区分享"}
        </h1>
        <Badge className="bg-brand/15 text-brand border-0 text-[11px] shrink-0">🔒 只读分享</Badge>
        {expiresAt && (
          <span className="hidden sm:inline text-xs text-muted-foreground shrink-0">
            有效期至 {expiresAt}
          </span>
        )}
        <div className="ml-auto shrink-0">
          {authenticated ? (
            <Button
              size="sm"
              className="bg-gradient-brand text-brand-foreground gap-1.5"
              onClick={handleClone}
              disabled={cloning}
            >
              {cloning ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
              {cloning ? "正在复制…" : "复制到我的账号"}
            </Button>
          ) : (
            <Button size="sm" variant="outline" className="gap-1.5" onClick={loginAndClone}>
              <Copy className="w-3.5 h-3.5" /> 登录后复制到我的账号
            </Button>
          )}
        </div>
      </header>

      {/* Tabs */}
      <Tabs defaultValue="overview" className="flex-1 flex flex-col overflow-hidden">
        <TabsList className="mx-4 sm:mx-6 mt-3 shrink-0 w-fit">
          <TabsTrigger value="overview">概览</TabsTrigger>
          <TabsTrigger value="files">文件</TabsTrigger>
          <TabsTrigger value="conversations">对话</TabsTrigger>
          <TabsTrigger value="tasks">任务</TabsTrigger>
        </TabsList>

        <TabsContent
          value="overview"
          className="flex-1 overflow-y-auto mt-0 pt-4 px-4 sm:px-6 scrollbar-thin"
        >
          {stats ? (
            <div className="max-w-3xl space-y-6">
              {meta?.workspace.description && (
                <div>
                  <h2 className="text-sm font-semibold mb-1.5">描述</h2>
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                    {meta.workspace.description}
                  </p>
                </div>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard
                  icon={<FileText className="w-4 h-4" />}
                  label="文件"
                  value={stats.files.toLocaleString()}
                />
                <StatCard
                  icon={<MessageSquare className="w-4 h-4" />}
                  label="对话"
                  value={stats.conversations.toLocaleString()}
                />
                <StatCard
                  icon={<PlayCircle className="w-4 h-4" />}
                  label="任务"
                  value={stats.tasks.toLocaleString()}
                />
                <StatCard
                  icon={<Folder className="w-4 h-4" />}
                  label="总大小"
                  value={formatBytes(stats.total_bytes)}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                分享为只读快照 —
                完整内容（含配置外的一切用户文件）可通过「复制到我的账号」保存为自己的工作区。
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> 加载中…
              <Button variant="ghost" size="sm" onClick={refreshMeta}>
                <RefreshCw className="w-3.5 h-3.5" />
              </Button>
            </div>
          )}
        </TabsContent>

        <TabsContent value="files" className="flex-1 overflow-hidden mt-0 pt-3">
          <FilesTab shareId={shareId} onShareGone={onShareGone} />
        </TabsContent>

        <TabsContent value="conversations" className="flex-1 overflow-hidden mt-0 pt-3">
          <ConversationsTab shareId={shareId} onShareGone={onShareGone} />
        </TabsContent>

        <TabsContent
          value="tasks"
          className="flex-1 overflow-y-auto mt-0 pt-4 px-4 sm:px-6 scrollbar-thin"
        >
          <TasksTab shareId={shareId} onShareGone={onShareGone} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-1.5 text-muted-foreground text-xs">
        {icon}
        {label}
      </div>
      <div className="mt-1.5 text-xl font-bold">{value}</div>
    </div>
  );
}

// ── 文件 Tab ────────────────────────────────────────────────────────

/** 后端扁平树 → FileTreeNode 嵌套结构 */
function buildTree(flat: SharedFileNode[]): FileTreeItem[] {
  const root: FileTreeItem[] = [];
  const dirChildren = new Map<string, FileTreeItem[]>();
  for (const n of flat) {
    const item: FileTreeItem =
      n.type === "directory"
        ? { name: n.name, path: n.path, type: "folder", children: [] }
        : { name: n.name, path: n.path, type: "file" };
    const parentPath = n.path.includes("/") ? n.path.slice(0, n.path.lastIndexOf("/")) : "";
    const list = parentPath ? dirChildren.get(parentPath) : root;
    if (list) list.push(item);
    if (item.type === "folder") dirChildren.set(n.path, item.children!);
  }
  return root;
}

const IMAGE_EXTS = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"];
const TEXT_EXTS = [
  "txt",
  "md",
  "markdown",
  "json",
  "csv",
  "log",
  "yml",
  "yaml",
  "xml",
  "html",
  "js",
  "ts",
  "py",
  "sh",
];

function extOf(name: string): string {
  return name.split(".").pop()?.toLowerCase() ?? "";
}

function FilesTab({ shareId, onShareGone }: { shareId: string; onShareGone: () => void }) {
  const [tree, setTree] = useState<FileTreeItem[] | null>(null);
  const [selected, setSelected] = useState<FileTreeItem | null>(null);
  const [preview, setPreview] = useState<{
    url: string;
    kind: "image" | "pdf" | "text" | "binary";
    text?: string;
  } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    shareViewerApi
      .fileTree(shareId)
      .then((r) => setTree(buildTree(r.fileTree || [])))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) onShareGone();
        else setTree([]);
      });
  }, [shareId, onShareGone]);

  // 预览对象 URL 生命周期: 换文件/卸载时回收
  const setObjectUrl = (url: string | null) => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    objectUrlRef.current = url;
  };
  useEffect(() => () => setObjectUrl(null), []);

  async function openPreview(item: FileTreeItem) {
    setSelected(item);
    setPreview(null);
    const ext = extOf(item.name);
    const isImage = IMAGE_EXTS.includes(ext);
    const isPdf = ext === "pdf";
    const isText = TEXT_EXTS.includes(ext);
    if (!isImage && !isPdf && !isText) return; // 二进制 → 只提供下载
    setPreviewLoading(true);
    try {
      const blob = await shareViewerApi.file(shareId, item.path, true);
      if (isText) {
        setPreview({ url: "", kind: "text", text: (await blob.text()).slice(0, 500_000) });
      } else {
        const url = URL.createObjectURL(blob);
        setObjectUrl(url);
        setPreview({ url, kind: isPdf ? "pdf" : "image" });
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) onShareGone();
      else toast.error("预览加载失败");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function download(path: string, name: string) {
    if (downloading) return;
    setDownloading(true);
    try {
      const blob = await shareViewerApi.file(shareId, path, false);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      // 给浏览器起步下载后回收（大文件 zip 场景留 60s 余量）
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) onShareGone();
      else toast.error("下载失败");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="h-full flex px-4 sm:px-6 gap-4 overflow-hidden">
      {/* 左: 文件树 */}
      <div className="w-60 sm:w-72 shrink-0 overflow-y-auto scrollbar-thin rounded-lg border border-border bg-card py-2">
        {tree === null ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          </div>
        ) : tree.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-8">暂无文件</p>
        ) : (
          tree.map((item) => (
            <FileTreeNode
              key={item.path}
              item={item}
              level={0}
              selectedPath={selected?.path ?? null}
              onClick={(it) => void openPreview(it)}
              renderActions={(it) => (
                <button
                  title={it.type === "folder" ? "下载 ZIP" : "下载"}
                  className="p-1 rounded hover:bg-muted"
                  onClick={(e) => {
                    e.stopPropagation();
                    void download(it.path, it.type === "folder" ? `${it.name}.zip` : it.name);
                  }}
                >
                  <Download className="w-3 h-3 text-muted-foreground" />
                </button>
              )}
            />
          ))
        )}
      </div>
      {/* 右: 预览 */}
      <div className="flex-1 min-w-0 overflow-hidden rounded-lg border border-border bg-card">
        {!selected ? (
          <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
            点击左侧文件预览（图片 / PDF / 文本可直接查看）
          </div>
        ) : (
          <div className="h-full flex flex-col">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-border/50 shrink-0">
              <span className="text-xs font-medium truncate">{selected.path}</span>
              <Button
                variant="outline"
                size="sm"
                className="ml-auto h-7 gap-1 text-xs shrink-0"
                disabled={downloading}
                onClick={() =>
                  void download(
                    selected.path,
                    selected.type === "folder" ? `${selected.name}.zip` : selected.name,
                  )
                }
              >
                {downloading ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Download className="w-3 h-3" />
                )}
                下载
              </Button>
            </div>
            <div className="flex-1 overflow-auto scrollbar-thin p-3">
              {previewLoading ? (
                <div className="flex justify-center py-10">
                  <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                </div>
              ) : preview?.kind === "image" ? (
                // svg 走 preview=1 时后端强制 attachment/octet-stream → 不会到这里当成图渲染（双保险）
                <img
                  src={preview.url}
                  alt={selected.name}
                  className="max-w-full max-h-full mx-auto object-contain"
                />
              ) : preview?.kind === "pdf" ? (
                <iframe
                  src={preview.url}
                  title={selected.name}
                  className="w-full h-full border-0"
                />
              ) : preview?.kind === "text" ? (
                <pre className="text-xs whitespace-pre-wrap break-words font-mono">
                  {preview.text}
                </pre>
              ) : (
                <div className="h-full flex flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                  该文件类型不支持在线预览
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void download(selected.path, selected.name)}
                  >
                    <Download className="w-3.5 h-3.5" /> 下载文件
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 对话 Tab ────────────────────────────────────────────────────────

function messageText(m: SharedMessage): string {
  if (typeof m.content === "string" && m.content.trim()) return m.content;
  if (Array.isArray(m.blocks)) {
    return m.blocks
      .map((b) =>
        typeof b?.text === "string"
          ? b.text
          : typeof b?.content === "string"
            ? String(b.content)
            : "",
      )
      .filter(Boolean)
      .join("\n\n");
  }
  return "";
}

function ConversationsTab({ shareId, onShareGone }: { shareId: string; onShareGone: () => void }) {
  const [list, setList] = useState<SharedConversationSummary[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<SharedMessage[] | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    shareViewerApi
      .conversations(shareId)
      .then((r) => {
        setList(r.conversations || []);
        if (r.conversations?.length) setActiveId(r.conversations[0].id);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) onShareGone();
        else setList([]);
      });
  }, [shareId, onShareGone]);

  useEffect(() => {
    if (!activeId) return;
    setDetailLoading(true);
    setMessages(null);
    shareViewerApi
      .conversation(shareId, activeId)
      .then((r) => setMessages(r.conversation?.messages || []))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) onShareGone();
        else setMessages([]);
      })
      .finally(() => setDetailLoading(false));
  }, [shareId, activeId, onShareGone]);

  return (
    <div className="h-full flex px-4 sm:px-6 gap-4 overflow-hidden">
      <div className="w-60 sm:w-72 shrink-0 overflow-y-auto scrollbar-thin rounded-lg border border-border bg-card">
        {list === null ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          </div>
        ) : list.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-8">暂无对话</p>
        ) : (
          list.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveId(c.id)}
              className={`w-full text-left px-3 py-2.5 border-b border-border/40 transition ${
                activeId === c.id ? "bg-brand/10" : "hover:bg-muted/60"
              }`}
            >
              <div className="text-xs font-medium truncate">{c.title || "未命名对话"}</div>
              <div className="mt-0.5 text-[10px] text-muted-foreground">
                {c.messageCount != null ? `${c.messageCount} 条消息 · ` : ""}
                {formatDate(c.lastUpdated || c.updatedAt || c.createdAt)}
              </div>
            </button>
          ))
        )}
      </div>
      <div className="flex-1 min-w-0 overflow-y-auto scrollbar-thin rounded-lg border border-border bg-card p-4 space-y-4">
        {detailLoading ? (
          <div className="flex justify-center py-10">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : !messages || messages.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-10">暂无消息</p>
        ) : (
          messages.map((m, i) => {
            const text = messageText(m);
            if (!text) return null;
            const isUser = m.role === "user";
            return (
              <div key={i} className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}>
                <div
                  className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-medium ${
                    isUser ? "bg-brand/15 text-brand" : "bg-muted text-muted-foreground"
                  }`}
                >
                  {isUser ? "我" : "AI"}
                </div>
                <div
                  className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm ${
                    isUser ? "bg-brand/10" : "bg-muted/60"
                  }`}
                >
                  <div className="prose-sm break-words">{renderMarkdown(text)}</div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ── 任务 Tab ────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: string }) {
  const s = status.toLowerCase();
  if (s === "done" || s === "completed" || s === "succeeded")
    return <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />;
  if (s === "failed" || s === "error" || s === "cancelled")
    return <XCircle className="w-3.5 h-3.5 text-destructive" />;
  if (s === "in_progress" || s === "running" || s === "doing")
    return <PlayCircle className="w-3.5 h-3.5 text-blue-500" />;
  return <Circle className="w-3.5 h-3.5 text-muted-foreground" />;
}

function TasksTab({ shareId, onShareGone }: { shareId: string; onShareGone: () => void }) {
  const [graphs, setGraphs] = useState<SharedTaskGraph[] | null>(null);

  useEffect(() => {
    shareViewerApi
      .tasks(shareId)
      .then((r) => setGraphs(r.graphs || []))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) onShareGone();
        else setGraphs([]);
      });
  }, [shareId, onShareGone]);

  if (graphs === null) {
    return (
      <div className="flex justify-center py-10">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (graphs.length === 0) {
    return <p className="text-sm text-muted-foreground text-center py-10">暂无任务</p>;
  }

  return (
    <div className="max-w-3xl space-y-4">
      {graphs.map((g) => (
        <div key={g.graph_id} className="rounded-lg border border-border bg-card overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border/50 bg-muted/30">
            <PlayCircle className="w-4 h-4 text-brand" />
            <span className="text-sm font-semibold truncate">{g.name}</span>
            <Badge variant="outline" className="text-[10px] shrink-0">
              {g.total_tasks} 个任务
            </Badge>
            {g.status && (
              <Badge variant="outline" className="text-[10px] shrink-0">
                {g.status}
              </Badge>
            )}
            {g.created_at && (
              <span className="ml-auto text-[10px] text-muted-foreground shrink-0">
                {formatDate(g.created_at)}
              </span>
            )}
          </div>
          <div className="divide-y divide-border/40">
            {g.tasks.map((t) => (
              <div key={t.task_id} className="px-4 py-2.5">
                <div className="flex items-start gap-2">
                  <StatusIcon status={t.status || ""} />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs leading-relaxed break-words">
                      {t.description || t.task_id}
                    </p>
                    {t.todos && t.todos.length > 0 && (
                      <ul className="mt-1.5 space-y-0.5">
                        {t.todos.map((todo, i) => (
                          <li
                            key={i}
                            className="flex items-center gap-1.5 text-[11px] text-muted-foreground"
                          >
                            {todo.done ? (
                              <CheckCircle2 className="w-3 h-3 text-green-600 shrink-0" />
                            ) : (
                              <Circle className="w-3 h-3 shrink-0" />
                            )}
                            <span className={todo.done ? "line-through" : ""}>{todo.text}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── 工具 ────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatDate(value?: string): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
