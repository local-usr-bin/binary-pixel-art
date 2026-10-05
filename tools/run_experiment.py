"""最小视觉实验入口。

用法：
    python3.11 -m tools.run_experiment <输入图片路径> [-o 输出目录]

对一张输入图，一次生成 6 张严格黑白结果：
    classic / m1_otsu / m2_bayer4 / m3_adaptive / m4_gradient / m5_pattern
并额外生成一张 2x3 contact sheet 便于并排比较（非核心依赖）。
"""

import argparse
import os
import sys

import cv2

# 让脚本既能 `python -m tools.run_experiment` 也能直接 `python tools/run_experiment.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import algorithms  # noqa: E402

ALGOS = [
    ("classic", algorithms.classic),
    ("m1_otsu", algorithms.m1_otsu),
    ("m2_bayer4", algorithms.m2_bayer4),
    ("m3_adaptive", algorithms.m3_adaptive),
    ("m4_gradient", algorithms.m4_gradient),
    ("m5_pattern", algorithms.m5_pattern),
]


def make_contact_sheet(images, labels):
    """2 行 3 列拼图，左上角放标签。"""
    assert len(images) == 6
    h, w = images[0].shape[:2]
    label_h = 28
    grid_rows = []
    for r in range(2):
        row_imgs = []
        for c in range(3):
            idx = r * 3 + c
            canvas = cv2.copyMakeBorder(
                images[idx], label_h, 0, 0, 0,
                cv2.BORDER_CONSTANT, value=(255, 255, 255),
            )
            cv2.putText(
                canvas, labels[idx], (4, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA,
            )
            row_imgs.append(canvas)
        grid_rows.append(cv2.hconcat(row_imgs))
    return cv2.vconcat(grid_rows)


def main():
    ap = argparse.ArgumentParser(description="binary-pixel-art 第一轮视觉实验")
    ap.add_argument("input", help="输入图片路径")
    ap.add_argument("-o", "--outdir", default="outputs", help="输出目录（默认 outputs/）")
    args = ap.parse_args()

    img = cv2.imread(args.input, cv2.IMREAD_COLOR)
    if img is None:
        print(f"无法读取输入图片: {args.input}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.input))[0]

    results, labels = [], []
    for name, fn in ALGOS:
        out = fn(img)
        path = os.path.join(args.outdir, f"{base}__{name}.png")
        cv2.imwrite(path, out)
        results.append(out)
        labels.append(name)
        print("wrote", path, out.shape)

    sheet = make_contact_sheet(results, labels)
    sheet_path = os.path.join(args.outdir, f"{base}__contact_sheet.png")
    cv2.imwrite(sheet_path, sheet)
    print("wrote", sheet_path, sheet.shape)


if __name__ == "__main__":
    main()
