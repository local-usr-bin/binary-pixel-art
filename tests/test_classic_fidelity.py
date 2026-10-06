"""Classic fidelity boundary：正式 classic() 与 Legacy Oracle 的边界测试。

本文件是长期边界测试，表达的是**有意设计**而非待修 bug。

正式 `classic()` 保留 Legacy 的**二值算法语义**（直方图均衡、两阶段 INTER_LINEAR
缩放、双阈值稀疏子网格、网点密度），但几何模型统一为严格 P×P（宽高均为 P 整数倍）。

因此本测试验证三类命题：

  1. 统一 geometry：classic 输出宽高 = actual_output_width/height，均为 P 整数倍，
     每个逻辑块严格 P×P；
  2. 算法语义保真：当几何尺寸恰好与 Legacy 一致时（如正方形源图），逐像素一致；
  3. intentional divergence：与 Legacy 的尺寸差异 ≤ ±(P-1) px，属已记录的预期设计。

运行：
    python3.11 -m pytest tests/test_classic_fidelity.py -v

本测试只读当前 classic()，并独立依据 legacy/xiangsudian.py 建立 oracle。
"""

import cv2
import numpy as np
import pytest

from src import algorithms
from src.params import compute_geometry


# ---------------------------------------------------------------------------
# 独立 Legacy Oracle：完全复刻 legacy/xiangsudian.py 的处理顺序
# ---------------------------------------------------------------------------

def legacy_oracle(img_bgr, d=1000, s=2, t=127, b=60, equalize=True):
    """按 legacy 原始顺序独立实现，不复用当前 classic()。

    保持：
      - equalize：灰度重读 -> equalizeHist -> GRAY2BGR；
      - 第一次 resize：宽 d，高 int(d*src_h/src_w)，默认 INTER_LINEAR；
      - 第二次 resize：宽 int(first_w/s)，高 int(first_h/s)，默认 INTER_LINEAR；
      - 两轮阈值（第一轮偶行偶列 t，第二轮全图 b，无 else）；
      - 最终 INTER_NEAREST 回 d × int(d*src_h/src_w)。
    """
    if equalize:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        img_s_e = cv2.equalizeHist(gray)
        img_input = cv2.cvtColor(img_s_e, cv2.COLOR_GRAY2BGR)
    else:
        img_input = img_bgr

    H, W = img_input.shape[:2]

    first = cv2.resize(img_input, (d, int(d * H / W)))
    second = cv2.resize(
        first,
        (int(first.shape[1] / s), int(first.shape[0] / s)),
    )

    canvas = np.zeros((second.shape[0], second.shape[1], 3), np.uint8)
    canvas[:] = [255, 255, 255]

    for i in range(0, second.shape[0], 2):
        for j in range(0, second.shape[1], 2):
            a = (int(second[i, j][0]) + int(second[i, j][1]) + int(second[i, j][2])) / 3
            if a < t:
                canvas[i, j][0] = 0
                canvas[i, j][1] = 0
                canvas[i, j][2] = 0

    for i in range(0, second.shape[0]):
        for j in range(0, second.shape[1]):
            a = (int(second[i, j][0]) + int(second[i, j][1]) + int(second[i, j][2])) / 3
            if a < b:
                canvas[i, j][0] = 0
                canvas[i, j][1] = 0
                canvas[i, j][2] = 0

    return cv2.resize(canvas, (d, int(d * H / W)), interpolation=cv2.INTER_NEAREST)


# ---------------------------------------------------------------------------
# 程序化输入样本（deterministic，避免纯色掩盖 resize 差异）
# ---------------------------------------------------------------------------

