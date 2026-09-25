# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""合规模板管理器 — 根据模板 YAML 初始化合规工作区

负责从 DAWEI_HOME/data/templates/compliance/ 加载模板，
并初始化工区目录结构、写入 Agent 指令、复制合规清单、填充用户表单数据。

如果 DAWEI_HOME 中没有模板，自动从 _MARKET_DATA_ROOT 同步（fallback）。
"""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _resolve_compliance_template_root() -> Path:
    """合规模板根目录 — 直接从 sidecar 打包数据加载。

    PyInstaller --onefile 将数据解压到 sys._MEIPASS，
    __file__ 也指向该目录下的模块路径，所以 parent.parent 得到 dawei/ 包根。
    """
    return Path(__file__).parent.parent / "templates" / "compliance"


def _resolve_checklist_base() -> Path:
    """合规检查清单根目录 — 直接从 sidecar 打包数据加载。"""
    return _resolve_compliance_template_root() / "checklists"


class ComplianceTemplateManager:
    """合规工作区模板管理器"""

    def __init__(self):
        self._index: dict[str, Any] = {}
        self._load_index()

    def _load_index(self) -> None:
        """加载模板索引。如果索引不存在，尝试从 market data 自动安装。"""
        template_base = _resolve_compliance_template_root() / "workspace"
        index_path = template_base / "index.yaml"
        if index_path.exists():
            with open(index_path, encoding="utf-8") as f:
                self._index = yaml.safe_load(f) or {}
        else:
            logger.warning("Compliance template index not found: %s, trying auto-install", index_path)
            if self._try_auto_install():
                if index_path.exists():
                    with open(index_path, encoding="utf-8") as f:
                        self._index = yaml.safe_load(f) or {}

    def list_templates(self, team_slug: str | None = None) -> list[dict[str, Any]]:
        """按团队列出可用模板

        Args:
            team_slug: 此处按 index.yaml 的 category（目录名）过滤，如 "supply-chain"。
                注意：与各模板 YAML 内的 ``team_slug``（用于 market team 解析）是两个不同概念。

        Returns:
            模板基本元数据列表，含 ``category`` 和 ``team_slug`` 字段。
        """
        result: list[dict[str, Any]] = []
        template_base = _resolve_compliance_template_root() / "workspace"
        for category, templates in self._index.get("templates", {}).items():
            if team_slug is None or category == team_slug:
                for t in templates:
                    item = {**t, "category": category}
                    # 读出模板 YAML 内的 team_slug（前端 launchChat 需要它构造正确的
                    # market team_id；缺失时由前端兜底到页面级 teamSlug）
                    yaml_path = template_base / category / f"{t['slug']}.yaml"
                    if yaml_path.exists():
                        try:
                            with open(yaml_path, encoding="utf-8") as f:
                                full = yaml.safe_load(f) or {}
                            tmpl_def = full.get("template") or {}
                            if tmpl_def.get("team_slug"):
                                item["team_slug"] = tmpl_def["team_slug"]
                        except Exception as e:
                            logger.warning("Failed to read team_slug from %s: %s", yaml_path, e)
                    result.append(item)
        return result

    def list_project_templates(self) -> list[dict[str, Any]]:
        """列出项目合规模板（纵向复合型模板）。

        项目合规模板以项目为中心，同时覆盖多个合规域，
        与单域分析模板（如 GDPR 评估、UFLPA 评估）不同。

        Returns:
            项目模板基本元数据列表，含 agent_teams 和 domains_covered。
        """
        project_index_path = (
            _resolve_compliance_template_root() / "workspace" / "project-templates" / "index.yaml"
        )
        if not project_index_path.exists():
            return []
        try:
            with open(project_index_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("templates", [])
        except Exception as e:
            logger.warning("Failed to load project templates index: %s", e)
            return []

    def load_project_template(self, slug: str) -> dict[str, Any] | None:
        """加载项目模板完整定义。

        Args:
            slug: 项目模板 slug，如 "project-overseas-epc"

        Returns:
            模板完整 YAML 定义，或 None。
        """
        yaml_path = (
            _resolve_compliance_template_root()
            / "workspace"
            / "project-templates"
            / f"{slug}.yaml"
        )
        if not yaml_path.exists():
            return None
        try:
            with open(yaml_path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning("Failed to load project template %s: %s", slug, e)
            return None

    def load_template(self, template_slug: str) -> dict[str, Any] | None:
        """加载模板完整定义。

        先从 DAWEI_HOME 查找，未找到时触发自动安装整个 domain。
        支持项目模板（slug 以 "project-" 开头）。

        Args:
            template_slug: 模板 slug，如 "supply-chain-uflpa" 或 "project-overseas-epc"

        Returns:
            模板完整 YAML 定义，或 None。
        """
        # 项目模板（纵向复合型）
        if template_slug.startswith("project-"):
            return self.load_project_template(template_slug)

        result = self._find_in_index(template_slug)
        if result is not None:
            return result

        # 未找到 → 自动安装 compliance domain 级别模板
        if self._try_auto_install():
            self._load_index()
            return self._find_in_index(template_slug)

        return None

    def get_installed_version(self, template_id: str) -> str | None:
        """从 .installed.yaml 读取已安装版本。

        Args:
            template_id: 完整 template ID，如 "template/compliance/supply-chain/supply-chain-uflpa"
        """
        installed_path = _resolve_compliance_template_root() / ".installed.yaml"
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
                    yaml_path = _resolve_compliance_template_root() / "workspace" / category / f"{template_slug}.yaml"
                    if yaml_path.exists():
                        with open(yaml_path, encoding="utf-8") as f:
                            return yaml.safe_load(f)
        return None

    def _try_auto_install(self) -> bool:
        """从 _MARKET_DATA_ROOT 安装整个 compliance domain 的模板到 DAWEI_HOME。

        当 DAWEI_HOME 中没有模板时作为 fallback 自动触发。
        返回 True 表示安装成功。
        """
        from dawei import get_dawei_home

        data_root = Path(os.environ.get(
            "MARKET_DATA_ROOT",
            str(Path(__file__).resolve().parents[4] / "nn-market-resources" / "data"),
        ))

        src_root = data_root / "compliance-templates"
        if not src_root.exists():
            logger.warning("Auto-install: compliance-templates source not found at %s", src_root)
            return False

        dawei_home = get_dawei_home()
        templates_root = dawei_home / "templates" / "compliance"

        # 1. 安装 workspace/
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
                        logger.error("Auto-install compliance category %s failed: %s", category, e)
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

        logger.info("Auto-installed compliance templates to %s", templates_root)
        return (templates_root / "workspace" / "index.yaml").exists()

    async def init_workspace_from_template(
        self,
        workspace_path: str,
        template_slug: str,
        form_data: dict[str, Any],
        storage: Any,
    ) -> dict[str, Any]:
        """根据模板初始化合规工作区

        执行步骤：
        1. 创建模板定义的目录结构 (input/, output/, reports/, references/)
        2. 写入初始 README 等文件
        3. 将用户表单数据写入对应的 JSON 文件
        4. 复制关联的合规清单 JSON 到 input/checklists/
        5. 渲染并写入 Agent 指令文件 input/AGENT_INSTRUCTIONS.md

        Args:
            workspace_path: 工作区根路径
            template_slug: 模板 slug
            form_data: 用户提交的表单数据
            storage: Storage 接口实例 (提供 create_directory, write_file, read_file)

        Returns:
            操作结果字典: {"dirs_created": [...], "files_written": [...]}
        """
        template = self.load_template(template_slug)
        if not template:
            raise ValueError(f"Template not found: {template_slug}")

        t = template.get("template", template)
        ws_root = Path(workspace_path)
        result: dict[str, Any] = {"dirs_created": [], "files_written": []}

        # 判断模式：表单模式 vs 对话采集模式
        is_chat_mode = not form_data  # 空对象 {} → 对话模式

        # 1. 创建目录结构
        for entry in t.get("workspace_structure", []):
            dir_name = entry.get("dir", "")
            if dir_name:
                await storage.create_directory(dir_name)
                result["dirs_created"].append(dir_name)

        # 2. 写入初始文件 (README.md 等)
        for entry in t.get("workspace_structure", []):
            for file_def in entry.get("initial_files", []):
                file_path = file_def.get("path", "")
                content = file_def.get("content", "")
                if file_path and content:
                    await storage.write_file(file_path, content)
                    result["files_written"].append(file_path)

        # 2.5 写入模板基本信息（两种模式都需要）
        await storage.write_file(
            "input/template_info.json",
            json.dumps({
                "slug": t.get("slug"),
                "name": t.get("name"),
                "team_slug": t.get("team_slug"),
                "description": t.get("description"),
                "collection_mode": "chat" if is_chat_mode else "form",
            }, ensure_ascii=False, indent=2),
        )
        result["files_written"].append("input/template_info.json")

        if is_chat_mode:
            # 对话采集模式：写入对话引导指令 + 空的采集状态
            instructions = self._render_chat_collection_instructions(t, workspace_path)
            await storage.write_file("input/AGENT_INSTRUCTIONS.md", instructions)
            result["files_written"].append("input/AGENT_INSTRUCTIONS.md")

            # 写入初始采集状态
            fields_status = {}
            for field in t.get("data_requirements", {}).get("required", []):
                fields_status[field.get("key", "")] = {"status": "pending", "required": True}
            for field in t.get("data_requirements", {}).get("optional", []):
                fields_status[field.get("key", "")] = {"status": "pending", "required": False}

            await storage.write_file(
                "input/collection_state.json",
                json.dumps({
                    "mode": "chat",
                    "template_slug": t.get("slug"),
                    "started_at": "",
                    "current_group": "",
                    "fields_status": fields_status,
                    "ready_to_analyze": False,
                }, ensure_ascii=False, indent=2),
            )
            result["files_written"].append("input/collection_state.json")
        else:
            # 表单模式：原有逻辑
            # 3. 填充表单数据 → JSON 文件
            for field in t.get("data_requirements", {}).get("required", []):
                await self._write_form_field(field, form_data, storage, result)
            for field in t.get("data_requirements", {}).get("optional", []):
                await self._write_form_field(field, form_data, storage, result)

        # 4. 复制关联的合规清单 JSON（两种模式都需要）
        await storage.create_directory("input/checklists")
        for ref in t.get("checklists", []):
            slug = ref["ref"].replace("checklist/", "")
            checklist_file = _resolve_checklist_base() / f"{slug}.json"
            if checklist_file.exists():
                content = checklist_file.read_text(encoding="utf-8")
                dest = f"input/checklists/{slug}.json"
                await storage.write_file(dest, content)
                result["files_written"].append(dest)
            else:
                logger.warning("Checklist not found: %s", checklist_file)

        # 5-6. 仅表单模式：写入 PDCA 分析指令 + 表单数据快照
        # （对话模式的指令已在上方 is_chat_mode 分支中写入，不能被覆盖）
        if not is_chat_mode:
            instructions = self._render_instructions(t, form_data, workspace_path)
            await storage.write_file("input/AGENT_INSTRUCTIONS.md", instructions)
            result["files_written"].append("input/AGENT_INSTRUCTIONS.md")

            await storage.write_file(
                "input/task_parameters.json",
                json.dumps(form_data, ensure_ascii=False, indent=2),
            )
            result["files_written"].append("input/task_parameters.json")

        logger.info(
            "Workspace initialized from template '%s': dirs=%d, files=%d",
            template_slug,
            len(result["dirs_created"]),
            len(result["files_written"]),
        )
        return result

    async def _write_form_field(
        self,
        field: dict[str, Any],
        form_data: dict[str, Any],
        storage: Any,
        result: dict[str, Any],
    ) -> None:
        """将单个表单字段写入 JSON 存储文件"""
        key = field.get("key", "")
        store_path = field.get("store", "")
        if not key or not store_path:
            return

        value = form_data.get(key)
        if value is None:
            return

        # 合并模式：读取已有 → 更新字段 → 写回
        existing = await self._read_json(storage, store_path)
        existing[key] = value
        await self._write_json(storage, store_path, existing)
        result["files_written"].append(store_path)

    def _render_chat_collection_instructions(
        self,
        template: dict[str, Any],
        ws_path: str,
    ) -> str:
        """渲染对话采集模式的 Agent 指令"""
        t = template
        required = t.get("data_requirements", {}).get("required", [])
        optional = t.get("data_requirements", {}).get("optional", [])

        # 构建字段引导列表
        field_guides: list[str] = []
        for f in required:
            desc = f.get("description", f.get("placeholder", ""))
            field_guides.append(f"- **{f.get('label', '')}**（必填）：{desc}")
        for f in optional:
            desc = f.get("description", f.get("placeholder", ""))
            field_guides.append(f"- **{f.get('label', '')}**（选填）：{desc}")

        fields_text = "\n".join(field_guides)

        # 构建对话分组（如果模板定义了 chat_collection.groups）
        chat_config = t.get("chat_collection", {})
        groups = chat_config.get("groups", [])
        groups_text = ""
        if groups:
            groups_text = "\n\n### 采集分组顺序\n"
            for i, g in enumerate(groups, 1):
                groups_text += f"\n**第 {i} 组：{g.get('name', '')}**\n"
                if g.get("intro"):
                    groups_text += f"引导语：{g['intro']}\n"
                fields_in_group = g.get("fields", [])
                groups_text += f"字段：{', '.join(fields_in_group)}\n"

        # 构建开场白
        opening = chat_config.get("opening", "")
        if not opening:
            opening = (
                f"你好！我是{t.get('name', '合规分析')}顾问。"
                "接下来我会逐步引导你提供所需的信息。你可以随时上传文件。"
            )

        # 构建合规清单表格
        checklist_table = self._build_checklist_table(t)

        template_name = t.get("name", "合规分析")

        return f"""# {template_name} — 对话引导采集模式

