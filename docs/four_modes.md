# 正式艺术风格方向（冻结）

当前正式产品模式**只有以下 4 种**，注册于 `src/algorithms.py` 的 `FORMAL_MODES`，
CLI/实验入口（`tools/run_experiment.py`）与文档统一使用这里的名称。

所有模式共用：标准灰度转换 → 逻辑宽 128（保持长宽比）→ 严格黑白二值 →
nearest-neighbor ×10 方块放大。输出严格只含 0/255，deterministic。

| 名称 | 核心算法 | 默认参数 | 视觉特征 |
|---|---|---|---|
| `classic` | 用户早年算法（双阈值 + 稀疏子网格），语义冻结 | s=2, t=127, b=60，默认直方图均衡 | 稀疏网格网点，颗粒粗粝；基准 |
| `bayer4` | Bayer 4×4 ordered dithering | 标准 4×4 矩阵 | 规则机械网点，稳定，最贴"伪像素点图"主题 |
| `adaptive_fine` | Adaptive **Gaussian** 局部阈值 | blockSize=11, C=2 | 细密、漫画墨线、雕版/蚀刻/刻线感 |
| `adaptive_bold` | Adaptive **Mean** 局部阈值 | blockSize=25, C=2 | 粗块、主体感强、木刻/海报感 |

Classic 的精确行为以 `docs/classic_algorithm.md` 为准，不允许修改语义；
bayer4 实现冻结，不调整。

## 非正式（实验阶段 / 开发基准）

以下实现保留在 `src/algorithms.py` 中供内部对照，**不进入正式算法列表，
也不进入未来的正式 GUI**：

- `m1_otsu`、`m4_gradient`、`m5_pattern` —— 第一轮实验候选，未入选；
- `m3_adaptive`（Mean / 11 / C=2）—— 第一轮原始 adaptive，保留为开发/回归基准；
- 第二轮的 `m3_smooth`（median 预平滑）与 `m3_original` 别名已随收敛移除，
  实验阶段的 `m3_alt_method` / `m3_large_window` 命名已分别正名为
  `adaptive_fine` / `adaptive_bold`。
