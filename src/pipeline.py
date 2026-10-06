"""共享脚手架：灰度 -> 缩小 -> 二值化 -> nearest-neighbor 放大。

尺寸模型统一走 src.params.compute_geometry：
  逻辑宽 = round(输出宽 / 像素块)，逻辑高 = round(逻辑宽 * 源高 / 源宽)，
  最终每个逻辑方块严格 P×P，nearest-neighbor 放大。

本模块提供：
- to_gray        BGR -> 单通道灰度
- resize_logic   把灰度图缩到 (logical_width, logical_height)，插值默认 AREA
- upscale_nn     把逻辑二值图（单通道 0/255）放大为 3 通道 BGR，方块严格 P×P
- apply_invert   仅在最终二值结果阶段执行 255 - out
"""

import cv2
import numpy as np

from .config import DEFAULT_RESIZE, FINAL_RESIZE
from .params import compute_geometry


def to_gray(img_bgr):
    """BGR -> 单通道灰度，OpenCV 标准加权。"""
    if img_bgr.ndim == 2:
        return img_bgr
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


def resize_logic(img_gray, geometry, interpolation=DEFAULT_RESIZE):
    """把灰度图缩到逻辑尺寸（geometry.logical_width × logical_height）。"""
    return cv2.resize(
        img_gray,
        (geometry.logical_width, geometry.logical_height),
        interpolation=interpolation,
    )


def upscale_nn(img_logic_01, geometry, interpolation=FINAL_RESIZE):
    """把逻辑二值图（单通道 0/255）放大为 3 通道 BGR。

    输出尺寸严格为 geometry.actual_output_width × actual_output_height，
    即 logical × pixel_block_size，因此每个逻辑方块严格 P×P。
    """
    out_w = geometry.actual_output_width
    out_h = geometry.actual_output_height
    up = cv2.resize(img_logic_01, (out_w, out_h), interpolation=interpolation)
    return cv2.cvtColor(up, cv2.COLOR_GRAY2BGR)


def apply_invert(img_bgr01):
    """仅在最终二值结果阶段做 0↔255。不反转输入、不改阈值方向。"""
    return 255 - img_bgr01
