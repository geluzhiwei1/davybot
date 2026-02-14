# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""领域适配器 - Domain Adapter

根据不同领域调整 agent 行为，实现通用 agent 的领域智能化。

支持的领域类型：
- SOFTWARE: 软件开发
- DATA_ANALYSIS: 数据分析
- WRITING: 文档写作
- RESEARCH: 研究项目
- BUSINESS: 业务管理
- EDUCATION: 教育培训
- OPERATIONS: 系统运维
- MARKETING: 集市营销
- GENERAL: 通用/其他
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DomainType(Enum):
    """任务领域类型"""

    SOFTWARE = "software"  # 软件开发
    DATA_ANALYSIS = "data"  # 数据分析
    WRITING = "writing"  # 文档写作
    RESEARCH = "research"  # 研究项目
    BUSINESS = "business"  # 业务管理
    EDUCATION = "education"  # 教育培训
    OPERATIONS = "operations"  # 运维操作
    MARKETING = "marketing"  # 集市营销
    GENERAL = "general"  # 通用/其他


@dataclass
class DomainContext:
    """领域特定上下文"""

    domain: DomainType
    typical_outputs: list[str]
    quality_criteria: list[str]
    common_tools: list[str]
    success_metrics: list[str]
    workflows: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "domain": self.domain.value,
            "typical_outputs": self.typical_outputs,
            "quality_criteria": self.quality_criteria,
            "common_tools": self.common_tools,
            "success_metrics": self.success_metrics,
            "workflows": self.workflows,
        }


