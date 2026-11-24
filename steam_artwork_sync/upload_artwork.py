"""Uploads a GIF/PNG as Steam Artwork: posts the multipart straight to depot-ingest, no <input type=file> needed.

Why it exists: a logged-in browser session often cannot put a local file into the page's file input (Steam's CSP
blocks fetches to 127.0.0.1 and popups are not allowed), and driving a browser extension depends on it being open.
The `sharedfiles/edititem/767/3/` form is SELF-SIGNED: `wg`/`wg_hmac`/`token` (a JWT tied to the sender's IP)
authorize the upload without a cookie. depot-ingest answers 302 to `filedetails/?...`; that last step uses the
login, so open the returned URL in the logged-in browser.

Usage:
  1. in the browser, on edititem/767/3/, save the hidden inputs of the `ugcupload` form into a JSON file (a file,
     never argv: the token leaks in the process list). The token lasts ~1 day and is single-use per page: grab a
     new one for each upload;
  2. python upload_artwork.py --campos fields.json --arquivo out/x.gif --titulo "..." [--longa]
     --longa writes image_width=1000 and image_height=1 (the long art trick).
Prints the status and the Location of the 302.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def multipart(campos: dict, arquivo: Path):
    b = uuid.uuid4().hex
    partes = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
              for k, v in campos.items()]
    tipo = arquivo.suffix.lstrip(".").lower().replace("jpg", "jpeg")
    partes.append(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{arquivo.name}"\r\n'
                  f"Content-Type: image/{tipo}\r\n\r\n".encode() + arquivo.read_bytes() + b"\r\n")
    partes.append(f"--{b}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={b}"


class SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fields", "--campos", dest="campos", required=True, help="JSON with the form's hidden inputs")
    ap.add_argument("--file", "--arquivo", dest="arquivo", required=True)
    ap.add_argument("--title", "--titulo", dest="titulo", required=True)
    ap.add_argument("--long", "--longa", dest="longa", action="store_true", help="image_width=1000, image_height=1")
    ap.add_argument("--visibility", "--visibilidade", dest="visibilidade", default="0", help="0 public, 1 friends, 2 private, 3 unlisted")
    a = ap.parse_args()

    arq = Path(a.arquivo)
    if arq.stat().st_size > 5242880:
        raise SystemExit(f"{arq} is over 5 MB")
    c = json.loads(Path(a.campos).read_text(encoding="utf8"))
    acao = c.pop("_action", "https://depot-ingest.discovery.steamserver.net/ugcupload/23")
    c["cloudfilenameprefix"] = f"{int(time.time())}_new_"
    if a.longa:
        c["image_width"], c["image_height"] = "1000", "1"
    c.update(title=a.titulo, description="", visibility=a.visibilidade, agree_terms="on")
    corpo, ctype = multipart(c, arq)
    req = urllib.request.Request(acao, data=corpo, method="POST", headers={
        "Content-Type": ctype, "User-Agent": "steam-artwork-sync/0.1",
        "Origin": "https://steamcommunity.com", "Referer": "https://steamcommunity.com/"})
    try:
        r = urllib.request.build_opener(SemRedirecionar).open(req, timeout=180)
        print("status", r.status, r.read(400))
    except urllib.error.HTTPError as e:
        print("status", e.code, "Location:", e.headers.get("Location"), e.read(400) if e.code >= 400 else "")


if __name__ == "__main__":
    main()
