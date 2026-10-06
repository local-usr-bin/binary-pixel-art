# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：binary-pixel-art Windows onedir + windowed 构建。

本 spec 表达的是已在 Windows 11 x64 / Python 3.13.16 真机验证成功的配置：
  - entry point：gui/app.py
  - onedir（COLLECT），非 onefile
  - windowed / noconsole（console=False）
  - hiddenimports / datas / binaries 均为空（标准 hooks 自动处理 tkinter、
    NumPy、OpenCV、Pillow，无需手工补充）

机器无关：entry point 由本 spec 自身位置（SPECPATH）解析，
仓库移动到任意盘符 / 任意父目录后仍有效；不写入任何开发机绝对路径。

构建：
    python -m PyInstaller --clean --noconfirm binary-pixel-art.spec
产物：
    dist/binary-pixel-art/
"""

import os

# 用 spec 自身所在目录（PyInstaller 提供的 SPECPATH）定位仓库根，
# 不依赖当前工作目录，也不写入机器绝对路径。
ROOT = os.path.abspath(SPECPATH)  # noqa: F821 —— SPECPATH 由 PyInstaller 注入

a = Analysis(
    [os.path.join(ROOT, "gui", "app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="binary-pixel-art",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="binary-pixel-art",
)
