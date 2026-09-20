# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""IP 工作区模板管理器 — 根据模板 YAML 初始化 IP 工作区

参照 ComplianceTemplateManager 代码模式，使用 storage 接口统一文件操作。
负责从 DAWEI_HOME/data/templates/ip/ 加载模板，并初始化工作区目录结构、
写入 Agent 指令、复制 IP 清单、填充用户表单数据。

如果 DAWEI_HOME 中没有模板，自动从 _MARKET_DATA_ROOT 同步（fallback）。
"""

import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _resolve_template_root() -> Path:
    """IP 模板根目录 — 直接从 sidecar 打包数据加载。

    PyInstaller --onefile 将数据解压到 sys._MEIPASS，
    __file__ 也指向该目录下的模块路径，所以 parent.parent 得到 dawei/ 包根。
    """
    return Path(__file__).parent.parent / "data" / "templates" / "ip"


def _resolve_market_data_root() -> Path:
    """nn-market-resources/data/ 根目录（自动安装时的源）。"""
    return Path(os.environ.get(
        "MARKET_DATA_ROOT",
        str(Path(__file__).resolve().parents[4] / "nn-market-resources" / "data"),
    ))


class IPTemplateManager:
    """IP 工作区模板管理器

    与 ComplianceTemplateManager 代码结构完全对称。
    单一路径解析：{category}/{slug}.yaml，无 fallback。
    索引中 slug 不含模块前缀，与文件名一致。

    改进：路径通过构造参数注入，方便测试和部署切换。
    无 fallback：DAWEI_HOME/data/templates/ip/ 是唯一来源。
    """

    def __init__(
        self,
        *,
        template_base: Path | None = None,
        checklist_base: Path | None = None,
        knowledge_base: Path | None = None,
    ):
        root = _resolve_template_root()
        self.template_base = template_base or root / "workspace"
        self.checklist_base = checklist_base or root / "checklists"
        self.knowledge_base = knowledge_base or root / "knowledge"
        self._index: dict[str, Any] = {}
        self._load_index()

    def _load_index(self) -> None:
        """加载模板索引。如果索引不存在，尝试从 market data 自动安装。"""
        index_path = self.template_base / "index.yaml"
        if index_path.exists():
            with open(index_path, encoding="utf-8") as f:
                self._index = yaml.safe_load(f) or {}
        else:
            logger.warning("IP template index not found: %s, trying auto-install", index_path)
            if self._try_auto_install():
                if index_path.exists():
                    with open(index_path, encoding="utf-8") as f:
                        self._index = yaml.safe_load(f) or {}

    def list_templates(self, module_slug: str | None = None, lang: str = "zh") -> list[dict[str, Any]]:
        """列出可用模板，可按 module 过滤

        Args:
            module_slug: IP 模块 slug，如 "ip-draft"。为 None 时返回全部。
            lang: 语言代码 "zh" 或 "en"。当 "en" 时使用 i18n.en 字段替换 name/description。

        Returns:
            模板基本元数据列表，含 category 字段。
        """
        result: list[dict[str, Any]] = []
        for category, templates in self._index.get("templates", {}).items():
            if module_slug is None or category == module_slug:
                for t in templates:
                    entry = {**t, "category": category}
                    # i18n override
                    if lang != "zh":
                        i18n = t.get("i18n", {}).get(lang, {})
                        if i18n.get("name"):
                            entry["name"] = i18n["name"]
                        if i18n.get("description"):
                            entry["description"] = i18n["description"]
                    result.append(entry)
        return result

    def get_version(self, template_slug: str) -> str | None:
        """获取模板版本号

        先从索引条目读取 version 字段，若缺失则加载完整 YAML 获取。

        Returns:
            版本字符串（如 "1.0"），或 None。
        """
        # Fast path: index entry may have version
        for _category, templates in self._index.get("templates", {}).items():
            for t in templates:
                if t["slug"] == template_slug:
                    if "version" in t:
                        return t["version"]
                    break
        # Slow path: load full YAML
        tmpl = self.load_template(template_slug)
        if tmpl:
            return tmpl.get("template", tmpl).get("version")
        return None

    def list_versions(self, module_slug: str | None = None) -> list[dict[str, str]]:
        """列出模板版本信息

        Returns:
            列表 [{"slug": ..., "version": ..., "category": ...}, ...]
        """
        result: list[dict[str, str]] = []
        for category, templates in self._index.get("templates", {}).items():
            if module_slug is None or category == module_slug:
                for t in templates:
                    slug = t["slug"]
                    version = t.get("version") or self.get_version(slug) or "unknown"
                    result.append({"slug": slug, "version": version, "category": category})
        return result

    def load_template(self, template_slug: str) -> dict[str, Any] | None:
        """加载模板完整定义。

        先从 DAWEI_HOME 查找，未找到时触发自动安装整个 domain。

        Args:
            template_slug: 模板 slug，如 "patent-draft", "cn-invention"

        Returns:
            模板完整 YAML 定义，或 None。
        """
        result = self._find_in_index(template_slug)
        if result is not None:
            return result

        # 未找到 → 自动安装 domain 级别模板
        if self._try_auto_install():
            self._load_index()
            return self._find_in_index(template_slug)

        return None

    def get_installed_version(self, template_id: str) -> str | None:
        """从 .installed.yaml 读取已安装版本。

        Args:
            template_id: 完整 template ID，如 "template/ip/ip-application/cn-invention"
        """
        installed_path = _resolve_template_root() / ".installed.yaml"
        if not installed_path.exists():
            return None
        with open(installed_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("installed", {}).get(template_id, {}).get("version")

    def _find_in_index(self, template_slug: str) -> dict[str, Any] | None:
        """从已加载的索引中查找模板"""
        for category, templates in self._index.get("templates", {}).items():
            for t in templates:
                if t["slug"] == template_slug:
                    yaml_path = self.template_base / category / f"{template_slug}.yaml"
                    if yaml_path.exists():
                        with open(yaml_path, encoding="utf-8") as f:
                            return yaml.safe_load(f)
        return None

    def _try_auto_install(self) -> bool:
        """从 _MARKET_DATA_ROOT 安装整个 IP domain 的模板到 DAWEI_HOME。

        当 DAWEI_HOME 中没有模板时作为 fallback 自动触发。
        安装范围：workspace/index.yaml + workspace/{category}/ + checklists/ + knowledge/

        返回 True 表示安装成功。
        """
        from dawei import get_dawei_home

        data_root = _resolve_market_data_root()
        src_root = data_root / "ip-templates"
        if not src_root.exists():
            logger.warning("Auto-install: ip-templates source not found at %s", src_root)
            return False

        dawei_home = get_dawei_home()
        templates_root = dawei_home / "data" / "templates" / "ip"

        # 1. 安装 workspace/ 目录（含 index.yaml + 所有 category）
        src_workspace = src_root / "workspace"
        if src_workspace.exists():
            for item in src_workspace.iterdir():
                if item.is_dir():
                    category = item.name
                    dest_dir = templates_root / "workspace"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    tmp = dest_dir / f".tmp_{category}"
                    final = dest_dir / category
                    try:
                        if tmp.exists():
                            shutil.rmtree(tmp)
                        shutil.copytree(item, tmp)
                        if final.exists():
                            shutil.rmtree(final)
                        tmp.rename(final)
                    except Exception as e:
                        if tmp.exists():
                            shutil.rmtree(tmp)
                        logger.error("Auto-install category %s failed: %s", category, e)
                elif item.name == "index.yaml":
                    dest_dir = templates_root / "workspace"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest_dir / "index.yaml")

        # 2. 安装 checklists/
        src_checklists = src_root / "checklists"
        if src_checklists.exists():
            dst = templates_root / "checklists"
            dst.mkdir(parents=True, exist_ok=True)
            for f in src_checklists.iterdir():
                if f.is_file():
                    shutil.copy2(f, dst / f.name)

        # 3. 安装 knowledge/
        src_knowledge = src_root / "knowledge"
        if src_knowledge.exists():
            dst = templates_root / "knowledge"
            dst.mkdir(parents=True, exist_ok=True)
            for item in src_knowledge.iterdir():
                target = dst / item.name
                if item.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)

        logger.info("Auto-installed IP templates to %s", templates_root)
        return (templates_root / "workspace" / "index.yaml").exists()

    async def init_workspace_from_template(
        self,
        workspace_path: str,
        template_slug: str,
        form_data: dict[str, Any],
        storage: Any,
        inherit_from: list[str] | None = None,
    ) -> dict[str, Any]:
        """根据 IP 模板初始化工作区

        编排方法：调用各子步骤，失败时回滚已创建的内容。

        Args:
            workspace_path: 工作区根路径
            template_slug: 模板 slug（如 "patent-draft", "cn-invention"）
            form_data: 用户表单数据
            storage: Storage 接口实例
            inherit_from: 上游 workspace_id 列表

        Returns:
            操作结果: {"dirs_created": [...], "files_written": [...]}
        """
        template = self.load_template(template_slug)
        if not template:
            raise ValueError(f"IP template not found: {template_slug}")

        t = template.get("template", template)
        ws_root = Path(workspace_path)
        result: dict[str, Any] = {"dirs_created": [], "files_written": []}

        try:
            # 1. 创建目录结构
            await self._create_dirs(t, storage, result)

            # 2. 写入初始文件 (README 等)
            await self._write_initial_files(t, storage, result)

            # 3. 批量写入表单数据 → task_params.json（一次 I/O）
            await self._write_task_params(t, form_data, storage, result)

            # 4. 复制 IP 清单
            await self._copy_checklists(t, storage, result)

            # 5. 复制知识参考（统一 storage 接口）
            await self._copy_knowledge(t, ws_root, storage, result)

            # 6. 文件继承——含过期检查和错误提示
            await self._inherit_upstream(inherit_from, ws_root, storage, result)

            # 7. 渲染并写入 Agent 指令
            instructions = self._render_instructions(t, form_data, workspace_path)
            await storage.write_file("input/AGENT_INSTRUCTIONS.md", instructions)
            result["files_written"].append("input/AGENT_INSTRUCTIONS.md")

            # 8. 写入工作区元数据
            await self._write_workspace_meta(
                t, form_data, ws_root, storage, result,
                template_slug, inherit_from,
            )

            logger.info(
                "IP workspace initialized from template '%s': dirs=%d, files=%d",
                template_slug,
                len(result["dirs_created"]),
                len(result["files_written"]),
            )
        except Exception:
            # 回滚：清理已创建的目录
            logger.exception(
                "Failed to init workspace from template '%s', rolling back",
                template_slug,
            )
            for d in reversed(result["dirs_created"]):
                try:
                    dir_path = ws_root / d
                    if dir_path.exists():
                        shutil.rmtree(dir_path, ignore_errors=True)
                except Exception:
                    pass
            raise

        return result

    # ── 子步骤方法 ──────────────────────────────────────────

    async def _create_dirs(
        self,
        template: dict[str, Any],
        storage: Any,
        result: dict[str, Any],
    ) -> None:
        """步骤 1：创建模板定义的目录结构"""
        for entry in template.get("workspace_structure", []):
            dir_name = entry.get("dir", "")
            if dir_name:
                await storage.create_directory(dir_name)
                result["dirs_created"].append(dir_name)

    async def _write_initial_files(
        self,
        template: dict[str, Any],
        storage: Any,
        result: dict[str, Any],
    ) -> None:
        """步骤 2：写入模板中的初始文件"""
        for entry in template.get("workspace_structure", []):
            for file_def in entry.get("initial_files", []):
                file_path = file_def.get("path", "")
                content = file_def.get("content", "")
                if file_path and content:
                    await storage.write_file(file_path, content)
                    result["files_written"].append(file_path)

    async def _write_task_params(
        self,
        template: dict[str, Any],
        form_data: dict[str, Any],
        storage: Any,
        result: dict[str, Any],
    ) -> None:
        """步骤 3：在内存中合并所有表单字段后一次性写入 task_params.json

        改进：避免 N×2 次文件 I/O（原方案每个字段 read+write）。
        """
        task_params: dict[str, Any] = {}

        # Required fields — 必须写入
        for field in template.get("data_requirements", {}).get("required", []):
            key = field.get("key", "")
            if not key:
                continue
            if key in form_data:
                task_params[key] = form_data[key]
            elif "default" in field:
                task_params[key] = field["default"]

        # Optional fields — 仅在有值时写入
        for field in template.get("data_requirements", {}).get("optional", []):
            key = field.get("key", "")
            if not key:
                continue
            if key in form_data and form_data[key]:
                task_params[key] = form_data[key]

        if task_params:
            await storage.write_file(
                "input/task_params.json",
                json.dumps(task_params, ensure_ascii=False, indent=2),
            )
            result["files_written"].append("input/task_params.json")

    async def _copy_checklists(
        self,
        template: dict[str, Any],
        storage: Any,
        result: dict[str, Any],
    ) -> None:
        """步骤 4：复制关联的 IP 清单 JSON"""
        await storage.create_directory("input/checklists")
        for ref in template.get("checklists", []):
            slug = ref["ref"].replace("checklist/", "")
            checklist_file = self.checklist_base / f"{slug}.json"
            if checklist_file.exists():
                content = checklist_file.read_text(encoding="utf-8")
                await storage.write_file(f"input/checklists/{slug}.json", content)
                result["files_written"].append(f"input/checklists/{slug}.json")
            else:
                logger.warning("IP checklist not found: %s", checklist_file)

    async def _copy_knowledge(
        self,
        template: dict[str, Any],
        ws_root: Path,
        storage: Any,
        result: dict[str, Any],
    ) -> None:
        """步骤 5：复制知识参考材料

        统一使用 storage 接口写入，不再混用 Path.mkdir() + storage.write_file()。
        """
        await storage.create_directory("references")
        for ref in template.get("knowledge_refs", []):
            slug = ref.replace("knowledge/", "")
            knowledge_dir = self.knowledge_base / slug
            if not knowledge_dir.exists():
                logger.warning("IP knowledge dir not found: %s", knowledge_dir)
                continue
            for kf in knowledge_dir.rglob("*"):
                if kf.is_file():
                    rel = kf.relative_to(knowledge_dir)
                    storage_rel = f"references/{slug}/{rel}"
                    content = kf.read_text(encoding="utf-8")
                    await storage.write_file(storage_rel, content)
                    result["files_written"].append(storage_rel)

    async def _inherit_upstream(
        self,
        inherit_from: list[str] | None,
        ws_root: Path,
        storage: Any,
        result: dict[str, Any],
    ) -> None:
        """步骤 6：从上游工作区继承文件"""
        if not inherit_from:
            return

        from dawei.workspace.ip_workspace_service import ip_workspace_service

        for upstream_ws_id in inherit_from:
            try:
                parent_path = await ip_workspace_service._resolve_workspace_path(
                    upstream_ws_id,
                )
                if parent_path is None:
                    logger.warning(
                        "Upstream workspace not found (possibly expired): %s",
                        upstream_ws_id,
                    )
                    continue

                src_files_dir = parent_path / ".dawei" / "files"
                if not src_files_dir.exists():
                    logger.warning(
                        "Upstream workspace has no files: %s",
                        upstream_ws_id,
                    )
                    continue

                # 复制到 input/inherited/
                await storage.create_directory("input/inherited")
                count = 0
                for src in src_files_dir.rglob("*"):
                    if src.is_file():
                        rel = src.relative_to(src_files_dir)
                        dest = f"input/inherited/{rel}"
                        content = src.read_text(encoding="utf-8")
                        await storage.write_file(dest, content)
                        result["files_written"].append(dest)
                        count += 1

                logger.info(
                    "Inherited %d files from upstream workspace %s",
                    count,
                    upstream_ws_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to inherit from workspace %s: %s",
                    upstream_ws_id,
                    e,
                )

    async def _write_workspace_meta(
        self,
        template: dict[str, Any],
        form_data: dict[str, Any],
        ws_root: Path,
        storage: Any,
        result: dict[str, Any],
        template_slug: str,
        inherit_from: list[str] | None,
    ) -> None:
        """步骤 8：写入工作区元数据 workspace.json

        元数据在 init 阶段写入初始状态，后续由 Agent 执行器更新 status/phase 字段。
        """
        meta: dict[str, Any] = {
            "module": template.get("module", ""),
            "template_slug": template_slug,
            "template_name": template.get("name", ""),
            "target_country": template.get("target_country", ""),
            "invention_title": form_data.get("invention_title", ""),
            "status": "initialized",
            "phase": "init",
            "inherit_from": inherit_from or [],
            "created_at": datetime.now(UTC).isoformat(),
            "deliverables": [
                d["file"] for d in template.get("deliverables", [])
            ],
        }
        await storage.write_file(
            "workspace.json",
            json.dumps(meta, ensure_ascii=False, indent=2),
        )
        result["files_written"].append("workspace.json")

    # ── 渲染 ──────────────────────────────────────────

    def _render_instructions(
        self,
        template: dict[str, Any],
        form_data: dict[str, Any],
        ws_path: str,
    ) -> str:
        """渲染 Agent 指令模板，填入变量和清单表格"""
        text = template.get("agent_instructions", "")

        # 构建清单表格(含文件路径列,防止 Agent 用裸文件名 read_file)
        rows: list[str] = []
        for ref in template.get("checklists", []):
            slug = ref["ref"].replace("checklist/", "")
            checklist_file = self.checklist_base / f"{slug}.json"
            if checklist_file.exists():
                try:
                    data = json.loads(checklist_file.read_text(encoding="utf-8"))
                    name = data.get("name", slug)
                    desc = data.get("description", "")
                    count = len(data.get("items", []))
                    rows.append(
                        f"| {name} | {desc} | {count} 项 | "
                        f"`input/checklists/{slug}.json` |"
                    )
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Failed to parse checklist %s: %s", slug, e)

        # 路径提示必须显式——Agent 看到 heading 后第一眼就是路径规则,
        # 避免它用 `patentability-check.json` 这类裸文件名触发 File not found。
        table = (
            "清单文件位于工作区 `input/checklists/` 目录下。"
            "读取清单必须使用完整相对路径 `input/checklists/<文件名>.json`"
            "(例如 `input/checklists/patentability-check.json`)"
            "——使用裸文件名会触发 `File not found` 错误。\n\n"
            "| 清单名称 | 说明 | 检查项数 | 文件路径 |\n"
            "|---------|------|---------|---------|\n"
        )
        table += "\n".join(rows) if rows else "| — | 无关联清单 | 0 | — |"

        variables = {
            "template_name": template.get("name", "IP 任务"),
            "checklist_table": table,
            "workspace_path": ws_path,
        }
        for k, v in variables.items():
            text = text.replace("{" + k + "}", v)

        return text


# ============================================================================
# 全局单例
# ============================================================================

ip_template_manager = IPTemplateManager()
