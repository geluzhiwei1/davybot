/** Chinese (zh-CN) — chat UI strings */
const zhCN = {
  // Follow-up dialog
  "followup.title": "智能体需要确认",
  "followup.suggested": "推荐回复",
  "followup.custom": "自定义回复",
  "followup.placeholder": "输入你的回复…",
  "followup.cancel": "取消",

  // Message actions
  "messageActions.copied": "已复制",
  "messageActions.copyFailed": "复制失败",
  "messageActions.mdExported": "已导出 Markdown",
  "messageActions.exportFailed": "导出失败",
  "messageActions.pdfFailed": "PDF 准备失败",
  "messageActions.copyTitle": "复制",
  "messageActions.exportMd": "导出 Markdown",
  "messageActions.exportPdf": "导出 PDF",

  // Resource mention picker
  "mention.tab.files": "文件",
  "mention.tab.experts": "专家",
  "mention.tab.recent": "最近",
  "mention.search.files": "搜索文件…",
  "mention.search.experts": "搜索专家…",
  "mention.search.recent": "搜索最近…",
  "mention.empty.files": "无匹配文件",
  "mention.empty.experts": "无匹配专家",
  "mention.empty.recent": "无最近使用",
  "mention.footer.navigate": "↑↓ 导航",
  "mention.footer.switchTab": "Tab 切换分类",
  "mention.footer.select": "↵ 选择",
  "mention.footer.close": "Esc 关闭",
  "mention.file.aiGenerated": "AI 生成",
  "mention.file.userUploaded": "用户上传",
  "mention.time.justNow": "刚刚",
  "mention.time.minutesAgo": "{{count}} 分钟前",
  "mention.time.hoursAgo": "{{count}} 小时前",
  "mention.time.daysAgo": "{{count}} 天前",

  // Slash commands
  "slash.searchPlaceholder": "搜索命令…",
  "slash.count": "{{count}} 条",
  "slash.noMatch": "无匹配命令",
  "slash.footer.navigate": "↑↓ 导航",
  "slash.footer.select": "↵ 选择",
  "slash.footer.close": "Esc 关闭",
  "slash.cmd.clear": "清空当前对话",
  "slash.cmd.reset": "重置对话，从头开始",
  "slash.cmd.help": "查看帮助和快捷键",
  "slash.cmd.expert": "选择法律专家",
  "slash.cmd.model": "切换 AI 模型",
  "slash.cmd.summarize": "总结当前对话",
  "slash.cmd.analyze": "深度分析文件或合同",
  "slash.cmd.task": "创建复杂任务流程",
  "slash.cmd.chat": "切换到聊天模式",
  "slash.cmd.review.run": "启动综述流水线（7 阶段 / 2 Gate）",
  "slash.cmd.paper.status": "查看论文流水线追踪表",
  "slash.cmd.paper.switch": "切换论文流水线 Stage",
  "slash.cmd.lens.run": "解读论文 PDF（解析→理解→展示）",
  "slash.cmd.lens.critique": "批判性分析论文 PDF（S08）",
  "slash.tag.system": "系统",
  "slash.tag.chat": "对话",
  "slash.tag.settings": "设置",
  "slash.tag.analysis": "分析",
  "slash.tag.advanced": "高级",
  "slash.tag.research": "科研",

  // Message component
  "message.exec.status.started": "启动中",
  "message.exec.status.validating": "验证中",
  "message.exec.status.executing": "执行中",
  "message.exec.status.completed": "已完成",
  "message.exec.status.failed": "失败",
  "message.exec.status.timeout": "超时",
  "message.subtask.title": "子任务",
  "message.subtask.delegate.blocking": "阻塞执行",
  "message.subtask.delegate.async": "异步委派",
  "message.subtask.status.pending": "待启动",
  "message.subtask.status.running": "运行中",
  "message.subtask.status.completed": "已完成",
  "message.subtask.status.failed": "失败",
  "message.subtask.status.aborted": "已中止",
  "message.subtask.viewThread": "查看子代理线程",
  "message.subtask.standaloneSession": "独立会话",
  "message.subtaskBatch.title": "批量子任务",
  "message.subtaskBatch.count": "{{count}} 项",
  "message.subtaskBatch.failed": "{{count}} 失败",
  "message.subtaskBatch.allDone": "全部完成",
  "message.subtaskBatch.partial": "部分创建 {{created}}/{{total}}（重复/失败项见工具结果）",
  "message.subtaskReport.title": "子任务执行报告",
  "message.subtaskReport.count": "{{count}} 个子任务",
  "message.subtaskReport.acceptance": "验收",
  "message.subtaskReport.result": "结果",
  "message.subtaskReport.verdictHint": "判定提示",
  "message.agent.default": "智能体",
  "message.thinking": "正在思考...",

  // File upload dialog
  "upload.title": "上传文件",
  "upload.dropzone": "拖拽文件到此处上传",
  "upload.dropzoneHint": "或点击选择文件 · 支持 PDF, DOCX, TXT, 图片等",
  "upload.selectFolder": "选择文件夹",
  "upload.done": "完成",
  "upload.cancel": "取消",
  "upload.uploading": "上传中…",
  "upload.uploadCount": "上传 {{count}} 个文件",
  "upload.uploaded": "已上传 {{n}} 个文件",
  "upload.retry": "重试",
  "upload.refreshFailed": "刷新文件列表失败",

  // Mention text
  "mentionText.fileChip": "文件: {{name}}",

  // List page renderer
  "listPage.showing": "显示 {{shown}} / {{total}} 条",
  "listPage.nextPage": "offset={{offset}} 看下一页",
  "listPage.more": "有更多结果",

  // Blob window renderer
  "blobWindow.omitted": "⸻ 省略 {{count}} 行 ⸻",
  "blobWindow.showing": "显示 {{shown}} / {{total}} 行",

  // Reasoning content
  "reasoning.title": "推理过程",
  "reasoning.raw": "原文",

  // Thinking content
  "thinking.title": "思考过程 ({{completed}}/{{total}})",
  "thinking.status.inProgress": "进行中",
  "thinking.status.completed": "已完成",
  "thinking.status.failed": "失败",

  // Tool call content
  "toolCall.status.started": "启动中",
  "toolCall.status.inProgress": "执行中",
  "toolCall.status.completed": "已完成",
  "toolCall.status.failed": "失败",
  "toolCall.input": "输入参数",
  "toolCall.output": "输出",
  "toolCall.error": "错误",
  "toolCall.duration": "耗时 {{seconds}}s",

  // Tool result content
  "toolResult.failed": "执行失败",
  "toolResult.success": "执行成功",
  "toolResult.expandFull": "展开完整结果",
  "toolResult.fullResult": "完整结果",
  "toolResult.collapse": "收起",
};

export default zhCN;
