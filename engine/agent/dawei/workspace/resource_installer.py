"""Market resource installer for workspaces.

Handles installing market resources (skills, agents, MCP servers,
knowledge bases, teams, templates) into a workspace.

Install strategy: skills/agents/MCP/templates are fetched from the market API
(``dawei.market.client.MarketClient``); knowledge resolves from the
nn-kb-searcher API.（本地 ``_MARKET_DATA_ROOT`` 直读路径已于 Phase 4 删除 — P10 死布局）

Workspace-side layout (unchanged, consumed at runtime):
  - skills   -> {workspace}/.dawei/skills/{slug}/
  - agents   -> {workspace}/.dawei/agents/{slug}/  (+ modes merged into mode_settings.json — 派生缓存，可从 agents/ 重建)
  - mcp      -> {workspace}/.dawei/configs/mcp.json  (+ mode_settings.json)
  - templates -> {DAWEI_HOME}/data/templates/{team}/checklists/{slug}.json
"""

import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

# nn-kb-searcher API fallback URL for knowledge base loading（E1: 无云端缺省）
_UNISEARCHER_API_URL = os.environ.get("UNISEARCHER_API_URL", "").rstrip("/")

from dawei import get_dawei_home

logger = logging.getLogger(__name__)


# ── Market API client (token-only) ────────────────────────────


def _get_market_client(token: str | None = None):
    """Get a ``MarketClient`` authenticated with the caller's user JWT.

    Market auth is token-only — the same ``JWT_SECRET`` is shared between
    local and prod, so the user's page-login JWT is forwarded as-is. A
    token is required; callers without one should not reach the Market API.
    """
    from dawei.market.client import MarketClient

    return MarketClient(token=token)


def _extract_zip(zip_path: Path, dest: Path) -> None:
    """Extract a zip into ``dest`` (created) with path-traversal guard."""
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            try:
                target.relative_to(dest_resolved)
            except ValueError:
                raise ValueError(f"unsafe zip entry: {member}")
        zf.extractall(dest)


def resolve_team_meta(
    team_id: str, client: "MarketClient | None" = None, token: str | None = None
) -> dict[str, Any] | None:
    """Resolve a team's referenced resource lists from the market API.

    Returns ``{skills, agents, mcps, knowledges}`` in ``{type}/{slug}`` form
    (as referenced by ``teams/*.yaml``), or ``None`` if the team can't be found.
    Used to backfill ``team_meta`` when the caller only supplies ``team_id``.
    """
    if not team_id:
        return None
    _, slug = _parse_resource_id(team_id)
    cli = client or _get_market_client(token)
    try:
        rid = cli.resolve("team", slug)
        if not rid:
            logger.warning(f"Team not found in market: {team_id}")
            return None
        em = (cli.get(rid) or {}).get("extra_metadata") or {}
    except Exception as e:
        logger.warning(f"Failed to resolve team meta for {team_id}: {e}")
        return None
    return {
        "skills": em.get("skills", []) or [],
        "agents": em.get("agents", []) or [],
        "mcps": em.get("mcps", []) or [],
        "knowledges": em.get("knowledges", []) or [],
    }




def _parse_resource_id(resource_id: str) -> tuple[str, str]:
    """Parse 'skill/docx' -> ('skill', 'docx')."""
    if "/" in resource_id:
        parts = resource_id.split("/", 1)
        return parts[0], parts[1]
    return resource_id, resource_id


# ── Version helpers ──────────────────────────────────────────


def _compare_versions(v1: str, v2: str) -> int:
    """Compare two semver strings. Returns >0 if v1 > v2."""
    def parse(v: str) -> tuple[int, ...]:
        parts = v.lstrip("v").split(".")
        return tuple(int(p) for p in parts[:3])

    p1, p2 = parse(v1), parse(v2)
    if p1 > p2:
        return 1
    elif p1 < p2:
        return -1
    return 0


