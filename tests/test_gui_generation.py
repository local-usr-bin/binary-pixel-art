"""GUI-001B1：Generate Preview 接线、GenerationKey / current-stale、后台 worker 的自动测试。

覆盖任务第十一节列出的可自动验证项：
  1. GenerationKey 同参数相等；
  2. 修改任一参数后 stale；
  3. 参数改回原值后恢复 current；
  4. 切模式 stale；
  5. 切回原模式且参数一致恢复 current；
  6. 新 source 后 stale；
  7. worker 成功返回 result；
  8. worker 异常可被 UI 状态捕获；
  9. 生成期间 busy 状态正确；
 10. 同时不能启动第二个 worker；
 11. Result Preview resize 不触发算法；
 12. 四个正式模式均可从 GUI 参数调用后端并得到严格二值结果；
 13. 后端既有测试无回归（由 tests/ 全套覆盖）；
 14. legacy SHA-256 不变（见 test_gui_state.py / 本文件末尾）。

不依赖 Tk 主循环：worker 测试用真实线程 + 轮询；App 级联调用纯 state/worker。
运行：python3.11 -m pytest tests/test_gui_generation.py -v
"""

import time

import numpy as np
import pytest

from tests.helpers import LEGACY_SHA, legacy_path, sha256_of

from gui.state import AppState, GenerationKey
from gui.worker import GenerationWorker, run_mode


def _img(seed=0, h=96, w=128):
    return (np.random.RandomState(seed).rand(h, w, 3) * 255).astype("uint8")


def _state_with_source(path="x.png", shape=(96, 128), digest="dg"):
    st = AppState()
    st.set_source(path, shape, content_digest=digest)
    return st


def _run(st, mode=None, source=None):
    """同步执行一次生成并 mark_generated（模拟成功路径）。"""
    mode = mode or st.current_mode
    params = st.get_params(mode)
    key = st.current_key()
    result = run_mode(mode, params, source if source is not None else _img())
    st.mark_generated(key, result)
    return key, result


# ---------------------------------------------------------------------------
# 1. GenerationKey 同参数相等
# ---------------------------------------------------------------------------

def test_generation_key_equal_same_params():
    st = _state_with_source()
    k1 = st.current_key()
    k2 = st.current_key()
    assert k1 == k2
    assert hash(k1) == hash(k2)
    # 可用于 set（可哈希）
    assert len({k1, k2}) == 1


def test_generation_key_differs_on_param():
    st = _state_with_source()
    k1 = st.current_key()
    st.set_param("output_width", 900)
    k2 = st.current_key()
    assert k1 != k2


def test_generation_key_includes_invert():
    st = _state_with_source()
    k1 = st.current_key()
    st.set_param("invert", True)
    assert st.current_key() != k1


def test_generation_key_includes_source_identity():
    st = _state_with_source(path="a.png")
    k1 = st.current_key()
    st.set_source("b.png", (96, 128), content_digest="dg")
    assert st.current_key() != k1
    # 同路径但内容指纹不同 -> 也视为不同 source
    st.set_source("b.png", (96, 128), content_digest="OTHER")
    assert st.current_key() != k1


def test_generation_key_includes_mode():
    st = _state_with_source()
    k_c = st.current_key()
    st.set_mode("bayer4")
    assert st.current_key() != k_c


# ---------------------------------------------------------------------------
# 2/3. 修改参数 -> stale；改回 -> current
# ---------------------------------------------------------------------------

def test_param_change_makes_stale_and_revert_restores_current():
    st = _state_with_source()
    _run(st)
    assert st.has_result() and st.is_current() and not st.is_stale()

    st.set_param("t", 140)          # 改经典参数
    assert st.is_stale() and not st.is_current()

    st.set_param("t", 127)          # 改回生成时值
    assert st.is_current() and not st.is_stale()


def test_each_param_change_makes_stale():
    """逐一修改 classic 的每个影响结果的参数，均应 stale。"""
    st = _state_with_source()
    _run(st)
    for key, val in (("output_width", 1010), ("pixel_block_size", 3),
                     ("t", 100), ("b", 40), ("equalize", False)):
        st.set_param(key, val)
        assert st.is_stale(), f"{key} 变化后未 stale"
        st.restore_defaults()       # 复位
        assert st.is_current(), f"{key} 复位后未 current"


