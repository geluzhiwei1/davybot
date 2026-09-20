/** Chinese (zh-CN) — marketAgent module strings(MarketingAgent,PRD §11) */
const zhCN = {
  // 跳转壳(routes/market/agent.tsx)
  "shell.entering": "正在进入 MarketingAgent…",
  "shell.initFailed": "MarketingAgent 工作区初始化失败",

  // Dock(market-agent-dock.tsx)
  "dock.open": "打开 MarketingAgent",
  "dock.title": "MarketingAgent 市场营销编排",
  "dock.contextCurrent": "当前上下文:{{summary}}",
  "dock.defaultDesc": "市场营销编排中枢 · 7 子智能体五段编队",
  "dock.preparing": "正在准备 MarketingAgent 工作区…",
  "dock.loadFailed": "加载失败:{{error}}",

  // Fleet badge(market-agent-fleet-badge.tsx)
  "fleet.ariaLabel": "MarketingAgent 编队状态",
  "fleet.title": "MarketingAgent 编队 · {{count}} 子智能体",
  "fleet.dotTitle": "{{name}} · {{status}}",
  "fleet.lastAction": "最近:{{action}}",
  "fleet.summary.thinking": "{{count}} 推理中",
  "fleet.summary.online": "{{active}}/{{total}} 在线",
  "fleet.summary.ready": "编队就绪",
  "fleet.status.idle": "空闲",
  "fleet.status.online": "在线",
  "fleet.status.thinking": "推理中",
  "fleet.status.tool": "工具调用",
  "fleet.dev.simulateTitle":
    "通过 event-bus 触发 market_agent_status 事件,验证 monitoring-ws → store → UI 全链路",
  "fleet.dev.demo": "演示",
  "fleet.dev.reset": "重置",
  "fleet.agent.mkt-radar-agent.name": "情报雷达",
  "fleet.agent.mkt-radar-agent.role": "信号/事件巡检与早鸟识别",
  "fleet.agent.mkt-visibility-agent.name": "可见度侦察",
  "fleet.agent.mkt-visibility-agent.role": "GEO 引用率与 SERP 排名",
  "fleet.agent.mkt-competitor-agent.name": "竞品分析师",
  "fleet.agent.mkt-competitor-agent.role": "竞品画像与内容策略",
  "fleet.agent.mkt-trend-agent.name": "趋势观察",
  "fleet.agent.mkt-trend-agent.role": "行业趋势三态与预判",
  "fleet.agent.mkt-opportunity-agent.name": "商机顾问",
  "fleet.agent.mkt-opportunity-agent.role": "需求评估与打单跟进",
  "fleet.agent.mkt-action-agent.name": "行动指挥",
  "fleet.agent.mkt-action-agent.role": "渠道行动草稿与外推",
  "fleet.agent.mkt-report-agent.name": "情报书记",
  "fleet.agent.mkt-report-agent.role": "晨报/周报与执行摘要",

  "chips.srLabel": "向 MarketingAgent 发起提问",

  // ChatView(market-agent-chat-view.tsx)
  "chat.orchLabel": "编排",
  "chat.inputPlaceholder": "向 MarketingAgent 下达指令…",

  // E2 编排面板(market-agent-orchestration-panel.tsx)
  "panel.nodes.title": "任务节点",
  "panel.nodes.empty": "暂无运行中任务",
  "panel.nodes.running": "运行中",
  "panel.context.title": "市场上下文",
  "panel.context.range": "时间范围:近 {{count}} 天",
  "panel.context.allProducts": "产品:全部",
  "panel.context.product": "产品:{{id}}…",
  "panel.llm.title": "模型",
  "panel.llm.gatewayNote":
    "对话模型经平台网关(llm-pricing 目录)按用户积分计费,零本地 LLM 配置;流水线(简报/画像/GEO)由市场模块自有引擎服务。",

  // 工件卡(market-agent-message-renderer.tsx)
  "artifact.kind.signal": "信号",
  "artifact.kind.event": "事件",
  "artifact.kind.brief": "简报",
  "artifact.kind.insight": "建议",
  "artifact.kind.action": "行动",
  "artifact.kind.report": "报告",
  "artifact.kind.profile": "画像",
  "artifact.kind.opportunity": "商机",
  "artifact.kind.product": "产品",
  "artifact.kind.other": "工件",
  "artifact.producedBy": "产出:{{name}}",
  "artifact.needsReview": "需人工确认",

  // 空态(market-agent-empty-state.tsx)
  "empty.subtitle": "你的 AI 市场合伙人——说目标,它拆解任务、调度编队、调用模块工具、产出交付物",
  "empty.briefing.title": "市场晨报 · {{date}}",
  "empty.briefing.modelTag": "生成模型",
  "empty.briefing.generate": "生成今日晨报",
  "empty.briefing.generating": "生成中…",
  "empty.snapshot.loading": "正在拉取市场快照…",
  "empty.snapshot.title": "市场快照(近 7 天)",
  "empty.snapshot.pending": "待处理信号",
  "empty.snapshot.events": "新事件",
  "empty.snapshot.briefs": "简报",
  "empty.snapshot.highConf": "高置信事件",
  "empty.snapshot.sources": "数据源 {{total}} 个 · 异常 {{errored}}",
  "empty.snapshot.unavailable": "市场快照暂不可用{{error}}——可直接提问,Agent 会用工具实时拉取",
  "empty.quick.geo.label": "引用率体检",
  "empty.quick.geo.hint": "GEO 引用与缺口分析",
  "empty.quick.geo.prompt": "萤火在 AI 回答里的引用率怎么样?哪些关键词没被引用,差距在哪?",
  "empty.quick.signals.label": "竞品动态",
  "empty.quick.signals.prompt": "最近 7 天竞品有什么高置信动作?给我事件列表和要点。",
  "empty.quick.signals.hint": "信号/事件巡检",
  "empty.quick.competitor.label": "竞品拆解",
  "empty.quick.competitor.prompt": "分析 Label Studio 最近的内容策略,它在我们目标品类里的声量怎样?",
  "empty.quick.competitor.hint": "画像与内容库",
  "empty.quick.opportunities.label": "商机盘点",
  "empty.quick.opportunities.prompt": "现在有哪些待跟进商机?按意向和阶段给我跟进建议。",
  "empty.quick.opportunities.hint": "漏斗与下一步",
  "empty.quick.actions.label": "行动漏斗",
  "empty.quick.actions.prompt": "渠道行动漏斗现在什么状态?哪些 idea 停滞了,给我下一步建议。",
  "empty.quick.actions.hint": "外推与推进",
  "empty.quick.briefing.label": "今日晨报",
  "empty.quick.briefing.prompt":
    "给我一份市场晨报:新信号、高置信事件、引用率变化、待办行动和 next-best-action。",
  "empty.quick.briefing.hint": "对齐与汇报",
};

export default zhCN;
