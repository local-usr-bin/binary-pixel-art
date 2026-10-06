"""binary-pixel-art 源码包。

提供四种正式二值艺术模式（classic / bayer4 / adaptive_fine / adaptive_bold）
与尺寸模型、参数校验、共享脚手架。
"""

from . import algorithms, params, pipeline

__all__ = ["algorithms", "params", "pipeline"]
