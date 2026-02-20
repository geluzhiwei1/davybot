# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""多模型智能路由器（
根据任务类型、上下文长度、重要性自动选择最优模型
目标：降低 LLM 成本 70-90%
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from dawei.config import get_dawei_home

# ============================================================================
# 任务类型枚举
# ============================================================================


class TaskType(StrEnum):
    """任务类型枚举"""

    CODE_COMPLETION = "code_completion"  # 代码补全
    COMPLEX_REASONING = "complex_reasoning"  # 复杂推理
    LONG_CONTEXT = "long_context"  # 长上下文
    CRITICAL_OUTPUT = "critical_output"  # 关键输出
    DAILY_CHAT = "daily_chat"  # 日常对话


# ============================================================================
# 配置数据类
# ============================================================================


@dataclass
class RouterConfig:
    """模型路由配置"""

    default: str  # 默认模型
    code_completion: str | None = None  # 代码补全模型
    complex_reasoning: str | None = None  # 复杂推理模型
    long_context: str | None = None  # 长上下文模型
    long_context_threshold: int = 60000  # 长上下文阈值 (tokens)
    critical_output: str | None = None  # 关键输出模型

    @classmethod
    def from_dict(cls, data: dict) -> "RouterConfig":
        """从字典创建配置

        Args:
            data: 配置字典

        Returns:
            RouterConfig: 验证后的配置对象

        Raises:
            ValueError: 如果配置无效
            TypeError: 如果数据类型错误
        """
        # Fast Fail: 验证输入
        if not isinstance(data, dict):
            raise TypeError(f"data must be a dictionary, got {type(data).__name__}")

        # 验证并提取必需字段
        default = data.get("default")
        if not default or not isinstance(default, str):
            raise ValueError(f"default field must be a non-empty string, got {default}")

        # 验证并提取可选字段
        long_context_threshold = data.get("longContextThreshold", 60000)
        if not isinstance(long_context_threshold, int) or long_context_threshold <= 0:
            raise ValueError(f"longContextThreshold must be a positive integer, got {long_context_threshold}")

        return cls(
            default=default,
            code_completion=data.get("codeCompletion"),
            complex_reasoning=data.get("complexReasoning"),
            long_context=data.get("longContext"),
            long_context_threshold=long_context_threshold,
            critical_output=data.get("criticalOutput"),
        )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "default": self.default,
            "codeCompletion": self.code_completion,
            "complexReasoning": self.complex_reasoning,
            "longContext": self.long_context,
            "longContextThreshold": self.long_context_threshold,
            "criticalOutput": self.critical_output,
        }


@dataclass
class ModelCost:
    """模型定价信息"""

    input: float  # 输入价格（per 1M tokens）
    output: float  # 输出价格（per 1M tokens）
    unit: str = "per_1m_tokens"  # 单位

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """计算使用成本"""
        input_cost = (input_tokens / 1_000_000) * self.input
        output_cost = (output_tokens / 1_000_000) * self.output
        return round(input_cost + output_cost, 4)


@dataclass
class ModelSelection:
    """模型选择结果"""

    model: str  # 选择的模型
    reason: str  # 选择原因
    task_type: TaskType  # 任务类型
    confidence: float = 1.0  # 置信度（0-1）
    timestamp: float = field(default_factory=time.time)


# ============================================================================
# 模型路由器
# ============================================================================


