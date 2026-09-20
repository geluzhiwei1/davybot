import {
  Scale,
  FileSearch,
  Landmark,
  ShieldAlert,
  Globe,
  Newspaper,
  TrendingUp,
  FileWarning,
  type LucideIcon,
} from "lucide-react";
import type { AutomationFrequency } from "./store";

export interface AutomationTemplate {
  id: string;
  name: string;
  desc: string;
  icon: LucideIcon;
  prompt: string;
  frequency: AutomationFrequency;
  time: string;
  weekdays: number[];
  intervalDays?: number;
}

export const AUTOMATION_TEMPLATES: AutomationTemplate[] = [
  {
    id: "daily-law-update",
    name: "每日新法规速递",
    desc: "每天汇总最新发布的法律法规、司法解释及政策文件，提炼核心要点。",
    icon: Scale,
    prompt:
      "汇总过去 24 小时中国最新发布的法律法规、司法解释、部门规章及重要政策文件，按「法律 / 行政法规 / 司法解释 / 部门规章 / 地方性法规」分类，每条给出文件名称、发布机关、生效日期和核心要点（2-3 句话）。如无新增则说明近期无新规发布。",
    frequency: "daily",
    time: "09:00",
    weekdays: [0, 1, 2, 3, 4, 5, 6],
  },
  {
    id: "weekly-case-review",
    name: "每周典型案例精析",
    desc: "每周精选 2-3 个典型法律案例，深入分析裁判要旨、法律适用与实务启示。",
    icon: FileSearch,
    prompt:
      "精选本周值得关注的 2-3 个典型法律案例（优先选取最高人民法院公报案例、指导性案例或社会关注度高的案件），对每个案例分别分析：(1) 基本案情摘要；(2) 争议焦点；(3) 裁判要旨与法律依据；(4) 对律师实务的启示与建议。按民商事、刑事、行政分类呈现。",
    frequency: "daily",
    time: "10:00",
    weekdays: [4],
  },
  {
    id: "compliance-check",
    name: "合规风险周报",
    desc: "每周扫描企业合规领域动态，提示潜在合规风险与监管趋势。",
    icon: Landmark,
    prompt:
      "梳理本周企业合规领域的重要动态，包括：(1) 监管执法动态——市场监管、数据合规、劳动用工、税务等领域的处罚案例与执法趋势；(2) 立法动向——正在征求意见或即将生效的涉企法规；(3) 行业合规热点——当前最受关注的合规话题（如数据跨境、ESG、反垄断等）；(4) 风险提示——基于以上信息，为企业法务/合规团队列出 3-5 条本周需重点关注的风险事项及应对建议。",
    frequency: "daily",
    time: "08:30",
    weekdays: [0],
  },
  // ─── M7 合规自动化模板 (Phase 2 Weeks 10-12) ──────────────────────
  {
    id: "daily-sanctions-scan",
    name: "每日制裁名单扫描",
    desc: "每日自动扫描 OFAC/UN/EU 制裁名单更新，推送新增/变更实体与风险提示。",
    icon: ShieldAlert,
    prompt:
      "扫描过去 24 小时内 OFAC SDN/SSI、UN 制裁名单、EU 制裁名单和 BIS 实体清单的更新情况。输出格式：(1) 新增制裁实体——名称/别名/制裁计划/管辖区域/制裁类型；(2) 移除或变更的实体；(3) 制裁政策更新——OFAC 一般许可证/EU 理事会法规变更；(4) 风险提示——本次更新中与中国企业/个人直接相关的条目，以及合规建议。如无更新则简要说明制裁名单今日无变动。",
    frequency: "daily",
    time: "08:00",
    weekdays: [0, 1, 2, 3, 4, 5, 6],
  },
  {
    id: "weekly-pep-rescreen",
    name: "每周 PEP 政治人物重筛",
    desc: "每周对监控名单中的客户/交易对手重新筛查是否为 PEP 及其亲属。",
    icon: Globe,
    prompt:
      "对监控名单中所有高/中风险客户重新执行 PEP 筛查。分析：(1) 是否有客户本人或其直系亲属新晋为政治公众人物（PEP）、国际组织高管或军警高官；(2) 对比上周状态，识别新增 PEP；(3) 按 FATF 风险等级分类 Tier 1（国家级元首/政府首脑）、Tier 2（部级/议会成员）、Tier 3（其他公职人员）；(4) 对新增 PEP 给出风险处置建议（升级 EDD、调整风险评级、加强交易监控等）。最后附上 PEP 数据库来源更新说明。",
    frequency: "daily",
    time: "09:00",
    weekdays: [0], // 周一
  },
  {
    id: "daily-adverse-media",
    name: "每日负面新闻扫描",
    desc: "每日对监控实体扫描全球主流媒体的负面新闻，识别洗钱/腐败/制裁规避风险。",
    icon: Newspaper,
    prompt:
      "扫描过去 24 小时内与监控名单中实体相关的负面新闻报道。按以下分类呈现：(1) 金融犯罪——洗钱/欺诈/税务犯罪相关报道；(2) 腐败贿赂——受贿/行贿/贪污案件；(3) 制裁规避——试图绕过制裁的报道；(4) 监管处罚——被监管机构/执法部门处罚的新闻；(5) 其他负面——环境/劳工/商业纠纷等。每条新闻标注来源、日期、相关实体名称、风险等级（红/黄/绿）、以及是否需要立即响应。最后以风险矩阵总览收尾。",
    frequency: "daily",
    time: "10:00",
    weekdays: [0, 1, 2, 3, 4, 5, 6],
  },
  {
    id: "monthly-compliance-report",
    name: "月度合规全景报告",
    desc: "每月自动生成合规全景报告——筛选统计、告警趋势、法规变动、审计建议。",
    icon: TrendingUp,
    prompt:
      "生成上个月的企业合规全景报告，包含以下六大板块：(1) 制裁筛查综述——本月筛查总量、命中率趋势、Top 10 命中制裁计划/国家分布；(2) 风险告警复盘——本月新告警/已解决告警/升级告警数量及典型案例；(3) 法规政策变动——影响本企业合规义务的新法规/监管政策/制裁令，标注重点和应对建议；(4) 尽调统计——KYC/供应商/合作伙伴尽职调查完成率与问题发现；(5) 合规培训与整改——本月实施的培训、发现的合规问题及整改措施进展；(6) 下月风险预警——基于当前趋势预测下月需重点关注的 5 大合规风险及建议行动。格式要求：专业报告风格，图表化数据（用表格呈现），行动导向的结论。",
    frequency: "daily",
    time: "07:00",
    weekdays: [0],
    intervalDays: 30,
  },
  {
    id: "export-control-watch",
    name: "出口管制法规变动预警",
    desc: "监控 EAR/ITAR/中国出口管制法/欧盟两用物项条例等法规变化，立即推送预警。",
    icon: FileWarning,
    prompt:
      "扫描最新的出口管制法规变动，涵盖但不限于：(1) 美国 EAR/BIS——CCL 清单调整、ECCN 重新分类、新实体清单/军事最终用户清单增删；(2) ITAR——USML 更新、新 ITAR 豁免/修正；(3) 中国出口管制法——管制清单更新、临时管制公告、不可靠实体清单调整；(4) 欧盟——两用物项条例更新、成员国管制措施变化；(5) 多边机制——瓦森纳安排/导弹技术管制制度/核供应国集团等更新。对每一项变动评估与本企业产品/业务的相关度（直接相关/间接相关/备查），直接相关须详细分析影响和应对建议。",
    frequency: "daily",
    time: "08:30",
    weekdays: [0, 1, 2, 3, 4], // 工作日
  },
  {
    id: "sanctions-policy-change",
    name: "制裁政策变动即时告警",
    desc: "OFAC/UN/EU/OF SI 等主要制裁机构发布新政策时即时推送分析。",
    icon: ShieldAlert,
    prompt:
      "检测到制裁政策变动后立即执行分析。检查以下来源的更新：(1) OFAC——新增制裁计划/一般许可证/FAQ 更新/合规框架变更；(2) UN 安理会——新增/调整制裁决议；(3) EU——理事会条例/决定更新、制裁名单增删；(4) UK OFSI——OF SI 金融制裁更新；(5) 中国——反外国制裁法相关执行措施/不可靠实体清单调整。对每项变动输出：(a) 发布机构与文件编号；(b) 核心内容摘要（2-3 句）；(c) 对中国出海企业的影响评估（金融/贸易/投资/人员）；(d) 紧急行动建议（停止交易/暂停出货/寻求法律意见/内部自查/备案存档）；(e) 生效时间与过渡期。最后按紧急程度排序（红色：立即行动/橙色：24h内/黄色：本周内/绿色：备查）。",
    frequency: "daily",
    time: "immediate",
    weekdays: [0, 1, 2, 3, 4, 5, 6],
  },
];
