"""跨平台测试共享 helper。

目的：让普通 pytest 测试在 Windows / Linux 均可运行，不依赖 Unix-only
命令（如 `sha256sum`）。

- `sha256_of(path)`：用标准库 hashlib 以二进制方式计算文件 SHA-256；
- `assert_legacy_unchanged` / `LEGACY_SHA`：legacy 三份 .py 的基准校验，
  收敛原先在多个测试文件中重复实现的同一逻辑。

不引入任何第三方依赖。
"""

import hashlib
import os
from pathlib import Path


# legacy 三份 .py 的 SHA-256 基准（字节级不变）。
LEGACY_SHA = {
    "legacy/xiangsudian.py": "d2dd4d6879e0e4b4392e3f54c1ca03b5037c8dc73405ff9e444685c94794ae16",
    "legacy/xiangsudian2.py": "ba1053a6fd9040061735806d7d4288c1008aa527f56e0a3645bd02532be08ca2",
    "legacy/xiangsudian3.py": "f103e325f03a0e1f26b1c6658d9c26a748cf1526aa3d5b29cc19625036f987a9",
}

# 仓库根目录（tests/ 的上一级）。
REPO_ROOT = Path(__file__).resolve().parent.parent


def sha256_of(path) -> str:
    """以二进制方式计算文件 SHA-256（标准库，跨平台）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def legacy_path(relpath) -> Path:
    """把仓库相对路径解析为绝对 Path。"""
    return REPO_ROOT / relpath
