"""Color Fill 正式接入 GUI v1 的集成测试。

对应施工要求第十三节 1–18：

  1. Color Fill 默认 OFF；
  2. OFF 时四模式结果逐像素保持既有行为（严格二值）；
  3. renderer 全白 mask（详见 test_render_color_fill.py，这里做接线层复核）；
  4. renderer 全黑 mask；
  5. 混合 mask；
  6. 3-channel binary mask 正确收敛成 H×W mask；
  7. 非法非二值 mask 的明确行为；
  8. INTER_LINEAR 彩色层；
  9. invert → mask → Color Fill 顺序；
 10. Classic equalize 只影响 mask；
 11. color_fill 改变 -> stale；
 12. 改回 -> current；
 13. mode 切换不改变全局 color_fill；
 14. Restore Defaults 不关闭 Color Fill；
 15. Save 彩色 PNG；
 16. Unicode open/save 无回归；
 17. blockSize 编辑修复无回归；
 18. legacy SHA 不变。

运行：python3.11 -m pytest tests/test_gui_color_fill.py -v
"""

import numpy as np
import pytest

from tests.helpers import LEGACY_SHA, legacy_path, sha256_of

from gui.state import AppState, GenerationKey, commit_block_size_text
from gui.worker import run_mode
from gui import save as save_mod
from src import imageio
from src.render import apply_color_fill, _as_mask_bool


FORMAL_NAMES = ["classic", "bayer4", "adaptive_fine", "adaptive_bold"]


def _img(seed=0, h=96, w=128):
    return (np.random.RandomState(seed).rand(h, w, 3) * 255).astype("uint8")


def _state_with_source(path="x.png", shape=(96, 128), digest="dg"):
    st = AppState()
    st.set_source(path, shape, content_digest=digest)
    return st


def _params(st, mode=None):
    mode = mode or st.current_mode
    p = st.get_params(mode)
    p["color_fill"] = st.get_color_fill()
    return p


# ---------------------------------------------------------------------------
# 1. 默认 OFF
# ---------------------------------------------------------------------------

def test_1_color_fill_default_off():
    st = AppState()
    assert st.get_color_fill() is False
    assert st.color_fill is False


# ---------------------------------------------------------------------------
# 2. OFF 时四模式结果保持既有严格二值行为
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", FORMAL_NAMES)
def test_2_off_keeps_binary_behavior(mode):
    st = _state_with_source()
    st.set_mode(mode)
    src = _img(seed=3)
    out = run_mode(mode, _params(st), src)
    assert out.shape[2] == 3
    assert set(np.unique(out).tolist()) <= {0, 255}
    # OFF 输出必须等于直接调用算法（未叠加 Color Fill）
    from src import algorithms
    fn = dict(algorithms.FORMAL_MODES)[mode]
    p = _params(st)
    direct = fn(src, output_width=p["output_width"],
                pixel_block_size=p["pixel_block_size"],
                invert=p["invert"],
                **{k: p[k] for k in
                   (("t", "b", "equalize") if mode == "classic" else
                    ("matrix_size", "tone_bias") if mode == "bayer4" else
                    ("block_size", "c"))})
    assert np.array_equal(out, direct)


# ---------------------------------------------------------------------------
# 3/4/5. renderer 三态 mask（接线层复核）
# ---------------------------------------------------------------------------

def test_3_4_5_renderer_masks_at_wiring_level():
    st = _state_with_source()
    st.set_color_fill(True)
    src = _img(seed=7)

    # 全白 mask -> 全白
    white = np.full((64, 80, 3), 255, np.uint8)
    assert np.all(apply_color_fill(src, white) == 255)

    # 全黑 mask -> 等于 resized source
    black = np.zeros((64, 80, 3), np.uint8)
    import cv2
    ref = cv2.resize(src, (80, 64), interpolation=cv2.INTER_LINEAR)
    assert np.array_equal(apply_color_fill(src, black), ref)

    # 混合 mask
    mixed = np.full((64, 80, 3), 255, np.uint8)
    mixed[:, :40] = 0
    out = apply_color_fill(src, mixed)
    assert np.all(out[:, 40:] == 255)
    assert np.array_equal(out[:, :40], ref[:, :40])


