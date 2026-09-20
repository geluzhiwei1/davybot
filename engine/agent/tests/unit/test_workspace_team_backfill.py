"""
Unit tests: 工作区团队安装回填 + agent_modes 还原（核心用户路径回归守卫）。

背景（E2E 2026-09-03 gelu-research）：
  - bug#6：POST /api/workspaces/create 只带 team_id（team_meta=null）时，
    旧代码直接把 None 传给 install_resources_to_workspace —— install_team
    无 meta 即静默 no-op → 201 成功但零安装（「原创论文」入口工作区无团队、
    专家下拉暴露其他模块专家）。修复：与 /create-temp 一致，先从市场 API
    resolve_team_meta 回填。
  - agent→mode 归属：安装器把各 agent 的 customModes 拍平进
    mode_settings.json，归属只保留在 .dawei/agents/<slug>/modes.yaml；
    GET /api/workspaces/{id}/resources 新增 agent_modes 字段从该文件还原，
    供前端专家下拉按入口专家所属 agent 过滤。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ============================================================================
# 1. _load_agent_modes_map（.dawei/agents/<slug>/modes.yaml → agent_modes）
# ============================================================================


def _write_agent_modes(root, agent: str, slugs: list[str]) -> None:
    agents_dir = root / ".dawei" / "agents" / agent
    agents_dir.mkdir(parents=True, exist_ok=True)
    lines = ["customModes:"]
    for s in slugs:
        lines.append(f"  - slug: {s}")
        lines.append(f'    name: "{s} name"')
    (agents_dir / "modes.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestLoadAgentModesMap:
    def test_multiple_agents(self, tmp_path):
        from dawei.api.workspaces.core import _load_agent_modes_map

        _write_agent_modes(tmp_path, "paper-team", ["paper-orchestrator", "paper-methods"])
        _write_agent_modes(tmp_path, "review-team", ["review-orchestrator"])

        result = _load_agent_modes_map(tmp_path / ".dawei")
        assert result == {
            "paper-team": ["paper-orchestrator", "paper-methods"],
            "review-team": ["review-orchestrator"],
        }

    def test_no_agents_dir_returns_empty(self, tmp_path):
        from dawei.api.workspaces.core import _load_agent_modes_map

        (tmp_path / ".dawei").mkdir()
        assert _load_agent_modes_map(tmp_path / ".dawei") == {}

    def test_agent_without_modes_yaml_skipped(self, tmp_path):
        from dawei.api.workspaces.core import _load_agent_modes_map

        (tmp_path / ".dawei" / "agents" / "paper-team").mkdir(parents=True)
        assert _load_agent_modes_map(tmp_path / ".dawei") == {}

    def test_invalid_yaml_skipped_not_raised(self, tmp_path):
        from dawei.api.workspaces.core import _load_agent_modes_map

        agents_dir = tmp_path / ".dawei" / "agents" / "broken"
        agents_dir.mkdir(parents=True)
        (agents_dir / "modes.yaml").write_text("customModes: [unclosed", encoding="utf-8")
        assert _load_agent_modes_map(tmp_path / ".dawei") == {}

    def test_entries_without_slug_skipped(self, tmp_path):
        from dawei.api.workspaces.core import _load_agent_modes_map

        agents_dir = tmp_path / ".dawei" / "agents" / "partial"
        agents_dir.mkdir(parents=True)
        (agents_dir / "modes.yaml").write_text(
            'customModes:\n  - slug: ok-mode\n    name: "ok"\n  - name: "no slug"\n',
            encoding="utf-8",
        )
        assert _load_agent_modes_map(tmp_path / ".dawei") == {"partial": ["ok-mode"]}


# ============================================================================
# 2. /create team_meta 回填（bug#6 回归守卫）
# ============================================================================

_RESOLVED_META = {
    "skills": ["skill/paper-craft"],
    "agents": ["agent/paper-team"],
    "mcps": [],
    "knowledges": [],
}


def _fake_http_request() -> MagicMock:
    req = MagicMock()
    # 注意：Bearer 是故意畸形的 JWT —— 端点内的 market token 转发只透传原始串，
    # 身份提取（get_authenticated_*）在下方 _run_create 中统一 mock。
    req.headers = {"authorization": "Bearer test-token"}
    return req


async def _mock_user_id(request):
    return "test-user"


async def _mock_tenant_id(request):
    return "personal"


def _run_create(tmp_path, **request_kwargs):
    from dawei.api.workspaces.crud import CreateWorkspaceRequest, create_workspace

    body = {
        "display_name": "Original Paper",
        "description": "[Research] Original Paper",
        "path": str(tmp_path / "ws"),
        **request_kwargs,
    }
    # 2026-09-15 default_user 移除：/create 无有效登录直接 401，
    # 单测需注入已认证身份（真实 JWT 由 e2e 覆盖）。
    with patch("dawei.api.auth.get_authenticated_user_id", new=_mock_user_id), patch(
        "dawei.api.auth.get_authenticated_tenant_id", new=_mock_tenant_id
    ):
        return asyncio.run(create_workspace(CreateWorkspaceRequest(**body), _fake_http_request()))


class TestCreateWorkspaceTeamMetaBackfill:
    @patch("dawei.api.workspaces.crud._register_workspace_in_system_index", new_callable=AsyncMock)
    @patch("dawei.workspace.resource_installer.install_resources_to_workspace")
    @patch("dawei.workspace.resource_installer.resolve_team_meta")
    def test_team_id_only_backfills_team_meta(
        self, mock_resolve, mock_install, mock_register, tmp_path
    ):
        """bug#6 回归：只带 team_id（team_meta=null）→ 必须 resolve 回填后再安装。"""
        mock_resolve.return_value = dict(_RESOLVED_META)
        mock_install.return_value = {"team": {"installed": True}}

        response = _run_create(tmp_path, team_id="team/gelu-research", team_meta=None)

        assert response.success is True
        mock_resolve.assert_called_once_with("team/gelu-research", token="test-token")
        mock_install.assert_called_once()
        _, install_kwargs = mock_install.call_args
        # 核心断言：传入的是 resolve 出来的 meta，而不是 None（旧 bug）
        assert install_kwargs.get("team_meta") == _RESOLVED_META
        assert install_kwargs.get("team_id") == "team/gelu-research"

    @patch("dawei.api.workspaces.crud._register_workspace_in_system_index", new_callable=AsyncMock)
    @patch("dawei.workspace.resource_installer.install_resources_to_workspace")
    @patch("dawei.workspace.resource_installer.resolve_team_meta")
    def test_resolve_failure_does_not_crash_create(
        self, mock_resolve, mock_install, mock_register, tmp_path
    ):
        """市场 API 解析失败：安装跳过（team_meta=None），工作区创建仍成功（FAST FAIL 日志）。"""
        mock_resolve.side_effect = RuntimeError("market unreachable")
        mock_install.return_value = {}

        response = _run_create(tmp_path, team_id="team/gelu-research")

        assert response.success is True
        mock_install.assert_called_once()
        _, install_kwargs = mock_install.call_args
        assert install_kwargs.get("team_meta") is None

    @patch("dawei.api.workspaces.crud._register_workspace_in_system_index", new_callable=AsyncMock)
    @patch("dawei.workspace.resource_installer.install_resources_to_workspace")
    @patch("dawei.workspace.resource_installer.resolve_team_meta")
    def test_explicit_team_meta_skips_resolve(
        self, mock_resolve, mock_install, mock_register, tmp_path
    ):
        """调用方已带 team_meta（install-v2 链路）→ 不再请求市场。"""
        explicit = {
            "skills": [],
            "agents": ["agent/paper-team"],
            "mcps": [],
            "knowledges": [],
        }
        mock_install.return_value = {}
        response = _run_create(tmp_path, team_id="team/gelu-research", team_meta=explicit)

        assert response.success is True
        mock_resolve.assert_not_called()
        _, install_kwargs = mock_install.call_args
        assert install_kwargs.get("team_meta") == explicit

    @patch("dawei.api.workspaces.crud._register_workspace_in_system_index", new_callable=AsyncMock)
    @patch("dawei.workspace.resource_installer.install_resources_to_workspace")
    @patch("dawei.workspace.resource_installer.resolve_team_meta")
    def test_no_resources_no_install(
        self, mock_resolve, mock_install, mock_register, tmp_path
    ):
        """不带任何资源字段（普通工作区）→ 不 resolve、不安装。"""
        response = _run_create(tmp_path)

        assert response.success is True
        mock_resolve.assert_not_called()
        mock_install.assert_not_called()
