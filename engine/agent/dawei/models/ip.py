"""
IP 任务上下文与工作区状态模型。

为 IP 模块提供统一的任务上下文 Schema 和工作区状态定义，
用于 IPWorkspaceService 的创建/恢复/查询接口。
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Optional, List


# ============================================================================
# Enum
# ============================================================================

class IPTaskPhase(StrEnum):
    """IP 任务执行阶段"""
    IDLE = "idle"
    PLAN = "plan"
    DO = "do"
    CHECK = "check"
    ACT = "act"
    COMPLETED = "completed"
    ERROR = "error"


# ============================================================================
# IpTaskContext — IP 任务提交时的上下文信息
# ============================================================================

@dataclass
class IpTaskContext:
    """IP 任务提交时的上下文信息

    用于 POST /api/ip/workspace/{module}/create 请求体。
    包含任务所需的所有元数据和可选跨模块引用。
    """

    # ─── 必填 ───
    module: str
    """模块标识: ip-idea-vault, ip-disclosure, ip-draft, etc."""

    task_type: str
    """任务类型: evaluate, generate_disclosure, generate_draft, etc."""

    # ─── 可选：跨模块上下文传递 ───
    parent_module: Optional[str] = None
    """来源模块标识"""

    parent_task_id: Optional[str] = None
    """来源任务 ID"""

    parent_workspace_id: Optional[str] = None
    """来源工作区 ID（用于继承文件）"""

    # ─── 可选：任务参数 ───
    file_ids: List[str] = field(default_factory=list)
    """上传文件 ID 列表"""

    reference_ids: List[str] = field(default_factory=list)
    """引用数据 ID 列表"""

    language: str = "zh-CN"
    """目标语言"""

    jurisdiction: str = "CN"
    """法律辖区: CN, US, EP, JP, KR"""

    # ─── 可选：撰写策略 ───
    draft_strategy: Optional[str] = None
    """撰写策略: broad, defensive, precise"""

    target_country: Optional[str] = None
    """目标国家: CN, US, EP, JP, KR"""

    # ─── 可选：用户输入 ───
    description: Optional[str] = None
    """用户提交的技术描述/经营范围等"""

    trademark_name: Optional[str] = None
    """商标名称 (M8)"""

    business_scope: Optional[str] = None
    """经营范围 (M8)"""

    # ─── 可选：文件继承 ───
    inherit_files: List[str] = field(default_factory=list)
    """从 parent workspace 继承的文件名列表"""

    # ─── 可选：用户偏好 ───
    user_preferences: dict = field(default_factory=dict)
    """用户偏好字典"""


# ============================================================================
# WorkspaceStatus — 工作区运行状态
# ============================================================================

@dataclass
class WorkspaceStatus:
    """工作区状态，用于 API 响应"""

    workspace_id: str
    """工作区 ID"""

    name: str
    """工作区名称"""

    display_name: str
    """工作区显示名称"""

    module: str
    """关联的 IP 模块标识"""

    lifecycle: str
    """生命周期: persistent, temporary"""

    status: str
    """运行状态: creating, running, paused, completed, error"""

    phase: Optional[str] = None
    """当前 PDCA 阶段: plan, do, check, act"""

    progress_current: Optional[int] = None
    """当前进度"""

    progress_total: Optional[int] = None
    """总进度"""

    created_at: Optional[str] = None
    """创建时间 ISO"""

    last_activity_at: Optional[str] = None
    """最后活动时间 ISO"""

    expires_at: Optional[str] = None
    """过期时间 ISO (仅临时工作区)"""

    file_count: int = 0
    """工作区文件数"""

    task_count: int = 0
    """关联任务数"""

    parent_workspace_id: Optional[str] = None
    """来源工作区 ID"""

    parent_module: Optional[str] = None
    """来源模块标识"""

    checkpoint: Optional[dict] = None
    """当前断点信息: {phase, description, timestamp}"""

    resources: Optional[dict] = None
    """已安装资源: {skills: [...], mcps: [...], knowledges: [...]}"""

    metadata: Optional[dict] = None
    """额外元数据 (模块特定信息)"""


# ============================================================================
# ResumableTask — 可恢复任务摘要
# ============================================================================

@dataclass
class ResumableTask:
    """可恢复的 IP 任务摘要，用于 GET /api/ip/workspace/resumable"""

    workspace_id: str
    name: str
    module: str
    phase: Optional[str] = None
    progress_current: int = 0
    progress_total: int = 0
    last_activity_at: Optional[str] = None
    expires_at: Optional[str] = None


# ============================================================================
# InheritRequest — 文件继承请求
# ============================================================================

@dataclass
class InheritRequest:
    """文件继承请求体，用于 POST /api/ip/workspace/{workspace_id}/inherit"""

    parent_workspace_id: str
    """来源工作区 ID"""

    file_names: List[str] = field(default_factory=list)
    """要继承的文件名列表（空列表表示继承全部）"""
