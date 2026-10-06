"""GUI UI 辅助：preview fit / center helper（可复用）。

封装「把一张图 fit 到预览窗格并居中」的逻辑，纯函数式计算 + Tk 显示，
不改变 source / result 数据，只生成显示用的缩放副本。

- fit_dimensions：纯几何计算（可单测，不依赖 Tk）；
- render_fitted：把图像 fit+center 渲染到给定的 tk.Canvas；
- tk_photo_from_bgr / bgr_to_tk_photo：BGR ndarray -> tk.PhotoImage。
"""

import cv2
import numpy as np


def fit_dimensions(src_w, src_h, pane_w, pane_h):
    """计算把 src_w×src_h 等比 fit 进 pane_w×pane_h 的显示尺寸。

    返回 (disp_w, disp_h)，均为 >=1 的整数，保持宽高比，不放大超过原图
    （若 pane 大于原图则按原图尺寸显示，避免无意义放大；如需允许放大可解注释）。
    """
    pane_w = max(1, int(pane_w))
    pane_h = max(1, int(pane_h))
    src_w = max(1, int(src_w))
    src_h = max(1, int(src_h))

    scale = min(pane_w / src_w, pane_h / src_h)
    # 保持宽高比 fit；不强制放大（小图不撑大，避免模糊）
    if scale > 1.0:
        scale = 1.0
    disp_w = max(1, int(round(src_w * scale)))
    disp_h = max(1, int(round(src_h * scale)))
    return disp_w, disp_h


def bgr_to_tk_photo(img_bgr):
    """BGR ndarray -> tk.PhotoImage（通过 PPM 中转，避免 PIL 依赖）。

    使用 tkinter.PhotoImage 的 data= 直接加载 PPM 二进制，兼容所有 Tk。
    """
    import tkinter as tk

    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    header = f"P6\n{w} {h}\n255\n".encode("ascii")
    ppm = header + rgb.tobytes()
    return tk.PhotoImage(data=ppm, format="PPM")


def render_fitted(canvas, img_bgr, center=True, nearest=False):
    """把 img_bgr 等比 fit 并居中渲染到 tk.Canvas。

    只影响显示层：计算 pane 尺寸 -> fit_dims -> cv2.resize(display) ->
    转 PhotoImage -> 在 canvas 居中放置。返回 (photo, disp_w, disp_h) 或 None。

    nearest=True 时缩放用 INTER_NEAREST（用于二值结果，保持方块锐利）。
    调用方需持有返回的 photo 引用（Tk 不持引用会被 GC）。
    """
    if img_bgr is None:
        return None
    pane_w = canvas.winfo_width()
    pane_h = canvas.winfo_height()
    if pane_w <= 1 or pane_h <= 1:
        # 尚未布局完成，跳过本轮（resize 事件会再次触发）
        return None

    src_h, src_w = img_bgr.shape[:2]
    disp_w, disp_h = fit_dimensions(src_w, src_h, pane_w, pane_h)

    if (disp_w, disp_h) != (src_w, src_h):
        if nearest:
            interp = cv2.INTER_AREA if disp_w < src_w else cv2.INTER_NEAREST
        else:
            interp = cv2.INTER_AREA
        shown = cv2.resize(img_bgr, (disp_w, disp_h), interpolation=interp)
    else:
        shown = img_bgr

    photo = bgr_to_tk_photo(shown)
    canvas.delete("all")
    if center:
        x = max(0, (pane_w - disp_w) // 2)
        y = max(0, (pane_h - disp_h) // 2)
    else:
        x = y = 0
    canvas.create_image(x, y, anchor="nw", image=photo)
    return photo, disp_w, disp_h


def render_placeholder(canvas, text):
    """在 canvas 居中显示占位文本（用于 Result Preview 未生成状态）。"""
    pane_w = canvas.winfo_width()
    pane_h = canvas.winfo_height()
    if pane_w <= 1 or pane_h <= 1:
        return
    canvas.delete("all")
    canvas.create_text(pane_w // 2, pane_h // 2, text=text, fill="#888888")
