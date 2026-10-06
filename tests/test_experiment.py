"""参数化重构后的正式四模式 + 回归测试。

覆盖（对应施工要求第八节的 13 类）：
  1. Classic 原始默认语义回归（独立参考实现逐像素一致）
  2. Bayer matrix=4/bias=0 与历史实现逐像素一致
  3. Fine block=11/C=2 与历史实现逐像素一致
  4. Bold block=25/C=2 与历史实现逐像素一致
  5. Bayer 2x2/8x8 输出合法、严格二值、deterministic
  6. tone bias 边界
  7. Classic t/b 边界
  8. b>=t 仍允许运行
  9. Adaptive blockSize 校验：奇数>=3 合法；偶数或<3 拒绝；不因大于逻辑图尺寸而拒绝
  10. invert 必须等于非 invert 输出的逐像素 255-x
  11. 尺寸模型：每逻辑块严格 P×P；actual width/height 为 P 整数倍；长宽比为整数网格最接近近似
  12. 四正式模式严格二值、deterministic
  13. legacy 三份 .py SHA-256 完全不变

运行：python3.11 -m pytest tests/ -v
"""

import os
import subprocess

import cv2
import numpy as np
import pytest

from src import algorithms
from src.params import (
    compute_geometry,
    CLASSIC_DEFAULT_T,
    CLASSIC_DEFAULT_B,
    ADAPTIVE_FINE_DEFAULT_BLOCK,
    ADAPTIVE_BOLD_DEFAULT_BLOCK,
    ADAPTIVE_DEFAULT_C,
)
from src.pipeline import to_gray

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FORMAL = list(algorithms.FORMAL_MODES)
FORMAL_NAMES = [n for n, _ in FORMAL]

LEGACY_SHA = {
    "legacy/xiangsudian.py": "d2dd4d6879e0e4b4392e3f54c1ca03b5037c8dc73405ff9e444685c94794ae16",
    "legacy/xiangsudian2.py": "ba1053a6fd9040061735806d7d4288c1008aa527f56e0a3645bd02532be08ca2",
    "legacy/xiangsudian3.py": "f103e325f03a0e1f26b1c6658d9c26a748cf1526aa3d5b29cc19625036f987a9",
}


@pytest.fixture(scope="module")
def test_img():
    """确定性测试图。"""
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, (64, 80, 3), dtype=np.uint8)
    return img


# ---------------------------------------------------------------------------
# 参考实现：复刻参数化重构前的历史默认行为（用于回归比对）
# ---------------------------------------------------------------------------

def _classic_reference(img_bgr, output_width=1000, s=2, t=127, b=60, equalize=True):
    """独立参考实现：统一 P×P geometry 下的 Classic（用于回归比对）。

    注意：与 legacy/xiangsudian.py 的差异见 tests/test_classic_fidelity.py。
    这里复刻的是「统一 geometry + 祖传双阈值语义」，宽度/高度均走 compute_geometry。
    """
    if equalize:
        gray = to_gray(img_bgr)
        eq = cv2.equalizeHist(gray)
        inp = cv2.cvtColor(eq, cv2.COLOR_GRAY2BGR)
    else:
        inp = img_bgr
    h0, w0 = inp.shape[:2]
    geo = compute_geometry(w0, h0, output_width, s)
    aw, ah = geo.actual_output_width, geo.actual_output_height
    lw, lh = geo.logical_width, geo.logical_height
    first = cv2.resize(inp, (aw, ah))
    second = cv2.resize(first, (lw, lh))
    H, W = second.shape[:2]
    canvas = np.full((H, W, 3), 255, np.uint8)
    a = second.mean(axis=2)
    for i in range(0, H, 2):
        for j in range(0, W, 2):
            if a[i, j] < t:
                canvas[i, j] = [0, 0, 0]
    for i in range(H):
        for j in range(W):
            if a[i, j] < b:
                canvas[i, j] = [0, 0, 0]
    return cv2.resize(canvas, (aw, ah), interpolation=cv2.INTER_NEAREST)


