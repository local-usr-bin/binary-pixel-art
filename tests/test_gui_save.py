"""GUI-001B2：current-only PNG 保存的自动测试。

覆盖任务第九节 1~16 项：
  1. 无 result -> Save disabled；
  2. current result -> Save enabled；
  3. stale result -> Save disabled；
  4. stale 参数改回 generated_key -> Save enabled；
  5. busy -> Save disabled；
  6. Save 不重新运行算法；
  7. 保存的是 full-resolution result，不是 preview；
  8. PNG 写入后重新读取，与 generated_result 逐像素一致；
  9. 严格黑白结果保存后仍只有 0/255；
 10. Save As cancel -> 不创建文件、不报错；
 11. 保存失败 -> 状态/错误处理正确，GUI 不崩溃；
 12. Unicode/中文路径保存成功；
 13. 默认建议文件名包含 source stem + mode；
 14. 四正式模式生成的 current result 均可保存；
 15. 后端既有完整测试无回归（tests/ 全套）；
 16. legacy SHA-256 不变。

不依赖 Tk 主循环：save 层为纯函数；enable 规则复用 AppState；
App 级行为（on_save / cancel / failure）用最小 Tk 在 xvfb 下验证的部分
放入 smoke 脚本；本文件用 state + save 层做确定性验证。
运行：python3.11 -m pytest tests/test_gui_save.py -v
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from tests.helpers import LEGACY_SHA, legacy_path, sha256_of

from gui.save import (
    default_filename, save_png, read_png_pixels, normalize_png_path,
    MODE_SHORT_NAMES,
)
from gui.state import AppState
from gui.worker import run_mode


ALL_MODES = ["classic", "bayer4", "adaptive_fine", "adaptive_bold"]


def _img(seed=0, h=96, w=128):
    return (np.random.RandomState(seed).rand(h, w, 3) * 255).astype("uint8")


def _state_with_source(path="x.png", shape=(96, 128), digest="dg"):
    st = AppState()
    st.set_source(path, shape, content_digest=digest)
    return st


def _run(st, source=None):
    mode = st.current_mode
    key = st.current_key()
    result = run_mode(mode, st.get_params(mode),
                      source if source is not None else _img())
    st.mark_generated(key, result)
    return key, result


# ---------------------------------------------------------------------------
# 1~5. Save enable 规则（current-only）
# ---------------------------------------------------------------------------

def test_1_no_result_save_disabled():
    st = _state_with_source()
    assert st.save_enabled() is False           # 尚未生成


def test_2_current_result_save_enabled():
    st = _state_with_source()
    _run(st)
    assert st.is_current() is True
    assert st.save_enabled() is True


def test_3_stale_result_save_disabled():
    st = _state_with_source()
    _run(st)
    st.set_param("t", 140)                        # 参数修改 -> stale
    assert st.is_stale() is True
    assert st.save_enabled() is False


def test_3b_mode_switch_stale_save_disabled():
    st = _state_with_source()
    _run(st)
    st.set_mode("bayer4")                         # 切模式 -> stale
    assert st.save_enabled() is False


def test_3c_new_source_stale_save_disabled():
    st = _state_with_source()
    _run(st)
    st.set_source("y.png", (96, 128), content_digest="other")
    assert st.save_enabled() is False


def test_4_stale_revert_makes_save_enabled():
    st = _state_with_source()
    key, _ = _run(st)
    st.set_param("t", 140)
    assert st.save_enabled() is False
    st.set_param("t", 127)                        # 改回 generated_key
    assert st.current_key() == key
    assert st.save_enabled() is True


def test_5_busy_save_disabled():
    st = _state_with_source()
    _run(st)
    assert st.save_enabled() is True
    st.busy = True                               # worker 正在运行
    assert st.save_enabled() is False
    st.busy = False
    assert st.save_enabled() is True


def test_5b_failed_generation_no_current_save_disabled():
    st = _state_with_source()
    # 生成失败语义：没有 mark_generated -> 无 result -> disabled
    assert st.has_result() is False
    assert st.save_enabled() is False


# ---------------------------------------------------------------------------
# 6. Save 不重新运行算法
# ---------------------------------------------------------------------------

def test_6_save_does_not_rerun_algorithm(monkeypatch, tmp_path):
    """save_png 只写文件，不触碰任何后端算法。"""
    from src import algorithms
    calls = {"n": 0}
    for name in ALL_MODES:
        orig = getattr(algorithms, name)
        def make_spy(orig):
            def _spy(*a, **k):
                calls["n"] += 1
                return orig(*a, **k)
            return _spy
        monkeypatch.setattr(algorithms, name, make_spy(orig))

    st = _state_with_source()
    _, result = _run(st)
    n_after_gen = calls["n"]
    out = tmp_path / "r.png"
    save_png(out, result)
    assert calls["n"] == n_after_gen     # 保存未再次调用算法


# ---------------------------------------------------------------------------
# 7. 保存的是 full-resolution result，不是 preview
# ---------------------------------------------------------------------------

def test_7_saves_full_resolution_not_preview(tmp_path):
    st = _state_with_source(path="p.png", shape=(150, 200))
    _, result = _run(st)                          # shape = actual output
    out = tmp_path / "full.png"
    save_png(out, result)
    back = read_png_pixels(out)
    assert back.shape[0] == result.shape[0]
    assert back.shape[1] == result.shape[1]
    # 与 full-resolution result 逐像素一致（非任何 fit 缩放副本）
    assert np.array_equal(back, result[:, :, ::-1])


# ---------------------------------------------------------------------------
# 8. 逐像素一致
# ---------------------------------------------------------------------------

def test_8_pixel_exact_roundtrip(tmp_path):
    st = _state_with_source()
    _, result = _run(st)
    out = tmp_path / "rt.png"
    save_png(out, result)
    back = read_png_pixels(out)
    assert back.shape == result.shape
    assert np.array_equal(back, result[:, :, ::-1])   # BGR -> RGB


# ---------------------------------------------------------------------------
# 9. 保存后仍严格 0/255
# ---------------------------------------------------------------------------

def test_9_strict_binary_after_save(tmp_path):
    st = _state_with_source()
    _, result = _run(st)
    assert set(np.unique(result).tolist()) <= {0, 255}
    out = tmp_path / "bw.png"
    save_png(out, result)
    back = read_png_pixels(out)
    assert set(np.unique(back).tolist()) <= {0, 255}


def test_9b_grayscale_2d_binary(tmp_path):
    gray = (np.random.RandomState(1).rand(40, 50) > 0.5).astype("uint8") * 255
    out = tmp_path / "g.png"
    save_png(out, gray)
    back = read_png_pixels(out)
    assert back.shape == gray.shape
    assert np.array_equal(back, gray)
    assert set(np.unique(back).tolist()) <= {0, 255}


# ---------------------------------------------------------------------------
# 11. 保存失败可被捕获
# ---------------------------------------------------------------------------

def test_11_save_failure_raises(tmp_path):
    result = _img()
    bad_dir = tmp_path / "no_such_dir" / "x.png"   # 目录不存在
    with pytest.raises(Exception):
        save_png(bad_dir, result)


# ---------------------------------------------------------------------------
# 12. Unicode / 中文路径
# ---------------------------------------------------------------------------

def test_12_unicode_path(tmp_path):
    st = _state_with_source()
    _, result = _run(st)
    out = tmp_path / "中文目录" / "结果__classic.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    save_png(out, result)
    assert out.exists()
    back = read_png_pixels(out)
    assert np.array_equal(back, result[:, :, ::-1])


def test_12b_unicode_default_filename():
    name = default_filename("/tmp/照 片.png", "bayer4")
    assert name == "照 片__bayer4.png"


# ---------------------------------------------------------------------------
# 13. 默认文件名：source stem + mode
# ---------------------------------------------------------------------------

def test_13_default_filename_rules():
    assert default_filename("C.png", "bayer4") == "C__bayer4.png"
    assert default_filename("/a/b/portrait.jpg", "adaptive_fine") == \
        "portrait__adaptive_fine.png"
    assert default_filename(None, "classic") == "result__classic.png"
    assert default_filename("", "adaptive_bold") == "result__adaptive_bold.png"
    for m, short in MODE_SHORT_NAMES.items():
        assert default_filename("x.png", m) == f"x__{short}.png"


def test_13b_default_filename_unknown_mode():
    with pytest.raises(ValueError):
        default_filename("x.png", "nope")


# ---------------------------------------------------------------------------
# 14. 四正式模式 current result 均可保存
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ALL_MODES)
def test_14_all_modes_savable(mode, tmp_path):
    st = _state_with_source(path=f"{mode}.png", shape=(150, 200))
    st.set_mode(mode)
    _, result = _run(st)
    assert st.save_enabled() is True
    out = tmp_path / f"{mode}.png"
    save_png(out, result)
    back = read_png_pixels(out)
    assert np.array_equal(back, result[:, :, ::-1])
    assert set(np.unique(back).tolist()) <= {0, 255}


# ---------------------------------------------------------------------------
# 辅助层：save_png 直接覆盖形状/通道处理
# ---------------------------------------------------------------------------

def test_save_handles_1channel_and_bgra(tmp_path):
    one = np.zeros((10, 12, 1), "uint8")
    one[::2] = 255
    out1 = tmp_path / "one.png"
    save_png(out1, one)
    assert read_png_pixels(out1).shape == (10, 12)

    bgra = np.zeros((8, 9, 4), "uint8")
    bgra[..., 3] = 255
    out2 = tmp_path / "bgra.png"
    save_png(out2, bgra)
    b = read_png_pixels(out2)
    assert b.shape == (8, 9, 3)


def test_read_png_helper(tmp_path):
    img = np.zeros((5, 6, 3), "uint8")
    p = tmp_path / "h.png"
    Image.fromarray(img).save(str(p))
    assert read_png_pixels(p).shape == (5, 6, 3)


# ---------------------------------------------------------------------------
# 17. PNG 扩展名归一化（fix: enforce PNG save extension）
#
# 注意：normalize_png_path 走 pathlib，Windows 上 `str(Path("/a/b/bar"))`
# 会变成 `\a\b\bar`（本机分隔符），这是正常平台行为、不是产品 bug。
# 因此这里只断言「路径语义」（name / suffix / parent / stem），不逐字比较
# 原始 POSIX 字符串，保证 Windows 与 POSIX 均可通过。
# ---------------------------------------------------------------------------

def _assert_png_path(inp, *, name, stem, suffix=".png", parent=None):
    """断言 normalize_png_path 结果在语义上是合法的 .png 路径。

    - name / stem / suffix 精确比较；
    - parent 若非 None，按 Path 语义比较（分隔符差异不影响）。
    """
    out = normalize_png_path(inp)
    p = Path(out)
    assert p.name == name
    assert p.stem == stem
    assert p.suffix == suffix
    assert p.suffix.lower() == ".png"
    if parent is not None:
        assert p.parent == Path(parent)
    return out


def test_17_normalize_no_extension():
    _assert_png_path("foo", name="foo.png", stem="foo")
    out = normalize_png_path(str(Path("a") / "b" / "bar"))
    p = Path(out)
    assert p.name == "bar.png"
    assert p.parent == Path("a") / "b"
    assert p.suffix == ".png"


def test_17_normalize_png_accepted():
    assert Path(normalize_png_path("foo.png")).name == "foo.png"
    assert Path(normalize_png_path("foo.PNG")).name == "foo.PNG"   # 保留原写法
    assert Path(normalize_png_path("foo.Png")).name == "foo.Png"
    for s in ("foo.png", "foo.PNG", "foo.Png"):
        assert Path(normalize_png_path(s)).suffix.lower() == ".png"


def test_17_normalize_other_ext_replaced():
    for bad in ("foo.jpg", "foo.jpeg", "foo.bmp", "foo.webp", "foo.gif"):
        out = normalize_png_path(bad)
        assert Path(out).name == "foo.png"
        assert Path(out).suffix == ".png"
    # 带目录：目录保留、扩展名替换
    out = normalize_png_path(str(Path("a") / "b" / "c.gif"))
    p = Path(out)
    assert p.name == "c.png"
    assert p.parent == Path("a") / "b"
    assert p.suffix == ".png"


def test_17_normalize_unicode_and_wrong_ext():
    assert Path(normalize_png_path("照片.jpg")).name == "照片.png"
    assert Path(normalize_png_path("照片")).name == "照片.png"
    # 中文目录 + 错误扩展名：目录与 stem 保留，仅扩展名归一化
    out = normalize_png_path(str(Path("目录") / "结果.jpeg"))
    p = Path(out)
    assert p.name == "结果.png"
    assert p.stem == "结果"
    assert p.parent == Path("目录")
    assert p.suffix == ".png"


def test_17_normalize_keeps_only_png_then_saves(tmp_path):
    """错误扩展名归一化后写出的确实是 PNG（内容与扩展名一致）。"""
    st = _state_with_source()
    _, result = _run(st)
    target = tmp_path / "foo.jpg"
    path = normalize_png_path(str(target))
    assert path.endswith(".png")
    save_png(path, result)
    assert not target.exists()                  # 不生成 .jpg
    assert tmp_path.joinpath("foo.png").exists()
    with Image.open(str(tmp_path / "foo.png")) as im:
        assert im.format == "PNG"
        back = np.array(im)
    assert np.array_equal(back, result[:, :, ::-1])   # 像素一致


def test_17_no_extension_saves_png(tmp_path):
    st = _state_with_source()
    _, result = _run(st)
    path = normalize_png_path(str(tmp_path / "foo"))
    save_png(path, result)
    out = tmp_path / "foo.png"
    assert out.exists()
    with Image.open(str(out)) as im:
        assert im.format == "PNG"
    assert np.array_equal(read_png_pixels(out), result[:, :, ::-1])


# ---------------------------------------------------------------------------
# 16. legacy SHA-256 不变
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("relpath,sha", sorted(LEGACY_SHA.items()))
def test_16_legacy_unchanged(relpath, sha):
    out = sha256_of(legacy_path(relpath))
    assert out == sha, f"{relpath} SHA-256 变化"
