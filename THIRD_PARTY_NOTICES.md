# Third-Party Notices

本项目 `binary-pixel-art` 自身以 [MIT License](LICENSE) 发布。

本项目在 **源码运行** 与 **Windows 打包（PyInstaller onedir）** 时会使用/携带以下第三方组件。
本文件记录各组件的 **名称、用途、许可证事实与官方来源**，并说明对应许可证原件在仓库中的位置。

> **范围说明**：本文件是第三方组件的 **清单与出处声明**，**不是法律意见**，
> **也不宣称穷尽所有可能的法律义务**。
> 仓库中的 `licenses/` 目录保存的是 **来自真实 Windows 构建环境的原始许可证文本**，
> 均为 **原样落库、不做任何改写、normalize 或合并**。

---

## 0. 许可证原件位置

| 组件 | 版本（来自 Windows build env） | 原件位置 |
| --- | --- | --- |
| CPython | 3.13.16 | `licenses/CPython-3.13.16-LICENSE.txt` |
| Tcl | 8.6.15 | `licenses/Tcl-8.6.15-license.terms` |
| Tk | 8.6.15 | `licenses/Tk-8.6.15-license.terms` |
| NumPy | 2.5.3 | `licenses/NumPy-2.5.3-licenses/`（完整 upstream license tree） |
| opencv-python | 5.0.0.93 | `licenses/opencv-python-5.0.0.93-LICENSE.txt` |
| opencv-python 第三方 binary material | 5.0.0.93 | `licenses/opencv-python-5.0.0.93-LICENSE-3RD-PARTY.txt` |
| Pillow | 12.3.0 | `licenses/Pillow-12.3.0-LICENSE.txt` |

> **材料状态：以上均为 _已从实际 Windows build environment 提取并落库_。**
> 原件来自已通过正式 PyInstaller build 与 Clean Win11 VM 验证的真实 Windows 构建环境。

---

## 1. 组件清单

| 组件 | 用途 | 许可证（官方声明） | 官方来源 |
| --- | --- | --- | --- |
| CPython | 运行期解释器基础 | PSF-2.0（Python Software Foundation License Version 2） | https://docs.python.org/3/license.html |
| Tcl/Tk（含 Tkinter） | GUI 窗口工具包与 Tcl/Tk 运行时 | Tcl/Tk License（BSD 风格） | https://www.tcl.tk/software/tcltk/license.html |
| NumPy | 数组与数值计算 | BSD-3-Clause | https://numpy.org/doc/stable/license.html |
| opencv-python | 图像处理（OpenCV 的 Python wheel 分发） | opencv-python packaging = MIT；内含 OpenCV 本体 = Apache-2.0；第三方法律材料见 `LICENSE-3RD-PARTY.txt` | https://github.com/opencv/opencv-python |
| Pillow | PNG 读写（`gui/save.py`） | MIT-CMU License | https://pillow.readthedocs.io/en/stable/about.html#license |
| PyInstaller | Windows 打包工具（仅构建期，onedir + windowed） | 见下方 2.6（GPL 2.0 + special exception；少数文件 Apache-2.0） | https://pyinstaller.org/en/stable/license.html |

---

## 2. 逐项说明

### 2.1 CPython

- 用途：Python 解释器本体。PyInstaller onedir 产物会打包解释器及其标准库。
- 许可证：PSF-2.0（Python Software Foundation License Version 2）。
- 来源：<https://docs.python.org/3/license.html>
- 原件：`licenses/CPython-3.13.16-LICENSE.txt`，来自 **实际 Windows Python 3.13.16 distribution**。
- **克制说明**：CPython 官方许可文档还包含 *Licenses and Acknowledgements for Incorporated
  Software* 等相关章节。因此 **不应** 将仓库中的单个 `CPython-* LICENSE.txt` 理解为
  "Python 生态全部第三方义务已穷尽"；本项目只是 **保存该真实 redistribution material**。
  本文件不是法律意见，也不宣称穷尽所有可能义务。

### 2.2 Tcl/Tk（Tkinter）

