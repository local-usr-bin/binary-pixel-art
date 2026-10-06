# 正式艺术风格方向（冻结）

当前正式产品模式**只有以下 4 种**，注册于 `src/algorithms.py` 的 `FORMAL_MODES`，
CLI/实验入口（`tools/run_experiment.py`）与文档统一使用这里的名称。

所有模式共用统一尺寸模型（见 `src/params.py`）：用户请求「目标宽度 + 像素块大小 P」，
逻辑宽 = round(目标宽/P)，逻辑高 = round(逻辑宽·原高/原宽)，最终每个逻辑方块严格 P×P，
nearest-neighbor 放大。输出严格只含 0/255，deterministic。

> **术语约定（目标宽度 vs 实际宽度）**：用户请求的是 **目标宽度
> （`requested_output_width`）**，实际产出的是 **实际宽度（`actual_output_width`）**。
> 当目标宽度不能被 P 整除时，实际宽度会吸附到最近的 P 整数倍（例如请求 1000、P=3，
> 实际为 999），二者可能不同。API/文档层应明确区分这两个值，避免暗示"请求 1000 一定输出 1000"。

## 正式模式与默认 preset

| 名称 | 核心算法 | 默认几何 | 默认专属参数 | 视觉特征 |
|---|---|---|---|---|
| `classic` | 双阈值 + 稀疏子网格（语义冻结） | 输出宽 1000、块 2 | t=127, b=60, equalize=on | 稀疏网格网点，颗粒粗粝；基准 |
| `bayer4` | Bayer ordered dithering | 输出宽 1280、块 10 | matrix_size=4, tone_bias=0 | 规则机械网点，稳定 |
| `adaptive_fine` | Adaptive **Gaussian** 局部阈值 | 输出宽 1280、块 10 | block_size=11, C=2 | 细密、漫画墨线、蚀刻感 |
| `adaptive_bold` | Adaptive **Mean** 局部阈值 | 输出宽 1280、块 10 | block_size=25, C=2 | 粗块、木刻/海报感 |

## 参数契约（GUI 将据此暴露）

- **目标宽度（`requested_output_width`）/ 像素块大小**：四模式共用，见尺寸模型。
  实际输出宽度为 `actual_output_width = logical_width × P`，可能与目标宽度相差（吸附到 P 整数倍）。
- **classic**：`output_width, pixel_block_size, t(0..255), b(0..255), equalize, invert`；
  `b>=t` 合法（偏离经典三档语义，允许但不推荐）；equalize 默认 True（直方图均衡，非"自动色阶"）。
- **bayer4**：`matrix_size ∈ {2,4,8}`（标准递归构造，默认 4）、`tone_bias`（阈值前
  `clip(gray+bias)`，默认 0）。
- **adaptive_fine**：Gaussian 固定；`block_size`（奇数 ≥3，默认 11）、`C`（默认 2）。
- **adaptive_bold**：Mean 固定；`block_size`（奇数 ≥3，默认 25）、`C`（默认 2）。
- **invert**（四模式共有）：仅在最终二值结果阶段 `255 - out`，不改算法判断。

Classic 的精确行为以 `docs/classic_algorithm.md` 为准，不允许修改语义。

> **Classic 几何边界**：正式 `classic()` 复刻的是 Legacy 的**二值算法语义与网点密度**，
> 采用统一 P×P 几何模型（宽高均为 P 整数倍）。因此在多数源图（含默认参数）下，其高度与
> Legacy 原脚本存在约 ±1 px 的有意尺寸差异（intentional divergence），详见
> `docs/classic_algorithm.md` 末节。

## 非正式（实验阶段 / 开发基准）

以下实现保留在 `src/algorithms.py` 中供内部对照，**不进入正式算法列表，
也不进入未来的正式 GUI**：

- `m1_otsu`、`m4_gradient`、`m5_pattern` —— 第一轮实验候选，未入选；
- `m3_adaptive`（Mean / 11 / C=2）—— 第一轮原始 adaptive，保留为开发/回归基准；
- 第二轮的 `m3_smooth`（median 预平滑）与 `m3_original` 别名已随收敛移除，
  实验阶段的 `m3_alt_method` / `m3_large_window` 命名已分别正名为
  `adaptive_fine` / `adaptive_bold`。

