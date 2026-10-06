"""GUI-001B2 xvfb smoke：驱动真实 App，验证 Save PNG 接线与 enable 规则。

在 xvfb 下运行真实 App；Save As 对话框用 monkeypatch 注入临时路径
（系统对话框不适合自动交互）。验证：
  - 打开图片 -> 生成一个模式；
  - Save 从 disabled -> enabled；
  - 保存成功、文件存在、读回像素与内存 generated_result 完全一致；
  - 改参数后 stale，Save disabled；改回后 current，Save enabled；
  - worker 运行期间 Save disabled；
  - Save As cancel -> 不创建文件、状态不变；
  - Save 失败 -> 不崩溃、状态含“保存失败”。
smoke 输出图片不 commit。
"""

import os
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import numpy as np
from PIL import Image

FAILS = []


def check(name, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {extra}")
    if not cond:
        FAILS.append(name)


def make_image(path, h=480, w=640, seed=1):
    import cv2
    img = np.zeros((h, w, 3), np.uint8)
    y, x = np.mgrid[0:h, 0:w]
    base = (128 + 100 * np.sin(x / 40.0) * np.cos(y / 55.0)).astype(np.uint8)
    img[..., 0] = base
    img[..., 1] = base
    img[..., 2] = base
    cv2.circle(img, (w // 2, h // 2), min(h, w) // 4, (240, 240, 240), -1)
    cv2.imwrite(path, img)
    return path


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
    from gui import app as app_mod

    root = tk.Tk()
    root.title("binary-pixel-art GUI (smoke 001B2)")
    root.geometry("1100x720")
    app = App(root)
    pump(root, 0.4)

    tmp = "/tmp/gui_b2_src.png"
    make_image(tmp, seed=5)
    app._load_source(tmp)
    pump(root, 0.4)

    # ---- 初始：无结果 -> Save disabled ----
    check("初始 Save disabled", str(app.save_btn.cget("state")) == "disabled")

    # ---- 生成 classic ----
    app.mode_var.set("classic")
    app.on_mode_change()
    pump(root, 0.15)
    app.on_generate()
    check("worker 运行期间 Save disabled",
          str(app.save_btn.cget("state")) == "disabled")
    ok = wait_until(root, lambda: app.state.has_result() and not app.state.busy)
    check("生成完成", ok)
    check("生成后 Save enabled", str(app.save_btn.cget("state")) == "normal")

    # ---- Save：注入临时 PNG 路径 ----
    save_path = "/tmp/gui_b2_out/照 片__classic.png"
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    if os.path.exists(save_path):
        os.remove(save_path)

    app_mod.filedialog.asksaveasfilename = \
        lambda **k: save_path  # 注入：返回固定路径
    app.on_save()
    pump(root, 0.3)
    check("保存后文件存在（含中文路径）", os.path.exists(save_path))
    back = np.array(Image.open(save_path))
    mem = app.state.generated_result
    check("读回像素与内存 generated_result 逐像素一致",
          np.array_equal(back, mem[:, :, ::-1]),
          f"back={back.shape} mem={mem.shape}")
    check("保存后仍严格黑白",
          set(np.unique(back).tolist()) <= {0, 255})
    check("状态栏显示已保存", "已保存" in app.status_var.get(),
          f"status={app.status_var.get()!r}")
    check("保存后仍 current", app.state.is_current())
    check("保存后 Save 仍 enabled", str(app.save_btn.cget("state")) == "normal")

    # ---- Save As cancel：返回空串 ----
    app_mod.filedialog.asksaveasfilename = lambda **k: ""
    before_status = app.status_var.get()
    app.on_save()
    pump(root, 0.1)
    check("cancel 后状态不变", app.status_var.get() == before_status)
    check("cancel 后仍 current/enabled",
          app.state.is_current() and str(app.save_btn.cget("state")) == "normal")

    # ---- 改参数 -> stale -> Save disabled；改回 -> enabled ----
    app.t_var.set("150")
    app.on_param_change()
    pump(root, 0.15)
    check("stale 后 Save disabled", str(app.save_btn.cget("state")) == "disabled")
    app.t_var.set("127")
    app.on_param_change()
    pump(root, 0.15)
    check("改回后 Save enabled", str(app.save_btn.cget("state")) == "normal")

    # ---- Save 失败：注入不可写目录，不应崩溃 ----
    app_mod.filedialog.asksaveasfilename = \
        lambda **k: "/tmp/gui_b2_out/nope_dir/x.png"
    # 屏蔽 messagebox 弹窗（无人交互）
    app_mod.messagebox.showerror = lambda *a, **k: None
    try:
        app.on_save()
        pump(root, 0.2)
        check("保存失败未崩溃", True)
        check("保存失败状态提示", "保存失败" in app.status_var.get(),
              f"status={app.status_var.get()!r}")
        check("失败后 current result 保留", app.state.has_result())
    except Exception as e:  # noqa: BLE001
        check("保存失败未崩溃", False, str(e))

    # ---- 换模式生成再保存 ----
    app.mode_var.set("adaptive_bold")
    app.on_mode_change()
    pump(root, 0.15)
    app.on_generate()
    ok = wait_until(root, lambda: app.state.has_result() and not app.state.busy)
    p2 = "/tmp/gui_b2_out/照片__adaptive_bold.png"
    app_mod.filedialog.asksaveasfilename = lambda **k: p2
    app.on_save()
    pump(root, 0.2)
    check("adaptive_bold 保存成功且像素一致",
          os.path.exists(p2) and np.array_equal(
              np.array(Image.open(p2)), app.state.generated_result[:, :, ::-1]))

    # ---- 截图（不 commit） ----
    pump(root, 0.3)
    os.system(f"import -window {root.winfo_id()} /tmp/gui_v1_b2_smoke.png 2>/dev/null")

    root.destroy()

    print("\n==== SMOKE 001B2 汇总 ====")
    if FAILS:
        print(f"FAIL {len(FAILS)} 项: {FAILS}")
        sys.exit(1)
    print("全部 PASS")


if __name__ == "__main__":
    main()
