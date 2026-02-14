# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具调用日志记录器

所有工具调用日志统一保存在 DAWEI_HOME/logs/tool_calls.log
"""

# 导入标准库的 logging 模块，避免与本地包冲突
import importlib
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dawei.config.logging_config import get_tool_log_path

std_logging = importlib.import_module("logging")

# 使用统一的日志路径
log_file = get_tool_log_path()

# Ensure the log directory exists

Path(log_file).parent.mkdir(parents=True, exist_ok=True)

# Create a logger instance
tool_logger = std_logging.getLogger("tool_logger")
tool_logger.setLevel(std_logging.INFO)
tool_logger.propagate = False  # Prevent logs from being passed to the root logger

# Create a file handler for the logger
# Use RotatingFileHandler to prevent log files from growing indefinitely
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=1024 * 1024 * 5,  # 5MB
    backupCount=5,
    encoding="utf-8",
)

# Create a JSON formatter
formatter = std_logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
file_handler.setFormatter(formatter)

# Add the handler to the logger, but only if it doesn't have handlers already
if not tool_logger.handlers:
    tool_logger.addHandler(file_handler)
