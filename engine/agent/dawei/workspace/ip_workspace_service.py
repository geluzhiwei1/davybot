"""
IP 工作区服务。

为 IP 八大模块提供工作区创建/恢复/清理的一站式服务。
封装 TempWorkspaceManager、ResourceInstaller、WorkspacePersistenceManager，
添加 IP 资源安装逻辑和文件继承能力。

核心原则：
    Task-as-Workspace — 每个 IP LLM 任务 = 一个临时工作区。
    任务生命周期与工作区生命周期绑定。
"""

import json
import logging
import shutil
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Optional, cast

from dawei.models.ip import (
    InheritRequest,
    IpTaskContext,
    IPTaskPhase,
    ResumableTask,
    WorkspaceStatus,
)
from dawei.workspace.models import WorkspaceLifecycle, WorkspaceType
from dawei.workspace.resource_installer import install_team
from dawei.workspace.temp_workspace_manager import temp_workspace_manager

logger = logging.getLogger(__name__)

# ============================================================================
# IP 模块资源清单
# 映射 module slug → { skills, agents, mcps, knowledges }
# 与 nn-market-resources/data/teams/team_zh-CN.yaml 中的定义保持同步
# ============================================================================

IP_MODULE_RESOURCES: dict[str, dict[str, list[str]]] = {
    "ip-idea-vault": {
        "skills": ["skill/docx", "skill/pdf", "skill/code2patent"],
        "agents": ["agent/patent-team"],
        "mcps": ["mcp/paper-search"],
        "knowledges": ["knowledge/patent-law"],
    },
    "ip-disclosure": {
        "skills": ["skill/docx", "skill/pdf", "skill/code2patent"],
        "agents": ["agent/patent-team"],
        "mcps": ["mcp/paper-search"],
        "knowledges": ["knowledge/patent-law"],
    },
    "ip-draft": {
        "skills": ["skill/docx", "skill/pdf", "skill/code2patent", "skill/patent-analysis"],
        "agents": ["agent/patent-team"],
        "mcps": ["mcp/paper-search", "mcp/nn-kb-searcher"],
        "knowledges": ["knowledge/patent-law", "knowledge/patent-examination-guidelines"],
    },
    "ip-filing": {
        "skills": ["skill/docx", "skill/pdf"],
        "agents": ["agent/patent-team"],
        "mcps": ["mcp/paper-search"],
        "knowledges": ["knowledge/patent-law"],
    },
    "ip-oa-reply": {
        "skills": ["skill/docx", "skill/pdf", "skill/patent-analysis"],
        "agents": ["agent/patent-team"],
        "mcps": ["mcp/paper-search", "mcp/nn-kb-searcher"],
        "knowledges": ["knowledge/patent-law", "knowledge/patent-examination-guidelines"],
    },
    "ip-reverse-detection": {
        "skills": [
            "skill/docx",
            "skill/pdf",
            "skill/patent-analysis",
            "skill/patent-claim-mapper",
            "skill/trademark-assistant",
        ],
        "agents": ["agent/patent-team"],
        "mcps": ["mcp/paper-search", "mcp/sanctions-knowledge"],
        "knowledges": ["knowledge/patent-law", "knowledge/trademark-law"],
    },
    "ip-portfolio": {
        "skills": ["skill/docx", "skill/pdf", "skill/patent-analysis"],
        "agents": ["agent/patent-team"],
        "mcps": ["mcp/paper-search"],
        "knowledges": ["knowledge/patent-law", "knowledge/trademark-law"],
    },
    "ip-trademark": {
        "skills": ["skill/trademark-assistant", "skill/docx", "skill/pdf"],
        "agents": ["agent/patent-team"],
        "mcps": ["mcp/paper-search"],
        "knowledges": ["knowledge/trademark-law"],
    },
    "ip-application": {
        "skills": [
            "skill/docx",
            "skill/pdf",
            "skill/patent-analysis",
            "skill/code2patent",
        ],
        "agents": ["agent/patent-team"],
        "mcps": ["mcp/paper-search", "mcp/nn-kb-searcher"],
        "knowledges": [
            "knowledge/patent-law",
            "knowledge/patent-examination-guidelines",
            "knowledge/us-patent-law",
        ],
    },
}

# IP 工作区默认 TTL（比普通临时工作区的 24h 更长）
DEFAULT_IP_WORKSPACE_TTL_H = 72


