"""binary-pixel-art GUI 包（Tkinter + ttk）。

GUI 层保持薄：算法与尺寸计算全部复用 src/，GUI 只做界面与状态管理。
本轮（GUI-001B1）已接通正式 Generate Preview（后台 worker + current/stale）；
仍不含 Save PNG 与打包。

- gui.state   —— 会话状态（模式参数记忆、geometry readout、GenerationKey），不依赖 Tk
- gui.ui_helpers —— preview fit/center 辅助
- gui.worker  —— 后台生成 worker（threading + queue）
- gui.app     —— Tkinter 主界面
"""
