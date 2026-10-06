# binary-pixel-art

Strict black-and-white pseudo-pixel image processing project.

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
- `src/` — 算法实现（`FORMAL_MODES` 注册正式四模式；其余为实验/基准实现）
- `tools/` — 实验入口与程序化测试图生成
- `tests/` — 正式模式 / 回归 / legacy 未改 测试
- `outputs/` — 实验输出（默认不进 Git）

## 快速开始

生成一张无版权争议的程序化测试图，并对它跑一次四模式输出：

```bash
python3.11 tools/make_test_image.py
python3.11 -m tools.run_experiment outputs/test_input.png -o outputs
```

对你自己的图片生成四张结果：

```bash
python3.11 -m tools.run_experiment /path/to/your_image.png -o outputs
```

会输出 `classic / bayer4 / adaptive_fine / adaptive_bold` 四张严格黑白图，外加一张 2×2 contact sheet 便于并排比较。

## 测试

```bash
python3.11 -m pytest tests/ -v
```

## 依赖

`opencv-python`（cv2）、`numpy`；测试用 `pytest`。不使用任何 AI / 神经网络依赖。
