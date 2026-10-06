"""Classic fidelity boundary：正式 classic() 与 Legacy Oracle 的边界测试。

本文件是长期边界测试，表达的是**有意设计**而非待修 bug。

正式 `classic()` 保留 Legacy 的**二值算法语义**（直方图均衡、两阶段 INTER_LINEAR
缩放、双阈值稀疏子网格、网点密度），但几何模型统一为严格 P×P（宽高均为 P 整数倍）。

因此本测试验证正式产品契约（而非错误的全局尺寸差异上限）：

  1. classic 输出尺寸严格等于 compute_geometry() 的 actual 尺寸；
  2. actual width/height 均为 P 整数倍；
  3. 每个逻辑像素严格 P×P（actual = logical × P）；
  4. requested width -> actual width 是最近合法 P 网格吸附（宽度差 ≤ P/2，数学严格成立）；
  5. 长宽比采用整数逻辑网格下的最近近似；
  6. 当 Product geometry 与 Legacy geometry 恰好一致时，算法结果逐像素一致；
  7. 对明确选定的 divergence 样本记录具体尺寸差异，不推广为全局上限。

注意：**不存在**「高度差恒 ≤ P」之类的普遍保证——宽度吸附误差会经源图宽高比
放大到高度，极端长宽比下高度差可能远超 P。

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
# 3. 正式产品契约：requested -> actual 吸附 / 长宽比近似
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("out_w,p", PARAM_CASES)
def test_classic_requested_width_adsorbs_to_nearest_p_grid(out_w, p):
    """requested width -> actual width 是最近合法 P 网格吸附。

    宽度吸附误差数学上严格 ≤ P/2（round 到最近 P 整数倍），这是唯一可普遍保证的
    宽度级契约。高度差异不在此设上限（见 test_classic_intentional_divergence_recorded）。
    """
    h, w = 600, 800
    img = make_pattern(h, w, seed=hash(("adsorb", out_w, p)) & 0xFFFFFFFF)
    got = algorithms.classic(img, output_width=out_w, pixel_block_size=p,
                             t=127, b=60, equalize=True)

    geo = compute_geometry(w, h, out_w, p)
    # actual_w = round(out_w / P) * P，吸附误差 ≤ P/2
    assert got.shape[1] == geo.actual_output_width
    assert abs(geo.actual_output_width - out_w) <= p / 2, "宽度吸附误差超过 P/2"
    # actual_w 是 P 整数倍
    assert geo.actual_output_width % p == 0


@pytest.mark.parametrize("h,w", SIZES)
def test_classic_aspect_ratio_nearest_integer_approx(h, w):
    """长宽比采用整数逻辑网格下的最近近似。

    logical_height = round(logical_width * H/W)，即高度在整数逻辑网格上最接近原比例。
    """
    img = make_pattern(h, w, seed=hash(("aspect", h, w)) & 0xFFFFFFFF)
    got = algorithms.classic(img, output_width=1000, pixel_block_size=2,
                             t=127, b=60, equalize=True)

    geo = compute_geometry(w, h, 1000, 2)
    # 逻辑高 = round(逻辑宽 * 源高 / 源宽)
    expected_lh = max(1, round(geo.logical_width * h / w))
    assert geo.logical_height == expected_lh, "逻辑高不符合整数网格最近近似"
    # 输出高 = logical_height * P，严格 P 整数倍
    assert got.shape[0] == geo.actual_output_height == geo.logical_height * 2


# ---------------------------------------------------------------------------
# 4. intentional divergence：对明确选定的样本记录具体尺寸差异（不设全局上限）
# ---------------------------------------------------------------------------

# 明确选定的 divergence 样本：(源高, 源宽, requested_width, pixel_block_size, 期望 dw, 期望 dh)
# 其中 dw = legacy_w - product_w，dh = legacy_h - product_h。
# 记录具体差异作为回归锚点，而非普遍数学保证。
DIVERGENCE_SAMPLES = [
    # (h, w, out_w, p, dw, dh)
    (600, 800, 1000, 3, 1, 0),   # actual_w=999 (legacy 1000)，高同为 750
    (800, 600, 1001, 4, 1, 2),   # actual_w=1000 (legacy 1001)，actual_h=1332 (legacy 1334)
]


@pytest.mark.parametrize("h,w,out_w,p,exp_dw,exp_dh", DIVERGENCE_SAMPLES)
def test_classic_intentional_divergence_recorded(h, w, out_w, p, exp_dw, exp_dh):
    """对明确选定的 divergence 样本，记录 Legacy 与 Product 的具体尺寸差异。

    本测试只验证：
      - Legacy 宽度恒等于 d（历史语义）；
      - Product 严格等于统一 geometry；
      - 记录二者具体差异值（作为锚点，防止无意回归）。

    **不**断言任何「高度差 ≤ P」之类的全局上限——那在极端长宽比下不成立。
    """
    img = make_pattern(h, w, seed=hash(("rec", h, w, out_w, p)) & 0xFFFFFFFF)
    got = algorithms.classic(img, output_width=out_w, pixel_block_size=p,
                             t=127, b=60, equalize=True)
    ref = legacy_oracle(img, d=out_w, s=p, t=127, b=60, equalize=True)

    # Legacy 宽度恒等于 d
    assert ref.shape[1] == out_w, "oracle 宽应恒等于 d（Legacy 语义）"

    # Product 严格等于统一 geometry
    geo = compute_geometry(w, h, out_w, p)
    assert got.shape[1] == geo.actual_output_width
    assert got.shape[0] == geo.actual_output_height

    # 记录具体尺寸差异（锚点；不同样本差异不同，无全局上限）
    dw = ref.shape[1] - got.shape[1]
    dh = ref.shape[0] - got.shape[0]
    assert dw == exp_dw, f"宽度差异漂移: dw={dw}, 期望 {exp_dw}"
    assert dh == exp_dh, f"高度差异漂移: dh={dh}, 期望 {exp_dh}"

    # 宽度差异有界（吸附 ≤ P/2）；高度差异**不**设上限（仅记录，不推广）
    assert abs(dw) <= p / 2


# ---------------------------------------------------------------------------
# 5. equalize=False 且几何一致：算法语义一致
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
# 6. 默认参数二值 & deterministic
# ---------------------------------------------------------------------------

def test_classic_default_binary_and_deterministic():
    """默认参数输出严格二值且 deterministic。"""
    img = make_pattern(640, 640, seed=42)
    a = algorithms.classic(img)
    b = algorithms.classic(img)
    assert set(np.unique(a).tolist()) <= {0, 255}
    assert np.array_equal(a, b)
