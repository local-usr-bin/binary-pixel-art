"""Unicode-safe 图片读取的自动测试（Windows 关键修复）。

背景：`cv2.imread(path)` 在 Windows 上对中文/Unicode 路径不可靠；
`src/imageio.imread_unicode` 改为 `Path.read_bytes()` + `cv2.imdecode()`，
把「路径访问」与「OpenCV 解码」解耦。

覆盖：
  1. ASCII 路径：imread_unicode 与参考 cv2.imread 逐像素一致（PNG 无损）；
  2. Unicode 目录 / 中文文件名 / 中文目录+中文文件名 / 空格 / Unicode 字符，
     与 ASCII 路径结果逐像素一致；
  3. 文件不存在 -> ImageReadError；
  4. 无效图片字节 -> ImageDecodeError；
  5. 解码 flag 与 cv2.IMREAD_COLOR 一致（保持既有解码语义）。

测试仅用 pathlib / tempfile，不写死 POSIX 分隔符，Linux/WB 亦可运行。
运行：python3.11 -m pytest tests/test_imageio_unicode.py -v
"""

import cv2
import numpy as np
import pytest

from src import imageio
from src.imageio import (
    imread_unicode, imwrite_unicode, ImageReadError, ImageDecodeError,
)


def _make_image(h=48, w=64, seed=0):
    """确定性彩色测试图（含结构，便于验证解码一致）。"""
    img = np.zeros((h, w, 3), np.uint8)
    y, x = np.mgrid[0:h, 0:w]
    img[..., 0] = (x * 3 % 256).astype(np.uint8)
    img[..., 1] = (y * 5 % 256).astype(np.uint8)
    img[..., 2] = ((x + y + seed) * 7 % 256).astype(np.uint8)
    return img


# ---------------------------------------------------------------------------
# 1. ASCII 路径：与参考 cv2.imread 逐像素一致（无损 PNG）
# ---------------------------------------------------------------------------

def test_ascii_png_matches_reference_imread(tmp_path):
    img = _make_image(seed=1)
    p = tmp_path / "plain.png"
    assert cv2.imwrite(str(p), img)              # 参考写入
    ref = cv2.imread(str(p), cv2.IMREAD_COLOR)   # 参考读取
    got = imread_unicode(str(p))
    assert ref is not None and got is not None
    assert got.shape == ref.shape
    assert np.array_equal(got, ref)


def test_ascii_jpeg_matches_reference_imread(tmp_path):
    """JPEG 有损：只要两条链路读的是同一文件，结果必须逐像素一致。"""
    img = _make_image(seed=2)
    p = tmp_path / "photo.jpg"
    assert cv2.imwrite(str(p), img)
    ref = cv2.imread(str(p), cv2.IMREAD_COLOR)
    got = imread_unicode(str(p))
    assert np.array_equal(got, ref)


# ---------------------------------------------------------------------------
# 2. Unicode / 中文 / 空格 / 特殊字符路径
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dirname,filename", [
    ("测试目录", "a.png"),              # 中文目录
    ("plain", "动漫图片.png"),           # 中文文件名
    ("测试目录", "动漫图片.png"),         # 中文目录 + 中文文件名
    ("带 空格 的目录", "my image.png"),   # 空格
    ("üñïçødé", "café_ñ.png"),          # 其他 Unicode 字符
])
def test_unicode_paths_match_ascii(tmp_path, dirname, filename):
    img = _make_image(seed=7)
    # 写到 ASCII 路径（无损 PNG）作为参考
    ref_path = tmp_path / "ref.png"
    assert cv2.imwrite(str(ref_path), img)
    ref = cv2.imread(str(ref_path), cv2.IMREAD_COLOR)

    # 同一张图写到 Unicode 路径
    uni_dir = tmp_path / dirname
    uni_dir.mkdir(parents=True, exist_ok=True)
    uni_path = uni_dir / filename
    assert imwrite_unicode(str(uni_path), img)

    got = imread_unicode(str(uni_path))
    assert got is not None
    assert got.shape == ref.shape
    assert np.array_equal(got, ref)     # 与 ASCII 路径逐像素一致


