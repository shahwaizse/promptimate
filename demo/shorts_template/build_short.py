"""Shorts template: shot list + voiceover timing -> a HyperFrames project for a vertical short (or a 16:9 animatic).

    .venv\\Scripts\\python.exe demo\\shorts_template\\build_short.py <short.json> [--render]

<short.json> (paths relative to the JSON file or absolute):
{
  "name": "wrong_turn",
  "size": [1080, 1920], "fps": 30,
  "title": "He asked for directions.",            # hook line on frame 0 (top band), optional
  "shots": [ {"id": "s1", "video": "renders/s1.mp4", "duration": 3.0, "media_start": 0.0, "punch": 1.04}, ... ],
  "voiceover": [ {"id": "vo1", "audio": "vo/vo1.wav", "start": 0.3, "text": "Leo had been walking for an hour.",
                  "words": [{"text": "Leo", "start": 0.0, "end": 0.3}, ...]} ],   # words optional, relative to line
  "music": {"src": null, "volume": 0.25},           # null = silent placeholder track (swap the file later)
  "sfx_on_cuts": true,
  "end_card": {"text": "Made with Promptimate", "duration": 1.6}
}
Shots play back to back with hard cuts. Captions are built from the voiceover words (given, or spread over each line
by syllable estimate), 2-4 words per group, the active word highlighted, inside the 9:16 safe band (above the
platform UI at 1330 px). The output folder is a normal HyperFrames project: preview/edit it in the HyperFrames desktop
app or Studio (`npx hyperframes preview`), render with `npx hyperframes render`.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HF = "hyperframes@0.9.45"
SFX_DIR = Path.home() / ".claude" / "skills" / "media-use" / "audio" / "assets" / "sfx"


def ffmpeg() -> str:
    for c in (os.environ.get("FFMPEG"), r"D:\tools\ffmpeg\bin\ffmpeg.exe", shutil.which("ffmpeg")):
        if c and Path(c).exists():
            return c
    raise SystemExit("ffmpeg not found")


def media_seconds(p: Path) -> float:
    probe = Path(ffmpeg()).with_name("ffprobe.exe")
    r = subprocess.run([str(probe) if probe.exists() else "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def speech_span(p: Path) -> tuple[float, float]:
    """(first, last) second with speech in an audio file (ffmpeg silencedetect)."""
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(p), "-af", "silencedetect=noise=-38dB:d=0.12", "-f", "null", "-"],
                       capture_output=True, text=True)
    dur = media_seconds(p)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    first = ends[0] if starts and starts[0] < 0.05 and ends else 0.0
    last = starts[-1] if starts and (not ends or starts[-1] > ends[-1]) else dur
    return first, max(first + 0.2, last)


def syllables(w: str) -> int:
    w = re.sub(r"[^a-z]", "", w.lower())
    return max(1, len(re.findall(r"[aeiouy]+", w)) - (1 if w.endswith("e") and len(w) > 3 else 0))


def estimate_words(text: str, t0: float, t1: float) -> list[dict]:
    words = text.split()
    weights = [syllables(w) + (0.6 if re.search(r"[,.;:!?]$", w) else 0) for w in words]
    total = sum(weights)
    out, t = [], t0
    for w, k in zip(words, weights):
        d = (t1 - t0) * k / total
        out.append({"text": w, "start": round(t, 3), "end": round(t + d * 0.92, 3)})
        t += d
    return out


def caption_groups(words: list[dict], max_words: int = 3) -> list[list[dict]]:
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        gap = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 9
        if len(cur) >= max_words or re.search(r"[.!?,;:]$", w["text"]) or gap > 0.15:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def build(spec_path: Path, out: Path | None = None) -> Path:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    base = spec_path.parent
    rel = lambda p: (Path(p) if Path(p).is_absolute() else base / p)  # noqa: E731
    name = spec.get("name", spec_path.stem)
    W, H = spec.get("size", [1080, 1920])
    vertical = H > W
    out = out or HERE / "build" / name
    if out.exists():  # clear the contents (the folder itself may be held open by a shell or Studio on Windows)
        for child in out.iterdir():
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
    (out / "compositions").mkdir(parents=True)
    (out / "assets" / "shots").mkdir(parents=True)
    (out / "assets" / "audio").mkdir(parents=True)

    # ---- shots (hard cuts, back to back) ----
    shots_html, t, cuts = [], 0.0, []
    for i, s in enumerate(spec["shots"]):
        src = rel(s["video"])
        dst = out / "assets" / "shots" / f"{s['id']}.mp4"
        shutil.copyfile(src, dst)
        avail = media_seconds(dst) - float(s.get("media_start", 0))
        d = round(min(float(s.get("duration", avail)), avail), 3)
        s["_start"], s["_dur"] = round(t, 3), d
        shots_html.append(
            f'      <video id="shot-{s["id"]}" class="clip shot" src="assets/shots/{s["id"]}.mp4" muted playsinline\n'
            f'        data-start="{t:.3f}" data-duration="{d:.3f}" data-media-start="{float(s.get("media_start", 0)):.3f}"'
            f' data-track-index="1" style="z-index:{i + 1}"></video>')
        if i:
            cuts.append(t)
        t += d
    total = round(t, 3)
    end = spec.get("end_card")
    end_dur = float(end.get("duration", 1.6)) if end else 0.0
    total_all = round(total + end_dur, 3)

    # ---- voiceover + words ----
    audio_html, all_words = [], []
    for k, line in enumerate(spec.get("voiceover", [])):
        lid = line.get("id", f"vo{k + 1}")
        src = rel(line["audio"])
        dst = out / "assets" / "audio" / f"{lid}{src.suffix}"
        shutil.copyfile(src, dst)
        st = float(line["start"])
        dur = media_seconds(dst)
        audio_html.append(f'      <audio id="{lid}" class="clip" src="assets/audio/{dst.name}" data-start="{st:.3f}" '
                          f'data-duration="{dur:.3f}" data-track-index="5" data-volume="1"></audio>')
        words = line.get("words")
        if not words:
            a, b = speech_span(dst)
            words = estimate_words(line["text"], a, b)
        all_words += [{"text": w["text"], "start": round(st + w["start"], 3), "end": round(st + w["end"], 3)} for w in words]

    # ---- music (placeholder slot) and cut whooshes ----
    music = spec.get("music") or {}
    if music.get("src"):
        msrc = rel(music["src"])
        mname = "music" + msrc.suffix
        shutil.copyfile(msrc, out / "assets" / "audio" / mname)
    else:
        mname = "music_placeholder.wav"
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                        "-t", f"{total_all:.3f}", str(out / "assets" / "audio" / mname)], check=True)
    audio_html.append(f'      <!-- Music: {"placeholder (silence) - drop a track in as assets/audio/" + mname + " or point src at it" if not music.get("src") else "bed"};'
                      f' ducked under the voiceover by its volume. -->\n'
                      f'      <audio id="music" class="clip" src="assets/audio/{mname}" data-start="0" data-duration="{total_all:.3f}" '
                      f'data-track-index="8" data-volume="{float(music.get("volume", 0.25))}" data-fade-out="1.2"></audio>')
    if spec.get("sfx_on_cuts", True) and (SFX_DIR / "whoosh-short.mp3").exists():
        shutil.copyfile(SFX_DIR / "whoosh-short.mp3", out / "assets" / "audio" / "whoosh-short.mp3")
        for j, c in enumerate(cuts):
            audio_html.append(f'      <audio id="sfx-cut{j + 1}" class="clip" src="assets/audio/whoosh-short.mp3" '
                              f'data-start="{max(0, c - 0.22):.3f}" data-duration="0.57" data-track-index="{9 + j % 2}" data-volume="0.16"></audio>')

    # ---- captions composition ----
    groups = caption_groups(all_words)
    cap_items, cap_js = [], []
    for g, ws in enumerate(groups):
        gs = max(0.1, ws[0]["start"] - 0.06)
        ge = (groups[g + 1][0]["start"] - 0.06) if g + 1 < len(groups) and groups[g + 1][0]["start"] - ws[-1]["end"] < 0.5 else ws[-1]["end"] + 0.25
        spans = " ".join(f'<span class="w" id="cw{g}-{i}">{html.escape(w["text"])}</span>' for i, w in enumerate(ws))
        cap_items.append(f'    <div id="cap{g}" class="clip cap" data-start="{gs:.3f}" data-duration="{max(0.2, ge - gs):.3f}">'
                         f'<div class="cap-in" id="capin{g}">{spans}</div></div>')
        cap_js.append(f'    tl.fromTo("#capin{g}", {{scale: 0.86, opacity: 0}}, {{scale: 1, opacity: 1, duration: 0.14, ease: "back.out(2.2)"}}, {gs:.3f});')
        for i, w in enumerate(ws):
            cap_js.append(f'    tl.fromTo("#cw{g}-{i}", {{color: "#ffffff"}}, {{color: "#ffd84a", duration: 0.06}}, {w["start"]:.3f});')
            cap_js.append(f'    tl.to("#cw{g}-{i}", {{color: "#ffffff", duration: 0.08}}, {max(w["end"], w["start"] + 0.08):.3f});')
    cap_bottom = 800 if vertical else 110  # 9:16: text ends ~1120 px, clear of every platform's bottom UI
    captions = f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; }}
    .cap {{ position: absolute; left: {60 if vertical else 0}px; right: {170 if vertical else 0}px; bottom: {cap_bottom}px; text-align: center; overflow: visible; }}
    .cap-in {{ display: inline-block; padding: 0 60px; font-family: "Montserrat", sans-serif; font-weight: 900;
              font-size: {84 if vertical else 64}px; line-height: 1.08; color: #fff; text-transform: uppercase;
              text-shadow: 0 4px 0 rgba(0,0,0,.55), 0 0 24px rgba(0,0,0,.45); -webkit-text-stroke: 3px rgba(0,0,0,.65);
              paint-order: stroke fill; max-width: {W - 260 if vertical else W - 160}px; }}
    .w {{ display: inline-block; margin: 0 .12em; }}
  </style>
  <div id="root" data-composition-id="captions" data-width="{W}" data-height="{H}">
{chr(10).join(cap_items)}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
{chr(10).join(cap_js)}
    window.__timelines["captions"] = tl;
  </script>
</template>
"""
    (out / "compositions" / "captions.html").write_text(captions, encoding="utf-8")

    hosts = []
    title = spec.get("title")
    if title:
        tdur = float(spec.get("title_duration", 2.4))
        (out / "compositions" / "title.html").write_text(f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; }}
    #title-text {{ position: absolute; left: {70 if vertical else 70}px; right: {180 if vertical else 70}px; top: {330 if vertical else 90}px; text-align: center;
                  font-family: "Montserrat", sans-serif; font-weight: 900; font-size: {96 if vertical else 72}px; line-height: 1.02;
                  color: #fff; text-shadow: 0 6px 0 rgba(0,0,0,.5), 0 0 30px rgba(0,0,0,.5); }}
    #title-text em {{ font-style: normal; color: #ffd84a; }}
  </style>
  <div id="root" data-composition-id="title" data-width="{W}" data-height="{H}">
    <div id="title-text" class="clip" data-start="0" data-duration="{tdur:.2f}" data-var-text="headline">{html.escape(title)}</div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo("#title-text", {{ y: 0, opacity: 1 }}, {{ y: -30, opacity: 0, duration: 0.25, ease: "power2.in" }}, {tdur - 0.3:.2f});
    window.__timelines["title"] = tl;
  </script>
