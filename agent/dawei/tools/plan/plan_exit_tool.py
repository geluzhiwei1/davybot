# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Plan Exit Tool - 完成规划阶段并准备退出

实现 plan 退出的工具
"""

import json
import logging
from typing import Any

from pydantic import BaseModel

from dawei.tools.custom_base_tool import CustomBaseTool

logger = logging.getLogger(__name__)


class PlanExitInput(BaseModel):
    """Plan Exit 工具输入

    无需参数，但保留扩展性
    """

    # 空输入，所有信息从上下文获取


class PlanExitTool(CustomBaseTool):
    """Plan Exit 工具 - 完成规划并建议切换到 build mode

    功能：
    1. 检查 plan 文件是否存在
    2. 生成完成消息
    3. 建议切换到 build mode
    4. 提供切换命令示例
    """

    name: str = "plan_exit"
    description: str = (
        "Call this tool when you have completed your planning phase in the PDCA cycle. "
        "This will inform the user that the plan is complete and ask if they "
        "want to switch to do mode to start execution. "
        "This applies to ANY task type (software, data, writing, research, business, etc.). "
        "You should only call this tool after: "
        "1. You have understood the requirements and explored relevant information "
        "2. You have designed an approach or solution "
        "3. You have documented your plan in the plan file "
        "4. You have addressed all clarifying questions "
        "IMPORTANT: Your turn should only end with either asking a question "
        "or calling plan_exit. Do not stop unless it's for these 2 reasons."
    )
    args_schema = type(PlanExitInput)

    def __init__(self, user_workspace=None):
        """初始化 PlanExitTool

        Args:
            user_workspace: 用户工作区实例

        """
        super().__init__(user_workspace)
        self.logger = logger

    def _run(self, **_kwargs) -> str:
        """执行 plan exit

        Args:
            **kwargs: 工具参数（当前为空）

        Returns:
            执行结果 JSON 字符串

        """
        try:
            # 获取上下文信息
            session_id = self._get_session_id()
            workspace_root = self._get_workspace_root()

            # 检查 plan 文件
            plan_file_info = self._check_plan_file(session_id, workspace_root)

            if not plan_file_info["exists"]:
                return json.dumps(
                    {
                        "success": False,
                        "message": ("❌ No plan file found. Please create a plan file before calling plan_exit.\nUse write_to_file to create your plan in .dawei/plans/ directory."),
                        "should_switch": False,
                        "error": "no_plan_file",
                    },
                    indent=2,
                )

            # 构建成功响应
            result = {
                "success": True,
                "message": self._build_completion_message(plan_file_info),
                "plan_file": plan_file_info["path"],
                "plan_stats": plan_file_info.get("stats", {}),
                "should_switch": True,
                "suggested_mode": "do",
                "suggested_command": f'switch_mode(mode="do", reason="Ready to implement plan at {plan_file_info["path"]}")',
                "next_steps": [
                    "1. Review the plan file if needed",
                    "2. Switch to do mode to start implementation",
                    "3. Use the plan as your guide for implementation",
                ],
            }

            self.logger.info(
                f"Plan exit called for session {session_id}, plan file: {plan_file_info['path']}",
            )

            return json.dumps(result, indent=2, ensure_ascii=False)

        except (FileNotFoundError, PermissionError, OSError) as e:
            # File system errors - user needs to know about these
            self.logger.error(f"Plan exit file system error: {e}", exc_info=True)
            return json.dumps(
                {
                    "success": False,
                    "message": f"File system error: {e!s}",
                    "should_switch": False,
                    "error": "file_system_error",
                },
                indent=2,
            )
        except (KeyError, ValueError, AttributeError) as e:
            # Data structure errors - indicates a bug in plan file format
            self.logger.error(f"Plan exit data error: {e}", exc_info=True)
            return json.dumps(
                {
                    "success": False,
                    "message": f"Plan file format error: {e!s}",
                    "should_switch": False,
                    "error": "data_format_error",
                },
                indent=2,
            )
        except Exception as e:
            # Unexpected errors - log with full trace
            self.logger.error(f"Plan exit unexpected error: {e}", exc_info=True)
            return json.dumps(
                {
                    "success": False,
                    "message": f"Unexpected error: {e!s}",
                    "should_switch": False,
                    "error": "unexpected_error",
                },
                indent=2,
            )

    def _get_session_id(self) -> str:
        """获取当前会话 ID"""
        if self.user_workspace and hasattr(self.user_workspace, "conversation_id"):
            return str(self.user_workspace.conversation_id)
        return "current"

    def _get_workspace_root(self) -> str:
        """获取工作区根目录"""
        if self.user_workspace and hasattr(self.user_workspace, "workspace_info"):
            return self.user_workspace.workspace_info.absolute_path
        return "."

    def _check_plan_file(self, session_id: str, workspace_root: str) -> dict[str, Any]:
        """检查 plan 文件是否存在

        Args:
            session_id: 会话 ID
            workspace_root: 工作区根目录

        Returns:
            文件信息字典

        """
        from pathlib import Path

        try:
            from dawei.workspace.plan_file_manager import PlanFileManager

            plan_manager = PlanFileManager(Path(workspace_root))
            metadata = plan_manager.get_plan_metadata(session_id)

            if metadata:
                # 文件存在
                return {
                    "exists": True,
                    "path": metadata["path"],
                    "stats": {
                        "size": metadata["size"],
                        "modified": metadata["modified"],
                        "created": metadata["created"],
                    },
                }
            # 文件不存在
            return {"exists": False}

        except (FileNotFoundError, PermissionError, OSError) as e:
            # File system errors - log and treat as file not found
            self.logger.error(f"File system error checking plan file: {e}", exc_info=True)
            return {"exists": False, "error": f"File system error: {e}"}
        except (KeyError, ValueError, AttributeError) as e:
            # Data structure errors - indicates a bug in plan metadata
            self.logger.error(f"Plan metadata format error: {e}", exc_info=True)
            return {"exists": False, "error": f"Metadata format error: {e}"}
        except Exception as e:
            # Unexpected errors - log with full trace
            self.logger.error(f"Unexpected error checking plan file: {e}", exc_info=True)
            return {"exists": False, "error": f"Unexpected error: {e}"}

    def _get_task_domain(self) -> str:
        """获取当前任务领域

        Returns:
            任务领域类型 (software, data, writing, research, business, default)
        """
        try:
            # 尝试从 PDCA 上下文获取领域信息
            if self.user_workspace and hasattr(self.user_workspace, "pdca_context"):
                from dawei.agentic.pdca_context import PDCACycleContext

                pdca_ctx = self.user_workspace.pdca_context
                if pdca_ctx and hasattr(pdca_ctx, "domain"):
                    # domain 是枚举类型，转换为小写字符串
                    return pdca_ctx.domain.value.lower() if hasattr(pdca_ctx.domain, "value") else str(pdca_ctx.domain).lower()
        except Exception as e:
            self.logger.debug(f"Could not get domain from pdca_context: {e}")

        return "default"

    def _build_completion_message(self, plan_file_info: dict[str, Any]) -> str:
        """构建完成消息

        Args:
            plan_file_info: Plan 文件信息

        Returns:
            完成消息文本

        """
        plan_path = plan_file_info["path"]
        stats = plan_file_info.get("stats", {})
        domain = self._get_task_domain()

        # 根据领域定制消息
        domain_messages = {
            "software": """## ✅ Planning Phase Complete

