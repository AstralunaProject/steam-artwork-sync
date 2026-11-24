"""Measures WHERE each animated Points Shop background moves: in the central column of the profile or on the sides.

Why: with a game-themed profile the showcases become transparent and the background video shows around the long
art, which is a GIF not synced with it. A background that moves in the CENTER fights the art; what works is a lot
of motion on the SIDES with a dark, still center.

Each video is streamed by ffmpeg (only the first --segundos), reduced to 96x54 grayscale, and the absolute
difference between frames becomes motion energy per column. Geometry measured on the profile page: the content
occupies x 472..1448 of 1920, i.e. columns 24..72 of 96.

    python motion.py --entrada out/dark_backgrounds.json --saida out/motion_backgrounds.json
"""
import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

W, H = 96, 54
C0, C1 = 24, 72  # central column of the profile, in 96 columns


def medir(item: dict, segundos: float, fps: int) -> dict | None:
    url = item.get("webm", "")
    if not url.endswith(".webm"):
        return None
    cmd = ["ffmpeg", "-v", "error", "-t", str(segundos), "-i", url,
           "-vf", f"fps={fps},scale={W}:{H},format=gray", "-f", "rawvideo", "-"]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=90).stdout
    except subprocess.TimeoutExpired:
        return None
    n = len(raw) // (W * H)
    if n < 3:
        return None
    q = np.frombuffer(raw[: n * W * H], np.uint8).reshape(n, H, W).astype(np.float32)
    dif = np.abs(np.diff(q, axis=0)).mean(axis=(0, 1))  # motion energy per column
    luz = q.mean(axis=(0, 1))
    lados = np.concatenate([dif[:C0], dif[C1:]])
    centro = dif[C0:C1]
    return {**item,
            "mov_lados": round(float(lados.mean()), 2),
            "mov_centro": round(float(centro.mean()), 2),
            "luz_centro": round(float(luz[C0:C1].mean()), 1),
            # high = busy sides, still and dark center: the background that leaves the art in peace
            "nota_lateral": round(float(lados.mean() / (centro.mean() + 0.3) * (1 - luz[C0:C1].mean() / 255)), 2)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--segundos", type=float, default=4)
    ap.add_argument("--fps", type=int, default=8)
    ap.add_argument("--threads", type=int, default=6)
    a = ap.parse_args()
    itens = json.loads(a.entrada.read_text(encoding="utf-8"))
    with ThreadPoolExecutor(a.threads) as ex:
        res = [r for r in ex.map(lambda i: medir(i, a.segundos, a.fps), itens) if r]
    res.sort(key=lambda r: -r["nota_lateral"])
    a.saida.write_text(json.dumps(res, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(res)} of {len(itens)} measured -> {a.saida}")


if __name__ == "__main__":
    main()