def _bayer4_reference(img_bgr, output_width=1280, p=10, matrix_size=4, tone_bias=0):
    B = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32) * (255.0 / 15.0)
    gray = to_gray(img_bgr)
    h0, w0 = gray.shape[:2]
    geo = compute_geometry(w0, h0, output_width, p)
    small = cv2.resize(gray, (geo.logical_width, geo.logical_height), interpolation=cv2.INTER_AREA)
    if tone_bias != 0:
        small = np.clip(small.astype(np.int32) + tone_bias, 0, 255).astype(np.uint8)
    h, w = small.shape
    tiled = np.tile(B, ((h + matrix_size - 1) // matrix_size, (w + matrix_size - 1) // matrix_size))[:h, :w]
    bw = np.where(small.astype(np.float32) > tiled, 255, 0).astype(np.uint8)
    up = cv2.resize(bw, (geo.actual_output_width, geo.actual_output_height), interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(up, cv2.COLOR_GRAY2BGR)


def _adaptive_reference(img_bgr, method, block, c, output_width=1280, p=10):
    gray = to_gray(img_bgr)
    h0, w0 = gray.shape[:2]
    geo = compute_geometry(w0, h0, output_width, p)
    small = cv2.resize(gray, (geo.logical_width, geo.logical_height), interpolation=cv2.INTER_AREA)
    bw = cv2.adaptiveThreshold(small, 255, method, cv2.THRESH_BINARY, block, c)
    up = cv2.resize(bw, (geo.actual_output_width, geo.actual_output_height), interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(up, cv2.COLOR_GRAY2BGR)


# ---------------------------------------------------------------------------
# 12. 四模式严格二值 + deterministic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,fn", FORMAL)
def test_formal_binary_and_deterministic(name, fn, test_img):
    a = fn(test_img)
    b = fn(test_img)
    assert set(np.unique(a).tolist()) <= {0, 255}, f"{name} 非二值"
    assert np.array_equal(a, b), f"{name} 非 deterministic"


# ---------------------------------------------------------------------------
# 1-4. 默认参数逐像素回归（与历史实现一致）
# ---------------------------------------------------------------------------

def test_classic_default_regression(test_img):
    got = algorithms.classic(test_img)  # 默认 output_width=1000, s=2, t=127, b=60, equalize=True
    ref = _classic_reference(test_img)
    assert np.array_equal(got, ref), "Classic 默认输出与统一 geometry 参考实现不一致"


def test_bayer4_default_regression(test_img):
    got = algorithms.bayer4(test_img)  # matrix=4, bias=0, 1280/10
    ref = _bayer4_reference(test_img)
    assert np.array_equal(got, ref), "Bayer4 默认输出与历史实现不一致"


def test_adaptive_fine_default_regression(test_img):
    got = algorithms.adaptive_fine(test_img)  # Gaussian/11/2, 1280/10
    ref = _adaptive_reference(test_img, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 11, 2)
    assert np.array_equal(got, ref), "adaptive_fine 默认输出与历史实现不一致"


def test_adaptive_bold_default_regression(test_img):
    got = algorithms.adaptive_bold(test_img)  # Mean/25/2, 1280/10
    ref = _adaptive_reference(test_img, cv2.ADAPTIVE_THRESH_MEAN_C, 25, 2)
    assert np.array_equal(got, ref), "adaptive_bold 默认输出与历史实现不一致"


# ---------------------------------------------------------------------------
# 5. Bayer 2x2 / 8x8 合法、二值、deterministic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("m", [2, 4, 8])
def test_bayer_matrix_sizes(m, test_img):
    a = algorithms.bayer4(test_img, matrix_size=m)
    b = algorithms.bayer4(test_img, matrix_size=m)
    assert set(np.unique(a).tolist()) <= {0, 255}, f"Bayer {m} 非二值"
    assert np.array_equal(a, b), f"Bayer {m} 非 deterministic"


# ---------------------------------------------------------------------------
# 6. tone bias 边界
# ---------------------------------------------------------------------------

def test_tone_bias_extremes(test_img):
    for bias in (-128, -1, 0, 1, 128):
        out = algorithms.bayer4(test_img, tone_bias=bias)
        assert set(np.unique(out).tolist()) <= {0, 255}, f"bias={bias} 非二值"


# ---------------------------------------------------------------------------
# 7/8. Classic t/b 边界；b>=t 允许
# ---------------------------------------------------------------------------

def test_classic_threshold_bounds(test_img):
    for t, b in [(0, 0), (255, 255), (127, 60), (60, 127), (200, 100)]:
        out = algorithms.classic(test_img, t=t, b=b)
        assert set(np.unique(out).tolist()) <= {0, 255}, f"t={t},b={b} 非二值"


def test_classic_b_ge_t_allowed(test_img):
    # b >= t 合法，不拒绝
    out = algorithms.classic(test_img, t=60, b=127)
    assert out is not None
    # 与 equalize=False 组合也允许
    algorithms.classic(test_img, t=100, b=200, equalize=False)


def test_classic_equalize_off(test_img):
    on = algorithms.classic(test_img, equalize=True)
    off = algorithms.classic(test_img, equalize=False)
    # 默认 equalize=True；off 应能正常二值
    assert set(np.unique(off).tolist()) <= {0, 255}
    assert on.shape == off.shape


# ---------------------------------------------------------------------------
# 9. Adaptive blockSize 校验
# ---------------------------------------------------------------------------

def test_adaptive_block_valid(test_img):
    # 奇数 >=3 合法
    algorithms.adaptive_fine(test_img, block_size=3)
    algorithms.adaptive_fine(test_img, block_size=11)
    algorithms.adaptive_bold(test_img, block_size=25)


def test_adaptive_block_invalid_rejected(test_img):
    # 偶数拒绝
    with pytest.raises(ValueError):
        algorithms.adaptive_fine(test_img, block_size=10)
    # <3 拒绝
    with pytest.raises(ValueError):
        algorithms.adaptive_bold(test_img, block_size=1)
    with pytest.raises(ValueError):
        algorithms.adaptive_bold(test_img, block_size=2)


def test_adaptive_block_larger_than_image_not_rejected(test_img):
    # blockSize 大于逻辑图尺寸不应被 API 层拒绝（OpenCV 边界扩展处理）
    # 逻辑图较小边：64x80 -> 1280/10=128 宽，64*128/80=102 高，较小边=102
    big = 1001  # 奇数且 > 逻辑较小边
    out = algorithms.adaptive_bold(test_img, block_size=big)
    assert set(np.unique(out).tolist()) <= {0, 255}


def test_adaptive_c_negative_and_zero(test_img):
    for c in (-32, -1, 0, 1, 32):
        out = algorithms.adaptive_fine(test_img, c=c)
        assert set(np.unique(out).tolist()) <= {0, 255}, f"C={c} 非二值"


# ---------------------------------------------------------------------------
# 10. invert 语义
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,fn", FORMAL)
def test_invert_is_bitwise_not(name, fn, test_img):
    normal = fn(test_img, invert=False)
    inverted = fn(test_img, invert=True)
    assert np.array_equal(inverted, 255 - normal), f"{name} invert 不等于逐像素 255-x"


# ---------------------------------------------------------------------------
# 11. 尺寸模型
# ---------------------------------------------------------------------------

def test_geometry_blocks_exact_p(test_img):
    h0, w0 = test_img.shape[:2]
    for name, fn in FORMAL:
        out = fn(test_img)
        oh, ow = out.shape[:2]
        # 每个逻辑块严格 P×P => 输出宽/高必须能被 P 整除（取各模式默认 P）
        # classic 默认 P=2, 其余 P=10
        P = 2 if name == "classic" else 10
        assert ow % P == 0 and oh % P == 0, f"{name} 输出尺寸不是 P={P} 的整数倍"


def test_geometry_actual_size(test_img):
    h0, w0 = test_img.shape[:2]
    # classic: output_width=1000, P=2 -> logical_w=500, actual_w=1000
    geo = compute_geometry(w0, h0, 1000, 2)
    assert geo.actual_output_width == 1000
    assert geo.actual_output_width == geo.logical_width * geo.pixel_block_size
    # bayer: 1280/10 -> logical_w=128, actual_w=1280
    geo2 = compute_geometry(w0, h0, 1280, 10)
    assert geo2.actual_output_width == 1280
    assert geo2.logical_width == 128


def test_geometry_aspect_approx(test_img):
    h0, w0 = test_img.shape[:2]
    geo = compute_geometry(w0, h0, 1280, 10)
    # 逻辑高 = round(逻辑宽 * h/w)
    expected_lh = max(1, round(geo.logical_width * h0 / w0))
    assert geo.logical_height == expected_lh


# ---------------------------------------------------------------------------
# 13. legacy 原件未改
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("relpath,sha", sorted(LEGACY_SHA.items()))
def test_legacy_unchanged(relpath, sha):
    path = os.path.join(REPO_ROOT, relpath)
    out = subprocess.check_output(["sha256sum", path]).decode().split()[0]
    assert out == sha, f"{relpath} SHA-256 变化"


# ---------------------------------------------------------------------------
# 附：实验/基准模式轻量覆盖
# ---------------------------------------------------------------------------

def test_experimental_modes_still_run(test_img):
    for name in ("m1_otsu", "m3_adaptive", "m4_gradient", "m5_pattern"):
        fn = getattr(algorithms, name)
        out = fn(test_img)
        assert set(np.unique(out).tolist()) <= {0, 255}, f"{name} 非二值"
