/** Chinese (zh-CN) — firmAgent module strings */
const zhCN = {
  // Dock (firm-agent-dock.tsx)
  "dock.open": "打开 FirmAgent",
  "dock.title": "FirmAgent 智能律所编排",
  "dock.contextCurrent": "当前上下文：{{summary}}",
  "dock.defaultDesc": "智能律所编排中枢 · 7 子 Agent 协同",
  "dock.preparing": "正在准备 FirmAgent 工作区…",
  "dock.loadFailed": "加载失败：{{error}}",

  // Fleet badge (firm-agent-fleet-badge.tsx)
  "fleet.ariaLabel": "FirmAgent 编队状态",
  "fleet.title": "FirmAgent 编队 · {{count}} 子 Agent",
  "fleet.dotTitle": "{{name}} · {{status}}",
  "fleet.lastAction": "最近：{{action}}",
  "fleet.summary.thinking": "{{count}} 推理中",
  "fleet.summary.online": "{{active}}/{{total}} 在线",
  "fleet.summary.ready": "编队就绪",
  "fleet.status.idle": "空闲",
  "fleet.status.online": "在线",
  "fleet.status.thinking": "推理中",
  "fleet.status.tool": "工具调用",
  "fleet.dev.simulateTitle":
    "通过 event-bus 触发 firm_agent_status 事件，验证 monitoring-ws.ts → store → UI 全链路",
  "fleet.dev.demo": "演示",
  "fleet.dev.reset": "重置",
  "fleet.agent.case-agent.name": "案件",
  "fleet.agent.case-agent.role": "案件事实梳理与策略",
  "fleet.agent.contract-agent.name": "合同",
  "fleet.agent.contract-agent.role": "合同审查与起草",
  "fleet.agent.compliance-agent.name": "合规",
  "fleet.agent.compliance-agent.role": "合规风险识别",
  "fleet.agent.finance-agent.name": "财务",
  "fleet.agent.finance-agent.role": "账务与税务测算",
  "fleet.agent.research-agent.name": "检索",
  "fleet.agent.research-agent.role": "类案与法规检索",
  "fleet.agent.sign-agent.name": "签章",
  "fleet.agent.sign-agent.role": "签署流程与归档",
  "fleet.agent.lead-agent.name": "案源",
  "fleet.agent.lead-agent.role": "线索评估与营销",

  // Chat view (firm-agent-chat-view.tsx)
  "chat.orchLabel": "编排",
  "chat.inputPlaceholder": "向 FirmAgent 下达指令…（例：为环球科技案准备答辩状，附 3 个类案）",

  // Empty state (firm-agent-empty-state.tsx)
  "empty.title": "FirmAgent 编队已就绪",
  "empty.subtitle":
    "指令 FirmAgent 编排 7 子 Agent（案件 / 合同 / 合规 / 财务 / 检索 / 签章 / 案源）。",
  "empty.quick": "快捷指令",
  "empty.quick.contract.label": "起草合同",
  "empty.quick.contract.prompt": "请起草一份技术服务合同，包含验收标准、违约责任与知识产权条款。",
  "empty.quick.conflict.label": "冲突检索",
  "empty.quick.conflict.prompt": "对当前案卷做利益冲突检索，输出潜在冲突方与建议措施。",
  "empty.quick.health.label": "案件健康度",
  "empty.quick.health.prompt": "评估当前案件的时效、证据完备度、风险点，输出案件健康度报告。",
  "empty.quick.defense.label": "答辩状草稿",
  "empty.quick.defense.prompt": "基于现有材料，为环球科技案起草一份答辩状草稿，附 3 个类案。",
  "empty.quick.pipeline.label": "案源分析",
  "empty.quick.pipeline.prompt": "本月案源漏斗分析：从线索到签约的转化率与流失原因。",
  "empty.quick.precedent.label": "类案速查",
  "empty.quick.precedent.prompt": "检索「商业秘密侵权」近 3 年典型案例 5 则，附裁判要旨。",
  "empty.hint.input": "输入",
  "empty.hint.ref": "引用文件，",
  "empty.hint.skill": "触发技能",

  // Morning briefing (firm-agent-empty-state.tsx)
  "brief.loading": "正在拉取今日晨报…",
  "brief.unavailable": "今日晨报暂不可用，可直接下达指令。",
  "brief.title": "今日晨报 · {{date}}",
  "brief.deadlineCount": "{{count}} 期限",
  "brief.deadlineFallback": "期限 {{index}}",
  "brief.alertCount": "{{count}} 条预警需关注（{{first}}）",
  "brief.recommendation": "💡 建议：{{text}}",

  // Orchestration panel (firm-agent-orchestration-panel.tsx)
  "orch.tab.jobs": "任务队列",
  "orch.tab.memory": "律所记忆",
  "orch.jobs.empty": "暂无活动任务",
  "orch.jobs.emptyHint1": "向 FirmAgent 下达指令后，",
  "orch.jobs.emptyHint2": "编排任务将在此实时显示。",
  "orch.jobs.totalProgress": "总进度",
  "orch.jobs.activeCount": "{{count}} 进行中",
  "orch.jobs.completedCount": "{{count}} 已完成",
  "orch.jobs.totalCount": "{{count}} 总计",
  "orch.jobs.status.done": "完成",
  "orch.jobs.status.running": "进行中",
  "orch.jobs.status.pending": "待开始",
  "orch.memory.refresh": "刷新",
  "orch.memory.effective": "生效（effective）",
  "orch.memory.override": "覆盖（override）",
  "orch.memory.default": "默认（default）",
  "orch.memory.empty": "暂无记忆",

  // Artifact card (firm-agent-message-renderer.tsx)
  "artifact.producedBy": "由 {{name}} 产出",
  "artifact.status.draft": "草稿",
  "artifact.status.final": "定稿",
  "artifact.status.pending_review": "待审",
  "artifact.kind.contract": "合同",
  "artifact.kind.brief": "答辩状",
  "artifact.kind.analysis": "分析",
  "artifact.kind.memo": "备忘录",
  "artifact.kind.research": "检索报告",
  "artifact.kind.letter": "函件",
  "artifact.kind.report": "报告",
  "artifact.kind.other": "工件",

  // Workspace (use-firm-agent-workspace.ts)
  "workspace.description": "FirmAgent 主线工作区（智能律所编排中枢）",
};

export default zhCN;
