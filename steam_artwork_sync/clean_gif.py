"""Converts a showcase GIF to black and white and, if asked, erases a FIXED TEXT from it (signature, written name).

Usage:
  uv run --no-project --with opencv-python-headless --with numpy python clean_gif.py \
      --entrada <gif> --saida <gif> [--tirar-texto x0,y0,x1,y1] [--contraste 1.25] [--cores 128]

How the text is found: text stays bright in ALL frames; glow, particles and hair move. The mask is the per-pixel
brightness minimum across frames, inside the box, above --limiar, dilated; each frame is then filled (OpenCV Telea
inpaint). Born from a test GIF with a written name on the side piece that had to be removed together with a B&W
conversion.

Output: same frames and rate as the original, ffmpeg palette (palettegen/paletteuse), and the last byte 0x3B -> 0x21
(the Steam trick to show it at full width, same as longart.py). Refuses if over 5 MB.
"""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

LIMITE = 5 * 1024 * 1024


def taxa(gif: Path) -> str:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                        "-of", "csv=p=0", str(gif)], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", required=True, type=Path)
    ap.add_argument("--saida", required=True, type=Path)
    ap.add_argument("--tirar-texto", help="box x0,y0,x1,y1 where the fixed text is")
    ap.add_argument("--limiar", type=int, default=170, help="minimum brightness of the letters")
    ap.add_argument("--sat-max", type=int, default=90, help="maximum saturation of the letters (a blue background exceeds it)")
    ap.add_argument("--freq", type=float, default=0.3, help="fraction of frames in which the pixel is a letter")
    ap.add_argument("--manter-cor", help="ellipse cx,cy,rx,ry that stays in color (the eye)")
    ap.add_argument("--gama", type=float, default=1.35, help="> 1 darkens midtones and preserves highlights")
    ap.add_argument("--piso", type=int, default=30, help="below this becomes black")
    ap.add_argument("--contraste", type=float, default=1.1)
    ap.add_argument("--cores", type=int, default=128)
    ap.add_argument("--cor", action="store_true", help="only removes the text; keeps the colors (no B&W)")
    ap.add_argument("--mascara-png", type=Path, help="saves the mask used, for checking")
    a = ap.parse_args()

    fps = taxa(a.entrada)
    tmp = Path(tempfile.mkdtemp(prefix="clean_gif_"))
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(a.entrada), "-vsync", "0", str(tmp / "q_%04d.png")], check=True)
        quadros = sorted(tmp.glob("q_*.png"))
        imgs = [cv2.imread(str(q)) for q in quadros]
        mask = np.zeros(imgs[0].shape[:2], np.uint8)
        if a.tirar_texto:
            # Measured on a test GIF: the background behind the letters is also bright, and the brightness minimum
            # picked up a 36k px block. What separates them is COLOR: near-white letters (low saturation) over a
            # saturated blue, in every frame.
            x0, y0, x1, y1 = map(int, a.tirar_texto.split(","))
            hsv = np.stack([cv2.cvtColor(i, cv2.COLOR_BGR2HSV) for i in imgs])
            # the text PULSES (brightness comes and goes): "letter" = bright and pale in a fraction of the frames, not in all
            freq = ((hsv[..., 1] < a.sat_max) & (hsv[..., 2] > a.limiar)).mean(0)
            print("fraction in the box, p50/p90/p99:", np.percentile(freq[y0:y1, x0:x1], [50, 90, 99]).round(2))
            letra = freq > a.freq
            mask[y0:y1, x0:x1] = letra[y0:y1, x0:x1].astype(np.uint8) * 255
            mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=2)
            if a.mascara_png:
                cv2.imwrite(str(a.mascara_png), mask)
        cor = None
        if a.manter_cor:
            # the eye stays colored: feathered ellipse x saturated bright pixels (the iris), the rest becomes B&W
            cx, cy, rx, ry = map(int, a.manter_cor.split(","))
            cor = np.zeros(imgs[0].shape[:2], np.float32)
            cv2.ellipse(cor, (cx, cy), (rx, ry), 0, 0, 360, 1.0, -1)
            cor = cv2.GaussianBlur(cor, (0, 0), max(rx, ry) / 4)
        for q, i in zip(quadros, imgs):
            if mask.any():
                i = cv2.inpaint(i, mask, 5, cv2.INPAINT_TELEA)
            if a.cor:  # below the end of the video the showcase sits on black, so it can stay in color
                cv2.imwrite(str(q), i)
                continue
            g = cv2.cvtColor(i, cv2.COLOR_BGR2GRAY).astype(float) / 255
            # curve: gamma > 1 darkens midtones and keeps the top (hair highlights stay at 255); the floor zeroes
            # near-black, as in the approved test
            g = np.clip((g ** a.gama - a.piso / 255) / (1 - a.piso / 255), 0, 1)
            g = np.clip((g - 0.5) * a.contraste + 0.5, 0, 1)
            out = cv2.cvtColor((g * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR).astype(float)
            if cor is not None:
                h = cv2.cvtColor(i, cv2.COLOR_BGR2HSV)
                iris = ((h[..., 1] > 110) & (h[..., 2] > 90)).astype(np.float32)
                peso = (cv2.GaussianBlur(iris, (0, 0), 1.5) * cor)[..., None]
                vivo = cv2.cvtColor(np.dstack([h[..., 0], np.clip(h[..., 1] * 1.15, 0, 255).astype(np.uint8), h[..., 2]]),
                                    cv2.COLOR_HSV2BGR).astype(float)
                out = out * (1 - peso) + vivo * peso
            cv2.imwrite(str(q), out.astype(np.uint8))
        pal = tmp / "pal.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", fps, "-i", str(tmp / "q_%04d.png"),
                        "-vf", f"palettegen=max_colors={a.cores}:stats_mode=diff", str(pal)], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", fps, "-i", str(tmp / "q_%04d.png"), "-i", str(pal),
                        "-lavfi", "paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle", "-gifflags", "+transdiff",
                        "-loop", "0", str(a.saida)], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    b = bytearray(a.saida.read_bytes())
    if b[-1] == 0x3B:
        b[-1] = 0x21
    a.saida.write_bytes(b)
    n = len(b)
    print(f"{a.saida.name}: {len(quadros)} frames at {fps}, {n / 1048576:.2f} MB, mask {int((mask > 0).sum())} px")
    if n > LIMITE:
        raise SystemExit(f"over 5 MB ({n} bytes): rerun with fewer --cores")


if __name__ == "__main__":
    main()
