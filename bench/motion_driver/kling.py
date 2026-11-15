"""Minimal Kling API client (global endpoint, direct Bearer API key). Never prints or logs the key.

  python kling.py image OUT.png "prompt"                         -> image generation (9:16)
  python kling.py motion NAME IMAGE.png VIDEO_URL [mode] [model] -> motion-control job, polls, downloads
Results and timings land in D:\\unity-text-to-anim\\.cache\\kling_test\\<NAME>\\.
"""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import httpx

BASE = "https://api-singapore.klingai.com"
OUT = Path(r"D:\unity-text-to-anim\.cache\kling_test")
_KEY = Path(r"D:\unity-text-to-anim\.cache\secrets\kling.key").read_text().strip()


def _h():
    return {"Authorization": f"Bearer {_KEY}", "Content-Type": "application/json"}


def _clean(s: str) -> str:
    return s.replace(_KEY, "<KEY>")


def post(path, body):
    r = httpx.post(BASE + path, json=body, headers=_h(), timeout=120)
    j = r.json()
    if r.status_code != 200 or j.get("code") != 0:
        raise RuntimeError(_clean(f"{r.status_code} {r.text[:500]}"))
    return j["data"]


def get(path):
    r = httpx.get(BASE + path, headers=_h(), timeout=60)
    j = r.json()
    if r.status_code != 200 or j.get("code") != 0:
        raise RuntimeError(_clean(f"{r.status_code} {r.text[:500]}"))
    return j["data"]


def poll(path, every=10, limit=3600):
    t0 = time.time()
    while True:
        d = get(path)
        st = d.get("task_status")
        print(f"  [{time.time() - t0:5.0f}s] {st} {d.get('task_status_msg') or ''}", flush=True)
        if st in ("succeed", "failed"):
            return d, time.time() - t0
        if time.time() - t0 > limit:
            raise TimeoutError(path)
        time.sleep(every)


def image(out: Path, prompt: str, neg: str = ""):
    d = post("/v1/images/generations", {"model_name": "kling-v2-1", "prompt": prompt, "negative_prompt": neg,
                                        "n": 1, "aspect_ratio": "9:16"})
    tid = d["task_id"]; print("image task", tid)
    d, dt = poll(f"/v1/images/generations/{tid}", every=5)
    if d["task_status"] != "succeed":
        raise RuntimeError(json.dumps(d)[:500])
    url = d["task_result"]["images"][0]["url"]
    out.write_bytes(httpx.get(url, timeout=120, follow_redirects=True).content)
    (out.with_suffix(".json")).write_text(json.dumps({"task": d, "seconds": dt, "prompt": prompt}, indent=1))
    print("saved", out, f"{dt:.0f}s")


def motion(name: str, img: Path, video_url: str, mode: str = "std", model: str = "kling-v3", prompt: str = ""):
    d_out = OUT / name; d_out.mkdir(parents=True, exist_ok=True)
    body = {"model_name": model, "image_url": base64.b64encode(img.read_bytes()).decode(), "video_url": video_url,
            "character_orientation": "video", "mode": mode, "keep_original_sound": "no"}
    if prompt:
        body["prompt"] = prompt
    t0 = time.time()
    d = post("/v1/videos/motion-control", body)
    tid = d["task_id"]; print(name, "task", tid, flush=True)
    (d_out / "task_id.txt").write_text(tid)
    d, dt = poll(f"/v1/videos/motion-control/{tid}", every=15)
    rec = {"task": d, "latency_s": time.time() - t0, "mode": mode, "model": model, "prompt": prompt}
    (d_out / "kling_result.json").write_text(json.dumps(rec, indent=1))
    if d["task_status"] != "succeed":
        print("FAILED", json.dumps(d)[:800]); return
    vids = d["task_result"]["videos"]
    url = vids[0]["url"]
    (d_out / "kling.mp4").write_bytes(httpx.get(url, timeout=300, follow_redirects=True).content)
    print(name, "done", f"{rec['latency_s']:.0f}s", "duration", vids[0].get("duration"))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "image":
        image(Path(sys.argv[2]), sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    elif cmd == "motion":
        motion(sys.argv[2], Path(sys.argv[3]), sys.argv[4], *(sys.argv[5:]))
    elif cmd == "get":
        print(json.dumps(get(sys.argv[2]), indent=1)[:3000])