class DomainAdapter:
    """领域适配器 - 根据不同领域调整 agent 行为"""

    def __init__(self):
        self._domain_keywords = self._init_domain_keywords()
        self._domain_contexts = self._init_domain_contexts()

    def _init_domain_keywords(self) -> dict[DomainType, list[str]]:
        """初始化领域关键词（中英文）"""
        return {
            DomainType.SOFTWARE: [
                # 中文关键词
                "代码",
                "编程",
                "开发",
                "软件",
                "应用",
                "功能",
                "bug",
                "修复",
                "api",
                "接口",
                "数据库",
                "前端",
                "后端",
                "部署",
                "测试",
                # 英文关键词
                "code",
                "coding",
                "programming",
                "develop",
                "software",
                "app",
                "application",
                "feature",
                "bug",
                "fix",
                "api",
                "database",
                "frontend",
                "backend",
                "deploy",
                "test",
                "git",
                "github",
                "commit",
                "pr",
                "pull request",
            ],
            DomainType.DATA_ANALYSIS: [
                # 中文关键词
                "数据",
                "分析",
                "模型",
                "统计",
                "可视化",
                "图表",
                "报表",
                "机器学习",
                "深度学习",
                "预测",
                "分类",
                "聚类",
                "pandas",
                "numpy",
                "数据分析",
                "dataframe",
                # 英文关键词
                "data",
                "analysis",
                "analytics",
                "model",
                "statistical",
                "visualization",
                "chart",
                "graph",
                "report",
                "dashboard",
                "machine learning",
                "ml",
                "deep learning",
                "dl",
                "predict",
                "classify",
                "cluster",
                "regression",
                "pandas",
                "numpy",
            ],
            DomainType.WRITING: [
                # 中文关键词
                "写",
                "文档",
                "文章",
                "报告",
                "总结",
                "发布",
                "博客",
                "教程",
                "指南",
                "手册",
                "说明",
                "描述",
                "撰写",
                # 英文关键词
                "write",
                "writing",
                "document",
                "documentation",
                "article",
                "report",
                "summary",
                "publish",
                "blog",
                "post",
                "tutorial",
                "guide",
                "manual",
                "instruction",
                "describe",
                "draft",
            ],
            DomainType.RESEARCH: [
                # 中文关键词
                "研究",
                "实验",
                "论文",
                "调查",
                "验证",
                "发现",
                "假设",
                "文献",
                "学术",
                "科学",
                "探索",
                "实证",
                # 英文关键词
                "research",
                "study",
                "experiment",
                "paper",
                "survey",
                "verify",
                "validate",
                "discovery",
                "hypothesis",
                "literature",
                "academic",
                "science",
                "scientific",
                "explore",
                "empirical",
            ],
            DomainType.BUSINESS: [
                # 中文关键词
                "业务",
                "策略",
                "管理",
                "kpi",
                "目标",
                "流程",
                "优化",
                "增长",
                "营收",
                "成本",
                "效率",
                "项目",
                "团队",
                # 英文关键词
                "business",
                "strategy",
                "management",
                "kpi",
                "goal",
                "process",
                "optimize",
                "growth",
                "revenue",
                "cost",
                "efficiency",
                "project",
                "team",
                "workflow",
                "roi",
            ],
            DomainType.EDUCATION: [
                # 中文关键词
                "教学",
                "培训",
                "课程",
                "学习",
                "教育",
                "训练",
                "学员",
                "评估",
                "考试",
                "知识",
                "技能",
                "教程",
                # 英文关键词
                "teach",
                "training",
                "course",
                "learning",
                "education",
                "student",
                "learner",
                "assess",
                "exam",
                "knowledge",
                "skill",
                "tutorial",
                "lesson",
                "instruction",
            ],
            DomainType.OPERATIONS: [
                # 中文关键词
                "运维",
                "部署",
                "监控",
                "故障",
                "诊断",
                "服务器",
                "系统",
                "网络",
                "性能",
                "安全",
                "备份",
                "恢复",
                # 英文关键词
                "ops",
                "operation",
                "deploy",
                "deployment",
                "monitor",
                "incident",
                "fault",
                "diagnose",
                "server",
                "system",
                "network",
                "performance",
                "security",
                "backup",
                "recover",
                "devops",
                "sre",
                "infrastructure",
            ],
            DomainType.MARKETING: [
                # 中文关键词
                "营销",
                "推广",
                "活动",
                "品牌",
                "用户",
                "客户",
                "集市",
                "渠道",
                "转化",
                "投放",
                "广告",
                "内容",
                # 英文关键词
                "marketing",
                "promote",
                "campaign",
                "brand",
                "branding",
                "customer",
                "client",
                "market",
                "channel",
                "conversion",
                "ad",
                "advertising",
                "content",
                "social media",
                "seo",
            ],
        }

    def _init_domain_contexts(self) -> dict[DomainType, DomainContext]:
        """初始化领域特定上下文"""
        return {
            DomainType.SOFTWARE: DomainContext(
                domain=DomainType.SOFTWARE,
                typical_outputs=["代码", "配置文件", "API文档", "测试报告"],
                quality_criteria=["功能正确", "性能达标", "代码质量", "无安全漏洞"],
                common_tools=["git", "ide", "testing_frameworks", "linter"],
                success_metrics=["功能完成度", "测试覆盖率", "性能指标", "代码质量分"],
                workflows={
                    "plan": ["需求分析", "技术探索", "架构设计", "任务分解"],
                    "do": ["编写代码", "编写测试", "代码审查", "提交代码"],
                    "check": ["运行测试", "性能测试", "安全扫描", "代码审查"],
                    "act": ["更新文档", "重构优化", "分享经验", "技术分享"],
                },
            ),
            DomainType.DATA_ANALYSIS: DomainContext(
                domain=DomainType.DATA_ANALYSIS,
                typical_outputs=["数据集", "模型", "分析报告", "可视化图表"],
                quality_criteria=["准确性", "完整性", "可重复性", "洞察价值"],
                common_tools=["python", "r", "sql", "pandas", "visualization_tools"],
                success_metrics=[
                    "模型准确率",
                    "数据完整性",
                    "分析洞察数量",
                    "报告质量",
                ],
                workflows={
                    "plan": ["问题理解", "数据探索", "方法选择", "分析计划"],
                    "do": ["数据清洗", "特征工程", "模型训练", "结果生成"],
                    "check": ["模型验证", "准确性测试", "结果复核", "可重复性检查"],
                    "act": ["文档化模型", "创建模板", "总结方法", "分享洞察"],
                },
            ),
            DomainType.WRITING: DomainContext(
                domain=DomainType.WRITING,
                typical_outputs=["文档", "文章", "报告", "教程"],
                quality_criteria=["准确性", "可读性", "结构清晰", "格式规范"],
                common_tools=["editor", "grammar_check", "formatting", "markdown"],
                success_metrics=["内容完整性", "阅读体验", "准确性", "格式规范"],
                workflows={
                    "plan": ["理解主题", "收集资料", "设计大纲", "撰写计划"],
                    "do": ["撰写内容", "组织结构", "编辑润色", "添加示例"],
                    "check": ["校对审核", "事实核查", "用户测试", "可读性检查"],
                    "act": ["完善发布", "创建模板", "更新规范", "总结经验"],
                },
            ),
            DomainType.RESEARCH: DomainContext(
                domain=DomainType.RESEARCH,
                typical_outputs=["研究论文", "实验数据", "研究方法", "发现结论"],
                quality_criteria=["科学性", "可重复性", "严谨性", "创新性"],
                common_tools=["实验设备", "统计软件", "文献管理", "数据分析"],
                success_metrics=[
                    "实验可重复性",
                    "数据可靠性",
                    "结论有依据",
                    "方法创新",
                ],
                workflows={
                    "plan": ["问题定义", "文献调研", "假设设计", "实验设计"],
                    "do": ["执行实验", "收集数据", "记录观察", "初步分析"],
                    "check": ["结果分析", "同行评议", "假设验证", "统计检验"],
                    "act": ["撰写论文", "发表发现", "贡献知识", "规划后续"],
                },
            ),
            DomainType.BUSINESS: DomainContext(
                domain=DomainType.BUSINESS,
                typical_outputs=["策略文档", "执行报告", "KPI报告", "流程优化方案"],
                quality_criteria=["目标达成", "ROI合理", "流程高效", "风险可控"],
                common_tools=["项目管理", "数据分析", "协作工具", "报告工具"],
                success_metrics=["KPI达成率", "ROI", "效率提升", "成本控制"],
                workflows={
                    "plan": ["目标设定", "集市分析", "策略设计", "资源规划"],
                    "do": ["执行策略", "配置资源", "管理运营", "跟踪数据"],
                    "check": ["KPI检查", "效果评估", "ROI分析", "风险评估"],
                    "act": ["优化流程", "标准化SOP", "总结案例", "规划改进"],
                },
            ),
            DomainType.EDUCATION: DomainContext(
                domain=DomainType.EDUCATION,
                typical_outputs=["课程内容", "教学材料", "评估报告", "学习指南"],
                quality_criteria=["学习效果", "内容质量", "教学方法", "学员满意度"],
                common_tools=["教学平台", "内容创作", "评估工具", "协作工具"],
                success_metrics=["学习成果", "学员反馈", "知识掌握度", "技能提升"],
                workflows={
                    "plan": ["需求分析", "受众调研", "课程设计", "教学计划"],
                    "do": ["准备教材", "实施教学", "组织活动", "评估学习"],
                    "check": ["效果评估", "学员反馈", "成果验证", "质量检查"],
                    "act": ["改进方法", "更新课程", "创建模板", "总结经验"],
                },
            ),
            DomainType.OPERATIONS: DomainContext(
                domain=DomainType.OPERATIONS,
                typical_outputs=["部署文档", "监控报告", "故障报告", "操作手册"],
                quality_criteria=["稳定性", "可靠性", "性能达标", "安全合规"],
                common_tools=["监控工具", "部署工具", "日志分析", "自动化脚本"],
                success_metrics=["系统可用性", "故障响应时间", "性能指标", "安全事件"],
                workflows={
                    "plan": ["问题诊断", "系统探索", "方案设计", "风险评估"],
                    "do": ["实施修复", "配置变更", "部署服务", "监控指标"],
                    "check": ["验证效果", "检查监控", "确认指标", "回归测试"],
                    "act": ["文档化", "预防措施", "自动化", "总结优化"],
                },
            ),
            DomainType.MARKETING: DomainContext(
                domain=DomainType.MARKETING,
                typical_outputs=["营销内容", "推广报告", "分析报告", "优化方案"],
                quality_criteria=["转化率", "ROI", "品牌曝光", "用户反馈"],
                common_tools=["分析工具", "内容创作", "社交媒体", "广告平台"],
                success_metrics=["转化率", "ROI", "用户增长", "品牌认知"],
                workflows={
                    "plan": ["集市调研", "目标定位", "策略制定", "内容规划"],
                    "do": ["创作内容", "执行推广", "管理活动", "跟踪数据"],
                    "check": ["数据分析", "效果评估", "转化分析", "ROI计算"],
                    "act": ["优化策略", "总结经验", "创建模板", "规划活动"],
                },
            ),
            DomainType.GENERAL: DomainContext(
                domain=DomainType.GENERAL,
                typical_outputs=["成果物", "报告", "文档"],
                quality_criteria=["目标达成", "质量达标", "按时完成"],
                common_tools=["通用工具"],
                success_metrics=["完成度", "质量", "效率"],
                workflows={
                    "plan": ["理解需求", "分析任务", "制定计划"],
                    "do": ["执行任务", "管理进度"],
                    "check": ["验证结果", "评估质量"],
                    "act": ["总结经验", "改进优化"],
                },
            ),
        }

    def detect_domain(self, task_description: str) -> DomainType:
        """检测任务领域

        Args:
            task_description: 任务描述

        Returns:
            检测到的领域类型

        """
        if not task_description:
            return DomainType.GENERAL

        # 转换为小写进行匹配
        task_lower = task_description.lower()

        # 计算每个领域的匹配分数
        scores = {}
        for domain, keywords in self._domain_keywords.items():
            score = 0
            for keyword in keywords:
                if keyword.lower() in task_lower:
                    score += 1
            scores[domain] = score

        # 找出最高分
        max_score = max(scores.values())

        if max_score > 0:
            # 返回得分最高的领域
            return max(scores, key=scores.get)

        # 没有匹配的关键词，返回通用类型
        return DomainType.GENERAL

    def get_domain_context(self, domain: DomainType) -> DomainContext:
        """获取领域特定上下文

        Args:
            domain: 领域类型

        Returns:
            领域上下文

        """
        return self._domain_contexts.get(domain, self._domain_contexts[DomainType.GENERAL])

    def get_workflow_for_phase(self, domain: DomainType, phase: str) -> list[str]:
        """获取特定领域和阶段的工作流程

        Args:
            domain: 领域类型
            phase: PDCA 阶段 (plan/do/check/act)

        Returns:
            工作流程步骤列表

        """
        context = self.get_domain_context(domain)
        return context.workflows.get(phase, [])

    def get_quality_criteria(self, domain: DomainType) -> list[str]:
        """获取质量标准"""
        context = self.get_domain_context(domain)
        return context.quality_criteria

    def get_typical_outputs(self, domain: DomainType) -> list[str]:
        """获取典型产出物"""
        context = self.get_domain_context(domain)
        return context.typical_outputs

    def get_success_metrics(self, domain: DomainType) -> list[str]:
        """获取成功指标"""
        context = self.get_domain_context(domain)
        return context.success_metrics

    def detect_domain_from_context(self, context: dict[str, Any]) -> DomainType:
        """从上下文中检测领域（更复杂的检测）

        Args:
            context: 任务上下文，可能包含文件路径、工具、环境信息等

        Returns:
            检测到的领域类型

        """
        # 检查文件扩展名
        file_paths = context.get("file_paths", [])
        for file_path in file_paths:
            if file_path.endswith((".py", ".js", ".ts", ".java", ".cpp", ".go")):
                return DomainType.SOFTWARE
            if file_path.endswith((".ipynb", ".csv", ".parquet", ".json")):
                return DomainType.DATA_ANALYSIS
            if file_path.endswith((".md", ".txt", ".docx", ".pdf")):
                return DomainType.WRITING

        # 检查工具
        tools = context.get("tools", [])
        tools_str = " ".join(tools).lower()
        if any(t in tools_str for t in ["git", "github", "ide", "test"]):
            return DomainType.SOFTWARE
        if any(t in tools_str for t in ["pandas", "numpy", "sql", "jupyter"]):
            return DomainType.DATA_ANALYSIS

        # 检查环境
        environment = context.get("environment", "").lower()
        if "dev" in environment or "production" in environment:
            return DomainType.SOFTWARE
        if "data" in environment or "analytics" in environment:
            return DomainType.DATA_ANALYSIS

        # 默认返回通用类型
        return DomainType.GENERAL


# 单例实例
_domain_adapter_instance = None


def get_domain_adapter() -> DomainAdapter:
    """获取领域适配器单例实例"""
    global _domain_adapter_instance
    if _domain_adapter_instance is None:
        _domain_adapter_instance = DomainAdapter()
    return _domain_adapter_instance
