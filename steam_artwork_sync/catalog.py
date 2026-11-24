"""Visual catalog of the ANIMATED Points Shop items matching a theme.

Reads the public, read-only ILoyaltyRewardsService/QueryRewardItems API (the same one the shop uses) and writes
an HTML page with each item's video, for picking by eye. Does not touch any account.

    python catalog.py --termos moon sword katana --saida catalog.html
"""
import argparse
import html
import json
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.steampowered.com/ILoyaltyRewardsService/QueryRewardItems/v1/"
CDN = "https://shared.fastly.steamstatic.com/community_assets/images/items/{appid}/{arquivo}"
CLASSES = {8: "Special profile", 3: "Profile background", 13: "Mini-profile background", 14: "Avatar frame", 15: "Animated avatar"}


def buscar(termo: str, por_pagina: int = 100, teto: int = 400) -> list[dict]:
    itens, cursor = [], None
    while len(itens) < teto:
        q = {"search_term": termo, "count": por_pagina, "language": "brazilian"}
        if cursor:
            q["cursor"] = cursor
        with urllib.request.urlopen(f"{API}?{urllib.parse.urlencode(q)}", timeout=30) as r:
            resp = json.load(r)["response"]
        itens += resp.get("definitions", [])
        cursor = resp.get("next_cursor")
        if not cursor or not resp.get("definitions"):
            break
    return itens


def midia(item: dict) -> tuple[str, str]:
    """(video, image) of the item; the video is empty when the shop only gives an image."""
    d, appid = item.get("community_item_data") or {}, item["appid"]
    url = lambda f: CDN.format(appid=appid, arquivo=f) if f else ""
    video = d.get("item_movie_webm") or d.get("item_movie_mp4") or d.get("item_movie_webm_small") or ""
    # animated avatar and frame come as gif/png in "small"; "large" is only the static cover
    pequena = d.get("item_image_small") or ""
    imagem = pequena if pequena.endswith((".gif", ".png")) else d.get("item_image_large") or pequena
    return url(video), url(imagem)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--terms", "--termos", dest="termos", nargs="+", required=True)
    ap.add_argument("--classes", nargs="+", type=int, default=list(CLASSES))
    ap.add_argument("--out", "--saida", dest="saida", type=Path, required=True)
    ap.add_argument("--json", type=Path, help="also writes the raw list")
    a = ap.parse_args()

    vistos: dict[int, dict] = {}
    for termo in a.termos:
        for it in buscar(termo):
            d = it.get("community_item_data") or {}
            if it.get("community_item_class") in a.classes and d.get("animated") and it.get("active"):
                vistos.setdefault(it["defid"], it).setdefault("_termos", set()).add(termo)

    cards = []
    for it in sorted(vistos.values(), key=lambda i: (i["community_item_class"], -int(i["point_cost"]))):
        d = it["community_item_data"]
        video, imagem = midia(it)
        media = (f'<video src="{video}" poster="{imagem}" autoplay loop muted playsinline></video>' if video
                 else f'<img src="{imagem}" loading="lazy">')
        cards.append(
            f'<figure data-c="{it["community_item_class"]}">{media}<figcaption><b>{html.escape(d.get("item_title", ""))}</b>'
            f'<span>{CLASSES[it["community_item_class"]]} · {int(it["point_cost"]):,} pts · app {it["appid"]}</span>'
            f'<span>search: {", ".join(sorted(it["_termos"]))}</span>'
            f'<a href="https://store.steampowered.com/points/shop/app/{it["appid"]}" target="_blank">shop</a></figcaption></figure>')

    a.saida.write_text(
        "<!doctype html><meta charset=utf-8><title>Animated catalog</title><style>"
        "body{background:#000;color:#ddd;font:14px system-ui;margin:16px}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}"
        "figure{margin:0;background:#0b0b0b;border:1px solid #222}video,img{width:100%;display:block}"
        "figcaption{padding:8px;display:grid;gap:2px}span{color:#888;font-size:12px}a{color:#c33}</style>"
        f"<h1>{len(cards)} animated items</h1><main>{''.join(cards)}</main>", encoding="utf-8")
    if a.json:
        a.json.write_text(json.dumps([{k: v for k, v in i.items() if k != "_termos"} for i in vistos.values()],
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(cards)} animated items -> {a.saida}")


if __name__ == "__main__":
    main()
