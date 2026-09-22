/** Chinese (zh-CN) — sandbox module strings */
const zhCN = {
  // Provider selector
  "provider.auto.label": "自动检测",
  "provider.auto.description": "根据环境自动选择最佳 Provider",
  "provider.auto.current": "当前生效: {{name}}",
  "provider.subprocess.label": "进程隔离 (subprocess)",
  "provider.subprocess.description": "子进程执行, 性能最优但无隔离",
  "provider.docker.label": "容器隔离 (Docker/Podman)",
  "provider.docker.description": "Docker/Podman 容器隔离, 适合本地多用户",
  "provider.e2b.label": "硬件隔离 (CubeSandbox KVM)",
  "provider.e2b.description": "CubeSandbox MicroVM 硬件级隔离, 支持自托管和云端",

  // Capabilities badge
  "capabilities.isolation.none": "无隔离",
  "capabilities.isolation.process": "进程级",
  "capabilities.isolation.container": "容器级",
  "capabilities.isolation.hardware": "硬件级 (KVM)",
  "capabilities.coldStart": "冷启动 {{ms}}ms",
  "capabilities.timeout": "超时 {{seconds}}s",

  // Sandbox section
  "section.title": "沙箱执行环境",
  "section.description": "配置命令沙箱的隔离级别和挂载策略",
  "section.currentStatus": "当前状态",
  "section.networkPolicy": "网络策略 (只读)",
  "section.advanced": "高级配置",
  "section.connectionTest": "连接测试",
  "section.mountMode": "工作区挂载模式",
  "section.detailedSettings": "沙箱详细配置 →",

  // VirtioFS toggle
  "virtiofs.label": "VirtioFS 挂载",
  "virtiofs.unavailable": "VirtioFS 需要 E2B Provider 支持, 当前 Provider 不兼容.",
  "virtiofs.localNote": "本地部署模式下, VirtioFS 通常不可用 (需要 KVM). 已自动禁用.",
  "virtiofs.cloudNote": "VirtioFS 提供高性能文件系统挂载, 在 E2B (KVM) 环境下推荐启用.",

  // Provider health indicator
  "health.available": "正常",
  "health.unavailable": "异常",

  // Test button
  "test.button": "测试连接",
  "test.failed": "测试失败",
  "test.success": "连接成功",
  "test.error": "连接失败",

  // Status panel
  "status.uninitialized": "未初始化",
  "status.idle": "空闲 (按需创建)",
  "status.initializing": "初始化中",
  "status.active": "运行中",
  "status.paused": "已暂停",
  "status.queued": "排队中",
  "status.reconnecting": "重连中",
  "status.destroyed": "已销毁",
  "status.error": "错误",

  // Mount mode selector
  "mountMode.ro": "只读 (ro)",
  "mountMode.rw": "读写 (rw)",
  "mountMode.rwWarning": "读写模式允许 Agent 修改工作区文件, 存在安全风险. 请确保信任当前 Agent.",
  "mountMode.roNote": "只读模式: Agent 可读取工作区文件但无法修改, 更安全.",

  // Command error modal
  "error.RO_MODE_WRITE_DENIED.title": "当前工作区以只读挂载",
  "error.QUOTA_EXCEEDED.title": "配额已超限",
  "error.PATH_OUT_OF_ALLOWLIST.title": "路径越界",
  "error.TMPFS_MASK_FAILED.title": "沙箱启动失败 — 安全检查未通过",
  "error.TRUSTED_CONTEXT_EXPIRED.title": "会话已过期, 请重新登录",
  "error.NETWORK_DENIED.title": "网络请求被策略拒绝",
  "error.SANDBOX_TIMEOUT.title": "命令执行超时",
  "error.UNKNOWN.title": "未知错误",
  "error.defaultTitle": "错误",
  "error.exitCode": "退出码: {{code}}",
  "error.action.close": "关闭",
  "error.action.open_settings": "去设置",
  "error.action.contact_admin": "联系管理员",
  "error.action.retry": "重试",

  // Quota indicator
  "quota.loading": "配额信息加载中...",
  "quota.region": "沙箱配额",
  "quota.sessions": "沙箱数",
  "quota.memory": "内存",
  "quota.rate": "速率 (/min)",

  // Network policy viewer
  "policy.loading": "网络策略加载中...",
  "policy.defaultDeny": "默认拒绝",
  "policy.defaultAllow": "默认允许",
  "policy.allowedDomains": "允许的域名",
  "policy.deniedDomains": "拒绝的域名",

  // Reconnect banner
  "reconnect.expired": "沙箱已因超时被销毁, 请重新执行命令",
  "reconnect.countdown": "连接中断, <strong>{{seconds}}s</strong> 内重连可恢复沙箱状态",
};

export default zhCN;
