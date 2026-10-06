# Third-Party Notices

本项目 `binary-pixel-art` 自身以 [MIT License](LICENSE) 发布。

本项目在 **源码运行** 与 **Windows 打包（PyInstaller onedir）** 时会使用/携带以下第三方组件。
下面仅记录各组件的 **名称、用途、许可证事实与官方来源**，用于发布材料准备与合规追踪。

> **范围说明**：本文件是第三方组件的 **清单与出处声明**，不是许可证全文合集。
> 本仓库 **不伪造、不搬运、不转写任何第三方许可证全文**；在非 Windows 环境（如 Linux）从
> wheel 中提取的许可证文件 **不能** 替代真实 Windows 产物中的许可证文件。
> 真实 Windows release bundle 的许可证文件必须从 **Windows 构建产物本身** 收齐，
> 这一步属于后续 **Windows Third-party License Harvest** gate，**本轮未完成**。

---

## 1. 组件清单

| 组件 | 用途 | 许可证（官方声明） | 官方来源 |
| --- | --- | --- | --- |
| CPython | 运行期解释器基础 | PSF-2.0（Python Software Foundation License Version 2） | https://docs.python.org/3/license.html |
| Tcl/Tk（含 Tkinter） | GUI 窗口工具包与 Tcl/Tk 运行时 | Tcl/Tk License（BSD 风格） | https://www.tcl.tk/software/tcltk/license.html |
| NumPy | 数组与数值计算 | BSD-3-Clause | https://numpy.org/doc/stable/license.html |
| opencv-python | 图像处理（OpenCV 的 Python wheel 分发） | Python 包本身 MIT；内含 OpenCV 本体 Apache-2.0；第三方依赖见 `LICENSE-3RD-PARTY.txt`（wheel 内随 FFmpeg，LGPLv2.1） | https://github.com/opencv/opencv-python |
| Pillow | PNG 读写（`gui/save.py`） | MIT-CMU License | https://pillow.readthedocs.io/en/stable/about.html#license |
| PyInstaller | Windows 打包工具（仅构建期，onedir + windowed） | GPL-2.0-or-later，附 **bootloader exception**（允许打包专有/其他许可程序并无须以 GPL 发布产物） | https://pyinstaller.org/en/stable/license.html |

---

## 2. 逐项说明

### 2.1 CPython

- 用途：Python 解释器本体。PyInstaller onedir 产物会打包解释器及其标准库。
- 许可证：PSF-2.0（Python Software Foundation License Version 2）。
- 来源：<https://docs.python.org/3/license.html>

### 2.2 Tcl/Tk（Tkinter）

- 用途：GUI 使用的 Tkinter 依赖 Tcl/Tk 运行时，PyInstaller 会一并收集。
- 许可证：Tcl/Tk License（BSD 风格，条款宽松，允许再分发）。
- 来源：<https://www.tcl.tk/software/tcltk/license.html>

### 2.3 NumPy

- 用途：二值 mask 与几何计算的数组实现。
- 许可证：BSD-3-Clause。
- 来源：<https://numpy.org/doc/stable/license.html>

### 2.4 opencv-python

- 用途：图像读写与形态学/阈值处理（`cv2`）。
- 许可证（官方 README 声明，需分别对待）：
  - **opencv-python 包本身（本仓库 scripts）**：MIT License；
  - **OpenCV 本体**：Apache-2.0 License；
  - **第三方包许可证**：见其 `LICENSE-3RD-PARTY.txt`；
  - wheel 随附的 FFmpeg：**LGPLv2.1**。
- 来源：<https://github.com/opencv/opencv-python>
- 备注：因包含 Apache-2.0 与 LGPLv2.1 组件，Windows 发布包必须原样携带其许可证文本
  （后续 gate 收齐），本文件仅记录事实。

### 2.5 Pillow

- 用途：`gui/save.py` 中的 PNG 保存与像素读取。
- 许可证：MIT-CMU License（Pillow 项目自身的宽松许可证）。
- 来源：<https://pillow.readthedocs.io/en/stable/about.html#license>

### 2.6 PyInstaller

- 用途：构建 Windows onedir + windowed 产物（`binary-pixel-art.spec`、`tools/build_windows.ps1`）。
- 许可证：GPL-2.0-or-later，附 **bootloader exception**，该例外明确允许用 PyInstaller 打包
  非 GPL 程序并以任意许可证发布打包产物。
- 来源：<https://pyinstaller.org/en/stable/license.html>
- 备注：PyInstaller 为构建期工具，其本体通常按需随产物附带许可证说明（后续 gate 确认）。

---

## 3. 未决 / 后续动作

以下事项 **本轮不处理**，属于后续 **Windows Third-party License Harvest** gate：

1. 从 **真实 Windows PyInstaller 产物** 中收集 `LICENSE` / `LICENSE.txt` / `*-3RD-PARTY.txt`
   等许可证文件，并核对与上表一致。
2. 确认 FFmpeg（LGPLv2.1）等弱 copyleft 组件的合规再分发方式。
3. 形成最终发布用的许可证 bundle 与 `THIRD_PARTY_NOTICES` 合并版。
