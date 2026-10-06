"""blockSize Spinbox 直接编辑 smoke（xvfb）。

复现并验证修复：当前值 13，全选后直接键入 9，最终应为 9（不是 113/139/913）。

真实键盘序列难以在无头环境重放，这里用与 Tk Entry 等价的编辑原语：
  entry.selection_range(0, END)  -> 全选
  entry.delete(0, END)           -> 全选后键入会先删除选区（Tk 内部行为）
  entry.insert(0, "9")           -> 键入新字符
中间态（空串/中间数字）应被允许，commit（此处用 FocusOut 等价：直接调用
_commit_block_size）后合法化。

Linux/WB 专用；不要求 Windows pytest 执行。
"""

import os
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

FAILS = []


def check(name, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {extra}")
    if not cond:
        FAILS.append(name)


def pump(root, seconds=0.2):
    t0 = time.time()
    while time.time() - t0 < seconds:
        root.update_idletasks()
        root.update()
        time.sleep(0.01)


def simulate_type(entry, text):
    """模拟「全选 -> 直接键入 text」在 Tk Entry 上的等价操作。"""
    entry.selection_range(0, tk.END)
    entry.delete(0, tk.END)     # 键入前 Tk 会先清除选区
    entry.insert(0, text)


def main():
    from gui.app import App

    root = tk.Tk()
    root.geometry("1100x720")
    app = App(root)
    pump(root, 0.3)

    # 切到 adaptive_fine
    app.mode_var.set("adaptive_fine")
    app.on_mode_change()
    pump(root, 0.2)

    spin = app.block_size_spin
    entry = spin  # ttk.Spinbox 自身即 Entry 子类，支持 selection_range/insert

    # ---- 场景 1：默认 13 -> 全选键入 9 -> 应为 9 ----
    app.state.set_param("block_size", 13)
    app.block_size_var.set("13")
    pump(root, 0.1)
    simulate_type(entry, "9")
    pump(root, 0.1)
    check("中间态 9 不被打断（未被回写成 139）",
          app.block_size_var.get() == "9",
          f"got={app.block_size_var.get()!r}")
    app._commit_block_size()
    pump(root, 0.1)
    check("13 全选键入 9 -> 9", app.block_size_var.get() == "9"
          and app.state.get_param("block_size") == 9,
          f"ui={app.block_size_var.get()!r} state={app.state.get_param('block_size')}")

    # ---- 场景 2：13 -> 25 ----
    app.state.set_param("block_size", 13)
    app.block_size_var.set("13")
    pump(root, 0.1)
    simulate_type(entry, "25")
    app._commit_block_size()
    pump(root, 0.1)
    check("13 全选键入 25 -> 25", app.state.get_param("block_size") == 25,
          f"state={app.state.get_param('block_size')}")

    # ---- 场景 3：25 -> 11 ----
    simulate_type(entry, "11")
    app._commit_block_size()
    pump(root, 0.1)
    check("25 全选键入 11 -> 11", app.state.get_param("block_size") == 11,
          f"state={app.state.get_param('block_size')}")

    # ---- 场景 4：13 -> 12 -> commit 应为 13 ----
    app.state.set_param("block_size", 13)
    app.block_size_var.set("13")
    pump(root, 0.1)
    simulate_type(entry, "12")
    pump(root, 0.1)
    check("编辑时允许中间态 12（未立即改写）",
          app.block_size_var.get() == "12",
          f"ui={app.block_size_var.get()!r}")
    app._commit_block_size()
    pump(root, 0.1)
    check("12 commit -> 13", app.state.get_param("block_size") == 13
          and app.block_size_var.get() == "13",
          f"ui={app.block_size_var.get()!r} state={app.state.get_param('block_size')}")

    # ---- 场景 5：全选删空 -> FocusOut 恢复/合法化，无旧值粘连 ----
    app.state.set_param("block_size", 13)
    app.block_size_var.set("13")
    pump(root, 0.1)
    entry.selection_range(0, tk.END)
    entry.delete(0, tk.END)
    pump(root, 0.1)
    check("删空允许中间态（不崩、不立即回写）",
          app.block_size_var.get() == "",
          f"ui={app.block_size_var.get()!r}")
    check("删空时 state 未被写入空串",
          isinstance(app.state.get_param("block_size"), int)
          and app.state.get_param("block_size") == 13,
          f"state={app.state.get_param('block_size')!r}")
    app._commit_block_size()
    pump(root, 0.1)
    check("删空后 commit 恢复 last valid 13，无粘连",
          app.block_size_var.get() == "13",
          f"ui={app.block_size_var.get()!r}")

    # ---- 场景 6：非数字 commit -> 恢复 last valid ----
    app.state.set_param("block_size", 13)
    app.block_size_var.set("abc")
    app._commit_block_size()
    pump(root, 0.1)
    check("非数字 commit -> 恢复 13", app.block_size_var.get() == "13"
          and app.state.get_param("block_size") == 13)

    # ---- Bold 模式同样适用 ----
    app.mode_var.set("adaptive_bold")
    app.on_mode_change()
    pump(root, 0.2)
    bspin = app.block_size_spin
    app.state.set_param("block_size", 25)
    app.block_size_var.set("25")
    pump(root, 0.1)
    simulate_type(bspin, "13")
    app._commit_block_size()
    pump(root, 0.1)
    check("Bold: 25 全选键入 13 -> 13", app.state.get_param("block_size") == 13,
          f"state={app.state.get_param('block_size')}")

    root.destroy()

    print("\n==== SMOKE BLOCKSIZE 汇总 ====")
    if FAILS:
        print(f"FAIL {len(FAILS)} 项: {FAILS}")
        sys.exit(1)
    print("全部 PASS")


if __name__ == "__main__":
    main()
