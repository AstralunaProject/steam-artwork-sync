"""Erases a rectangular strip (bar, divider) from every frame of a GIF, filling it from the surroundings.

Use case: an art used as a single piece with no side piece, so a vertical divider (e.g. two light lines with a
black gap) has no reason to exist. OpenCV Telea inpaint frame by frame; delays copied from the original (sync and
duration intact); trailer 0x21 through longart's gravar_gif. Run watermark.py AFTERWARDS.

    uv run --no-project --with opencv-python-headless --with numpy --with pillow python erase_strip.py \
        --entrada x.gif --saida y.gif --caixa 102,2,118,822 [--raio 6] [--cores 48]
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from longart import blocos_gce, gravar_gif  # noqa: E402
from watermark import quadros_gif  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", "--entrada", dest="entrada", type=Path, required=True)
    ap.add_argument("--out", "--saida", dest="saida", type=Path, required=True)
    ap.add_argument("--box", "--caixa", dest="caixa", required=True, help="x0,y0,x1,y1 (x1/y1 exclusive); repeat with ; for several")
    ap.add_argument("--radius", "--raio", dest="raio", type=int, default=6)
    ap.add_argument("--colors", "--cores", dest="cores", type=int, default=64)
    a = ap.parse_args()

    orig = a.entrada.read_bytes()
    cs = [orig[p] | orig[p + 1] << 8 for p in blocos_gce(orig)]
    fr = quadros_gif(a.entrada)
    w, h = fr[0].size
    mask = np.zeros((h, w), np.uint8)
    for cx in a.caixa.split(";"):
        x0, y0, x1, y1 = map(int, cx.split(","))
        mask[y0:y1, x0:x1] = 255
    saida = [Image.fromarray(cv2.inpaint(np.asarray(f.convert("RGB")), mask, a.raio, cv2.INPAINT_TELEA)) for f in fr]
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    n = gravar_gif(saida, cs, a.saida, a.cores, 100 * len(cs) / sum(cs))
    print(f"{a.saida}: {len(fr)} frames, {int(mask.sum() / 255)} px erased per frame, {n:,} bytes",
          "OK" if n <= 5242880 else "OVER 5 MB")


if __name__ == "__main__":
    main()
