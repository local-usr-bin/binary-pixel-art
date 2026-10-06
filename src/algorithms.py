"""二值艺术算法实现。

正式产品模式见文件末尾 FORMAL_MODES（classic / bayer4 / adaptive_fine /
adaptive_bold）。其余函数为实验阶段或开发基准实现，保留供回归对照，
不进入正式算法列表。

统一入口约定：传入 BGR 原图，返回 3 通道 BGR 严格黑白图（0/255）。
除 Classic 外，所有 Modern 实现共用：
  - 同一灰度转换（to_gray）
  - 同一逻辑宽度 LOGICAL_WIDTH
  - 同一 AREA 缩小（shrink_modern）
  - 同一 nearest-neighbor 放大（upscale_nn）
"""

import cv2
import numpy as np

from .config import (
    ADAPTIVE_FINE_BLOCK,
    ADAPTIVE_BOLD_BLOCK,
    ADAPTIVE_C,
    GRAD_KERNEL,
    GRAD_THRESH,
    GRAD_INVERT,
    PATTERN_LEVELS,
)
from .pipeline import (
    to_gray,
    shrink_modern,
    upscale_nn,
    classic_pipeline,
    output_size,
)
from .config import SCALE_UP, FINAL_RESIZE, LOGICAL_WIDTH, CLASSIC_S


# ---------------------------------------------------------------------------
# Classic（基准）
# ---------------------------------------------------------------------------

def classic(img_bgr):
    """Classic 精确复现，见 src/pipeline.classic_pipeline。

    Classic 语义中 d 是「第一阶段缩到的宽度」，逻辑网格再除以 s（=2）。
    为让 Classic 的逻辑网格与 Modern 候选一致（宽 = LOGICAL_WIDTH），
    此处传 d = LOGICAL_WIDTH * 2，使第一阶段缩到 2*LOGICAL_WIDTH、
    第二阶段 ÷s 后逻辑网格宽 = LOGICAL_WIDTH，最终输出与其它候选同尺寸。
    这不改变 Classic 语义，只是按其实际缩放结构对齐逻辑分辨率。
    """
    return classic_pipeline(img_bgr, d=LOGICAL_WIDTH * CLASSIC_S)


# ---------------------------------------------------------------------------
# M1: AREA + Otsu
# ---------------------------------------------------------------------------