You have successfully:
1. ✅ Understood the requirements
2. ✅ Explored the codebase
3. ✅ Designed the architecture
4. ✅ Created implementation plan
5. ✅ Documented everything""",
            "data": """## ✅ Planning Phase Complete

You have successfully:
1. ✅ Understood the problem
2. ✅ Explored the data
3. ✅ Selected analysis methods
4. ✅ Created analysis plan
5. ✅ Documented approach""",
            "writing": """## ✅ Planning Phase Complete

You have successfully:
1. ✅ Understood the topic
2. ✅ Collected materials
3. ✅ Designed the structure
4. ✅ Created writing plan
5. ✅ Documented outline""",
            "research": """## ✅ Planning Phase Complete

You have successfully:
1. ✅ Defined the research question
2. ✅ Conducted literature review
3. ✅ Designed research methodology
4. ✅ Created research plan
5. ✅ Documented approach""",
            "business": """## ✅ Planning Phase Complete

You have successfully:
1. ✅ Defined business objectives
2. ✅ Analyzed market conditions
3. ✅ Designed strategy
4. ✅ Created execution plan
5. ✅ Documented approach""",
            "default": """## ✅ Planning Phase Complete

You have successfully:
1. ✅ Understood the requirements
2. ✅ Explored relevant information
3. ✅ Designed an approach
4. ✅ Created a detailed plan
5. ✅ Documented everything""",
        }

        phase_complete_message = domain_messages.get(domain, domain_messages["default"])

        message = f"""🎯 **Plan Phase Complete!**

Your plan has been documented at:
`{plan_path}`
"""

        if stats:
            if "modified" in stats:
                message += f"\n**Last Modified**: {stats['modified']}"
            if "size" in stats:
                size_kb = stats["size"] / 1024
                message += f"\n**File Size**: {size_kb:.1f} KB"

        message += f"""

---

{phase_complete_message}

---

## 🚀 Next Steps

**Recommended**: Switch to **do mode** to start executing the plan

Use this command:
```
switch_mode(mode="do", reason="Ready to execute plan")
```

**Alternative**: Stay in plan mode to refine the plan further

---

## 📋 Execution Checklist

When you switch to do mode:
1. Read the plan file carefully
2. Follow the steps in order
3. Update the plan as you go if needed
4. Use the success criteria to verify completion
"""

        return message