</template>
""", encoding="utf-8")
        hosts.append(f'      <div id="title" data-composition-id="title" data-composition-src="compositions/title.html" '
                     f'data-start="0" data-duration="{tdur:.2f}" data-track-index="3" data-track-kind="graphics" '
                     f'data-width="{W}" data-height="{H}" style="z-index:50"></div>')
    hosts.append(f'      <div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html" '
                 f'data-start="0" data-duration="{total_all:.3f}" data-track-index="4" data-track-kind="captions" '
                 f'data-width="{W}" data-height="{H}" style="z-index:60"></div>')
    if end:
        (out / "compositions" / "endcard.html").write_text(f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; background: #0d0f14; }}
    #end-text {{ position: absolute; left: 80px; right: {180 if vertical else 80}px; top: 42%; text-align: center; font-family: "Montserrat", sans-serif;
                font-weight: 900; font-size: {70 if vertical else 60}px; color: #fff; }}
  </style>
  <div id="root" data-composition-id="endcard" data-width="{W}" data-height="{H}">
    <div id="end-text" class="clip" data-start="0" data-duration="{end_dur:.2f}" data-var-text="endText">{html.escape(end.get("text", ""))}</div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo("#end-text", {{ opacity: 0, y: 20 }}, {{ opacity: 1, y: 0, duration: 0.3, ease: "power3.out" }}, 0.05);
    window.__timelines["endcard"] = tl;
  </script>
</template>
""", encoding="utf-8")
        hosts.append(f'      <div id="endcard" data-composition-id="endcard" data-composition-src="compositions/endcard.html" '
                     f'data-start="{total:.3f}" data-duration="{end_dur:.2f}" data-track-index="2" data-track-kind="graphics" '
                     f'data-width="{W}" data-height="{H}" style="z-index:70"></div>')

    # Punch-ins: a slow push on shots that ask for it (scale on the video itself, from the root timeline).
    punch_js = [f'      tl.fromTo("#shot-{s["id"]}", {{scale: 1}}, {{scale: {float(s["punch"])}, duration: {s["_dur"]:.3f}, ease: "none"}}, {s["_start"]:.3f});'
                for s in spec["shots"] if s.get("punch")]
    index = f"""<!doctype html>
<html lang="en" data-resolution="{"portrait" if vertical else "landscape"}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: {W}px; height: {H}px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: 100%; height: 100%; }}
      .shot {{ position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; object-fit: cover; }}
    </style>
  </head>
  <body>
    <!-- "{html.escape(name)}": generated by demo/shorts_template/build_short.py from {html.escape(spec_path.name)}.
         Shots are Promptimate render_shot MP4s on hard cuts; edit timings here or re-run the builder. -->
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total_all:.3f}" data-width="{W}" data-height="{H}">
{chr(10).join(shots_html)}
{chr(10).join(hosts)}
{chr(10).join(audio_html)}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
{chr(10).join(punch_js)}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
    (out / "index.html").write_text(index, encoding="utf-8")
    (out / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
        "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
        "media": {"autoProxy": True}}, indent=2), encoding="utf-8")
    (out / "package.json").write_text(json.dumps({
        "name": name, "private": True, "type": "module",
        "scripts": {"dev": f"npx --yes {HF} preview", "check": f"npx --yes {HF} check", "render": f"npx --yes {HF} render"}},
        indent=2), encoding="utf-8")
    (out / "words.json").write_text(json.dumps(all_words, indent=1), encoding="utf-8")
    print(f"built {out} ({total_all:.2f} s, {len(spec['shots'])} shots, {len(groups)} caption groups)")
    return out


def npx(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("npm_config_cache", r"D:\npm-cache" if Path("D:/").exists() else env.get("npm_config_cache", ""))
    # HyperFrames needs ffmpeg/ffprobe on PATH for the audio mix.
    env["PATH"] = str(Path(ffmpeg()).parent) + os.pathsep + env.get("PATH", "")
    cmd = ["npx.cmd" if os.name == "nt" else "npx", "--yes", HF, *args]
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--out")
    ap.add_argument("--render", action="store_true", help="run hyperframes check + render after building")
    a = ap.parse_args()
    proj = build(Path(a.spec).resolve(), Path(a.out).resolve() if a.out else None)
    if a.render:
        c = npx(["check", "--json"], proj)
        print(c.stdout[-3000:], c.stderr[-2000:])
        r = npx(["render", "--output", str(proj / f"{proj.name}.mp4")], proj)
        print(r.stdout[-3000:], r.stderr[-2000:])
        sys.exit(r.returncode)
