"""Renders every camera preset and every lighting preset on one two-person scene and tiles them into labelled
gallery images (demo/shorts_template/build/gallery/*.png). Also a quick regression check for the shot renderer:
fails if any render's validation fails.

    .venv\\Scripts\\python.exe demo\\shorts_template\\gallery.py [--aspect 9:16] [--quality draft]
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "mcp_server"))
import shots  # noqa: E402

M = json.loads((HERE / "story" / "motions.json").read_text())


def scene(**kw):
    return {"actors": [{"id": "leo", "cast": "adventurer", "at": [-0.85, 0], "yaw": 90, "motion": M["leo_listen"]},
                       {"id": "ava", "cast": "punk", "at": [0.85, 0], "yaw": -90, "motion": M["ava_points"]}],
            "seconds": 2.5, **kw}


CAMS = [("wide", {"preset": "wide"}), ("medium", {"preset": "medium", "subject": "ava"}),
        ("close_up", {"preset": "close_up", "subject": "leo"}),
        ("over_shoulder", {"preset": "over_shoulder", "subject": "leo", "target": "ava"}),
        ("follow", {"preset": "follow", "subject": "ava"}), ("push_in", {"preset": "push_in", "subject": "ava"}),
        ("orbit", {"preset": "orbit"}), ("low_angle", {"preset": "low_angle", "subject": "ava"}),
        ("top_down", {"preset": "top_down"}), ("two_shot", {"preset": "two_shot", "subject": "leo", "target": "ava"})]
LIGHTS = [("day", "park"), ("golden_hour", "street"), ("night_street", "street"), ("interior_warm", "interior"),
          ("studio", "studio")]


def tile(items, out: Path, cols: int):
    from PIL import Image, ImageDraw
    ims = []
    for label, res in items:
        d = Path(res["mp4"]).parent / "frames"
        fr = sorted(d.glob("f*.*"))
        im = Image.open(fr[len(fr) // 2]).convert("RGB")
        ims.append((label, im))
    w = 360
    h = round(ims[0][1].height * w / ims[0][1].width)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w + (cols - 1) * 6, rows * (h + 30)), (16, 16, 20))
    for i, (label, im) in enumerate(ims):
        x, y = (i % cols) * (w + 6), (i // cols) * (h + 30)
        sheet.paste(im.resize((w, h), Image.LANCZOS), (x, y))
        ImageDraw.Draw(sheet).text((x + 6, y + h + 8), label, fill=(235, 235, 235))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--quality", default="draft")
    ap.add_argument("--resolution", default="720p")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    tag = a.aspect.replace(":", "x")
    cams, lights, fails, times = [], [], [], {}
    for label, cam in CAMS:
        if a.only and a.only not in label:
            continue
        t0 = time.time()
        r = shots.render(scene(name=f"gal_{tag}_cam_{label}", camera=cam, stage="street", lighting="golden_hour",
                               aspect=a.aspect, quality=a.quality, resolution=a.resolution, key_yaw=-60), keep_frames=True)
        times[label] = round(time.time() - t0, 1)
        cams.append((f"{label}  ({'ok' if r['validation']['passed'] else 'FAIL'})", r))
        if not r["validation"]["passed"]:
            fails.append((label, r["validation"]["failures"]))
        print(label, times[label], "s", r["validation"]["failures"], r["validation"]["warnings"], flush=True)
    for label, st in LIGHTS:
        if a.only and a.only not in label:
            continue
        t0 = time.time()
        r = shots.render(scene(name=f"gal_{tag}_light_{label}", camera={"preset": "two_shot", "subject": "leo", "target": "ava"},
                               stage=st, lighting=label, aspect=a.aspect, quality=a.quality, resolution=a.resolution), keep_frames=True)
        times[label] = round(time.time() - t0, 1)
        lights.append((f"{label} / {st}  ({'ok' if r['validation']['passed'] else 'FAIL'})", r))
        if not r["validation"]["passed"]:
            fails.append((label, r["validation"]["failures"]))
        print(label, times[label], "s", r["validation"]["failures"], r["validation"]["warnings"], flush=True)
    out = HERE / "build" / "gallery"
    if cams:
        print(tile(cams, out / f"cameras_{tag}.png", 5))
    if lights:
        print(tile(lights, out / f"lighting_{tag}.png", 5))
    (out / f"times_{tag}.json").write_text(json.dumps(times, indent=1))
    if fails:
        print("FAILED:", json.dumps(fails, indent=1))
        sys.exit(1)


if __name__ == "__main__":
    main()