# ---------------------------------------------------------------------------
# 6. 3-channel mask 收敛为 H×W
# ---------------------------------------------------------------------------

def test_6_three_channel_converges_to_hw():
    m = np.zeros((10, 12, 3), np.uint8)
    m[5, 6] = 255
    mask = _as_mask_bool(m)
    assert mask.shape == (10, 12) and mask.dtype == bool
    assert mask[0, 0] and not mask[5, 6]


# ---------------------------------------------------------------------------
# 7. 非法非二值 mask 明确报错
# ---------------------------------------------------------------------------

def test_7_invalid_mask_raises():
    bad3 = np.full((10, 12, 3), 200, np.uint8)
    with pytest.raises(ValueError):
        _as_mask_bool(bad3)
    bad2 = np.full((10, 12), 77, np.uint8)
    with pytest.raises(ValueError):
        _as_mask_bool(bad2)
    # 三通道语义不一致
    inconsistent = np.zeros((4, 4, 3), np.uint8)
    inconsistent[1, 1] = [0, 0, 255]
    with pytest.raises(ValueError):
        _as_mask_bool(inconsistent)


# ---------------------------------------------------------------------------
# 8. INTER_LINEAR 彩色层
# ---------------------------------------------------------------------------

def test_8_inter_linear_color_layer():
    import cv2
    from src.config import COLOR_FILL_RESIZE
    assert COLOR_FILL_RESIZE == cv2.INTER_LINEAR
    src = _img(seed=9)
    mask = np.zeros((70, 90, 3), np.uint8)
    out = apply_color_fill(src, mask)
    assert np.array_equal(
        out, cv2.resize(src, (90, 70), interpolation=cv2.INTER_LINEAR))


# ---------------------------------------------------------------------------
# 9. invert -> mask -> Color Fill 顺序
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", FORMAL_NAMES)
def test_9_invert_before_color_fill(mode):
    st = _state_with_source()
    st.set_mode(mode)
    st.set_color_fill(True)
    src = _img(seed=11)

    p_off = _params(st)
    p_off["invert"] = False
    out_off = run_mode(mode, p_off, src)

    p_on = dict(p_off)
    p_on["invert"] = True
    out_on = run_mode(mode, p_on, src)

    # 实际算法 mask（不含 color_fill）
    from src import algorithms
    fn = dict(algorithms.FORMAL_MODES)[mode]
    kw = dict(output_width=p_off["output_width"],
              pixel_block_size=p_off["pixel_block_size"])
    if mode == "classic":
        kw.update(t=p_off["t"], b=p_off["b"], equalize=p_off["equalize"])
    elif mode == "bayer4":
        kw.update(matrix_size=p_off["matrix_size"], tone_bias=p_off["tone_bias"])
    else:
        kw.update(block_size=p_off["block_size"], c=p_off["c"])

    mask_off = fn(src, invert=False, **kw)
    mask_on = fn(src, invert=True, **kw)
    assert np.array_equal(mask_on, 255 - mask_off)
    # Color Fill 结果 = 对应最终 mask 的合成（renderer 不再自行 invert）
    assert np.array_equal(out_off, apply_color_fill(src, mask_off))
    assert np.array_equal(out_on, apply_color_fill(src, mask_on))
    assert not np.array_equal(out_off, out_on)


# ---------------------------------------------------------------------------
# 10. Classic equalize 只影响 mask
# ---------------------------------------------------------------------------

def test_10_equalize_mask_only():
    st = _state_with_source()
    st.set_color_fill(True)
    src = _img(seed=13)

    st.set_mode("classic")
    st.set_param("equalize", False)
    out_a = run_mode("classic", _params(st, "classic"), src)

    st.set_param("equalize", True)
    out_b = run_mode("classic", _params(st, "classic"), src)

    assert not np.array_equal(out_a, out_b)   # mask 变了
    # 两结果非白像素颜色都来自同一彩色层
    import cv2
    ref = cv2.resize(src, (out_a.shape[1], out_a.shape[0]),
                     interpolation=cv2.INTER_LINEAR)
    for out in (out_a, out_b):
        nonwhite = ~np.all(out == 255, axis=2)
        assert np.array_equal(out[nonwhite], ref[nonwhite])


