"""Side-by-side demo GIF: the artist's regular GIFs vs. the synced pieces, both over the background video.

This is how docs/demo.gif was made. Positions default to a 1920 px window (main at x 495, side at x 1010, y 256).
The raw output is ~13 MB; docs/demo.gif is --scale 0.45 followed by a 64-colour palette pass:

    ffmpeg -i raw.gif -vf "split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" demo.gif
"""
import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from watermark import FONTE, quadros_gif  # reads GIFs with the 0x21 trailer that PIL rejects


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--background", required=True, type=Path, help="background video (.webm)")
    p.add_argument("--regular", nargs=2, required=True, type=Path, metavar=("MAIN", "SIDE"), help="the artist's regular GIFs")
    p.add_argument("--synced", nargs=2, required=True, type=Path, metavar=("MAIN", "SIDE"), help="the longart.py output")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--scale", type=float, default=0.5)
    p.add_argument("--y", type=int, default=256, help="showcase top inside the background")
    p.add_argument("--main-x", type=int, default=495)
    p.add_argument("--side-x", type=int, default=1010)
    p.add_argument("--link", default="github.com/AstralunaProject/steam-artwork-sync", help="watermark along the bottom")
    p.add_argument("--tag", default="@AstralunaProject", help="translucent watermark in the centre")
    p.add_argument("--font", default=FONTE)
    a = p.parse_args()

    Y, xs = a.y, (a.main_x, a.side_x)
    load = lambda gifs: [(x, [np.asarray(f.convert("RGB")) for f in quadros_gif(g)]) for x, g in zip(xs, gifs)]
    synced, regular = load(a.synced), load(a.regular)
    n = len(synced[0][1])
    # width and height must be EVEN: with odd values ffmpeg rounds the yuv crop and the raw frames do not reshape
    cx0, cy0 = a.main_x - 111, Y - 110
    cw = ((a.side_x + 100 + 110) - cx0) // 2 * 2
    ch = (1200 - cy0) // 2 * 2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(a.background), "-vf", f"crop={cw}:{ch}:{cx0}:{cy0}",
                          "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    fundo = np.frombuffer(raw, np.uint8).reshape(-1, ch, cw, 3)
    f_label, f_link, f_tag = (ImageFont.truetype(a.font, s) for s in (30, 15, 30))
    pw, ph = round(cw * a.scale), round(ch * a.scale)
    frames = []
    for i in range(n):
        panels = []
        for pieces, label in ((regular, "regular GIF"), (synced, "steam-artwork-sync")):
            q = fundo[i % len(fundo)].copy()
            for x, fs in pieces:
                f = fs[i * len(fs) // n]
                q[Y - cy0:Y - cy0 + f.shape[0], x - cx0:x - cx0 + f.shape[1]] = f[: ch - (Y - cy0)]
            im = Image.fromarray(q).resize((pw, ph), Image.Resampling.LANCZOS)
            ImageDraw.Draw(im).text((10, 8), label, font=f_label, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
            layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            for txt, fnt, y, alpha in ((a.link, f_link, ph - 30, 200), (a.tag, f_tag, ph // 2 - 18, 70)):
                if txt:
                    w = d.textlength(txt, font=fnt)
                    d.text(((pw - w) / 2, y), txt, font=fnt, fill=(255, 255, 255, alpha), stroke_width=1, stroke_fill=(0, 0, 0, alpha))
            panels.append(Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB"))
        tela = Image.new("RGB", (2 * pw + 10, ph), (0, 0, 0))
        tela.paste(panels[0], (0, 0))
        tela.paste(panels[1], (pw + 10, 0))
        frames.append(tela)
    dur = [30 if i % 3 == 0 else 40 for i in range(n)]  # same 3/4 cs pattern longart.py uses
    frames[0].save(a.out, save_all=True, append_images=frames[1:], duration=dur, loop=0)
    print(a.out, n, "frames", frames[0].size)


if __name__ == "__main__":
    main()