class ModelRouter:
    """多模型智能路由器

    根据任务特征自动选择最优模型，实现成本优化
    """

    def __init__(
        self,
        config: RouterConfig,
        cost_config: dict[str, ModelCost] | None = None,
        user_default_model: str | None = None,
    ):
        """初始化模型路由器

        Args:
            config: 路由配置
            cost_config: 模型成本配置（可选）
            user_default_model: 用户选择的默认模型（可选，优先级高于 config.default）

        """
        self.config = config
        self.cost_config = cost_config or {}
        self.user_default_model = user_default_model
        self.logger = logging.getLogger(__name__)

        # 如果用户选择了模型，记录日志
        if user_default_model:
            self.logger.info(
                f"ModelRouter initialized with user-selected default model: {user_default_model}",
            )

        # 【可靠性增强】模型健康状态管理
        self.model_health = {}  # {model_name: is_healthy}
        self.model_failure_count = {}  # {model_name: failure_count}
        self.health_check_threshold = 3  # 连续失败3次标记为不健康

        # 复杂推理关键词检测
        self.complex_reasoning_keywords = [
            "design",
            "architecture",
            "refactor",
            "optimize",
            "设计",
            "架构",
            "重构",
            "优化",
            "algorithm",
            "performance",
            "策略",
            "分析",
            "规划",
            "方案",
            "complex",
            "complexity",
            "复杂",
        ]

        # 关键任务关键词
        self.critical_keywords = [
            "formal report",
            "正式报告",
            "production",
            "生产环境",
            "official",
            "官方",
        ]

    def select_model(
        self,
        prompt: str,
        context_length: int = 0,
        task_type: TaskType | None = None,
        is_critical: bool = False,
        available_models: list[str] | None = None,
    ) -> ModelSelection:
        """根据任务特征选择最优模型

        Args:
            prompt: 用户提示词
            context_length: 上下文长度（tokens）
            task_type: 显式指定的任务类型（可选）
            is_critical: 是否为关键任务
            available_models: 可用的模型列表（可选）

        Returns:
            模型选择结果

        """
        # 1. 验证模型可用性
        selected_model = self._select_model_internal(prompt, context_length, task_type, is_critical)

        # 如果模型不在可用列表中，回退到默认模型（优先用户选择）
        if available_models and selected_model not in available_models:
            self.logger.warning(
                f"Selected model {selected_model} not in available models, falling back to default",
            )
            selected_model = self.user_default_model or self.config.default

        # 推断任务类型（用于记录）
        inferred_task_type = task_type or self._infer_task_type(prompt, context_length, is_critical)

        # 生成选择原因
        reason = self._generate_selection_reason(
            selected_model,
            inferred_task_type,
            context_length,
            is_critical,
        )

        self.logger.info(
            f"ModelRouter selected {selected_model} - {reason} (task: {inferred_task_type.value}, context: {context_length} tokens)",
        )

        return ModelSelection(
            model=selected_model,
            reason=reason,
            task_type=inferred_task_type,
            confidence=self._calculate_confidence(inferred_task_type, context_length),
        )

    def _select_model_internal(
        self,
        prompt: str,
        context_length: int,
        task_type: TaskType | None,
        is_critical: bool,
    ) -> str:
        """内部模型选择逻辑（考虑模型健康状态）"""
        # 【可靠性增强】构建候选模型列表，优先选择健康的模型
        candidates = []

        # 1. 长上下文任务检测（最高优先级）
        if context_length > self.config.long_context_threshold and self.config.long_context:
            candidates.append(self.config.long_context)

        # 2. 关键任务检测
        if is_critical and self.config.critical_output:
            candidates.append(self.config.critical_output)

        # 3. 显式任务类型
        if task_type:
            model = self._get_model_for_task_type(task_type)
            if model:
                candidates.append(model)

        # 4. 自动检测任务类型
        auto_task_type = self._infer_task_type(prompt, context_length, is_critical)
        model = self._get_model_for_task_type(auto_task_type)
        if model:
            candidates.append(model)

        # 5. 默认模型（优先使用用户选择，其次使用配置默认值）
        default_model = self.user_default_model or self.config.default
        candidates.append(default_model)

        # 【可靠性增强】从候选模型中选择第一个健康的模型
        for candidate_model in candidates:
            if self._is_model_healthy(candidate_model):
                self.logger.debug(f"Selected healthy model: {candidate_model}")
                return candidate_model
            self.logger.warning(
                f"Model {candidate_model} is unhealthy (recent failures), trying next candidate",
            )

        # 【可靠性增强】如果所有候选模型都不健康，返回默认模型并警告
        default_model = self.user_default_model or self.config.default
        self.logger.error(
            f"All candidate models are unhealthy, falling back to default: {default_model}",
        )
        return default_model

    def _infer_task_type(self, prompt: str, context_length: int, is_critical: bool) -> TaskType:
        """自动推断任务类型"""
        # 关键任务
        if is_critical or self._contains_keywords(prompt, self.critical_keywords):
            return TaskType.CRITICAL_OUTPUT

        # 长上下文
        if context_length > self.config.long_context_threshold:
            return TaskType.LONG_CONTEXT

        # 复杂推理
        if self._contains_keywords(prompt, self.complex_reasoning_keywords):
            return TaskType.COMPLEX_REASONING

        # 代码补全
        if self._is_code_completion_task(prompt):
            return TaskType.CODE_COMPLETION

        # 默认为日常对话
        return TaskType.DAILY_CHAT

    def _get_model_for_task_type(self, task_type: TaskType) -> str | None:
        """根据任务类型获取对应模型"""
        mapping = {
            TaskType.CODE_COMPLETION: self.config.code_completion,
            TaskType.COMPLEX_REASONING: self.config.complex_reasoning,
            TaskType.LONG_CONTEXT: self.config.long_context,
            TaskType.CRITICAL_OUTPUT: self.config.critical_output,
        }
        return mapping.get(task_type)

    def _contains_keywords(self, text: str, keywords: list[str]) -> bool:
        """检查文本是否包含关键词"""
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)

    def _is_code_completion_task(self, prompt: str) -> bool:
        """判断是否为代码补全任务"""
        code_indicators = [
            "完成这个函数",
            "complete the function",
            "实现这个方法",
            "implement this method",
            "补全代码",
            "代码补全",
        ]
        return self._contains_keywords(prompt, code_indicators)

    def _generate_selection_reason(
        self,
        _model: str,
        task_type: TaskType,
        context_length: int,
        is_critical: bool,
    ) -> str:
        """生成模型选择原因"""
        reasons = []

        if is_critical:
            reasons.append("critical task")

        if task_type == TaskType.LONG_CONTEXT:
            reasons.append(f"long context ({context_length} tokens)")
        elif task_type == TaskType.COMPLEX_REASONING:
            reasons.append("complex reasoning")
        elif task_type == TaskType.CODE_COMPLETION:
            reasons.append("code completion")
        elif task_type == TaskType.CRITICAL_OUTPUT:
            reasons.append("critical output")

        if not reasons:
            reasons.append("default model")

        return ", ".join(reasons)

    def _calculate_confidence(self, task_type: TaskType, _context_length: int) -> float:
        """计算选择置信度"""
        # 显式任务类型置信度更高
        confidence_map = {
            TaskType.CRITICAL_OUTPUT: 0.95,
            TaskType.LONG_CONTEXT: 0.90,
            TaskType.COMPLEX_REASONING: 0.80,
            TaskType.CODE_COMPLETION: 0.75,
            TaskType.DAILY_CHAT: 0.70,
        }
        return confidence_map.get(task_type, 0.70)

    def get_model_cost(self, model: str) -> ModelCost | None:
        """获取模型定价信息"""
        return self.cost_config.get(model)

    def calculate_cost_savings(
        self,
        selected_model: str,
        input_tokens: int,
        output_tokens: int,
        alternative_model: str = "anthropic/claude-opus-4",
    ) -> dict[str, Any]:
        """计算成本节省

        Args:
            selected_model: 实际使用的模型
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
            alternative_model: 对比的高成本模型

        Returns:
            成本节省信息

        """
        selected_cost = self.cost_config.get(selected_model)
        alternative_cost_info = self.cost_config.get(alternative_model)

        if not selected_cost or not alternative_cost_info:
            return {"error": "Cost information not available"}

        actual_cost = selected_cost.calculate_cost(input_tokens, output_tokens)
        alternative_cost = alternative_cost_info.calculate_cost(input_tokens, output_tokens)

        savings = alternative_cost - actual_cost
        savings_percentage = (savings / alternative_cost * 100) if alternative_cost > 0 else 0

        return {
            "actual_cost": round(actual_cost, 4),
            "alternative_cost": round(alternative_cost, 4),
            "savings": round(savings, 4),
            "savings_percentage": round(savings_percentage, 1),
            "selected_model": selected_model,
            "alternative_model": alternative_model,
        }

    # ========================================================================
    # 模型健康状态管理（可靠性增强）
    # ========================================================================

    def _is_model_healthy(self, model: str) -> bool:
        """检查模型是否健康"""
        # 如果没有记录过失败，默认健康
        if model not in self.model_health:
            return True
        return self.model_health[model]

    def report_model_failure(self, model: str, error: str | None = None):
        """报告模型调用失败

        Args:
            model: 失败的模型名称
            error: 错误信息（可选）

        """
        # Fast Fail: 验证model参数
        if not model or not isinstance(model, str):
            raise ValueError(f"Invalid model identifier: {model}. Expected non-empty string")

        # 增加失败计数
        self.model_failure_count[model] = self.model_failure_count.get(model, 0) + 1
        failure_count = self.model_failure_count[model]

        self.logger.warning(
            f"Model {model} failed {failure_count} time(s). Error: {error or 'Unknown error'}",
        )

        # 如果失败次数达到阈值，标记为不健康
        if failure_count >= self.health_check_threshold:
            self.model_health[model] = False
            self.logger.error(
                f"Model {model} marked as unhealthy due to {failure_count} consecutive failures",
            )

    def report_model_success(self, model: str):
        """报告模型调用成功，重置失败计数

        Args:
            model: 成功的模型名称

        """
        # 如果模型之前被标记为不健康，恢复健康状态
        if model in self.model_health and not self.model_health[model]:
            self.logger.info(f"Model {model} recovered, marking as healthy")

        self.model_health[model] = True
        self.model_failure_count[model] = 0

    def get_model_health_status(self) -> dict[str, dict[str, Any]]:
        """获取所有模型的健康状态

        Returns:
            健康状态字典 {model: {"healthy": bool, "failures": int}}

        """
        status = {}
        for model in set(list(self.model_health.keys()) + list(self.model_failure_count.keys())):
            status[model] = {
                "healthy": self.model_health.get(model, True),
                "failures": self.model_failure_count.get(model, 0),
            }
        return status