class IPWorkspaceService:
    """IP 工作区一站式服务。

    封装 TempWorkspaceManager + ResourceInstaller，提供 IP 模块专用的
    工作区创建/恢复/状态查询/清理能力。
    """

    _instance: Optional["IPWorkspaceService"] = None

    def __init__(self) -> None:
        self._module_resources = IP_MODULE_RESOURCES

    @classmethod
    def get_instance(cls) -> "IPWorkspaceService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─── Resource helpers ──────────────────────────────────────

    def get_module_resources(self, module: str) -> dict[str, list[str]]:
        """获取指定 IP 模块的资源清单。"""
        return self._module_resources.get(module, {})

    # ─── Workspace lifecycle ───────────────────────────────────

    async def create_ip_workspace(
        self,
        module: str,
        task_context: IpTaskContext,
        lifecycle: str = WorkspaceLifecycle.TEMPORARY.value,
        *,
        template_slug: str | None = None,
        template_form_data: dict[str, Any] | None = None,
        inherit_from: list[str] | None = None,
        market_token: str | None = None,
    ) -> WorkspaceStatus:
        """创建 IP 任务专用工作区。

        1. 调用 TempWorkspaceManager 创建临时工作区目录
        2. 安装模块专属 resources (skills, mcps, knowledges)
        3. 如果有 parent_workspace_id，继承指定文件
        4. 如果有 template_slug，使用 IPTemplateManager 初始化工作区结构
        5. 返回 WorkspaceStatus

        Args:
            module: IP 模块标识 (e.g., "ip-draft")
            task_context: 任务上下文
            lifecycle: 工作区生命周期 ("temporary" | "persistent")
            template_slug: 模板 slug（如 "patent-draft"），启用模板化工作区
            template_form_data: 模板表单数据
            inherit_from: 上游 workspace_id 列表

        Returns:
            WorkspaceStatus
        """
        # 生成工作区名称
        workspace_name = self._generate_workspace_name(module)
        display_name = self._generate_display_name(module, task_context)

        # 确定工作区类型：直接使用 module slug 作为 workspace_type
        # 例如 "ip-idea-vault", "ip-disclosure", 等等（对应 WorkspaceType 枚举值）
        ws_type = module

        # 创建临时工作区
        ws_info = await temp_workspace_manager.create_temp_workspace(
            name=workspace_name,
            display_name=display_name,
            workspace_type=ws_type,
        )

        workspace_id = ws_info["id"]
        workspace_path = Path(ws_info["path"])

        # 安装模块资源
        try:
            resources = await self._install_module_resources(
                workspace_path, module, token=market_token
            )
        except Exception as e:
            logger.warning(f"Failed to install resources for workspace {workspace_id}: {e}")
            resources = {"skills": [], "mcps": [], "knowledges": [], "agents": []}

        # 文件继承
        if task_context.parent_workspace_id:
            await self._inherit_files(
                target_workspace_path=workspace_path,
                parent_workspace_id=task_context.parent_workspace_id,
                file_names=task_context.inherit_files,
            )

        # 模板结构初始化（Path B: 模板驱动工作区）
        if template_slug:
            try:
                from dawei.workspace.ip_template import IPTemplateManager

                # 获取 storage 接口 — 根目录指向 .dawei/files/
                storage = self._get_workspace_storage(workspace_path)
                manager = IPTemplateManager()
                template_result = await manager.init_workspace_from_template(
                    workspace_path=str(workspace_path),
                    template_slug=template_slug,
                    form_data=template_form_data or {},
                    storage=storage,
                    inherit_from=inherit_from,
                )
                logger.info(
                    "Template '%s' initialized: dirs=%d, files=%d",
                    template_slug,
                    len(template_result.get("dirs_created", [])),
                    len(template_result.get("files_written", [])),
                )
            except Exception as e:
                logger.warning(
                    "Failed to init workspace from template '%s': %s",
                    template_slug,
                    e,
                )

        # 写入 IP metadata 到 workspace.json
        await self._write_ip_metadata(
            workspace_path, module, task_context, lifecycle, resources
        )

        now = datetime.now(UTC)

        return WorkspaceStatus(
            workspace_id=workspace_id,
            name=workspace_name,
            display_name=display_name,
            module=module,
            lifecycle=lifecycle,
            status="creating",
            phase=IPTaskPhase.IDLE.value,
            created_at=now.isoformat(),
            last_activity_at=now.isoformat(),
            expires_at=(
                self._compute_expiry(now, lifecycle) if lifecycle == WorkspaceLifecycle.TEMPORARY.value else None
            ),
            file_count=0,
            task_count=0,
            parent_workspace_id=task_context.parent_workspace_id,
            parent_module=task_context.parent_module,
            resources=resources,
            metadata={
                "task_type": task_context.task_type,
                "language": task_context.language,
                "jurisdiction": task_context.jurisdiction,
                "draft_strategy": task_context.draft_strategy,
                "target_country": task_context.target_country,
            },
        )

    async def get_workspace_status(self, workspace_id: str) -> WorkspaceStatus:
        """查询工作区运行状态。

        通过检查工作区目录和 .dawei 元数据来确定当前状态。
        """
        ws_path = await self._resolve_workspace_path(workspace_id)
        if ws_path is None:
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")

        dawei_path = ws_path / ".dawei"
        workspace_json = dawei_path / "workspace.json"

        # 默认状态
        status: dict[str, Any] = {
            "workspace_id": workspace_id,
            "name": workspace_id,
            "display_name": workspace_id,
            "module": "unknown",
            "lifecycle": WorkspaceLifecycle.TEMPORARY.value,
            "status": "idle",
            "phase": None,
            "file_count": 0,
            "task_count": 0,
        }

        # 读取 workspace.json
        if workspace_json.exists():
            import json
            try:
                with workspace_json.open() as f:
                    ws_config = json.load(f)
                # 提取 IP metadata
                ip_meta = ws_config.get("ip_metadata", {})
                status["module"] = ip_meta.get("module", "unknown")
                status["lifecycle"] = ws_config.get("lifecycle", WorkspaceLifecycle.TEMPORARY.value)
                status["name"] = ws_config.get("name", workspace_id)
                status["display_name"] = ws_config.get("display_name", workspace_id)
                status["parent_workspace_id"] = ip_meta.get("parent_workspace_id")
                status["parent_module"] = ip_meta.get("parent_module")
                status["resources"] = ip_meta.get("resources")
                status["metadata"] = ip_meta.get("metadata")
                status["created_at"] = ip_meta.get("created_at")
                status["expires_at"] = ip_meta.get("expires_at")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to read workspace.json for {workspace_id}: {e}")

        # 检测 checkpoint
        checkpoints_dir = dawei_path / "checkpoints"
        if checkpoints_dir.exists():
            cps = sorted(checkpoints_dir.glob("*.json"), key=lambda p: p.name, reverse=True)
            if cps:
                try:
                    import json
                    with cps[0].open() as f:
                        cp = json.load(f)
                    status["checkpoint"] = {
                        "phase": cp.get("phase"),
                        "description": cp.get("description"),
                        "timestamp": cp.get("timestamp"),
                    }
                    status["status"] = "paused"
                    status["phase"] = cp.get("phase")
                    status["progress_current"] = cp.get("progress_current", 0)
                    status["progress_total"] = cp.get("progress_total", 0)
                except Exception as e:
                    logger.warning(f"Failed to read checkpoint for {workspace_id}: {e}")

        # 检测任务图
        task_graphs_dir = dawei_path / "task_graphs"
        if task_graphs_dir.exists():
            graphs = list(task_graphs_dir.glob("*.json"))
            status["task_count"] = len(graphs)

        # 检测文件
        files_dir = dawei_path / "files"
        if files_dir.exists():
            status["file_count"] = len(list(files_dir.rglob("*")))

        # 最后活动时间
        try:
            mtime = ws_path.stat().st_mtime
            status["last_activity_at"] = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
        except OSError:
            pass

        return WorkspaceStatus(**status)

    async def resume_workspace(self, workspace_id: str) -> WorkspaceStatus:
        """检查工作区状态，判断是否可以恢复。

        返回 WorkspaceStatus；如果工作区不存在或已过期则抛出异常。
        """
        status = await self.get_workspace_status(workspace_id)

        if status.status == "error":
            return status

        # 检查是否过期
        if status.lifecycle == WorkspaceLifecycle.TEMPORARY.value and status.expires_at:
            try:
                expires = datetime.fromisoformat(status.expires_at)
                if datetime.now(UTC) > expires:
                    raise RuntimeError(f"工作区已过期: {workspace_id} (expired at {status.expires_at})")
            except ValueError:
                pass

        return status

    async def cleanup_workspace(self, workspace_id: str, force: bool = False) -> bool:
        """清理工作区。

        Args:
            workspace_id: 工作区 ID
            force: True 时跳过活跃检查直接删除

        Returns:
            是否清理成功
        """
        if not force:
            # 检查是否活跃（有未完成任务）
            status = await self.get_workspace_status(workspace_id)
            if status.status in ("running", "creating"):
                raise RuntimeError(
                    f"Cannot cleanup active workspace {workspace_id} (status={status.status}). Use force=True to override."
                )

        ws_path = await self._resolve_workspace_path(workspace_id)
        if ws_path is None:
            return False

        try:
            shutil.rmtree(ws_path)
            logger.info(f"Cleaned up IP workspace: {workspace_id}")
            return True
        except OSError as e:
            logger.exception(f"Failed to cleanup workspace {workspace_id}: {e}")
            return False

    async def inherit_files(
        self,
        workspace_id: str,
        request: InheritRequest,
    ) -> list[str]:
        """从父工作区继承文件到目标工作区。

        Args:
            workspace_id: 目标工作区 ID
            request: 继承请求（parent_workspace_id + file_names）

        Returns:
            继承成功的文件名列表
        """
        target_path = await self._resolve_workspace_path(workspace_id)
        if target_path is None:
            raise FileNotFoundError(f"Target workspace not found: {workspace_id}")

        parent_path = await self._resolve_workspace_path(request.parent_workspace_id)
        if parent_path is None:
            raise FileNotFoundError(f"Parent workspace not found: {request.parent_workspace_id}")

        return await self._inherit_files(
            target_workspace_path=target_path,
            parent_workspace_id=request.parent_workspace_id,
            file_names=request.file_names,
        )

    async def list_resumable_tasks(self) -> list[ResumableTask]:
        """获取所有可恢复的 IP 任务。

        遍历所有临时工作区目录，筛选出 IP 模块相关的可恢复任务。
        """
        resumable: list[ResumableTask] = []
        temp_base = temp_workspace_manager.get_temp_workspace_base_dir()

        if not temp_base.exists():
            return resumable

        for ws_dir in sorted(temp_base.iterdir()):
            if not ws_dir.is_dir():
                continue

            dawei_path = ws_dir / ".dawei"
            workspace_json = dawei_path / "workspace.json"

            if not workspace_json.exists():
                continue

            try:
                import json
                with workspace_json.open() as f:
                    ws_config = json.load(f)

                ip_meta = ws_config.get("ip_metadata")
                if not ip_meta:
                    continue

                # 检查是否有 checkpoint（可恢复的标志）
                checkpoints_dir = dawei_path / "checkpoints"
                if not checkpoints_dir.exists() or not list(checkpoints_dir.glob("*.json")):
                    continue

                cps = sorted(checkpoints_dir.glob("*.json"),
                             key=lambda p: p.name, reverse=True)
                if not cps:
                    continue

                with cps[0].open() as f:
                    cp = json.load(f)

                resumable.append(ResumableTask(
                    workspace_id=ws_dir.name,
                    name=ws_config.get("display_name", ws_dir.name),
                    module=ip_meta.get("module", "unknown"),
                    phase=cp.get("phase"),
                    progress_current=cp.get("progress_current", 0),
                    progress_total=cp.get("progress_total", 0),
                    last_activity_at=ip_meta.get("last_activity_at"),
                    expires_at=ip_meta.get("expires_at"),
                ))
            except Exception as e:
                logger.debug(f"Skipping workspace {ws_dir.name}: {e}")
                continue

        return resumable

    async def get_workspace_files(self, workspace_id: str) -> list[dict[str, Any]]:
        """获取工作区文件列表（扫描 workspace root，排除 .dawei 目录）。

        Returns:
            [{name, size, modified_at, path_relative}]
        """
        ws_path = await self._resolve_workspace_path(workspace_id)
        if ws_path is None:
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")

        if not ws_path.exists():
            return []

        result: list[dict[str, Any]] = []
        for f in sorted(ws_path.rglob("*")):
            # Skip .dawei internal directory
            if ".dawei" in f.parts:
                continue
            if f.is_file():
                stat = f.stat()
                result.append({
                    "name": f.name,
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                    "path_relative": str(f.relative_to(ws_path)),
                })

        return result

    # ─── Listing & aggregation ─────────────────────────────────

    async def list_ip_workspaces(
        self,
        workspace_type: str | None = None,
        search_query: str | None = None,
    ) -> list[dict[str, Any]]:
        """List IP workspaces from the unified workspace index.

        Reads from ~/.normnomos/workspaces.json (system index) — same source
        as GET /api/workspaces/list.  Filters to entries whose workspace_type
        starts with "ip-" to guarantee authoritative typing (no more name-prefix
        inference).

        Returns workspace dicts compatible with the frontend Workspace interface:
        {id, name, display_name, files, createdAt, workspaceType, workspace_category, metadata}.

        Args:
            workspace_type: Filter by exact workspace type slug (e.g. "ip-draft")
            search_query: Case-insensitive name search
        """
        from dawei.storage.storage_provider import StorageProvider

        result: list[dict[str, Any]] = []
        system_storage = StorageProvider.get_system_storage()

        try:
            content = await system_storage.read_file("workspaces.json")
            index_data = json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError):
            return result

        all_workspaces: list[dict[str, Any]] = index_data.get("workspaces", [])

        # Filter: IP workspaces only (authoritative workspace_type starts with "ip-")
        ip_entries = [
            w for w in all_workspaces
            if w.get("workspace_type", "").startswith("ip-")
        ]

        # Apply type filter
        if workspace_type:
            ip_entries = [w for w in ip_entries if w.get("workspace_type") == workspace_type]

        # Resolve paths and read workspace.json for detailed metadata
        for entry in ip_entries:
            ws_path_str = entry.get("path", "")
            ws_path = Path(ws_path_str) if ws_path_str else None
            if not ws_path or not ws_path.exists():
                continue

            ws_id = entry["id"]
            display_name = entry.get("display_name", entry.get("name", ws_path.name))
            ws_type = entry.get("workspace_type", "unknown")
            lifecycle = entry.get("lifecycle", "")

            # Filter by search query (on display_name)
            if search_query:
                if search_query.lower() not in display_name.lower():
                    continue

            # Read workspace.json for ip_metadata and detailed info
            workspace_json_path = ws_path / ".dawei" / "workspace.json"
            ws_config: dict[str, Any] = {}
            ip_meta: dict[str, Any] = {}
            try:
                if workspace_json_path.exists():
                    with workspace_json_path.open() as f:
                        ws_config = json.load(f)
                    ip_meta = ws_config.get("ip_metadata") or {}
            except (json.JSONDecodeError, OSError):
                pass

            # Files listing
            files: list[dict[str, Any]] = []
            files_dir = ws_path / ".dawei" / "files"
            if files_dir.exists():
                for fp in sorted(files_dir.rglob("*")):
                    if fp.is_file():
                        files.append({
                            "id": str(fp.relative_to(files_dir)),
                            "name": fp.name,
                            "kind": "file",
                        })

            # Compute createdAt as Unix timestamp (ms)
            raw_created_at = entry.get("created_at") or ws_config.get("created_at") or ""
            created_ts = 0
            try:
                if isinstance(raw_created_at, str) and raw_created_at:
                    created_dt = datetime.fromisoformat(raw_created_at.replace("Z", "+00:00"))
                    created_ts = int(created_dt.timestamp() * 1000)
            except (ValueError, TypeError, OSError):
                pass

            # Build standardized metadata from ip_metadata
            metadata: dict[str, Any] = {
                "phase": ip_meta.get("phase"),
                "task_type": ip_meta.get("task_type"),
                "status": ip_meta.get("status"),
                "score": ip_meta.get("score"),
                "parent_workspace_id": ip_meta.get("parent_workspace_id"),
                "inherited_files": ip_meta.get("inherited_files"),
            }

            # Merge extra metadata fields
            extra_meta = ip_meta.get("metadata", {})
            if isinstance(extra_meta, dict):
                metadata.update(extra_meta)

            # Alerts
            alerts = ip_meta.get("alerts")
            if alerts:
                metadata["alerts"] = alerts

            # Checkpoints
            checkpoints_dir = ws_path / ".dawei" / "checkpoints"
            if checkpoints_dir.exists():
                cps = sorted(checkpoints_dir.glob("*.json"), key=lambda p: p.name, reverse=True)
                if cps:
                    metadata["checkpoints"] = []
                    try:
                        for cp_path in cps:
                            with cp_path.open() as f:
                                metadata["checkpoints"].append(json.load(f))
                    except Exception:
                        pass

            # Derive status from phase
            if not metadata.get("status"):
                phase = metadata.get("phase")
                if phase in ("idle", None):
                    metadata["status"] = "idle"
                elif phase == "completed":
                    metadata["status"] = "completed"
                elif phase == "error":
                    metadata["status"] = "error"
                else:
                    metadata["status"] = "running"

            from dawei.workspace.models import WorkspaceType as WsTypeEnum

            result.append({
                "id": ws_id,
                "name": display_name,
                "display_name": display_name,
                "files": files,
                "createdAt": created_ts,
                "workspaceType": ws_type,
                "lifecycle": lifecycle,
                "workspace_category": WsTypeEnum(ws_type).category.value if ws_type.startswith("ip-") else "ip",
                "metadata": metadata,
            })

        return result

    async def get_portfolio_stats(self) -> dict[str, Any]:
        """Aggregate portfolio statistics across all IP workspaces.

        Returns counts broken down by module, patent/trademark statuses,
        health score, and recent activity.
        """
        all_workspaces = await self.list_ip_workspaces()

        # Module counts
        module_counts: dict[str, int] = {}
        patents_granted = 0
        patents_pending = 0
        trademarks_registered = 0
        trademarks_pending = 0
        health_scores: list[int] = []
        new_this_year = 0
        current_year = datetime.now(UTC).year

        for ws in all_workspaces:
            module = ws.get("workspaceType", "unknown")
            module_counts[module] = module_counts.get(module, 0) + 1

            metadata = ws.get("metadata", {})

            # Count patents
            if metadata.get("granted_patents"):
                patents_granted += int(metadata["granted_patents"])
            if metadata.get("pending_patents"):
                patents_pending += int(metadata["pending_patents"])

            # Count trademarks
            if metadata.get("registered_trademarks"):
                trademarks_registered += int(metadata["registered_trademarks"])
            if metadata.get("pending_trademarks"):
                trademarks_pending += int(metadata["pending_trademarks"])

            # Health score
            health = metadata.get("health_score")
            if health is not None:
                health_scores.append(int(health))

            # New this year
            created_ts = ws.get("createdAt", 0)
            if created_ts:
                try:
                    created_year = datetime.fromtimestamp(created_ts / 1000, tz=UTC).year
                    if created_year == current_year:
                        new_this_year += 1
                except (ValueError, OSError):
                    pass

        # Compute aggregate health score
        avg_health = round(sum(health_scores) / len(health_scores)) if health_scores else None

        # Module breakdown for frontend
        modules_list = [
            {"type": mod, "count": count}
            for mod, count in sorted(module_counts.items(), key=lambda x: -x[1])
        ]

        # Recent workspaces (top 10)
        recent = all_workspaces[:10]

        return {
            "total_workspaces": len(all_workspaces),
            "health_score": avg_health,
            "patents_granted": patents_granted,
            "patents_pending": patents_pending,
            "trademarks_registered": trademarks_registered,
            "trademarks_pending": trademarks_pending,
            "new_this_year": new_this_year,
            "modules": modules_list,
            "recent_workspaces": recent,
        }

    # ─── Private helpers ───────────────────────────────────────

    def _generate_workspace_name(self, module: str) -> str:
        """生成工作区名: e.g., ip-draft-a1b2c3d4"""
        import uuid
        short_id = uuid.uuid4().hex[:8]
        return f"{module}-{short_id}"

    def _generate_display_name(self, module: str, ctx: IpTaskContext) -> str:
        """生成人类可读的工作区显示名"""
        module_labels: dict[str, str] = {
            "ip-idea-vault": "创意评估",
            "ip-disclosure": "交底书",
            "ip-draft": "专利撰写",
            "ip-application": "专利申请",
            "ip-filing": "申请管理",
            "ip-oa-reply": "OA答复",
            "ip-reverse-detection": "反向侵权探测",
            "ip-portfolio": "资产分析",
            "ip-trademark": "商标注册",
        }
        base = module_labels.get(module, module)
        if ctx.trademark_name:
            return f"{ctx.trademark_name} · {base}"
        if ctx.description:
            short = ctx.description[:20] + ("..." if len(ctx.description) > 20 else "")
            return f"{short} · {base}"
        return f"{base}"

    def _get_workspace_storage(self, workspace_path: Path) -> Any:
        """获取工作区的 Storage 接口实例

        根目录指向 workspace_path，与通用工作区文件 API 统一存储位置。
        """
        from dawei.storage.storage_provider import StorageProvider

        return StorageProvider.get_workspace_storage(str(workspace_path))

    async def _install_module_resources(
        self, workspace_path: Path, module: str, token: str | None = None
    ) -> dict[str, Any]:
        """安装 IP 模块需要的资源到工作区。"""
        resources = self._module_resources.get(module)
        if not resources:
            logger.info(f"No resources defined for module: {module}")
            return {"skills": [], "mcps": [], "knowledges": [], "agents": []}

        results: dict[str, Any] = {"skills": [], "mcps": [], "knowledges": [], "agents": []}

        # 将 module slug 映射为 team id
        # 使用 install_team 一次性安装团队所有资源
        team_meta = {
            "skills": resources.get("skills", []),
            "agents": resources.get("agents", []),
            "mcps": resources.get("mcps", []),
            "knowledges": resources.get("knowledges", []),
        }

        try:
            install_team(
                workspace_path=workspace_path,
                team_id=module,
                team_meta=team_meta,
                results=results,
                token=token,
            )
            logger.info(f"Installed resources for {module}: {results}")
        except Exception as e:
            logger.exception(f"Failed to install resources for {module}: {e}")
            # Don't re-raise — allow workspace creation to continue
            results.setdefault("failed", []).append("team")

        # 半成品显性化：某类资源装失败时高声告警（结果随 results 返回调用方，
        # 便于前端提示）。静默吞掉会让工作区缺专家/缺工具而无人知晓。
        failed = results.get("failed") or []
        if failed:
            logger.warning(
                f"Workspace {workspace_path.name} ({module}) partially installed, "
                f"failed categories: {failed} — team.json declares more than what landed on disk"
            )

        return results

    async def _inherit_files(
        self,
        target_workspace_path: Path,
        parent_workspace_id: str,
        file_names: list[str],
    ) -> list[str]:
        """从父工作区复制文件到目标工作区的 .dawei/files/"""
        parent_path = await self._resolve_workspace_path(parent_workspace_id)
        if parent_path is None:
            logger.warning(f"Parent workspace not found for inheritance: {parent_workspace_id}")
            return []

        src_files_dir = parent_path / ".dawei" / "files"
        if not src_files_dir.exists():
            return []

        dst_files_dir = target_workspace_path / ".dawei" / "files"
        dst_files_dir.mkdir(parents=True, exist_ok=True)

        inherited: list[str] = []

        if file_names:
            # 复制指定的文件
            for fname in file_names:
                src = src_files_dir / fname
                if src.exists() and src.is_file():
                    dst = dst_files_dir / fname
                    shutil.copy2(src, dst)
                    inherited.append(fname)
        else:
            # 复制全部文件
            for src in src_files_dir.rglob("*"):
                if src.is_file():
                    rel = src.relative_to(src_files_dir)
                    dst = dst_files_dir / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    inherited.append(str(rel))

        logger.info(f"Inherited {len(inherited)} files from {parent_workspace_id}")
        return inherited

    async def _write_ip_metadata(
        self,
        workspace_path: Path,
        module: str,
        ctx: IpTaskContext,
        lifecycle: str,
        resources: dict[str, Any],
    ) -> None:
        """写入 IP 元数据到 workspace.json。"""
        import json

        workspace_json = workspace_path / ".dawei" / "workspace.json"
        config: dict[str, Any] = {}
        if workspace_json.exists():
            try:
                with workspace_json.open() as f:
                    config = json.load(f)
            except json.JSONDecodeError:
                pass

        now = datetime.now(UTC)
        config["ip_metadata"] = {
            "module": module,
            "task_type": ctx.task_type,
            "parent_workspace_id": ctx.parent_workspace_id,
            "parent_module": ctx.parent_module,
            "parent_task_id": ctx.parent_task_id,
            "language": ctx.language,
            "jurisdiction": ctx.jurisdiction,
            "resources": resources,
            "metadata": {
                "draft_strategy": ctx.draft_strategy,
                "target_country": ctx.target_country,
                "user_preferences": ctx.user_preferences,
            },
            "created_at": now.isoformat(),
            "last_activity_at": now.isoformat(),
            "expires_at": (
                self._compute_expiry(now, lifecycle) if lifecycle == WorkspaceLifecycle.TEMPORARY.value else None
            ),
        }

        with workspace_json.open("w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _compute_expiry(now: datetime, lifecycle: str) -> str:
        """计算工作区过期时间。"""
        from datetime import timedelta
        if lifecycle == WorkspaceLifecycle.TEMPORARY.value:
            return (now + timedelta(hours=DEFAULT_IP_WORKSPACE_TTL_H)).isoformat()
        return ""  # persistent 永不过期

    async def _resolve_workspace_path(self, workspace_id: str) -> Path | None:
        """解析工作区 ID 到文件系统路径。

        优先从统一系统索引 (workspaces.json) 获取路径，
        fallback 到 temp_workspaces 和用户工作区目录扫描。
        """
        from dawei.storage.storage_provider import StorageProvider

        system_storage = StorageProvider.get_system_storage()
        try:
            content = await system_storage.read_file("workspaces.json")
            index_data = json.loads(content)
            for w in index_data.get("workspaces", []):
                if w["id"] == workspace_id:
                    p = Path(w["path"])
                    if p.exists() and p.is_dir():
                        return p
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # Fallback to legacy temp_workspaces scan
        temp_base = temp_workspace_manager.get_temp_workspace_base_dir()
        path = temp_base / workspace_id
        if path.exists() and path.is_dir():
            return path

        # Fallback to user workspace directory scan
        from dawei import get_dawei_home
        user_ws = get_dawei_home() / "workspaces" / workspace_id
        if user_ws.exists() and user_ws.is_dir():
            return user_ws

        return None

    async def _count_active_ip_workspaces(self) -> int:
        """使用统一系统索引统计活跃 IP 工作区数量。"""
        from dawei.storage.storage_provider import StorageProvider

        system_storage = StorageProvider.get_system_storage()
        try:
            content = await system_storage.read_file("workspaces.json")
            index_data = json.loads(content)
            return sum(
                1 for w in index_data.get("workspaces", [])
                if w.get("workspace_type", "").startswith("ip-") and w.get("is_active", True)
            )
        except (FileNotFoundError, json.JSONDecodeError):
            return 0

    # ─── Checkpoint persistence ─────────────────────────────────

    async def save_checkpoint(
        self,
        workspace_id: str,
        phase: str,
        description: str = "",
        progress_current: int = 0,
        progress_total: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """保存 IP 任务 checkpoint 到工作区。

        写入 .dawei/checkpoints/checkpoint-{timestamp}.json，
        与 get_workspace_status 读取的格式一致。

        Args:
            workspace_id: 工作区 ID
            phase: PDCA 阶段 (idle/plan/do/check/act/completed/error)
            description: 当前步骤描述
            progress_current: 当前进度
            progress_total: 总进度
            metadata: 额外元数据

        Returns:
            checkpoint 摘要 dict
        """
        ws_path = await self._resolve_workspace_path(workspace_id)
        if ws_path is None:
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")

        checkpoints_dir = ws_path / ".dawei" / "checkpoints"
        checkpoints_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(UTC)
        timestamp = now.strftime("%Y%m%dT%H%M%S%f")  # microsecond precision for uniqueness
        checkpoint_id = f"checkpoint-{timestamp}"

        checkpoint_data: dict[str, Any] = {
            "id": checkpoint_id,
            "phase": phase,
            "description": description,
            "timestamp": now.isoformat(),
            "progress_current": progress_current,
            "progress_total": progress_total,
        }
        if metadata:
            checkpoint_data["metadata"] = metadata

        checkpoint_path = checkpoints_dir / f"{checkpoint_id}.json"
        with checkpoint_path.open("w") as f:
            json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

        # 更新 workspace.json 的 ip_metadata 记录最新活动
        await self._touch_workspace_activity(ws_path, now)

        logger.info(
            f"[IP] Checkpoint saved: ws={workspace_id} phase={phase} "
            f"progress={progress_current}/{progress_total}"
        )

        return {
            "id": checkpoint_id,
            "workspace_id": workspace_id,
            "phase": phase,
            "progress_current": progress_current,
            "progress_total": progress_total,
            "saved_at": now.isoformat(),
        }

    async def get_latest_checkpoint(self, workspace_id: str) -> dict[str, Any] | None:
        """获取工作区最新的 checkpoint。

        Returns:
            最新 checkpoint dict，如果不存在则返回 None
        """
        ws_path = await self._resolve_workspace_path(workspace_id)
        if ws_path is None:
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")

        checkpoints_dir = ws_path / ".dawei" / "checkpoints"
        if not checkpoints_dir.exists():
            return None

        cps = sorted(
            checkpoints_dir.glob("*.json"),
            key=lambda p: p.name,
            reverse=True,
        )
        if not cps:
            return None

        try:
            with cps[0].open() as f:
                return cast("dict[str, Any]", json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read checkpoint for {workspace_id}: {e}")
            return None

    async def list_checkpoints(self, workspace_id: str) -> list[dict[str, Any]]:
        """列出工作区所有 checkpoint（按时间降序）。

        Returns:
            checkpoint dict 列表
        """
        ws_path = await self._resolve_workspace_path(workspace_id)
        if ws_path is None:
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")

        checkpoints_dir = ws_path / ".dawei" / "checkpoints"
        if not checkpoints_dir.exists():
            return []

        result: list[dict[str, Any]] = []
        for cp_path in sorted(
            checkpoints_dir.glob("*.json"),
            key=lambda p: p.name,
            reverse=True,
        ):
            try:
                with cp_path.open() as f:
                    result.append(cast("dict[str, Any]", json.load(f)))
            except (json.JSONDecodeError, OSError):
                continue

        return result

    # ─── IP-specific cleanup ────────────────────────────────────

    async def cleanup_expired_ip_workspaces(self) -> int:
        """清理过期的 IP 临时工作区。

        扫描所有临时工作区目录，对具有 ip_metadata 的工作区使用
        IP 专用 72h TTL 判断是否过期。

        Returns:
            清理的工作区数量
        """
        temp_base = temp_workspace_manager.get_temp_workspace_base_dir()
        if not temp_base.exists():
            return 0

        now = datetime.now(UTC)
        cleaned = 0

        for ws_dir in sorted(temp_base.iterdir()):
            if not ws_dir.is_dir():
                continue

            workspace_json = ws_dir / ".dawei" / "workspace.json"
            if not workspace_json.exists():
                continue

            try:
                with workspace_json.open() as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            ip_meta = config.get("ip_metadata")
            if not ip_meta:
                continue  # 非 IP 工作区，跳过

            lifecycle = config.get("lifecycle", "")
            if lifecycle == WorkspaceLifecycle.PERSISTENT.value:
                continue  # 持久工作区不清理

            # 检查是否过期（IP 专用 72h TTL）
            expires_at_str = ip_meta.get("expires_at")
            if not expires_at_str:
                # 无过期时间的工作区，根据最后活动判断
                last_activity = ip_meta.get("last_activity_at", ip_meta.get("created_at", ""))
                if last_activity:
                    try:
                        last_dt = datetime.fromisoformat(last_activity)
                        delta = (now - last_dt).total_seconds()
                        if delta > DEFAULT_IP_WORKSPACE_TTL_H * 3600:
                            shutil.rmtree(ws_dir)
                            cleaned += 1
                            logger.info(f"[IP] Cleaned orphan IP workspace: {ws_dir.name} (inactive {delta/3600:.1f}h)")
                    except (ValueError, OSError):
                        pass
            else:
                try:
                    expires_dt = datetime.fromisoformat(expires_at_str)
                    if now > expires_dt:
                        shutil.rmtree(ws_dir)
                        cleaned += 1
                        logger.info(f"[IP] Cleaned expired IP workspace: {ws_dir.name}")
                except ValueError:
                    pass

        if cleaned:
            logger.info(f"[IP] Cleanup complete: removed {cleaned} expired IP workspace(s)")

        return cleaned

    # ─── Private helpers (continued) ────────────────────────────

    async def _touch_workspace_activity(self, ws_path: Path, now: datetime) -> None:
        """更新 workspace.json 中的最后活动时间。

        Args:
            ws_path: 工作区路径
            now: 当前时间
        """
        workspace_json = ws_path / ".dawei" / "workspace.json"
        if not workspace_json.exists():
            return

        try:
            with workspace_json.open() as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        if "ip_metadata" in config:
            config["ip_metadata"]["last_activity_at"] = now.isoformat()
            with workspace_json.open("w") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)


# ============================================================================
# 全局单例
# ============================================================================

ip_workspace_service = IPWorkspaceService()
