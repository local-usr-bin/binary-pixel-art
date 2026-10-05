"""生成一张无版权争议的程序化测试图，用于本地冒烟/回归验证。

不依赖任何外部素材，内容是一张"类动漫大脸"的灰度示意：
- 大面积浅色脸部（保平坦区）
- 深色头发块
- 高对比眼睛（深色瞳孔 + 浅色高光）
- 几条细发丝线条
- 一处强边缘

仅用于程序自测与本地观察，不代表最终视觉验收素材。
"""

import cv2
import numpy as np


def make_test_image(h=512, w=640, seed=0):
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 220, np.uint8)  # 浅灰底

    # 头发：顶部大深块
    cv2.rectangle(img, (int(w * 0.1), 0), (int(w * 0.9), int(h * 0.28)), (30, 30, 30), -1)

    # 脸：中央浅色椭圆
    cv2.ellipse(
        img,
        (w // 2, int(h * 0.55)),
        (int(w * 0.28), int(h * 0.34)),
        0, 0, 360, (225, 225, 225), -1,
    )

    # 左右眼：深色瞳孔 + 白色高光点（考验细节/密度表达）
    for cx in (int(w * 0.40), int(w * 0.60)):
        cy = int(h * 0.48)
        cv2.circle(img, (cx, cy), int(w * 0.035), (20, 20, 20), -1)      # 瞳孔
        cv2.circle(img, (cx + int(w * 0.012), cy - int(w * 0.012)),
                   int(w * 0.008), (255, 255, 255), -1)                   # 高光

    # 嘴：细线
    cv2.line(img, (int(w * 0.44), int(h * 0.70)),
             (int(w * 0.56), int(h * 0.70)), (40, 40, 40), 3)

    # 发丝：几条细斜线（深底上的浅线 + 浅底上的深线）
    for k in range(6):
        x = int(w * 0.15) + k * int(w * 0.05)
        cv2.line(img, (x, int(h * 0.05)), (x + int(w * 0.03), int(h * 0.25)),
                 (200, 200, 200), 1)

    # 强边缘：一侧黑色竖条
    cv2.rectangle(img, (0, 0), (int(w * 0.05), h), (10, 10, 10), -1)

    # 轻微确定性噪声（固定种子），避免完全平坦导致 adaptive/gradient 退化
    noise = rng.integers(-4, 5, img.shape, dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return img


if __name__ == "__main__":
    import os
    out = make_test_image()
    os.makedirs("outputs", exist_ok=True)
    path = os.path.join("outputs", "test_input.png")
    cv2.imwrite(path, out)
    print("wrote", path, out.shape)
