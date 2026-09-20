# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Configuration utility functions"""

from typing import List, Dict, Any

from dawei.agentic.agent_config import AgentMode, Config
from dawei.core.errors import ValidationError


def validate_and_create_config(config: Config | Dict[str, Any] | None = None) -> Config:
    """Validate and create a Config object from various input types.

    Args:
        config: Configuration object, dictionary, or None

    Returns:
        Validated Config object

    Raises:
        ValidationError: If config type is invalid

    """
    if config is None:
        config_obj = Config()
    elif isinstance(config, dict):
        config_obj = Config(config)
    elif isinstance(config, Config):
        config_obj = config
    else:
        raise ValidationError("config", str(type(config)), "must be None, dict, or Config")

    # Apply environment variable overrides
    config_obj.apply_env_overrides()

    return config_obj


def workspace_config_to_agent_dict(ws_config: Any) -> Dict[str, Any]:
    """把 WorkspaceConfig（config.json 的 Pydantic 模型）转为 Config 可接受的扁平 dict。

    桥接「UI 写入的 config.json」与「运行时读取的 AgentConfig」：把各段字段映射为
    ``Config.update_from_dict`` 认识的键名（处理命名错位，如 ``skills.enabled``→
    ``enable_skills``）。纯函数、无 I/O，便于单测。

    ``mode`` 仅在属于 ``AgentMode``（orchestrator/pdca）时才输出；PDCA 子模式（plan/do…）
    会被跳过，避免触发 ``AgentMode(value)`` ValueError 崩溃 Agent 创建——真实运行模式由
    chat handler 的 ``_sync_mode_to_agent`` 每消息覆盖。

    注：``auto_approve_tools`` 仅做 round-trip（运行时无消费点，真审批 gate 是安全策略
    ApprovalGate）。
    """
    result: Dict[str, Any] = {}
    try:
        agent = ws_config.agent
        mode_val = str(getattr(agent, "mode", "")).lower()
        try:
            AgentMode(mode_val)
            result["mode"] = mode_val
        except ValueError:
            pass  # 非 AgentMode 子集 → 跳过，留给运行时 _sync_mode_to_agent
        result["plan_mode_confirm_required"] = agent.plan_mode_confirm_required
        result["enable_auto_mode_switch"] = agent.enable_auto_mode_switch
        result["auto_approve_tools"] = agent.auto_approve_tools
        result["max_concurrent_subtasks"] = agent.max_concurrent_subtasks

        result["enable_skills"] = ws_config.skills.enabled  # 命名错位

        ckpt = ws_config.checkpoint
        result["checkpoint_interval"] = ckpt.checkpoint_interval
        result["max_checkpoints"] = ckpt.max_checkpoints
        result["enable_checkpoint_compression"] = ckpt.enable_compression  # 命名错位
        result["auto_create_enabled"] = ckpt.auto_create_enabled
        result["min_interval_minutes"] = ckpt.min_interval_minutes
        result["max_checkpoints_per_task"] = ckpt.max_checkpoints_per_task
        result["validation_enabled"] = ckpt.validation_enabled

        comp = ws_config.compression
        result["compression_threshold"] = comp.compression_threshold
        result["max_context_tokens"] = comp.max_tokens  # 命名错位

        log_cfg = ws_config.logging
        result["log_level"] = log_cfg.level  # 命名错位
        result["enable_performance_logging"] = log_cfg.enable_performance_logging

        result["tool_execution_timeout"] = ws_config.tools.default_timeout  # 命名错位
    except AttributeError:
        return {}
    return result
