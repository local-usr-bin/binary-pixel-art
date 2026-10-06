# binary-pixel-art

Pseudo-pixel image processing project.

核心算法生成严格二值 pseudo-pixel mask；默认输出为黑白；
可选 **Color Fill（彩色填充）** 使用该硬边界 mask 显示原图连续色彩纹理，
即 mask 黑处取原图颜色、白处保持纯白，mask 边界始终严格锐利。

正式产品模式共 **4 种**（详见 `docs/four_modes.md`）：

- `classic` — 用户早年算法，语义冻结（权威依据：`docs/classic_algorithm.md`）
- `bayer4` — Bayer 4×4 有序抖动，规则网点
- `adaptive_fine` — Adaptive Gaussian（11, C=2），细密云纹/墨线/蚀刻感
- `adaptive_bold` — Adaptive Mean（25, C=2），粗块/木刻/海报感

## 目录

- `legacy/` — 早期三份脚本考古归档（原样保存，不修改；`xiangsudian.py` 是 Classic 的唯一复刻依据）
- `docs/classic_algorithm.md` — Classic 算法精确行为记录
- `docs/four_modes.md` — 当前冻结的四种正式风格方向
- `docs/modern_round1.md` — Modern 第一轮实验记录（历史参考）
- `docs/WB_WORKFLOW.md` — WB 沙箱 / CNB 协作约定
- `src/` — 算法实现（`FORMAL_MODES` 注册正式四模式；`render.py` 为 Color Fill 下游 renderer；其余为实验/基准实现）
- `gui/` — Tkinter GUI（`gui.state` 会话状态、`gui.app` 主界面、`gui.worker` 后台生成、`gui.save` PNG 保存）
- `tools/` — 实验入口与程序化测试图生成（含 Color Fill 视觉矩阵脚本）
- `tests/` — 正式模式 / 回归 / legacy 未改 / GUI 状态 / Color Fill 测试
- `outputs/` — 实验输出（默认不进 Git）

## 快速开始

生成一张无版权争议的程序化测试图，并对它跑一次四模式输出：

```bash
python tools/make_test_image.py
python -m tools.run_experiment outputs/test_input.png -o outputs
```

对你自己的图片生成四张结果：

```bash
python -m tools.run_experiment /path/to/your_image.png -o outputs
```

会输出 `classic / bayer4 / adaptive_fine / adaptive_bold` 四张严格黑白图，外加一张 2×2 contact sheet 便于并排比较。

## GUI

从源码启动：

```bash
python -m pip install -r requirements.txt
python -m gui.app
```

GUI 已支持：打开图片、四模式参数面板、Generate Preview、current/stale 状态、
Save PNG、黑白反转（Invert）与彩色填充（Color Fill）全局输出选项。

当前目标平台为 **Windows 10/11 x64**，Python 3.13；v1 真人验证环境为
Python 3.13.16，Tkinter/Tcl-Tk 来自对应 Python 的 Windows 安装。

## 测试

```bash
python -m pytest tests/ -v
```

## 依赖

Runtime 第三方依赖（见 `requirements.txt`）：`numpy`、`opencv-python`、`Pillow`；
测试用 `pytest`（见 `requirements-dev.txt`）。不使用任何 AI / 神经网络依赖。
