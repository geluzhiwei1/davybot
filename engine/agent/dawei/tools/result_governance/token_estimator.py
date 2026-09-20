# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""L1 — Token 估算器

字符 -> token 估算。优先 tiktoken，回退启发式。
CJK 密度高时 len//2，否则 len//4。
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 尝试加载 tiktoken（可选依赖）
_tiktoken_enc = None
try:
    import tiktoken

    _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
    logger.debug("tiktoken loaded for precise token estimation")
except ImportError:
    logger.debug("tiktoken not available, using heuristic estimation")
except Exception as e:
    logger.debug(f"tiktoken init failed: {e}, using heuristic")


def _cjk_ratio(text: str) -> float:
    """估算字符串中 CJK 字符的占比 (0.0 - 1.0)。"""
    if not text:
        return 0.0
    cjk_count = 0
    for ch in text:
        cp = ord(ch)
        # CJK Unified Ideographs + Common ranges
        if (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0x20000 <= cp <= 0x2A6DF
            or 0x3040 <= cp <= 0x30FF  # Hiragana + Katakana
            or 0xAC00 <= cp <= 0xD7AF  # Hangul
        ):
            cjk_count += 1
    return cjk_count / len(text)


class TokenEstimator:
    """字符 -> token 估算器。

    策略：
    1. tiktoken 可用时：精确计算
    2. 否则：CJK 密度高时 len//2，否则 len//4
    """

    def estimate(self, text: str) -> int:
        """估算字符串的 token 数。"""
        if not text:
            return 0

        if _tiktoken_enc is not None:
            try:
                return len(_tiktoken_enc.encode(text))
            except Exception:
                pass  # 回退到启发式

        # 启发式：CJK 字符通常 1 char ≈ 0.5-1 token，ASCII 通常 4 chars ≈ 1 token
        ratio = _cjk_ratio(text)
        if ratio > 0.3:
            # CJK 密度高：平均 1 char ≈ 0.6 token
            return max(1, int(len(text) * 0.6))
        # 以 ASCII 为主：平均 4 chars ≈ 1 token
        return max(1, len(text) // 4)

    def estimate_json(self, obj: Any) -> int:
        """JSON 序列化后估算 token 数。"""
        try:
            text = json.dumps(obj, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(obj)
        return self.estimate(text)


# 单例
_token_estimator: TokenEstimator | None = None


def get_token_estimator() -> TokenEstimator:
    """获取全局 TokenEstimator 单例。"""
    global _token_estimator
    if _token_estimator is None:
        _token_estimator = TokenEstimator()
    return _token_estimator
