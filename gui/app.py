"""GUI v1 主界面（Tkinter + ttk）—— GUI-001A 骨架轮。

本轮范围（严格）：
- 主窗口骨架、图片打开、Source Preview、模式参数面板、参数状态；
- Source Preview 完整显示原图（fit + 居中，不裁切）；
- Result Preview 仅空白占位（"No preview generated"），不接正式生成；
- Generate Preview 可 disabled / 未接线；Save PNG 必须 disabled；
- 不做 worker thread、不做 Save、不做打包、不自动实时生成。

调用：python3.11 -m gui.app
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, ttk

# 允许 `python3.11 -m gui.app` 与直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402

from gui.state import AppState, MODE_LABELS, MODE_ORDER  # noqa: E402
from gui.ui_helpers import render_fitted, render_placeholder  # noqa: E402


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=6)
        self.master = master
        self.state = AppState()
        self.source_bgr = None          # 原始 BGR 数据（不因预览 resize 改变）
        self._preview_job = None        # resize debounce job id
        self._photo_refs = {}           # 持有 PhotoImage 引用，防 GC
        self._param_widgets = {}        # key -> 控件/变量，便于回填
        self._syncing = False           # 回填/重建控件期间抑制 trace 回调

        self.grid(row=0, column=0, sticky="nsew")
        master.rowconfigure(0, weight=1)
        master.columnconfigure(0, weight=1)

        self._build_topbar()
        self._build_body()
        self._build_statusbar()

        # 初始同步：默认模式 + geometry readout
        self._sync_mode_ui()
        self._update_geometry_readout()
        self._refresh_source_preview()

    # ------------------------------------------------------------------ 顶栏
    def _build_topbar(self):
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        bar.columnconfigure(2, weight=1)

        ttk.Button(bar, text="Open Image...", command=self.on_open).grid(
            row=0, column=0, padx=(0, 8))
        self.filename_var = tk.StringVar(value="（未打开图片）")
        ttk.Label(bar, textvariable=self.filename_var).grid(row=0, column=1, sticky="w")

        # 右侧预留 Save PNG（本轮 disabled）
        self.save_btn = ttk.Button(bar, text="Save PNG...", state="disabled")
        self.save_btn.grid(row=0, column=3, sticky="e")

    # ------------------------------------------------------------------ 主体
    def _build_body(self):
        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="nsew")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # 左侧 Controls
        self._build_controls(body)

        # 右侧预览：ttk.PanedWindow 水平双栏
        self.paned = ttk.PanedWindow(body, orient="horizontal")
        self.paned.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        src_frame = ttk.Labelframe(self.paned, text="Source Preview")
        res_frame = ttk.Labelframe(self.paned, text="Result Preview")
        self.paned.add(src_frame, weight=1)
        self.paned.add(res_frame, weight=1)

        self.source_canvas = tk.Canvas(src_frame, background="#f0f0f0",
                                       highlightthickness=0)
        self.source_canvas.pack(fill="both", expand=True)
        self.result_canvas = tk.Canvas(res_frame, background="#f0f0f0",
                                       highlightthickness=0)
        self.result_canvas.pack(fill="both", expand=True)

        # resize 时重建 display preview（debounce）
        self.source_canvas.bind("<Configure>", self._on_preview_configure)
        self.result_canvas.bind("<Configure>", self._on_preview_configure)

    # -------------------------------------------------------------- 参数面板
    def _build_controls(self, parent):
        wrap = ttk.Frame(parent)
        wrap.grid(row=0, column=0, sticky="ns")
        wrap.columnconfigure(0, weight=1)

        # 模式选择（Radio Button，非下拉框）
        mode_box = ttk.Labelframe(wrap, text="模式")
        mode_box.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.mode_var = tk.StringVar(value=self.state.current_mode)
        for i, mode in enumerate(MODE_ORDER):
            label, hint = MODE_LABELS[mode]
            rb = ttk.Radiobutton(
                mode_box, text=f"{label}    {hint}", value=mode,
                variable=self.mode_var, command=self.on_mode_change,
            )
            rb.grid(row=i, column=0, sticky="w", padx=4)

        # 共同参数
        common = ttk.Labelframe(wrap, text="参数")
        common.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        common.columnconfigure(1, weight=1)
        self._common_box = common
        self._build_common_params(common)

        # 模式专属参数容器（切换时重建）
        self.specific_box = ttk.Labelframe(wrap, text="模式参数")
        self.specific_box.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.specific_box.columnconfigure(1, weight=1)

        # geometry readout
        geo_box = ttk.Labelframe(wrap, text="输出尺寸")
        geo_box.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        self.geo_var = tk.StringVar(value="")
        ttk.Label(geo_box, textvariable=self.geo_var, justify="left").grid(
            row=0, column=0, sticky="w", padx=4, pady=2)

        # Advanced / Output
        adv = ttk.Labelframe(wrap, text="Advanced / Output")
        adv.grid(row=4, column=0, sticky="ew", pady=(0, 6))
        self.invert_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(adv, text="黑白反转", variable=self.invert_var,
                        command=self.on_param_change).grid(
            row=0, column=0, sticky="w", padx=4)

        # 操作按钮
        btns = ttk.Frame(wrap)
        btns.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        # Generate Preview：本轮 disabled / 未接线
        self.gen_btn = ttk.Button(btns, text="Generate Preview", state="disabled")
        self.gen_btn.grid(row=0, column=0, padx=2)
        ttk.Button(btns, text="恢复默认值",
                   command=self.on_restore_defaults).grid(row=1, column=0,
                                                          padx=2, pady=(4, 0))

    def _build_common_params(self, box):
        self.width_var = tk.StringVar()
        self.block_var = tk.StringVar()
        ttk.Label(box, text="目标宽度").grid(row=0, column=0, sticky="w", padx=4)
        ttk.Spinbox(box, from_=1, to=20000, increment=10, width=8,
                    textvariable=self.width_var,
                    command=self.on_param_change).grid(row=0, column=1, sticky="w")
        ttk.Label(box, text="像素块大小").grid(row=1, column=0, sticky="w", padx=4)
        ttk.Spinbox(box, from_=1, to=64, increment=1, width=8,
                    textvariable=self.block_var,
                    command=self.on_param_change).grid(row=1, column=1, sticky="w")
        # 绑定键盘输入
        for var in (self.width_var, self.block_var):
            var.trace_add("write", lambda *_: self.on_param_change())

    # ------------------------------------------------------ 模式专属参数面板
    def _build_specific_params(self, mode):
        for w in self.specific_box.winfo_children():
            w.destroy()
        self._param_widgets = {}
        p = self.state.get_params(mode)

        if mode == "classic":
            self.t_var = tk.StringVar(value=str(p["t"]))
            self.b_var = tk.StringVar(value=str(p["b"]))
            self.equalize_var = tk.BooleanVar(value=p["equalize"])
            ttk.Label(self.specific_box, text="网点阈值 t").grid(row=0, column=0, sticky="w", padx=4)
            ttk.Spinbox(self.specific_box, from_=0, to=255, width=8,
                        textvariable=self.t_var).grid(row=0, column=1, sticky="w")
            ttk.Label(self.specific_box, text="实黑阈值 b").grid(row=1, column=0, sticky="w", padx=4)
            ttk.Spinbox(self.specific_box, from_=0, to=255, width=8,
                        textvariable=self.b_var).grid(row=1, column=1, sticky="w")
            ttk.Checkbutton(self.specific_box, text="直方图均衡",
                            variable=self.equalize_var).grid(row=2, column=0, sticky="w", padx=4)
            self.b_hint_var = tk.StringVar(value="")
            ttk.Label(self.specific_box, textvariable=self.b_hint_var,
                      foreground="#aa6600").grid(row=3, column=0, columnspan=2, sticky="w", padx=4)
            for var in (self.t_var, self.b_var, self.equalize_var):
                var.trace_add("write", lambda *_: self.on_param_change())

        elif mode == "bayer4":
            self.matrix_var = tk.IntVar(value=p["matrix_size"])
            self.bias_var = tk.StringVar(value=str(p["tone_bias"]))
            ttk.Label(self.specific_box, text="Bayer 矩阵").grid(row=0, column=0, sticky="w", padx=4)
            mf = ttk.Frame(self.specific_box)
            mf.grid(row=0, column=1, sticky="w")
            for i, m in enumerate((2, 4, 8)):
                ttk.Radiobutton(mf, text=f"{m}×{m}", value=m,
                                variable=self.matrix_var).grid(row=0, column=i, padx=2)
            ttk.Label(self.specific_box, text="明暗偏移 tone bias").grid(row=1, column=0, sticky="w", padx=4)
            ttk.Spinbox(self.specific_box, from_=-128, to=128, width=8,
                        textvariable=self.bias_var).grid(row=1, column=1, sticky="w")
            for var in (self.matrix_var, self.bias_var):
                var.trace_add("write", lambda *_: self.on_param_change())

        elif mode in ("adaptive_fine", "adaptive_bold"):
            self.block_size_var = tk.StringVar(value=str(p["block_size"]))
            self.c_var = tk.StringVar(value=str(p["c"]))
            label = "细节尺度 blockSize" if mode == "adaptive_fine" else "结构尺度 blockSize"
            ttk.Label(self.specific_box, text=label).grid(row=0, column=0, sticky="w", padx=4)
            ttk.Spinbox(self.specific_box, from_=3, to=999, increment=2, width=8,
                        textvariable=self.block_size_var).grid(row=0, column=1, sticky="w")
            ttk.Label(self.specific_box, text="黑白偏移 C").grid(row=1, column=0, sticky="w", padx=4)
            ttk.Spinbox(self.specific_box, from_=-64, to=64, width=8,
                        textvariable=self.c_var).grid(row=1, column=1, sticky="w")
            for var in (self.block_size_var, self.c_var):
                var.trace_add("write", lambda *_: self.on_param_change())

    # -------------------------------------------------------------- 状态同步
    def _sync_mode_ui(self):
        """把当前模式的参数值回填到控件（切模式 / 恢复默认后调用）。

        回填期间设置 _syncing，抑制 trace 触发的 on_param_change，
        避免控件重建与状态读取的时序竞争。
        """
        self._syncing = True
        try:
            mode = self.state.current_mode
            p = self.state.get_params(mode)
            # 共同参数
            self.width_var.set(str(p["output_width"]))
            self.block_var.set(str(p["pixel_block_size"]))
            self.invert_var.set(bool(p.get("invert", False)))
            # 模式专属
            self._build_specific_params(mode)
            if mode == "classic":
                self._update_b_hint()
        finally:
            self._syncing = False

    def _read_widgets_into_state(self):
        """把控件当前值写回 state（当前模式）。容忍非法中间输入。"""
        mode = self.state.current_mode
        updates = {}
        try:
            updates["output_width"] = int(self.width_var.get())
        except (ValueError, tk.TclError):
            pass
        try:
            updates["pixel_block_size"] = int(self.block_var.get())
        except (ValueError, tk.TclError):
            pass
        updates["invert"] = bool(self.invert_var.get())

        if mode == "classic":
            if hasattr(self, "t_var"):
                try:
                    updates["t"] = int(self.t_var.get())
                except (ValueError, tk.TclError):
                    pass
            if hasattr(self, "b_var"):
                try:
                    updates["b"] = int(self.b_var.get())
                except (ValueError, tk.TclError):
                    pass
            if hasattr(self, "equalize_var"):
                updates["equalize"] = bool(self.equalize_var.get())
        elif mode == "bayer4":
            if hasattr(self, "bias_var"):
                try:
                    updates["tone_bias"] = int(self.bias_var.get())
                except (ValueError, tk.TclError):
                    pass
            if hasattr(self, "matrix_var"):
                updates["matrix_size"] = int(self.matrix_var.get())
        elif mode in ("adaptive_fine", "adaptive_bold"):
            if hasattr(self, "block_size_var"):
                try:
                    updates["block_size"] = int(self.block_size_var.get())
                except (ValueError, tk.TclError):
                    pass
            if hasattr(self, "c_var"):
                try:
                    updates["c"] = int(self.c_var.get())
                except (ValueError, tk.TclError):
                    pass

        self.state.update_params(updates, mode=mode)

    # -------------------------------------------------------------- 事件
    def on_param_change(self):
        """参数变化：不运行算法，只更新 state + geometry readout。"""
        if self._syncing:
            return
        self._read_widgets_into_state()
        # blockSize 规范化后回填（保证 UI 显示合法奇数）
        mode = self.state.current_mode
        if mode in ("adaptive_fine", "adaptive_bold"):
            norm = self.state.get_param("block_size")
            if str(norm) != self.block_size_var.get():
                self._syncing = True
                try:
                    self.block_size_var.set(str(norm))
                finally:
                    self._syncing = False
        if mode == "classic":
            self._update_b_hint()
        self._update_geometry_readout()

    def _update_b_hint(self):
        t = self.state.get_param("t")
        b = self.state.get_param("b")
        self.b_hint_var.set(self.state.classic_b_ge_t_warning(t, b))

    def _update_geometry_readout(self):
        readout = self.state.geometry_readout()
        self.geo_var.set(readout.format())

    def on_mode_change(self):
        # 先保存旧模式控件值，再切模式并回填
        self._read_widgets_into_state()
        self.state.set_mode(self.mode_var.get())
        self._sync_mode_ui()
        self._update_geometry_readout()
        self.set_status(f"当前模式：{MODE_LABELS[self.state.current_mode][0]}")

    def on_restore_defaults(self):
        self.state.restore_defaults()   # 仅恢复当前模式
        self._sync_mode_ui()
        self._update_geometry_readout()
        self.set_status(f"已恢复 {MODE_LABELS[self.state.current_mode][0]} 默认值")

    # -------------------------------------------------------------- 打开图片
    def on_open(self):
        path = filedialog.askopenfilename(
            title="Open Image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            self.set_status(f"无法读取图片：{path}")
            return
        self.source_bgr = img
        h, w = img.shape[:2]
        self.state.set_source(path, (h, w))
        self.filename_var.set(f"{os.path.basename(path)}  ({w}×{h})")
        self.set_status(f"已打开：{os.path.basename(path)}")
        self._refresh_source_preview()
        self._update_geometry_readout()
        # Result 保持占位（本轮不生成）
        self._refresh_result_placeholder()

    # -------------------------------------------------------------- 预览
    def _refresh_source_preview(self):
        if self.source_bgr is None:
            return
        res = render_fitted(self.source_canvas, self.source_bgr)
        if res is not None:
            self._photo_refs["source"] = res[0]

    def _refresh_result_placeholder(self):
        render_placeholder(self.result_canvas, "No preview generated")

    def _on_preview_configure(self, event=None):
        """窗口/窗格 resize：debounce 后仅重建 display preview。"""
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(80, self._redraw_previews)

    def _redraw_previews(self):
        self._preview_job = None
        self._refresh_source_preview()
        # Result 本轮恒为占位
        self._refresh_result_placeholder()

    # -------------------------------------------------------------- 状态栏
    def _build_statusbar(self):
        self.status_var = tk.StringVar(value="就绪")
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Label(bar, text="GUI-001A 骨架轮：Generate/Save 未接线").grid(
            row=0, column=1, sticky="e")

    def set_status(self, text):
        self.status_var.set(text)


def main():
    root = tk.Tk()
    root.title("binary-pixel-art GUI")
    root.geometry("1100x720")
    root.minsize(820, 560)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