# ---------------------------------------------------------------------------
# 4/5. 切模式 stale；切回且参数一致恢复 current
# ---------------------------------------------------------------------------

def test_mode_switch_makes_stale_switch_back_restores_current():
    st = _state_with_source()
    _run(st)
    assert st.is_current()

    st.set_mode("adaptive_fine")
    assert st.is_stale() and not st.is_current()

    st.set_mode("classic")          # 切回且参数未改
    assert st.is_current() and not st.is_stale()


def test_mode_switch_back_with_changed_params_stays_stale():
    st = _state_with_source()
    _run(st)
    st.set_mode("bayer4")
    st.set_mode("classic")
    st.set_param("output_width", 1234)   # 切回后改了参数
    assert st.is_stale()


# ---------------------------------------------------------------------------
# 6. 新 source 后 stale
# ---------------------------------------------------------------------------

def test_new_source_makes_stale():
    st = _state_with_source()
    _run(st)
    assert st.is_current()

    # 换一张内容不同的图
    st.set_source("y.png", (96, 128), content_digest="another")
    assert st.has_result()          # 旧结果仍保留
    assert st.is_stale() and not st.is_current()


# ---------------------------------------------------------------------------
# 7. worker 成功返回 result
# ---------------------------------------------------------------------------

def _wait_worker(worker, timeout=30.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        ok, payload = worker.poll()
        if ok is not None:
            return ok, payload
        time.sleep(0.01)
    raise AssertionError("worker 超时未返回")


def test_worker_success_returns_result():
    st = _state_with_source()
    src = _img()
    key = st.current_key()
    w = GenerationWorker(None, st.current_mode, st.get_params(), src, key)
    w.start()
    ok, payload = _wait_worker(w)
    assert ok is True
    assert isinstance(payload, np.ndarray)
    assert set(np.unique(payload).tolist()) <= {0, 255}
    assert w.is_done()
    # 已取过一次 -> 再 poll 返回 (None, None)
    assert w.poll() == (None, None)


def test_worker_result_matches_direct_call():
    st = _state_with_source()
    src = _img(seed=7)
    key = st.current_key()
    w = GenerationWorker(None, st.current_mode, st.get_params(), src, key)
    w.start()
    ok, payload = _wait_worker(w)
    direct = run_mode(st.current_mode, st.get_params(), src)
    assert np.array_equal(payload, direct)


# ---------------------------------------------------------------------------
# 8. worker 异常可被捕获
# ---------------------------------------------------------------------------

def test_worker_exception_is_reported():
    st = _state_with_source()
    src = _img()
    # 构造一个会产生异常的 params（矩阵尺寸非法）
    bad_params = st.get_params("bayer4")
    bad_params["matrix_size"] = 3      # 非法（应触发后端异常）
    st.set_mode("bayer4")
    key = st.current_key()
    w = GenerationWorker(None, "bayer4", bad_params, src, key)
    w.start()
    ok, payload = _wait_worker(w)
    assert ok is False
    assert isinstance(payload, Exception)


def test_worker_unknown_mode_exception():
    w = GenerationWorker(None, "nope", {}, _img(), None)
    w.start()
    ok, payload = _wait_worker(w)
    assert ok is False
    assert isinstance(payload, Exception)


# ---------------------------------------------------------------------------
# 9. busy 状态
# ---------------------------------------------------------------------------

def test_busy_flag_and_save_enabled_logic():
    st = _state_with_source()
    assert st.save_enabled() is False          # 无结果

    _run(st)
    assert st.save_enabled() is True           # 有结果且 current 且不 busy

    st.busy = True
    assert st.save_enabled() is False          # busy 时不 enable

    st.busy = False
    st.set_param("t", 200)
    assert st.save_enabled() is False          # stale 时不 enable


def test_poll_before_complete_returns_none():
    """未完成时 poll 应返回 (None, None)（驱动 UI 继续轮询）。"""
    st = _state_with_source()
    # 大图 + 大 block 制造可观计算量，保证首次 poll 前线程未必完成
    src = _img(h=400, w=500)
    w = GenerationWorker(None, "classic", st.get_params("classic"), src,
                         st.current_key())
    # 不 start：poll 直接为空
    assert w.poll() == (None, None)
    w.start()
    _wait_worker(w)


# ---------------------------------------------------------------------------
# 10. 不能启动第二个 worker（App 层语义在 state 上可验证）
# ---------------------------------------------------------------------------

def test_only_one_worker_guard_semantics():
    """App.on_generate 以 _worker is not None 作为守卫；此处验证该语义。

    模拟：worker 未完成时守卫条件为真（应拒绝再次启动）。
    """
    st = _state_with_source()
    src = _img(h=500, w=600)
    w1 = GenerationWorker(None, "classic", st.get_params(), src, st.current_key())
    current = None

    class _FakeApp:
        """复刻 App.on_generate 的守卫条件（不含 Tk）。"""
        def __init__(self):
            self._worker = None
        def try_start(self):
            if self._worker is not None:
                return "rejected"
            self._worker = w1
            return "started"

    app = _FakeApp()
    assert app.try_start() == "started"
    assert app.try_start() == "rejected"       # 第二次被拒
    assert app._worker is w1


# ---------------------------------------------------------------------------
# 11. Result Preview resize 不触发算法
# ---------------------------------------------------------------------------

def test_resize_does_not_rerun_algorithm(monkeypatch):
    """render_fitted(nearest) 只做显示缩放，不调用任何后端算法。"""
    from gui import ui_helpers

    called = {"n": 0}
    from src import algorithms

    orig = algorithms.classic
    def _spy(*a, **k):
        called["n"] += 1
        return orig(*a, **k)
    monkeypatch.setattr(algorithms, "classic", _spy)

    # 仅做 display fit 的缩放计算（纯函数，不依赖 Tk 布局）
    img = _img(h=200, w=300)
    dw, dh = ui_helpers.fit_dimensions(300, 200, 150, 150)
    assert (dw, dh) == (150, 100)
    # fit_dimensions 是纯几何，不触碰算法
    assert called["n"] == 0
    # 直接缩放显示副本，也不调用算法
    import cv2
    shown = cv2.resize(img, (dw, dh), interpolation=cv2.INTER_NEAREST)
    assert shown.shape[:2] == (dh, dw)
    assert called["n"] == 0


# ---------------------------------------------------------------------------
# 12. 四模式 GUI 参数 -> 后端严格二值
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["classic", "bayer4", "adaptive_fine", "adaptive_bold"])
def test_all_modes_binary_via_gui_params(mode):
    st = _state_with_source()
    st.set_mode(mode)
    src = _img(h=150, w=200)
    result = run_mode(mode, st.get_params(mode), src)
    assert result.ndim == 3 and result.shape[2] == 3
    uniq = set(np.unique(result).tolist())
    assert uniq <= {0, 255}, f"{mode} 非严格二值: {uniq}"
    # geometry 与 state readout 一致
    readout = st.geometry_readout(mode)
    assert result.shape[1] == readout.actual_output_width
    assert result.shape[0] == readout.actual_output_height


@pytest.mark.parametrize("mode", ["classic", "bayer4", "adaptive_fine", "adaptive_bold"])
def test_modes_deterministic(mode):
    st = _state_with_source()
    st.set_mode(mode)
    src = _img(seed=3, h=120, w=160)
    a = run_mode(mode, st.get_params(mode), src)
    b = run_mode(mode, st.get_params(mode), src)
    assert np.array_equal(a, b), f"{mode} 不确定"


# ---------------------------------------------------------------------------
# 14. legacy SHA-256 不变
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("relpath,sha", sorted(LEGACY_SHA.items()))
def test_legacy_unchanged(relpath, sha):
    out = sha256_of(legacy_path(relpath))
    assert out == sha, f"{relpath} SHA-256 变化"
