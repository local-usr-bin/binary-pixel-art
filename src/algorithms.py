"""二值艺术算法实现。

正式产品模式见文件末尾 FORMAL_MODES（classic / bayer4 / adaptive_fine /
adaptive_bold），均已参数化。其余函数（m1_otsu / m3_adaptive / m4_gradient /
m5_pattern）为实验或开发基准实现，不进正式列表。

统一入口约定：
  传入 BGR 原图，返回 3 通道 BGR 严格黑白图（0/255）。
  尺寸统一走 src.params.compute_geometry（输出宽度 + 像素块大小），
  最终 nearest-neighbor 放大，方块严格 P×P。

重要回归约束：
  各模式使用默认参数时，必须与已人工验收的历史实现逐像素一致。
"""

import cv2
import numpy as np

from .config import GRAD_KERNEL, GRAD_THRESH, GRAD_INVERT, PATTERN_LEVELS
from .params import (
    compute_geometry,
    validate_classic_thresholds,
    validate_matrix_size,
    validate_tone_bias,
    validate_adaptive_block,
    validate_adaptive_c,
    CLASSIC_DEFAULT_T,
    CLASSIC_DEFAULT_B,
    CLASSIC_DEFAULT_EQUALIZE,
    BAYER_DEFAULT_MATRIX,
    BAYER_DEFAULT_TONE_BIAS,
    ADAPTIVE_DEFAULT_C,
    ADAPTIVE_FINE_DEFAULT_BLOCK,
    ADAPTIVE_BOLD_DEFAULT_BLOCK,
)
from .pipeline import to_gray, resize_logic, upscale_nn, apply_invert


# ---------------------------------------------------------------------------
# 经典 Bayer 矩阵构造（递归定义，2/4/8 均唯一确定）
# ---------------------------------------------------------------------------

def build_bayer_matrix(n):
    """按标准递归构造 n×n Bayer 矩阵，n 仅支持 2/4/8。

    递归：B(2n) = [[4B, 4B+2], [4B+3, 4B+1]]，B(1)=[[0]]，值域 0..n^2-1。
    产生的 4×4 与历史手写矩阵逐像素一致。
    """
    n = validate_matrix_size(n)
    b = np.array([[0]], dtype=np.int64)
    size = 1
    while size < n:
        b = np.block(
            [
                [4 * b, 4 * b + 2],
                [4 * b + 3, 4 * b + 1],
            ]
        )
        size *= 2
    return b


# ---------------------------------------------------------------------------
# Classic（正式）
# ---------------------------------------------------------------------------

def classic(
    img_bgr,
    output_width=1000,
    pixel_block_size=2,
    t=CLASSIC_DEFAULT_T,
    b=CLASSIC_DEFAULT_B,
    equalize=CLASSIC_DEFAULT_EQUALIZE,
    invert=False,
):
    """Classic：复刻 legacy/xiangsudian.py 的算法语义，已参数化并统一几何。

    - output_width 为目标宽度（requested_output_width），映射为 Classic 的 d；
      当它不能被 pixel_block_size 整除时，实际输出宽度吸附到最近的 P 整数倍
      （见 src.params.compute_geometry，intentional divergence，非逐字节复刻 Legacy）；
    - pixel_block_size 映射为 s；
    - t/b 为整数 0..255，b>=t 合法不拒绝；
    - equalize 默认 True（祖传默认直方图均衡）；
    - invert 仅在最终二值结果阶段 0↔255。

    几何统一：宽高均走 compute_geometry，输出严格 P×P（actual = logical × s），
    每个逻辑方块严格 s×s。两阶段缩放均用 OpenCV 默认 INTER_LINEAR；
    第一轮 (偶,偶) 且 a<t 置黑；第二轮全位置 a<b 置黑、无 else；最终 INTER_NEAREST 放大。

    与 Legacy 的几何差异（intentional divergence）：Legacy 用 int() 截断且输出高
    = int(d*h0/w0)，而本实现宽高均为 P 整数倍，故在多数源图（含默认参数）下与
    Legacy 存在约 ±1 px 高度差异。算法语义（均衡/两阶段缩放/双阈值/网点密度）不变。
    """
    t, b = validate_classic_thresholds(t, b)

    # 预处理：直方图均衡（默认开，丢弃彩色）
    if equalize:
        gray = to_gray(img_bgr)
        img_s_e = cv2.equalizeHist(gray)
        img_input = cv2.cvtColor(img_s_e, cv2.COLOR_GRAY2BGR)
    else:
        img_input = img_bgr

    h0, w0 = img_input.shape[:2]

    # 几何：宽高均统一 P×P（actual = logical × s）
    geo = compute_geometry(w0, h0, output_width, pixel_block_size)
    s = geo.pixel_block_size
    actual_w = geo.actual_output_width
    actual_h = geo.actual_output_height
    logical_w = geo.logical_width
    logical_h = geo.logical_height

    # 两阶段缩放（默认 INTER_LINEAR）：先到 actual 尺寸，再到 logical 尺寸（÷s）
    first = cv2.resize(img_input, (actual_w, actual_h))
    second = cv2.resize(first, (logical_w, logical_h))

    # 二值画布：全白
    canvas = np.full(second.shape[:2] + (3,), 255, np.uint8)
    H, W = second.shape[:2]

    # 第一轮：偶数行、偶数列，均值 < t 置黑
    for i in range(0, H, 2):
        for j in range(0, W, 2):
            a = (
                int(second[i, j][0])
                + int(second[i, j][1])
                + int(second[i, j][2])
            ) / 3
            if a < t:
                canvas[i, j] = [0, 0, 0]

    # 第二轮：全部位置，均值 < b 置黑；无 else
    for i in range(H):
        for j in range(W):
            a = (
                int(second[i, j][0])
                + int(second[i, j][1])
                + int(second[i, j][2])
            ) / 3
            if a < b:
                canvas[i, j] = [0, 0, 0]

    # 最近邻放大回最终输出尺寸（严格 P×P）
    out = cv2.resize(canvas, (actual_w, actual_h), interpolation=cv2.INTER_NEAREST)
    if invert:
        out = apply_invert(out)
    return out


