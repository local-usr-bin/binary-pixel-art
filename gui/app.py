"""GUI v1 主界面（Tkinter + ttk）。

- 后台 worker thread 生成正式 full-resolution 结果（调用 src 后端，不复制算法）；
- Result Preview 显示结果（display fit，二值 nearest）；
- current / stale 状态（GenerationKey）、生成状态反馈、busy 期间禁用控件；
- 参数改变/切模式/换图 -> stale（保留旧结果）；参数改回 -> 自动 current；
- resize 只重新 fit，不重跑算法；
- Save PNG：current-only 保存 full-resolution 结果；
- Color Fill：全局输出渲染开关（默认 OFF，跨模式保持），
  开启时由 worker 在 mask 之后调用 src.render.apply_color_fill 叠加原图色彩。

调用：python3.11 -m gui.app
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# 允许 `python3.11 -m gui.app` 与直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from src import imageio  # noqa: E402

from gui import state as state_mod  # noqa: E402
from gui.state import AppState, MODE_LABELS, MODE_ORDER  # noqa: E402
from gui.ui_helpers import render_fitted, render_placeholder  # noqa: E402
from gui.worker import GenerationWorker  # noqa: E402
from gui import save as save_mod  # noqa: E402

# 状态文案（统一中文）
TXT_READY = "就绪"
TXT_GENERATING = "正在生成…"
TXT_GENERATED = "预览已生成"
TXT_STALE = "参数已更改，请重新生成"
TXT_FAILED = "生成失败"
TXT_NEW_SOURCE = "已打开新图片，请重新生成"
PLACEHOLDER_RESULT = "尚未生成预览"
TXT_SAVE_FAILED = "保存失败"


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
        self._worker = None             # 当前生成 worker（同一时间仅一个）
        self._poll_job = None           # worker 轮询 job id
        self._lock_widgets = []         # busy 期间需禁用的控件收集

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
        self._refresh_result_placeholder()
        self._refresh_save_state()      # 无结果 -> Save disabled

    # ------------------------------------------------------------------ 顶栏
    def _build_topbar(self):
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        bar.columnconfigure(2, weight=1)

        self.open_btn = ttk.Button(bar, text="打开图片...", command=self.on_open)
        self.open_btn.grid(row=0, column=0, padx=(0, 8))
        self.filename_var = tk.StringVar(value="（未打开图片）")
        ttk.Label(bar, textvariable=self.filename_var).grid(row=0, column=1, sticky="w")

        # 右侧 Save PNG（enable 由 current-only 规则驱动）
        self.save_btn = ttk.Button(bar, text="保存 PNG...", state="disabled",
                                   command=self.on_save)
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

        src_frame = ttk.Labelframe(self.paned, text="原图预览")
        res_frame = ttk.Labelframe(self.paned, text="效果预览")
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
        adv = ttk.Labelframe(wrap, text="高级 / 输出")
        adv.grid(row=4, column=0, sticky="ew", pady=(0, 6))
        self.invert_var = tk.BooleanVar(value=False)
        self.invert_chk = ttk.Checkbutton(adv, text="黑白反转", variable=self.invert_var,
                                          command=self.on_param_change)
        self.invert_chk.grid(row=0, column=0, sticky="w", padx=4)
        # Color Fill：全局输出渲染开关（不属于任何 mode preset，默认 OFF）
        self.color_fill_var = tk.BooleanVar(value=self.state.get_color_fill())
        self.color_fill_chk = ttk.Checkbutton(
            adv, text="彩色填充", variable=self.color_fill_var,
            command=self.on_color_fill_change)
        self.color_fill_chk.grid(row=1, column=0, sticky="w", padx=4)

        # 操作按钮：生成预览为主按钮（加宽），恢复默认值为次级
        btns = ttk.Frame(wrap)
        btns.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        btns.columnconfigure(0, weight=1)
        self.gen_btn = ttk.Button(btns, text="生成预览", command=self.on_generate)
        self.gen_btn.grid(row=0, column=0, sticky="ew", padx=2, ipady=4)
        self.restore_btn = ttk.Button(btns, text="恢复默认值",
                                      command=self.on_restore_defaults)
        self.restore_btn.grid(row=1, column=0, sticky="ew", padx=2, pady=(4, 0))

    def _collect_lock_widgets(self):
        """动态收集 busy 期间需要禁用的控件（模式/参数/按钮）。

        每次切换 busy 前重新收集，避免模式专属参数重建后集合失效。
        """
        widgets = [self.open_btn, self.gen_btn, self.restore_btn, self.save_btn]

        def walk(w):
            for child in w.winfo_children():
                if isinstance(child, (ttk.Radiobutton, ttk.Spinbox,
                                      ttk.Checkbutton, ttk.Entry, ttk.Button)):
                    widgets.append(child)
                walk(child)

        walk(self)
        return widgets

    def _set_busy(self, busy: bool):
        """生成期间禁用/恢复控件。Save 的可用性由 current-only 规则驱动。"""
        self.state.busy = busy
        new_state = "disabled" if busy else "normal"
        for w in self._collect_lock_widgets():
            if w is self.save_btn:
                continue                     # Save 由 _refresh_save_state 统一决定
            try:
                w.config(state=new_state)
            except tk.TclError:
                pass
        if busy:
            self.progress.grid()
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.grid_remove()
        # busy 结束/开始时刷新 Save 的 enable 逻辑
        self._refresh_save_state()

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
            # blockSize：编辑期允许中间态（""/纯数字），提交时再合法化。
            # validatecommand 只拦非法字符（如字母），不强制奇数/>=3，
            # 以保证「全选 -> 直接键入」能正常替换，不被每键回写打断。
            vcmd = (self.register(self._validate_block_text), "%P")
            self.block_size_spin = ttk.Spinbox(
                self.specific_box, from_=3, to=999, increment=2, width=8,
                textvariable=self.block_size_var,
                validate="key", validatecommand=vcmd)
            self.block_size_spin.grid(row=0, column=1, sticky="w")
            # 提交时机：Enter / 失焦 / 上下箭头
            self.block_size_spin.bind("<Return>", self._commit_block_size)
            self.block_size_spin.bind("<FocusOut>", self._commit_block_size)
            self.block_size_spin.bind("<Up>", self._commit_block_size)
            self.block_size_spin.bind("<Down>", self._commit_block_size)
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
            # 全局 Color Fill：不属于 mode preset，切模式/恢复默认时保持全局值
            self.color_fill_var.set(self.state.get_color_fill())
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
            # blockSize 不在按键时写入 state：编辑中间态（""/部分数字）不进入
            # GenerationKey；只有 _commit_block_size（Enter/失焦/箭头）提交
            # 合法值后才更新 state。
            if hasattr(self, "c_var"):
                try:
                    updates["c"] = int(self.c_var.get())
                except (ValueError, tk.TclError):
                    pass

        self.state.update_params(updates, mode=mode)

    # -------------------------------------------------------------- 事件
    def on_param_change(self):
        """参数变化：不运行算法，只更新 state + geometry + stale 状态。

        注意：blockSize 不回写控件——编辑期（含中间态 ""/12）保持用户输入，
        合法化只在 _commit_block_size（Enter/失焦/箭头）时进行。
        """
        if self._syncing:
            return
        self._read_widgets_into_state()
        mode = self.state.current_mode
        if mode == "classic":
            self._update_b_hint()
        self._update_geometry_readout()
        self._refresh_result_status()

    def on_color_fill_change(self):
        """Color Fill 开关变化：更新全局状态，仅影响 current/stale。

        Color Fill 是全局输出状态（不进 mode params）。切换后不自动生成；
        旧结果按 GenerationKey（含 color_fill）判定 current/stale。
        """
        if self._syncing:
            return
        self.state.set_color_fill(self.color_fill_var.get())
        self._refresh_result_status()

    def _validate_block_text(self, proposed) -> bool:
        """Spinbox validatecommand：编辑期只拦非法字符，不强制奇数/>=3。

        允许中间态（""/纯数字），因此用户可「全选 -> 直接键入」。
        """
        return state_mod.is_editable_block_size_text(proposed)

    def _commit_block_size(self, event=None):
        """提交 blockSize：Enter / 失焦 / 上下箭头时合法化并写回。

        空 或 非数字 -> 恢复 last valid；数字 -> normalize（<3->3；偶数->+1）。
        """
        last_valid = self.state.get_param("block_size")
        committed = state_mod.commit_block_size_text(
            self.block_size_var.get(), last_valid)
        self._syncing = True
        try:
            self.block_size_var.set(str(committed))
        finally:
            self._syncing = False
        # 合法提交才写入 state（影响 GenerationKey / stale）
        self.state.set_param("block_size", committed)
        self._update_geometry_readout()
        self._refresh_result_status()
        # Spinbox 上下箭头：允许默认步进行为继续（不 return "break"）
        return None

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
        # 不自动生成；旧结果保留，按 key 判定 current/stale
        self._refresh_result_status()
        if not self.state.has_result():
            self.set_status(f"当前模式：{MODE_LABELS[self.state.current_mode][0]}")

    def on_restore_defaults(self):
        self.state.restore_defaults()   # 仅恢复当前模式
        self._sync_mode_ui()
        self._update_geometry_readout()
        self._refresh_result_status()
        if not self.state.has_result():
            self.set_status(f"已恢复 {MODE_LABELS[self.state.current_mode][0]} 默认值")

    # -------------------------------------------------------------- 打开图片
    def on_open(self):
        path = filedialog.askopenfilename(
            title="打开图片",
            filetypes=[
                ("图片", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        self._load_source(path)

    def _load_source(self, path):
        """加载 source（供 filedialog 与测试直接调用）。

        使用 Unicode-safe 读取（Path.read_bytes + cv2.imdecode），
        Windows 上含中文/Unicode 的路径也能正常打开。
        解码 flag 与既有 cv2.imread(path, IMREAD_COLOR) 完全一致。
        """
        try:
            img = imageio.imread_unicode(path)
        except imageio.ImageReadError as exc:
            self.set_status(f"无法读取图片：{exc}")
            return
        except imageio.ImageDecodeError as exc:
            self.set_status(f"无法解码图片：{exc}")
            return
        self.source_bgr = img
        h, w = img.shape[:2]
        digest = self._source_digest(img)
        self.state.set_source(path, (h, w), content_digest=digest)
        self.filename_var.set(f"{os.path.basename(path)}  ({w}×{h})")
        self._refresh_source_preview()
        self._update_geometry_readout()
        # 新 source：旧结果保留但立即 stale；不自动生成
        self._refresh_result_status()
        if self.state.has_result():
            self.set_status(TXT_NEW_SOURCE)
        else:
            self.set_status(f"已打开：{os.path.basename(path)}")

    @staticmethod
    def _source_digest(img_bgr):
        """source 内容指纹（尺寸 + 采样像素），用于 GenerationKey 的 source identity。"""
        import hashlib
        h, w = img_bgr.shape[:2]
        # 采样以避免大图哈希过慢；尺寸也纳入
        step_h = max(1, h // 64)
        step_w = max(1, w // 64)
        sample = img_bgr[::step_h, ::step_w]
        m = hashlib.sha1()
        m.update(f"{w}x{h}".encode("ascii"))
        m.update(np.ascontiguousarray(sample).tobytes())
        return m.hexdigest()

    # -------------------------------------------------------------- 生成
    def on_generate(self):
        """点击「生成预览」：启动后台 worker（同一时间仅一个）。"""
        if self._worker is not None:
            # 已有任务在跑，忽略重复点击
            return
        if self.source_bgr is None:
            self.set_status("请先打开图片")
            return
        # 确保控件值已写入 state
        self._read_widgets_into_state()
        # 全局 Color Fill 状态以 state 为准（on_color_fill_change 已同步），
        # 作为下游 renderer 开关注入 params 传给 worker。
        self.state.set_color_fill(self.color_fill_var.get())
        mode = self.state.current_mode
        params = self.state.get_params(mode)
        params["color_fill"] = self.state.get_color_fill()
        key = self.state.current_key()

        self._set_busy(True)
        self.set_status(TXT_GENERATING)
        self._worker = GenerationWorker(
            self, mode, params, self.source_bgr.copy(), key)
        self._worker.start()
        self._schedule_poll()

    def _schedule_poll(self):
        self._poll_job = self.after(60, self._poll_worker)

    def _poll_worker(self):
        """主线程轮询 worker 结果；完成后回主线程更新 UI。"""
        self._poll_job = None
        if self._worker is None:
            return
        ok, payload = self._worker.poll()
        if ok is None:
            # 未完成，继续轮询
            self._schedule_poll()
            return
        worker = self._worker
        self._worker = None
        if ok:
            self._on_generate_success(worker.key, payload)
        else:
            self._on_generate_failure(payload)

    def _on_generate_success(self, key, result):
        self.state.mark_generated(key, result)
        self._set_busy(False)
        self._refresh_result_preview()
        self._refresh_result_status()
        # 生成成功时 key 必等于 current（参数未变）；若期间被改则 stale
        if self.state.is_current():
            self.set_status(TXT_GENERATED)
        else:
            self.set_status(TXT_STALE)

    def _on_generate_failure(self, exc):
        self._set_busy(False)
        self.set_status(f"{TXT_FAILED}：{type(exc).__name__}: {exc}")
        # 保留旧结果（若有）；不清空

    # -------------------------------------------------------------- 预览
    def _refresh_source_preview(self):
        if self.source_bgr is None:
            return
        res = render_fitted(self.source_canvas, self.source_bgr)
        if res is not None:
            self._photo_refs["source"] = res[0]

    def _refresh_result_preview(self):
        """显示正式 result（display fit，二值 nearest）或占位。"""
        if self.state.generated_result is None:
            self._refresh_result_placeholder()
            return
        res = render_fitted(self.result_canvas, self.state.generated_result,
                            nearest=True)
        if res is not None:
            self._photo_refs["result"] = res[0]

    def _refresh_result_placeholder(self):
        render_placeholder(self.result_canvas, PLACEHOLDER_RESULT)

    def _refresh_result_status(self):
        """根据 key 判定刷新状态文本与 Save enable 逻辑（不重跑算法）。"""
        self._refresh_save_state()
        if not self.state.has_result():
            return
        if self.state.is_current():
            # 参数已改回生成时状态 -> 自动恢复 current
            if not self.state.busy:
                self.set_status(TXT_GENERATED)
        else:
            if not self.state.busy:
                self.set_status(TXT_STALE)

    def _refresh_save_state(self):
        """按 current-only 规则刷新 Save 按钮的 enable 状态。

        规则（复用 state.save_enabled()，不另写第二套判断）：
          result 存在 且 为 current 且 无 worker 在跑 -> enabled，否则 disabled。
        """
        enabled = self.state.save_enabled()
        self._save_should_be_enabled = enabled
        try:
            self.save_btn.config(state="normal" if enabled else "disabled")
        except tk.TclError:
            pass

    # -------------------------------------------------------------- 保存 PNG
    def on_save(self):
        """「保存 PNG...」：把 full-resolution current result 写为 PNG。

        - 不重新运行算法；
        - 保存的是 AppState.generated_result（非 preview / 非截图）；
        - 用户取消对话框 -> 不写文件、不报错、状态不变。
        """
        if not self.state.save_enabled():
            # 防御：按钮本应 disabled；被外部误调用时直接忽略
            return
        result = self.state.generated_result
        if result is None:
            return
        default_name = save_mod.default_filename(self.state.source_path,
                                                 self.state.current_mode)
        path = filedialog.asksaveasfilename(
            title="保存 PNG",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG 图片", "*.png")],
        )
        if not path:
            # 用户取消：不写文件、不报错、状态不变
            return
        self._save_result_to(path, result)

    def _save_result_to(self, path, result):
        """执行保存并更新状态栏（供 on_save 与测试直接调用）。"""
        # 扩展名归一化：杜绝「非 .png 文件名但内部是 PNG」的文件
        path = save_mod.normalize_png_path(path)
        try:
            save_mod.save_png(path, result)
        except Exception as exc:  # noqa: BLE001 —— 任何保存异常都要提示且不崩溃
            self.set_status(f"{TXT_SAVE_FAILED}：{exc}")
            messagebox.showerror("保存失败", f"无法保存图片：\n{exc}")
            # current result 保留在内存，key 不变，可再次尝试
            return False
        name = os.path.basename(path)
        self.set_status(f"已保存：{name}")
        # 不变 stale，generated_key 不变，Save 继续可用
        self._refresh_save_state()
        return True

    def _on_preview_configure(self, event=None):
        """窗口/窗格 resize：debounce 后仅重建 display preview（不重跑算法）。"""
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(80, self._redraw_previews)

    def _redraw_previews(self):
        self._preview_job = None
        self._refresh_source_preview()
        # Result：只重新 fit 当前 result，不运行算法
        self._refresh_result_preview()

    # -------------------------------------------------------------- 状态栏
    def _build_statusbar(self):
        self.status_var = tk.StringVar(value=TXT_READY)
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        # 轻量 indeterminate 进度条（生成期间显示，无百分比）
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=140)
        self.progress.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.progress.grid_remove()
        self.hint_var = tk.StringVar(value="GUI-001B2：生成 + 保存 PNG 已接线")
        ttk.Label(bar, textvariable=self.hint_var).grid(row=0, column=2, sticky="e", padx=(8, 0))

    def set_status(self, text):
        if hasattr(self, "status_var"):
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
