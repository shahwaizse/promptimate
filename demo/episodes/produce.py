"""Produce one Roblox "In this town" episode end to end, fast: cast -> perform -> record -> narration -> music/SFX
mix -> captions -> final 9:16 MP4.

    .venv\\Scripts\\python.exe demo\\episodes\\produce.py <episode> [--from perform|record|audio] [--rounds 1]

Episodes are modules in demo/episodes/eps/ with CAST, ACTORS, CAMERAS, LINES, MUSIC, SFX (see eps/README.md).
Narration: Kokoro (local, Apache-2.0). Music and SFX: Openverse (CC0 / CC BY; credits written next to the video).
Outputs: demo/episodes/build/<episode>/ (gitignored). Studio must be open with the town place and visible on screen
(roblox_record's fast path)."""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
sys.path.insert(0, str(HERE))
os.environ.setdefault("TEMP", r"D:\tmp")
os.environ.setdefault("npm_config_cache", r"D:\npm-cache")
FF = r"D:\tools\ffmpeg\bin\ffmpeg.exe"
FP = r"D:\tools\ffmpeg\bin\ffprobe.exe"
BUILD = HERE / "build"
UA = {"User-Agent": "promptimate-episodes"}
SR = 48000


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        raise SystemExit(f"failed: {' '.join(map(str, cmd))[:300]}\n{(r.stderr or r.stdout)[-1500:]}")
    return r


def duration(p) -> float:
    return float(run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).stdout.strip())


# ------------------------------------------------------------------------------------------------ media fetching
def openverse(query: str, kind: str, out_dir: Path, pick: int = 0, min_s: float = 0, max_s: float = 1e9) -> dict:
    """First CC0/CC BY result for query (kind: music | sound_effect), downloaded; returns {path, title, creator,
    license, url}. Cached by query."""
    out_dir.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^a-z0-9]+", "_", f"{kind}_{query}_{pick}".lower())
    meta_p = out_dir / f"{key}.json"
    if meta_p.exists():
        m = json.loads(meta_p.read_text())
        if Path(m["path"]).exists():
            return m
    params = {"q": query, "license": "cc0,by", "page_size": 20}
    if kind == "music":
        params["category"] = "music"
    else:
        params["source"] = "freesound"         # Freesound sounds carry no category in Openverse
    q = urllib.parse.urlencode(params)
    d = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.openverse.org/v1/audio/?{q}", headers=UA), timeout=40))
    res = [r for r in d.get("results", []) if min_s * 1000 <= (r.get("duration") or 0) <= max_s * 1000 and r.get("url")]
    if not res:
        raise SystemExit(f"openverse: nothing for {kind} '{query}'")
    r = res[min(pick, len(res) - 1)]
    ext = ".mp3" if "mp3" in r["url"] or r.get("filetype") in (None, "mp3", "mp32") else "." + r.get("filetype", "mp3")
    path = out_dir / f"{key}{ext}"
    with urllib.request.urlopen(urllib.request.Request(r["url"], headers=UA), timeout=120) as f:
        path.write_bytes(f.read())
    m = {"path": str(path), "title": r.get("title"), "creator": r.get("creator"), "license": r.get("license"),
         "license_version": r.get("license_version"), "url": r.get("foreign_landing_url") or r["url"], "source": r.get("source")}
    meta_p.write_text(json.dumps(m, indent=1))
    return m


TINY_VOCA = Path(r"D:\tmp\tts_try")      # tiny-voca (Apache-2.0) venv + weights; voices "tv_M2" / "tv_F2"


def tts(text: str, voice: str, speed: float, out: Path) -> Path:
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    if voice.startswith("tv_"):
        env = dict(os.environ, DIZIONE_DATA=str(TINY_VOCA / "tiny-voca" / "weights" / "phonemizer"), PYTHONIOENCODING="utf-8")
        run([str(TINY_VOCA / "venv" / "Scripts" / "python.exe"), "-m", "tiny_voca.infer", "--checkpoint",
             str(TINY_VOCA / "tiny-voca" / "weights" / "tiny-voca.pt"), "--voice", voice[3:], "--speed", str(speed),
             "--text", text, "--output", str(out)], env=env)
        return out
    npx = "npx.cmd" if os.name == "nt" else "npx"
    env = dict(os.environ)
    venv_py = ROOT / ".cache" / "tts-venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        env.setdefault("HYPERFRAMES_PYTHON", str(venv_py))
    run([npx, "--yes", "hyperframes", "tts", text, "--voice", voice, "--speed", str(speed), "-o", str(out)],
        cwd=str(out.parent), env=env)
    return out


