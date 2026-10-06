"""Color Fill 渲染层（src/render.py）单元测试（第一轮视觉实验）。

覆盖施工要求第六节 1–12：

  1. Color Fill OFF（即不调用 renderer）时四模式输出完全不变；
  2. 全白 mask -> 输出严格全白；
  3. 全黑 mask -> 输出逐像素等于 INTER_LINEAR resize 后的 source；
  4. 混合 mask：白区=255，黑区=resized source，边界无额外灰阶 blending；
  5. 输出尺寸 = binary result 尺寸；
  6. dtype = uint8；
  7. deterministic；
  8. source 彩色层不受 Classic equalize 影响（equalize 只改 mask）；
  9. 传入「已 invert 的最终 mask」时 renderer 只服从 mask，不自行再反转；
 10. Unicode source path 不产生回归；
 11. Save PNG 能正确保存彩色 3-channel 输出（复用已验收保存 helper）；
 12. legacy SHA 不变。

运行：python3.11 -m pytest tests/test_render_color_fill.py -v
"""

import cv2
import numpy as np
import pytest

from tests.helpers import LEGACY_SHA, legacy_path, sha256_of

from src import algorithms
from src.render import apply_color_fill
from src.config import COLOR_FILL_RESIZE
from src import imageio
from gui import save as save_mod


FORMAL_NAMES = [n for n, _ in algorithms.FORMAL_MODES]

# Color Fill 默认输出尺寸（四种算法的 result 尺寸都等于各自 geometry 的 actual 尺寸）
OUT_W = 320
OUT_H = 200


@pytest.fixture
def source_color():
    """确定性彩色源图（BGR uint8），尺寸与输出不同以验证 resize 路径。"""
    rng = np.random.default_rng(7)
    return rng.integers(0, 256, (120, 160, 3), dtype=np.uint8)


@pytest.fixture
def reference_color_layer(source_color):
    """参考彩色层：INTER_LINEAR resize 到输出尺寸。"""
    return cv2.resize(source_color, (OUT_W, OUT_H), interpolation=cv2.INTER_LINEAR)


# ---------------------------------------------------------------------------
# 1. Color Fill OFF：四模式现有输出完全不变
# ---------------------------------------------------------------------------

def test_1_formal_modes_unchanged_without_color_fill():
    """不调用 renderer 时，四正式模式输出与「纯二值」基准逐像素一致。

    renderer 是独立下游模块，算法函数签名与本轮之前完全相同；
    此处再显式核验一遍：算法输出仍严格二值、equalize 语义未变。
    """
    rng = np.random.default_rng(1)
    img = rng.integers(0, 256, (64, 80, 3), dtype=np.uint8)

    for name, fn in algorithms.FORMAL_MODES:
        out = fn(img)
        assert out.ndim == 3 and out.shape[2] == 3, f"{name} 输出不是 3 通道"
        assert out.dtype == np.uint8, f"{name} dtype 非 uint8"
        uniq = set(np.unique(out).tolist())
        assert uniq <= {0, 255}, f"{name} 非严格二值: {uniq}"

    # Classic equalize 开关仍只影响算法自身输出（语义未被本轮触碰）
    off = algorithms.classic(img, equalize=False)
    on = algorithms.classic(img, equalize=True)
    assert off.shape == on.shape
    assert not np.array_equal(off, on), "equalize 开关应改变 Classic mask"


# ---------------------------------------------------------------------------
# 2. 全白 mask -> 严格全白
# ---------------------------------------------------------------------------

def test_2_all_white_mask_is_all_white(source_color):
    mask = np.full((OUT_H, OUT_W, 3), 255, np.uint8)
    out = apply_color_fill(source_color, mask)
    assert out.shape == (OUT_H, OUT_W, 3)
    assert np.all(out == 255)


# ---------------------------------------------------------------------------
# 3. 全黑 mask -> 逐像素等于 INTER_LINEAR resize 后的 source
# ---------------------------------------------------------------------------

def test_3_all_black_mask_equals_resized_source(source_color, reference_color_layer):
    mask = np.zeros((OUT_H, OUT_W, 3), np.uint8)
    out = apply_color_fill(source_color, mask)
    assert np.array_equal(out, reference_color_layer)


