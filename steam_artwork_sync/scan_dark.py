"""Scans ALL animated items of a Points Shop class and ranks them by how black they are.

The shop's keyword search is imprecise; here the public read-only API is walked completely by cursor, the cover of
each animated item is downloaded and measured: fraction of near-black pixels (luminance < --limiar).
Output: ranked JSON + a numbered contact sheet of the N darkest, for visual curation.

    python scan_dark.py --classe 3 --top 120 --saida out/dark_backgrounds
"""
import argparse
import io
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

API = "https://api.steampowered.com/ILoyaltyRewardsService/QueryRewardItems/v1/"
CDN = "https://shared.fastly.steamstatic.com/community_assets/images/items/{}/{}"


def todos(classe: int) -> list[dict]:
    itens, cursor = [], None
    while True:
        q = {"community_item_classes[0]": classe, "count": 1000, "language": "brazilian"}
        if cursor:
            q["cursor"] = cursor
        with urllib.request.urlopen(f"{API}?{urllib.parse.urlencode(q)}", timeout=60) as r:
            resp = json.load(r)["response"]
        lote = resp.get("definitions", [])
        itens += [i for i in lote if (i.get("community_item_data") or {}).get("animated") and i.get("active")]
        cursor = resp.get("next_cursor")
        if not lote or not cursor:
            return itens


def medir(item: dict, limiar: int) -> dict | None:
    capa = (item.get("community_item_data") or {}).get("item_image_large")
    if not capa:
        return None
    try:
        with urllib.request.urlopen(CDN.format(item["appid"], capa), timeout=30) as r:
            im = Image.open(io.BytesIO(r.read())).convert("L")
    except OSError:  # cover gone from the CDN or a format Pillow cannot open: the item just stays out of the ranking
        return None
    im.thumbnail((192, 108))
    px = list(im.getdata())
    return {"defid": item["defid"], "appid": item["appid"], "titulo": item["community_item_data"].get("item_title", ""),
            "pontos": int(item["point_cost"]), "capa": CDN.format(item["appid"], capa),
            "webm": CDN.format(item["appid"], item["community_item_data"].get("item_movie_webm", "")),
            "preto": round(sum(p < limiar for p in px) / len(px), 3), "media": round(sum(px) / len(px), 1)}


def folha(ranking: list[dict], destino: Path) -> None:
    w, h, cols = 320, 180, 6
    linhas = (len(ranking) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, linhas * (h + 18)), "black")
    dr = ImageDraw.Draw(sheet)
    for n, it in enumerate(ranking):
        try:
            with urllib.request.urlopen(it["capa"], timeout=30) as r:
                im = Image.open(io.BytesIO(r.read())).convert("RGB")
        except OSError:
            continue
        im.thumbnail((w, h))
        x, y = (n % cols) * w, (n // cols) * (h + 18)
        sheet.paste(im, (x, y))
        dr.text((x + 3, y + h + 2), f"{n} {it['preto']:.0%} {it['titulo'][:36]}", fill="white")
    sheet.save(destino, quality=85)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--class", "--classe", dest="classe", type=int, default=3, help="3 background, 13 mini-profile, 14 frame, 15 avatar")
    ap.add_argument("--top", type=int, default=120)
    ap.add_argument("--threshold", "--limiar", dest="limiar", type=int, default=28, help="luminance 0-255 below which a pixel counts as black")
    ap.add_argument("--out", "--saida", dest="saida", type=Path, required=True, help="prefix: writes <prefix>.json and <prefix>.jpg")
    a = ap.parse_args()

    itens = todos(a.classe)
    with ThreadPoolExecutor(16) as ex:
        medidos = [m for m in ex.map(lambda i: medir(i, a.limiar), itens) if m]
    medidos.sort(key=lambda m: -m["preto"])
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    a.saida.with_suffix(".json").write_text(json.dumps(medidos, ensure_ascii=False, indent=1), encoding="utf-8")
    folha(medidos[: a.top], a.saida.with_suffix(".jpg"))
    print(f"{len(itens)} animated in class {a.classe}; {len(medidos)} measured; sheet of the {a.top} blackest -> {a.saida}.jpg")


if __name__ == "__main__":
    main()