# ---------------------------------------------------------------------------
# 11/12. color_fill 改变 -> stale；改回 -> current
# ---------------------------------------------------------------------------

def test_11_12_color_fill_toggles_stale_current():
    st = _state_with_source()
    st.set_mode("classic")
    src = _img(seed=15)
    key = st.current_key()
    st.mark_generated(key, run_mode("classic", _params(st), src))
    assert st.is_current()

    st.set_color_fill(True)
    assert st.is_stale()

    st.set_color_fill(False)
    assert st.is_current()   # 其它参数/source/mode 未变 -> 自动恢复 current


# ---------------------------------------------------------------------------
# 13. mode 切换不改变全局 color_fill
# ---------------------------------------------------------------------------

def test_13_mode_switch_keeps_color_fill():
    st = _state_with_source()
    st.set_color_fill(True)
    for mode in FORMAL_NAMES:
        st.set_mode(mode)
        assert st.get_color_fill() is True
    st.set_mode("classic")
    assert st.get_color_fill() is True


# ---------------------------------------------------------------------------
# 14. Restore Defaults 不关闭 Color Fill
# ---------------------------------------------------------------------------

def test_14_restore_defaults_keeps_color_fill():
    st = _state_with_source()
    st.set_mode("adaptive_fine")
    st.set_color_fill(True)
    st.set_param("block_size", 33)
    st.set_param("c", -5)

    st.restore_defaults()
    assert st.get_color_fill() is True          # 全局画笔状态不受影响
    assert st.get_param("block_size") == 11     # Fine 默认
    assert st.get_param("c") == 2


# ---------------------------------------------------------------------------
# 15. Save 彩色 PNG
# ---------------------------------------------------------------------------

def test_15_save_color_png(tmp_path):
    st = _state_with_source(path="C.jpg")
    st.set_mode("bayer4")
    st.set_color_fill(True)
    src = _img(seed=17)
    result = run_mode("bayer4", _params(st), src)

    name = save_mod.default_filename(st.source_path, "bayer4")
    target = tmp_path / name
    path = save_mod.normalize_png_path(str(target))
    save_mod.save_png(path, result)
    assert path.endswith("__bayer4.png")

    back = save_mod.read_png_pixels(path)
    assert back.shape == result.shape
    assert np.array_equal(back[:, :, ::-1], result)   # RGB 读回 == BGR 原值
    white = np.all(result == 255, axis=2)
    assert np.all(back[white] == 255)


# ---------------------------------------------------------------------------
# 16. Unicode open/save 无回归
# ---------------------------------------------------------------------------

def test_16_unicode_open_save_color(tmp_path):
    src = _img(seed=19)
    udir = tmp_path / "像素点项目临时文件"
    udir.mkdir()
    upath = udir / "照片 A.png"
    assert imageio.imwrite_unicode(str(upath), src)
    loaded = imageio.imread_unicode(str(upath))
    assert np.array_equal(loaded, src)

    st = _state_with_source(path=str(upath), shape=src.shape[:2])
    st.set_color_fill(True)
    result = run_mode("classic", _params(st), loaded)

    out_path = save_mod.normalize_png_path(str(udir / "彩色结果"))
    save_mod.save_png(out_path, result)
    back = save_mod.read_png_pixels(out_path)
    assert np.array_equal(back[:, :, ::-1], result)


# ---------------------------------------------------------------------------
# 17. blockSize 编辑修复无回归
# ---------------------------------------------------------------------------

def test_17_block_size_fix_no_regression():
    assert commit_block_size_text("9", 11) == 9
    assert commit_block_size_text("12", 11) == 13
    assert commit_block_size_text("", 13) == 13
    assert commit_block_size_text("abc", 13) == 13
    st = _state_with_source()
    st.set_mode("adaptive_fine")
    st.set_param("block_size", 12)
    assert st.get_param("block_size") == 13


# ---------------------------------------------------------------------------
# 18. legacy SHA 不变
# ---------------------------------------------------------------------------

def test_18_legacy_unchanged():
    for relpath, expected in LEGACY_SHA.items():
        assert sha256_of(legacy_path(relpath)) == expected
