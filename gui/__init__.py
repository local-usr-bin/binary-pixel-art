"""binary-pixel-art GUI 包（Tkinter + ttk）。

GUI 层保持薄：算法与尺寸计算全部复用 src/，GUI 只做界面与状态管理。
本轮（GUI-001A）只含骨架、参数面板与状态，不含正式生成 / Save。

- gui.state   —— 会话状态（模式参数记忆、geometry readout），不依赖 Tk
- gui.ui_helpers —— preview fit/center 辅助
- gui.app     —— Tkinter 主界面
"""
