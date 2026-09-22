# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""server start --password 注入语义单元测试

- apply_server_password: 非空注入 / None-空不动环境变量（.env 预设仍生效）
- Click 参数注册: --password 存在、默认 None（缺省 = 无密码门，零行为变化）
- 与 access_gate 联动: 注入后 access_gate_active() 为 True（server 模式）
"""

import os

import pytest

from dawei.cli.commands.server import apply_server_password, server_cmd

pytestmark = pytest.mark.unit


# ==================== apply_server_password 语义 ====================


def test_apply_password_injects_env(monkeypatch):
    """非空 → 写入 DAWEI_SERVER_PASSWORD 并返回 True"""
    monkeypatch.delenv("DAWEI_SERVER_PASSWORD", raising=False)
    assert apply_server_password("s3cret") is True
    assert os.environ["DAWEI_SERVER_PASSWORD"] == "s3cret"


def test_apply_password_overrides_preset(monkeypatch):
    """CLI 显式参数优先级最高：覆盖 .env / 环境预设值"""
    monkeypatch.setenv("DAWEI_SERVER_PASSWORD", "from-env")
    assert apply_server_password("cli-wins") is True
    assert os.environ["DAWEI_SERVER_PASSWORD"] == "cli-wins"


def test_apply_password_none_keeps_preset(monkeypatch):
    """None（缺省）→ 不动环境变量：.env 已设的密码仍生效"""
    monkeypatch.setenv("DAWEI_SERVER_PASSWORD", "preset")
    assert apply_server_password(None) is False
    assert os.environ["DAWEI_SERVER_PASSWORD"] == "preset"


def test_apply_password_empty_keeps_unset(monkeypatch):
    """空串 → 视为未设置：不注入，环境无密码（默认免密码）"""
    monkeypatch.delenv("DAWEI_SERVER_PASSWORD", raising=False)
    assert apply_server_password("") is False
    assert "DAWEI_SERVER_PASSWORD" not in os.environ


# ==================== Click 参数注册 ====================


def test_start_command_has_password_option_default_none():
    """--password 已注册且默认 None（缺省启动 = 零行为变化）"""
    cmd = server_cmd.commands["start"]
    param = next((p for p in cmd.params if p.name == "password"), None)
    assert param is not None, "--password must be registered on `server start`"
    assert param.default is None


# ==================== 与 access_gate 联动 ====================


def test_password_injection_activates_gate(monkeypatch):
    """注入后（且无 auth 能力）密码门生效 —— CLI 参数到中间件的完整链路"""
    from dawei.api.access_gate import access_gate_active

    monkeypatch.delenv("DAWEI_SERVER_PASSWORD", raising=False)
    # access_gate 在函数内 `from dawei.runtime import get_capabilities` → 补丁打在源模块
    monkeypatch.setattr("dawei.runtime.get_capabilities", lambda: ["relay"])
    assert access_gate_active() is False  # 无密码 → 门关闭（默认路径）

    apply_server_password("gate-on")
    assert access_gate_active() is True  # 注入 → 门开启
