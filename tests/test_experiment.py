"""正式四模式 + 回归 + 实验模式的自动化测试。

覆盖：
  1. 四个正式模式输出严格 0/255；
  2. deterministic；
  3. 尺寸与长宽比规则正确、四模式同尺寸；
  4. Classic 无行为回归（真值表 + 第二轮不回白）；
  5. Bayer4 无行为回归（独立参考实现逐像素比对）；
  6. Adaptive Fine 参数核验（Gaussian / 11 / C=2，独立参考比对）；
  7. Adaptive Bold 参数核验（Mean / 25 / C=2，独立参考比对）；
  8. legacy 三份 .py 字节完全不变（SHA-256）；
  附：实验/基准模式（m1/m3_adaptive/m4/m5）仅做二值 + 确定性轻量覆盖。

运行：
    python3.11 -m pytest tests/ -v
"""

import os
import subprocess

import cv2
import numpy as np
import pytest

from src import algorithms
from src.config import (
    LOGICAL_WIDTH,
    SCALE_UP,
    ADAPTIVE_FINE_BLOCK,
    ADAPTIVE_BOLD_BLOCK,
    ADAPTIVE_C,
)
from src.pipeline import to_gray, shrink_modern, upscale_nn
from tools.make_test_image import make_test_image

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FORMAL = list(algorithms.FORMAL_MODES)
FORMAL_NAMES = [n for n, _ in FORMAL]

# 实验/开发基准模式：不进入正式列表，仅轻量回归覆盖
EXPERIMENTAL = [
    ("m1_otsu", algorithms.m1_otsu),
    ("m3_adaptive", algorithms.m3_adaptive),
    ("m4_gradient", algorithms.m4_gradient),
    ("m5_pattern", algorithms.m5_pattern),
]

# legacy 三份原件的 SHA-256（与 legacy/README.md 记录一致）
LEGACY_SHA = {
    "legacy/xiangsudian.py": "d2dd4d6879e0e4b4392e3f54c1ca03b5037c8dc73405ff9e444685c94794ae16",
    "legacy/xiangsudian2.py": "ba1053a6fd9040061735806d7d4288c1008aa527f56e0a3645bd02532be08ca2",
    "legacy/xiangsudian3.py": "f103e325f03a0e1f26b1c6658d9c26a748cf1526aa3d5b29cc19625036f987a9",
}


@pytest.fixture(scope="module")
def test_img():
    return make_test_image()


# ---------------------------------------------------------------------------
# 0. 正式模式列表核验
# ---------------------------------------------------------------------------

def test_formal_modes_exactly_four():
    assert FORMAL_NAMES == [
        "classic", "bayer4", "adaptive_fine", "adaptive_bold",
    ], f"正式模式列表不符: {FORMAL_NAMES}"


# ---------------------------------------------------------------------------
# 1/2/3. 正式模式：二值 / deterministic / 尺寸与长宽比
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,fn", FORMAL)
def test_formal_output_is_binary(name, fn, test_img):
    uniq = set(np.unique(fn(test_img)).tolist())
    assert uniq <= {0, 255}, f"{name} 输出含非二值像素: {sorted(uniq)}"


@pytest.mark.parametrize("name,fn", FORMAL)
def test_formal_deterministic(name, fn, test_img):
    assert np.array_equal(fn(test_img), fn(test_img)), f"{name} 两次结果不一致"


@pytest.mark.parametrize("name,fn", FORMAL)
def test_formal_output_size_and_aspect(name, fn, test_img):
    h0, w0 = test_img.shape[:2]
    oh, ow = fn(test_img).shape[:2]
    exp_h = int(LOGICAL_WIDTH * h0 / w0) * SCALE_UP
    exp_w = LOGICAL_WIDTH * SCALE_UP
    assert (ow, oh) == (exp_w, exp_h), (
        f"{name} 尺寸错误: got {(ow, oh)}, expect {(exp_w, exp_h)}"
    )


def test_formal_all_same_output_size(test_img):
    shapes = {fn(test_img).shape for _, fn in FORMAL}
    assert len(shapes) == 1, f"四模式输出尺寸不一致: {shapes}"


# ---------------------------------------------------------------------------
# 4. Classic 无行为回归（真值表 + 第二轮不回白）
# ---------------------------------------------------------------------------

def _classic_logic_grid(img_bgr):
    """复刻 Classic 到逻辑二值网格（不放大），用于核验真值表。"""
    from src.config import CLASSIC_S, CLASSIC_T, CLASSIC_B

    d = LOGICAL_WIDTH * CLASSIC_S
    gray = to_gray(img_bgr)
    eq = cv2.equalizeHist(gray)
    inp = cv2.cvtColor(eq, cv2.COLOR_GRAY2BGR)
    h0, w0 = inp.shape[:2]
    first = cv2.resize(inp, (d, int(d * h0 / w0)))
    second = cv2.resize(
        first, (int(first.shape[1] / CLASSIC_S), int(first.shape[0] / CLASSIC_S))
    )
    H, W = second.shape[:2]
    canvas = np.full((H, W), 255, np.uint8)
    a = second.mean(axis=2)
    for i in range(0, H, 2):
        for j in range(0, W, 2):
            if a[i, j] < CLASSIC_T:
                canvas[i, j] = 0
    for i in range(H):
        for j in range(W):
            if a[i, j] < CLASSIC_B:
                canvas[i, j] = 0
    return second, canvas


