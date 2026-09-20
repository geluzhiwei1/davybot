/**
 * 科研助手 9 个工具的向导配置（供 ToolPage wizard prop 消费）。
 *
 * key 与路由 bizModule 一一对应（research-review / research-original / …）。
 * 每个配置 3 步：定位/范围 → 方法或要求 → 产出约定；ToolWizard 末尾自动追加
 * 「需求单预览」步，提交后需求单作为开场消息发给对应 expert。
 *
 * 文案沿用 ProductSurveyWizard 先例：硬编码中文，不走 i18n。
 */
import type { ToolWizardConfig } from "@/components/tool-wizard";

export const RESEARCH_WIZARDS: Record<string, ToolWizardConfig> = {
  /** 综述写作 · review-orchestrator */
  "research-review": {
    topicKey: "topic",
    // 需求单收尾指令：驱动 review-orchestrator 按 auto-academic-review
    // （7 Phase / 17 Stage / 2 Gate，见 input/dao.md 约定）启动，而不是泛泛开工。
    briefFooter:
      "请作为综述流水线编排者（review-orchestrator）处理本需求单：" +
      "1) 先向用户简要确认需求要点；" +
      "2) 将需求单整理为综述意图声明并写入 `input/dao.md`（综述意图 / 文献范围 / 约束）；" +
      "3) 初始化「流水线追踪表」（7 Phase / 17 Stage / 2 Gate），从 Stage 0（prepare）开始执行，" +
      "每完成一个 Stage 在对应 `output/phase-XX/stage-XX/` 路径落盘产物后再派发下一棒。",
    steps: [
      {
        title: "主题与目标",
        fields: [
          {
            key: "topic",
            label: "综述主题",
            required: true,
            placeholder: "例：大语言模型在药物发现中的应用",
          },
          {
            key: "questions",
            label: "核心研究问题",
            type: "textarea",
            placeholder: "这篇综述要回答哪些问题？",
          },
          {
            key: "seeds",
            label: "种子论文（可选）",
            type: "textarea",
            placeholder:
              "3-5 篇代表性论文，每行一篇（DOI 或 arXiv ID，如 10.1038/s41592-021-01195-4）；留空则由 agent 按主题检索",
          },
          { key: "audience", label: "目标读者", defaultValue: "同行研究者" },
        ],
      },
      {
        title: "文献范围",
        fields: [
          {
            key: "timeWindow",
            label: "检索年限",
            type: "radio",
            options: ["近 3 年", "近 5 年", "近 10 年", "不限"],
            defaultValue: "近 5 年",
          },
          { key: "targetCount", label: "目标文献量（篇）", defaultValue: "50" },
          {
            key: "databases",
            label: "数据库偏好",
            type: "radio",
            options: ["不限", "PubMed + Web of Science", "arXiv", "知网"],
            defaultValue: "不限",
          },
          {
            key: "criteria",
            label: "纳入/排除标准",
            type: "textarea",
            placeholder: "如：仅纳入同行评审期刊、排除会议摘要…",
          },
        ],
      },
      {
        title: "产出要求",
        fields: [
          {
            key: "structure",
            label: "综述类型",
            type: "radio",
            options: ["系统综述（PRISMA）", "叙述性综述", "范围综述（Scoping Review）"],
            defaultValue: "叙述性综述",
          },
          {
            key: "journal",
            label: "目标期刊（可选）",
            placeholder:
              "如：Nature Reviews Methods；质量门将按该刊物 rubric 评分，留空默认 7.5/10",
          },
          {
            key: "language",
            label: "写作语言",
            type: "radio",
            options: ["中文", "英文"],
            defaultValue: "中文",
          },
          { key: "length", label: "篇幅", defaultValue: "8000 字左右" },
          { key: "refStyle", label: "参考文献格式", defaultValue: "GB/T 7714" },
        ],
      },
    ],
  },

  /** 原创论文 · paper-orchestrator */
  "research-original": {
    topicKey: "topic",
    // 需求单收尾指令：驱动 paper-orchestrator 按 academic-paper-pipeline
    // （10 Phase / 28 Stage / 4 Gate，见 input/dao.md 约定）启动，而不是泛泛开工。
    briefFooter:
      "请作为原创论文流水线编排者（paper-orchestrator）处理本需求单：" +
      "1) 先向用户简要确认需求要点；" +
      "2) 将需求单整理为研究意图声明并写入 `input/dao.md`（研究意图 / 数据声明 / 约束）；" +
      "3) 初始化「流水线追踪表」（10 Phase / 28 Stage / 4 Gate），从 Stage 00（start-point）开始执行，" +
      "每完成一个 Stage 在对应 `output/phase-XX/stage-XX/` 路径落盘产物后再派发下一棒。",
    steps: [
      {
        title: "选题与问题",
        fields: [
          {
            key: "topic",
            label: "论文选题",
            required: true,
            placeholder: "例：基于多模态影像的阿尔茨海默病早期预测",
          },
          {
            key: "hypothesis",
            label: "研究问题/假设",
            type: "textarea",
            placeholder: "要验证或回答的核心科学问题",
          },
          {
            key: "studyType",
            label: "研究类型",
            type: "radio",
            options: ["观察性研究", "实验研究", "横断面研究", "质性研究", "方法学研究"],
          },
        ],
      },
      {
        title: "方法与数据",
        fields: [
          {
            key: "dataSource",
            label: "数据来源",
            type: "textarea",
            placeholder: "公开数据集/自有队列/实验采集…（可后续在会话中上传）",
          },
          { key: "sampleSize", label: "样本量/数据规模", placeholder: "如：约 1200 例" },
          {
            key: "methods",
            label: "计划分析方法",
            type: "textarea",
            placeholder: "如：Cox 回归、消融实验、消融分析…",
          },
        ],
      },
      {
        title: "目标与篇幅",
        fields: [
          { key: "journal", label: "目标期刊", placeholder: "如未定可留空，由助手推荐" },
          {
            key: "length",
            label: "篇幅",
            type: "radio",
            options: ["短篇（≤3000 字）", "中篇（3000–6000 字）", "长篇（≥6000 字）"],
            defaultValue: "中篇（3000–6000 字）",
          },
          {
            key: "language",
            label: "写作语言",
            type: "radio",
            options: ["中文", "英文"],
            defaultValue: "中文",
          },
          {
            key: "ethics",
            label: "伦理声明",
            type: "radio",
            options: ["需要", "不需要", "待定"],
            defaultValue: "待定",
          },
        ],
      },
    ],
  },

  /** 论文解读 · lens-orchestrator */
  "research-lens": {
    topicKey: "paper",
    steps: [
      {
        title: "论文信息",
        fields: [
          {
            key: "paper",
            label: "论文标题 / DOI / 链接",
            required: true,
            placeholder: "粘贴论文标题、DOI 或全文链接",
          },
          {
            key: "motive",
            label: "阅读动机",
            type: "textarea",
            placeholder: "为什么读这篇？想解决自己的什么问题？",
          },
        ],
      },
      {
        title: "解读视角",
        fields: [
          {
            key: "mode",
            label: "解读类型",
            type: "radio",
            options: ["深度精读", "快速概览", "批判性评估", "方法复现向"],
            defaultValue: "深度精读",
          },
          {
            key: "focus",
            label: "重点关注",
            type: "textarea",
            placeholder: "如：统计方法、实验设计、结论可靠性、与本人研究的对照…",
          },
        ],
      },
      {
        title: "产出要求",
        fields: [
          {
            key: "depth",
            label: "解读深度",
            type: "radio",
            options: ["逐节精读", "摘要式", "两页笔记"],
            defaultValue: "逐节精读",
          },
          {
            key: "language",
            label: "输出语言",
            type: "radio",
            options: ["中文", "英文", "中英对照"],
            defaultValue: "中文",
          },
          { key: "output", label: "期望产出", defaultValue: "结构化解读笔记" },
        ],
      },
    ],
  },

  /** 数据分析 · data-analysis-expert */
  "research-analysis": {
    topicKey: "goal",
    steps: [
      {
        title: "分析目标",
        fields: [
          {
            key: "goal",
            label: "分析目标 / 研究问题",
            required: true,
            placeholder: "例：哪些因素影响用户复购",
          },
          {
            key: "background",
            label: "背景说明",
            type: "textarea",
            placeholder: "项目背景、已有结论、此次分析想验证什么",
          },
        ],
      },
      {
        title: "数据情况",
        fields: [
          {
            key: "dataType",
            label: "数据类型",
            type: "radio",
            options: ["横断面问卷", "纵向随访", "实验数据", "组学数据", "文本数据", "其他"],
          },
          { key: "scale", label: "数据量级", defaultValue: "约 500 行" },
          {
            key: "fields",
            label: "字段/变量说明",
            type: "textarea",
            placeholder: "关键字段名与含义（数据文件可后续在会话中上传）",
          },
          {
            key: "tool",
            label: "软件偏好",
            type: "radio",
            options: ["不限", "R", "Python", "SPSS"],
            defaultValue: "Python",
          },
        ],
      },
      {
        title: "方法与产出",
        fields: [
          {
            key: "methods",
            label: "期望方法",
            type: "textarea",
            placeholder: "如：描述统计、回归、生存分析、机器学习…（可留空由助手建议）",
          },
          { key: "alpha", label: "显著性水平", defaultValue: "α = 0.05" },
          {
            key: "output",
            label: "产出要求",
            type: "textarea",
            defaultValue: "图表 + 方法说明 + 结果解读",
          },
        ],
      },
    ],
  },

  /** 学术写作 · writing-expert */
  "research-writing": {
    topicKey: "task",
    steps: [
      {
        title: "写作任务",
        fields: [
          {
            key: "task",
            label: "写作任务",
            required: true,
            placeholder: "如：摘要润色 / 引言重写 / 讨论部分扩写",
          },
          {
            key: "draft",
            label: "当前稿件段落",
            type: "textarea",
            placeholder: "粘贴需要处理的原文（也可后续在会话中上传）",
          },
        ],
      },
      {
        title: "写作要求",
        fields: [
          { key: "journal", label: "目标期刊/会议", placeholder: "如未定可留空" },
          {
            key: "language",
            label: "语言",
            type: "radio",
            options: ["中文", "英文"],
            defaultValue: "英文",
          },
          {
            key: "style",
            label: "风格要求",
            type: "radio",
            options: ["学术严谨", "简洁凝练", "母语化润色"],
            defaultValue: "学术严谨",
          },
          { key: "wordLimit", label: "字数要求", placeholder: "如：≤250 词" },
        ],
      },
      {
        title: "参考与禁忌",
        fields: [
          {
            key: "keep",
            label: "必须保留的内容",
            type: "textarea",
            placeholder: "术语、结论、数据等不可改动项",
          },
          {
            key: "avoid",
            label: "需要避免的问题",
            type: "textarea",
            placeholder: "如：美式口语、过度声称、重复用词…",
          },
        ],
      },
    ],
  },

  /** 基金申请 · grant-expert */
  "research-grant": {
    topicKey: "topic",
    steps: [
      {
        title: "申请信息",
        fields: [
          {
            key: "fundType",
            label: "基金类型",
            required: true,
            type: "radio",
            options: ["国自然青年项目", "国自然面上项目", "省自然科学基金", "其他"],
          },
          {
            key: "topic",
            label: "项目主题",
            required: true,
            placeholder: "例：基于单细胞测序的肿瘤微环境研究",
          },
          { key: "deadline", label: "申报截止时间", placeholder: "如：2026-03-20" },
        ],
      },
      {
        title: "研究基础",
        fields: [
          {
            key: "basis",
            label: "研究基础与预实验",
            type: "textarea",
            placeholder: "已有工作积累、预实验结果",
          },
          { key: "team", label: "团队情况", type: "textarea", placeholder: "成员构成、分工" },
          { key: "papers", label: "代表性论文", placeholder: "1–5 篇，附期刊与年份" },
        ],
      },
      {
        title: "撰写范围",
        fields: [
          {
            key: "scope",
            label: "需撰写部分",
            type: "radio",
            options: ["立项依据", "研究内容", "技术路线", "全套申请书"],
            defaultValue: "全套申请书",
          },
          { key: "budget", label: "预算需求", type: "textarea", placeholder: "经费额度与主要用途" },
          {
            key: "notes",
            label: "特别提醒",
            type: "textarea",
            placeholder: "评审偏好、以往函审意见等",
          },
        ],
      },
    ],
  },

  /** 临床研究 · clinical-expert */
  "research-clinical": {
    topicKey: "question",
    steps: [
      {
        title: "研究设计",
        fields: [
          {
            key: "question",
            label: "研究问题（PICO）",
            required: true,
            placeholder: "例：某药 vs 安慰剂对 2 型糖尿病 HbA1c 的影响",
          },
          {
            key: "studyType",
            label: "研究类型",
            type: "radio",
            options: ["随机对照试验（RCT）", "队列研究", "病例对照", "横断面研究", "真实世界研究"],
          },
        ],
      },
      {
        title: "对象与干预",
        fields: [
          {
            key: "subjects",
            label: "研究对象 / 入排标准",
            type: "textarea",
            placeholder: "纳入标准、排除标准",
          },
          {
            key: "intervention",
            label: "干预 / 暴露因素",
            type: "textarea",
            placeholder: "试验组与对照组方案，或暴露定义",
          },
          { key: "endpoint", label: "主要终点指标", placeholder: "如：12 周 HbA1c 变化值" },
        ],
      },
      {
        title: "统计与伦理",
        fields: [
          {
            key: "sampleSizeNeed",
            label: "样本量估算",
            type: "radio",
            options: ["需要", "不需要", "已完成"],
            defaultValue: "需要",
          },
          {
            key: "analysis",
            label: "统计分析计划",
            type: "textarea",
            placeholder: "主要分析集、亚组、缺失数据处理…（可留空由助手建议）",
          },
          {
            key: "registration",
            label: "注册与伦理",
            type: "radio",
            options: ["已注册", "未注册", "不适用"],
            defaultValue: "未注册",
          },
        ],
      },
    ],
  },

  /** 投稿助手 · submission-expert */
  "research-submission": {
    topicKey: "topic",
    steps: [
      {
        title: "投稿信息",
        fields: [
          { key: "topic", label: "论文主题", required: true, placeholder: "论文标题或核心主题" },
          {
            key: "journal",
            label: "目标期刊",
            required: true,
            placeholder: "如未定可填「待推荐」",
          },
          {
            key: "articleType",
            label: "投稿类型",
            type: "radio",
            options: ["原创论著", "综述", "病例报告", "研究快讯"],
            defaultValue: "原创论著",
          },
        ],
      },
      {
        title: "稿件状态",
        fields: [
          {
            key: "lang",
            label: "当前稿件语言",
            type: "radio",
            options: ["中文", "英文"],
            defaultValue: "英文",
          },
          {
            key: "stage",
            label: "稿件完成度",
            type: "radio",
            options: ["初稿", "已润色", "返修中"],
            defaultValue: "初稿",
          },
          {
            key: "reviews",
            label: "已有审稿意见",
            type: "textarea",
            placeholder: "粘贴审稿意见（返修场景）",
          },
        ],
      },
      {
        title: "服务范围",
        fields: [
          {
            key: "service",
            label: "需要的服务",
            type: "radio",
            options: ["期刊匹配推荐", "Cover Letter", "审稿意见逐条回复", "投稿格式调整"],
          },
          { key: "timeline", label: "时间要求", placeholder: "如：两周内返修" },
          { key: "notes", label: "其他说明", type: "textarea" },
        ],
      },
    ],
  },

  /** 诚信检测 · integrity-expert */
  "research-integrity": {
    topicKey: "target",
    steps: [
      {
        title: "检测对象",
        fields: [
          {
            key: "target",
            label: "检测内容类型",
            required: true,
            type: "radio",
            options: ["论文文本", "数据", "图像", "引用"],
            defaultValue: "论文文本",
          },
          {
            key: "paper",
            label: "论文标题或片段",
            type: "textarea",
            placeholder: "粘贴待检测的标题/摘要/正文片段（全文可后续在会话中上传）",
          },
        ],
      },
      {
        title: "检测关注",
        fields: [
          {
            key: "risk",
            label: "关注风险",
            type: "radio",
            options: ["文本抄袭", "数据造假", "图像重复", "不当引用", "AI 生成痕迹", "全面体检"],
            defaultValue: "全面体检",
          },
          {
            key: "clues",
            label: "已知疑点",
            type: "textarea",
            placeholder: "被质疑的段落、相似文献线索等",
          },
        ],
      },
      {
        title: "报告要求",
        fields: [
          {
            key: "output",
            label: "输出形式",
            type: "radio",
            options: ["风险清单", "详细报告", "整改建议"],
            defaultValue: "详细报告",
          },
          { key: "standard", label: "依据标准", defaultValue: "出版伦理委员会（COPE）准则" },
          { key: "deadline", label: "处理时限", placeholder: "如：3 个工作日内" },
        ],
      },
    ],
  },
};