# ---------------------------------------------------------------------------
# Bayer（正式）
# ---------------------------------------------------------------------------

def bayer4(
    img_bgr,
    output_width=1280,
    pixel_block_size=10,
    matrix_size=BAYER_DEFAULT_MATRIX,
    tone_bias=BAYER_DEFAULT_TONE_BIAS,
    invert=False,
):
    """Bayer 有序抖动，已参数化。

    - matrix_size 支持 2/4/8（标准递归构造），默认 4；
    - tone_bias：在 Bayer 阈值前做 clip(gray + bias, 0, 255)，deterministic；
    - invert 仅在最终二值结果阶段。

    回归：matrix_size=4、tone_bias=0 时与历史 bayer4 逐像素一致。
    """
    matrix_size = validate_matrix_size(matrix_size)
    tone_bias = validate_tone_bias(tone_bias)

    gray = to_gray(img_bgr)
    h0, w0 = gray.shape[:2]
    geo = compute_geometry(w0, h0, output_width, pixel_block_size)
    small = resize_logic(gray, geo)

    # tone bias：进入阈值前均匀亮度偏置
    if tone_bias != 0:
        small = np.clip(small.astype(np.int32) + tone_bias, 0, 255).astype(np.uint8)

    h, w = small.shape
    bayer = build_bayer_matrix(matrix_size).astype(np.float32)
    # 把矩阵 0..(n^2-1) 映射到 0..255 灰度域
    bayer = bayer * (255.0 / (matrix_size * matrix_size - 1))
    tiled = np.tile(bayer, ((h + matrix_size - 1) // matrix_size,
                            (w + matrix_size - 1) // matrix_size))[:h, :w]
    bw = np.where(small.astype(np.float32) > tiled, 255, 0).astype(np.uint8)

    out = upscale_nn(bw, geo)
    if invert:
        out = apply_invert(out)
    return out


# ---------------------------------------------------------------------------
# Adaptive Fine / Bold（正式）
# ---------------------------------------------------------------------------

def _adaptive(
    img_bgr,
    output_width,
    pixel_block_size,
    block_size,
    c,
    method,
    invert,
):
    """Adaptive 阈值通用实现（Gaussian/Mean 由 method 决定）。"""
    block_size = validate_adaptive_block(block_size)
    c = validate_adaptive_c(c)

    gray = to_gray(img_bgr)
    h0, w0 = gray.shape[:2]
    geo = compute_geometry(w0, h0, output_width, pixel_block_size)
    small = resize_logic(gray, geo)

    bw = cv2.adaptiveThreshold(
        small, 255, method, cv2.THRESH_BINARY, block_size, c
    )
    out = upscale_nn(bw, geo)
    if invert:
        out = apply_invert(out)
    return out


def adaptive_fine(
    img_bgr,
    output_width=1280,
    pixel_block_size=10,
    block_size=ADAPTIVE_FINE_DEFAULT_BLOCK,
    c=ADAPTIVE_DEFAULT_C,
    invert=False,
):
    """Adaptive Fine（正式）：Gaussian 固定，默认 block=11, C=2。"""
    return _adaptive(
        img_bgr, output_width, pixel_block_size, block_size, c,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, invert,
    )


def adaptive_bold(
    img_bgr,
    output_width=1280,
    pixel_block_size=10,
    block_size=ADAPTIVE_BOLD_DEFAULT_BLOCK,
    c=ADAPTIVE_DEFAULT_C,
    invert=False,
):
    """Adaptive Bold（正式）：Mean 固定，默认 block=25, C=2。"""
    return _adaptive(
        img_bgr, output_width, pixel_block_size, block_size, c,
        cv2.ADAPTIVE_THRESH_MEAN_C, invert,
    )


# ---------------------------------------------------------------------------
# 实验 / 开发基准实现（不进入正式模式）
# ---------------------------------------------------------------------------

def m1_otsu(img_bgr, output_width=1280, pixel_block_size=10):
    gray = to_gray(img_bgr)
    h0, w0 = gray.shape[:2]
    geo = compute_geometry(w0, h0, output_width, pixel_block_size)
    small = resize_logic(gray, geo)
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return upscale_nn(bw, geo)


def m3_adaptive(img_bgr, output_width=1280, pixel_block_size=10):
    """[开发基准，非正式] Mean 局部阈值，block=11, C=2。"""
    return _adaptive(
        img_bgr, output_width, pixel_block_size,
        ADAPTIVE_FINE_DEFAULT_BLOCK, ADAPTIVE_DEFAULT_C,
        cv2.ADAPTIVE_THRESH_MEAN_C, False,
    )


def m4_gradient(img_bgr, output_width=1280, pixel_block_size=10):
    gray = to_gray(img_bgr)
    h0, w0 = gray.shape[:2]
    geo = compute_geometry(w0, h0, output_width, pixel_block_size)
    small = resize_logic(gray, geo)
    gx = cv2.Sobel(small, cv2.CV_64F, 1, 0, ksize=GRAD_KERNEL)
    gy = cv2.Sobel(small, cv2.CV_64F, 0, 1, ksize=GRAD_KERNEL)
    mag = np.sqrt(gx * gx + gy * gy)
    edge = mag >= GRAD_THRESH
    bw = np.where(edge, 0, 255).astype(np.uint8) if GRAD_INVERT else np.where(edge, 255, 0).astype(np.uint8)
    return upscale_nn(bw, geo)


# 5 档空间密度图案（2x2），刻意不用标准 Bayer 2x2。
_PATTERN_2x2 = [
    np.array([[0, 0], [0, 0]], np.uint8),
    np.array([[1, 0], [0, 0]], np.uint8),
    np.array([[1, 0], [0, 1]], np.uint8),
    np.array([[1, 1], [0, 1]], np.uint8),
    np.array([[1, 1], [1, 1]], np.uint8),
]


def m5_pattern(img_bgr, output_width=1280, pixel_block_size=10):
    gray = to_gray(img_bgr)
    h0, w0 = gray.shape[:2]
    geo = compute_geometry(w0, h0, output_width, pixel_block_size)
    small = resize_logic(gray, geo)
    h, w = small.shape
    level = np.clip(np.round(small.astype(np.float32) / 255.0 * (PATTERN_LEVELS - 1)), 0, PATTERN_LEVELS - 1).astype(np.uint8)
    pat = np.zeros((h * 2, w * 2), np.uint8)
    for i in range(h):
        for j in range(w):
            blk = _PATTERN_2x2[level[i, j]]
            pat[i * 2:i * 2 + 2, j * 2:j * 2 + 2] = np.where(blk == 1, 0, 255).astype(np.uint8)
    # 图案承载层是逻辑网格的 2 倍，最终仍放大到 actual_output 尺寸（方块 P×P）
    out = cv2.resize(pat, (geo.actual_output_width, geo.actual_output_height), interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


# ---------------------------------------------------------------------------
# 正式产品算法注册表
# ---------------------------------------------------------------------------

FORMAL_MODES = (
    ("classic", classic),
    ("bayer4", bayer4),
    ("adaptive_fine", adaptive_fine),
    ("adaptive_bold", adaptive_bold),
)
