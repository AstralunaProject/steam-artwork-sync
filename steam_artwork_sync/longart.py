"""Builds a showcase long art WITH the animated background baked in, in sync with the video loop.

The usual trick: the showcase GIF carries the slice of the background video that sits behind it, so the art looks
transparent. What goes wrong is TIMING. Here:
  * the crop comes from the Points Shop webm itself, at the measured x/y of the showcase;
  * the art goes on top in "lighten" mode (per-pixel max): the art's black disappears and its white shows over the
    background;
  * the GIF has exactly the frames of the video loop, and the SUM of the delays is the loop rounded to the
    centisecond, spread by Bresenham (GIF only takes delays in centiseconds: 3.336 cs per frame does not exist).
What cannot be controlled: the starting point (each viewer starts whenever their page loads) and the webm pause
when the tab loses focus. So the seam should be hidden by a frame or a dark border in the art.

    python longart.py --fundo background.webm --arte art.png --saida out/v1
"""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence


def quadros(webm: Path) -> tuple[np.ndarray, float]:
    info = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
         "stream=width,height,avg_frame_rate,nb_read_frames", "-of", "json", str(webm)],
        capture_output=True, text=True, check=True).stdout)["streams"][0]
    w, h, n = info["width"], info["height"], int(info["nb_read_frames"])
    num, den = map(int, info["avg_frame_rate"].split("/"))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(webm), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    q = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)[:n]
    return q, n * den / num  # exact loop duration in seconds


