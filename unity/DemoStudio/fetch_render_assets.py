"""Download the redistributable starter cast and stage kits for the shot renderer (render_shot).

    .venv\\Scripts\\python.exe unity\\DemoStudio\\fetch_render_assets.py [--force] [--only id,id]

Every asset is CC0 (public domain) and listed with its source and license in render_assets.json. The files land in
unity/DemoStudio/Assets/ThirdParty/ (gitignored), the same way setup downloads model weights into models/: nothing
third-party is committed. A LICENSES.md with the attribution for each pack is written next to them.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import re
import shutil
import sys
import time
import urllib.request
import zipfile
from http.cookiejar import CookieJar
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "render_assets.json"
DEST = HERE / "Assets" / "ThirdParty"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PromptimateAssetFetch/1.0"


def _opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def _get(op, url: str, referer: str | None = None, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Referer": referer, "Origin": "https://kenney.nl"}
                                                                    if referer else {})})
    last = None
    for attempt in range(3):
        try:
            with op.open(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # flaky CDN: retry a couple of times
            last = e
            time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"download failed: {url}: {last}")


def _kenney_zip(op, page: str) -> bytes:
    """Kenney serves each pack through a short-lived signed link requested from the asset page (what the page's
    'Continue without donating' button does)."""
    html = _get(op, page).decode("utf-8", "replace")
    m = re.search(r"data-download-id='([0-9a-f]+)'", html)
    if not m:
        raise RuntimeError(f"no download id on {page}")
    info = json.loads(_get(op, f"https://kenney.nl/download-link/{m.group(1)}", referer=page))
    if not info.get("url"):
        raise RuntimeError(f"kenney refused the download link for {page}: {info}")
    return _get(op, info["url"], referer=page, timeout=600)


def _extract(data: bytes, dest: Path, keep: list[str], strip: str = "") -> int:
    n = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir() or not any(fnmatch.fnmatch(name, k) for k in keep):
                continue
            rel = name[len(strip):] if strip and name.startswith(strip) else name
            out = (dest / rel).resolve()
            if dest.resolve() not in out.parents:  # zip-slip guard
                raise RuntimeError(f"unsafe path in archive: {name}")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(info))
            n += 1
    return n


def fetch(force: bool = False, only: set[str] | None = None, log=print) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    DEST.mkdir(parents=True, exist_ok=True)
    op = _opener()
    done = {}
    for p in manifest["packs"]:
        if only and p["id"] not in only:
            continue
        dest = DEST / p["dest"]
        marker = (dest if p["kind"] == "zip-kenney" else dest.parent) / f".{p['id']}.ok"
        if marker.exists() and not force:
            done[p["id"]] = "cached"
            continue
        t0 = time.time()
        if p["kind"] == "zip-kenney":
            data = _kenney_zip(op, p["page"])
            if dest.exists():
                shutil.rmtree(dest)
            n = _extract(data, dest, p["keep"], p.get("strip", ""))
            info = f"{n} files"
        elif p["kind"] == "file":
            data = _get(op, p["url"])
            want = p.get("sha256")
            got = hashlib.sha256(data).hexdigest()
            if want and want != got:
                raise RuntimeError(f"{p['id']}: sha256 mismatch (got {got}, manifest {want})")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            info = f"{len(data) // 1024} KB"
        else:
            raise RuntimeError(f"unknown kind {p['kind']}")
        marker.write_text(json.dumps({"id": p["id"], "fetched": time.strftime("%Y-%m-%d %H:%M:%S")}))
        done[p["id"]] = info
        log(f"  {p['id']}: {info} ({time.time() - t0:.0f}s)")
    _write_licenses(manifest)
    return done


def _write_licenses(manifest: dict) -> None:
    lines = ["# Third-party render assets", "",
             "Downloaded by `fetch_render_assets.py` from the sources below. All are CC0 1.0 (public domain): free",
             "for commercial use, redistribution and modification; credit is appreciated but not required.", "",
             "| Asset | Author | License | Source |", "|---|---|---|---|"]
    for p in manifest["packs"]:
        lines.append(f"| {p['title']} | {p['author']} | {p['license']} | {p['page']} |")
    (DEST / "LICENSES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def missing() -> list[str]:
    """Pack ids that have not been downloaded yet."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out = []
    for p in manifest["packs"]:
        dest = DEST / p["dest"]
        marker = (dest if p["kind"] == "zip-kenney" else dest.parent) / f".{p['id']}.ok"
        if not marker.exists():
            out.append(p["id"])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="download again even if present")
    ap.add_argument("--only", default="", help="comma-separated pack ids")
    a = ap.parse_args()
    print(f"fetching render assets into {DEST}")
    res = fetch(a.force, set(filter(None, a.only.split(","))) or None)
    print(json.dumps(res, indent=1))
    sys.exit(0)
