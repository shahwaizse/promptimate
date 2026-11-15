"""Finish the Roblox 'In This Town' comparison: voiceover (local Kokoro TTS), music/SFX bed, captions and vertical
assembly with the HyperFrames shorts template, for versions A (stock), B (Promptimate), C (Roblox Prompt-to-Animation),
plus a 16:9 side-by-side (A | B | C) and contact sheets / judge packets.

    .venv\\Scripts\\python.exe demo\\roblox_short\\make_short.py [--versions A,B,C] [--no-render] [--sheets-only]

Inputs: .cache/roblox_short/<V>_full.mp4 + frames/<V>/ (roblox/short/render.py). Shots are cut from the continuous
render on the story.py shot list (edit time == story time). Outputs under demo/roblox_short/build/ (gitignored).
The music is a synthesized placeholder bed (real shorts use a recognisable song; swap music.wav for one you have
rights to). The narrator is Kokoro af_heart pitched up ~2.5 semitones for a younger, generic voice (no cloning).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "roblox" / "short"))
sys.path.insert(0, str(ROOT / "demo" / "shorts_template"))
import build_short  # noqa: E402  (imported, not edited)
import story as S  # noqa: E402

CACHE = ROOT / ".cache" / "roblox_short"
BUILD = HERE / "build"
FF = build_short.ffmpeg()
SR = 48000
END_CARD = {"A": "Stock Roblox animations", "B": "Animated with Promptimate", "C": "Roblox Prompt-to-Animation"}
FONT = "C:/Windows/Fonts/arialbd.ttf"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"failed: {' '.join(map(str, cmd))}\n{r.stderr[-1500:]}")
    return r


# ---------------------------------------------------------------------------------------------------------- audio
def tts(text, voice, out: Path):
    if out.exists():
        return out
    env = os.environ.copy()
    env.setdefault("npm_config_cache", r"D:\npm-cache")
    venv_py = ROOT / ".cache" / "tts-venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        env.setdefault("HYPERFRAMES_PYTHON", str(venv_py))
    r = subprocess.run(["npx.cmd" if os.name == "nt" else "npx", "--yes", build_short.HF, "tts", text, "--voice", voice,
                        "--output", str(out)], capture_output=True, text=True, env=env, cwd=str(out.parent))
    if r.returncode or not out.exists():
        raise SystemExit(f"tts failed: {r.stdout[-800:]} {r.stderr[-800:]}")
    return out


def pitch_up(src: Path, dst: Path, semis=2.5):
    if dst.exists():
        return dst
    k = 2 ** (semis / 12)
    run([FF, "-y", "-loglevel", "error", "-i", str(src), "-af", f"asetrate=24000*{k:.5f},aresample=24000,atempo={1 / k:.5f}", str(dst)])
    return dst


def voiceover():
    vo_dir = BUILD / "vo"
    vo_dir.mkdir(parents=True, exist_ok=True)
    out, t_free = [], 0.0
    for k, (want, who, text) in enumerate(S.VO):
        raw = tts(text, S.VOICE[who], vo_dir / f"vo{k + 1:02d}_{who}.wav")
        wav = pitch_up(raw, vo_dir / f"vo{k + 1:02d}_{who}_kid.wav") if who == "narrator" else raw
        a0, a1 = build_short.speech_span(wav)
        start = max(want - a0, t_free)
        out.append({"id": f"vo{k + 1}", "audio": str(wav), "start": round(start, 3), "text": text})
        t_free = start + a1 + 0.1
    return out, t_free


def _write_wav(path: Path, x: np.ndarray):
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        st = np.stack([x, x], axis=1) if x.ndim == 1 else x
        w.writeframes((st * 32767).astype(np.int16).tobytes())


def _read_mp3(path: Path) -> np.ndarray:
    r = subprocess.run([FF, "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32).astype(np.float64)


def music_bed(total: float) -> Path:
    """Playful marimba/pluck loop (C-Am-F-G, 112 bpm) + soft bass + hats; phone ring at 7.2 s and a hit on 'Boo!'."""
    path = BUILD / "music_sfx.wav"
    n = int(total * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    bpm = 112
    beat = 60 / bpm
    chords = [[60, 64, 67], [57, 60, 64], [53, 57, 60], [55, 59, 62]]
    rng = random.Random(3)
    mel = [0, 2, 1, 2, 0, 1, 2, 1]

    def note(midi, start, dur, amp, decay=6.0, harm=(1, 0.35, 0.12)):
        i0 = int(start * SR)
        m = min(n - i0, int(dur * SR))
        if m <= 0:
            return
        tt = np.arange(m) / SR
        fr = 440 * 2 ** ((midi - 69) / 12)
        env = np.exp(-decay * tt) * np.minimum(1, tt / 0.004)
        sig = sum(h * np.sin(2 * np.pi * fr * (k + 1) * tt) for k, h in enumerate(harm))
        x[i0:i0 + m] += amp * env * sig

    b = 0
    while b * beat < total:
        ch = chords[(b // 8) % 4]
        st = b * beat
        note(ch[mel[b % 8]] + 12, st, beat * 1.5, 0.11, decay=5.5)
        if b % 2 == 0:
            note(ch[0] - 24, st, beat * 1.8, 0.16, decay=2.5, harm=(1, 0.2))
        if b % 4 == 2:
            note(ch[2] + 12, st + beat * 0.5, beat, 0.06, decay=7)
        # hat: short noise burst
        i0 = int((st + beat / 2) * SR)
        m = min(n - i0, int(0.05 * SR))
        if m > 0:
            x[i0:i0 + m] += 0.025 * np.array([rng.uniform(-1, 1) for _ in range(m)]) * np.exp(-np.arange(m) / (0.012 * SR))
        b += 1
    x *= 0.55
    # phone ring (two-tone trill) 7.2-8.4 s
    for k in range(2):
        s0 = 7.2 + k * 0.6
        i0, m = int(s0 * SR), int(0.4 * SR)
        tt = np.arange(m) / SR
        trill = (np.sign(np.sin(2 * np.pi * 20 * tt)) + 1) / 2
        x[i0:i0 + m] += 0.12 * (np.sin(2 * np.pi * 1300 * tt) * trill + np.sin(2 * np.pi * 1650 * tt) * (1 - trill))
    hit = SFX = Path.home() / ".claude" / "skills" / "media-use" / "audio" / "assets" / "sfx"
    for name, at, vol in (("impact-bass-1.mp3", 23.0, 0.5), ("pop.mp3", 24.1, 0.35)):
        f = SFX / name
        if f.exists():
            y = _read_mp3(f)
            i0 = int(at * SR)
            m = min(n - i0, len(y))
            x[i0:i0 + m] += vol * y[:m]
    fade = int(1.2 * SR)
    x[-fade:] *= np.linspace(1, 0, fade)
    _write_wav(path, x)
    return path


# ---------------------------------------------------------------------------------------------------------- video
def cut_shots(version: str) -> list[dict]:
    src = CACHE / f"{version}_full.mp4"
    d = BUILD / f"shots_{version}"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for sid, a, b, cam, desc in S.SHOTS:
        f = d / f"{sid}.mp4"
        if not f.exists() or f.stat().st_mtime < src.stat().st_mtime:
            run([FF, "-y", "-loglevel", "error", "-ss", f"{a:.4f}", "-i", str(src), "-t", f"{b - a:.4f}",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-an", str(f)])
        out.append({"id": sid, "video": str(f), "duration": round(b - a, 3),
                    **({"punch": 1.05} if cam.get("fov", 60) <= 45 else {})})
    return out


def make_version(version: str, vo, bed: Path, render: bool) -> dict:
    t0 = time.time()
    spec = {"name": f"roblox_town_{version}", "size": list(S.SIZE), "fps": 30, "title": S.TITLE,
            "shots": cut_shots(version), "voiceover": vo, "music": {"src": str(bed), "volume": 1.0},
            "sfx_on_cuts": True, "end_card": {"text": END_CARD[version], "duration": 1.6}}
    sp = BUILD / f"short_{version}.json"
    sp.write_text(json.dumps(spec, indent=1))
    proj = build_short.build(sp, BUILD / f"roblox_town_{version}")
    res = {"project": str(proj), "build_s": round(time.time() - t0, 1)}
    if render:
        c = build_short.npx(["check", "--json"], proj)
        (proj / "check.json").write_text(c.stdout, encoding="utf-8")
        t1 = time.time()
        mp4 = proj / f"roblox_town_{version}.mp4"
        r = build_short.npx(["render", "--output", str(mp4)], proj)
        (proj / "render.log").write_text(r.stdout + "\n" + r.stderr, encoding="utf-8")
        res.update({"render_s": round(time.time() - t1, 1), "mp4": str(mp4), "ok": mp4.exists() and r.returncode == 0})
        print(version, res, flush=True)
    return res


def side_by_side(versions=("A", "B", "C")) -> Path:
    ins = [BUILD / f"roblox_town_{v}" / f"roblox_town_{v}.mp4" for v in versions]
    out = BUILD / "roblox_town_side_by_side.mp4"
    labels = {"A": "A  STOCK ANIMATIONS", "B": "B  PROMPTIMATE", "C": "C  ROBLOX PROMPT-TO-ANIMATION"}
    fl = []
    for i, v in enumerate(versions):
        fl.append(f"[{i}:v]scale=576:1024,setsar=1,pad=600:1080:12:44:color=0x111318,"
                  f"drawtext=fontfile='{FONT.replace(':', chr(92) + ':')}':text='{labels[v]}':fontcolor=white:fontsize=24:x=(w-text_w)/2:y=12[v{i}]")
    fl.append(f"[v0][v1][v2]hstack=inputs=3,pad=1920:1080:60:0:color=0x111318[out]")
    cmd = [FF, "-y", "-loglevel", "error"]
    for f in ins:
        cmd += ["-i", str(f)]
    cmd += ["-filter_complex", ";".join(fl), "-map", "[out]", "-map", "1:a?", "-c:v", "libx264", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)]
    run(cmd)
    return out


# ---------------------------------------------------------------------------------------------------------- sheets
def frame_at(version, t):
    i = min(int(round(t * S.FPS)), int(S.END * S.FPS) - 1)
    return Image.open(CACHE / "frames" / version / f"f{i:05d}.png").convert("RGB")


def _font(sz):
    try:
        return ImageFont.truetype(FONT, sz)
    except Exception:
        return ImageFont.load_default()


def contact_sheet(version, label, out: Path, cols=7, w=240):
    h = int(w * 16 / 9)
    n = len(S.SHOTS)
    rows = math.ceil(n / cols)
    sheet = Image.new("RGB", (cols * w + (cols + 1) * 8, rows * (h + 34) + 70), (18, 19, 24))
    d = ImageDraw.Draw(sheet)
    d.text((10, 14), label, fill=(255, 255, 255), font=_font(30))
    for k, (sid, a, b, cam, desc) in enumerate(S.SHOTS):
        im = frame_at(version, (a + b) / 2).resize((w, h), Image.LANCZOS)
        x, y = 8 + (k % cols) * (w + 8), 64 + (k // cols) * (h + 34)
        sheet.paste(im, (x, y))
        d.text((x + 2, y + h + 4), f"{sid}  t={(a + b) / 2:.1f}s", fill=(200, 200, 210), font=_font(16))
    sheet.save(out, quality=90)
    return out


def beat_strips(version, label, out: Path, w=200):
    """For judges: every story beat as 4 frames (-0.6, -0.2, +0.2, +0.6 s around the beat)."""
    h = int(w * 16 / 9)
    offs = (-0.6, -0.2, 0.2, 0.6)
    sheet = Image.new("RGB", (len(offs) * (w + 6) + 330, len(S.BEATS) * (h + 8) + 60), (18, 19, 24))
    d = ImageDraw.Draw(sheet)
    d.text((10, 12), label, fill=(255, 255, 255), font=_font(28))
    for r, (bid, t, desc) in enumerate(S.BEATS):
        y = 54 + r * (h + 8)
        d.text((10, y + h / 2 - 30), f"{r + 1}. {desc}", fill=(230, 230, 235), font=_font(17))
        for c, o in enumerate(offs):
            im = frame_at(version, min(max(t + o, 0), S.END - 0.05)).resize((w, h), Image.LANCZOS)
            sheet.paste(im, (330 + c * (w + 6), y))
    sheet.save(out, quality=88)
    return out


def judge_packets(versions=("A", "B", "C")):
    """Anonymous packets for blind judging: X/Y/Z in a shuffled (but recorded) order."""
    jd = BUILD / "judge"
    jd.mkdir(parents=True, exist_ok=True)
    order = list(versions)
    random.Random(20261115).shuffle(order)
    key = {}
    for name, v in zip("XYZ", order):
        key[name] = v
        contact_sheet(v, f"Version {name}: one frame per shot", jd / f"{name}_shots.jpg")
        beat_strips(v, f"Version {name}: story beats", jd / f"{name}_beats.jpg")
    (CACHE / "judge_key.json").write_text(json.dumps(key, indent=1))   # kept out of the judges' folder
    return jd, key


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", default="A,B,C")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--sheets-only", action="store_true")
    a = ap.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    vs = a.versions.split(",")
    report = json.loads((CACHE / "finish_report.json").read_text()) if (CACHE / "finish_report.json").exists() else {}
    if not a.sheets_only:
        t0 = time.time()
        vo, vo_end = voiceover()
        bed = music_bed(S.END + 1.6)
        report["audio_s"] = round(time.time() - t0, 1)
        report["vo_end_s"] = round(vo_end, 2)
        for v in vs:
            report[v] = make_version(v, vo, bed, not a.no_render)
        if not a.no_render and all((BUILD / f"roblox_town_{v}" / f"roblox_town_{v}.mp4").exists() for v in "ABC"):
            report["side_by_side"] = str(side_by_side())
    for v in vs:
        contact_sheet(v, f"Version {v} ({END_CARD[v]})", BUILD / f"contact_{v}.jpg")
    if all((CACHE / "frames" / v).exists() for v in "ABC"):
        jd, key = judge_packets()
        report["judge_dir"] = str(jd)
    (CACHE / "finish_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
