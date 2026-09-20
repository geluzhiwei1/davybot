# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""SchemaCompressor — OpenAI function schema 压缩器。

将完整 JSON Schema 压缩为最小必要表示。
策略：
1. 保留 name + 精简 description（首句）
2. 参数只保留 name + type + required，删除 description 中冗余内容
3. 删除 $schema、title、default 等元字段
4. 枚举值保留（LLM 需要知道合法值）
"""


class SchemaCompressor:
    """将完整 OpenAI function schema 压缩为最小必要表示。"""

    MAX_DESC_LEN: int = 120  # description 最大字符数

    @staticmethod
    def compress(tool_schema: dict) -> dict:
        """压缩单个工具的 OpenAI function schema。

        Args:
            tool_schema: 原始工具 schema（含 type/function/parameters）

        Returns:
            压缩后的 schema
        """
        func = tool_schema.get("function", tool_schema)

        params_in = func.get("parameters", {})
        props_in = params_in.get("properties", {})
        required_in = params_in.get("required", [])

        return {
            "type": "function",
            "function": {
                "name": func.get("name", ""),
                "description": SchemaCompressor._trim_desc(func.get("description", "")),
                "parameters": {
                    "type": "object",
                    "properties": SchemaCompressor._trim_props(props_in),
                    "required": required_in,
                },
            },
        }

    @staticmethod
    def compress_many(tool_schemas: list[dict]) -> list[dict]:
        """批量压缩工具 schema。"""
        return [SchemaCompressor.compress(ts) for ts in tool_schemas]

    @staticmethod
    def _trim_desc(desc: str) -> str:
        """保留首句 + 总长 ≤ MAX_DESC_LEN 字符。

        中文用"。"分句，英文用 ". " 分句，取第一句。
        """
        if not desc:
            return ""

        # 按中文句号或英文句号+空格分句
        first_sentence = desc.split("。", 1)[0].split(". ", 1)[0].split("\n", 1)[0]
        return first_sentence[: SchemaCompressor.MAX_DESC_LEN]

    @staticmethod
    def _trim_props(props: dict) -> dict:
        """每个参数只保留 type + enum（如有），删 description/default 等。

        保留字段：type, enum, items（用于 array type）, minimum, maximum
        删除字段：description, default, title, $ref, examples
        """
        trimmed = {}

        for name, schema in props.items():
            if not isinstance(schema, dict):
                trimmed[name] = {"type": "string"}
                continue

            entry: dict = {"type": schema.get("type", "string")}

            # 保留枚举值
            if "enum" in schema:
                entry["enum"] = schema["enum"]

            # 保留数值约束
            for k in ("minimum", "maximum", "minLength", "maxLength"):
                if k in schema:
                    entry[k] = schema[k]

            # array 类型保留 items 的 type
            if schema.get("type") == "object" and "properties" in schema:
                # 嵌套对象：递归压缩
                entry["type"] = "object"
                entry["properties"] = SchemaCompressor._trim_props(schema["properties"])
                entry["required"] = schema.get("required", [])
            elif schema.get("type") == "array" and "items" in schema:
                items_schema = schema["items"]
                if isinstance(items_schema, dict):
                    entry["items"] = {"type": items_schema.get("type", "string")}
                    if "enum" in items_schema:
                        entry["items"]["enum"] = items_schema["enum"]

            trimmed[name] = entry

        return trimmed
