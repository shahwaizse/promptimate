"""Renders every camera preset, every lighting preset, the night moods (clear / rain / fog / rain+fog), every held
prop and the cast on a two-person scene and tiles them into labelled gallery images
(demo/shorts_template/build/gallery/*.png). Also a quick regression check for the shot renderer: fails if any
render's validation fails.

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
MOODS = ["", "rain", "fog", "rain_fog"]
PROP_TILES = [("phone", "leo"), ("coffee", "leo"), ("cup", "ava"), ("bag", "leo"), ("briefcase", "leo"),
              ("sword", "ava"), ("book", "leo"), ("flashlight", "ava"), ("umbrella", "leo"), ("stick", "leo"),
              ("baton", "ava")]
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
    moods, propt = [], []
    for w in MOODS:
        label = "night " + (w or "clear")
        if a.only and a.only not in label:
            continue
        t0 = time.time()
        sc = scene(name=f"gal_{tag}_mood_{w or 'clear'}", camera={"preset": "two_shot", "subject": "leo", "target": "ava"},
                   stage="street", lighting={"preset": "night_street", "weather": w, "key_yaw": -40, "rim": 1.0},
                   aspect=a.aspect, quality=a.quality, resolution=a.resolution,
                   furniture=[{"id": "bench", "type": "bench", "at": [0, 1.4], "yaw": 180, "stretch": 1.6},
                              {"id": "lamp", "type": "street_lamp", "at": [1.9, 1.6], "yaw": -90}])
        r = shots.render(sc, keep_frames=True)
        times[label] = round(time.time() - t0, 1)
        moods.append((f"{label}  ({'ok' if r['validation']['passed'] else 'FAIL'})", r))
        if not r["validation"]["passed"]:
            fails.append((label, r["validation"]["failures"]))
        print(label, times[label], "s", r["validation"]["failures"], r["validation"]["warnings"], flush=True)
    for prop, who in PROP_TILES:
        label = "prop " + prop
        if a.only and a.only not in label:
            continue
        t0 = time.time()
        sc = scene(name=f"gal_{tag}_prop_{prop}", camera={"preset": "wide", "subject": who, "distance": 0.62},
                   stage="studio", lighting="studio", aspect=a.aspect, quality=a.quality, resolution=a.resolution)
        for x in sc["actors"]:
            x["props"] = [{"prop": prop, "hand": "right"}] if x["id"] == who else []
        r = shots.render(sc, keep_frames=True)
        times[label] = round(time.time() - t0, 1)
        pv = (r["validation"].get("props") or {}).get(f"{who}.{prop}", {})
        propt.append((f"{prop}  pen {pv.get('maxPenetrationCm', '?')} cm, drift {pv.get('handDriftCm', '?')} cm", r))
        if not r["validation"]["passed"]:
            fails.append((label, r["validation"]["failures"]))
        print(label, times[label], "s", r["validation"]["failures"], r["validation"]["warnings"], flush=True)
    out = HERE / "build" / "gallery"
    if moods:
        print(tile(moods, out / f"night_moods_{tag}.png", 4))
    if propt:
        print(tile(propt, out / f"props_{tag}.png", 6))
    if not a.only or "cast" in a.only:
        names = list(shots.CAST)[:5] + list(shots.CAST_EXTRA)
        n = len(names)
        r = shots.render({"name": "gal_cast", "aspect": "16:9", "stage": "studio", "lighting": "studio", "quality": a.quality,
                          "seconds": 1.0, "camera": {"preset": "explicit", "pos": [0, 1.2, -19.5], "look_at": [0, 0.85, 0], "fov": 30},
                          "actors": [{"id": f"c{i}", "cast": c, "at": [round((i - (n - 1) / 2) * 0.82, 3), 0], "yaw": 180}
                                     for i, c in enumerate(names)]}, keep_frames=True)
        from PIL import Image, ImageDraw
        fr = sorted((Path(r["mp4"]).parent / "frames").glob("f*.*"))
        im = Image.open(fr[-1]).convert("RGB")
        rep_ = json.loads(Path(r["report"]).read_text())["frames"][-1]["actors"]
        canvas = Image.new("RGB", (im.width, im.height + 60), (16, 16, 20))
        canvas.paste(im, (0, 0))
        d = ImageDraw.Draw(canvas)
        for k, (c, ra) in enumerate(zip(names, rep_)):
            x = (ra["bbox"][0] + ra["bbox"][2]) / 2 * im.width
            d.text((x - 3.2 * len(c), im.height + 8 + 18 * (k % 2)), c, fill=(235, 235, 235))
        canvas.save(out / "cast.png")
        print(out / "cast.png", r["validation"]["failures"])
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