你已加入合规工作区，当前处于**对话引导采集模式**。

## 你的角色

你是一位耐心的合规顾问，正在通过对话引导用户逐步提供合规分析所需的信息和材料。

## 工作区路径
{ws_path}

## 采集目标

你需要通过对话收集以下信息：

{fields_text}
{groups_text}

## 对话采集原则

1. **每次只问一个问题**（或 2-3 个相关小问题），不要一次性问太多
2. **解释为什么需要这个信息**，帮助用户理解其合规意义
3. **提供示例**：当用户不确定如何回答时，给出示例值或场景
4. **接受自然语言**：用户不需要精确填写，你可以从描述中提取结构化数据
5. **主动追问**：如果用户的回答不够详细，礼貌追问细节
6. **接受文件上传**：引导用户上传相关文件（合同、股权图、提单等）
7. **标记进度**：定期告诉用户"已收集 X/Y 项必填信息"
8. **尊重用户节奏**：用户可以随时跳过某个问题，稍后再补充

## 对话流程

### 开场白

{opening}

### 采集循环

按以下顺序引导用户：
1. 基础信息（快速建立上下文）
2. 核心信息（按分组顺序，每组 1-3 个相关问题）
3. 补充材料（可选，引导上传文件）

### 采集完成判定

当所有必填字段已收集完毕时：
- 告知用户"信息已足够开始分析"
- 展示已收集信息摘要，请用户确认
- 用户确认后：
  a. 将对话中收集的数据写入 input/*.json（按模板的 store 路径映射）
  b. 更新 input/collection_state.json（ready_to_analyze: true）
  c. 输出："正在启动 PDCA 分析流程..."
  d. 进入 Plan 阶段

### 如果信息不足
- 告知用户当前缺少哪些关键信息
- 用户可选择"先用现有信息开始"或"补充后再开始"

### 中断恢复

如果检测到 input/collection_state.json 已存在且 ready_to_analyze 为 false：
- 读取 current_group 和 fields_status
- 生成恢复消息："欢迎回来！上次我们进行到「{{current_group}}」阶段。我们继续？"
- 从中断点继续

## 数据写入规范

- 同一个 store 路径的字段合并写入同一个 JSON 文件
- 文件上传保存到 input/ 目录
- 每轮对话后更新 input/collection_state.json

## 关联合规清单
以下合规清单已加载到 `input/checklists/` 目录：
{checklist_table}
"""

    def _build_checklist_table(self, template: dict[str, Any]) -> str:
        """构建合规清单表格"""
        rows: list[str] = []
        for ref in template.get("checklists", []):
            slug = ref["ref"].replace("checklist/", "")
            checklist_file = _resolve_checklist_base() / f"{slug}.json"
            if checklist_file.exists():
                data = json.loads(checklist_file.read_text(encoding="utf-8"))
                name = data.get("name", slug)
                desc = data.get("description", "")
                count = len(data.get("items", []))
                rows.append(f"| {name} | {desc} | {count} 项 |")

        table = "| 清单名称 | 说明 | 检查项数 |\n|---------|------|----------|\n"
        table += "\n".join(rows) if rows else "| — | 无关联清单 | 0 |"
        return table

    def _render_instructions(
        self,
        template: dict[str, Any],
        form_data: dict[str, Any],
        ws_path: str,
    ) -> str:
        """渲染 Agent 指令模板，填入变量和合规清单表格"""
        text = template.get("agent_instructions", "")

        # 使用共享方法构建合规清单表格
        table = self._build_checklist_table(template)

        variables = {
            "template_name": template.get("name", "合规分析"),
            "checklist_table": table,
            "workspace_path": ws_path,
            "form_data_summary": json.dumps(form_data, ensure_ascii=False, indent=2),
        }
        for k, v in variables.items():
            text = text.replace("{" + k + "}", v)

        return text

    async def _read_json(self, storage: Any, path: str) -> dict[str, Any]:
        """从 storage 读取 JSON 文件，不存在则返回 {}"""
        try:
            content = await storage.read_file(path)
            return json.loads(content)
        except Exception:
            return {}

    async def _write_json(self, storage: Any, path: str, data: dict[str, Any]) -> None:
        """将 dict 写入 JSON 文件"""
        await storage.write_file(path, json.dumps(data, ensure_ascii=False, indent=2))


# ── §18.3 缝改造：向核心 ext_hooks 注册合规模板初始化器（S5 模式）───────
# 核心 crud.create_workspace 不 import 本模块；biz 在场（本模块被 import）即注册，
# 缺席 = 无初始化器 = workspace 创建的模板初始化步骤静默跳过。

async def _init_compliance_workspace_template(
    workspace_path: str, template_slug: str, form_data: dict, storage=None
) -> dict | None:
    if not ComplianceTemplateManager().load_template(template_slug):
        return None  # 非合规域 slug，不认领
    return await ComplianceTemplateManager().init_workspace_from_template(
        workspace_path=workspace_path,
        template_slug=template_slug,
        form_data=form_data or {},
        storage=storage,
    )


def _register_ext_hook() -> None:
    from dawei.core.ext_hooks import register_workspace_template_initializer

    register_workspace_template_initializer("compliance", _init_compliance_workspace_template)


_register_ext_hook()
