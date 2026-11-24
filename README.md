# steam-artwork-sync

**Animated Steam profile artwork that stays in sync with your animated background.**

Steam plays the profile background (a WebM video) and the showcase artwork (GIFs) independently, so a long art that is meant to "continue" the background drifts out of place after a few seconds. This kit bakes the background *into* the artwork: each GIF carries the exact crop of the video behind it, with frame delays that add up to the video's loop, so the showcase looks like a window cut into the background.

## What it does

| step | tool | notes |
|---|---|---|
| Find animated backgrounds that suit a showcase | `scan_dark.py`, `catalog.py`, `motion.py` | reads the public Points Shop API (read-only); ranks backgrounds by how dark they are and by how much motion sits in the centre vs. the sides |
| Build the synced long art | `longart.py` | crops the video at the showcase position (main 506 px + side 100 px, or a single 630 px featured piece), lays your art on top (alpha or mask), retimes the art to one background loop, keeps every piece under Steam's 5 MB, patches the GIF trailer so Steam shows it full width |
| Touch-ups | `interpolate.py`, `erase_strip.py`, `black_background.py`, `clean_gif.py` | smoother motion within the size budget, inpaint a divider, turn an animated background to black below the video, remove baked-in text |
| Watermark | `watermark.py` | your profile link along the bottom (rotated 90° on side pieces) plus an optional centre tag; frame delays are preserved, so sync is untouched |
| Upload | `upload_artwork.py` | posts to Steam's artwork upload form with the hidden width/height trick (`1000×1`) that makes artwork render at full width |

Measured on a real profile (1920 px wide window): showcase main piece at x 495 / y 256 of the background video, side piece at x 1010. On ultrawide screens Steam scales the background but not the showcase, so the sync only holds for one width; pick the width your visitors use.

## Requirements

- Python 3.11+
- `ffmpeg` and `ffprobe` on PATH
- `pip install -r requirements.txt`

## Quick start

```
python steam_artwork_sync/longart.py --fundo background.webm --arte art.gif --saida out/
python steam_artwork_sync/watermark.py --entrada out/principal.gif --saida out/main_marked.gif --texto "steamcommunity.com/id/<you>"
```

Each tool has `--help`.

## Uploading

`upload_artwork.py` needs the hidden fields of the upload form at `steamcommunity.com/sharedfiles/edititem/767/3/` while you are logged in. Save them to a JSON file and pass it with `--campos`; never put them on the command line. The form token expires after about 24 hours; an upload that comes back with `fileuploadsuccess=15` usually means a stale token, so read the fields again.

## Known limits

- Steam does not start the background and the GIFs at the same moment, so the very first loop can be off; short loops (1–2 s) recover on their own.
- Game profile themes add a frosted-glass panel (`backdrop-filter: blur(20px)`) around showcases; only the artwork itself shows the background sharp.

## Status

Early and private. Tools were built and measured against one profile; expect rough edges.
