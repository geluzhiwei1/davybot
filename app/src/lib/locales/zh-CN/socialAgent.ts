/** Chinese (zh-CN) — socialAgent module strings(SocialAgent,镜像 marketAgent) */
const zhCN = {
  // 跳转壳(routes/social/agent.tsx)
  "shell.entering": "正在进入 SocialAgent…",
  "shell.initFailed": "SocialAgent 工作区初始化失败",

  // Dock(social-agent-dock.tsx)
  "dock.open": "打开 SocialAgent",
  "dock.title": "SocialAgent 社媒编排",
  "dock.contextCurrent": "当前上下文:{{summary}}",
  "dock.defaultDesc": "社媒编排中枢 · 6 子智能体五段编队",
  "dock.preparing": "正在准备 SocialAgent 工作区…",
  "dock.loadFailed": "加载失败:{{error}}",

  // Fleet badge(social-agent-fleet-badge.tsx)
  "fleet.ariaLabel": "SocialAgent 编队状态",
  "fleet.title": "SocialAgent 编队 · {{count}} 子智能体",
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
    "通过 event-bus 触发 social_agent_status 事件,验证 monitoring-ws → store → UI 全链路",
  "fleet.dev.demo": "演示",
  "fleet.dev.reset": "重置",
  "fleet.agent.soc-trending-agent.name": "热点雷达",
  "fleet.agent.soc-trending-agent.role": "今日热点检索与选题判断",
  "fleet.agent.soc-geo-agent.name": "GEO 侦察",
  "fleet.agent.soc-geo-agent.role": "社媒内容 GEO 可见度分析",
  "fleet.agent.soc-analytics-agent.name": "数据洞察",
  "fleet.agent.soc-analytics-agent.role": "内容表现与账号数据分析",
  "fleet.agent.soc-drafter-agent.name": "内容主创",
  "fleet.agent.soc-drafter-agent.role": "一源多稿与多平台适配",
  "fleet.agent.soc-schedule-agent.name": "发布管家",
  "fleet.agent.soc-schedule-agent.role": "发布日历与排期节奏",
  "fleet.agent.soc-approvals-agent.name": "审批 steward",
  "fleet.agent.soc-approvals-agent.role": "审批队列与合规对齐",

  "chips.srLabel": "向 SocialAgent 发起提问",

  // ChatView(social-agent-chat-view.tsx)
  "chat.orchLabel": "编排",
  "chat.inputPlaceholder": "向 SocialAgent 下达指令…",

  // E2 编排面板(social-agent-orchestration-panel.tsx)
  "panel.nodes.title": "任务节点",
  "panel.nodes.empty": "暂无运行中任务",
  "panel.nodes.running": "运行中",
  "panel.context.title": "社媒上下文",
  "panel.context.brand": "当前品牌:{{name}}",
  "panel.context.allBrands": "全部品牌",
  "panel.context.brandHint": "创作与查询会按当前品牌过滤;切换品牌在侧边栏「品牌」行。",
  "panel.llm.title": "模型",
  "panel.llm.gatewayNote":
    "对话模型经平台网关(llm-pricing 目录)按用户积分计费,零本地 LLM 配置;发布/审批等终态操作走社媒控制面页面通道,人是合并者。",

  // 工件卡(social-agent-message-renderer.tsx)
  "artifact.kind.trending": "热点",
  "artifact.kind.geo": "GEO",
  "artifact.kind.insight": "洞察",
  "artifact.kind.draft": "草稿",
  "artifact.kind.content": "内容",
  "artifact.kind.schedule": "排期",
  "artifact.kind.approval": "审批",
  "artifact.kind.account": "账号",
  "artifact.kind.other": "工件",
  "artifact.producedBy": "产出:{{name}}",
  "artifact.needsReview": "需人工确认",

  // 空态(social-agent-empty-state.tsx)
  "empty.subtitle": "你的 AI 社媒运营合伙人——说目标,它拆解任务、调度编队、调用模块工具、产出交付物",
  "empty.quick.trending.label": "今日热点",
  "empty.quick.trending.hint": "选题角度与跟不跟",
  "empty.quick.trending.prompt": "今日各平台有什么和品牌相关的热点?哪些值得跟,从什么角度切入?",
  "empty.quick.geo.label": "GEO 体检",
  "empty.quick.geo.hint": "内容可见度分析",
  "empty.quick.geo.prompt": "我们社媒内容的 GEO 可见度怎么样?哪些话题被 AI 回答引用,哪些没有?",
  "empty.quick.analytics.label": "表现复盘",
  "empty.quick.analytics.hint": "数据洞察",
  "empty.quick.analytics.prompt":
    "最近发布内容的表现怎么样?按平台和内容类型给我数据洞察和改进建议。",
  "empty.quick.draft.label": "一源多稿",
  "empty.quick.draft.hint": "多平台适配",
  "empty.quick.draft.prompt": "帮我围绕品牌最近的一个话题,起草小红书、公众号、微博三个平台的稿件。",
  "empty.quick.calendar.label": "排期盘点",
  "empty.quick.calendar.hint": "发布日历",
  "empty.quick.calendar.prompt": "发布日历上最近的安排怎么样?有没有空窗或冲突,给我节奏建议。",
  "empty.quick.approvals.label": "审批队列",
  "empty.quick.approvals.hint": "对齐与风险",
  "empty.quick.approvals.prompt": "审批中心现在有哪些待办?哪些内容有合规风险,给我处理建议。",
};

export default zhCN;