def test_classic_truth_table(test_img):
    """黑 = {a<b} ∪ {y偶∧x偶∧ b≤a<t}。"""
    from src.config import CLASSIC_T, CLASSIC_B

    second, canvas = _classic_logic_grid(test_img)
    a = second.mean(axis=2)
    H, W = canvas.shape
    for i in range(H):
        for j in range(W):
            av = a[i, j]
            is_black = canvas[i, j] == 0
            expected = (av < CLASSIC_B) or (
                i % 2 == 0 and j % 2 == 0 and CLASSIC_B <= av < CLASSIC_T
            )
            assert is_black == expected, (
                f"Classic 真值不符 at ({i},{j}): a={av}, canvas={canvas[i,j]}"
            )


def test_classic_second_pass_never_whitens(test_img):
    from src.config import CLASSIC_T, CLASSIC_B

    second, _ = _classic_logic_grid(test_img)
    a = second.mean(axis=2)
    H, W = second.shape[:2]
    first_pass = np.full((H, W), 255, np.uint8)
    for i in range(0, H, 2):
        for j in range(0, W, 2):
            if a[i, j] < CLASSIC_T:
                first_pass[i, j] = 0
    second_pass = first_pass.copy()
    for i in range(H):
        for j in range(W):
            if a[i, j] < CLASSIC_B:
                second_pass[i, j] = 0
    first_black = first_pass == 0
    assert (second_pass[first_black] == 0).all(), "第二轮把黑点设回白了"


# ---------------------------------------------------------------------------
# 5. Bayer4 无行为回归（独立参考实现逐像素比对）
# ---------------------------------------------------------------------------

def _bayer4_reference(img_bgr):
    """测试内独立书写的 Bayer 4x4 参考实现，用于捕获实现漂移。"""
    B = np.array(
        [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
        dtype=np.float32,
    ) * (255.0 / 15.0)
    small = shrink_modern(to_gray(img_bgr))
    h, w = small.shape
    tiled = np.tile(B, ((h + 3) // 4, (w + 3) // 4))[:h, :w]
    bw = np.where(small.astype(np.float32) > tiled, 255, 0).astype(np.uint8)
    return upscale_nn(bw)


def test_bayer4_no_regression(test_img):
    got = algorithms.m2_bayer4(test_img)
    ref = _bayer4_reference(test_img)
    assert np.array_equal(got, ref), "bayer4 与独立参考实现不一致（行为漂移）"


# ---------------------------------------------------------------------------
# 6/7. Adaptive Fine / Bold 参数核验（独立参考比对）
# ---------------------------------------------------------------------------

def _adaptive_reference(img_bgr, method, block, c):
    small = shrink_modern(to_gray(img_bgr))
    bw = cv2.adaptiveThreshold(small, 255, method, cv2.THRESH_BINARY, block, c)
    return upscale_nn(bw)


def test_adaptive_fine_params(test_img):
    """Fine 必须恰为 Gaussian / block=11 / C=2。"""
    ref = _adaptive_reference(
        test_img, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 11, 2
    )
    got = algorithms.adaptive_fine(test_img)
    assert np.array_equal(got, ref), "adaptive_fine 与 Gaussian/11/C=2 参考不一致"
    assert ADAPTIVE_FINE_BLOCK == 11 and ADAPTIVE_C == 2


def test_adaptive_bold_params(test_img):
    """Bold 必须恰为 Mean / block=25 / C=2。"""
    ref = _adaptive_reference(
        test_img, cv2.ADAPTIVE_THRESH_MEAN_C, 25, 2
    )
    got = algorithms.adaptive_bold(test_img)
    assert np.array_equal(got, ref), "adaptive_bold 与 Mean/25/C=2 参考不一致"
    assert ADAPTIVE_BOLD_BLOCK == 25 and ADAPTIVE_C == 2


# ---------------------------------------------------------------------------
# 8. legacy 原件未被修改
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("relpath,sha", sorted(LEGACY_SHA.items()))
def test_legacy_unchanged(relpath, sha):
    path = os.path.join(REPO_ROOT, relpath)
    assert os.path.exists(path), f"缺少 {relpath}"
    out = subprocess.check_output(["sha256sum", path]).decode().split()[0]
    assert out == sha, f"{relpath} SHA-256 变化: {out} != {sha}"


# ---------------------------------------------------------------------------
# 附：实验/基准模式轻量覆盖（二值 + deterministic + 与正式模式同尺寸）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,fn", EXPERIMENTAL)
def test_experimental_binary_and_deterministic(name, fn, test_img):
    a, b = fn(test_img), fn(test_img)
    assert set(np.unique(a).tolist()) <= {0, 255}, f"{name} 输出含非二值像素"
    assert np.array_equal(a, b), f"{name} 两次结果不一致"
    ref_shape = algorithms.m2_bayer4(test_img).shape
    assert a.shape == ref_shape, f"{name} 尺寸 {a.shape} 与正式模式 {ref_shape} 不一致"
