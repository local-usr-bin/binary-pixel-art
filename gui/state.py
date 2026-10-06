"""GUI 状态层（不依赖 Tkinter，可独立自动测试）。

职责（刻意保持薄）：
- 记住每个正式模式在本次会话中的参数（mode -> parameter state）；
- 提供 Restore Defaults（仅恢复当前模式）；
- 参数校验（blockSize 奇数 / t、b 范围 / b>=t 允许）；
- 全局输出渲染状态（color_fill 等，跨模式保持不变）；
- geometry readout：复用 src.params.compute_geometry，不复制算法逻辑；
- GenerationKey（source/mode/参数/invert/color_fill）与 current/stale 判定；
- result 内存状态与 save_enabled 条件逻辑。

本模块不接触 cv2 图像处理，也不导入 Tkinter。
"""

import hashlib
from dataclasses import dataclass

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
    "bayer4": ("Bayer", "规则网点"),
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


# 每个模式「影响结果」的参数键（用于构造 GenerationKey）。
# 不含 invert（invert 是共同输出选项，单独纳入 key）。
_MODE_RESULT_KEYS = {
    "classic": ("t", "b", "equalize"),
    "bayer4": ("matrix_size", "tone_bias"),
    "adaptive_fine": ("block_size", "c"),
    "adaptive_bold": ("block_size", "c"),
}


@dataclass(frozen=True)
class GenerationKey:
    """一次生成结果的唯一标识（轻量、可哈希、可相等比较）。

    包含：source identity、mode、target/requested width、pixel block size、
    模式专属参数、invert、color_fill。两把 key 完全相等 <=> 结果可判定为 current。
    """
    source_id: str          # source 身份（路径 + 尺寸 + 内容指纹）
    mode: str
    output_width: int
    pixel_block_size: int
    invert: bool
    color_fill: bool
    mode_params: tuple      # 模式专属参数，排序后的 (k, v) 元组，保证可哈希

    @staticmethod
    def _source_identity(path, shape, content_digest):
        """source 身份：结合路径、尺寸与内容指纹，避免不同图片同参数误判。"""
        h, w = (shape if shape else (0, 0))
        parts = [str(path), f"{w}x{h}", str(content_digest)]
        joined = "|".join(parts)
        return hashlib.sha1(joined.encode("utf-8")).hexdigest()

    @classmethod
    def from_state(cls, state, source_content_digest=None):
        """从当前 AppState 构造 current key。"""
        mode = state.current_mode
        p = state.get_params(mode)
        mp = tuple(sorted((k, p[k]) for k in _MODE_RESULT_KEYS[mode]))
        return cls(
            source_id=cls._source_identity(
                state.source_path, state.source_shape, source_content_digest),
            mode=mode,
            output_width=int(p["output_width"]),
            pixel_block_size=int(p["pixel_block_size"]),
            invert=bool(p.get("invert", False)),
            color_fill=bool(state.color_fill),
            mode_params=mp,
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
    """把 blockSize 规范为合法奇数（>=3）。

    规则（固定、确定性，产品契约）：
      - < 3        -> 3
      - 偶数 n     -> n + 1（例如 12 -> 13，与向上步进直觉一致）
    """
    v = int(value)
    if v < 3:
        v = 3
    if v % 2 == 0:
        v += 1
    return v


def is_editable_block_size_text(text) -> bool:
    """判断文本是否为 blockSize 编辑期允许的「中间态」。

    允许：空字符串 ""、纯数字串（如 "1" / "12" / "123"）。
    不允许：含非数字字符的文本（编辑期直接拒绝）。
    用于 Spinbox validatecommand，保证用户可以「全选 -> 直接键入」。
    """
    if text == "":
        return True
    return text.isdigit()


def commit_block_size_text(text, last_valid: int) -> int:
    """把编辑框文本提交为合法 blockSize（确定性）。

    - 空 或 非数字 -> 恢复 last_valid（不崩、不写入空串）
    - 数字        -> normalize_block_size（<3 -> 3；偶数 -> +1）
    """
    s = (text or "").strip()
    if s == "" or not s.isdigit():
        return int(last_valid)
    return normalize_block_size(int(s))


class AppState:
    """GUI 会话状态：每模式参数记忆 + source 状态 + geometry readout。

    刻意轻量：mode -> parameter dict，不引入 profile/preset 系统。
    """

    def __init__(self):
        # 每个模式独立记住自己的参数
        self._params = {m: default_params(m) for m in MODE_ORDER}
        self.current_mode = "classic"
        # 全局输出渲染状态（不属于任何 mode preset；跨模式保持不变）
        # - color_fill：Color Fill 全局开关，默认 OFF
        self.color_fill = False
        # source 状态
        self.source_path = None
        self.source_shape = None  # (height, width) 或 None
        self.source_digest = None  # source 内容指纹（见 set_source）
        # 生成结果状态
        self.generated_key = None      # GenerationKey 或 None
        self.generated_result = None   # 正式 full-resolution BGR ndarray 或 None
        self.busy = False              # 是否有生成任务在跑

    # ------------------------------------------------------------------ 模式
    def set_mode(self, mode: str):
        if mode not in self._params:
            raise ValueError(f"未知模式: {mode}")
        self.current_mode = mode

    def modes(self):
        return list(MODE_ORDER)

    # ------------------------------------------------------- 全局渲染状态
    def set_color_fill(self, value: bool):
        """设置全局 Color Fill 开关（不属于任何 mode preset）。"""
        self.color_fill = bool(value)
        return self.color_fill

    def get_color_fill(self) -> bool:
        return bool(self.color_fill)

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
        """恢复当前（或指定）模式的默认 preset；**不影响**其它模式。

        注意：Color Fill 是全局画笔状态，不属于任何 mode preset，
        因此本方法**不修改** ``color_fill``（也不修改其它全局输出状态）。
        """
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
    def set_source(self, path, shape, content_digest=None):
        """打开新 source：记录路径、(h, w) 与内容指纹。"""
        self.source_path = path
        self.source_shape = (int(shape[0]), int(shape[1]))
        self.source_digest = content_digest

    @property
    def source_filename(self):
        import os
        return os.path.basename(self.source_path) if self.source_path else ""

    # ------------------------------------------------ GenerationKey / 状态判定
    def current_key(self) -> GenerationKey:
        """当前 UI 状态实时计算的 key。"""
        return GenerationKey.from_state(self, self.source_digest)

    def has_result(self) -> bool:
        return self.generated_result is not None

    def is_current(self) -> bool:
        """结果状态是否为 current（无结果 -> False）。"""
        if self.generated_result is None or self.generated_key is None:
            return False
        return self.current_key() == self.generated_key

    def is_stale(self) -> bool:
        """存在结果但 key 不一致 -> stale。"""
        return self.has_result() and not self.is_current()

    def mark_generated(self, key, result):
        """生成成功：记录 key 与正式 full-resolution 结果。"""
        self.generated_key = key
        self.generated_result = result

    def save_enabled(self) -> bool:
        """GUI-001B2 预留：Save PNG 的 enable 条件（本轮按钮仍禁用）。

        条件：result 存在 且 为 current 且 当前无生成任务。
        """
        return self.has_result() and self.is_current() and not self.busy
