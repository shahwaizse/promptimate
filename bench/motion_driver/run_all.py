"""One-shot Kling motion-control experiment: upload drivers -> submit 3 jobs -> download -> side-by-side sheets.

  python run_all.py [--mode std] [--model kling-v3] [--only a_walk_wave,...] [--url-file urls.json]

Kling's motion-control API takes the character image as base64, but the driver video must be a public URL. By
default each driver.mp4 is uploaded to litterbox.catbox.moe with a 1-hour expiry (harmless gray-mannequin footage
only, never anything private). Pass --url-file {"a_walk_wave": "https://..."} to use your own hosting instead.
One job per test; re-run a test only if it failed for a technical reason.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kling  # noqa: E402

OUT = kling.OUT
TESTS = ["a_walk_wave", "b_sit_head", "c_punch"]


def upload(p: Path) -> str:
    with p.open("rb") as f:
        r = httpx.post("https://litterbox.catbox.moe/resources/internals/api.php",
                       data={"reqtype": "fileupload", "time": "1h"}, files={"fileToUpload": (p.name, f, "video/mp4")},
                       timeout=300)
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"upload failed: {url[:200]}")
    return url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="std"); ap.add_argument("--model", default="kling-v3")
    ap.add_argument("--only", default=""); ap.add_argument("--url-file", default="")
    ap.add_argument("--image", default=str(OUT / "character.png"))
    ap.add_argument("--style", default="dressed", choices=["dressed", "gray"],
                    help="dressed = readable mannequin (recommended), gray = plain gray mannequin")
    a = ap.parse_args()
    tests = [t for t in TESTS if not a.only or t in a.only.split(",")]
    urls = json.loads(Path(a.url_file).read_text()) if a.url_file else {}
    for t in tests:
        name = f"dressed/{t}" if a.style == "dressed" else t
        d = OUT / name
        if (d / "kling.mp4").exists():
            print(t, "already done, skipping (delete kling.mp4 to re-run)"); continue
        url = urls.get(t) or upload(d / "driver.mp4")
        print(t, "driver at", url, flush=True)
        kling.motion(name, Path(a.image), url, a.mode, a.model)
        if (d / "kling.mp4").exists():
            subprocess.run([sys.executable, str(HERE / "compare.py"), str(d)], check=False)


if __name__ == "__main__":
    main()
