"""Erases the ANIMATED background of a showcase GIF (spiral, particles) and leaves it black, keeping character and frame.

Criterion, measured on a test GIF: the per-pixel MINIMUM across frames. What passes through (the spiral) vanishes
in the minimum; character and frame stay bright in every frame. The deviation between frames does NOT work: there
the frame glows and the character breathes, so everything "moves".
  pixel bright in the minimum (dilated)  -> original frame
  the rest                               -> the minimum itself (near black; in dark clothing areas, the usual tone)
Delays and the 0x21 trailer preserved (gravar_gif from longart.py).

    python black_background.py --entrada a.gif --saida b.gif [--limiar 22] [--dilatar 2]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
from longart import blocos_gce, gravar_gif  # noqa: E402
from watermark import quadros_gif  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", "--entrada", dest="entrada", type=Path, required=True)
    ap.add_argument("--out", "--saida", dest="saida", type=Path, required=True)
    ap.add_argument("--threshold", "--limiar", dest="limiar", type=int, default=22, help="minimum brightness (0-255) to count as character/frame")
    ap.add_argument("--dilate", "--dilatar", dest="dilatar", type=int, default=2, help="px of margin around what stays")
    ap.add_argument("--colors", "--cores", dest="cores", type=int, default=128)
    ap.add_argument("--mask-png", "--mascara-png", dest="mascara_png", type=Path, help="saves the mask for checking")
    a = ap.parse_args()

    orig = a.entrada.read_bytes()
    cs = [orig[p] | orig[p + 1] << 8 for p in blocos_gce(orig)]
    fr = np.stack([np.asarray(f) for f in quadros_gif(a.entrada)])
    mn = fr.min(0)
    m = Image.fromarray(((mn.max(2) > a.limiar) * 255).astype(np.uint8))
    if a.dilatar:
        m = m.filter(ImageFilter.MaxFilter(2 * a.dilatar + 1))
    if a.mascara_png:
        m.save(a.mascara_png)
    keep = (np.asarray(m) > 0)[None, :, :, None]
    out = np.where(keep, fr, mn[None])
    n = gravar_gif([Image.fromarray(q) for q in out], cs, a.saida, a.cores, 100 * len(cs) / sum(cs))
    print(f"{a.saida}: {len(cs)} frames, {keep.mean():.1%} of the area kept, {n:,} bytes",
          "OK" if n <= 5242880 else "OVER 5 MB")


if __name__ == "__main__":
    main()
