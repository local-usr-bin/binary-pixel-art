"""GUI 状态层与 UI 辅助的自动测试（GUI-001A）。

覆盖任务第十二节的可自动验证项：
  1. 四模式默认参数正确；
  2. 模式切换保留各自参数；
  3. Restore Defaults 只恢复当前模式；
  4. geometry readout 与 compute_geometry 一致；
  5. Adaptive blockSize UI 输入保持合法奇数；
  6. b >= t 不被拒绝；
  7. 打开新 source 后 source state 正确；
  8. legacy SHA-256 不变；
  9. 后端既有完整测试无回归（由 tests/ 全套覆盖）。

GUI 视觉布局需人工 smoke，本文件只测非视觉逻辑。
运行：python3.11 -m pytest tests/test_gui_state.py -v
"""

import pytest

from tests.helpers import LEGACY_SHA, legacy_path, sha256_of

from gui.state import (
    AppState,
    default_params,
    normalize_block_size,
    MODE_ORDER,
    MODE_LABELS,
    GeometryReadout,
)
from gui.ui_helpers import fit_dimensions
from src.params import (
    compute_geometry,
    DEFAULT_GEOMETRY,
    CLASSIC_DEFAULT_T,
    CLASSIC_DEFAULT_B,
    BAYER_DEFAULT_MATRIX,
    BAYER_DEFAULT_TONE_BIAS,
    ADAPTIVE_FINE_DEFAULT_BLOCK,
    ADAPTIVE_BOLD_DEFAULT_BLOCK,
    ADAPTIVE_DEFAULT_C,
)


# ---------------------------------------------------------------------------
# 1. 四模式默认参数正确
# ---------------------------------------------------------------------------

def test_defaults_classic():
    p = default_params("classic")
    assert p["output_width"] == 1000
    assert p["pixel_block_size"] == 2
    assert p["t"] == CLASSIC_DEFAULT_T == 127
    assert p["b"] == CLASSIC_DEFAULT_B == 60
    assert p["equalize"] is True
    assert p["invert"] is False


def test_defaults_bayer4():
    p = default_params("bayer4")
    assert p["output_width"] == 1280
    assert p["pixel_block_size"] == 10
    assert p["matrix_size"] == BAYER_DEFAULT_MATRIX == 4
    assert p["tone_bias"] == BAYER_DEFAULT_TONE_BIAS == 0


def test_defaults_adaptive_fine():
    p = default_params("adaptive_fine")
    assert p["output_width"] == 1280
    assert p["pixel_block_size"] == 10
    assert p["block_size"] == ADAPTIVE_FINE_DEFAULT_BLOCK == 11
    assert p["c"] == ADAPTIVE_DEFAULT_C == 2


def test_defaults_adaptive_bold():
    p = default_params("adaptive_bold")
    assert p["output_width"] == 1280
    assert p["pixel_block_size"] == 10
    assert p["block_size"] == ADAPTIVE_BOLD_DEFAULT_BLOCK == 25
    assert p["c"] == ADAPTIVE_DEFAULT_C == 2


def test_defaults_match_backend_geometry():
    """GUI 默认 geometry 与后端 DEFAULT_GEOMETRY 完全对齐。"""
    for mode in MODE_ORDER:
        p = default_params(mode)
        assert p["output_width"] == DEFAULT_GEOMETRY[mode]["output_width"]
        assert p["pixel_block_size"] == DEFAULT_GEOMETRY[mode]["pixel_block_size"]


def test_state_initial_mode_classic():
    st = AppState()
    assert st.current_mode == "classic"
    assert set(st.modes()) == set(MODE_ORDER)
    assert set(MODE_LABELS.keys()) == set(MODE_ORDER)


# ---------------------------------------------------------------------------
# 2. 模式切换保留各自参数
# ---------------------------------------------------------------------------

def test_mode_switch_keeps_params():
    st = AppState()
    # Classic 调参
    st.set_param("output_width", 900)
    st.set_param("pixel_block_size", 3)
    st.set_param("t", 140)
    # 切到 Bayer 调参
    st.set_mode("bayer4")
    st.set_param("output_width", 1600)
    st.set_param("matrix_size", 8)
    st.set_param("tone_bias", -20)
    # 切回 Classic：应恢复 900/3/140 等
    st.set_mode("classic")
    p = st.get_params()
    assert p["output_width"] == 900
    assert p["pixel_block_size"] == 3
    assert p["t"] == 140
    assert p["b"] == 60          # 未改，保持默认
    assert p["equalize"] is True
    # 再切回 Bayer：应恢复 1600/8/-20
    st.set_mode("bayer4")
    pb = st.get_params()
    assert pb["output_width"] == 1600
    assert pb["matrix_size"] == 8
    assert pb["tone_bias"] == -20


def test_independent_mode_params():
    st = AppState()
    st.set_param("output_width", 1111, mode="classic")
    st.set_param("output_width", 2222, mode="bayer4")
    st.set_param("output_width", 3333, mode="adaptive_fine")
    assert st.get_param("output_width", "classic") == 1111
    assert st.get_param("output_width", "bayer4") == 2222
    assert st.get_param("output_width", "adaptive_fine") == 3333


# ---------------------------------------------------------------------------
# 3. Restore Defaults 只恢复当前模式
# ---------------------------------------------------------------------------

