"""Color Fill 第一轮视觉实验。

用法：
    python3 -m tools.run_color_fill_experiment <图片...> -o <输出目录>

对每张输入图，按四种正式模式的**各自默认参数**生成：

    A. Color Fill ON / invert OFF
    B. Color Fill ON / invert ON

即每张图 4 模式 × 2 极性 = 8 张独立彩色结果；N 张图共 8N 张。

同时为每张输入生成一张 4 行 × 3 列 contact sheet，便于人工鉴赏：

    [黑白基准] [彩色填充] [彩色填充 + 反转]
    Classic
    Bayer
    Adaptive Fine
    Adaptive Bold

本脚本不修改任何算法、不修改 GUI；仅组合「算法 mask + src.render.apply_color_fill」。
实验图片与结果只留沙箱，不进入 Git/CNB。
"""

import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import algorithms, imageio  # noqa: E402
from src.render import apply_color_fill  # noqa: E402


MODES = list(algorithms.FORMAL_MODES)  # [(name, fn), ...] 各用默认参数

# contact sheet 顶部每模式标签（与 GUI 显示名一致）。
MODE_DISPLAY = {
    "classic": "Classic",
    "bayer4": "Bayer",
    "adaptive_fine": "Adaptive Fine",
    "adaptive_bold": "Adaptive Bold",
}

COL_LABELS = ["binary base", "color fill", "color fill + invert"]

LABEL_H = 30
PAD = 8
BG = (240, 240, 240)
FG = (10, 10, 10)


def _put_label(img, text, scale=0.55):
    """在图像顶部加白底标签条并写入 text。"""
    canvas = cv2.copyMakeBorder(
        img, LABEL_H, 0, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255)
    )
    cv2.putText(
        canvas, text, (6, 21), cv2.FONT_HERSHEY_SIMPLEX, scale, FG, 1, cv2.LINE_AA
    )
    return canvas


def _fit(img, w, h):
    """按目标画布尺寸等比缩放并用白底居中（仅用于拼图预览）。"""
    ih, iw = img.shape[:2]
    scale = min(w / iw, h / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    interp = cv2.INTER_NEAREST if (nw, nh) == (iw, ih) else cv2.INTER_AREA
    resized = cv2.resize(img, (nw, nh), interpolation=interp)
    tile = np.full((h, w, 3), 255, np.uint8)
    y0, x0 = (h - nh) // 2, (w - nw) // 2
    tile[y0:y0 + nh, x0:x0 + nw] = resized
    return tile


def make_contact_sheet(rows, cell_w, cell_h):
    """rows: 4 行，每行 3 张图 [base, fill, fill+inv]。返回 4×3 拼图。"""
    # 顶部列标签行
    header_cells = []
    for c in range(3):
        cell = np.full((LABEL_H, cell_w, 3), 255, np.uint8)
        cv2.putText(
            cell, COL_LABELS[c], (6, 21),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, FG, 1, cv2.LINE_AA,
        )
        header_cells.append(cell)
    header_row = np.full((LABEL_H, cell_w * 3 + PAD * 2, 3), 255, np.uint8)
    for c, cell in enumerate(header_cells):
        x0 = c * (cell_w + PAD)
        header_row[:, x0:x0 + cell_w] = cell

    grid_rows = []
    for label, imgs in rows:
        cells = [
            _put_label(_fit(im, cell_w, cell_h), COL_LABELS[c])
            for c, im in enumerate(imgs)
        ]
        row = np.full((cells[0].shape[0], cell_w * 3 + PAD * 2, 3), BG, np.uint8)
        for c, cell in enumerate(cells):
            x0 = c * (cell_w + PAD)
            row[:, x0:x0 + cell_w] = cell
        # 左侧模式名以叠加文本方式贴在左上角（避免改动行高）
        cv2.putText(
            row, label, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, FG, 2, cv2.LINE_AA
        )
        grid_rows.append(row)

    rows_with_pad = []
    for i, r in enumerate(grid_rows):
        rows_with_pad.append(r)
        if i != len(grid_rows) - 1:
            rows_with_pad.append(np.full((PAD, r.shape[1], 3), BG, np.uint8))
    return np.vstack([header_row, *rows_with_pad])


def main():
    ap = argparse.ArgumentParser(description="Color Fill 第一轮视觉实验")
    ap.add_argument("inputs", nargs="+", help="输入图片路径（A–E…）")
    ap.add_argument("-o", "--outdir", default="cf_experiment",
                    help="输出目录（默认 cf_experiment/，已在 .gitignore 之外，勿提交）")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    total_color = 0
    total_sheets = 0

    for in_path in args.inputs:
        img = imageio.imread_unicode(in_path)
        stem = os.path.splitext(os.path.basename(in_path))[0]
        print(f"\n=== {stem} ===  source={img.shape}")

        rows = []
        for name, fn in MODES:
            base = fn(img)                                # 黑白基准（默认参数）
            fill = apply_color_fill(img, base)            # A: fill ON / invert OFF
            inv_mask = 255 - base                         # invert 后的最终 mask
            fill_inv = apply_color_fill(img, inv_mask)    # B: fill ON / invert ON

            for tag, out in (("cf", fill), ("cf_inv", fill_inv)):
                path = os.path.join(args.outdir, f"{stem}__{name}__{tag}.png")
                assert cv2.imwrite(path, out), f"写入失败: {path}"
                total_color += 1
            print(f"  [{MODE_DISPLAY[name]}] base={base.shape} "
                  f"cf={fill.shape} cf_inv={fill_inv.shape}")

            rows.append((MODE_DISPLAY[name], [base, fill, fill_inv]))

        # contact sheet：统一 cell 尺寸，取第一张（classic）尺寸为基准
        ref_h, ref_w = rows[0][1][0].shape[:2]
        cell_w = min(640, ref_w)
        cell_h = max(1, int(round(ref_h * cell_w / ref_w)))
        sheet = make_contact_sheet(rows, cell_w, cell_h)
        sheet_path = os.path.join(args.outdir, f"{stem}__contact_sheet.png")
        assert cv2.imwrite(sheet_path, sheet), f"写入失败: {sheet_path}"
        total_sheets += 1
        print(f"  contact sheet -> {sheet_path} {sheet.shape}")

    print(f"\n完成：{total_color} 张彩色结果 + {total_sheets} 张 contact sheet")
    print(f"输出目录：{os.path.abspath(args.outdir)}")


if __name__ == "__main__":
    main()
