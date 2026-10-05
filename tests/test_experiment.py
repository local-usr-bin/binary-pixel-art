"""确定性 / 二值性 / 尺寸 / Classic 文档一致性 / legacy 未改 的自动化测试。

运行：
    python3.11 -m pytest tests/ -v
（在仓库根目录执行；tests/ 通过 conftest.py 把根目录加入 sys.path）
"""

import os
import subprocess

import numpy as np
import pytest

from src import algorithms
from src.config import LOGICAL_WIDTH, SCALE_UP
from tools.make_test_image import make_test_image

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ALGOS = [
    ("classic", algorithms.classic),
    ("m1_otsu", algorithms.m1_otsu),
    ("m2_bayer4", algorithms.m2_bayer4),
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
# 1. 输出严格二值（只有 0/255）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,fn", ALGOS)
def test_output_is_binary(name, fn, test_img):
    out = fn(test_img)
    uniq = set(np.unique(out).tolist())
    assert uniq <= {0, 255}, f"{name} 输出含非二值像素: {sorted(uniq)}"


# ---------------------------------------------------------------------------
# 2/3. 输出尺寸正确且保持长宽比，六算法一致
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,fn", ALGOS)
def test_output_size_and_aspect(name, fn, test_img):
    h0, w0 = test_img.shape[:2]
    out = fn(test_img)
    oh, ow = out.shape[:2]
    # 逻辑宽 = LOGICAL_WIDTH，逻辑高 = int(LOGICAL_WIDTH*h0/w0)
    exp_h = int(LOGICAL_WIDTH * h0 / w0) * SCALE_UP
    exp_w = LOGICAL_WIDTH * SCALE_UP
    assert (ow, oh) == (exp_w, exp_h), (
        f"{name} 尺寸错误: got {(ow, oh)}, expect {(exp_w, exp_h)}"
    )


def test_all_algos_same_output_size(test_img):
    shapes = {fn(test_img).shape for _, fn in ALGOS}
    assert len(shapes) == 1, f"六算法输出尺寸不一致: {shapes}"


# ---------------------------------------------------------------------------
# 4. 同输入同参数结果 deterministic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,fn", ALGOS)
def test_deterministic(name, fn, test_img):
    a = fn(test_img)
    b = fn(test_img)
    assert np.array_equal(a, b), f"{name} 同输入两次结果不一致"


# ---------------------------------------------------------------------------
# 5. Classic 行为与文档一致（真值表核验，不依赖视觉）
# ---------------------------------------------------------------------------

def _classic_logic_grid(img_bgr):
    """复刻 Classic 到逻辑二值网格（不放大），用于核验真值表。"""
    import cv2
    from src.pipeline import to_gray
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
    # 第一轮：偶数行、偶数列
    for i in range(0, H, 2):
        for j in range(0, W, 2):
            if a[i, j] < CLASSIC_T:
                canvas[i, j] = 0
    # 第二轮：全位置，无 else
    for i in range(H):
        for j in range(W):
            if a[i, j] < CLASSIC_B:
                canvas[i, j] = 0
    return second, canvas


def test_classic_truth_table(test_img):
    """核验 Classic 精确真值：黑 = {a<b} ∪ {y偶∧x偶∧ b≤a<t}。"""
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
    """第二轮不得把第一轮已变黑的像素设回白。"""
    from src.config import CLASSIC_T, CLASSIC_B

    second, _ = _classic_logic_grid(test_img)
    a = second.mean(axis=2)
    H, W = second.shape[:2]
    first_pass = np.full((H, W), 255, np.uint8)
    for i in range(0, H, 2):
        for j in range(0, W, 2):
            if a[i, j] < CLASSIC_T:
                first_pass[i, j] = 0
    # 模拟第二轮
    second_pass = first_pass.copy()
    for i in range(H):
        for j in range(W):
            if a[i, j] < CLASSIC_B:
                second_pass[i, j] = 0
    # 第一轮的黑点在第二轮后必须仍为黑
    first_black = first_pass == 0
    assert (second_pass[first_black] == 0).all(), "第二轮把黑点设回白了"


# ---------------------------------------------------------------------------
# 6. legacy 原件未被修改
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("relpath,sha", sorted(LEGACY_SHA.items()))
def test_legacy_unchanged(relpath, sha):
    path = os.path.join(REPO_ROOT, relpath)
    assert os.path.exists(path), f"缺少 {relpath}"
    out = subprocess.check_output(["sha256sum", path]).decode().split()[0]
    assert out == sha, f"{relpath} SHA-256 变化: {out} != {sha}"
