# Modern 第一轮视觉实验实现说明

> 本文档记录第一轮 Modern 候选的**精确实现**与**固定参数**，供人工审查与后续迭代。
> 不宣布任何 Modern 最终胜出；Classic 语义未变，仍以 `docs/classic_algorithm.md` 为准。

## 目录结构

```
src/            实验算法实现（脚手架 + 六个算法）
  config.py     全部固定参数（集中记录，第一轮不扫描）
  pipeline.py   共享脚手架：灰度 / 缩小 / 放大 / Classic 管线
  algorithms.py Classic + M1~M5 六个算法入口
tools/          最小实验入口与测试图生成
  run_experiment.py   输入一张图 -> 一次输出 6 张 + contact sheet
  make_test_image.py  生成无版权争议的程序化测试图
tests/          确定性 / 二值性 / 尺寸 / Classic 一致性 / legacy 未改
outputs/        实验输出（默认不进 Git，见 .gitignore）
```

## 统一实验条件（所有 Modern 候选一致）

| 项 | 值 | 说明 |
|---|---|---|
| 灰度转换 | `cv2.cvtColor(BGR2GRAY)` | 标准加权 |
| 逻辑宽度 | `LOGICAL_WIDTH = 128` | 见 config 注释（2 的幂、颗粒感适中、输出便于观察） |
| 长宽比 | 保持原图，不强制正方形 | 逻辑高 = `int(128*h/w)`（与 Classic 的 `int()` 截断一致） |
| Modern 缩小插值 | `INTER_AREA` | 区域平均 |
| 最终放大 | `INTER_NEAREST`，`SCALE_UP=10` | 锐利方块 |
| 确定性 | 同输入同参必同输出 | 有测试保证 |
| 输出 | 严格 0/255 的 3 通道 BGR | 有测试保证 |

**逻辑宽度取 128 的理由**：(1) 2 的幂，Bayer 4×4 与自定义 2×2 pattern 都能整除，避免尾块不整；(2) 低到足以保留老式单色 LCD 颗粒感，又不至于五官难辨；(3) 输出 1280×(按长宽比) 便于肉眼观察每个逻辑方块。

## 六种算法实现概要

### Classic（基准）
严格复现 `docs/classic_algorithm.md`：默认直方图均衡预处理（丢弃彩色）→ 两阶段 `INTER_LINEAR` 缩放 → 全白画布 → 第一轮 `(偶,偶)` 且 `a<t` 置黑 → 第二轮全位置 `a<b` 置黑（无 else，不回白）→ `INTER_NEAREST` 放大。
**对齐说明**：Classic 语义中 `d` 是第一阶段宽度、逻辑网格再 `÷s(=2)`。为让其逻辑网格与 Modern 一致（宽=128），实验入口传 `d = 128*2 = 256`，**仅按其实际缩放结构对齐逻辑分辨率，不改变 Classic 语义**。

### M1 = AREA + Otsu
`BGR2GRAY` → `INTER_AREA` 缩到 128 宽 → `cv2.threshold(..., THRESH_BINARY+THRESH_OTSU)` → nearest 放大。Otsu 自动选全局阈值，无手动参数。

### M2 = AREA + Bayer 4×4
`BGR2GRAY` → `INTER_AREA` 缩到 128 宽 → 标准 4×4 Bayer 矩阵（`[[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]]`，映射到 0..255 灰度域）逐像素比较 → nearest 放大。第一轮只用固定标准矩阵，不扫矩阵大小。

### M3 = AREA + Adaptive Threshold
`BGR2GRAY` → `INTER_AREA` 缩到 128 宽 → `cv2.adaptiveThreshold(..., ADAPTIVE_THRESH_MEAN_C, THRESH_BINARY, blockSize=11, C=2)` → nearest 放大。
**选择 adaptive mean 而非 Gaussian 的理由**：Gaussian 权重中心高、边缘低，在高对比细线处容易把细线拉成断点；mean 对窗口内所有像素一视同仁，更能保住动漫图大色块内部一致性。第一轮固定 `blockSize=11, C=2`，不扫描。

### M4 = Gradient / Edge Driven
`BGR2GRAY` → `INTER_AREA` 缩到 128 宽 → 对灰度图做 x/y 方向 `cv2.Sobel(CV_64F, ksize=3)` → 幅值用 L2 范数 `sqrt(gx²+gy²)` → **幅值 ≥ 30 判为结构（黑），否则白**（`GRAD_INVERT=True`，即轮廓黑/背景白，偏线条版）→ nearest 放大。
**二值化规则**：`黑 = { |∇I| ≥ 30 }`。允许偏轮廓化/抽象，但不以"越不像原图越好"为目标。第一轮固定 `ksize=3, thresh=30`，不扫参。

### M5 = Custom Pattern Mapping（自定义图案映射）
`BGR2GRAY` → `INTER_AREA` 缩到 128 宽 → 亮度线性分桶到 5 档（`level = round(gray/255 * 4)`，0..4）→ 每个逻辑像素按档位查 2×2 黑白小图案，在同一逻辑网格的 2 倍承载层上展开（每个逻辑像素 → 2×2）→ 放大到与其它候选一致的最终尺寸（等效 `SCALE_UP/2`），每个输出逻辑像素是一个带 2×2 纹理的方块。

**图案表**（2×2，1=黑，从全白到全黑共 5 档空间密度）：

| level | 图案 | 黑密度 | 含义 |
|---|---|---|---|
| 0 | `[[0,0],[0,0]]` | 0/4 | 全白 |
| 1 | `[[1,0],[0,0]]` | 1/4 | 左上角单黑 |
| 2 | `[[1,0],[0,1]]` | 2/4 | 对角双黑 |
| 3 | `[[1,1],[0,1]]` | 3/4 | 三黑（缺左下） |
| 4 | `[[1,1],[1,1]]` | 4/4 | 全黑 |

**分桶规则**：`level = clip(round(gray/255 * 4), 0, 4)`（均匀五档）。
**刻意不用标准 Bayer 2×2**（Bayer 2×2 顺序为 `0,2 / 3,1`），这里用「先角后边」的填充顺序，让低密度时黑点更孤立、高密度时呈块状。第一轮不做内容感知开关。

## 测试

`tests/` 共 24 项，全部通过：

1. 每个候选输出只有 0/255（6 项）；
2. 输出尺寸正确且保持长宽比（6 项）+ 六算法输出尺寸完全一致（1 项）；
3. 同输入同参 deterministic（6 项）；
4. Classic 行为与文档一致——真值表核验 `黑={a<b}∪{y偶∧x偶∧b≤a<t}`（1 项）+ 第二轮不回白（1 项）；
5. legacy 三份原件 SHA-256 未变（3 项）。

运行：`python3.11 -m pytest tests/ -v`
