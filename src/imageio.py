"""Unicode-safe 图片读取/写入 helper。

背景：`cv2.imread(path, ...)` 在 Windows 上对含中文/Unicode 的文件路径不可靠
（底层使用窄字符 `fopen`，非 ASCII 路径可能失败）。本模块把
「文件系统路径访问」与「OpenCV 解码」解耦：

    1. 用 Python `pathlib.Path` 访问文件（Windows 原生 Unicode 路径支持）；
    2. `Path(path).read_bytes()` 读取原始字节；
    3. `np.frombuffer(..., dtype=np.uint8)`；
    4. `cv2.imdecode(...)` 解码。

解码仍走 OpenCV，使用与调用方一致的 IMREAD flag，**不改变既有解码语义**。

错误分层：
- `ImageReadError`   ：文件层面失败（不存在 / 权限 / IO）；
- `ImageDecodeError` ：字节层面失败（非受支持图片 / 解码返回空）。

不通过临时英文文件、shell、subprocess、locale 修改或文件名转 ASCII 等
手段规避问题。
"""

from pathlib import Path

import cv2
import numpy as np


class ImageReadError(Exception):
    """文件读取失败（路径访问层面）。"""


class ImageDecodeError(Exception):
    """图片解码失败（内容层面）。"""


# GUI / 工具当前统一使用的解码 flag（与既有 cv2.imread 调用保持一致）。
DEFAULT_IMREAD_FLAG = cv2.IMREAD_COLOR


def imread_unicode(path, flag=DEFAULT_IMREAD_FLAG):
    """Unicode-safe 读取图片，返回 BGR ndarray。

    与 `cv2.imread(path, flag)` 的解码结果一致；区别仅在于经由
    `Path.read_bytes()` + `cv2.imdecode()`，从而支持 Windows Unicode 路径。

    失败时抛出明确异常（而非返回 None）：
    - 文件不存在 / 权限 / IO -> ImageReadError
    - 内容不是受支持图片 / 解码为空 -> ImageDecodeError
    """
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise ImageReadError(f"无法读取文件：{p}（{exc}）") from exc

    if not data:
        raise ImageDecodeError(f"文件为空，无法解码：{p}")

    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, flag)
    if img is None or img.size == 0:
        raise ImageDecodeError(f"无法解码图片（内容不是受支持的图片格式）：{p}")
    return img


def imwrite_unicode(path, img, params=None):
    """Unicode-safe 写入图片（按扩展名推断格式）。

    返回 True / False（与 cv2.imwrite 语义一致）。
    支持 Unicode 路径：先 `cv2.imencode` 到内存，再 `Path.write_bytes`。
    """
    p = Path(path)
    ext = p.suffix or ".png"
    ok, buf = cv2.imencode(ext, img, params or [])
    if not ok:
        return False
    try:
        p.write_bytes(buf.tobytes())
    except OSError:
        return False
    return True