# ============================================================================
# 配置加载器
# ============================================================================


def load_model_router_config(workspace_path: Path | str) -> RouterConfig:
    """从工作区加载模型路由配置

    优先级：
    1. .dawei/model_router.json (工作区配置)
    2. ~/.dawei/model_router.json (用户配置)
    3. /etc/dawei/model_router.json (系统配置)
    4. 默认配置

    Args:
        workspace_path: 工作区路径（Path 或 str）

    Returns:
        路由配置实例

    """
    # 确保 workspace_path 是 Path 对象
    workspace_path = Path(workspace_path) if isinstance(workspace_path, str) else workspace_path

    config_paths = [
        workspace_path / ".dawei" / "model_router.json",
        Path(get_dawei_home()) / "model_router.json",
        Path("/etc/dawei/model_router.json"),
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with Path(config_path).open(encoding="utf-8") as f:
                    data = json.load(f)

                router_config = RouterConfig.from_dict(data.get("modelRouter", {}))

                logging.info(f"Loaded model router config from {config_path}")
                return router_config
            except (FileNotFoundError, PermissionError) as e:
                # File access errors - log and try next config path
                logging.warning(f"Cannot access config file {config_path}: {e}")
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                # Invalid config format - log and try next config path
                logging.warning(f"Invalid config format in {config_path}: {e}")
            except Exception as e:
                # Unexpected errors - log with full trace and try next config path
                logging.warning(
                    f"Unexpected error loading config from {config_path}: {e}",
                    exc_info=True,
                )

    # 返回默认配置
    logging.info("Using default model router configuration")
    return RouterConfig(default="deepseek-chat")


def load_cost_config(config_path: Path | None = None) -> dict[str, ModelCost]:
    """加载模型定价配置

    Args:
        config_path: 配置文件路径（可选）

    Returns:
        模型定价字典

    """
    if config_path and config_path.exists():
        try:
            with Path(config_path).open(encoding="utf-8") as f:
                data = json.load(f)

            costs = {}
            for model, cost_info in data.get("modelCosts", {}).items():
                costs[model] = ModelCost(
                    input=cost_info["input"],
                    output=cost_info["output"],
                    unit=cost_info.get("unit", "per_1m_tokens"),
                )

            logging.info(f"Loaded cost config from {config_path}")
            return costs
        except (FileNotFoundError, PermissionError) as e:
            # File access errors - log and use defaults
            logging.warning(f"Cannot access cost config file {config_path}: {e}")
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Invalid config format - log and use defaults
            logging.warning(f"Invalid cost config format in {config_path}: {e}")
        except Exception as e:
            # Unexpected errors - log with full trace and use defaults
            logging.warning(
                f"Unexpected error loading cost config from {config_path}: {e}",
                exc_info=True,
            )

    # 返回默认定价（2026年集市价格）
    return {
        "deepseek-chat": ModelCost(input=0.14, output=0.28),
        "deepseek-reasoner": ModelCost(input=1.0, output=2.0),
        "google/gemini-2.5-pro": ModelCost(input=1.25, output=5.0),
        "anthropic/claude-opus-4": ModelCost(input=15.0, output=75.0),
        "anthropic/claude-sonnet-4": ModelCost(input=3.0, output=15.0),
        "openai/gpt-4": ModelCost(input=5.0, output=15.0),
        "openai/gpt-4-turbo": ModelCost(input=0.5, output=1.5),
        "local/qwen2.5-coder:7b": ModelCost(input=0.0, output=0.0),
        "local/deepseek-coder": ModelCost(input=0.0, output=0.0),
    }