def test_restore_defaults_only_current_mode():
    st = AppState()
    # 改 Classic 和 Bayer
    st.set_param("output_width", 900, mode="classic")
    st.set_param("t", 140, mode="classic")
    st.set_param("output_width", 1600, mode="bayer4")
    # 当前模式设为 classic，恢复默认
    st.set_mode("classic")
    st.restore_defaults()
    pc = st.get_params("classic")
    assert pc["output_width"] == 1000
    assert pc["t"] == 127
    # Bayer 不应被重置
    pb = st.get_params("bayer4")
    assert pb["output_width"] == 1600


def test_restore_defaults_specific_mode():
    st = AppState()
    st.set_param("output_width", 1600, mode="bayer4")
    st.restore_defaults(mode="bayer4")
    assert st.get_param("output_width", "bayer4") == 1280


# ---------------------------------------------------------------------------
# 4. geometry readout 与 compute_geometry 一致
# ---------------------------------------------------------------------------

def test_geometry_readout_matches_backend():
    st = AppState()
    st.set_source("x.png", (600, 800))   # h, w
    st.set_param("output_width", 1000, mode="classic")
    st.set_param("pixel_block_size", 3, mode="classic")
    r = st.geometry_readout("classic")
    geo = compute_geometry(800, 600, 1000, 3)
    assert r.actual_output_width == geo.actual_output_width
    assert r.actual_output_height == geo.actual_output_height
    assert r.logical_width == geo.logical_width
    assert r.logical_height == geo.logical_height
    # requested 记录的是目标宽度（非吸附后）
    assert r.requested_output_width == 1000
    assert r.pixel_block_size == 3
    # 展示文本包含实际输出与逻辑网格
    txt = r.format()
    assert "实际输出" in txt and "逻辑网格" in txt


def test_geometry_readout_default_classic():
    st = AppState()
    st.set_source("x.png", (600, 800))
    r = st.geometry_readout("classic")
    # 1000/2 -> logical 500, actual 1000
    assert r.actual_output_width == 1000
    assert r.logical_width == 500


def test_geometry_readout_without_source_uses_placeholder():
    st = AppState()
    # 未打开 source 也应能返回 readout（不抛异常）
    r = st.geometry_readout()
    assert isinstance(r, GeometryReadout)
    assert r.actual_output_width >= 1


# ---------------------------------------------------------------------------
# 5. Adaptive blockSize UI 输入保持合法奇数
# ---------------------------------------------------------------------------

def test_normalize_block_size():
    assert normalize_block_size(1) == 3
    assert normalize_block_size(2) == 3
    assert normalize_block_size(3) == 3
    assert normalize_block_size(4) == 5
    assert normalize_block_size(10) == 11
    assert normalize_block_size(11) == 11
    assert normalize_block_size(0) == 3
    assert normalize_block_size(-5) == 3


@pytest.mark.parametrize("mode", ["adaptive_fine", "adaptive_bold"])
def test_block_size_always_odd_via_state(mode):
    st = AppState()
    for bad in (4, 6, 10, 2, 0, 1):
        stored = st.set_param("block_size", bad, mode=mode)
        assert stored >= 3 and stored % 2 == 1


# ---------------------------------------------------------------------------
# 6. b >= t 不被拒绝
# ---------------------------------------------------------------------------

def test_b_ge_t_not_rejected():
    st = AppState()
    # 允许写入 b >= t
    st.set_param("t", 60, mode="classic")
    stored = st.set_param("b", 127, mode="classic")
    assert stored == 127
    assert st.get_param("b", "classic") == 127
    # 有轻量提示
    warn = st.classic_b_ge_t_warning(60, 127)
    assert warn  # 非空
    # b < t 时无提示
    assert st.classic_b_ge_t_warning(127, 60) == ""


# ---------------------------------------------------------------------------
# 7. 打开新 source 后 source state 正确
# ---------------------------------------------------------------------------

def test_set_source():
    st = AppState()
    assert st.source_path is None
    assert st.source_shape is None
    assert st.source_filename == ""
    st.set_source("/tmp/foo/bar.png", (1080, 1920))
    assert st.source_shape == (1080, 1920)
    assert st.source_filename == "bar.png"
    # 换一张
    st.set_source("/tmp/baz.jpg", (480, 640))
    assert st.source_shape == (480, 640)
    assert st.source_filename == "baz.jpg"


# ---------------------------------------------------------------------------
# 8. legacy SHA-256 不变
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("relpath,sha", sorted(LEGACY_SHA.items()))
def test_legacy_unchanged(relpath, sha):
    out = sha256_of(legacy_path(relpath))
    assert out == sha, f"{relpath} SHA-256 变化"


# ---------------------------------------------------------------------------
# 附加：preview fit helper 纯几何
# ---------------------------------------------------------------------------

def test_fit_dimensions_keeps_aspect_ratio():
    # 宽图 fit 进方框 -> 受宽度限制
    dw, dh = fit_dimensions(1000, 500, 400, 400)
    assert dw == 400 and dh == 200
    # 竖图 fit 进方框 -> 受高度限制
    dw, dh = fit_dimensions(500, 1000, 400, 400)
    assert dw == 200 and dh == 400


def test_fit_dimensions_no_upscale():
    # 小图不放大
    dw, dh = fit_dimensions(100, 80, 400, 400)
    assert (dw, dh) == (100, 80)


def test_fit_dimensions_min_one():
    dw, dh = fit_dimensions(1000, 1000, 0, 0)
    assert dw >= 1 and dh >= 1