# ------------------------------------------------------------------------------------------------ captions
def _ass_time(t: float) -> str:
    h, r = divmod(max(t, 0), 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def captions(lines: list[dict], out: Path, size=(1080, 1920), titles=(), highlight=True, max_words=3) -> Path:
    """TikTok-style captions: 1-3 word chunks timed across each narration clip (proportional to characters), big
    white text with a black outline, the current word in yellow."""
    W, H = size
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial Black,{int(getattr(captions, "size", 92))},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,2,2,80,80,{int(H * 0.25)},1
Style: Title,Arial Black,110,&H00FFFFFF,&H00FFFFFF,&H00000000,&HB4000000,-1,0,0,0,100,100,2,0,3,18,0,8,60,60,{int(H * 0.14)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for ln in lines:
        words = ln["text"].replace("—", " ").split()
        if not words:
            continue
        t0, dur = ln["t"], ln["dur"]
        weights = [len(re.sub(r"[^A-Za-z0-9]", "", w)) + 2 for w in words]
        tot = sum(weights)
        starts, acc = [], 0.0
        for w in weights:
            starts.append(t0 + dur * acc / tot)
            acc += w
        ends = starts[1:] + [t0 + dur]
        chunks, cur = [], []
        for i, w in enumerate(words):
            cur.append(i)
            if len(cur) == max_words or w.endswith((",", ".", "!", "?", "…")) or i == len(words) - 1:
                chunks.append(cur)
                cur = []
        for ci, ch in enumerate(chunks):
            chunk_end = starts[chunks[ci + 1][0]] if ci + 1 < len(chunks) else t0 + dur + 0.15
            if not highlight:     # one event per chunk
                ev.append(f"Dialogue: 0,{_ass_time(starts[ch[0]])},{_ass_time(chunk_end)},Cap,,0,0,0,,"
                          + " ".join(words[j].upper() for j in ch))
                continue
            for i in ch:          # one event per word: the chunk shown, the spoken word highlighted
                txt = " ".join(("{\\c&H00E6FF&}" + words[j].upper() + "{\\c&HFFFFFF&}") if (j == i and highlight) else words[j].upper()
                               for j in ch)
                pop = "{\\fscx108\\fscy108\\t(0,90,\\fscx100\\fscy100)}" if i == ch[0] else ""
                ev.append(f"Dialogue: 0,{_ass_time(starts[i])},{_ass_time(ends[i] if i != ch[-1] else chunk_end)},Cap,,0,0,0,,{pop}{txt}")
    for t0, t1, text in titles:
        ev.append(f"Dialogue: 1,{_ass_time(t0)},{_ass_time(t1)},Title,,0,0,0,,{{\\fad(120,120)}}{text.upper()}")
    out.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    return out


# ------------------------------------------------------------------------------------------------ audio mix
def mix(ep, total: float, out_dir: Path) -> tuple[Path, list[dict], list[str]]:
    """Narration clips at their times, music bed ducked under the voice, SFX; loudness -14 LUFS. Returns
    (wav, placed lines with durations, credits)."""
    voice = getattr(ep, "VOICE", "af_heart")
    speed = getattr(ep, "SPEED", 1.05)
    placed, credits = [], []
    inputs, filters, vo_labels = [], [], []
    for k, ln in enumerate(ep.LINES):
        t, text = ln[0], ln[1]
        v = ln[2] if len(ln) > 2 else voice
        p = tts(text, v, speed, out_dir / "vo" / f"l{k:02d}_{v}_{__import__("hashlib").sha1((text + str(speed)).encode()).hexdigest()[:8]}.wav")
        d = duration(p)
        placed.append({"t": t, "text": text, "dur": d, "path": str(p)})
        if k and placed[k - 1]["t"] + placed[k - 1]["dur"] > t + 0.05:
            log(f"  note: line {k} starts {placed[k - 1]['t'] + placed[k - 1]['dur'] - t:.2f}s before line {k - 1} ends")
    for k, ln in enumerate(placed):
        inputs += ["-i", ln["path"]]
        filters.append(f"[{k}:a]aresample={SR},aformat=channel_layouts=stereo,adelay={int(ln['t'] * 1000)}|{int(ln['t'] * 1000)},"
                       f"volume={getattr(ep, 'VO_GAIN', 1.0)}[v{k}]")
        vo_labels.append(f"[v{k}]")
    n = len(placed)
    filters.append(f"{''.join(vo_labels)}amix=inputs={n}:normalize=0,apad=whole_dur={total:.3f}[vo]")
    filters.append("[vo]asplit=2[vo1][vosc]")
    idx = n
    mus = ep.MUSIC
    m = openverse(mus["query"], "music", BUILD / "_media", pick=mus.get("pick", 0), min_s=total * 0.6)
    credits.append(f"Music: \"{m['title']}\" by {m['creator']} ({m['license'].upper()} {m.get('license_version') or ''}) {m['url']}")
    inputs += ["-ss", str(mus.get("from", 0)), "-i", m["path"]]
    fade_out = max(total - 1.2, 0)
    filters.append(f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,atrim=0:{total:.3f},asetpts=N/SR/TB,"
                   f"volume={mus.get('gain', 0.5)},afade=t=in:d=0.6,afade=t=out:st={fade_out:.2f}:d=1.2[mraw]")
    filters.append("[mraw][vosc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=350[mus]")
    idx += 1
    sfx_labels = []
    for k, s in enumerate(getattr(ep, "SFX", [])):
        t, q = s[0], s[1]
        g = s[2] if len(s) > 2 else 0.8
        try:
            f = openverse(q, "sound_effect", BUILD / "_media", max_s=8)
        except SystemExit as e:
            log("  sfx skipped:", e)
            continue
        credits.append(f"SFX: \"{f['title']}\" by {f['creator']} ({f['license'].upper()}) {f['url']}")
        inputs += ["-i", f["path"]]
        filters.append(f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,atrim=0:6,adelay={int(t * 1000)}|{int(t * 1000)},"
                       f"volume={g}[s{k}]")
        sfx_labels.append(f"[s{k}]")
        idx += 1
    filters.append(f"[vo1][mus]{''.join(sfx_labels)}amix=inputs={2 + len(sfx_labels)}:normalize=0,"
                   f"atrim=0:{total:.3f},acompressor=threshold=0.25:ratio=3:attack=10:release=200,"
                   f"loudnorm=I=-14:TP=-1.2:LRA=9[out]")
    wav = out_dir / "mix.wav"
    run([FF, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-ar", str(SR), str(wav)])
    return wav, placed, credits


# ------------------------------------------------------------------------------------------------ cue sheet extras
def annotate(ep):
    """Face-expression and prop cues from the episode (FACES, PROPS) into the Studio cue sheet (Performance)."""
    from roblox_studio import studio
    from roblox_tools import long_str
    faces, props = getattr(ep, "FACES", {}), getattr(ep, "PROPS", [])
    if not faces and not props:
        return
    st = studio()
    raw = st.luau('return require(game:GetService("ReplicatedStorage").Promptimate.Performance:Clone())')
    perf = json.loads(raw)
    for name, cues in faces.items():
        if name in perf.get("actors", {}):
            perf["actors"][name]["faces"] = [[float(t), e] for t, e in cues]
    perf["props"] = props
    src = "return " + long_str(json.dumps(perf, separators=(",", ":")))
    st.luau('local m = game:GetService("ReplicatedStorage").Promptimate.Performance; m.Source = ' + long_str(src) + '; return 1')


# ------------------------------------------------------------------------------------------------ pipeline
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--from", dest="start", default="cast", choices=["cast", "perform", "record", "audio"])
    ap.add_argument("--rounds", type=int, default=0, help="repair rounds in roblox_perform")
    ap.add_argument("--voice", default=None, help="override the narrator (af_heart, tv_M2, ...)")
    ap.add_argument("--suffix", default="", help="append to the output file name")
    ap.add_argument("--attempts", type=int, default=1, help="seeds tried per beat for facing/mark/seat")
    a = ap.parse_args()
    ep = importlib.import_module(f"eps.{a.episode}")
    if a.voice:
        ep.VOICE = a.voice
        if a.voice.startswith("tv_") and ep.SPEED < 1.2:
            ep.SPEED = 1.35
    out = BUILD / a.episode
    out.mkdir(parents=True, exist_ok=True)
    T = {}
    t_all = time.time()
    steps = ["cast", "perform", "record", "audio"]
    todo = steps[steps.index(a.start):]
    import server  # noqa: F401  (registers the Roblox tools: sets their server module)
    import roblox_record as RR
    if "cast" in todo:
        import cast as CAST
        t = time.time()
        r = CAST.ensure(ep.CAST)
        bad = {k: v for k, v in r.items() if v != "ok"}
        if bad:
            raise SystemExit(f"cast failed: {bad}")
        T["cast"] = time.time() - t
        log("cast", r, f"{T['cast']:.0f}s")
    if "perform" in todo:
        os.environ.setdefault("PROMPTIMATE_RBX_TAKES", "1")
        # a clean cue sheet: only this episode's characters perform (earlier episodes' entries would be posed too)
        from roblox_studio import studio
        studio().luau('local f = game:GetService("ReplicatedStorage"):FindFirstChild("Promptimate"); '
                      'local m = f and f:FindFirstChild("Performance"); '
                      'if m then m.Source = "return [[{\\"version\\":1,\\"actors\\":{}}]]" end; return 1')
        # props back home (a previous recording may have left one hidden or in a hand): seats must be where they live
        studio().luau('for _, d in workspace:GetDescendants() do if d:IsA("PVInstance") and typeof(d:GetAttribute("PromptimateHome")) == "CFrame" '
                      'then d:PivotTo(d:GetAttribute("PromptimateHome")) end end; return 1')
        os.environ["PROMPTIMATE_REPAIR_ROUNDS"] = str(a.rounds)
        os.environ["PROMPTIMATE_RBX_ATTEMPTS"] = str(a.attempts)
        import server  # noqa: F401  (motion engine + generate_motion)
        import roblox_tools as RT
        sys.path.insert(0, str(ROOT / "roblox" / "short"))
        import fastgrab as FG
        t = time.time()
        FG.minimize_studio()          # a rendering Studio steals the GPU from motion generation (~6x slower)
        try:
            res = RT.perform([RT.Actor(**x) for x in ep.ACTORS])
        finally:
            FG.pin_studio(True)
        info = json.loads(res[0])
        (out / "perform.json").write_text(json.dumps(info, indent=1))
        T["perform"] = time.time() - t
        log(f"perform {T['perform']:.0f}s: generated {info.get('generated')} reused {info.get('reused')}")
        for w in info.get("warnings", [])[:10]:
            log("   !", w)
        if len(res) > 1:
            import shutil
            shutil.copy(res[1].path if hasattr(res[1], "path") else res[1], out / "plan.png")
    if "record" in todo:
        annotate(ep)
        t = time.time()
        cams = [RR.CameraCue(**c) for c in ep.CAMERAS]
        r = RR.record(cams, name=a.episode, quality="final", end=getattr(ep, "LENGTH", None))
        info = json.loads(r[0])
        for w in info.get("camera_warnings", [])[:8]:
            log("   cam!", w)
        while True:
            time.sleep(3)
            st = json.loads(RR.record([], job=info["job"])[0])
            if st.get("state") in ("done", "failed", "cancelled"):
                break
        if st["state"] != "done":
            raise SystemExit(f"record {st}")
        (out / "silent.mp4").write_bytes(Path(st["mp4"]).read_bytes())
        T["record"] = time.time() - t
        log(f"record {T['record']:.0f}s")
    if "audio" in todo:
        t = time.time()
        silent = out / "silent.mp4"
        total = duration(silent)
        wav, placed, credits = mix(ep, total, out)
        cap = getattr(ep, "CAPTIONS", {})
        captions.size = cap.get("size", 92)
        ass = captions(placed, out / "captions.ass", titles=getattr(ep, "TITLES", []), highlight=cap.get("highlight", True),
                       max_words=cap.get("max_words", 3))
        final = out / f"{a.episode}{a.suffix}.mp4"
        fonts = "C\\:/Windows/Fonts"
        assp = str(ass).replace("\\", "/").replace(":", "\\:")
        run([FF, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-filter_complex",
             f"[0:v]ass='{assp}':fontsdir='{fonts}'[v]", "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(final)])
        (out / "credits.txt").write_text("\n".join([getattr(ep, "TITLE", a.episode), "", *credits,
                                                    "Narration: Kokoro TTS (Apache-2.0)"]) + "\n", encoding="utf-8")
        T["audio"] = time.time() - t
        log(f"audio+captions {T['audio']:.0f}s -> {final}")
    T["total"] = time.time() - t_all
    (out / "timing.json").write_text(json.dumps({k: round(v, 1) for k, v in T.items()}))
    log("timing", {k: round(v) for k, v in T.items()})


if __name__ == "__main__":
    main()
