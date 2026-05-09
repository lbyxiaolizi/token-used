"""Compatibility facade for TokenUsed shared plugin helpers.

插件入口和测试仍从 `_shared` import；实际实现按职责拆到同目录
`_shared_core.py`、`_shared_cache.py`、`_shared_parsers.py`、`_shared_builders.py`。
保持这些模块都是 `plugins/*.py`，这样现有手动安装命令仍会复制依赖。
"""
from __future__ import annotations

from _shared_builders import *  # noqa: F401,F403
from _shared_cache import *  # noqa: F401,F403
from _shared_core import *  # noqa: F401,F403
from _shared_parsers import *  # noqa: F401,F403
