"""GUI-001B1 xvfb smoke：驱动真实 App，验证生成接线 / busy / stale / resize 行为。

在 xvfb 下运行，构造合成图片（写临时文件）后：
  1. 启动真实 App；
  2. 通过 _load_source 打开图片（跳过 file dialog）；
  3. 点击生成（on_generate）-> 观察 busy -> 等待完成 -> Result Preview 有结果；
  4. 改参数 -> stale；改回 -> current；
  5. 切模式 -> stale；切回 -> current；
  6. 换图 -> stale；
  7. 触发 resize（_redraw_previews）-> 确认不重跑算法（用计数器）；
  8. 截图保存。
打印 PASS/FAIL 明细，任何断言失败以非 0 退出。
"""

import os
import sys
import time
import tkinter as tk
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import cv2
import numpy as np

FAILS = []


def check(name, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {extra}")
    if not cond:
        FAILS.append(name)


def make_image(path, h=480, w=640, seed=1):
    """合成一张有结构的黑白灰图片，便于观察点阵效果。"""
    img = np.zeros((h, w, 3), np.uint8)
    rs = np.random.RandomState(seed)
    y, x = np.mgrid[0:h, 0:w]
    base = (128 + 100 * np.sin(x / 40.0) * np.cos(y / 55.0)).astype(np.uint8)
    img[..., 0] = base
    img[..., 1] = base
    img[..., 2] = base
    cv2.circle(img, (w // 2, h // 2), min(h, w) // 4, (240, 240, 240), -1)
    img = img + rs.randint(0, 20, img.shape, dtype=np.uint8)
    cv2.imwrite(path, img)
    return path


def pump(root, seconds):
    """跑 Tk 事件循环指定时长。"""
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
    from gui import app as app_mod

    # 计数后端算法调用，验证 resize / param change 不重跑算法
    call_count = {"n": 0}
    from src import algorithms

    for fname in ("classic", "bayer4", "adaptive_fine", "adaptive_bold"):
        orig = getattr(algorithms, fname)

        def make_spy(orig):
            def _spy(*a, **k):
                call_count["n"] += 1
                return orig(*a, **k)
            return _spy
        setattr(algorithms, fname, make_spy(orig))

    root = tk.Tk()
    root.title("binary-pixel-art GUI (smoke)")
    root.geometry("1100x720")
    app = App(root)
    root.update_idletasks()
    root.update()
    pump(root, 0.4)

    tmp = "/tmp/gui_smoke_src.png"
    make_image(tmp, seed=1)
    app._load_source(tmp)
    pump(root, 0.4)
    check("打开图片：source 已记录", app.state.source_path == tmp)
    check("打开图片：Source Preview 有渲染", "source" in app._photo_refs)

    # ---- 生成 ----
    before = call_count["n"]
    app.on_generate()
    # 注意：这里不 pump，立即断言 busy UI 状态，避免小图过快完成造成竞态
    check("生成期间 busy=True", app.state.busy is True)
    check("生成期间控件被禁用",
          str(app.gen_btn.cget("state")) == "disabled")
    root.update_idletasks()
    check("生成期间进度条已 grid（可见）",
          app.progress.winfo_manager() == "grid")
    # 再次点击不应启动第二个 worker
    app.on_generate()
    check("重复点击被忽略（仍单 worker）", app._worker is not None)
    ok = wait_until(root, lambda: app.state.has_result() and not app.state.busy)
    check("生成完成", ok)
    check("生成调用了后端一次", call_count["n"] == before + 1,
          f"({call_count['n']-before})")
    check("Result Preview 有渲染", "result" in app._photo_refs)
    check("生成后 current", app.state.is_current() and not app.state.is_stale())
    check("生成后 busy=False", app.state.busy is False)
    check("生成后控件恢复", str(app.gen_btn.cget("state")) == "normal")
    check("Save 仍禁用（本轮未接线）", str(app.save_btn.cget("state")) == "disabled")
    check("save_enabled 逻辑为 True（预留）", app.state.save_enabled() is True)

    # ---- 参数变化 -> stale；改回 -> current ----
    n_before = call_count["n"]
    app.t_var.set("140")
    app.on_param_change()
    pump(root, 0.2)
    check("改参数后 stale", app.state.is_stale())
    check("改参数不重跑算法", call_count["n"] == n_before)
    check("改参数保留旧结果", app.state.has_result())
    app.t_var.set("127")
    app.on_param_change()
    pump(root, 0.2)
    check("改回原值 -> current", app.state.is_current())

    # ---- 切模式 -> stale；切回 -> current ----
    app.mode_var.set("adaptive_fine")
    app.on_mode_change()
    pump(root, 0.2)
    check("切模式后 stale", app.state.is_stale())
    app.mode_var.set("classic")
    app.on_mode_change()
    pump(root, 0.2)
    check("切回原模式 -> current", app.state.is_current())

    # ---- resize 不重跑算法 ----
    n_before = call_count["n"]
    app._redraw_previews()
    pump(root, 0.3)
    check("resize 重绘不重跑算法", call_count["n"] == n_before)

    # ---- 换图 -> stale ----
    tmp2 = "/tmp/gui_smoke_src2.png"
    make_image(tmp2, seed=99)
    app._load_source(tmp2)
    pump(root, 0.3)
    check("换图后 stale", app.state.is_stale())

    # ---- 换图后重新生成，四模式各跑一次 ----
    for mode in ("classic", "bayer4", "adaptive_fine", "adaptive_bold"):
        app.mode_var.set(mode)
        app.on_mode_change()
        pump(root, 0.15)
        app.on_generate()
        ok = wait_until(root, lambda: app.state.has_result() and not app.state.busy)
        check(f"模式 {mode} 生成完成且 current",
              ok and app.state.is_current(),
              f"shape={None if app.state.generated_result is None else app.state.generated_result.shape}")

    # 截图
    pump(root, 0.4)
    try:
        wid = root.winfo_id()
        os.system(f"import -window {wid} /tmp/gui_v1_smoke.png 2>/dev/null")
    except Exception as e:  # noqa: BLE001
        print("screenshot 失败:", e)

    root.destroy()

    print("\n==== SMOKE 汇总 ====")
    if FAILS:
        print(f"FAIL {len(FAILS)} 项: {FAILS}")
        sys.exit(1)
    print("全部 PASS")


if __name__ == "__main__":
    main()
