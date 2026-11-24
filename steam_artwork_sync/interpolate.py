"""Doubles the frames of a showcase GIF (motion interpolation), keeping the duration and a closed loop.

Why: some arts look "choppier" than others even at the same frame rate, because the jump between frames is 3-5x
larger (measured mean motion 5.4 against 1-2). More in-between frames = smoother motion.

Closed loop: 3 turns on input, the middle one is kept (the end->start seam also gets its in-between frame;
adjusted because minterpolate eats frames at the ends). Delays are redistributed to add up to the SAME duration as
the original.
Engine: ffmpeg minterpolate (CPU, no queue). WARNING: it halos anime outlines where motion is large; RIFE is
better, but only runs on the GPU. Output has no watermark: run watermark.py afterwards.

    python interpolate.py --entrada x.gif --saida y.gif [--fator 2] [--cores 64]
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from longart import blocos_gce, gravar_gif  # noqa: E402
from watermark import quadros_gif  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", "--entrada", dest="entrada", type=Path, required=True)
    ap.add_argument("--out", "--saida", dest="saida", type=Path, required=True)
    ap.add_argument("--factor", "--fator", dest="fator", type=int, default=2)
    ap.add_argument("--frames", "--quadros", dest="quadros", type=int, help="total frames per loop (overrides --fator)")
    ap.add_argument("--colors", "--cores", dest="cores", type=int, default=64)
    ap.add_argument("--threshold", "--limiar", dest="limiar", type=int, default=0, help="0-255: a difference below this repeats the previous pixel (mild loss, smaller file)")
    a = ap.parse_args()

    orig = a.entrada.read_bytes()
    total = sum(orig[p] | orig[p + 1] << 8 for p in blocos_gce(orig))  # centiseconds
    fr = quadros_gif(a.entrada)
    n = len(fr)
    w, h = fr[0].size
    fps = 100 * n / total
    # 3 turns and keep the MIDDLE one: minterpolate eats frames at the ends (46 -> 88, not 90), and the middle turn
    # has neighbors on both sides, so the end->start seam comes out interpolated like any other pair
    raw = b"".join(f.convert("RGB").tobytes() for f in fr * 3)
    # --quadros M: the loop comes out with M frames (non-integer factor, e.g. 45 -> 68 = 1.5x, fits in 5 MB when 2x does not)
    m = a.quadros or n * a.fator
    out = subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", f"{fps:.6f}", "-i", "-", "-vf",
                          f"minterpolate=fps={100 * m / total:.6f}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], input=raw, capture_output=True, check=True).stdout
    todos = np.frombuffer(out, np.uint8).reshape(-1, h, w, 3)
    novos = [Image.fromarray(q) for q in todos[m: 2 * m]]
    if len(novos) != m:
        raise SystemExit(f"minterpolate returned {len(novos)} frames in the middle turn, expected {m}")
    if a.limiar:
        # same trick as gifsicle --lossy: a small difference (star, gradient) repeats the previous frame, and the
        # GIF transdiff stops rewriting the whole screen (32 colors without this still gave 6.6 MB)
        ant = np.asarray(novos[0], dtype=np.int16)
        lisos = [novos[0]]
        for q in novos[1:]:
            cur = np.asarray(q, dtype=np.int16)
            igual = (np.abs(cur - ant).max(axis=2) < a.limiar)[..., None]
            ant = np.where(igual, ant, cur)
            lisos.append(Image.fromarray(ant.astype(np.uint8)))
        novos = lisos
    # spread the integer centiseconds to close the exact sum (GIF only takes delays in cs)
    m = len(novos)
    cs = [(total * (i + 1)) // m - (total * i) // m for i in range(m)]
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    tam = gravar_gif(novos, cs, a.saida, a.cores, 100 * m / total)
    print(f"{a.saida}: {n} -> {m} frames, {total / 100:.2f} s, {100 * m / total:.1f} fps, {tam:,} bytes",
          "OK" if tam <= 5242880 else "OVER 5 MB")


if __name__ == "__main__":
    main()
