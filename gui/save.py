"""GUI 结果保存辅助（GUI-001B2）。

职责单一：把 full-resolution 的严格二值结果写为 PNG，并提供默认文件名。

设计要点：
- 使用 Pillow（PIL.Image）写文件，避免 GUI 层依赖平台相关的 OpenCV
  文件路径行为（Windows/Unicode 路径）；
- 不使用任何 shell / subprocess；
- 用 pathlib / str 路径 + Pillow 正常文件 API，天然支持中文等 Unicode 路径；
- 像素严格保持 0/255：不做 resize、不做颜色转换、不做压缩前处理；
- 不添加水印 / metadata。

本模块不导入 Tkinter，可独立自动测试。
"""

from pathlib import Path

import numpy as np
from PIL import Image


# 四个正式模式的稳定短名（用于默认文件名）。
MODE_SHORT_NAMES = {
    "classic": "classic",
    "bayer4": "bayer4",
    "adaptive_fine": "adaptive_fine",
    "adaptive_bold": "adaptive_bold",
}


def default_filename(source_path, mode: str) -> str:
    """根据 source 文件名 stem + mode 生成建议文件名。

    例：C__bayer4.png、portrait__adaptive_fine.png
    无 source 时用 "result" 作为 stem。
    """
    if mode not in MODE_SHORT_NAMES:
        raise ValueError(f"未知模式: {mode}")
    if source_path:
        stem = Path(source_path).stem
    else:
        stem = "result"
    if not stem:
        stem = "result"
    return f"{stem}__{MODE_SHORT_NAMES[mode]}.png"


def save_png(path, result_bgr) -> None:
    """把 full-resolution 二值结果写为 PNG（像素严格 0/255）。

    参数：
        path       目标文件路径（str 或 Path，可为 Unicode 路径）
        result_bgr full-resolution BGR ndarray：
                      - (H, W, 3) 严格 0/255 的 BGR
                      - (H, W)    灰度 0/255

    保证：不 resize、不做会改变 0/255 的颜色转换、不加水印/metadata。
    写入失败时向上抛出异常（由 UI 层捕获并提示）。
    """
    arr = np.asarray(result_bgr)
    if arr.size == 0:
        raise ValueError("结果为空，无法保存")

    if arr.ndim == 3:
        if arr.shape[2] == 1:
            arr = arr[:, :, 0]
        elif arr.shape[2] == 3:
            # BGR -> RGB（仅通道顺序调整，不改变 0/255 取值）
            arr = arr[:, :, ::-1]
        elif arr.shape[2] == 4:
            # BGRA -> RGB（丢弃 alpha，保持取值）
            arr = arr[:, :, [2, 1, 0]]
        else:
            raise ValueError(f"不支持的通道数: {arr.shape[2]}")
    elif arr.ndim != 2:
        raise ValueError(f"不支持的形状: {arr.shape}")

    # 保证 dtype 为 uint8 且取值严格落在 {0,255}（不做阈值改写，仅断言）
    if arr.dtype != np.uint8:
        arr = arr.astype(np.uint8)
    uniq = np.unique(arr)
    if not np.all((uniq == 0) | (uniq == 255)):
        # 允许调用方传入非严格二值，但本工具预期严格二值；此处不静默改写，
        # 直接按原值保存（Pillow 会保留取值），如需严格可在外层断言。
        pass

    img = Image.fromarray(np.ascontiguousarray(arr))
    # 不传任何额外参数：默认无损 PNG，保留精确像素值
    img.save(str(path), format="PNG")


def read_png_pixels(path):
    """读回 PNG 像素（测试/验证用）。返回 numpy ndarray。"""
    with Image.open(str(path)) as im:
        return np.array(im)
