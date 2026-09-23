import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import {
  ArrowUp,
  Paperclip,
  Users,
  AtSign,
  Sparkles,
  Loader2,
  StopCircle,
  Slash,
  Database,
  Cpu,
  Settings2,
  WifiOff,
  Check,
} from "lucide-react";
import { modesToExperts, scopeModesByExpert } from "@/lib/experts";
import {
  useStore,
  modelsOfficialFirst,
  type Task,
  type Workspace,
  type WorkspaceMode,
} from "@/lib/store";
import { useChatStore } from "@/lib/chat-store";
import { useConnectionStore } from "@/lib/connection-store";
import { useTaskStore } from "@/lib/task-store";
import { wsClient } from "@/lib/ws-client";
import { ExpertIcon, getCategoryHue } from "@/components/expert-icon";
import { cn } from "@/lib/utils";
import { SlashCommands, type SlashCommand } from "@/components/chat/slash-commands";
import {
  ResourceMention,
  saveRecentMention,
  type MentionItem,
} from "@/components/chat/resource-mention";
import { FileUploadDialog } from "@/components/chat/file-upload-dialog";
import { useWorkspaceFilesStore } from "@/lib/workspace-files-store";

interface Props {
  task: Task;
  workspace?: Workspace;
  /** E4: Custom placeholder text for the input area */
  placeholder?: string;
  /** 右侧资源面板隐藏时为 true — 输入框与消息区同步放宽 */
  wide?: boolean;
}

/** Stable empty array ref — avoids new [] on every selector call (React infinite-render fix) */
const EMPTY_MODES: WorkspaceMode[] = [];

