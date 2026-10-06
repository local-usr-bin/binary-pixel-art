"""GUI 状态层（不依赖 Tkinter，可独立自动测试）。

职责（刻意保持薄）：
- 记住每个正式模式在本次会话中的参数（mode -> parameter state）；
- 提供 Restore Defaults（仅恢复当前模式）；
- 参数校验（blockSize 奇数 / t、b 范围 / b>=t 允许）；
- geometry readout：复用 src.params.compute_geometry，不复制算法逻辑。

本模块不接触 cv2 图像处理，也不导入 Tkinter。
"""

from dataclasses import dataclass, field

from src.params import (
    compute_geometry,
    DEFAULT_GEOMETRY,
    CLASSIC_DEFAULT_T,
    CLASSIC_DEFAULT_B,
    CLASSIC_DEFAULT_EQUALIZE,
    BAYER_DEFAULT_MATRIX,
    BAYER_DEFAULT_TONE_BIAS,
    ADAPTIVE_DEFAULT_C,
    ADAPTIVE_FINE_DEFAULT_BLOCK,
    ADAPTIVE_BOLD_DEFAULT_BLOCK,
)


# 四种正式模式的显示名与简短辅助说明（不在状态层放长文）。
MODE_LABELS = {
    "classic": ("Classic", "稀疏点阵"),
    "bayer4": ("Bayer 4×4", "规则网点"),
    "adaptive_fine": ("Adaptive Fine", "细密墨线"),
    "adaptive_bold": ("Adaptive Bold", "粗块木刻"),
}

MODE_ORDER = ("classic", "bayer4", "adaptive_fine", "adaptive_bold")


@dataclass
class GeometryReadout:
    """geometry readout 结果，供 GUI 回显。"""
    requested_output_width: int
    pixel_block_size: int
    logical_width: int
    logical_height: int
    actual_output_width: int
    actual_output_height: int

    def format(self) -> str:
        return (
            f"实际输出：{self.actual_output_width} × {self.actual_output_height}\n"
            f"逻辑网格：{self.logical_width} × {self.logical_height}"
        )


def default_params(mode: str) -> dict:
    """返回某模式的默认参数预设（对齐后端 src.params 默认值）。"""
    geo = DEFAULT_GEOMETRY[mode]
    base = {
        "output_width": geo["output_width"],
        "pixel_block_size": geo["pixel_block_size"],
        "invert": False,
    }
    if mode == "classic":
        base.update({
            "t": CLASSIC_DEFAULT_T,
            "b": CLASSIC_DEFAULT_B,
            "equalize": CLASSIC_DEFAULT_EQUALIZE,
        })
    elif mode == "bayer4":
        base.update({
            "matrix_size": BAYER_DEFAULT_MATRIX,
            "tone_bias": BAYER_DEFAULT_TONE_BIAS,
        })
    elif mode == "adaptive_fine":
        base.update({
            "block_size": ADAPTIVE_FINE_DEFAULT_BLOCK,
            "c": ADAPTIVE_DEFAULT_C,
        })
    elif mode == "adaptive_bold":
        base.update({
            "block_size": ADAPTIVE_BOLD_DEFAULT_BLOCK,
            "c": ADAPTIVE_DEFAULT_C,
        })
    else:
        raise ValueError(f"未知模式: {mode}")
    return base


def normalize_block_size(value) -> int:
    """把 blockSize 规范为合法奇数（>=3）。用于 UI 步长 2 的输入收敛。"""
    v = int(value)
    if v < 3:
        v = 3
    if v % 2 == 0:
        v += 1
    return v


class AppState:
    """GUI 会话状态：每模式参数记忆 + source 状态 + geometry readout。

    刻意轻量：mode -> parameter dict，不引入 profile/preset 系统。
    """

    def __init__(self):
        # 每个模式独立记住自己的参数
        self._params = {m: default_params(m) for m in MODE_ORDER}
        self.current_mode = "classic"
        # source 状态
        self.source_path = None
        self.source_shape = None  # (height, width) 或 None

    # ------------------------------------------------------------------ 模式
    def set_mode(self, mode: str):
        if mode not in self._params:
            raise ValueError(f"未知模式: {mode}")
        self.current_mode = mode

    def modes(self):
        return list(MODE_ORDER)

    # ------------------------------------------------------------- 参数读写
    def get_params(self, mode=None) -> dict:
        mode = mode or self.current_mode
        return dict(self._params[mode])

    def get_param(self, key, mode=None):
        mode = mode or self.current_mode
        return self._params[mode][key]

    def set_param(self, key, value, mode=None):
        """设置某模式的一个参数。返回实际写入值（可能被规范化）。"""
        mode = mode or self.current_mode
        if key == "block_size":
            value = normalize_block_size(value)
        self._params[mode][key] = value
        return value

    def update_params(self, updates: dict, mode=None):
        """批量更新某模式参数。返回键 -> 实际写入值。"""
        result = {}
        for k, v in updates.items():
            result[k] = self.set_param(k, v, mode=mode)
        return result

    def restore_defaults(self, mode=None):
        """恢复当前（或指定）模式的默认 preset；**不影响**其它模式。"""
        mode = mode or self.current_mode
        self._params[mode] = default_params(mode)

    # --------------------------------------------------------------- 校验
    @staticmethod
    def classic_b_ge_t_warning(t, b):
        """b >= t 是允许的；返回轻量提示文本（不阻止）。"""
        if int(b) >= int(t):
            return "提示：b ≥ t（偏离经典三档语义，允许但不推荐）"
        return ""

    # -------------------------------------------------------- geometry readout
    def geometry_readout(self, mode=None) -> GeometryReadout:
        """用当前参数 + 当前 source 尺寸计算 geometry（复用后端 API）。

        无 source 时用占位尺寸（不影响参数本身）。
        """
        mode = mode or self.current_mode
        p = self._params[mode]
        if self.source_shape is None:
            src_h, src_w = 600, 800  # 占位，仅用于 readout 展示
        else:
            src_h, src_w = self.source_shape
        geo = compute_geometry(
            src_w, src_h,
            p["output_width"], p["pixel_block_size"],
        )
        return GeometryReadout(
            requested_output_width=p["output_width"],
            pixel_block_size=p["pixel_block_size"],
            logical_width=geo.logical_width,
            logical_height=geo.logical_height,
            actual_output_width=geo.actual_output_width,
            actual_output_height=geo.actual_output_height,
        )

    # --------------------------------------------------------------- source
    def set_source(self, path, shape):
        """打开新 source：记录路径与 (h, w)。"""
        self.source_path = path
        self.source_shape = (int(shape[0]), int(shape[1]))

    @property
    def source_filename(self):
        import os
        return os.path.basename(self.source_path) if self.source_path else ""