def atrasos(n: int, total_cs: int) -> list[int]:
    """n integer delays in centiseconds that add up to total_cs, spread evenly."""
    base, resto = divmod(total_cs, n)
    return [base + (1 if (k * resto) // n != ((k + 1) * resto) // n else 0) for k in range(n)]


def blocos_gce(b: bytes) -> list[int]:
    """Position of each Graphic Control Extension's delay field, walking the GIF structure (not a byte search)."""
    i = 13
    if b[10] & 0x80:
        i += 3 * 2 ** ((b[10] & 7) + 1)
    pos = []
    while i < len(b) - 1 and b[i] != 0x3B:  # the delivered GIF has no trailer (0x3B became 0x21): stop at end of file
        if b[i] == 0x21:
            if b[i + 1] == 0xF9:
                pos.append(i + 4)
            i += 2
            while b[i]:
                i += b[i] + 1
            i += 1
        elif b[i] == 0x2C:
            p = b[i + 9]
            i += 10 + (3 * 2 ** ((p & 7) + 1) if p & 0x80 else 0) + 1
            while b[i]:
                i += b[i] + 1
            i += 1
        else:
            raise ValueError(f"unknown block 0x{b[i]:02x} at {i}")
    return pos


def gravar_gif(frames: list[Image.Image], cs: list[int], destino: Path, cores: int, fps: float) -> int:
    # ffmpeg with transdiff: only what changes between frames is written (506 px spiral: 11.7 MB -> 1.56 MB at 64 colors)
    raw = b"".join(f.convert("RGB").tobytes() for f in frames)
    w, h = frames[0].size
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                    "-r", f"{fps:.6f}", "-i", "-", "-vf",
                    f"split[a][b];[a]palettegen=max_colors={cores}:stats_mode=full[p];[b][p]paletteuse=dither=none:diff_mode=rectangle",
                    "-gifflags", "+transdiff", "-loop", "0", str(destino)], input=raw, check=True)
    b = bytearray(destino.read_bytes())
    pos = blocos_gce(bytes(b))
    if len(pos) != len(cs):
        raise ValueError(f"{destino.name}: {len(pos)} frames in the GIF, {len(cs)} delays")
    for p, c in zip(pos, cs):  # ffmpeg rounds timing its own way; what matters here is the exact loop sum
        b[p], b[p + 1] = c & 0xFF, c >> 8
    if b[-1] == 0x3B:  # without the trailer Steam shows the piece at full width (Steam-Workshop-Art-Maker, gif_utils.py)
        b[-1] = 0x21
    destino.write_bytes(bytes(b))
    return len(b)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--background", "--fundo", dest="fundo", type=Path, required=True)
    ap.add_argument("--art", "--arte", dest="arte", type=Path, required=True, help="art image; covers main piece + gap + side piece")
    ap.add_argument("--out", "--saida", dest="saida", type=Path, required=True)
    ap.add_argument("--x", type=int, default=495, help="x of the main piece in the background video")
    ap.add_argument("--y", type=int, default=256, help="y of the showcase top in the background video")
    ap.add_argument("--piece-width", "--larg", dest="larg", type=int, default=506)
    ap.add_argument("--side-x", "--lat-x", dest="lat_x", type=int, default=1010)
    ap.add_argument("--side-width", "--lat-larg", dest="lat_larg", type=int, default=100)
    ap.add_argument("--step", "--passo", dest="passo", type=int, default=1, help="use 1 of every N frames (2 halves the file size)")
    ap.add_argument("--colors", "--cores", dest="cores", type=int, default=64, help="palette colors; background and B&W art hold up at 32-64")
    ap.add_argument("--black", "--preto", dest="preto", type=int, default=40, help="art without transparency: max channel below this becomes pure black")
    ap.add_argument("--mask", "--mascara", dest="mascara", type=Path, help="character mask (white = opaque), e.g. isnet-anime on the 1st frame")
    ap.add_argument("--frame-light", "--luz-moldura", dest="luz_moldura", type=int, default=70, help="with --mascara: pixels brighter than this are also opaque (the frame)")
    ap.add_argument("--static-outside", "--fora-estatico", dest="fora_estatico", action="store_true",
                    help="with --mascara: outside the character use only what is STILL in the art (removes animated panel streaks)")
    ap.add_argument("--main-only", "--so-principal", dest="so_principal", action="store_true", help="the art has only the 506 px piece; the side piece gets only the background")
    ap.add_argument("--side-art", "--arte-lateral", dest="arte_lateral", type=Path, help="own art for the 100 px side piece (some packs ship both)")
    ap.add_argument("--side-mask", "--mascara-lateral", dest="mascara_lateral", type=Path, help="side piece mask; with no character, only what is bright stays opaque")
    ap.add_argument("--glass", "--vidro", dest="vidro", type=float, default=0, help="blur sigma of the Steam panel's frosted glass (20 with a game theme; 0 = sharp)")
    ap.add_argument("--glass-dark", "--vidro-escuro", dest="vidro_escuro", type=float, default=0.3, help="the black over the glass (the panel is rgba(0,0,0,.3))")
    a = ap.parse_args()

    q, loop_s = quadros(a.fundo)
    if a.vidro > 0:
        # Measured on the profile page (getComputedStyle): with a game theme, EVERY panel has `backdrop-filter:
        # blur(20px)` + background rgba(0,0,0,.3), the showcase included. Around the GIF a frosted strip is left; if
        # the GIF carries the sharp video, the edge shows. Here the GIF background gets the SAME glass: in CSS the
        # blur() radius IS the standard deviation (MDN), and PIL's GaussianBlur also takes the standard deviation.
        # The whole frame, before cropping, so the crop edge does not pull in black.
        from PIL import ImageFilter
        q = np.stack([np.asarray(Image.fromarray(f).filter(ImageFilter.GaussianBlur(a.vidro))) for f in q])
        q = (q.astype(np.float32) * (1 - a.vidro_escuro)).astype(np.uint8)
    vao = a.lat_x - a.x  # the art spans from the start of the main piece to the end of the side piece, gap in between
    total_w = vao + a.lat_larg
    # The art can be ANIMATED (e.g. a pack shipped as a 30-frame x 70 ms = 2.1 s GIF). Different loops do not close
    # together in a GIF of acceptable size, so the art frames are RESAMPLED to fit one turn of the background
    # (2.1 s -> 1.668 s, 26% faster: not noticeable on a blink or an earring).
    def preparar(caminho, larg, mascara):
        """-> (RGBA frames as float, fixed alpha or None). External mask (isnet-anime on the 1st frame) added to what
        is BRIGHT in the frame (frame border and hair strands), with a soft ramp so the strand edges do not alias."""
        src = Image.open(caminho)
        fs = [f.convert("RGBA") for f in ImageSequence.Iterator(src)] or [src.convert("RGBA")]
        esc = larg / fs[0].width
        h = round(fs[0].height * esc)
        arts_ = [np.asarray(f.resize((larg, h), Image.Resampling.LANCZOS)).astype(np.float32) for f in fs]
        if not mascara:
            return arts_, None
        mk = np.asarray(Image.open(mascara).convert("L").resize((larg, h))).astype(np.float32) / 255
        if a.fora_estatico:
            # Case: an animated artwork whose side panels have their own animation (speed lines INSIDE the panels).
            # The frame alpha comes from frame 0, so the bright streaks in it became fixed opaque windows through
            # which the art's own animation blinked in slivers, out of phase with the background. Outside the
            # character only what is STILL in the art is kept (MEDIAN over time: a streak that runs past disappears,
            # and a frame that pulses stays at normal brightness; with the minimum the diamonds came out dimmed): the
            # frame stays, the animated streak goes.
            parado = np.median(np.stack([f[..., :3] for f in arts_]), axis=0)
            for f in arts_:
                f[..., :3] = f[..., :3] * mk[..., None] + parado * (1 - mk[..., None])
            lum0 = parado.mean(axis=2)
        else:
            lum0 = arts_[0][..., :3].mean(axis=2)
        claro = np.clip((lum0 - a.luz_moldura + 30) / 60, 0, 1)
        return arts_, np.maximum(mk, claro)[..., None]

    # Two pieces, two arts (a pack can ship a 506 main and a 100 side). Without --arte-lateral, --arte covers
    # main + gap + side (or only the main, with --so-principal).
    if a.arte_lateral:
        fontes = {"principal": preparar(a.arte, a.larg, a.mascara), "lateral": preparar(a.arte_lateral, a.lat_larg, a.mascara_lateral)}
        recorte = {"principal": 0, "lateral": 0}
    else:
        larg_arte = a.larg if a.so_principal else total_w
        unica = preparar(a.arte, larg_arte, a.mascara)
        fontes = {"principal": unica, "lateral": None if a.so_principal else unica}
        recorte = {"principal": 0, "lateral": vao}
    alt = min([q.shape[1] - a.y] + [f[0][0].shape[0] for f in fontes.values() if f])
    for f in fontes.values():
        if f and f[1] is None and not bool((f[0][0][..., 3] < 254).any()):
            for fr_ in f[0]:  # no alpha or mask: "lighten"; near-black becomes black (else a gray rectangle is left)
                fr_[fr_[..., :3].max(axis=2) < a.preto] = 0

    sel = q[:: a.passo]
    cs = atrasos(len(sel), round(loop_s * 100))
    a.saida.mkdir(parents=True, exist_ok=True)
    pecas = {"principal": (a.x, 0, a.larg), "lateral": (a.lat_x, vao, a.lat_larg)}
    rel = {"loop_video_s": round(loop_s, 4), "quadros_video": int(q.shape[0]), "quadros_gif": len(sel),
           "soma_atrasos_s": sum(cs) / 100, "deriva_ms_por_volta": round((sum(cs) / 100 - loop_s) * 1000, 2),
           "altura": int(alt), "pecas": {}}
    for nome, (vx, _ax, w) in pecas.items():
        fonte, ax = fontes[nome], recorte[nome]
        fr = []
        for k, f in enumerate(sel):
            fundo = f[a.y:a.y + alt, vx:vx + w].astype(np.float32)
            if fonte is None:  # the art only covers the main piece: the side piece gets only the background
                fr.append(Image.fromarray(fundo.clip(0, 255).astype(np.uint8)))
                continue
            arts, alfa_fixo = fonte
            art = arts[k * len(arts) // len(sel)][:alt]  # the art frame that falls at this instant of the background loop
            pa = art[:, ax:ax + w, :3]
            tem_alfa = alfa_fixo is not None or bool((art[..., 3] < 254).any())
            al = (alfa_fixo[:alt] if alfa_fixo is not None else art[..., 3:] / 255)[:, ax:ax + w]
            mix = fundo * (1 - al) + pa * al if tem_alfa else np.maximum(fundo, pa)
            fr.append(Image.fromarray(mix.clip(0, 255).astype(np.uint8)))
        tam = gravar_gif(fr, cs, a.saida / f"{nome}.gif", a.cores, len(sel) / loop_s)
        rel["pecas"][nome] = {"largura": w, "bytes": tam, "cabe_5mb": tam < 5 * 1024 * 1024}
    (a.saida / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rel, ensure_ascii=False))


if __name__ == "__main__":
    main()
