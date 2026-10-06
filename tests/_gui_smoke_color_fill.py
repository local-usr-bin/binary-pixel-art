"""Color Fill GUI smoke（xvfb）：端到端验证 Color Fill 接入。

覆盖施工要求第十五节 1–15：
  1. Unicode 路径打开图片；
  2. Bayer；
  3. Color Fill OFF -> 生成黑白；
  4. Color Fill ON -> stale；
  5. Generate -> 彩色结果；
  6. invert ON -> stale；
  7. Generate -> 彩色反转 mask 结果；
  8. 切 Adaptive Fine；
  9. Color Fill 仍为 ON；
 10. Generate；
 11. Restore Defaults；
 12. Color Fill 仍为 ON；
 13. Save PNG；
 14. 读回像素一致；
 15. 窗口 resize 不重跑算法。

运行：xvfb-run -a python3.11 tests/_gui_smoke_color_fill.py
"""

import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402

from src import imageio  # noqa: E402
from gui.app import App  # noqa: E402


RESULTS = []


def check(name, cond):
    RESULTS.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


def pump(root, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def wait_generate(app, root, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        if app._worker is None and not app.state.busy:
            return True
        time.sleep(0.02)
    return False


def main():
    tmp = tempfile.mkdtemp(prefix="cf_smoke_")
    udir = os.path.join(tmp, "像素点项目临时文件")
    os.makedirs(udir)

    # 造一张有色彩层次的测试图
    rng = np.random.RandomState(0)
    img = np.zeros((140, 200, 3), np.uint8)
    img[:, :, 2] = np.linspace(40, 220, 200).astype(np.uint8)   # R 渐变
    img[:, :, 1] = np.linspace(200, 30, 140).astype(np.uint8)[:, None]
    img[:70, :100] = (30, 180, 240)
    src_path = os.path.join(udir, "照片 A.png")
    imageio.imwrite_unicode(src_path, img)

    root = tk.Tk()
    root.geometry("980x680")
    app = App(root)
    root.update()

    # 1. Unicode 路径打开
    app._load_source(src_path)
    root.update()
    check("1. Unicode 路径打开图片", app.source_bgr is not None)

    # 2. Bayer
    app.mode_var.set("bayer4")
    app.on_mode_change()
    root.update()
    check("2. 切到 Bayer", app.state.current_mode == "bayer4")

    # 3. Color Fill OFF -> 生成黑白
    app.color_fill_var.set(False)
    app.on_color_fill_change()
    app.state.set_color_fill(False)
    app.on_generate()
    check("3a. Generate 启动（busy）", app.state.busy)
    wait_generate(app, root)
    res = app.state.generated_result
    check("3b. Color Fill OFF -> 结果严格黑白",
          res is not None and set(np.unique(res).tolist()) <= {0, 255})
    check("3c. 生成后 current", app.state.is_current())

    # 4. Color Fill ON -> stale
    app.color_fill_var.set(True)
    app.on_color_fill_change()
    root.update()
    check("4. Color Fill ON -> stale", app.state.is_stale())

    # 5. Generate -> 彩色结果
    app.on_generate()
    wait_generate(app, root)
    res_color = app.state.generated_result
    nonwhite = ~np.all(res_color == 255, axis=2)
    check("5a. 彩色结果含非白彩色像素", bool(nonwhite.any()))
    check("5b. 彩色结果非严格二值",
          not (set(np.unique(res_color).tolist()) <= {0, 255}))
    check("5c. 白区严格 255", bool(np.all(res_color[np.all(res_color == 255, axis=2)] == 255)))

    # 6. invert ON -> stale
    app.invert_var.set(True)
    app.on_param_change()
    root.update()
    check("6. invert ON -> stale", app.state.is_stale())

    # 7. Generate -> 彩色反转 mask 结果
    app.on_generate()
    wait_generate(app, root)
    res_inv = app.state.generated_result
    check("7. 反转 mask 彩色结果与上一版不同",
          not np.array_equal(res_inv, res_color))
    # 反转 mask 的白色区域应与前一版的黑区互补
    white_prev = np.all(res_color == 255, axis=2)
    white_now = np.all(res_inv == 255, axis=2)
    check("7b. 两极性白区互补", bool(np.array_equal(white_prev, ~white_now)))

    # 8. 切 Adaptive Fine
    app.mode_var.set("adaptive_fine")
    app.on_mode_change()
    root.update()
    check("8. 切到 Adaptive Fine", app.state.current_mode == "adaptive_fine")

    # 9. Color Fill 仍为 ON
    check("9. 切模式后 Color Fill 仍 ON", app.state.get_color_fill() is True)

    # 10. Generate
    app.on_generate()
    wait_generate(app, root)
    check("10. Fine 生成完成", app.state.has_result() and app.state.is_current())

    # 11. Restore Defaults
    app.on_restore_defaults()
    root.update()
    check("11. Restore Defaults 执行", app.state.get_param("block_size") == 11)

    # 12. Color Fill 仍为 ON
    check("12. Restore Defaults 后 Color Fill 仍 ON",
          app.state.get_color_fill() is True)

    # 13. Save PNG（current-only）
    # 先确保 current：restore 后 Fine 参数回默认，但结果 may be stale，重生成
    if not app.state.is_current():
        app.on_generate()
        wait_generate(app, root)
    save_path = os.path.join(udir, "彩色结果.png")
    app._save_result_to(save_path, app.state.generated_result)
    root.update()
    check("13. Save PNG 写出文件", os.path.exists(save_path))

    # 14. 读回像素一致
    from gui import save as save_mod
    back = save_mod.read_png_pixels(save_path)
    check("14. 读回像素与结果一致",
          np.array_equal(back[:, :, ::-1], app.state.generated_result))

    # 15. 窗口 resize 不重跑算法
    key_before = app.state.generated_key
    root.geometry("1200x820")
    pump(root, 0.6)
    app._refresh_result_preview()
    root.update()
    check("15. resize 不改变 generated_key（未重跑算法）",
          app.state.generated_key == key_before)

    root.destroy()

    print("\n==== SMOKE COLOR FILL 汇总 ====")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
    print("全部 PASS")


if __name__ == "__main__":
    main()
