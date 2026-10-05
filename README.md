# binary-pixel-art

Strict black-and-white pseudo-pixel image processing project.

最终同时保留两套算法：**Classic**（复现早年旧二值算法，语义已冻结）与 **Modern**（重新设计，目标是在严格黑白 + 低分辨率 + 最近邻方块放大框架内探索有趣、有辨识度的视觉风格）。

## 目录

- `legacy/` — 早期三份脚本考古归档（原样保存，不修改；`xiangsudian.py` 是 Classic 的唯一复刻依据）
- `docs/classic_algorithm.md` — Classic 算法精确行为记录（Classic 的唯一权威依据）
- `docs/modern_round1.md` — Modern 第一轮候选实现与固定参数说明
- `docs/WB_WORKFLOW.md` — WB 沙箱 / CNB 协作约定
- `src/` — 实验算法实现（Classic 复现 + M1~M5 Modern 候选）
- `tools/` — 最小实验入口与程序化测试图生成
- `tests/` — 确定性 / 二值性 / 尺寸 / Classic 一致性 / legacy 未改 测试
- `outputs/` — 实验输出（默认不进 Git）

## 快速开始

生成一张无版权争议的程序化测试图，并对它跑一次六算法实验：

```bash
python3.11 tools/make_test_image.py
python3.11 -m tools.run_experiment outputs/test_input.png -o outputs
```

对你自己的图片生成六张结果：

```bash
python3.11 -m tools.run_experiment /path/to/your_image.png -o outputs
```

会输出 `classic / m1_otsu / m2_bayer4 / m3_adaptive / m4_gradient / m5_pattern` 六张严格黑白图，外加一张 2×3 contact sheet 便于并排比较。

## 测试

```bash
python3.11 -m pytest tests/ -v
```

## 依赖

`opencv-python`（cv2）、`numpy`；测试用 `pytest`。不使用任何 AI / 神经网络依赖。
