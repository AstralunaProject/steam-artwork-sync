"""Puts a watermark (e.g. a profile link) on a showcase GIF without touching its timing.

Meant to be discreet; on side pieces it is rotated 90 degrees and fainter.
Each frame's delay is copied from the original GIF (a long art matches the background loop: re-encoding without
that breaks the sync), and the trailer goes back as 0x21 (full width on Steam), through the same `gravar_gif` as
longart.py.

    python watermark.py --texto "example.com/me" --entrada x.gif --saida y.gif               # main piece: text at the bottom, centered
    python watermark.py --texto "example.com/me" --entrada lat.gif --saida y.gif --vertical  # side piece: text rotated 90 deg, in the middle
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from longart import blocos_gce, gravar_gif  # noqa: E402

TEXTO = ""
FONTE = "C:/Windows/Fonts/bahnschrift.ttf"


def quadros_gif(gif: Path) -> list[Image.Image]:
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "json",
                                      str(gif)], capture_output=True, text=True, check=True).stdout)["streams"][0]
    w, h = info["width"], info["height"]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(gif), "-vsync", "0", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return [Image.fromarray(q) for q in np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)]


def camada(w: int, h: int, tam: int, opac: float, vertical: bool, margem: int, centro_x: int | None = None) -> Image.Image:
    fonte = ImageFont.truetype(FONTE, tam)
    x0, y0, x1, y1 = fonte.getbbox(TEXTO)
    txt = Image.new("RGBA", (x1 - x0 + 4, y1 - y0 + 4), (0, 0, 0, 0))
    ImageDraw.Draw(txt).text((2 - x0, 2 - y0), TEXTO, font=fonte, fill=(255, 255, 255, round(255 * opac)),
                             stroke_width=1, stroke_fill=(0, 0, 0, round(255 * opac)))  # outline: stays readable on a light background
    if vertical:
        txt = txt.rotate(90, expand=True)  # reads bottom to top, like a book spine
        cx = w // 2 if centro_x is None else centro_x
        pos = (cx - txt.width // 2, (h - txt.height) // 2)
    else:
        pos = ((w - txt.width) // 2, h - txt.height - margem)
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    c.alpha_composite(txt, pos)
    return c


def centro(w: int, h: int, texto: str, tam: int, opac: float) -> Image.Image:
    """Second mark, in the middle of the piece, at lower opacity (e.g. a handle)."""
    fonte = ImageFont.truetype(FONTE, tam)
    x0, y0, x1, y1 = fonte.getbbox(texto)
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(c).text(((w - (x1 - x0)) // 2 - x0, (h - (y1 - y0)) // 2 - y0), texto, font=fonte,
                           fill=(255, 255, 255, round(255 * opac)), stroke_width=1,
                           stroke_fill=(0, 0, 0, round(255 * opac)))  # outline: readable over white hair too
    return c


def main() -> None:
    global TEXTO, FONTE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", "--entrada", dest="entrada", type=Path, required=True)
    ap.add_argument("--out", "--saida", dest="saida", type=Path, required=True)
    ap.add_argument("--text", "--texto", dest="texto", required=True, help="watermark text, e.g. a profile link")
    ap.add_argument("--font", "--fonte", dest="fonte", default=FONTE, help="path to a TrueType font file")
    ap.add_argument("--vertical", action="store_true", help="side piece: text rotated 90 degrees")
    ap.add_argument("--size", "--tam", dest="tam", type=int, default=13)
    ap.add_argument("--opacity", "--opacidade", dest="opacidade", type=float, help="default 0.35 on the main piece and 0.22 on the side piece")
    ap.add_argument("--margin", "--margem", dest="margem", type=int, default=10, help="distance from the bottom edge (main piece)")
    ap.add_argument("--colors", "--cores", dest="cores", type=int, default=64)
    ap.add_argument("--center", "--meio", dest="meio", help="extra text at the center of the piece, e.g. @handle")
    ap.add_argument("--center-size", "--meio-tam", dest="meio_tam", type=int, default=22)
    ap.add_argument("--center-opacity", "--meio-opacidade", dest="meio_opacidade", type=float, default=0.12)
    ap.add_argument("--center-x", "--centro-x", dest="centro_x", type=int, help="with --vertical: x of the text middle (e.g. a black column)")
    ap.add_argument("--height", "--altura", dest="altura", type=int, help="crops the piece to this height (removes what is below)")
    ap.add_argument("--width", "--largura", dest="largura", type=int, help="wider canvas, art flush left, rest black (single art: 630)")
    a = ap.parse_args()
    TEXTO, FONTE = a.texto, a.fonte

    orig = a.entrada.read_bytes()
    cs = [orig[p] | orig[p + 1] << 8 for p in blocos_gce(orig)]
    fr = quadros_gif(a.entrada)
    if len(fr) != len(cs):
        raise SystemExit(f"{len(fr)} frames read, {len(cs)} delays in the GIF")
    if a.altura:  # e.g. a caption strip lives in the last 140 px; cropping the pair at 768 removes it entirely
        fr = [f.crop((0, 0, f.width, a.altura)) for f in fr]
    largura_arte = None
    if a.largura:
        largura_arte = fr[0].width
        # A single art is CENTERED (x 557 to 1920) and a pair of arts is flush left (x 495): on a 630 canvas with
        # the art on the left, the centered piece starts at 495 and the bars of both line up
        fundo = Image.new("RGB", (a.largura, fr[0].height), (0, 0, 0))
        fr = [(lambda c, f: (c.paste(f, (0, 0)), c)[1])(fundo.copy(), f.convert("RGB")) for f in fr]
    opac = a.opacidade if a.opacidade is not None else (0.22 if a.vertical else 0.35)
    # the marks are measured on the ART (original width), not the widened canvas, and sit flush left along with it
    aw = largura_arte or fr[0].width
    marca_arte = camada(aw, fr[0].height, a.tam, opac, a.vertical, a.margem, a.centro_x)
    if a.meio:
        marca_arte.alpha_composite(centro(aw, fr[0].height, a.meio, a.meio_tam, a.meio_opacidade))
    marca = Image.new("RGBA", fr[0].size, (0, 0, 0, 0))
    marca.alpha_composite(marca_arte, (0, 0))
    saida = [Image.alpha_composite(f.convert("RGBA"), marca).convert("RGB") for f in fr]
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    n = gravar_gif(saida, cs, a.saida, a.cores, 100 * len(cs) / sum(cs))
    print(f"{a.saida}: {len(fr)} frames, {sum(cs) / 100:.2f} s, {n:,} bytes", "OK" if n <= 5242880 else "OVER 5 MB")


if __name__ == "__main__":
    main()