def _update_installed_record(
    templates_root: Path, domain: str,
    template_id: str, version: str, category: str,
) -> None:
    """Update .installed.yaml with installed template version."""
    installed_path = templates_root / domain / ".installed.yaml"

    if installed_path.exists():
        with open(installed_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {"domain": domain, "updated_at": "", "installed": {}}

    data["installed"][template_id] = {
        "version": version,
        "installed_at": datetime.now(UTC).isoformat(),
        "category": category,
    }
    data["updated_at"] = datetime.now(UTC).isoformat()

    # Atomic write
    tmp = installed_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    tmp.rename(installed_path)


# ── Install functions ──────────────────────────────────────────


def install_mcp_servers(
    workspace_path: Path,
    mcp_ids: list[str],
    results: dict[str, Any],
    client: "MarketClient | None" = None,
    token: str | None = None,
) -> None:
    """Install MCP server configs into workspace mode_settings.json + configs/mcp.json.

    Server config is read from the market API (``extra_metadata`` of the mcp
    resource); written with merge semantics so other MCPs are preserved.
    """
    if not mcp_ids:
        return

    cli = client or _get_market_client(token)

    # Fetch each requested MCP's server config from the market API
    selected: dict[str, Any] = {}
    for mcp_id in mcp_ids:
        _, slug = _parse_resource_id(mcp_id)
        try:
            rid = cli.resolve("mcp", slug) or mcp_id
            info = cli.get(rid) or {}
            cfg = info.get("extra_metadata") or {}
        except Exception as e:
            logger.warning(f"Failed to fetch MCP '{slug}' from market: {e}")
            continue
        if cfg:
            selected[slug] = cfg
            logger.info(f"Selected MCP: {slug}")
        else:
            logger.warning(f"MCP server '{slug}' has no config in market data")

    if not selected:
        return

    # Merge into workspace mode_settings.json
    settings_path = workspace_path / ".dawei" / "mode_settings.json"
    existing = {"customModes": [], "mcpServers": {}}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing.setdefault("mcpServers", {}).update(selected)
    existing["_derived"] = True  # 派生缓存标记（Phase 4c；事实源 = configs/mcp.json + market）
    settings_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    results.setdefault("mcps", []).extend(selected.keys())
    logger.info(f"Installed {len(selected)} MCP servers to {settings_path}")

    # Also write to .dawei/configs/mcp.json for mcp_tool_manager.py runtime loading
    configs_dir = workspace_path / ".dawei" / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    mcp_runtime_path = configs_dir / "mcp.json"
    runtime_existing = {"mcpServers": {}}
    if mcp_runtime_path.exists():
        try:
            runtime_existing = json.loads(mcp_runtime_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    runtime_existing.setdefault("mcpServers", {}).update(selected)
    mcp_runtime_path.write_text(json.dumps(runtime_existing, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Also wrote MCP configs to {mcp_runtime_path} for runtime loading")


def _fetch_knowledge_from_api() -> list[dict[str, Any]] | None:
    """Try to fetch knowledge bases from nn-kb-searcher REST API.

    Returns list of knowledge entry dicts (same shape as knowledge.yaml) or None on failure.
    """
    if not _UNISEARCHER_API_URL:
        return None  # E1: 未配置 UNISEARCHER_API_URL → 知识市场拉取关闭
    import httpx

    url = f"{_UNISEARCHER_API_URL}/knowledge-bases"
    try:
        resp = httpx.get(url, timeout=5.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
        kbs = data.get("knowledge_bases", data.get("data", []))
        if not kbs:
            return None
        # Map nn-kb-searcher KB format to knowledge.yaml format
        entries = []
        for kb in kbs:
            entries.append({
                "slug": kb.get("id", ""),
                "name": kb.get("name", ""),
                "type": "knowledge_base",
                "description": kb.get("description", ""),
                "source": "nn-kb-searcher",
                "tags": kb.get("legal_domains", []),
                "enabled": True,
                "_api_source": True,
            })
        return entries
    except Exception:
        return None


def install_knowledge_bases(
    workspace_path: Path, knowledge_ids: list[str], results: dict[str, Any]
) -> None:
    """Install knowledge base entries into workspace config.

    Source: nn-kb-searcher REST API (:8014)。
    （本地 knowledge.yaml fallback 已随 _MARKET_DATA_ROOT 于 Phase 4 删除 — P10）
    """
    if not knowledge_ids:
        return

    all_knowledge = _fetch_knowledge_from_api()
    if all_knowledge:
        logger.info("Loaded %d knowledge bases from nn-kb-searcher API", len(all_knowledge))

    if not all_knowledge:
        logger.warning("No knowledge bases available (nn-kb-searcher API unreachable)")
        return

    # Filter to only requested knowledge bases
    requested_slugs = set()
    for kid in knowledge_ids:
        _, slug = _parse_resource_id(kid)
        requested_slugs.add(slug)

    selected = []
    for kb in all_knowledge:
        if kb.get("slug") in requested_slugs:
            selected.append(kb)

    if not selected:
        logger.warning(f"No matching knowledge bases found for: {knowledge_ids}")
        return

    # Write to workspace config
    kb_path = workspace_path / ".dawei" / "knowledge_bases.json"
    existing = []
    if kb_path.exists():
        try:
            existing = json.loads(kb_path.read_text())
        except Exception:
            pass

    existing_slugs = {kb.get("slug") for kb in existing}
    for kb in selected:
        if kb.get("slug") not in existing_slugs:
            existing.append(kb)

    kb_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    results.setdefault("knowledge", []).extend(kb.get("slug") for kb in selected)
    logger.info(f"Installed {len(selected)} knowledge bases to {kb_path}")


def install_skills(
    workspace_path: Path,
    skill_ids: list[str],
    results: dict[str, Any],
    client: "MarketClient | None" = None,
    token: str | None = None,
) -> None:
    """Install skill files into workspace .dawei/skills/ directory (from market API)."""
    if not skill_ids:
        return

    cli = client or _get_market_client(token)
    skills_dir = workspace_path / ".dawei" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    for skill_id in skill_ids:
        _, slug = _parse_resource_id(skill_id)
        rid = cli.resolve("skill", slug)
        if not rid:
            raise ValueError(f"Skill not found in market: {skill_id}")
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = cli.download_zip(rid, tmp)
            dest = skills_dir / slug
            if dest.exists():
                shutil.rmtree(dest)
            _extract_zip(Path(zip_path), dest)
        results.setdefault("skills", []).append(slug)
        logger.info(f"Installed skill: {slug}")


def install_agents(
    workspace_path: Path,
    agent_ids: list[str],
    results: dict[str, Any],
    client: "MarketClient | None" = None,
    token: str | None = None,
) -> None:
    """Install agent configs (modes.yaml + rules) into workspace (from market API).

    Team agents are indexed per-mode in the market; resolving by team name and
    downloading one mode yields the whole team source dir (modes.yaml + rules).
    """
    if not agent_ids:
        return

    cli = client or _get_market_client(token)
    agents_dir = workspace_path / ".dawei" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    for agent_id in agent_ids:
        # 【2026-09-14】单个 agent 失败只记录不中断同类其余 —— 与 install_team
        # 分类容错同哲学 (某市场条目坏了不应让整类归零, 半成品工作区放大器)。
        try:
            _, slug = _parse_resource_id(agent_id)
            rid = cli.resolve("agent", slug)
            if not rid:
                raise ValueError(f"Agent not found in market: {agent_id}")
            with tempfile.TemporaryDirectory() as tmp:
                zip_path = cli.download_zip(rid, tmp)
                dest = agents_dir / slug
                if dest.exists():
                    shutil.rmtree(dest)
                _extract_zip(Path(zip_path), dest)
            results.setdefault("agents", []).append(slug)
            logger.info(f"Installed agent: {slug}")
        except Exception as e:
            logger.exception(f"Failed to install agent {agent_id}: {e}")
            results.setdefault("failed", []).append(agent_id)

    # Merge agent modes into workspace mode_settings.json
    _merge_agent_modes(workspace_path, agents_dir)


def _merge_agent_modes(workspace_path: Path, agents_dir: Path) -> None:
    """Read all agents' modes.yaml and merge customModes into mode_settings.json.

    【Phase 4c】mode_settings.json 是**派生缓存**：事实源为 .dawei/agents/*/modes.yaml
    （ModeManager workspace 层 + ModeRegistry 读取），本文件可随时从 agents/ 重建，
    不再作为 API 列表的事实源（P5 双事实源消除）。写入时打 ``_derived: true`` 标记。
    """
    settings_path = workspace_path / ".dawei" / "mode_settings.json"
    existing = {"customModes": [], "mcpServers": {}}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    all_modes = existing.get("customModes", [])
    existing_slugs = {m.get("slug") for m in all_modes if isinstance(m, dict)}

    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue
        modes_file = agent_dir / "modes.yaml"
        if not modes_file.exists():
            continue
        try:
            with open(modes_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            for mode in data.get("customModes", []):
                if isinstance(mode, dict) and mode.get("slug") not in existing_slugs:
                    # Tag with source so the resources API can identify workspace-level custom modes
                    mode["source"] = "workspace"
                    all_modes.append(mode)
                    existing_slugs.add(mode.get("slug"))
        except Exception as e:
            logger.error(f"Failed to read modes from {modes_file}: {e}")

    existing["customModes"] = all_modes
    existing["_derived"] = True  # 派生缓存标记（Phase 4c）
    settings_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Merged agent modes into {settings_path}: {len(all_modes)} total modes")


def install_team(
    workspace_path: Path,
    team_id: str,
    team_meta: dict[str, Any] | None,
    results: dict[str, Any],
    client: "MarketClient | None" = None,
    token: str | None = None,
) -> None:
    """Install a team and all its referenced resources.

    team_meta comes from the market API and contains:
      skills: ["skill/docx", "skill/pdf"]
      agents: ["agent/patent-team"]
      mcps: ["mcp/paper-search-mcp"]
      knowledges: ["knowledge/us-sanctions-regulations"]
    """
    if not team_meta:
        logger.warning(f"No metadata for team: {team_id}")
        return

    _, slug = _parse_resource_id(team_id)

    # Write team info to workspace
    dawei_dir = workspace_path / ".dawei"
    dawei_dir.mkdir(parents=True, exist_ok=True)
    team_path = dawei_dir / "team.json"
    team_path.write_text(json.dumps({
        "team_id": team_id,
        "slug": slug,
        **team_meta,
    }, indent=2, ensure_ascii=False))

    results.setdefault("team", []).append(team_id)
    logger.info(f"Installed team: {team_id}")

    # Install all team-referenced resources. 各类资源独立安装：某类失败
    # （如市场缺某个 skill / 无 token）不得中断后续类别，否则会出现
    # team.json 已写但 agents 未装的半成品工作区（IP 模块曾因此丢专家）。
    team_skills = team_meta.get("skills", []) or []
    team_agents = team_meta.get("agents", []) or []
    team_mcps = team_meta.get("mcps", []) or []
    failures: list[str] = results.setdefault("failed", [])
    for label, installer, refs in (
        ("skills", install_skills, team_skills),
        ("agents", install_agents, team_agents),
        ("mcps", install_mcp_servers, team_mcps),
    ):
        if not refs:
            continue
        try:
            installer(workspace_path, refs, results, client=client, token=token)
        except Exception as e:
            logger.exception(f"Failed to install {label} for team {team_id}: {e}")
            failures.append(label)
    # 【2026-09-14 接通】team_meta.knowledges 原样存 team.json 但从不安装 ——
    # 与单装路径同病(前端"安装知识库"空转)。现走 install_knowledge_bases 写
    # .dawei/knowledge_bases.json, 由 agent.initialize 默认注入。
    team_knowledges = team_meta.get("knowledges", []) or []
    if team_knowledges:
        try:
            install_knowledge_bases(workspace_path, team_knowledges, results)
        except Exception as e:
            logger.exception(f"Failed to install knowledges for team {team_id}: {e}")
            failures.append("knowledges")


def install_templates(
    workspace_path: Path,
    template_ids: list[str],
    results: dict[str, Any],
    versions: dict[str, str] | None = None,
    client: "MarketClient | None" = None,
    token: str | None = None,
) -> None:
    """Install checklist templates from the market API to DAWEI_HOME/data/templates/.

    v3 market templates are checklist JSONs (slug/name/category/description/
    applicable_scenarios/items). ``/archive`` for a template resource returns
    the owning team's whole template set as flat ``{slug}.json`` files; we
    download once per resource id (cached per call) and write the requested
    slug to ``data/templates/{team}/checklists/{slug}.json`` — the layout
    consumed by ``api/checklists.py`` template endpoints.

    Args:
        workspace_path: Workspace path (unused; templates install to DAWEI_HOME).
        template_ids: ["template/supply-chain/supplier-annual-review", ...]
            (2-segment ``template/{slug-or-name}`` also accepted — resolved
            loosely against the market, like skills/agents).
        results: Dict to collect installation results.
        versions: Optional {"template/{team}/{slug}": "1.0.0"} version map.
        client/token: Market API client or caller JWT (see install_skills).
    """
    if not template_ids:
        return

    versions = versions or {}
    cli = client or _get_market_client(token)
    dawei_home = get_dawei_home()
    templates_root = dawei_home / "data" / "templates"

    zip_cache: dict[str, Path] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for tid in template_ids:
            _, slug_ref = _parse_resource_id(tid)  # "{team}/{slug}" or "{slug-or-name}"
            rid = cli.resolve("template", slug_ref.rsplit("/", 1)[-1])
            if not rid:
                raise ValueError(f"Template not found in market: {tid}")

            # The resolved id is authoritative: template/{team}/{slug}. The zip
            # is per-team, so the real slug may differ from what the caller
            # sent (e.g. 2-segment ids carrying a display name).
            rid_parts = rid.split("/")
            team = rid_parts[1] if len(rid_parts) >= 3 else "common"
            slug = rid_parts[-1]

            if rid not in zip_cache:
                zip_cache[rid] = cli.download_zip(rid, tmp)
            zip_path = zip_cache[rid]

            # Locate the member for this slug (flat "{slug}.json" in the zip)
            with zipfile.ZipFile(zip_path) as zf:
                member = next(
                    (n for n in zf.namelist() if n.endswith(f"/{slug}.json") or n == f"{slug}.json"),
                    None,
                )
                if not member:
                    raise ValueError(f"Template '{slug}' not found in archive for {tid}")
                try:
                    data = json.loads(zf.read(member).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as e:
                    raise ValueError(f"Invalid template JSON for {tid}: {e}") from e
                if not isinstance(data.get("items"), list):
                    raise ValueError(f"Template '{slug}' has no checklist items")

            # Atomic write to data/templates/{team}/checklists/{slug}.json
            dest_dir = templates_root / team / "checklists"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{slug}.json"
            tmp_file = dest_dir / f".tmp_{slug}.json"
            tmp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_file.replace(dest)

            version = versions.get(tid, versions.get(rid, "0.0.0"))
            category = str(data.get("category", "")) or slug
            _update_installed_record(templates_root, team, rid, version, category)

            results.setdefault("templates", []).append({
                "id": rid, "version": version, "status": "installed"
            })
            logger.info(f"Installed template: {rid} v{version}")


# ── Main entry point ───────────────────────────────────────────


def _precheck_market_access(
    client: "MarketClient",
    typed_ids: list[tuple[str, str]],
) -> None:
    """Resolve + can-access pre-check before installing (spec §16.4).

    Maps each requested id to its market resource id via ``resolve`` (the same
    visibility-filtered path the install itself uses). Unresolvable requests
    (invisible to this user) are checked by raw id — the server treats
    nonexistent and invisible identically. Any denied id raises
    ``PermissionError`` — the API layer turns that into 403 ``forbidden_team``.
    """
    rid_by_req: dict[str, str] = {}
    unresolved: list[str] = []
    for req_id, rtype in typed_ids:
        _, slug_ref = _parse_resource_id(req_id)
        try:
            rid = client.resolve(rtype, slug_ref.rsplit("/", 1)[-1])
        except Exception as e:
            logger.warning(f"precheck resolve failed for {req_id}: {e}")
            rid = None
        if rid:
            rid_by_req[req_id] = rid
        else:
            # Not in the visibility-filtered list: either invisible to this
            # user or nonexistent — the server treats both the same way.
            unresolved.append(req_id)

    if not rid_by_req and not unresolved:
        return

    # Batch-check resolved ids + raw unresolved ids in one call.
    to_check = sorted(set(rid_by_req.values()) | set(unresolved))
    verdict = client.can_access(to_check)
    denied = set(verdict.get("denied") or [])
    if not denied:
        return
    denied_reqs = sorted(
        [req for req, rid in rid_by_req.items() if rid in denied]
        + [req for req in unresolved if req in denied]
    )
    raise PermissionError(f"forbidden_team: no access to market resources: {denied_reqs}")


def install_resources_to_workspace(
    workspace_path: str,
    team_id: str | None = None,
    team_meta: dict[str, Any] | None = None,
    skill_ids: list[str] | None = None,
    agent_ids: list[str] | None = None,
    mcp_ids: list[str] | None = None,
    knowledge_ids: list[str] | None = None,
    template_ids: list[str] | None = None,
    versions: dict[str, str] | None = None,
    market_token: str | None = None,
) -> dict[str, Any]:
    """Install all requested market resources into a workspace.

    Skills/agents/MCP/templates are fetched from the market API (templates as
    checklist JSON via ``/archive``); a can-access pre-check fails fast on
    denied team-scope resources.

    Args:
        versions: Optional version map for templates, e.g. {"template/ip/.../slug": "1.0.0"}.
        market_token: Optional forwarded user JWT — when set, the market client
            authenticates as that user (no service-account login). Pass the
            incoming request's Bearer token so installs run under the page login.

    Returns:
        Dict with installed resource counts/names.
    """
    ws = Path(workspace_path)
    results: dict[str, Any] = {}
    # Per-request client bound to the caller's JWT (or None if no token).
    client = _get_market_client(market_token) if market_token else None

    # Pre-check access for individually selected resources (spec §16.4):
    # denied team-scope resources fail fast with 403 instead of mid-install errors.
    typed_ids: list[tuple[str, str]] = [
        *((rid, "skill") for rid in skill_ids or []),
        *((rid, "agent") for rid in agent_ids or []),
        *((rid, "mcp") for rid in mcp_ids or []),
        *((rid, "template") for rid in template_ids or []),
    ]
    if client and typed_ids:
        _precheck_market_access(client, typed_ids)

    # If team selected, install team first (which installs its referenced resources)
    if team_id:
        install_team(ws, team_id, team_meta, results, client=client, token=market_token)
    else:
        # Install individually selected resources
        if skill_ids:
            install_skills(ws, skill_ids, results, client=client, token=market_token)
        if agent_ids:
            install_agents(ws, agent_ids, results, client=client, token=market_token)
        if mcp_ids:
            install_mcp_servers(ws, mcp_ids, results, client=client, token=market_token)
        if template_ids:
            install_templates(ws, template_ids, results, versions=versions, client=client, token=market_token)
        # 【2026-09-14 接通】原注释称 "knowledge_ids are display-only labels; no install
        # needed" —— 与事实不符: install_knowledge_bases(写 .dawei/knowledge_bases.json)
        # 早已实现但全仓零调用方, 前端"安装知识库"实际是空转。现接回;
        # 下游读取方 = agent.initialize 默认注入工作区已安装 KB。
        if knowledge_ids:
            install_knowledge_bases(ws, knowledge_ids, results)

    # 【Phase 4c】装后失效 ModeRegistry 缓存：安装团队后同会话 switch_mode 即可见
    # （mode统一管理.md §7 验收 #7 —— 消除 300s/永久陈旧窗口；market.py 的
    # WorkspaceContext.invalidate_context 只清会话上下文，不清 mode 单例）
    from dawei.mode.registry import invalidate_registry

    invalidate_registry(workspace_path)

    logger.info(f"Resource install complete: {results}")
    return results
