"""全局常量（仅保留真正的全局项；各模式参数已移至 src/params.py）。"""

import cv2

# Modern 缩小插值：AREA（区域平均）。
DEFAULT_RESIZE = cv2.INTER_AREA

# 最终放大插值：nearest-neighbor（方块必须锐利）。
FINAL_RESIZE = cv2.INTER_NEAREST

# 实验候选（未进入正式模式）仍需要的固定参数。
GRAD_KERNEL = 3       # Sobel ksize
GRAD_THRESH = 30      # 梯度幅值阈值
GRAD_INVERT = True    # 轮廓黑/背景白
PATTERN_LEVELS = 5    # M5 pattern 亮度分桶数