def test_unicode_path_roundtrip_png(tmp_path):
    img = _make_image(seed=9)
    p = tmp_path / "中文目录" / "结果图.PNG"
    p.parent.mkdir(parents=True, exist_ok=True)
    assert imwrite_unicode(str(p), img)
    got = imread_unicode(str(p))
    assert np.array_equal(got, img)     # PNG 无损 -> 完全一致


def test_pathlib_path_object_accepted(tmp_path):
    """直接传 pathlib.Path（而非 str）也应工作（Windows 原生 Unicode）。"""
    img = _make_image(seed=3)
    p = tmp_path / "目录" / "img.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    assert imwrite_unicode(p, img)      # Path 对象
    got = imread_unicode(p)             # Path 对象
    assert np.array_equal(got, img)


# ---------------------------------------------------------------------------
# 3. 文件读取失败 -> ImageReadError
# ---------------------------------------------------------------------------

def test_missing_file_raises_read_error(tmp_path):
    with pytest.raises(ImageReadError):
        imread_unicode(str(tmp_path / "does_not_exist.png"))


def test_missing_file_unicode_path_raises_read_error(tmp_path):
    with pytest.raises(ImageReadError):
        imread_unicode(str(tmp_path / "不存在的目录" / "不存在.png"))


def test_directory_path_raises_read_error(tmp_path):
    # 传目录路径：读字节失败 -> ImageReadError（而非崩溃）
    with pytest.raises((ImageReadError, ImageDecodeError)):
        imread_unicode(str(tmp_path))


# ---------------------------------------------------------------------------
# 4. 无效图片字节 -> ImageDecodeError
# ---------------------------------------------------------------------------

def test_invalid_bytes_raises_decode_error(tmp_path):
    p = tmp_path / "bad.png"
    p.write_bytes(b"this is definitely not an image")
    with pytest.raises(ImageDecodeError):
        imread_unicode(str(p))


def test_empty_file_raises_decode_error(tmp_path):
    p = tmp_path / "empty.png"
    p.write_bytes(b"")
    with pytest.raises(ImageDecodeError):
        imread_unicode(str(p))


def test_invalid_bytes_unicode_path_raises_decode_error(tmp_path):
    p = tmp_path / "中文目录" / "坏图.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x00\x01\x02notimage")
    with pytest.raises(ImageDecodeError):
        imread_unicode(str(p))


# ---------------------------------------------------------------------------
# 5. 解码 flag 与既有 cv2.imread 语义一致
# ---------------------------------------------------------------------------

def test_default_flag_is_imread_color():
    assert imageio.DEFAULT_IMREAD_FLAG == cv2.IMREAD_COLOR


def test_grayscale_flag_optional(tmp_path):
    """显式传 flag 时行为与 cv2.imread 同 flag 一致。"""
    img = _make_image(seed=5)
    p = tmp_path / "gray.png"
    assert cv2.imwrite(str(p), img)
    ref = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    got = imread_unicode(str(p), cv2.IMREAD_GRAYSCALE)
    assert got.ndim == 2
    assert np.array_equal(got, ref)


def test_imwrite_unicode_returns_false_on_bad_dir(tmp_path):
    img = _make_image()
    bad = tmp_path / "no_such_dir" / "x.png"
    assert imwrite_unicode(str(bad), img) is False


# ---------------------------------------------------------------------------
# 保护：既有后端算法不受影响（源读取与算法解耦）
# ---------------------------------------------------------------------------

def test_algorithms_unchanged_on_unicode_source(tmp_path):
    """用 Unicode 路径读到的 source 走 classic，与 ASCII 版本结果一致。"""
    from gui.worker import run_mode
    from gui.state import AppState

    img = _make_image(h=120, w=160, seed=11)
    p_ascii = tmp_path / "src.png"
    assert cv2.imwrite(str(p_ascii), img)
    p_uni = tmp_path / "中文目录" / "源图.png"
    p_uni.parent.mkdir(parents=True, exist_ok=True)
    assert imwrite_unicode(str(p_uni), img)

    a = imread_unicode(str(p_ascii))
    b = imread_unicode(str(p_uni))
    assert np.array_equal(a, b)

    st = AppState()
    st.set_source("x", a.shape[:2], content_digest="d")
    out_a = run_mode("classic", st.get_params("classic"), a)
    out_b = run_mode("classic", st.get_params("classic"), b)
    assert np.array_equal(out_a, out_b)
    assert set(np.unique(out_a).tolist()) <= {0, 255}
