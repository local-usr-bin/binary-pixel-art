"""所有候选算法共享的脚手架：灰度 -> 缩小 -> 二值化 -> nearest-neighbor 放大。

约束：
- 所有 Modern 候选用同一灰度转换、同一逻辑宽度、同一 AREA 缩小、同一 nearest 放大；
- Classic 按其文档走自己的两阶段缩放（INTER_LINEAR）与双阈值；
- 所有最终输出严格为 0/255 的 3 通道 BGR 图。
"""

import cv2
import numpy as np

from .config import (
    LOGICAL_WIDTH,
    SCALE_UP,
    DEFAULT_RESIZE,
    FINAL_RESIZE,
    CLASSIC_S,
    CLASSIC_T,
    CLASSIC_B,
)


# ---------------------------------------------------------------------------
# 灰度转换（所有 Modern 候选统一）
# ---------------------------------------------------------------------------

def to_gray(img_bgr):
    """BGR -> 单通道灰度，OpenCV 标准加权。"""
    if img_bgr.ndim == 2:
        return img_bgr
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


# ---------------------------------------------------------------------------
# 尺寸计算
# ---------------------------------------------------------------------------

def logic_size(img_shape, logical_width=LOGICAL_WIDTH):
    """按原图长宽比计算逻辑（低分辨率）尺寸 (w, h)。

    用 int() 截断（与 Classic 文档的 int(d*h/w) 一致），保证同一张输入图
    在 Classic 与所有 Modern 候选下的输出尺寸完全相同，便于 A/B 对比。
    """
    h, w = img_shape[:2]
    logical_h = max(1, int(logical_width * h / w))
    return logical_width, logical_h


def output_size(logic_shape, scale_up=SCALE_UP):
    """逻辑尺寸 -> 最终输出尺寸 (w, h)。"""
    h, w = logic_shape[:2]
    return w * scale_up, h * scale_up


# ---------------------------------------------------------------------------
# 缩小（Modern 统一：AREA）
# ---------------------------------------------------------------------------

def shrink_modern(img_gray, logical_width=LOGICAL_WIDTH, interpolation=DEFAULT_RESIZE):
    """把灰度图缩到逻辑尺寸，Modern 统一用 INTER_AREA。"""
    lw, lh = logic_size(img_gray.shape, logical_width)
    return cv2.resize(img_gray, (lw, lh), interpolation=interpolation)


# ---------------------------------------------------------------------------
# 最终放大（统一：nearest-neighbor，单通道 -> 3 通道 BGR）
# ---------------------------------------------------------------------------

def upscale_nn(img_logic_01, scale_up=SCALE_UP, interpolation=FINAL_RESIZE):
    """把逻辑二值图（单通道，0/255）放大为 3 通道 BGR 输出。"""
    out_w, out_h = output_size(img_logic_01.shape, scale_up)
    up = cv2.resize(img_logic_01, (out_w, out_h), interpolation=interpolation)
    return cv2.cvtColor(up, cv2.COLOR_GRAY2BGR)


# ---------------------------------------------------------------------------
# Classic 专用：两阶段缩放 + 双阈值（严格按 docs/classic_algorithm.md）
# ---------------------------------------------------------------------------

def classic_pipeline(img_bgr, d=LOGICAL_WIDTH, s=CLASSIC_S, t=CLASSIC_T, b=CLASSIC_B):
    """精确复现 legacy/xiangsudian.py 的语义。

    注意：该实现**忠实于文档**，包括：
      - 两阶段 resize 均用 OpenCV 默认 INTER_LINEAR；
      - 预处理默认走「灰度重读 -> equalizeHist -> 转 BGR」；
      - 第一轮只在 (偶数行, 偶数列) 位置按 t 置黑；
      - 第二轮全位置按 b 置黑，无 else，不会把已变黑的像素设回白；
      - 最终 INTER_NEAREST 放大。
    """
    # 预处理：默认 c='y'，丢弃原始颜色，直方图均衡后转三通道
    gray = to_gray(img_bgr)
    img_s_e = cv2.equalizeHist(gray)
    img_input = cv2.cvtColor(img_s_e, cv2.COLOR_GRAY2BGR)

    # 两阶段缩放（默认 INTER_LINEAR）
    h0, w0 = img_input.shape[:2]
    first = cv2.resize(img_input, (d, int(d * h0 / w0)))
    second = cv2.resize(
        first, (int(first.shape[1] / s), int(first.shape[0] / s))
    )

    # 二值画布：全白
    canvas = np.zeros(second.shape[:2] + (3,), np.uint8)
    canvas[:] = [255, 255, 255]

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

    # 第二轮：全部位置，均值 < b 置黑；无 else，不回白
    for i in range(0, H):
        for j in range(0, W):
            a = (
                int(second[i, j][0])
                + int(second[i, j][1])
                + int(second[i, j][2])
            ) / 3
            if a < b:
                canvas[i, j] = [0, 0, 0]

    # 最近邻放大回输出尺寸
    out_w, out_h = output_size(canvas.shape, SCALE_UP)
    return cv2.resize(canvas, (out_w, out_h), interpolation=cv2.INTER_NEAREST)
