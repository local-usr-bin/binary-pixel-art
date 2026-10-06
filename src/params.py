"""参数契约与尺寸模型。

统一尺寸模型（四模式共用）：

    logical_width  = max(1, round(requested_output_width / P))
    actual_output_width  = logical_width * P
    logical_height = max(1, round(logical_width * source_h / source_w))
    actual_output_height = logical_height * P

其中 P 为像素块边长，最终每个逻辑方块严格为 P×P，不使用非整数倍率拉伸；
长宽比在整数逻辑网格上做最接近近似（不声称"绝对不变"）。

术语约定：
- `requested_output_width`：用户请求的**目标宽度**（可能不是 P 的整数倍）。
- `actual_output_width`：实际输出宽度，恒为 P 的整数倍；当目标宽度不可被 P 整除时，
  会吸附到最近的 P 整数倍，与目标宽度相差约 ±(P-1) px（有意产品化行为）。

本模块只做纯函数式的尺寸计算、默认 preset 与参数校验，不接触 cv2，
也不做任何图像处理。
"""

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# 尺寸模型
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Geometry:
    """一次请求的尺寸结果，供上层（GUI）回显。"""
    requested_output_width: int
    pixel_block_size: int
    logical_width: int
    logical_height: int
    actual_output_width: int
    actual_output_height: int


def compute_geometry(source_width, source_height, requested_output_width, pixel_block_size):
    """按统一尺寸模型计算几何参数。

    source_width/source_height 为原图（或灰度源）宽高，单位像素。
    """
    if requested_output_width < 1:
        raise ValueError("requested_output_width 必须 >= 1")
    if pixel_block_size < 1:
        raise ValueError("pixel_block_size 必须 >= 1")

    P = pixel_block_size
    logical_width = max(1, round(requested_output_width / P))
    logical_height = max(1, round(logical_width * source_height / source_width))
    return Geometry(
        requested_output_width=requested_output_width,
        pixel_block_size=P,
        logical_width=logical_width,
        logical_height=logical_height,
        actual_output_width=logical_width * P,
        actual_output_height=logical_height * P,
    )


# ---------------------------------------------------------------------------
# 默认 preset（按模式保存；保持已人工验收的默认视觉结果）
# ---------------------------------------------------------------------------

# 每个模式的默认输出宽度 / 像素块大小（geometry 部分）。
DEFAULT_GEOMETRY = {
    "classic": {"output_width": 1000, "pixel_block_size": 2},
    "bayer4": {"output_width": 1280, "pixel_block_size": 10},
    "adaptive_fine": {"output_width": 1280, "pixel_block_size": 10},
    "adaptive_bold": {"output_width": 1280, "pixel_block_size": 10},
}

# Classic 祖传默认参数。
CLASSIC_DEFAULT_T = 127
CLASSIC_DEFAULT_B = 60
CLASSIC_DEFAULT_EQUALIZE = True

# Bayer 默认参数。
BAYER_DEFAULT_MATRIX = 4
BAYER_DEFAULT_TONE_BIAS = 0

# Adaptive 默认参数（Fine / Bold 的 blockSize 不同，C 相同）。
ADAPTIVE_DEFAULT_C = 2
ADAPTIVE_FINE_DEFAULT_BLOCK = 11
ADAPTIVE_BOLD_DEFAULT_BLOCK = 25


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def validate_classic_thresholds(t, b):
    """t / b 为整数 0..255；b>=t 合法（偏离经典三档语义但允许），不拒绝。"""
    t = int(t)
    b = int(b)
    if not (0 <= t <= 255):
        raise ValueError(f"t 必须在 0..255，得到 {t}")
    if not (0 <= b <= 255):
        raise ValueError(f"b 必须在 0..255，得到 {b}")
    return t, b


def validate_matrix_size(matrix_size):
    """Bayer 矩阵尺寸，只允许 2 / 4 / 8。"""
    if matrix_size not in (2, 4, 8):
        raise ValueError(f"matrix_size 只允许 2/4/8，得到 {matrix_size}")
    return matrix_size


def validate_tone_bias(tone_bias):
    """tone_bias 为整数，建议范围 -128..128（此处不强制，仅作 API 层约定）。"""
    return int(tone_bias)


def validate_adaptive_block(block_size):
    """OpenCV adaptiveThreshold 硬约束：blockSize 为奇数且 >= 3。

    不实现 blockSize <= min(logical_width, logical_height) 的硬限制：
    OpenCV 会用边界扩展处理邻域，blockSize 大于图像某一边本身并非非法调用。
    """
    block_size = int(block_size)
    if block_size < 3:
        raise ValueError(f"blockSize 必须 >= 3，得到 {block_size}")
    if block_size % 2 != 1:
        raise ValueError(f"blockSize 必须为奇数，得到 {block_size}")
    return block_size


def validate_adaptive_c(c):
    """C 为整数；允许正/零/负，API 层不拒绝。"""
    return int(c)
