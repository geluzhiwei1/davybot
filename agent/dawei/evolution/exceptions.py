# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Evolution Feature Exceptions

自定义异常层次结构，用于Evolution功能的错误处理。
"""


class EvolutionError(Exception):
    """Evolution功能的基础异常类

    所有Evolution相关的异常都应该继承此类。
    """


class EvolutionAlreadyRunningError(EvolutionError):
    """当尝试启动一个已在运行的evolution cycle时抛出

    这个异常用于强制执行"每个workspace同时只能有一个evolution cycle在运行"的约束。
    """


class EvolutionStateError(EvolutionError):
    """当操作对当前cycle状态无效时抛出

    例如：
    - 尝试暂停一个已完成的cycle
    - 尝试恢复一个未暂停的cycle
    - 尝试中止一个已失败的cycle
    """


class EvolutionPhaseError(EvolutionError):
    """当一个phase在所有重试后仍然失败时抛出

    这个异常表示某个PDCA phase执行失败，已经达到最大重试次数。
    """


class EvolutionStorageError(EvolutionError):
    """当存储读写操作失败时抛出

    这个异常包装了文件I/O错误、JSON解析错误等底层存储问题。
    """
