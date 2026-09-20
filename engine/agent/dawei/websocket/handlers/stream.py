# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""流消息处理器

处理流式数据传输，支持大文件传输和实时数据流。
"""

import json
import logging
from io import BytesIO
from typing import List, Dict, Any

from dawei.websocket.protocol import (
    BaseWebSocketMessage,
    ErrorMessage,
    MessageType,
    TaskNodeCompleteMessage,
    TaskNodeProgressMessage,
    TaskNodeStartMessage,
)

from .base import AsyncMessageHandler, StatefulMessageHandler

logger = logging.getLogger(__name__)


class StreamHandler(AsyncMessageHandler, StatefulMessageHandler):
    """流消息处理器"""

    def __init__(self, max_chunk_size: int = 8192, max_concurrent_streams: int = 5):
        AsyncMessageHandler.__init__(self, max_concurrent_tasks=max_concurrent_streams)
        StatefulMessageHandler.__init__(self)

        self.max_chunk_size = max_chunk_size
        self.active_streams: Dict[str, Dict[str, Any]] = {}

    def get_supported_types(self) -> List[str]:
        """获取支持的消息类型"""
        return [
            MessageType.TASK_NODE_START,
            MessageType.TASK_NODE_PROGRESS,
            MessageType.TASK_NODE_COMPLETE,
            MessageType.ERROR,
        ]

    async def on_initialize(self):
        """初始化时的回调"""
        await super().on_initialize()
        await self.set_state("initialized", True)
        logger.info("流处理器已初始化")

    async def process_message(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
    ) -> BaseWebSocketMessage | None:
        """处理流消息

        Args:
            session_id: 会话ID
            message: 流消息

        Returns:
            可选的响应消息

        """
        message_type = message.type

        if message_type == MessageType.TASK_NODE_START:
            return await self._handle_stream_start(session_id, message)
        if message_type == MessageType.TASK_NODE_PROGRESS:
            return await self._handle_stream_data(session_id, message)
        if message_type == MessageType.TASK_NODE_COMPLETE:
            return await self._handle_stream_end(session_id, message)
        if message_type == MessageType.ERROR:
            return await self._handle_stream_error(session_id, message)
        logger.warning(f"不支持的流消息类型: {message_type}")
        return None

    async def _handle_stream_start(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
    ) -> BaseWebSocketMessage | None:
        """处理流开始消息

        Args:
            session_id: 会话ID
            message: 流开始消息

        Returns:
            可选的响应消息

        """
        if not isinstance(message, TaskNodeStartMessage):
            return None

        stream_id = message.task_id
        task_node_id = message.task_node_id

        # 检查是否已存在该流
        if stream_id in self.active_streams:
            logger.warning(f"流 {stream_id} 已存在")
            return await self.send_error_message(
                session_id,
                "STREAM_ALREADY_EXISTS",
                f"流 {stream_id} 已存在",
                {"stream_id": stream_id},
            )

        # 创建新的流
        self.active_streams[stream_id] = {
            "session_id": session_id,
            "stream_id": stream_id,
            "started_at": message.timestamp,
            "data": BytesIO(),
            "size": 0,
            "chunks": 0,
            "status": "active",
        }

        # 更新处理器状态
        await self.set_state(
            f"stream_{stream_id}",
            {
                "status": "started",
                "session_id": session_id,
                "started_at": message.timestamp,
            },
        )

        logger.info(f"已开始流 {stream_id} for session {session_id}")

        # 发送确认消息
        return TaskNodeStartMessage(
            session_id=session_id,
            task_id=stream_id or task_node_id,  # 🔧 修复：优先使用 node_id，如果 stream_id 为空
            task_node_id=task_node_id,
            node_type="stream",
            description=f"流 {stream_id} 已开始",
        )

    async def _handle_stream_data(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
    ) -> BaseWebSocketMessage | None:
        """处理流数据消息

        Args:
            session_id: 会话ID
            message: 流数据消息

        Returns:
            可选的响应消息

        """
        if not isinstance(message, TaskNodeProgressMessage):
            return None

        stream_id = message.task_id
        task_node_id = message.task_node_id

        # 检查流是否存在
        if stream_id not in self.active_streams:
            logger.warning(f"流 {stream_id} 不存在")
            return await self.send_error_message(
                session_id,
                "STREAM_NOT_FOUND",
                f"流 {stream_id} 不存在",
                {"stream_id": stream_id},
            )

        stream_info = self.active_streams[stream_id]

        # 检查流状态
        if stream_info["status"] != "active":
            logger.warning(f"流 {stream_id} 状态不正确: {stream_info['status']}")
            return await self.send_error_message(
                session_id,
                "STREAM_NOT_ACTIVE",
                f"流 {stream_id} 不处于活跃状态",
                {"stream_id": stream_id, "status": stream_info["status"]},
            )

        # 获取数据
        data = message.data or {}
        chunk_data = data.get("chunk", "")

        if isinstance(chunk_data, str):
            # 如果是字符串，转换为字节
            chunk_bytes = chunk_data.encode("utf-8")
        elif isinstance(chunk_data, bytes):
            chunk_bytes = chunk_data
        else:
            # 其他类型转换为字符串再编码
            chunk_bytes = str(chunk_data).encode("utf-8")

        # 写入数据
        stream_info["data"].write(chunk_bytes)
        stream_info["size"] += len(chunk_bytes)
        stream_info["chunks"] += 1

        # 更新处理器状态
        await self.set_state(
            f"stream_{stream_id}",
            {
                "status": "streaming",
                "size": stream_info["size"],
                "chunks": stream_info["chunks"],
            },
        )

        # 检查大小限制
        max_size = await self.get_state("max_stream_size", 100 * 1024 * 1024)  # 默认100MB
        if stream_info["size"] > max_size:
            logger.warning(f"流 {stream_id} 超过大小限制")
            await self._cleanup_stream(stream_id)
            return await self.send_error_message(
                session_id,
                "STREAM_TOO_LARGE",
                f"流 {stream_id} 超过大小限制",
                {
                    "stream_id": stream_id,
                    "size": stream_info["size"],
                    "max_size": max_size,
                },
            )

        # 发送进度确认
        return TaskNodeProgressMessage(
            session_id=session_id,
            task_id=message.task_id,
            task_node_id=task_node_id,
            progress=message.progress,
            status="streaming",
            message=f"已接收 {stream_info['chunks']} 个数据块，总计 {stream_info['size']} 字节",
            data={"chunks": stream_info["chunks"], "size": stream_info["size"]},
        )

    async def _handle_stream_end(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
    ) -> BaseWebSocketMessage | None:
        """处理流结束消息

        Args:
            session_id: 会话ID
            message: 流结束消息

        Returns:
            可选的响应消息

        """
        if not isinstance(message, TaskNodeCompleteMessage):
            return None

        stream_id = message.task_id
        task_node_id = message.task_node_id

        # 检查流是否存在
        if stream_id not in self.active_streams:
            logger.warning(f"流 {stream_id} 不存在")
            return await self.send_error_message(
                session_id,
                "STREAM_NOT_FOUND",
                f"流 {stream_id} 不存在",
                {"stream_id": stream_id},
            )

        stream_info = self.active_streams[stream_id]

        # 获取完整数据
        stream_info["data"].seek(0)
        complete_data = stream_info["data"].read()

        # 处理完整数据
        try:
            result = await self._process_complete_data(
                session_id,
                stream_id,
                complete_data,
                message.result or {},
            )

            # 更新流状态
            stream_info["status"] = "completed"

            # 更新处理器状态
            await self.set_state(
                f"stream_{stream_id}",
                {
                    "status": "completed",
                    "size": stream_info["size"],
                    "chunks": stream_info["chunks"],
                    "result": result,
                },
            )

            # 清理流
            await self._cleanup_stream(stream_id)

            logger.info(f"流 {stream_id} 已完成，总计 {stream_info['size']} 字节")

            # 发送完成确认
            return TaskNodeCompleteMessage(
                session_id=session_id,
                task_id=stream_id or task_node_id,  # 🔧 修复：优先使用 node_id，如果 stream_id 为空
                task_node_id=task_node_id,
                result={
                    "status": "completed",
                    "size": stream_info["size"],
                    "chunks": stream_info["chunks"],
                    "result": result,
                },
                duration_ms=0,
            )

        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"处理流数据时出错: {e}", exc_info=True)

            # 清理流
            await self._cleanup_stream(stream_id)

            return await self.send_error_message(
                session_id,
                "STREAM_PROCESSING_ERROR",
                f"处理流数据时出错: {e!s}",
                {"stream_id": stream_id},
            )

    async def _handle_stream_error(
        self,
        session_id: str,
        message: BaseWebSocketMessage,
    ) -> BaseWebSocketMessage | None:
        """处理流错误消息

        Args:
            session_id: 会话ID
            message: 流错误消息

        Returns:
            可选的响应消息

        """
        if not isinstance(message, ErrorMessage):
            return None

        # 清理流 - 从错误消息的details中获取stream_id
        stream_id = None
        if message.details and "stream_id" in message.details:
            stream_id = message.details["stream_id"]

        if stream_id and stream_id in self.active_streams:
            await self._cleanup_stream(stream_id)

            # 更新处理器状态
            await self.set_state(
                f"stream_{stream_id}",
                {"status": "error", "error": message.message, "code": message.code},
            )

            logger.error(f"流 {stream_id} 发生错误: {message.message}")

        # 发送错误确认
        return ErrorMessage(
            session_id=session_id,
            code=message.code,
            message=f"流错误已确认: {message.message}",
            details=message.details,
            recoverable=message.recoverable,
        )

    async def _process_complete_data(
        self,
        _session_id: str,
        _stream_id: str,
        data: bytes,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """处理完整的数据

        Args:
            session_id: 会话ID
            stream_id: 流ID
            data: 完整数据
            metadata: 元数据

        Returns:
            处理结果

        """
        # 这里可以根据实际需求处理数据
        # 例如：保存到文件、解析内容、调用其他服务等

        try:
            # 示例：尝试解析为JSON
            if data.startswith(b"{") and data.endswith(b"}"):
                import json

                json_data = json.loads(data.decode("utf-8"))
                return {"type": "json", "data": json_data, "size": len(data)}

            # 示例：尝试解析为文本
            try:
                text_data = data.decode("utf-8")
                return {
                    "type": "text",
                    "data": text_data,
                    "size": len(data),
                    "lines": len(text_data.split("\n")),
                }
            except UnicodeDecodeError:
                pass

            # 默认：作为二进制数据处理
            return {"type": "binary", "size": len(data), "metadata": metadata}

        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"处理完整数据时出错: {e}", exc_info=True)
            raise

    async def _cleanup_stream(self, stream_id: str):
        """清理流资源

        Args:
            stream_id: 流ID

        """
        if stream_id in self.active_streams:
            stream_info = self.active_streams[stream_id]

            # 关闭数据流
            if hasattr(stream_info["data"], "close"):
                stream_info["data"].close()

            # 从活跃流中移除
            del self.active_streams[stream_id]

            # 清理处理器状态
            await self.set_state(f"stream_{stream_id}", None)

    async def get_stream_info(self, stream_id: str) -> Dict[str, Any] | None:
        """获取流信息

        Args:
            stream_id: 流ID

        Returns:
            流信息，不存在返回None

        """
        return self.active_streams.get(stream_id)

    async def get_active_streams(self) -> List[Dict[str, Any]]:
        """获取所有活跃流

        Returns:
            活跃流列表

        """
        return [
            {
                "stream_id": stream_id,
                "session_id": info["session_id"],
                "size": info["size"],
                "chunks": info["chunks"],
                "status": info["status"],
                "started_at": info["started_at"],
            }
            for stream_id, info in self.active_streams.items()
        ]

    async def set_max_stream_size(self, max_size: int):
        """设置最大流大小

        Args:
            max_size: 最大大小（字节）

        """
        await self.set_state("max_stream_size", max_size)
        logger.info(f"已设置最大流大小: {max_size} 字节")

    async def cleanup(self):
        """清理资源"""
        # 清理所有活跃流
        for stream_id in list(self.active_streams.keys()):
            await self._cleanup_stream(stream_id)

        # 清理状态
        await self.clear_state()

        # 调用父类清理
        await super().cleanup()

        logger.info("流处理器已清理")