def m1_otsu(img_bgr):
    gray = to_gray(img_bgr)
    small = shrink_modern(gray)
    _, bw = cv2.threshold(
        small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return upscale_nn(bw)


# ---------------------------------------------------------------------------
# M2: AREA + Bayer 4x4 ordered dithering
# ---------------------------------------------------------------------------

_BAYER_4 = np.array(
    [
        [0, 8, 2, 10],
        [12, 4, 14, 6],
        [3, 11, 1, 9],
        [15, 7, 13, 5],
    ],
    dtype=np.uint8,
)


def m2_bayer4(img_bgr):
    gray = to_gray(img_bgr)
    small = shrink_modern(gray)
    h, w = small.shape
    # 标准 Bayer 阈值：把 0..15 矩阵映射到 0..255 灰度域
    bayer = _BAYER_4.astype(np.float32) * (255.0 / 15.0)
    tiled = np.tile(bayer, ((h + 3) // 4, (w + 3) // 4))[:h, :w]
    bw = np.where(small.astype(np.float32) > tiled, 255, 0).astype(np.uint8)
    return upscale_nn(bw)


# ---------------------------------------------------------------------------
# Adaptive Fine / Adaptive Bold（正式产品模式）
# ---------------------------------------------------------------------------

def adaptive_fine(img_bgr):
    """Adaptive Fine（正式）：Gaussian 局部阈值。

    参数固定：ADAPTIVE_THRESH_GAUSSIAN_C, blockSize=ADAPTIVE_FINE_BLOCK(11),
    C=ADAPTIVE_C(2)。艺术特征：细密、漫画墨线、雕版/蚀刻/刻线感。
    源自第二轮实验的 m3_alt_method。
    """
    gray = to_gray(img_bgr)
    small = shrink_modern(gray)
    bw = cv2.adaptiveThreshold(
        small,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        ADAPTIVE_FINE_BLOCK,
        ADAPTIVE_C,
    )
    return upscale_nn(bw)


def adaptive_bold(img_bgr):
    """Adaptive Bold（正式）：Mean 局部阈值。

    参数固定：ADAPTIVE_THRESH_MEAN_C, blockSize=ADAPTIVE_BOLD_BLOCK(25),
    C=ADAPTIVE_C(2)。艺术特征：粗块、主体感强、木刻/海报感。
    源自第二轮实验的 m3_large_window。
    """
    gray = to_gray(img_bgr)
    small = shrink_modern(gray)
    bw = cv2.adaptiveThreshold(
        small,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        ADAPTIVE_BOLD_BLOCK,
        ADAPTIVE_C,
    )
    return upscale_nn(bw)


# ---------------------------------------------------------------------------
# m3_adaptive：第一轮实验的原始 adaptive 实现（开发/历史基准）
# 不进入正式产品模式，仅保留作内部开发对照与回归参考。
# ---------------------------------------------------------------------------

def m3_adaptive(img_bgr):
    """[开发基准，非正式模式] Mean 局部阈值，block=11, C=2。

    第一轮实验选 mean 的理由：高斯权重在高对比细线处容易把线拉成断点，
    mean 对窗口内像素一视同仁，更能保住大色块内部一致性。
    """
    gray = to_gray(img_bgr)
    small = shrink_modern(gray)
    bw = cv2.adaptiveThreshold(
        small,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        ADAPTIVE_FINE_BLOCK,
        ADAPTIVE_C,
    )
    return upscale_nn(bw)


# ---------------------------------------------------------------------------
# M4: Gradient / Edge Driven
# ---------------------------------------------------------------------------

def m4_gradient(img_bgr):
    """Sobel 梯度幅值 -> 阈值二值化。

    规则：
      1. 缩小到逻辑分辨率后，对灰度图分别做 x/y 方向 Sobel（ksize=3）；
      2. 幅值用 L2 范数 sqrt(gx^2 + gy^2)；
      3. 幅值 >= GRAD_THRESH 判为「结构」（黑），否则白；
      4. 若 GRAD_INVERT=True 则轮廓黑/背景白（偏线条版）。
    第一轮固定 ksize=3, thresh=30，不扫描。
    """
    gray = to_gray(img_bgr)
    small = shrink_modern(gray)
    gx = cv2.Sobel(small, cv2.CV_64F, 1, 0, ksize=GRAD_KERNEL)
    gy = cv2.Sobel(small, cv2.CV_64F, 0, 1, ksize=GRAD_KERNEL)
    mag = np.sqrt(gx * gx + gy * gy)
    edge = mag >= GRAD_THRESH
    if GRAD_INVERT:
        bw = np.where(edge, 0, 255).astype(np.uint8)
    else:
        bw = np.where(edge, 255, 0).astype(np.uint8)
    return upscale_nn(bw)


# ---------------------------------------------------------------------------
# M5: Custom Pattern Mapping（自定义图案映射）
# ---------------------------------------------------------------------------

# 5 档空间密度图案（2x2 单元），从全白到全黑：
#   level 0: 全白
#   level 1: 左上 1 黑 / 4
#   level 2: 对角 2 黑 / 4
#   level 3: 右上+左下+右下 3 黑 / 4
#   level 4: 全黑
#
# 图案刻意不用标准 Bayer 2x2（Bayer 2x2 的顺序是 0,2 / 3,1），
# 这里用「先角后边」的填充顺序，让低密度时黑点更孤立、高密度时呈块状。
_PATTERN_2x2 = [
    np.array([[0, 0], [0, 0]], np.uint8),          # 全白
    np.array([[1, 0], [0, 0]], np.uint8),          # 1/4 黑
    np.array([[1, 0], [0, 1]], np.uint8),          # 2/4 对角黑
    np.array([[1, 1], [0, 1]], np.uint8),          # 3/4 黑
    np.array([[1, 1], [1, 1]], np.uint8),          # 全黑
]


def m5_pattern(img_bgr):
    """自定义 pattern mapping。

    流程：
      1. 把灰度图缩到统一逻辑宽度 LOGICAL_WIDTH（与其它候选一致）；
      2. 把 0..255 亮度线性映射到 0..(PATTERN_LEVELS-1) 共 5 档；
      3. 每个逻辑像素按档位查 2x2 黑白小图案，在**同一逻辑网格的 2 倍
         承载层**上展开（每个逻辑像素 -> 2x2），形成带图案纹理的二值图；
      4. 该承载层分辨率是逻辑分辨率的 2 倍，再用 nearest-neighbor 放大
         到与其它候选一致的最终输出尺寸（SCALE_UP 按逻辑网格计算），
         因此每个输出逻辑像素在成品上是一个带 2x2 纹理的方块。
    第一轮固定 5 档、2x2 单元，不做内容感知开关。
    """
    gray = to_gray(img_bgr)
    small = shrink_modern(gray)  # (LOGICAL_WIDTH, 按长宽比)
    h, w = small.shape
    # 亮度分桶：均匀映射到 0..4
    level = (small.astype(np.float32) / 255.0) * (PATTERN_LEVELS - 1)
    level = np.clip(np.round(level), 0, PATTERN_LEVELS - 1).astype(np.uint8)

    # 在同一逻辑网格的 2 倍承载层上展开图案：每个逻辑像素 -> 2x2
    pat = np.zeros((h * 2, w * 2), np.uint8)
    for i in range(h):
        for j in range(w):
            blk = _PATTERN_2x2[level[i, j]]
            pat[i * 2 : i * 2 + 2, j * 2 : j * 2 + 2] = np.where(
                blk == 1, 0, 255
            ).astype(np.uint8)

    # 承载层是逻辑网格的 2 倍，最终输出尺寸要与其它候选一致：
    # 其它候选输出 = LOGICAL_WIDTH*SCALE_UP 宽，故此处放大倍数 = SCALE_UP/2。
    out_w, out_h = output_size(small.shape, SCALE_UP)
    up = cv2.resize(pat, (out_w, out_h), interpolation=FINAL_RESIZE)
    return cv2.cvtColor(up, cv2.COLOR_GRAY2BGR)


# ---------------------------------------------------------------------------
# 正式产品算法注册表
# 当前正式模式只有这 4 种；其余函数（m1_otsu / m3_adaptive / m4_gradient /
# m5_pattern）为实验阶段或开发基准实现，不在此列。
# ---------------------------------------------------------------------------

FORMAL_MODES = (
    ("classic", classic),
    ("bayer4", m2_bayer4),
    ("adaptive_fine", adaptive_fine),
    ("adaptive_bold", adaptive_bold),
)