export function FloatingInput({ task, workspace, placeholder, wide }: Props) {
  const { t } = useTranslation("commonUi");
  const addMessage = useStore((s) => s.addMessage);
  const setTaskModel = useStore((s) => s.setTaskModel);
  const setTaskExpert = useStore((s) => s.setTaskExpert);
  const setTaskMode = useStore((s) => s.setTaskMode);
  const pendingInsert = useStore((s) => s.pendingInsert);
  const consumeInsert = useStore((s) => s.consumeInsert);
  const setActiveDrawer = useStore((s) => s.setActiveDrawer);
  const models = useStore((s) => s.models);
  // 切换模型下拉：官方模型排在上方（仅展示顺序，不影响默认模型选择）
  const orderedModels = useMemo(() => modelsOfficialFirst(models), [models]);
  const ensureConversation = useChatStore((s) => s.ensureConversation);
  const setStreaming = useChatStore((s) => s.setStreaming);
  const finalizeStaleStreams = useChatStore((s) => s.finalizeStaleStreams);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const getMessages = useChatStore((s) => s.getMessages);
  const connectionState = useConnectionStore((s) => s.state);
  const reconnect = useConnectionStore((s) => s.connect);
  const knowledgeBases = useWorkspaceFilesStore((s) => s.knowledgeBases);
  const isOnline = connectionState === "connected";
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  // 会话级流式状态：人工发送(handleSend)与自动开场白(chat-view autoStart)都会置 isStreaming=true。
  // 发送按钮的忙碌态据此（而非仅本地 sending）驱动，保证两条发送路径行为一致。
  const isStreaming = useChatStore((s) => s.conversations.get(task.id)?.isStreaming ?? false);
  const busy = sending || isStreaming;
  const taRef = useRef<HTMLTextAreaElement>(null);
  const streamUnsubRef = useRef<(() => void) | null>(null); // cleanup for stream subscription

  // ── Refs to avoid stale closures in callbacks ──────────────────
  const inputRef = useRef(input);
  inputRef.current = input;
  const busyRef = useRef(busy);
  busyRef.current = busy;

  // ── Workspace modes for expert mention ──────────────────────
  const { workspaceModes, agentModes } = useStore(
    useShallow((s) => {
      const ws = s.workspaces.find((w) => w.id === workspace?.id);
      return { workspaceModes: ws?.modes ?? EMPTY_MODES, agentModes: ws?.agentModes };
    }),
  );

  // Load workspace resources when entering a workspace
  useEffect(() => {
    if (workspace?.id) useStore.getState().fetchWorkspaceResources(workspace.id);
  }, [workspace?.id]);

  // Popover state for slash commands and resource mentions
  const [showSlash, setShowSlash] = useState(false);
  const [showMention, setShowMention] = useState(false);
  const [showUpload, setShowUpload] = useState(false);

  // Controlled popover state for /model and /expert slash commands
  const [showModelPopover, setShowModelPopover] = useState(false);
  const [showExpertPopover, setShowExpertPopover] = useState(false);

  // File tree for @mention files tab — individual selectors to avoid full-store re-renders
  const fileTree = useWorkspaceFilesStore((s) => s.fileTree);

  // Fetch file tree when workspace changes
  useEffect(() => {
    if (workspace?.id) {
      useWorkspaceFilesStore.getState().fetchFileTree(workspace.id);
    }
  }, [workspace?.id]);

  // Flatten file tree for ResourceMention
  const allWorkspaceFiles = useMemo(() => {
    if (!workspace) return [];
    const flatten = (items: typeof fileTree): { id: string; name: string; path?: string; kind?: string }[] => {
      return items.flatMap((item) => {
        const current = { id: item.path, name: item.name, path: item.path, kind: item.type as string | undefined };
        const children =
          "children" in item ? (item as { children?: typeof fileTree }).children : undefined;
        return children && children.length > 0 ? [current, ...flatten(children)] : [current];
      });
    };
    return flatten(fileTree);
  }, [fileTree, workspace]);

  // Knowledge base selection persistence
  const [lastKbId, setLastKbId] = useState<string | null>(() => {
    try {
      return localStorage.getItem("normnomos-last-kb");
    } catch {
      return null;
    }
  });

  // Auto-resize textarea
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    if (!input) {
      // 空内容交给 CSS(min-h 36px + rows=1):Chrome 下空 textarea 的 scrollHeight
      // 会把换行的 placeholder 高度算进去,导致「初始很高、输入后骤缩」
      ta.style.height = "";
      return;
    }
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [input]);

  // Cleanup stream subscription on unmount
  useEffect(() => {
    return () => {
      streamUnsubRef.current?.();
      streamUnsubRef.current = null;
    };
  }, []);

  // ── 移动端软键盘避让(方案 Phase 2 第 4 项) ──
  // iOS 上键盘弹起时 visualViewport 收缩,但 100dvh 布局视口不变,composer 会被
  // 键盘整体盖住。这里把「键盘占用高度」写入全局 CSS 变量,composer 用它把输入
  // 卡片抬到键盘上方;键盘收起/桌面端(无软键盘)时移除变量,布局回到 pb 基线。
  // 仅在粗指针(触屏)设备启用 —— 桌面端零影响(含桌面 pinch-zoom)。
  useEffect(() => {
    if (!window.visualViewport || !window.matchMedia("(pointer: coarse)").matches) return;
    const vv = window.visualViewport;
    const apply = () => {
      const root = document.documentElement;
      const keyboardHeight = window.innerHeight - vv.height;
      if (keyboardHeight > 24) {
        root.style.setProperty("--app-keyboard-height", `${keyboardHeight}px`);
      } else {
        root.style.removeProperty("--app-keyboard-height");
      }
    };
    apply();
    vv.addEventListener("resize", apply);
    vv.addEventListener("scroll", apply);
    return () => {
      vv.removeEventListener("resize", apply);
      vv.removeEventListener("scroll", apply);
      document.documentElement.style.removeProperty("--app-keyboard-height");
    };
  }, []);

  // Consume pending insert requests from other components
  useEffect(() => {
    if (pendingInsert && pendingInsert.taskId === task.id) {
      const text = consumeInsert(task.id);
      if (text) {
        setInput((v) => (v ? `${v} ${text} ` : `${text} `));
        taRef.current?.focus();
      }
    }
  }, [pendingInsert, task.id, consumeInsert]);

  // ── Input change handler with trigger detection ────────────────
  const handleInputChange = useCallback((value: string) => {
    setInput(value);

    // Detect '/' at start or after space → show slash commands
    if (value === "/" || (value.startsWith("/") && value.length <= 20)) {
      setShowSlash(true);
      setShowMention(false);
    } else {
      setShowSlash(false);

      // Detect '@' → show resource mention
      // Only trigger if @ is at the end or followed by 1-15 chars of text
      const atMatch = value.match(/@(\S{0,15})$/);
      if (atMatch) {
        setShowMention(true);
      } else {
        setShowMention(false);
      }
    }
  }, []);

  // ── Send ───────────────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    const text = inputRef.current.trim();
    if (!text || busyRef.current) return;
    if (!task.model) return; // No model selected — cannot send
    setSending(true);
    setInput("");
    setShowSlash(false);
    setShowMention(false);

    if (isOnline) {
      // Real backend path via WebSocket
      // task.id IS the backend conversation UUID (set by createTask via POST /api/.../conversations).
      // Ensure chat-store has a conversation entry, then send via WS.
      ensureConversation(task.id, {
        title: task.title,
        model: task.model,
        expertId: task.expertId,
        mode: task.mode,
      });

      // Add user message to local display immediately (optimistic UI)
      const convId = task.id;
      useChatStore.setState((s) => {
        const next = new Map(s.conversations);
        const c = next.get(convId);
        if (!c) return {};
        const userMsg = {
          id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          role: "user" as const,
          content: text,
          status: "complete" as const,
          ts: Date.now(),
        };
        const title = c.messages.length === 0 ? text.slice(0, 24) : c.title;
        next.set(convId, {
          ...c,
          title,
          messages: [...c.messages, userMsg],
        });
        return { conversations: next };
      });

      // Send message via WS with workspace context + UI metadata
      // 查出所选模型的来源/provider 配置名，明确告诉后端走本地 provider 还是官方网关。
      const modelObj = models.find((m) => m.id === task.model);
      wsClient.send({
        type: "user_message",
        content: text,
        conversation_id: task.id,
        workspace_id: task.workspaceId ?? undefined,
        data: {
          mode: task.mode,
          model: task.model,
          expert_id: task.expertId,
          auth_token: localStorage.getItem("auth_token") || undefined,
        },
        user_ui_context: {
          current_experts: task.expertId ? [task.expertId] : [],
          current_llm_id: task.model,
          current_llm_source: modelObj?.source,
          current_config_name: modelObj?.configName,
        },
      });

      // Mark streaming in chat-store so UI shows loading state until backend responds
      setStreaming(task.id, true);

      // Subscribe to stream completion for this conversation (event-driven, no polling)
      streamUnsubRef.current?.(); // cleanup any previous subscription
      streamUnsubRef.current = useChatStore.subscribe((state) => {
        const conv = state.conversations.get(task.id);
        if (conv && !conv.isStreaming) {
          setSending(false);
          streamUnsubRef.current?.();
          streamUnsubRef.current = null;
        }
      });
    } else {
      // Backend not connected — show error via legacy task.messages
      const details =
        connectionState === "error"
          ? t("input.connFailedDetail")
          : connectionState === "reconnecting"
            ? t("input.reconnectingDetail")
            : t("input.connectFirstDetail");
      addMessage(task.id, {
        role: "agent",
        agentId: "system",
        agentName: t("input.systemAgent"),
        content: t("input.cannotConnect", { reason: details }),
      });
      // Don't clear input so user can retry after reconnect
      setInput(text);
      setSending(false);
    }
  }, [
    isOnline,
    connectionState,
    task.id,
    task.title,
    task.model,
    task.expertId,
    task.mode,
    task.workspaceId,
    ensureConversation,
    setStreaming,
    addMessage,
    t,
  ]);

  // ── Textarea keydown ───────────────────────────────────────────
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // If slash or mention is open, let those components handle keys
      if (showSlash || showMention) return;

      // Ctrl+Enter or Meta+Enter: always send
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        handleSend();
        return;
      }

      // Enter without Shift: send
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [showSlash, showMention, handleSend],
  );

  const handleStop = useCallback(() => {
    // 1) 解除 stream 完成订阅（停止场景下不再依赖该订阅收尾）
    streamUnsubRef.current?.();
    streamUnsubRef.current = null;

    // 2) 通知后端终止正在执行的 Agent。
    //    task_id 优先用后端在 task_node_start 里回传的执行态 id，
    //    没有则回退 conversation_id（后端 _active_agents 未命中时也会发 stopped 确认）。
    //    🔧 修复：去掉 isOnline 门控 —— ws-client 断线时会把消息入队、重连后补发；
    //    此前断线/重连中直接静默跳过，后端从未收到 agent_stop（"点了停止还在继续"）。
    const taskStore = useTaskStore.getState();
    const backendTaskId = task.workspaceId ? taskStore.getCurrentTaskId(task.workspaceId) : null;
    wsClient.send({
      type: "agent_stop",
      conversation_id: task.id,
      task_id: backendTaskId ?? task.id,
    });

    // 3) 乐观收尾：立即结束会话流式态，并把消息级 streaming/pending
    //    状态收口为 complete（终态事件缺失时转圈永不复位）。
    //    即使后端 stopped 确认丢失/延迟，前端也不会卡死在忙碌态。
    setSending(false);
    finalizeStaleStreams(task.id);
  }, [task.workspaceId, task.id, finalizeStaleStreams]);

  // ── Slash command handler ──────────────────────────────────────
  const handleSlashSelect = useCallback(
    (cmd: SlashCommand) => {
      setShowSlash(false);
      switch (cmd.id) {
        // ── P0: /clear vs /reset differentiation ──
        case "clear":
          setInput("");
          clearMessages(task.id);
          break;

        case "reset":
          setInput("");
          clearMessages(task.id);
          // Notify backend to reset conversation
          wsClient.send({
            type: "reset_conversation",
            conversation_id: task.id,
          });
          // Reset task context — clear model/expert to undefined (no hardcoded default)
          setTaskModel(task.id, undefined);
          setTaskExpert(task.id, undefined);
          break;

        // ── P1: /help → open help drawer ──
        case "help":
          setInput("");
          setActiveDrawer("help");
          break;

        // ── P1: /model → open model popover ──
        case "model":
          setInput("");
          setShowModelPopover(true);
          break;

        // ── P1: /expert → open expert popover ──
        case "expert":
          setInput("");
          setShowExpertPopover(true);
          break;

        // ── P2: /summarize → construct summary request ──
        case "summarize":
          setInput("");
          ensureConversation(task.id, {
            title: task.title,
            model: task.model,
            expertId: task.expertId,
            mode: task.mode,
          });
          wsClient.send({
            type: "user_message",
            content: "请总结以上对话的关键要点和法律建议。",
            conversation_id: task.id,
            workspace_id: task.workspaceId ?? undefined,
            data: {
              mode: task.mode,
              model: task.model,
              expert_id: task.expertId,
              auth_token: localStorage.getItem("auth_token") || undefined,
            },
            user_ui_context: {
              current_experts: task.expertId ? [task.expertId] : [],
              current_llm_id: task.model,
              current_llm_source: models.find((m) => m.id === task.model)?.source,
              current_config_name: models.find((m) => m.id === task.model)?.configName,
              action: "summarize",
            },
          });
          setStreaming(task.id, true);
          break;

        // ── P2: /analyze → open file upload dialog ──
        case "analyze":
          setInput("");
          if (!task.workspaceId) {
            addMessage(task.id, {
              role: "agent",
              agentId: "system",
              agentName: t("input.systemAgent"),
              content: t("input.needWorkspace"),
            });
            break;
          }
          setShowUpload(true);
          break;

        // ── P2: /task → insert text, let backend handle the rest ──
        case "task":
          setInput("/task ");
          taRef.current?.focus();
          break;

        // ── P3: /chat → switch to single chat mode, clear expert ──
        case "chat":
          setInput("");
          setTaskExpert(task.id, undefined);
          setTaskMode(task.id, "single");
          break;

        // ── gelu-research pipeline commands (PRD §6.4.2) ──
        // Select the pipeline orchestrator expert + team mode, then insert a
        // kickoff template the user completes (topic / stage / pdf path).
        case "review-run":
          setTaskExpert(task.id, "review-orchestrator");
          setTaskMode(task.id, "team");
          setInput(t("slash.gelu.reviewRunTemplate"));
          taRef.current?.focus();
          break;

        // /paper status needs no args — send the tracking-table request now.
        case "paper-status":
          setInput("");
          setTaskExpert(task.id, "paper-orchestrator");
          setTaskMode(task.id, "team");
          ensureConversation(task.id, {
            title: task.title,
            model: task.model,
            expertId: "paper-orchestrator",
            mode: "team",
          });
          wsClient.send({
            type: "user_message",
            content: t("slash.gelu.paperStatusMessage"),
            conversation_id: task.id,
            workspace_id: task.workspaceId ?? undefined,
            data: {
              mode: "team",
              model: task.model,
              expert_id: "paper-orchestrator",
              auth_token: localStorage.getItem("auth_token") || undefined,
            },
            user_ui_context: {
              current_experts: ["paper-orchestrator"],
              current_llm_id: task.model,
              current_llm_source: models.find((m) => m.id === task.model)?.source,
              current_config_name: models.find((m) => m.id === task.model)?.configName,
              action: "paper_status",
            },
          });
          setStreaming(task.id, true);
          break;

        case "paper-switch":
          setTaskExpert(task.id, "paper-orchestrator");
          setTaskMode(task.id, "team");
          setInput(t("slash.gelu.paperSwitchTemplate"));
          taRef.current?.focus();
          break;

        case "lens-run":
          setTaskExpert(task.id, "lens-orchestrator");
          setTaskMode(task.id, "team");
          setInput(t("slash.gelu.lensRunTemplate"));
          taRef.current?.focus();
          break;

        // Critique is a standalone expert mode (S08), not an orchestrator.
        case "lens-critique":
          setTaskExpert(task.id, "paper-ppt-critique");
          setTaskMode(task.id, "single");
          setInput(t("slash.gelu.lensCritiqueTemplate"));
          taRef.current?.focus();
          break;

        default:
          // For unknown commands, insert the command name
          setInput(`${cmd.name} `);
          taRef.current?.focus();
          break;
      }
    },
    [
      clearMessages,
      task.id,
      task.title,
      task.model,
      task.expertId,
      task.mode,
      task.workspaceId,
      models,
      setTaskModel,
      setTaskExpert,
      setTaskMode,
      setActiveDrawer,
      ensureConversation,
      setStreaming,
      addMessage,
      t,
    ],
  );

  // ── Mention select handler ─────────────────────────────────────
  const handleMentionSelect = useCallback(
    (item: MentionItem) => {
      setShowMention(false);
      // Replace the @query part with @name
      setInput((v) => v.replace(/@\S{0,15}$/, `@${item.name} `));
      saveRecentMention(item.id, item.name, item.type);

      // Sync expert context: if an expert is selected via @, update task.expertId
      if (item.type === "expert") {
        setTaskExpert(task.id, item.id);
      }
      // File references are handled by backend AtMessageProcessor

      taRef.current?.focus();
    },
    [setTaskExpert, task.id],
  );

  // ── Expert / file quick insert ─────────────────────────────────
  const insertExpert = (name: string) => {
    setInput((v) => (v ? `${v} @${name} ` : `@${name} `));
    taRef.current?.focus();
  };

  // Experts to display: workspace modes converted to Expert objects.
  // 按当前任务的入口专家所属 agent 过滤（见 experts.ts scopeModesByExpert）。
  const scopedModes = useMemo(
    () => scopeModesByExpert(workspaceModes, agentModes, task.expertId),
    [agentModes, task.expertId, workspaceModes],
  );
  const onlineExperts = useMemo(() => modesToExperts(scopedModes), [scopedModes]);

  return (
    <div
      className="px-4 sticky bottom-0 z-10"
      // 键盘弹起(触屏)→ 抬高到键盘上方;否则 pb 基线 = pb-4(桌面端与原值一致)
      // + 底部 safe-area(刘海屏 home 横条)
      style={{
        paddingBottom: "var(--app-keyboard-height, max(1rem, env(safe-area-inset-bottom)))",
      }}
    >
      {/* Top fade */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-6 h-6 bg-gradient-to-b from-transparent to-background"
      />
      <div className={cn("mx-auto relative", wide ? "max-w-6xl" : "max-w-3xl")}>
        {/* Expert chips (after first message sent) */}
        {getMessages(task.id).length > 0 && (
          <div className="mb-2 flex items-center gap-2 overflow-x-auto scrollbar-thin pb-1">
            {workspace ? (
              <>
                <HoverCard openDelay={120} closeDelay={80}>
                  <HoverCardTrigger asChild>
                    <button
                      type="button"
                      className="shrink-0 inline-flex items-center gap-2 px-2 py-1 rounded-full bg-brand/10 border border-brand/30 hover:bg-brand/15 transition cursor-default"
                      title={t("input.configuredTitle")}
                    >
                      <div className="flex -space-x-1.5">
                        {onlineExperts.slice(0, 3).map((e) => (
                          <ExpertIcon
                            key={e.id}
                            emoji={e.icon}
                            hue={getCategoryHue(e.category)}
                            size="sm"
                            shape="circle"
                            className="!w-5 !h-5 ring-2 ring-background"
                          />
                        ))}
                      </div>
                      <span className="text-[11px] text-brand">
                        {t("input.configuredCount", { count: onlineExperts.length })}
                      </span>
                    </button>
                  </HoverCardTrigger>
                  <HoverCardContent align="start" className="w-64 p-3">
                    <div className="flex items-center gap-1.5 mb-2">
                      <Sparkles className="w-3.5 h-3.5 text-brand" />
                      <span className="text-xs font-medium">{t("input.configuredExperts")}</span>
                      <span className="ml-auto text-[10px] text-muted-foreground">
                        {t("input.autoCollaborate")}
                      </span>
                    </div>
                    <div className="space-y-1.5 max-h-64 overflow-y-auto scrollbar-thin">
                      {onlineExperts.map((e) => (
                        <div key={e.id} className="flex items-center gap-2">
                          <ExpertIcon
                            emoji={e.icon}
                            hue={getCategoryHue(e.category)}
                            size="sm"
                            className="!w-6 !h-6 shrink-0"
                          />
                          <span className="text-xs">{e.name}</span>
                        </div>
                      ))}
                    </div>
                  </HoverCardContent>
                </HoverCard>
                <span className="shrink-0 h-4 w-px bg-border" />
                {onlineExperts.slice(3).map((e) => (
                  <button
                    key={e.id}
                    onClick={() => insertExpert(e.name)}
                    className="shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-card/60 hover:bg-card border border-border text-xs transition"
                  >
                    <ExpertIcon
                      emoji={e.icon}
                      hue={getCategoryHue(e.category)}
                      size="sm"
                      className="!w-4 !h-4 !rounded-md"
                    />
                    {e.name}
                  </button>
                ))}
              </>
            ) : (
              <>
                <span className="text-[11px] text-muted-foreground shrink-0 inline-flex items-center gap-1">
                  <Sparkles className="w-3 h-3" /> {t("input.commonExperts")}
                </span>
                {onlineExperts.slice(0, 8).map((e) => (
                  <button
                    key={e.id}
                    onClick={() => insertExpert(e.name)}
                    className="shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-card/60 hover:bg-card border border-border text-xs transition"
                  >
                    <ExpertIcon
                      emoji={e.icon}
                      hue={getCategoryHue(e.category)}
                      size="sm"
                      className="!w-4 !h-4 !rounded-md"
                    />
                    {e.name}
                  </button>
                ))}
              </>
            )}
          </div>
        )}

        {/* Input wrapper with relative positioning for popovers */}
        <div className="relative">
          {/* Slash commands popover */}
          <SlashCommands
            visible={showSlash}
            onSelect={handleSlashSelect}
            onClose={() => setShowSlash(false)}
          />

          {/* Resource mention popover */}
          <ResourceMention
            visible={showMention}
            workspaceFiles={allWorkspaceFiles}
            experts={onlineExperts}
            onSelect={handleMentionSelect}
            onClose={() => setShowMention(false)}
          />

          <div className="rounded-2xl border border-border shadow-card overflow-hidden bg-background/95 backdrop-blur-md">
            <Textarea
              ref={taRef}
              value={input}
              onChange={(e) => handleInputChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                placeholder ??
                (workspace
                  ? t("input.placeholder.workspace", { name: workspace.name })
                  : t("input.placeholder.default"))
              }
              className="min-h-[36px] max-h-[200px] resize-none border-0 bg-transparent focus-visible:ring-0 text-sm px-4 py-2"
              rows={1}
            />
            <div className="flex items-center gap-2 px-3 py-2 border-t border-border/60">
              {/* Offline indicator + reconnect */}
              {!isOnline && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-8 px-2 gap-1 text-xs text-red-500 hover:text-red-600"
                  title={t("input.reconnectTitle")}
                  onClick={() => reconnect()}
                >
                  {connectionState === "reconnecting" ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <WifiOff className="w-3.5 h-3.5" />
                  )}
                  {connectionState === "reconnecting"
                    ? t("input.reconnecting")
                    : t("input.reconnect")}
                </Button>
              )}

              {/* Upload file button */}
              <Button
                size="sm"
                variant="ghost"
                className="h-8 px-2"
                title={t("input.uploadFile")}
                onClick={() => setShowUpload(true)}
              >
                <Paperclip className="w-3.5 h-3.5" />
              </Button>

              {/* @ mention button */}
              <Button
                size="sm"
                variant="ghost"
                className="h-8 px-2 gap-1 text-xs"
                title={t("input.mention")}
                onClick={() => {
                  setInput((v) => (v.endsWith("@") || v.endsWith("@ ") ? v : `${v}@`));
                  setShowMention(true);
                  taRef.current?.focus();
                }}
              >
                <AtSign className="w-3.5 h-3.5" />
              </Button>

              {/* Slash command hint */}
              <Button
                size="sm"
                variant="ghost"
                className="h-8 px-2 gap-1 text-xs"
                title={t("input.command")}
                onClick={() => {
                  setInput("/");
                  setShowSlash(true);
                  taRef.current?.focus();
                }}
              >
                <Slash className="w-3.5 h-3.5" />
              </Button>

              {/* Separator before context dropdowns */}
              <span className="shrink-0 h-4 w-px bg-border/60" />

              {/* Experts dropdown */}
              {onlineExperts.length > 0 && (
                <Popover open={showExpertPopover} onOpenChange={setShowExpertPopover}>
                  <PopoverTrigger asChild>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 px-2 gap-1 text-xs text-muted-foreground hover:text-foreground"
                    >
                      <Users className="w-3.5 h-3.5" />
                      {task.expertId
                        ? (onlineExperts.find((e) => e.id === task.expertId)?.name ??
                          t("input.expert"))
                        : t("input.expert")}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent align="start" className="w-60 p-1.5">
                    <div className="text-[11px] font-medium px-2 py-1 mb-1 flex items-center gap-1.5 text-muted-foreground">
                      <Users className="w-3 h-3" /> {t("input.selectExpert")}
                      {task.expertId && (
                        <span className="ml-auto text-[10px] text-brand">
                          <Check className="w-3 h-3 inline" /> {t("input.selected")}
                        </span>
                      )}
                    </div>
                    <div className="max-h-[240px] overflow-y-auto scrollbar-thin">
                      {onlineExperts.map((e) => (
                        <button
                          key={e.id}
                          className={cn(
                            "w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left transition text-xs",
                            e.id === task.expertId ? "bg-brand/10 text-brand" : "hover:bg-muted/60",
                          )}
                          onClick={() => {
                            setTaskExpert(task.id, e.id);
                            insertExpert(e.name);
                          }}
                        >
                          <ExpertIcon
                            emoji={e.icon}
                            hue={getCategoryHue(e.category)}
                            size="sm"
                            className="!w-4 !h-4 shrink-0"
                          />
                          <span className="truncate">{e.name}</span>
                        </button>
                      ))}
                    </div>
                  </PopoverContent>
                </Popover>
              )}

              {/* Knowledge bases dropdown */}
              {knowledgeBases.length > 0 && (
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      size="sm"
                      variant="ghost"
                      title={t("input.knowledgeBase")}
                      className="h-8 w-8 p-0 justify-center text-muted-foreground hover:text-foreground"
                    >
                      <Database className="w-3.5 h-3.5" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent align="start" className="w-60 p-1.5">
                    <div className="text-[11px] font-medium px-2 py-1 mb-1 flex items-center gap-1.5 text-muted-foreground">
                      <Database className="w-3 h-3" /> {t("input.connectedKb")}
                    </div>
                    <div className="max-h-[240px] overflow-y-auto scrollbar-thin">
                      {knowledgeBases.map((kb) => {
                        const isSelected = lastKbId === kb.id;
                        return (
                          <button
                            key={kb.id}
                            onClick={() => {
                              try {
                                localStorage.setItem("normnomos-last-kb", kb.id);
                              } catch {
                                /* no-op */
                              }
                              setLastKbId(kb.id);
                            }}
                            className={cn(
                              "w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left transition text-xs",
                              isSelected ? "bg-brand/10 text-brand" : "hover:bg-muted/60",
                            )}
                          >
                            <Database className="w-3.5 h-3.5 shrink-0 text-brand/60" />
                            <div className="min-w-0 flex-1">
                              <div className="truncate font-medium">{kb.name}</div>
                              <div className="text-[10px] text-muted-foreground">
                                {t("input.kbStats", {
                                  docs: kb.stats.total_documents,
                                  chunks: kb.stats.total_chunks,
                                })}
                              </div>
                            </div>
                            {kb.is_default && (
                              <span className="text-[9px] px-1 py-0.5 rounded bg-brand/10 text-brand shrink-0">
                                {t("input.defaultKb")}
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </PopoverContent>
                </Popover>
              )}

              {/* LLM models dropdown (replaces the old inline model selector) */}
              {models.length > 0 && (
                <Popover open={showModelPopover} onOpenChange={setShowModelPopover}>
                  <PopoverTrigger asChild>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 px-2 gap-1 text-xs text-muted-foreground hover:text-foreground"
                    >
                      <Cpu className="w-3.5 h-3.5" />
                      {models.find((m) => m.id === task.model)?.name ??
                        task.model ??
                        t("input.selectModel")}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent align="start" className="w-60 p-1.5">
                    <div className="text-[11px] font-medium px-2 py-1 mb-1 flex items-center gap-1.5 text-muted-foreground">
                      <Cpu className="w-3 h-3" /> {t("input.switchModel")}
                    </div>
                    <div className="max-h-[240px] overflow-y-auto scrollbar-thin">
                      {orderedModels.map((m) => (
                        <button
                          key={m.id}
                          className={cn(
                            "w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left transition text-xs",
                            m.id === task.model ? "bg-brand/10 text-brand" : "hover:bg-muted/60",
                          )}
                          onClick={() => setTaskModel(task.id, m.id)}
                        >
                          <Cpu className="w-3.5 h-3.5 shrink-0" />
                          <span className="truncate font-medium">{m.name}</span>
                          {m.source === "official" && (
                            <span className="text-[9px] px-1 py-px rounded bg-brand/15 text-brand shrink-0">
                              {t("input.official")}
                            </span>
                          )}
                          {m.provider && (
                            <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
                              {m.provider}
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                    <div className="border-t mt-1 pt-1">
                      <button
                        className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left transition text-xs hover:bg-muted/60 text-muted-foreground"
                        onClick={() => setActiveDrawer("llm")}
                      >
                        <Settings2 className="w-3.5 h-3.5 shrink-0" />
                        <span>{t("input.llmConfigMenu")}</span>
                      </button>
                    </div>
                  </PopoverContent>
                </Popover>
              )}

              {/* LLM config button (always visible, opens drawer with credits/auto-mode/gateway models) */}
              {!models.length && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-8 px-2 gap-1 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => setActiveDrawer("llm")}
                >
                  <Settings2 className="w-3.5 h-3.5" />
                  {t("input.llmConfig")}
                </Button>
              )}

              {/* Send / Stop */}
              <div className="ml-auto flex items-center gap-2">
                {busy ? (
                  <Button
                    onClick={handleStop}
                    size="sm"
                    className="h-8 w-8 p-0 rounded-full bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    title={t("input.stop")}
                  >
                    <StopCircle className="w-4 h-4" />
                  </Button>
                ) : (
                  <Button
                    onClick={handleSend}
                    disabled={!input.trim() || !task.model}
                    size="sm"
                    className="h-8 w-8 p-0 rounded-full bg-gradient-brand text-brand-foreground hover:opacity-90 shadow-brand disabled:opacity-40"
                  >
                    <ArrowUp className="w-4 h-4" />
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>

        <p className="text-[10px] text-center text-muted-foreground mt-2">
          {t("input.disclaimer.a")} <code className="px-0.5 rounded bg-muted/60">/</code>{" "}
          {t("input.disclaimer.b")} <code className="px-0.5 rounded bg-muted/60">@</code>{" "}
          {t("input.disclaimer.c")}
          <code className="px-0.5 rounded bg-muted/60">Ctrl+Enter</code> {t("input.disclaimer.d")}
        </p>
      </div>

      {/* File upload dialog */}
      <FileUploadDialog
        open={showUpload}
        onOpenChange={setShowUpload}
        workspaceId={workspace?.id}
        workspaceName={workspace?.name}
      />
    </div>
  );
}
