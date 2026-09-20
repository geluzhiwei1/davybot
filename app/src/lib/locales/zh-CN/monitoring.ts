/** Chinese (zh-CN) — monitoring module strings */
const zhCN = {
  // System health
  "systemHealth.title": "系统健康",
  "systemHealth.waiting": "等待连接...",
  "systemHealth.memory": "内存",
  "systemHealth.disk": "磁盘",
  "systemHealth.networkLatency": "网络延迟",

  // Cost tracker
  "cost.title": "Token & 费用追踪",
  "cost.waiting": "等待数据...",
  "cost.totalTokens": "总 Token",
  "cost.totalCost": "总费用",
  "cost.inputTokens": "输入 Token",
  "cost.outputTokens": "输出 Token",
  "cost.modelBreakdown": "模型明细",

  // Subtask tree
  "subtask.title": "子任务委派",
  "subtask.completedOf": "{{completed}}/{{total}} 完成",
  "subtask.empty": "暂无子任务（等待 new_task 委派…）",
  "subtask.status.pending": "待启动",
  "subtask.status.running": "运行中",
  "subtask.status.completed": "已完成",
  "subtask.status.failed": "失败",
  "subtask.status.aborted": "已中止",
  "subtask.standaloneThread": "独立会话",
  "subtask.viewThread": "查看子代理线程",
  "subtask.sendSteer": "发送 steer 指令",
  "subtask.confirmAbortTitle": "再次点击确认中止（级联整棵子树）",
  "subtask.confirmAbortShort": "确认中止?",
  "subtask.abortTitle": "中止子任务（级联整棵子树）",
  "subtask.abortFailed": "中止失败",
  "subtask.rerunTitle": "原位重跑（重置为待启动，旧结果归档）",
  "subtask.rerunFailed": "重跑失败",

  // Trace waterfall
  "trace.empty": "暂无追踪数据",
  "trace.emptyHint": "Agent 执行后将在此显示全链路追踪",
  "trace.start": "开始:",
  "trace.end": "结束:",
  "trace.input": "输入:",
  "trace.output": "输出:",
  "trace.legend": "图例:",

  // Todos panel
  "todos.title": "任务清单",
  "todos.stats": "{{completed}}/{{total}} 完成 ({{rate}}%)",
  "todos.filter.all": "全部",
  "todos.filter.PENDING": "待处理",
  "todos.filter.IN_PROGRESS": "进行中",
  "todos.filter.COMPLETED": "已完成",
  "todos.empty": "暂无任务",

  // Task graph
  "taskGraph.empty": "选择执行查看任务图",
  "taskGraph.completedOf": "{{completed}}/{{total}} 完成",
  "taskGraph.done": "完成",
  "taskGraph.failed": "失败",

  // Alert system
  "alert.title": "告警",
  "alert.unacknowledged": "({{count}} 未确认)",
  "alert.empty": "暂无告警",

  // Agent profiles
  "profile.title": "Agent Profile 注册表",
  "profile.counts": "内置 {{builtin}} · 自定义 {{custom}}",
  "profile.refresh": "刷新",
  "profile.refreshTitle": "刷新 Profile 注册表",
  "profile.noWorkspace": "未连接工作区",
  "profile.loading": "加载 Profile…",
  "profile.empty": "当前工作区无 Agent Profile（内置 default/worker/explorer 应可见）",
  "profile.loadFailed": "Profile 注册表加载失败",
  "profile.builtin": "内置",
  "profile.custom": "自定义",
  "profile.subtasks": "子任务 ×{{count}}",

  // Log viewer
  "log.title": "日志",
  "log.autoScroll": "自动滚动",
  "log.manual": "手动",
  "log.all": "全部",
  "log.empty": "暂无日志",

  // Agents overview
  "agents.title": "并行任务",
  "agents.active": "活跃: {{count}}",
  "agents.completed": "完成: {{count}}",
  "agents.failed": "失败: {{count}}",
  "agents.empty": "暂无活跃任务",
};

export default zhCN;
