# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""上下文管理模块

使用 contextvars 提供线程安全的上下文变量管理，
用于在整个应用程序的异步任务中传递请求级别的上下文信息。
"""

from contextvars import ContextVar

# 定义上下文变量，并提供默认值
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)
message_id_var: ContextVar[str | None] = ContextVar("message_id", default=None)


# --- Getter Functions ---


def get_user_id() -> str | None:
    """获取当前上下文的 user_id"""
    return user_id_var.get()


def get_session_id() -> str | None:
    """获取当前上下文的 session_id"""
    return session_id_var.get()


def get_message_id() -> str | None:
    """获取当前上下文的 message_id"""
    return message_id_var.get()


def get_full_context() -> dict[str, str | None]:
    """获取所有上下文变量的字典"""
    return {
        "user_id": user_id_var.get(),
        "session_id": session_id_var.get(),
        "message_id": message_id_var.get(),
    }


# --- Setter Functions ---


def set_user_id(user_id: str) -> None:
    """设置当前上下文的 user_id"""
    user_id_var.set(user_id)


def set_session_id(session_id: str) -> None:
    """设置当前上下文的 session_id"""
    session_id_var.set(session_id)


def set_message_id(message_id: str) -> None:
    """设置当前上下文的 message_id"""
    message_id_var.set(message_id)


def set_local_context(
    user_id: str | None = None,
    session_id: str | None = None,
    message_id: str | None = None,
) -> None:
    """批量设置上下文变量。"""
    if user_id is not None:
        set_user_id(user_id)
    if session_id is not None:
        set_session_id(session_id)
    if message_id is not None:
        set_message_id(message_id)
