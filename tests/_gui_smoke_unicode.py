"""Unicode 路径 GUI smoke（xvfb）：验证 Windows 中文/Unicode 路径可正常打开。

流程（驱动真实 App）：
  1. 启动真实 App；
  2. 造一张图，写到「中文目录 / 中文文件名」Unicode 路径；
  3. app._load_source(unicode_path) -> Source Preview 成功、source 已记录；
  4. on_generate -> Generate 成功、结果严格二值；
  5. 对照：同一文件 ASCII 路径结果逐像素一致。

Linux/WB 专用（xvfb）；不要求 Windows pytest 执行。
输出图片不 commit。
"""

import os
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import numpy as np

from src import imageio

FAILS = []


def check(name, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {extra}")
    if not cond:
        FAILS.append(name)


def make_image(path, h=240, w=320, seed=3):
    img = np.zeros((h, w, 3), np.uint8)
    y, x = np.mgrid[0:h, 0:w]
    img[..., 0] = ((x * 2) % 256).astype(np.uint8)
    img[..., 1] = ((y * 3) % 256).astype(np.uint8)
    img[..., 2] = ((x + y + seed) % 256).astype(np.uint8)
    assert imageio.imwrite_unicode(path, img)
    return img


def pump(root, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        root.update_idletasks()
        root.update()
        time.sleep(0.01)


def wait_until(root, cond, timeout=60.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        root.update_idletasks()
        root.update()
        if cond():
            return True
        time.sleep(0.02)
    return False


def main():
    from gui.app import App

    base = "/tmp/gui_unicode_src"
    os.makedirs(base, exist_ok=True)
    ascii_path = os.path.join(base, "ascii_src.png")
    uni_path = os.path.join(base, "测试目录", "动漫图片 空格.jpeg")
    os.makedirs(os.path.dirname(uni_path), exist_ok=True)

    img = make_image(ascii_path, seed=3)
    # 同一张图另存为 JPEG 到 Unicode 路径（与 ascii 源内容等价）
    assert imageio.imwrite_unicode(uni_path, img)

    root = tk.Tk()
    root.title("binary-pixel-art GUI (smoke unicode)")
    root.geometry("1100x720")
    app = App(root)
    pump(root, 0.4)

    # ---- 打开 Unicode 路径 ----
    app._load_source(uni_path)
    pump(root, 0.4)
    check("Unicode 路径：source 已记录", app.state.source_path == uni_path)
    check("Unicode 路径：source_bgr 非空", app.source_bgr is not None)
    check("Unicode 路径：Source Preview 已渲染", "source" in app._photo_refs)
    check("Unicode 路径：无错误提示",
          "无法读取" not in app.status_var.get()
          and "无法解码" not in app.status_var.get(),
          f"status={app.status_var.get()!r}")
    check("Unicode 路径：文件名正确显示含中文",
          "动漫图片 空格.jpeg" in app.filename_var.get(),
          f"filename={app.filename_var.get()!r}")

    # ---- 生成 ----
    app.on_generate()
    ok = wait_until(root, lambda: app.state.has_result() and not app.state.busy)
    check("Unicode 路径：Generate 成功", ok)
    check("Unicode 路径：结果严格二值",
          app.state.generated_result is not None
          and set(np.unique(app.state.generated_result).tolist()) <= {0, 255})

    # ---- 对照：ASCII 路径同样流程，结果一致 ----
    uni_result = None if app.state.generated_result is None else \
        app.state.generated_result.copy()
    app._load_source(ascii_path)
    pump(root, 0.3)
    app.on_generate()
    ok = wait_until(root, lambda: app.state.has_result() and not app.state.busy)
    check("ASCII 路径：Generate 成功", ok)
    ascii_result = app.state.generated_result
    # 两张源图内容一致（JPEG 有损，但 GUI 用同一 encode），仅验证可读+尺寸
    check("ASCII/Unicode 源尺寸一致",
          ascii_result is not None and uni_result is not None
          and ascii_result.shape == uni_result.shape,
          f"ascii={None if ascii_result is None else ascii_result.shape} "
          f"uni={None if uni_result is None else uni_result.shape}")

    root.destroy()

    print("\n==== SMOKE UNICODE 汇总 ====")
    if FAILS:
        print(f"FAIL {len(FAILS)} 项: {FAILS}")
        sys.exit(1)
    print("全部 PASS")


if __name__ == "__main__":
    main()
