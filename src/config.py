"""第一轮视觉实验的统一配置。

所有参数第一轮固定，不扫描。任何参数变更都在此集中记录。
"""

import cv2

# --- 统一实验条件 ---
# 逻辑宽度（缩小的目标水平像素）。选择 128：
#  1) 2 的幂，Bayer 4x4 与自定义 pattern 的 2x2/3x3 单元都能整除或近似整除，避免尾块不整；
#  2) 足够低以保留老式单色 LCD 的颗粒感，又不至于低到五官不可辨认；
#  3) 输出 1280x(按长宽比) 便于肉眼观察每个逻辑像素方块。
LOGICAL_WIDTH = 128

# 最终放大倍数（逻辑图 -> 输出图），统一用 nearest-neighbor。
SCALE_UP = 10

# 所有 Modern 候选统一的缩小插值：AREA（区域平均）。
DEFAULT_RESIZE = cv2.INTER_AREA

# 最终放大插值：nearest-neighbor。
FINAL_RESIZE = cv2.INTER_NEAREST

# --- Classic 固定参数（严格依据 docs/classic_algorithm.md） ---
CLASSIC_S = 2      # 降采样系数
CLASSIC_T = 127    # 第一轮灰度阈值
CLASSIC_B = 60     # 第二轮黑色阈值（CLI bug 导致不可改，实际固定为 60）

# --- Adaptive 系列固定参数（正式产品 + 开发基准共用 C） ---
# Adaptive Fine（正式）：Gaussian 局部阈值，细密云纹/墨线/蚀刻感
ADAPTIVE_FINE_BLOCK = 11
# Adaptive Bold（正式）：Mean 局部阈值，粗块/木刻/海报感
ADAPTIVE_BOLD_BLOCK = 25
# 两者共用的常数偏移
ADAPTIVE_C = 2

# --- M4 gradient 固定参数 ---
GRAD_KERNEL = 3       # Sobel ksize
GRAD_THRESH = 30      # 梯度幅值阈值（L2 范数），>= 该值判黑（轮廓）
GRAD_INVERT = True    # True: 轮廓黑/背景白（偏线条版）；False: 相反

# --- M5 pattern 固定参数 ---
PATTERN_LEVELS = 5    # 亮度分桶数（0..4），对应 5 档空间密度
