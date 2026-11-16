"""Fetch the CC0 music and sound effects listed in audio_assets.json into build/audio/ (gitignored)."""
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "build" / "audio"


def main():
    man = json.loads((HERE / "audio_assets.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    for e in man["music"] + man["sfx"]:
        dest = OUT / f"{e['id']}.mp3"
        if dest.exists() and dest.stat().st_size > 0:
            continue
        req = urllib.request.Request(e["url"], headers={"User-Agent": "promptimate-fidelity-fetch/1.0"})
        dest.write_bytes(urllib.request.urlopen(req, timeout=60).read())
        print("got", dest.name, e["license"], e["page"])


if __name__ == "__main__":
    main()