- 用途：GUI 使用的 Tkinter 依赖 Tcl/Tk 运行时，PyInstaller 会一并收集。
- 许可证：Tcl/Tk License（BSD 风格，条款宽松，允许再分发）。
- 来源：<https://www.tcl.tk/software/tcltk/license.html>
- 原件：`licenses/Tcl-8.6.15-license.terms`（Tcl 8.6.15）、`licenses/Tk-8.6.15-license.terms`（Tk 8.6.15），
  来自实际 Windows 环境的 Tcl/Tk 8.6.15。

### 2.3 NumPy

- 用途：二值 mask 与几何计算的数组实现。
- 许可证：BSD-3-Clause（NumPy 本体）；其内部还包含若干按组件分别许可的第三方源码，
  对应的完整 upstream license tree 已原样保存在 `licenses/NumPy-2.5.3-licenses/`。
- 来源：<https://numpy.org/doc/stable/license.html>
- 原件：`licenses/NumPy-2.5.3-licenses/`，来自实际 Windows 环境的 NumPy 2.5.3。

### 2.4 opencv-python

- 用途：图像读写与形态学/阈值处理（`cv2`）。
- 许可证（官方 README 声明，需分别对待）：
  - **opencv-python 包本身（packaging）**：**MIT**；
  - **OpenCV 本体**：**Apache-2.0**；
  - **第三方 binary license material**：原样保留在
    `licenses/opencv-python-5.0.0.93-LICENSE-3RD-PARTY.txt`。
- 来源：<https://github.com/opencv/opencv-python>
- 原件：`licenses/opencv-python-5.0.0.93-LICENSE.txt`（packaging MIT）与
  `licenses/opencv-python-5.0.0.93-LICENSE-3RD-PARTY.txt`（第三方 binary material），
  来自实际 Windows 环境的 opencv-python 5.0.0.93。
- 说明：**不对 `LICENSE-3RD-PARTY.txt` 中每个第三方组件做人工拆分或重新解释**；
  该文件按 upstream 原样保留，作为权威材料。

### 2.5 Pillow

- 用途：`gui/save.py` 中的 PNG 保存与像素读取。
- 许可证：MIT-CMU License（Pillow 项目自身的宽松许可证）。
- 来源：<https://pillow.readthedocs.io/en/stable/about.html#license>
- 原件：`licenses/Pillow-12.3.0-LICENSE.txt`，来自实际 Windows 环境的 Pillow 12.3.0。

### 2.6 PyInstaller

- 用途：本项目 **Windows build tool**，用于产出 onedir + windowed 产物
  （`binary-pixel-art.spec`、`tools/build_windows.ps1`）。
- **许可结构（准确表述）**：
  - PyInstaller 采用 **GPL 2.0 + special exception** 的许可结构；**少数文件采用 Apache-2.0**。
  - 该官方 exception 明确允许：**将 PyInstaller 与应用程序打包后，生成的 bundle 可以使用
    应用程序自身的许可证发布**。
  - 因此，本项目 **最终应用不要求附带 PyInstaller license，也不要求 PyInstaller attribution**。
- **本仓库的处理**：本项目最终 portable license bundle 中 **不复制 PyInstaller `COPYING.txt`**；
  相应的 `licenses/` 目录也 **不包含** PyInstaller 的许可证文件。
- 来源：<https://pyinstaller.org/en/stable/license.html>
- 澄清：以上 **不等于** PyInstaller 让本项目本身变成 GPL；本项目仍以自身 MIT License 发布。

---

## 3. 后续动作

**Windows Third-party License Harvest 已完成**：`licenses/` 中的材料均来自实际 Windows build
environment 的第三方许可证原件，原样落库。

仍待进行：

1. 在 **Final Windows Release Package Assembly** gate 中，将 `LICENSE`、`THIRD_PARTY_NOTICES.md`
   与 `licenses/` 一并放入最终绿色 ZIP，并计算最终 ZIP 的 SHA-256。
2. 在 Clean Win11 VM 上对最终 release-candidate ZIP 做最后一次 smoke。
