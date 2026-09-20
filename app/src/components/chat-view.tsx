import { useEffect, useRef, useState, useCallback, useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { type Task, type Workspace, useStore } from "@/lib/store";
import { ChatMessage as ChatMessageComponent } from "./chat/message";
import { FollowupQuestionDialog } from "./chat/followup-dialog";
import { FloatingInput } from "./floating-input";
import { getExpert, toExperts } from "@/lib/experts";
import { useMarketTeamsStore } from "@/lib/market-teams-store";
import { useChatStore, type DisplayMode } from "@/lib/chat-store";
import { useConnectionStore } from "@/lib/connection-store";
import { consumePendingAutoStart, peekPendingAutoStart } from "@/lib/pending-auto-start";
import { useWorkspaceFilesStore } from "@/lib/workspace-files-store";
import { selectFiles } from "@/lib/platform/files";
import { WorkspacePanel } from "@/components/workspace-panel";
import { FileContentArea } from "@/components/files/file-content-area";
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable";
import { useIsMobile } from "@/hooks/use-mobile";
import {
  FolderOpen,
  MessageSquare,
  Sparkles,
  FileText,
  Users,
  Lightbulb,
  X,
  WifiOff,
  Loader2,
  RefreshCw,
  AlertTriangle,
  Upload,
  Lightbulb as LightbulbIcon,
  PenTool,
  Send,
  Settings,
  Shield,
  Ticket,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ContentBlock } from "@/lib/types";
import { AgentDegradedBanner } from "@/components/agent-degraded-banner";
import { marketApi, type TeamHierarchyEntry } from "@/lib/market-api";
import {
  BIZ_WORKSPACE_EMPTY_STATES,
  BIZ_WORKSPACE_EMPTY_COMPONENTS,
} from "@/lib/biz-registry";

/** Stable empty array ref — avoids new [] on every render */
const EMPTY_ARR: never[] = [];

/** 长对话窗口化(方案 Phase 3.2):仅渲染最近 N 条消息,顶部"加载更早"按需扩窗 */
const MESSAGE_WINDOW = 120;

interface ExtraPanelToggle {
  icon: ReactNode;
  label: string;
  panel: ReactNode;
}

interface Props {
  task: Task;
  workspace?: Workspace;
  /** E1: Extra node rendered in the top bar (right of expert badge) */
  extraTopBarNode?: ReactNode;
  /** E2: Extra toggle button + panel (rendered as a 4th resizable panel) */
  extraPanelToggle?: ExtraPanelToggle;
  /** E3: Extension for rendering custom message content block types */
  messageRendererExt?: (block: ContentBlock) => ReactNode | null;
  /** E4: Custom placeholder text for the input area */
  inputPlaceholder?: string;
}

export function ChatView({
  task,
  workspace,
  extraTopBarNode,
  extraPanelToggle,
  messageRendererExt,
  inputPlaceholder,
}: Props) {
  const { t } = useTranslation("commonUi");
  const scrollRef = useRef<HTMLDivElement>(null);
  const marketTeams = useMarketTeamsStore((s) => s.teams);
  const fetchTeams = useMarketTeamsStore((s) => s.fetchTeams);
  const allExperts = useMemo(() => toExperts(marketTeams), [marketTeams]);
  useEffect(() => {
    fetchTeams();
  }, [fetchTeams]);
  const expert = task.expertId ? getExpert(allExperts, task.expertId) : undefined;
  const requestInsert = useStore((s) => s.requestInsert);
  const setActiveDrawer = useStore((s) => s.setActiveDrawer);
  const setFilesDrawerFor = useStore((s) => s.setFilesDrawerFor);
  const retryLoadHistory = useChatStore((s) => s.retryLoadHistory);
  const displayMode = useChatStore((s) => s.displayMode);
  const setDisplayMode = useChatStore((s) => s.setDisplayMode);
  const compactMode = useChatStore((s) => s.compactMode);
  const fontSize = useChatStore((s) => s.fontSize);
  const historyLoadErrors = useChatStore((s) => s.historyLoadErrors);
  const connectionState = useConnectionStore((s) => s.state);
  const reconnect = useConnectionStore((s) => s.connect);
  const isOnline = connectionState === "connected";
  const showConnBanner = !isOnline && connectionState !== "disconnected";
  // task.id IS the backend conversation UUID (created by POST /api/.../conversations).
  // Use it directly as the key into chat-store conversations map.
  const activeConv = useChatStore((s) => s.conversations.get(task.id));
  const streamBuffer = activeConv?.streamBuffer;
  const followup = activeConv?.followup ?? null;
  const respondFollowup = useChatStore((s) => s.respondFollowup);
  const cancelFollowup = useChatStore((s) => s.cancelFollowup);
  const chatMessages =
    activeConv?.messages ??
    (EMPTY_ARR as typeof activeConv extends { messages: infer M } ? M : never[]);

  const setActiveFile = useWorkspaceFilesStore((s) => s.setActiveFile);
  const closeFile = useWorkspaceFilesStore((s) => s.closeFile);
  const openFiles = useWorkspaceFilesStore((s) => s.openFiles);
  const activeFileId = useWorkspaceFilesStore((s) => s.activeFileId);
  const uploadFiles = useWorkspaceFilesStore((s) => s.uploadFiles);

  const handleUpload = useCallback(async () => {
    if (!workspace) return;
    const selected = await selectFiles({ multiple: true });
    if (selected.length > 0) {
      uploadFiles(workspace.id, selected);
    }
  }, [workspace, uploadFiles]);

  // Panel visibility — all three panels independently hideable
  const [showChatPanel, setShowChatPanel] = useState(true);
  const [showRightPanel, setShowRightPanel] = useState(!!workspace);
  const [showContentPanel, setShowContentPanel] = useState(false);
  const [showExtraPanel, setShowExtraPanel] = useState(false);

  // Auto-show right panel when workspace is available
  useEffect(() => {
    if (workspace) setShowRightPanel(true);
  }, [workspace?.id]);

  // Auto-show content panel when files are opened
  useEffect(() => {
    if (openFiles.length > 0) setShowContentPanel(true);
  }, [openFiles.length]);

  // Load conversation history for workspace tasks.
  useEffect(() => {
    if (task.workspaceId && task.id && chatMessages.length === 0) {
      useChatStore.getState().loadHistory(task.id, task.workspaceId);
    }
  }, [task.id, task.workspaceId, chatMessages.length]);

  // 对话引导自动启动：合规工作区由 launchChat 预置了开场白。WS 已连、会话存在且
  // 无历史消息时，自动发出该开场白，驱动 Agent 按 AGENT_INSTRUCTIONS.md 开始多轮对话。
  // 仅消费一次；有任何历史消息则永不自动启动。
  //
  // 注意：不能依赖 effect 重跑来"等会话创建"。ensureConversation 是同步 set，
  // 之后 getMessages 通过 zustand 的 get() 立即可见。历史上这里曾 return 等"下一帧
  // 重试"，但 deps 是 [task.id, isOnline, chatMessages.length]，会话从无到有时
  // messages.length 始终是 0，effect 不会重跑 —— 只有 React StrictMode 在开发模式
  // 下的双调用副作用能掩盖，生产构建下 StrictMode 失效，auto-start 就永远不触发。
  const autoStartFired = useRef(false);
  useEffect(() => {
    if (autoStartFired.current || !isOnline) return;
    const cs = useChatStore.getState();
    // sendMessage 内部会读 conversations.get(convId)，没有就 return。
    // ensureConversation 同步 set，下文 getMessages 立即可见。
    if (!cs.conversations.get(task.id)) {
      cs.ensureConversation(task.id);
    }
    if (cs.getMessages(task.id).length > 0) {
      autoStartFired.current = true; // 已有历史 → 不自动启动
      return;
    }
    const prompt = peekPendingAutoStart(task.id);
    if (!prompt) return;
    // 先取后消费：model 未就绪时保留 pending（task.model 在 deps 中，就绪后 effect
    // 重跑再真正发出）。此前"取出即删 + model 缺失即丢"会把开场白静默吞掉。
    if (!task.model) return;
    consumePendingAutoStart(task.id);
    autoStartFired.current = true;
    // Pass full task context so the backend routes to the correct workspace and
    // selects the right LLM/experts (same payload shape as manual input).
    cs.sendMessage(prompt, task.id, {
      workspaceId: task.workspaceId,
      model: task.model,
      expertId: task.expertId,
      mode: task.mode,
    });
  }, [task.id, isOnline, chatMessages.length, task.model]);

  // Track whether the user is near the bottom of the scroll area. When they've
  // scrolled up to read history, we must NOT yank them back down on every new
  // streaming chunk — that's both rude and disorienting.
  const isNearBottomRef = useRef(true);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Auto-scroll on new messages and streaming chunks.
  // - Skip when the user is reading history (see isNearBottomRef).
  // - Use instant scroll for streaming chunks: smooth animations get cancelled
  //   by the next chunk and never settle, which used to leave the view stuck
  //   inside the bottom padding with no messages visible.
  // - rAF so scrollHeight reflects the just-rendered DOM before we jump.
  const prevMsgCountRef = useRef(chatMessages.length);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (!isNearBottomRef.current) return;
    const isNewMessage = chatMessages.length !== prevMsgCountRef.current;
    prevMsgCountRef.current = chatMessages.length;
    const raf = requestAnimationFrame(() => {
      el.scrollTo({
        top: el.scrollHeight,
        behavior: isNewMessage ? "smooth" : "auto",
      });
    });
    return () => cancelAnimationFrame(raf);
  }, [chatMessages.length, streamBuffer?.content]);

  // ── 长对话窗口化(方案 Phase 3.2)──
  // 长对话(数百条 markdown 消息)一次性渲染是移动端卡顿与内存占用主因,
  // 仅渲染最近 MESSAGE_WINDOW 条;顶部"加载更早"扩窗,并用 scrollHeight
  // 差值补偿 scrollTop,保证点击后视口停留在原消息上(不被新前置内容顶走)。
  const [messageWindow, setMessageWindow] = useState(MESSAGE_WINDOW);
  useEffect(() => {
    setMessageWindow(MESSAGE_WINDOW);
  }, [task.id]);
  const hiddenCount = Math.max(0, chatMessages.length - messageWindow);
  const visibleMessages = useMemo(
    () => (hiddenCount > 0 ? chatMessages.slice(-messageWindow) : chatMessages),
    [chatMessages, hiddenCount, messageWindow],
  );
  const prependScrollRef = useRef<number | null>(null);
  const loadEarlierMessages = () => {
    prependScrollRef.current = scrollRef.current?.scrollHeight ?? null;
    setMessageWindow((w) => w + MESSAGE_WINDOW);
  };
  // 扩窗提交后:把新增前置内容的高度加回 scrollTop(仅在点击后的一次提交执行)
  useEffect(() => {
    const prevHeight = prependScrollRef.current;
    if (prevHeight == null) return;
    prependScrollRef.current = null;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop += el.scrollHeight - prevHeight;
  });

  // Determine which panels are visible to compute correct default sizes
  const showContent = showContentPanel && openFiles.length > 0;
  const showResources = !!workspace && showRightPanel;
  const showExtra = showExtraPanel && !!extraPanelToggle;
  const panelCount =
    (showChatPanel ? 1 : 0) + (showResources ? 1 : 0) + (showContent ? 1 : 0) + (showExtra ? 1 : 0);

  // Build layout dynamically based on visibility — equal widths
  const chatDefault = panelCount <= 1 ? 100 : Math.round(100 / panelCount);
  const contentDefault = panelCount <= 1 ? 100 : Math.round(100 / panelCount);
  const rightDefault = panelCount <= 1 ? 100 : Math.round(100 / panelCount);

  // No panels visible — show a hint
  const noPanelVisible = panelCount === 0;

  // ── 移动端堆叠布局(方案 Phase 2 第 4 项) ──
  // <md:可拖拽多栏降级为单栏 + 顶部子视图切换。面板体提取为下方 const,桌面
  // ResizablePanelGroup 与移动堆叠树共享同一份 JSX —— 桌面端渲染结果保持不变。
  const isMobile = useIsMobile();
  type MobileView = "chat" | "resources" | "content" | "extra";
  const [mobileView, setMobileView] = useState<MobileView>("chat");

  // 新面板出现时自动切过去(仅在上升沿触发一次;用户手动切走后不拉回)
  const prevShowContentRef = useRef(showContent);
  const prevShowExtraRef = useRef(showExtra);
  useEffect(() => {
    if (isMobile && showContent && !prevShowContentRef.current) setMobileView("content");
    prevShowContentRef.current = showContent;
  }, [isMobile, showContent]);
  useEffect(() => {
    if (isMobile && showExtra && !prevShowExtraRef.current) setMobileView("extra");
    prevShowExtraRef.current = showExtra;
  }, [isMobile, showExtra]);

  // 当前视图对应的面板被关闭时,回退到第一个仍可见的视图
  const mobileViewVisible: Record<MobileView, boolean> = {
    chat: showChatPanel,
    resources: showResources,
    content: showContent,
    extra: showExtra,
  };
  const effMobileView = mobileViewVisible[mobileView]
    ? mobileView
    : ((["chat", "resources", "content", "extra"] as MobileView[]).find(
        (v) => mobileViewVisible[v],
      ) ?? "chat");

  const mobileTabs = [
    showChatPanel && {
      view: "chat" as const,
      label: t("chatView.mobileTab.chat"),
      icon: <MessageSquare className="w-3.5 h-3.5" />,
    },
    showResources && {
      view: "resources" as const,
      label: t("chatView.mobileTab.resources"),
      icon: <FolderOpen className="w-3.5 h-3.5" />,
    },
    showContent && {
      view: "content" as const,
      label: t("chatView.mobileTab.content"),
      icon: <FileText className="w-3.5 h-3.5" />,
    },
    showExtra &&
      extraPanelToggle && {
        view: "extra" as const,
        label: extraPanelToggle.label,
        icon: extraPanelToggle.icon,
      },
  ].filter(Boolean) as { view: MobileView; label: string; icon: ReactNode }[];

  // ── 共享面板体(桌面/移动两棵树引用同一份 JSX) ──
  const chatPanelBody = (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin">
        {/* Display mode toggle — moved to dialog display area */}
        <div className="sticky top-0 z-10 flex justify-center py-1.5">
          <div className="flex items-center gap-0.5 border border-border/60 rounded-md p-0.5 bg-background/80 backdrop-blur-sm shadow-sm">
            {[
              { mode: "minimal" as DisplayMode, label: t("chatView.display.minimal") },
              { mode: "default" as DisplayMode, label: t("chatView.display.default") },
              { mode: "detailed" as DisplayMode, label: t("chatView.display.detailed") },
            ].map(({ mode, label }) => (
              <button
                key={mode}
                onClick={() => setDisplayMode(mode)}
                className={cn(
                  "text-[10px] px-2 py-0.5 rounded transition",
                  displayMode === mode
                    ? "bg-brand/10 text-brand font-medium"
                    : "text-muted-foreground hover:text-foreground",
                )}
                title={label}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div
          className={cn(
            // 右侧资源面板隐藏时放宽容器，把腾出的宽度利用上
            "mx-auto pt-2 px-2 pb-4",
            showResources ? "max-w-3xl" : "max-w-6xl",
            compactMode ? "space-y-2" : "space-y-5",
          )}
        >
          {chatMessages.length === 0 && !streamBuffer ? (
            <EmptyState
              workspace={workspace}
              taskId={task.id}
              onInsert={(text) => requestInsert(task.id, text)}
              onTogglePanel={() => setShowRightPanel((v) => !v)}
              onUpload={handleUpload}
            />
          ) : (
            <>
              {hiddenCount > 0 && (
                <div className="flex justify-center pb-1">
                  <button
                    onClick={loadEarlierMessages}
                    className="text-xs text-muted-foreground underline underline-offset-2 hover:text-brand py-1"
                  >
                    {t("chatView.loadEarlier", { count: hiddenCount })}
                  </button>
                </div>
              )}
              {visibleMessages.map((m) => (
                <ChatMessageComponent
                  key={m.id}
                  message={m}
                  isStreaming={m.status === "streaming"}
                  displayMode={displayMode}
                  compactMode={compactMode}
                  fontSize={fontSize}
                  messageRendererExt={messageRendererExt}
                />
              ))}
            </>
          )}
        </div>
      </div>

      <FloatingInput
        task={task}
        workspace={workspace}
        placeholder={inputPlaceholder}
        wide={!showResources}
      />
    </div>
  );

  const resourcesPanelBody = workspace ? (
    <WorkspacePanel task={task} workspace={workspace} />
  ) : null;

  const contentPanelBody = (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border flex items-center gap-2 shrink-0">
        <FileText className="w-3.5 h-3.5 text-brand" />
        <span className="text-xs font-medium">{t("chatView.contentPreview")}</span>
        <span className="text-[10px] text-muted-foreground">
          {t("chatView.fileCount", { count: openFiles.length })}
        </span>
        <button
          onClick={() => setShowContentPanel(false)}
          className="ml-auto p-1 rounded hover:bg-muted/60 transition"
          title={t("chatView.contentPanel.close")}
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      {/* File content area */}
      <div className="flex-1 min-h-0">
        <FileContentArea
          files={openFiles}
          activeFileId={activeFileId}
          onActiveChange={(id) => setActiveFile(id)}
          onClose={(id) => closeFile(id)}
        />
      </div>
    </div>
  );

  const extraPanelBody = extraPanelToggle ? (
    <div className="flex flex-col h-full bg-background">
      <div className="px-3 py-2 border-b border-border flex items-center gap-2 shrink-0">
        <span className="text-brand">{extraPanelToggle.icon}</span>
        <span className="text-xs font-medium">{extraPanelToggle.label}</span>
        <button
          onClick={() => setShowExtraPanel(false)}
          className="ml-auto p-1 rounded hover:bg-muted/60 transition"
          title={t("chatView.panel.close")}
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">{extraPanelToggle.panel}</div>
    </div>
  ) : null;

  return (
    <div className="flex flex-col h-full">
      {/* ── Workspace Top Bar ── */}
      <div className="border-b border-border glass px-4 py-1.5 flex items-center gap-3 shrink-0">
        {workspace ? (
          <FolderOpen className="w-4 h-4 text-brand" />
        ) : (
          <MessageSquare className="w-4 h-4 text-brand" />
        )}
        <div className="flex flex-col leading-tight min-w-0">
          <div className="text-[11px] text-foreground/60">
            {workspace ? (
              <span>{t("chatView.workspace", { name: workspace.name })}</span>
            ) : (
              t("chatView.recentTask")
            )}
          </div>
          <div className="text-sm font-medium truncate">{task.title}</div>
        </div>
        {expert && (
          <Badge variant="outline" className="ml-2">
            {expert.name}
          </Badge>
        )}
        {/* E1: Extra top bar node (e.g. IP phase indicator) */}
        {extraTopBarNode}
        {/* Right-side panel toggles — all three panels independently hideable */}
        <div className="ml-auto flex items-center gap-1.5 min-w-0">
          {/* Open workspace settings drawer (LLM providers / MCP / agents …) */}
          {workspace && (
            <button
              onClick={() => {
                setFilesDrawerFor(workspace.id);
                setActiveDrawer("workspace-settings");
              }}
              className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-border hover:border-brand/40 hover:text-brand transition shrink-0"
              title={t("chatView.settings.title")}
            >
              <Settings className="w-3.5 h-3.5" />
              <span className="hidden md:inline">{t("chatView.settings.short")}</span>
            </button>
          )}
          {/* 面板 toggle 排:<md 隐藏 —— 移动端已有顶部子视图 Tab 行(方案
              Phase 2),同一职能双入口挤爆顶栏(真机反馈的"竖排图标条") */}
          <div className="hidden md:flex items-center gap-1.5">
            {/* Toggle chat panel */}
            <button
              onClick={() => setShowChatPanel((v) => !v)}
              className={
                showChatPanel
                  ? "inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-brand/40 text-brand transition"
                  : "inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-border hover:border-brand/40 hover:text-brand transition"
              }
              title={showChatPanel ? t("chatView.chat.close") : t("chatView.chat.open")}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              {t("chatView.chat")}
            </button>
            {/* Toggle resources panel */}
            {workspace && (
              <button
                onClick={() => setShowRightPanel((v) => !v)}
                className={
                  showRightPanel
                    ? "inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-brand/40 text-brand transition"
                    : "inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-border hover:border-brand/40 hover:text-brand transition"
                }
                title={
                  showRightPanel ? t("chatView.resources.close") : t("chatView.resources.open")
                }
              >
                <FolderOpen className="w-3.5 h-3.5" />
                {t("chatView.resources")}
              </button>
            )}
            {/* Toggle content editor panel */}
            {openFiles.length > 0 && (
              <button
                onClick={() => setShowContentPanel((v) => !v)}
                className={
                  showContentPanel
                    ? "inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-brand/40 text-brand transition"
                    : "inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-border hover:border-brand/40 hover:text-brand transition"
                }
                title={showContentPanel ? t("chatView.content.close") : t("chatView.content.open")}
              >
                <FileText className="w-3.5 h-3.5" />
                {t("chatView.content")}
              </button>
            )}
            {/* E2: Extra panel toggle (e.g. IP special panel) */}
            {extraPanelToggle && (
              <button
                onClick={() => setShowExtraPanel((v) => !v)}
                className={
                  showExtraPanel
                    ? "inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-brand/40 text-brand transition"
                    : "inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-border hover:border-brand/40 hover:text-brand transition"
                }
                title={
                  showExtraPanel
                    ? t("chatView.extra.close", { label: extraPanelToggle.label })
                    : t("chatView.extra.open", { label: extraPanelToggle.label })
                }
              >
                {extraPanelToggle.icon}
                {extraPanelToggle.label}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Connection status banner (connecting / reconnecting / error) ── */}
      {showConnBanner && (
        <div className="flex items-center gap-2 px-4 py-1.5 text-xs border-b border-border/60 shrink-0 bg-muted/30">
          {connectionState === "connecting" || connectionState === "reconnecting" ? (
            <>
              <Loader2 className="w-3 h-3 animate-spin text-yellow-500" />
              <span className="text-muted-foreground">
                {connectionState === "connecting"
                  ? t("chatView.conn.connecting")
                  : t("chatView.conn.reconnecting")}
              </span>
            </>
          ) : (
            <>
              <WifiOff className="w-3 h-3 text-red-500" />
              <span className="text-red-600 dark:text-red-400">{t("chatView.conn.failed")}</span>
              <button
                onClick={() => reconnect()}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-border hover:border-brand/40 hover:text-brand transition ml-auto"
              >
                <RefreshCw className="w-3 h-3" />
                {t("chatView.conn.retry")}
              </button>
            </>
          )}
        </div>
      )}

      {/* ── Agent degraded features banner ── */}
      {task.workspaceId && <AgentDegradedBanner workspaceId={task.workspaceId} />}

      {/* ── History load error banner ── */}
      {historyLoadErrors[task.id] && (
        <div className="flex items-center gap-2 px-4 py-1.5 text-xs border-b border-border/60 shrink-0 bg-amber-50 dark:bg-amber-950/20">
          <AlertTriangle className="w-3 h-3 text-amber-500 shrink-0" />
          <span className="text-muted-foreground">{t("chatView.history.failed")}</span>
          <span className="text-[11px] text-muted-foreground/70 truncate max-w-60">
            {historyLoadErrors[task.id]}
          </span>
          <button
            onClick={() => retryLoadHistory(task.id, task.workspaceId!)}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-border hover:border-brand/40 hover:text-brand transition ml-auto shrink-0"
          >
            <RefreshCw className="w-3 h-3" />
            {t("common.retry")}
          </button>
        </div>
      )}

      {/* ── Panel area ── */}
      {noPanelVisible ? (
        <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
          {t("chatView.noPanelHint")}
        </div>
      ) : isMobile ? (
        /* 移动端:单栏堆叠 + 顶部子视图切换,一次只显示一个面板(方案 Phase 2 第 4 项) */
        <div className="flex-1 min-w-0 flex flex-col">
          <div
            className="flex items-stretch border-b border-border bg-muted/30 shrink-0 overflow-x-auto scrollbar-thin"
            role="tablist"
          >
            {mobileTabs.map(({ view, label, icon }) => (
              <button
                key={view}
                role="tab"
                aria-selected={effMobileView === view}
                onClick={() => setMobileView(view)}
                className={cn(
                  "flex-1 min-w-0 min-h-11 flex items-center justify-center gap-1.5 px-2 text-xs border-b-2 transition",
                  effMobileView === view
                    ? "border-brand text-brand font-medium bg-background"
                    : "border-transparent text-muted-foreground",
                )}
              >
                {icon}
                <span className="truncate">{label}</span>
              </button>
            ))}
          </div>
          <div className="flex-1 min-h-0">
            {effMobileView === "chat" && chatPanelBody}
            {effMobileView === "resources" && resourcesPanelBody}
            {effMobileView === "content" && contentPanelBody}
            {effMobileView === "extra" && extraPanelBody}
          </div>
        </div>
      ) : (
        <ResizablePanelGroup
          id="workspace-layout"
          orientation="horizontal"
          className="flex-1 min-w-0"
        >
          {/* ── Workspace Chat Panel ── */}
          {showChatPanel && (
            <ResizablePanel id="workspace-chat-panel" defaultSize={chatDefault} minSize={25}>
              {chatPanelBody}
            </ResizablePanel>
          )}

          {/* ── Workspace Resources (file tree + context) ── */}
          {showResources && (
            <>
              {showChatPanel && <ResizableHandle withHandle />}
              <ResizablePanel id="workspace-resources" defaultSize={rightDefault} minSize={15}>
                {resourcesPanelBody}
              </ResizablePanel>
            </>
          )}

          {/* ── Workspace Content Editor (file preview) ── */}
          {showContent && (
            <>
              {(showChatPanel || showResources || showExtra) && <ResizableHandle withHandle />}
              <ResizablePanel
                id="workspace-content-editor"
                defaultSize={contentDefault}
                minSize={15}
                className="border-l border-border"
              >
                {contentPanelBody}
              </ResizablePanel>
            </>
          )}

          {/* ── E2: Extra panel (injected via extraPanelToggle) ── */}
          {showExtra && extraPanelToggle && (
            <>
              {(showChatPanel || showResources || showContent) && <ResizableHandle withHandle />}
              <ResizablePanel
                id="workspace-extra-panel"
                defaultSize={rightDefault}
                minSize={15}
                className="border-l border-border"
              >
                {extraPanelBody}
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>
      )}

      {/* ── Follow-up question dialog (ask_followup_question, human-in-the-loop) ── */}
      <FollowupQuestionDialog
        open={!!followup}
        onOpenChange={(o) => {
          // ESC / 点击遮罩关闭 = 取消追问（作答/点取消后 followup 已置空，此处为 no-op）
          if (!o) cancelFollowup(task.id);
        }}
        question={followup?.question ?? ""}
        suggestions={followup?.suggestions ?? []}
        toolCallId={followup?.toolCallId}
        taskId={followup?.taskId}
        onResponse={(text) => respondFollowup(task.id, text)}
        onCancel={() => cancelFollowup(task.id)}
      />
    </div>
  );
}

function EmptyState({
  workspace,
  taskId,
  onInsert,
  onTogglePanel,
  onUpload,
}: {
  workspace?: Workspace;
  taskId: string;
  onInsert: (text: string) => void;
  onTogglePanel: () => void;
  onUpload: () => void;
}) {
  const { t } = useTranslation("commonUi");
  if (workspace) {
    void taskId;

    // ── biz 注册空状态：workspaceType === prefix 或 name 以 prefix- 开头命中 ──
    // （原 IP_EMPTY_STATES 推导的注册表化等价形式；命中优先级 = 表序）
    const ipConfig = BIZ_WORKSPACE_EMPTY_STATES.find(
      (e) => workspace.workspaceType === e.prefix || workspace.name?.startsWith(e.prefix + "-"),
    )?.config;

    if (ipConfig) {
      // Resolve the icon component by name
      const iconMap: Record<string, ReactNode> = {
        Lightbulb: <LightbulbIcon className="w-5 h-5 text-brand-foreground" />,
        FileText: <FileText className="w-5 h-5 text-brand-foreground" />,
        PenTool: <PenTool className="w-5 h-5 text-brand-foreground" />,
        Send: <Send className="w-5 h-5 text-brand-foreground" />,
        MessageSquare: <MessageSquare className="w-5 h-5 text-brand-foreground" />,
        Shield: <Shield className="w-5 h-5 text-brand-foreground" />,
        Ticket: <Ticket className="w-5 h-5 text-brand-foreground" />,
      };
      const moduleIcon = iconMap[ipConfig.icon] ?? (
        <LightbulbIcon className="w-5 h-5 text-brand-foreground" />
      );

      return (
        <div className="py-8 px-4">
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-brand shadow-brand mb-3">
              {moduleIcon}
            </div>
            <h2 className="text-2xl font-semibold tracking-tight">{ipConfig.title}</h2>
            <p className="text-sm text-muted-foreground mt-1.5 max-w-sm mx-auto">
              {ipConfig.description}
            </p>
          </div>

          {/* Primary action */}
          <div className="flex items-center justify-center gap-3 mb-6">
            <button
              onClick={ipConfig.primaryIsUpload ? onUpload : onTogglePanel}
              className="inline-flex items-center gap-1.5 text-xs px-4 py-2 rounded-lg bg-brand text-brand-foreground hover:bg-brand/90 transition font-medium"
            >
              {ipConfig.primaryIsUpload ? (
                <Upload className="w-3.5 h-3.5" />
              ) : (
                <Sparkles className="w-3.5 h-3.5" />
              )}
              {ipConfig.primaryAction}
            </button>
            {ipConfig.secondaryAction && (
              <button
                onClick={() => {
                  if (ipConfig.secondaryActionPrompt) {
                    onInsert(ipConfig.secondaryActionPrompt);
                  } else {
                    onTogglePanel();
                  }
                }}
                className="inline-flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg border border-border hover:border-brand/40 hover:text-brand transition bg-card/40"
              >
                {ipConfig.secondaryActionPrompt ? (
                  <Sparkles className="w-3.5 h-3.5" />
                ) : (
                  <FolderOpen className="w-3.5 h-3.5" />
                )}
                {ipConfig.secondaryAction}
              </button>
            )}
          </div>

          <div className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground">
            <Lightbulb className="w-3 h-3 text-brand" />
            {t("chatView.atTip.prefix")}{" "}
            <code className="px-1 py-0.5 rounded bg-muted/60 text-foreground">@</code>{" "}
            {t("chatView.atTip.suffix")}
          </div>
        </div>
      );
    }

    // ── biz 注册空状态组件(market/social/firm agent 等,assemble 注入;核心构建 = 空表不命中) ──
    const emptyCompEntry = BIZ_WORKSPACE_EMPTY_COMPONENTS.find((e) =>
      e.match({ workspaceType: workspace.workspaceType, name: workspace.name }),
    );
    if (emptyCompEntry) {
      const EmptyComponent = emptyCompEntry.component;
      return <EmptyComponent onInsert={onInsert} />;
    }

    // ── Generic workspace empty state ──
    return (
      <div className="py-8 px-4">
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-brand shadow-brand mb-3">
            <FolderOpen className="w-5 h-5 text-brand-foreground" />
          </div>
          <h2 className="text-2xl font-semibold tracking-tight">
            {t("chatView.empty.startIn", { name: workspace.name })}
          </h2>
        </div>

        {/* Quick actions */}
        <div className="flex items-center justify-center gap-3 mb-6">
          <button
            onClick={onTogglePanel}
            className="inline-flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg border border-border hover:border-brand/40 hover:text-brand transition bg-card/40"
          >
            <FolderOpen className="w-3.5 h-3.5" />
            {t("chatView.empty.browseFiles")}
          </button>
        </div>

        <div className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground">
          <Lightbulb className="w-3 h-3 text-brand" />
          {t("chatView.atTip.prefix")}{" "}
          <code className="px-1 py-0.5 rounded bg-muted/60 text-foreground">@</code>{" "}
          {t("chatView.atTip.suffix")}
        </div>
      </div>
    );
  }

  // Temporary task empty state — load teams from market API
  return <TempTaskEmptyState onInsert={onInsert} />;
}

/** Separate component so we can use hooks for team fetching */
function TempTaskEmptyState({ onInsert }: { onInsert: (text: string) => void }) {
  const { t } = useTranslation("commonUi");
  const [teams, setTeams] = useState<TeamHierarchyEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const loadTeams = useCallback(async () => {
    try {
      const res = await marketApi.getTeamHierarchy();
      const list = res?.teams?.filter((t) => t.enabled !== false) ?? [];
      setTeams(list);
    } catch (e) {
      console.error("Failed to load teams for temp page:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTeams();
  }, [loadTeams]);

  if (loading) {
    return (
      <div className="text-center py-12 px-4">
        <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
      </div>
    );
  }

  if (teams.length === 0) {
    return (
      <div className="text-center py-12 px-4">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-brand shadow-brand mb-4">
          <Sparkles className="w-6 h-6 text-brand-foreground" />
        </div>
        <h2 className="text-2xl font-semibold tracking-tight">{t("chatView.empty.startChat")}</h2>
        <p className="text-sm text-muted-foreground mt-2">{t("chatView.empty.noTeams")}</p>
      </div>
    );
  }

  return (
    <div className="text-center py-12 px-4">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-brand shadow-brand mb-4">
        <Sparkles className="w-6 h-6 text-brand-foreground" />
      </div>
      <h2 className="text-2xl font-semibold tracking-tight">{t("chatView.empty.startChat")}</h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
        {t("chatView.empty.tryAsk")}
      </p>
      <div className="mt-8 max-w-3xl mx-auto">
        <div className="flex items-center mb-3 px-1">
          <span className="text-xs font-medium text-muted-foreground inline-flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5 text-brand" />
            {t("chatView.empty.chooseExpert", { count: teams.length })}
          </span>
        </div>
        <div className="flex gap-3 overflow-x-auto scrollbar-thin pb-3 -mx-2 px-2 snap-x">
          {teams.map((team, idx) => (
            <button
              key={team.slug || team.name || idx}
              onClick={() => onInsert(`@${team.name}`)}
              className="shrink-0 w-[200px] snap-start bg-card/60 border border-border rounded-xl p-3 text-left hover:border-brand/40 transition"
            >
              <div className="flex items-center gap-2 mb-2">
                <div className="w-7 h-7 rounded-lg bg-brand/10 flex items-center justify-center shrink-0 text-sm">
                  {team.icon ? String(team.icon) : <Users className="w-4 h-4 text-brand" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium truncate">{team.name}</div>
                  {team.slug && (
                    <div className="text-[10px] text-muted-foreground truncate">{team.slug}</div>
                  )}
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground/80 line-clamp-2 leading-relaxed">
                {team.description ||
                  t("chatView.empty.memberCount", {
                    count: team.members_count ?? team.members?.length ?? 0,
                  })}
              </p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