def make_pattern(h, w, seed):
    """生成带渐变 + 高频纹理的彩色 pattern，避免纯色。"""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = (xx / w * 200 + yy / h * 55).astype(np.float32)
    checker = ((xx.astype(int) // 3 + yy.astype(int) // 3) % 2) * 60
    noise = rng.integers(-20, 21, (h, w)).astype(np.float32)
    g = np.clip(base + checker + noise, 0, 255).astype(np.uint8)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)


# 尺寸样本：(height, width) —— 覆盖各种取整边界
SIZES = [
    (600, 800),
    (800, 600),
    (667, 1000),
    (853, 640),
    (640, 640),
    (601, 801),
    (500, 500),
    (375, 1000),
]

# 几何恰好一致的样本：round(logical_w*H/W)*P == int(d*H/W) 时，classic 与 Legacy 逐像素一致。
# 正方形（或宽高比使除法整除）满足此条件。
GEOMETRY_AGREE_SIZES = [
    (640, 640),   # 正方形：int(1000*640/640)=1000 == round(500*640/640)*2=1000
    (500, 500),   # 正方形
]

# 参数组合：(requested_output_width, pixel_block_size)
PARAM_CASES = [
    (1000, 2),    # 默认，可整除
    (1000, 3),    # 不可整除 -> actual 999
    (1001, 4),    # 不可整除 -> actual 1000
]


# ---------------------------------------------------------------------------
# 1. 统一 geometry：宽高均为 P 整数倍、严格 P×P
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("out_w,p", PARAM_CASES)
@pytest.mark.parametrize("h,w", SIZES)
def test_classic_uses_unified_pp_geometry(h, w, out_w, p):
    """classic 输出宽高均走统一 geometry（P 整数倍，严格 P×P）。"""
    img = make_pattern(h, w, seed=hash(("geo", out_w, p, h, w)) & 0xFFFFFFFF)
    got = algorithms.classic(img, output_width=out_w, pixel_block_size=p,
                             t=127, b=60, equalize=True)

    geo = compute_geometry(w, h, out_w, p)
    # 宽高严格等于统一 geometry 的 actual 尺寸
    assert got.shape[1] == geo.actual_output_width, "actual 宽度不符合统一 geometry"
    assert got.shape[0] == geo.actual_output_height, "actual 高度不符合统一 geometry"
    # 均为 P 整数倍
    assert got.shape[1] % p == 0, "actual 宽度不是 P 整数倍"
    assert got.shape[0] % p == 0, "actual 高度不是 P 整数倍"
    # 严格 P×P（actual = logical × P）
    assert geo.actual_output_width == geo.logical_width * p
    assert geo.actual_output_height == geo.logical_height * p
    # 严格二值
    assert set(np.unique(got).tolist()) <= {0, 255}, "classic 输出非二值"


# ---------------------------------------------------------------------------
# 2. 算法语义保真：几何一致时逐像素一致
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("h,w", GEOMETRY_AGREE_SIZES)
def test_classic_matches_legacy_when_geometry_agrees(h, w):
    """当几何尺寸恰好一致（如正方形源图）时，classic 与 Legacy 逐像素一致。

    证明：祖传二值算法语义（均衡/两阶段缩放/双阈值/网点密度）被完整保留，
    差异仅在几何取整层。
    """
    img = make_pattern(h, w, seed=hash(("agree", h, w)) & 0xFFFFFFFF)
    got = algorithms.classic(img, output_width=1000, pixel_block_size=2,
                             t=127, b=60, equalize=True)
    ref = legacy_oracle(img, d=1000, s=2, t=127, b=60, equalize=True)
    assert got.shape == ref.shape, f"几何一致样本尺寸应一致: got {got.shape} ref {ref.shape}"
    assert np.array_equal(got, ref), f"几何一致样本应逐像素一致 ({h}x{w})"


# ---------------------------------------------------------------------------
# 3. intentional divergence：尺寸差异 ≤ ±(P-1) px，属预期设计
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("out_w,p", PARAM_CASES)
@pytest.mark.parametrize("h,w", SIZES)
def test_classic_intentional_divergence_bounded(h, w, out_w, p):
    """classic 与 Legacy 的尺寸差异是预期的，且宽度差异 ≤ P-1。

    Legacy 宽恒为 d（=out_w），classic 宽为 P 整数倍（吸附到最近合法值），
    二者差不超过 P-1。高度差异同样由几何取整决定，属 intentional divergence。
    """
    img = make_pattern(h, w, seed=hash(("div", out_w, p, h, w)) & 0xFFFFFFFF)
    got = algorithms.classic(img, output_width=out_w, pixel_block_size=p,
                             t=127, b=60, equalize=True)
    ref = legacy_oracle(img, d=out_w, s=p, t=127, b=60, equalize=True)

    # Legacy 宽度恒等于 d
    assert ref.shape[1] == out_w, "oracle 宽应恒等于 d（Legacy 语义）"

    geo = compute_geometry(w, h, out_w, p)
    # 宽度差异 = |out_w - actual_w|，吸附到最近 P 整数倍，故 ≤ P-1
    assert abs(ref.shape[1] - got.shape[1]) <= p - 1, "宽度偏差超出预期 ±(P-1) px"
    # 高度差异由几何取整决定，同样有界（不要求逐像素一致）
    assert abs(ref.shape[0] - got.shape[0]) <= p, "高度偏差异常"
    # classic 宽高仍严格 P 整数倍
    assert got.shape[1] == geo.actual_output_width
    assert got.shape[0] == geo.actual_output_height


# ---------------------------------------------------------------------------
# 4. equalize=False 且几何一致：算法语义一致
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("h,w", GEOMETRY_AGREE_SIZES)
def test_classic_equalize_off_geometry_agrees(h, w):
    """equalize=False 且几何一致（正方形）时，classic 与 Legacy 逐像素一致。"""
    img = make_pattern(h, w, seed=hash(("off-agree", h, w)) & 0xFFFFFFFF)
    got = algorithms.classic(img, output_width=1000, pixel_block_size=2,
                             t=127, b=60, equalize=False)
    ref = legacy_oracle(img, d=1000, s=2, t=127, b=60, equalize=False)
    assert got.shape == ref.shape
    assert np.array_equal(got, ref)


# ---------------------------------------------------------------------------
# 5. 默认参数二值 & deterministic
# ---------------------------------------------------------------------------

def test_classic_default_binary_and_deterministic():
    """默认参数输出严格二值且 deterministic。"""
    img = make_pattern(640, 640, seed=42)
    a = algorithms.classic(img)
    b = algorithms.classic(img)
    assert set(np.unique(a).tolist()) <= {0, 255}
    assert np.array_equal(a, b)
