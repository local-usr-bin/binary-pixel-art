"""Color Fill：算法之后的统一渲染层（第一轮视觉实验候选）。

定位
----
Color Fill **不是第五种算法**，而是四种正式算法共同的下游 renderer。
四种算法仍只负责生成严格二值 mask；本模块在 mask 之上叠加一层连续的
原始彩色图。

冻结语义
--------
::

    source image
        ├── 四种正式算法
        │       ↓
        │   binary result
        │       ↓
        │   invert（如开启，由算法侧完成）
        │       ↓
        │   final binary mask      ──┐
        │                            │
        └── 原始彩色 source          │
                ↓                    │
           resize 到 final output 精确尺寸
           interpolation = INTER_LINEAR
                ↓                    │
           continuous color layer   ─┘
                ↓
           composite

合成规则：

- final mask 中为 **黑（0）** 的输出位置 → 取 color layer 对应位置的原图颜色；
- final mask 中为 **白（255）** 的输出位置 → 保持纯白 ``[255, 255, 255]``。

硬约束
------
1. mask 边界保持严格二值、锐利（不对 mask 做 blur / antialias）；
2. 彩色层固定使用 ``cv2.INTER_LINEAR``（本轮不暴露插值选项）；
3. 彩色层不做 pixelate、不做「每块取平均色」；
4. 本模块**不复制任何算法逻辑**，也不做 equalize / gamma / 饱和度等美化；
5. 入参 ``binary_result`` 被视为**已经完成 invert 后的最终 mask**，
   renderer 只服从该 mask，绝不自行再次 invert。

设计约束
--------
- 输入 source 为 GUI / pipeline 使用的 BGR uint8；
- ``binary_result`` 为三通道 BGR 0/255（隐藏地兼容单通道 0/255 灰度）；
- 输出尺寸严格等于 ``binary_result``，dtype 为 uint8 BGR；
- deterministic：相同输入恒得相同输出。
"""

import cv2
import numpy as np

from .config import COLOR_FILL_RESIZE


def _as_mask_bool(binary_result):
    """把二值结果规整为 H×W boolean mask（正式数据契约）。

    True 表示 mask 黑（0，将显示颜色），False 表示 mask 白（255，保持纯白）。

    接受的输入（现有二值契约）：
      - (H, W)      : 单通道 0/255
      - (H, W, 1)   : 单通道 0/255（退化为 (H, W)）
      - (H, W, 3)   : 三通道 0/255，且每个像素三通道语义一致

    判定规则（显式、不依赖隐式 broadcasting）：
      - 2D / 单通道：直接 ``arr == 0``；
      - 3 通道：``np.all(arr == 0, axis=2)``，即三通道全 0 才算黑。

    契约违反（非二值、通道语义不一致、形状不支持）时抛 ``ValueError``。
    这是技术合法性检查，与审美无关。
    """
    arr = np.asarray(binary_result)
    if arr.size == 0:
        raise ValueError("binary_result 为空，无法合成")

    if arr.ndim == 3:
        if arr.shape[2] == 1:
            arr = arr[:, :, 0]
        elif arr.shape[2] == 3:
            uniq = np.unique(arr)
            if not np.all((uniq == 0) | (uniq == 255)):
                raise ValueError(
                    "binary_result 必须是严格二值（仅 0/255），"
                    f"实际取值包含 {sorted(set(uniq.tolist()) - {0, 255})}"
                )
            # 三通道语义必须一致：每像素要么全 0 要么全 255
            all_black = np.all(arr == 0, axis=2)
            all_white = np.all(arr == 255, axis=2)
            if not np.all(all_black | all_white):
                raise ValueError(
                    "binary_result 三通道语义不一致：存在像素三通道取值不统一"
                )
            return all_black
        else:
            raise ValueError(f"不支持的通道数: {arr.shape[2]}")
    elif arr.ndim != 2:
        raise ValueError(f"不支持的形状: {arr.shape}")

    uniq = np.unique(arr)
    if not np.all((uniq == 0) | (uniq == 255)):
        raise ValueError(
            "binary_result 必须是严格二值（仅 0/255），"
            f"实际取值包含 {sorted(set(uniq.tolist()) - {0, 255})}"
        )
    return arr == 0


def apply_color_fill(source_bgr, binary_result):
    """把最终二值 mask 与原始彩色 source 合成为彩色结果。

    参数
    ----
    source_bgr
        原始彩色图（BGR uint8，(H0, W0, 3)）。可以是灰度输入，此时会被
        当作单通道数据；但正常调用应传原始彩色 source。
    binary_result
        算法输出且**已完成 invert（如开启）**的最终二值结果，
        尺寸即目标输出尺寸，取值严格 0/255，可为 (H, W, 3) 或 (H, W)。
        三通道形式要求每像素三通道语义一致；违反二值契约时抛 ValueError。

    返回
    ----
    (H, W, 3) uint8 BGR：
        - mask 白（255）位置严格 ``[255, 255, 255]``；
        - mask 黑（0）位置逐像素等于 ``cv2.resize(source_bgr, (W, H),
          interpolation=INTER_LINEAR)`` 的同位置颜色。
    """
    src = np.asarray(source_bgr)
    if src.size == 0:
        raise ValueError("source_bgr 为空，无法合成")

    mask_black = _as_mask_bool(binary_result)
    out_h, out_w = mask_black.shape[:2]

    # 彩色层：原始 source -> 精确输出尺寸，固定 INTER_LINEAR
    color_layer = cv2.resize(
        src, (out_w, out_h), interpolation=COLOR_FILL_RESIZE
    )
    if color_layer.ndim == 2:
        color_layer = cv2.cvtColor(color_layer, cv2.COLOR_GRAY2BGR)

    # 合成：白区恒 255，黑区取彩色层
    out = np.full((out_h, out_w, 3), 255, np.uint8)
    out[mask_black] = color_layer[mask_black]
    return out
