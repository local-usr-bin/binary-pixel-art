"""binary-pixel-art 实验源码包。

本包提供 Classic（精确复现）与第一轮 Modern 五个候选的最小实现。
所有算法共享同一套脚手架：灰度 -> 缩小 -> 二值化 -> nearest-neighbor 放大。
"""

from .config import LOGICAL_WIDTH, DEFAULT_RESIZE
from . import algorithms

__all__ = ["LOGICAL_WIDTH", "DEFAULT_RESIZE", "algorithms"]