def test_3b_color_layer_uses_inter_linear(source_color):
    """彩色层必须固定 INTER_LINEAR（不是 NEAREST/AREA）。"""
    mask = np.zeros((OUT_H, OUT_W, 3), np.uint8)
    out = apply_color_fill(source_color, mask)
    linear = cv2.resize(source_color, (OUT_W, OUT_H), interpolation=cv2.INTER_LINEAR)
    nearest = cv2.resize(source_color, (OUT_W, OUT_H), interpolation=cv2.INTER_NEAREST)
    assert COLOR_FILL_RESIZE == cv2.INTER_LINEAR
    assert np.array_equal(out, linear)
    assert not np.array_equal(out, nearest)


# ---------------------------------------------------------------------------
# 4. 混合 mask：白=255 / 黑=resized source / 边界无 blending
# ---------------------------------------------------------------------------

def test_4_mixed_mask_composite(source_color, reference_color_layer):
    mask = np.full((OUT_H, OUT_W, 3), 255, np.uint8)
    # 左半黑右半白（硬边界）
    mask[:, : OUT_W // 2] = 0
    out = apply_color_fill(source_color, mask)

    # 白区严格 255
    assert np.all(out[:, OUT_W // 2 :] == 255)
    # 黑区逐像素等于彩色层
    assert np.array_equal(out[:, : OUT_W // 2], reference_color_layer[:, : OUT_W // 2])


def test_4b_mask_boundary_is_sharp_no_blending(source_color, reference_color_layer):
    """mask 边界没有额外灰阶 blending：过渡列只能整体取红或整体取白。"""
    mask = np.full((OUT_H, OUT_W, 3), 255, np.uint8)
    mask[:, : OUT_W // 2] = 0
    out = apply_color_fill(source_color, mask)

    # 边界列：全白侧一列必然全 255；边界黑侧一列必然等于彩色层（非二者的中间值）
    assert np.all(out[:, OUT_W // 2] == 255)
    boundary_black = OUT_W // 2 - 1
    assert np.array_equal(out[:, boundary_black], reference_color_layer[:, boundary_black])

    # 不存在「既非 255 又非彩色层原值」的插值像素
    for x in range(OUT_W):
        col = out[:, x]
        if np.all(col == 255):
            continue
        assert np.array_equal(col, reference_color_layer[:, x])


# ---------------------------------------------------------------------------
# 5 & 6. 输出尺寸 = binary result 尺寸；dtype = uint8
# ---------------------------------------------------------------------------

def test_5_output_size_equals_binary_result(source_color):
    for size in [(60, 90), (OUT_H, OUT_W), (257, 131)]:
        h, w = size
        mask = np.zeros((h, w, 3), np.uint8)
        out = apply_color_fill(source_color, mask)
        assert out.shape[:2] == (h, w)
        assert out.shape == (h, w, 3)


def test_5b_accepts_grayscale_mask_shape(source_color, reference_color_layer):
    """兼容单通道 0/255 mask（隐藏兼容），输出仍为 3 通道。"""
    mask = np.zeros((OUT_H, OUT_W), np.uint8)
    out = apply_color_fill(source_color, mask)
    assert out.ndim == 3 and out.shape == (OUT_H, OUT_W, 3)
    assert np.array_equal(out, reference_color_layer)


def test_6_dtype_is_uint8(source_color):
    mask = np.zeros((OUT_H, OUT_W, 3), np.uint8)
    out = apply_color_fill(source_color, mask)
    assert out.dtype == np.uint8


# ---------------------------------------------------------------------------
# 6b/6c. mask 数据契约：3 通道收敛为 H×W；非法 mask 明确报错
# ---------------------------------------------------------------------------

def test_6b_three_channel_mask_converges_to_hw(source_color, reference_color_layer):
    """3 通道 mask 必须收敛为 H×W boolean mask，且需三通道全 0 才算黑。"""
    from src.render import _as_mask_bool

    # 三通道全 0 -> 黑；全 255 -> 白
    m = np.zeros((4, 5, 3), np.uint8)
    m[1, 2] = 255
    mask = _as_mask_bool(m)
    assert mask.shape == (4, 5) and mask.dtype == bool
    assert mask[0, 0] and not mask[1, 2]

    # 一像素仅部分通道为 0 -> 不属于合法二值语义 -> 明确报错
    bad = np.zeros((4, 5, 3), np.uint8)
    bad[1, 2] = [0, 0, 255]
    with pytest.raises(ValueError):
        _as_mask_bool(bad)

    # 端到端：合法 3 通道 mask 与等价 2D mask 结果一致
    m2d = np.zeros((OUT_H, OUT_W), np.uint8)
    m2d[:, : OUT_W // 2] = 255
    m3d = np.repeat(m2d[:, :, None], 3, axis=2)
    assert np.array_equal(
        apply_color_fill(source_color, m2d), apply_color_fill(source_color, m3d)
    )


def test_6c_invalid_nonbinary_mask_rejected(source_color):
    """非严格二值 mask（含中间灰阶）必须抛出明确错误。"""
    from src.render import _as_mask_bool

    gray_mask = np.full((OUT_H, OUT_W, 3), 128, np.uint8)
    with pytest.raises(ValueError):
        _as_mask_bool(gray_mask)
    with pytest.raises(ValueError):
        apply_color_fill(source_color, gray_mask)

    gray2d = np.full((OUT_H, OUT_W), 100, np.uint8)
    with pytest.raises(ValueError):
        _as_mask_bool(gray2d)


# ---------------------------------------------------------------------------
# 7. deterministic
# ---------------------------------------------------------------------------

def test_7_deterministic(source_color):
    rng = np.random.default_rng(3)
    # 合法二值 mask：每像素三通道一致（先出单通道再广播）
    m2d = (rng.integers(0, 2, (OUT_H, OUT_W)) * 255).astype(np.uint8)
    mask = np.repeat(m2d[:, :, None], 3, axis=2)
    a = apply_color_fill(source_color, mask)
    b = apply_color_fill(source_color, mask)
    assert np.array_equal(a, b)


# ---------------------------------------------------------------------------
# 8. source 彩色层不受 Classic equalize 影响
# ---------------------------------------------------------------------------

def test_8_equalize_does_not_touch_color_layer():
    """equalize 只改变 mask，不改变「被显示出来的颜色本身」。"""
    rng = np.random.default_rng(11)
    img = rng.integers(0, 256, (120, 160, 3), dtype=np.uint8)

    mask_off = algorithms.classic(img, output_width=OUT_W, pixel_block_size=2, equalize=False)
    mask_on = algorithms.classic(img, output_width=OUT_W, pixel_block_size=2, equalize=True)

    out_off = apply_color_fill(img, mask_off)
    out_on = apply_color_fill(img, mask_on)

    # mask 不同 -> 结果不同
    assert not np.array_equal(mask_off, mask_on)
    assert not np.array_equal(out_off, out_on)

    # 但彩色层本身相同：两结果「非白像素」的颜色集合一致
    def colors(u):
        m = ~np.all(u == 255, axis=2)
        return set(map(tuple, u[m].tolist()))

    # 取两 mask 都在黑的地方，颜色应逐像素一致（源于同一彩色层）
    both_black = np.all(mask_off == 0, axis=2) & np.all(mask_on == 0, axis=2)
    assert np.array_equal(out_off[both_black], out_on[both_black])
    # 两个结果的颜色都来自同一份原图彩色层
    ref = cv2.resize(img, (OUT_W, mask_on.shape[0]), interpolation=cv2.INTER_LINEAR)
    assert colors(out_off) <= colors(ref) | {tuple(c) for c in ref.reshape(-1, 3).tolist()}


# ---------------------------------------------------------------------------
# 9. renderer 只服从最终 mask，不自行再次 invert
# ---------------------------------------------------------------------------

def test_9_renderer_does_not_reinvert(source_color, reference_color_layer):
    """同一 mask 无论来自哪个极性，renderer 行为完全一致。"""
    base = np.zeros((OUT_H, OUT_W, 3), np.uint8)
    base[:, : OUT_W // 2] = 255

    out = apply_color_fill(source_color, base)
    assert np.all(out[:, : OUT_W // 2] == 255)                 # mask 白 -> 白
    assert np.array_equal(out[:, OUT_W // 2 :], reference_color_layer[:, OUT_W // 2 :])

    # 传入"已 invert 的 mask"时，renderer 不自行反转回来
    inverted = 255 - base
    out_inv = apply_color_fill(source_color, inverted)
    assert not np.array_equal(out, out_inv)
    assert np.all(out_inv[:, OUT_W // 2 :] == 255)             # 反转后白区变了
    assert np.array_equal(out_inv[:, : OUT_W // 2], reference_color_layer[:, : OUT_W // 2])


def test_9b_invert_wiring_order_per_mode():
    """算法内 invert 发生在 mask 阶段 -> renderer 只吃最终 mask。"""
    rng = np.random.default_rng(21)
    img = rng.integers(0, 256, (120, 160, 3), dtype=np.uint8)

    for name, fn in algorithms.FORMAL_MODES:
        mask_normal = fn(img, output_width=OUT_W, pixel_block_size=4, invert=False)
        mask_inv = fn(img, output_width=OUT_W, pixel_block_size=4, invert=True)
        # 算法侧 invert 就是 255 - mask
        assert np.array_equal(mask_inv, 255 - mask_normal), f"{name} invert 语义异常"

        out_normal = apply_color_fill(img, mask_normal)
        out_inv = apply_color_fill(img, mask_inv)
        # 两极性结果互补：一个位置要么白要么取色
        white_n = np.all(out_normal == 255, axis=2)
        white_i = np.all(out_inv == 255, axis=2)
        assert np.array_equal(white_n, ~white_i), f"{name} 互补性异常"


# ---------------------------------------------------------------------------
# 10. Unicode source path 不产生回归
# ---------------------------------------------------------------------------

def test_10_unicode_path_no_regression(tmp_path):
    rng = np.random.default_rng(31)
    img = rng.integers(0, 256, (120, 160, 3), dtype=np.uint8)

    udir = tmp_path / "像素点项目临时文件"
    udir.mkdir()
    upath = udir / "照片 A.png"
    assert imageio.imwrite_unicode(str(upath), img)

    loaded = imageio.imread_unicode(str(upath))
    assert np.array_equal(loaded, img)

    mask = algorithms.classic(loaded, output_width=OUT_W, pixel_block_size=2)
    out = apply_color_fill(loaded, mask)
    out_ascii = apply_color_fill(img, mask)
    assert np.array_equal(out, out_ascii), "Unicode 路径读取导致 Color Fill 结果回归"


# ---------------------------------------------------------------------------
# 11. Save PNG 能正确保存彩色 3-channel 输出（复用已验收保存链路）
# ---------------------------------------------------------------------------

def test_11_save_png_color_output(tmp_path):
    rng = np.random.default_rng(41)
    img = rng.integers(0, 256, (120, 160, 3), dtype=np.uint8)
    mask = algorithms.bayer4(img, output_width=OUT_W, pixel_block_size=4)
    out = apply_color_fill(img, mask)
    assert out.dtype == np.uint8 and out.shape[2] == 3

    target = tmp_path / "彩色结果.png"
    path = save_mod.normalize_png_path(str(target))
    save_mod.save_png(path, out)
    assert path.endswith(".png")

    read_back = save_mod.read_png_pixels(path)
    # Pillow 读回是 RGB；BGR 写时做过通道翻转，比较时再翻回来
    assert read_back.shape == out.shape
    assert np.array_equal(read_back[:, :, ::-1], out)

    # 白区在白 PNG 中仍是纯白
    white = np.all(out == 255, axis=2)
    assert np.all(read_back[white] == 255)


def test_11b_save_png_helper_unchanged_source():
    """已验收保存链路未被本轮修改（MODE_SHORT_NAMES 与默认文件名契约不变）。"""
    assert save_mod.MODE_SHORT_NAMES["bayer4"] == "bayer4"
    assert save_mod.default_filename("C.jpeg", "bayer4") == "C__bayer4.png"


# ---------------------------------------------------------------------------
# 12. legacy SHA 不变
# ---------------------------------------------------------------------------

def test_12_legacy_unchanged():
    for relpath, expected in LEGACY_SHA.items():
        assert sha256_of(legacy_path(relpath)) == expected, f"{relpath} 被改动"
