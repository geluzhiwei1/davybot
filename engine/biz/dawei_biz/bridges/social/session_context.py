"""社媒编辑会话上下文(设计:project/docs/PRD-social-flow/高级编辑和资产管理.md A.3/A.5)。

前端每条 WS 消息在 data 里携带 ``social_context = {content_id, tenant_id}``
(auth_token 走既有 local_context 通路);ChatHandler 把它写入本 ContextVar,
``social_*`` 工具运行时读取 —— 不进 LLM 上下文、不落盘、不作为工具参数。

上下文用"拉"不用"推":稿件在多轮中被手动修改,由 social_read_draft 实时拉取兜底。
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class SocialSessionContext:
    content_id: str = ""
    tenant_id: str = ""


_social_ctx_var: ContextVar[SocialSessionContext | None] = ContextVar(
    "social_session_context", default=None
)


def set_social_context(raw: object) -> SocialSessionContext | None:
    """绑定当前请求的社媒上下文(非 dict / 空值 → 清除)。返回绑定结果。"""
    if not isinstance(raw, dict):
        _social_ctx_var.set(None)
        return None
    ctx = SocialSessionContext(
        content_id=str(raw.get("content_id") or ""),
        tenant_id=str(raw.get("tenant_id") or ""),
    )
    bound = ctx if (ctx.content_id or ctx.tenant_id) else None
    _social_ctx_var.set(bound)
    return bound


def get_social_context() -> SocialSessionContext | None:
    """工具侧读取;未绑定返回 None(工具给"未关联稿件"人话提示)。"""
    return _social_ctx_var.get()


__all__ = ["SocialSessionContext", "set_social_context", "get_social_context"]
