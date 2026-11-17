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
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
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

# Narration style, measured against the craftee_films reference shorts (D:\tmp\audio_hc\report.md): they speak
# ~4.2-4.6 words/s almost wall to wall (sentence pauses ~0-0.15 s); tiny-voca at 1.0 with its own ~0.25 s
# silence before every sentence gave 3.0 words/s with 20% silence. The owner rejected 1.6x: never above 1.2x.
TV_SPEED_SCALE, TV_SPEED_MAX = 1.2, 1.2
TV_STYLE = {"pitch_range": 1.45, "gap": 0.02, "max_pause": 0.12, "v": 2}
# ^ wider pitch movement; pause between sentences in a line (s); longer silences inside a sentence cut to max_pause
LINE_GAP = (0.03, 0.06, 0.20)      # between lines: after a statement, after ! ? ..., before a one/two-word reveal


def narr_speed(ep, voice: str) -> float:
    s = float(getattr(ep, "SPEED", 1.05))
    return min(TV_SPEED_MAX, round(s * TV_SPEED_SCALE, 3)) if voice.startswith("tv_") else s


def vo_path(out_dir: Path, k: int, text: str, voice: str, speed: float) -> Path:
    import hashlib
    style = json.dumps(TV_STYLE, sort_keys=True) if voice.startswith("tv_") else ""
    return out_dir / "vo" / f"l{k:02d}_{voice}_{hashlib.sha1((text + str(speed) + style).encode()).hexdigest()[:8]}.wav"


def tts_many(items) -> None:
    """Synthesise every missing tiny-voca line in one process (one model load); items = [(text, voice, speed, out)].
    Each sentence is trimmed of the model's own edge silence and joined with TV_STYLE["gap"]."""
    todo = [{"text": t, "voice": v[3:], "speed": sp, "out": str(o), **TV_STYLE} for t, v, sp, o in items
            if v.startswith("tv_") and not Path(o).exists()]
    if not todo:
        return
    jf = Path(os.environ.get("TEMP", str(BUILD))) / f"tv_jobs_{os.getpid()}.json"
    jf.write_text(json.dumps(todo), encoding="utf-8")
    env = dict(os.environ, DIZIONE_DATA=str(TINY_VOCA / "tiny-voca" / "weights" / "phonemizer"), PYTHONIOENCODING="utf-8")
    t = time.time()
    run([str(TINY_VOCA / "venv" / "Scripts" / "python.exe"), str(Path(__file__).with_name("tv_batch.py")),
         str(TINY_VOCA / "tiny-voca" / "weights" / "tiny-voca.pt"), str(jf)], env=env)
    log(f"tts: {len(todo)} lines in {time.time() - t:.0f}s (batched)")


def tts(text: str, voice: str, speed: float, out: Path) -> Path:
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    if voice.startswith("tv_"):
        tts_many([(text, voice, speed, out)])      # same trimming and sentence gaps as the batch
        return out
    npx = "npx.cmd" if os.name == "nt" else "npx"
    env = dict(os.environ)
    venv_py = ROOT / ".cache" / "tts-venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        env.setdefault("HYPERFRAMES_PYTHON", str(venv_py))
    run([npx, "--yes", "hyperframes", "tts", text, "--voice", voice, "--speed", str(speed), "-o", str(out)],
        cwd=str(out.parent), env=env)
    return out


# ------------------------------------------------------------------------------------------------ narration timing
_REF = re.compile(r"^@([A-Za-z_][\w-]*)(\.end)?\s*([+-]\s*\d+(?:\.\d+)?)?$")


def pace(ep, out_dir: Path) -> None:
    """Narration-driven timing. LINES may be dicts {"id", "text", "gap"?, "voice"?} (no times): the narration is
    synthesised first and laid back to back (gap after the previous line: LINE_GAP), and every time anywhere
    in the episode written as "@id", "@id.end", "@id+0.4" or "@id.end-0.2" becomes seconds. Fast narration then
    never leaves dead air, and retiming a line moves its beats, shots, faces and sound effects with it."""
    if not any(isinstance(ln, dict) for ln in ep.LINES):
        return
    voice = getattr(ep, "VOICE", "af_heart")
    t = float(getattr(ep, "LEAD_IN", 0.05))     # the references speak within the first 0.1 s
    marks, lines = {}, []
    items = []
    for k, ln in enumerate(ep.LINES):
        txt = ln["text"] if isinstance(ln, dict) else ln[1]
        v = (ln.get("voice") if isinstance(ln, dict) else (ln[2] if len(ln) > 2 else None)) or voice
        items.append((txt, v, narr_speed(ep, v), vo_path(out_dir, k, txt, v, narr_speed(ep, v))))
    tts_many(items)
    for k, ln in enumerate(ep.LINES):
        if not isinstance(ln, dict):
            ln = {"text": ln[1], "at": ln[0], "voice": ln[2] if len(ln) > 2 else None}
        v = ln.get("voice") or voice
        p = tts(ln["text"], v, narr_speed(ep, v), vo_path(out_dir, k, ln["text"], v, narr_speed(ep, v)))
        d = duration(p)
        prev_txt = (ep.LINES[k - 1]["text"] if isinstance(ep.LINES[k - 1], dict) else ep.LINES[k - 1][1]) if k else ""
        breath = LINE_GAP[1] if prev_txt.rstrip().endswith(("!", "?", "…", "...")) else LINE_GAP[0]
        txt_k = ln["text"] if isinstance(ln, dict) else ln[1]
        if len(txt_k.split()) <= 2:
            breath = LINE_GAP[2]              # a beat before a one- or two-word reveal ("Zero." "Forty-eight.")
        t0 = float(ln["at"]) if isinstance(ln.get("at"), (int, float)) else (t + (ln.get("gap", breath) if k else 0))
        marks[ln.get("id") or f"L{k}"] = (t0, t0 + d)
        lines.append((round(t0, 3), ln["text"]) + ((ln["voice"],) if ln.get("voice") else ()))
        t = t0 + d
    marks["last"] = (t, t)

    def res(x):
        if isinstance(x, str):
            m = _REF.match(x.strip())
            if m:
                if m.group(1) not in marks:
                    raise SystemExit(f"unknown narration mark {x!r} (ids: {', '.join(marks)})")
                a, b = marks[m.group(1)]
                return round((b if m.group(2) else a) + float((m.group(3) or "0").replace(" ", "")), 3)
            return x
        if isinstance(x, dict):
            return {k: res(v) for k, v in x.items()}
        if isinstance(x, list):
            return [res(v) for v in x]
        if isinstance(x, tuple):
            return tuple(res(v) for v in x)
        return x
    for name in ("ACTORS", "CAMERAS", "TITLES", "FACES", "PROPS", "FX", "SFX", "LENGTH", "MUSIC", "EVENTS"):
        if hasattr(ep, name):
            setattr(ep, name, res(getattr(ep, name)))
    ep.LINES = lines
    tail = float(getattr(ep, "TAIL", 0.5))       # the references end 0.1-0.3 s after the last word
    if not hasattr(ep, "LENGTH") or ep.LENGTH is None or float(ep.LENGTH) < t + tail:
        ep.LENGTH = round(t + tail, 2)        # never cut off mid-line: hold the last shot after the last word
    log(f"paced: {len(lines)} lines, narration ends {t:.1f}s, length {ep.LENGTH}s")


# ------------------------------------------------------------------------------------------------ captions
def _ass_time(t: float) -> str:
    h, r = divmod(max(t, 0), 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def captions(lines: list[dict], out: Path, size=(1080, 1920), titles=(), highlight=True, max_words=3,
             labels=()) -> Path:
    """TikTok-style captions: 1-3 word chunks timed across each narration clip (proportional to characters), big
    white text with a black outline, the current word in yellow."""
    W, H = size
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Montserrat ExtraBold,{int(getattr(captions, "size", 84))},&H00FFFFFF,&H00FFFFFF,&H00101010,&H78000000,0,0,0,0,100,100,0,0,1,{max(5, int(getattr(captions, "size", 84) * 0.09))},3,{8 if getattr(captions, "pos", "low") == "top" else 2},90,90,{int(H * (0.17 if getattr(captions, "pos", "low") == "top" else 0.30))},1
Style: Label,Montserrat Black,118,&H0030C8FF,&H0030C8FF,&H00101010,&H78000000,0,0,0,0,100,100,2,0,1,9,5,8,60,60,{int(H * 0.19)},1
Style: Title,Montserrat Black,104,&H00FFFFFF,&H00FFFFFF,&H00101010,&H78000000,0,0,0,0,100,100,1,0,1,8,4,8,60,60,{int(H * 0.08)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    keys = {k.upper() for k in getattr(captions, "keywords", ())}

    def word(w):      # key words (episode KEYWORDS, numbers, money) pop in yellow
        bare = re.sub(r"[^A-Za-z0-9$]", "", w).upper()
        if bare and (bare in keys or re.search(r"[0-9$]", bare)):
            return "{\\c&H00E6FF&}" + w + "{\\c&HFFFFFF&}"
        return w

    def under_title(t0, t1):
        return any(a < t1 - 0.05 and t0 + 0.05 < b for a, b, _ in titles)
    for li, ln in enumerate(lines):
        nxt = lines[li + 1]["t"] if li + 1 < len(lines) else 1e9
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
        weak = {"a", "an", "the", "of", "to", "in", "on", "at", "my", "his", "her", "your", "our", "their", "and",
                "but", "or", "for", "with", "from", "into", "is", "was", "were", "be", "that", "this", "as", "by", "so"}
        for i, w in enumerate(words):
            cur.append(i)
            if w.endswith((",", ".", "!", "?", "…")) or i == len(words) - 1:
                chunks.append(cur)
                cur = []
            elif len(cur) >= max_words:
                # never end a card on a dangling article/preposition ("A STAR THE"): carry it to the next card
                if len(cur) > 1 and re.sub(r"[^a-z]", "", w.lower()) in weak:
                    chunks.append(cur[:-1])
                    cur = [i]
                else:
                    chunks.append(cur)
                    cur = []
        for ci, ch in enumerate(chunks):
            chunk_end = starts[chunks[ci + 1][0]] if ci + 1 < len(chunks) else min(t0 + dur + 0.15, nxt - 0.02)
            # (captions keep running under title cards: titles sit at the top, captions below the faces)
            if not highlight:     # one event per chunk
                ev.append(f"Dialogue: 0,{_ass_time(starts[ch[0]])},{_ass_time(chunk_end)},Cap,,0,0,0,,"
                          + " ".join(word(words[j]) for j in ch))
                continue
            for i in ch:          # one event per word: the chunk shown, the spoken word highlighted
                txt = " ".join(("{\\c&H00E6FF&}" + words[j] + "{\\c&HFFFFFF&}") if (j == i and highlight) else word(words[j])
                               for j in ch)
                pop = "{\\fscx108\\fscy108\\t(0,90,\\fscx100\\fscy100)}" if i == ch[0] else ""
                ev.append(f"Dialogue: 0,{_ass_time(starts[i])},{_ass_time(ends[i] if i != ch[-1] else chunk_end)},Cap,,0,0,0,,{pop}{txt}")
    for t0, t1, text in labels:      # the story's numbers/verdicts ("11 MINUTES"): big gold, popping in
        ev.append(f"Dialogue: 2,{_ass_time(t0)},{_ass_time(t1)},Label,,0,0,0,,"
                  r"{\fad(60,150)\fscx40\fscy40\t(0,140,\fscx112\fscy112)\t(140,240,\fscx100\fscy100)}" + text)
    for t0, t1, text in titles:
        ev.append(f"Dialogue: 1,{_ass_time(t0)},{_ass_time(t1)},Title,,0,0,0,,{{\\fad(120,120)}}{text}")
    out.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    return out


# ------------------------------------------------------------------------------------------------ audio mix
# Levels and tone measured against the craftee_films reference shorts (D:\tmp\audio_hc\report.md): the voice sits
# on top, a dark steady bed ~12 dB under it (barely ducked, never swelling to the voice in the gaps), effects that
# are actually heard. Every source is measured (EBU R128) and set to its target relative to the voice, so a loud or
# quiet Openverse file no longer decides the balance; the episode's gains are offsets from their usual values
# (music 0.45, SFX 0.5).
MIX = {"voice_lufs": -16.0, "bed_rel": -9.5, "sfx_rel": -8.0,
       "duck": {"threshold": 0.1, "ratio": 1.0, "attack": 40, "release": 600}}
VOICE_FX = ("highpass=f=80,equalizer=f=300:t=q:w=1.2:g=-1,equalizer=f=2500:t=q:w=1.0:g=3.5,"
            "deesser=i=0.5:m=0.5:f=0.5,"
            "acompressor=threshold=0.1:ratio=3:attack=5:release=90:makeup=1")
BED_FX = "highpass=f=40,lowshelf=f=200:g=3,lowpass=f=2200,equalizer=f=2500:t=q:w=1.3:g=-6"    # out of the voice's presence band
SFX_FX = "silenceremove=start_periods=1:start_threshold=-50dB,atrim=0:3,afade=t=out:st=2.6:d=0.4"   # hit on the cue


def levels(path, af: str = "") -> dict:
    """Integrated loudness and loudest momentary (400 ms) loudness of a file (after filter `af`), cached."""
    cache = BUILD / "_media" / "_levels.json"
    key = f"{Path(path).resolve()}|{os.path.getmtime(path):.0f}|{af}"
    db = json.loads(cache.read_text()) if cache.exists() else {}
    if key in db and "vo" not in Path(path).name:
        return db[key]
    r = subprocess.run([FF, "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
                        (af + "," if af else "") + "aresample=48000,ebur128=framelog=info", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ms = [float(x) for x in re.findall(r"\sM:\s*(-?[\d.]+)", r.stderr)]
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    out = {"I": float(i[-1]) if i else -70.0, "Mmax": max(ms) if ms else -70.0}
    if "vo" not in Path(path).name:          # media files only (the voice stem changes every run)
        db[key] = out
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(db, indent=0))
    return out


def _db(x: float) -> float:
    import math
    return 20 * math.log10(max(x, 1e-4))


def mix(ep, total: float, out_dir: Path) -> tuple[Path, list[dict], list[str]]:
    """Narration clips at their times (voice EQ, de-essing, compression), a steady music bed under the voice, SFX;
    loudness -14 LUFS (two-pass, linear). Returns (wav, placed lines with durations, credits)."""
    voice = getattr(ep, "VOICE", "af_heart")
    placed, credits = [], []
    inputs, filters, vo_labels = [], [], []
    items = []
    for k, ln in enumerate(ep.LINES):
        v = ln[2] if len(ln) > 2 else voice
        items.append((ln[1], v, narr_speed(ep, v), vo_path(out_dir, k, ln[1], v, narr_speed(ep, v))))
    tts_many(items)
    for k, ln in enumerate(ep.LINES):
        t, text = ln[0], ln[1]
        p = tts(*items[k])
        d = duration(p)
        placed.append({"t": t, "text": text, "dur": d, "path": str(p)})
        if k and placed[k - 1]["t"] + placed[k - 1]["dur"] > t + 0.05:
            log(f"  note: line {k} starts {placed[k - 1]['t'] + placed[k - 1]['dur'] - t:.2f}s before line {k - 1} ends")
    # 1) the voice stem (EQ, de-essing, compression), measured
    for k, ln in enumerate(placed):
        inputs += ["-i", ln["path"]]
        filters.append(f"[{k}:a]aresample={SR},aformat=channel_layouts=stereo,adelay={int(ln['t'] * 1000)}|{int(ln['t'] * 1000)}[v{k}]")
        vo_labels.append(f"[v{k}]")
    filters.append(f"{''.join(vo_labels)}amix=inputs={len(placed)}:normalize=0,apad=whole_dur={total:.3f},"
                   f"atrim=0:{total:.3f},{VOICE_FX}[out]")
    vo_wav = out_dir / "vo_stem.wav"
    run([FF, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]",
         "-ar", str(SR), "-c:a", "pcm_f32le", str(vo_wav)])
    vo_gain = MIX["voice_lufs"] - levels(vo_wav)["I"] + _db(getattr(ep, "VO_GAIN", 1.0))
    # 2) voice + bed + effects
    inputs = ["-i", str(vo_wav)]
    filters = [f"[0:a]volume={vo_gain:.2f}dB,asplit=2[vo1][vosc]"]
    idx = 1
    mus = ep.MUSIC
    m = openverse(mus["query"], "music", BUILD / "_media", pick=mus.get("pick", 0), min_s=total * 0.6)
    credits.append(f"Music: \"{m['title']}\" by {m['creator']} ({m['license'].upper()} {m.get('license_version') or ''}) {m['url']}")
    inputs += ["-stream_loop", "-1", "-ss", str(mus.get("from", 0)), "-i", m["path"]]   # loop: never run out
    bed_gain = MIX["voice_lufs"] + MIX["bed_rel"] - levels(m["path"], BED_FX)["I"] + _db(mus.get("gain", 0.45) / 0.45)
    fo = min(0.3, max(total - 0.1, 0.1))        # the references end near full level
    dk = MIX["duck"]
    filters.append(f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,atrim=0:{total:.3f},asetpts=N/SR/TB,{BED_FX},"
                   f"volume={bed_gain:.2f}dB,afade=t=in:d=0.05,afade=t=out:st={total - fo:.2f}:d={fo:.2f}[mraw]")
    filters.append(f"[mraw][vosc]sidechaincompress=threshold={dk['threshold']}:ratio={dk['ratio']}:attack={dk['attack']}:"
                   f"release={dk['release']}[mus]")
    idx += 1
    sfx_labels = []
    for k, s in enumerate(getattr(ep, "SFX", [])):
        t, q = s[0], s[1]
        g = s[2] if len(s) > 2 else 0.5
        try:
            f = openverse(q, "sound_effect", BUILD / "_media", max_s=8)
        except SystemExit as e:
            log("  sfx skipped:", e)
            continue
        credits.append(f"SFX: \"{f['title']}\" by {f['creator']} ({f['license'].upper()}) {f['url']}")
        inputs += ["-i", f["path"]]
        sg = MIX["voice_lufs"] + MIX["sfx_rel"] - levels(f["path"], SFX_FX)["Mmax"] + _db(g / 0.5)
        filters.append(f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,{SFX_FX},volume={min(sg, 24):.2f}dB,"
                       f"adelay={int(t * 1000)}|{int(t * 1000)}[s{k}]")
        sfx_labels.append(f"[s{k}]")
        idx += 1
    filters.append(f"[vo1][mus]{''.join(sfx_labels)}amix=inputs={2 + len(sfx_labels)}:normalize=0,"
                   f"atrim=0:{total:.3f},acompressor=threshold=0.35:ratio=2:attack=10:release=200[out]")
    pre = out_dir / "premix.wav"
    run([FF, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]",
         "-ar", str(SR), "-c:a", "pcm_f32le", str(pre)])
    # 3) -14 LUFS, two-pass linear loudnorm (one-pass loudnorm rides the gain and pumps the bed)
    ln_args = "loudnorm=I=-14:TP=-1.2:LRA=11"
    r = subprocess.run([FF, "-hide_banner", "-nostats", "-i", str(pre), "-af", ln_args + ":print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    st = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    wav = out_dir / "mix.wav"
    run([FF, "-y", "-loglevel", "error", "-i", str(pre), "-af",
         f"{ln_args}:linear=true:measured_I={st['input_i']}:measured_TP={st['input_tp']}:measured_LRA={st['input_lra']}:"
         f"measured_thresh={st['input_thresh']}:offset={st['target_offset']},aresample={SR}", "-ar", str(SR), str(wav)])
    return wav, placed, credits


# ------------------------------------------------------------------------------------------------ cue sheet extras
def annotate(ep):
    """Face-expression and prop cues from the episode (FACES, PROPS) into the Studio cue sheet (Performance)."""
    from roblox_studio import studio
    from roblox_tools import long_str
    faces, props, fx = getattr(ep, "FACES", {}), getattr(ep, "PROPS", []), getattr(ep, "FX", [])
    if not faces and not props and not fx:
        return
    st = studio()
    raw = st.luau('return require(game:GetService("ReplicatedStorage").Promptimate.Performance:Clone())')
    perf = json.loads(raw)
    for name, cues in faces.items():
        if name in perf.get("actors", {}):
            perf["actors"][name]["faces"] = [[float(t), e] for t, e in cues]
    perf["props"] = props
    perf["fx"] = [{"actor": f["actor"], "kind": f["kind"], "text": f.get("text"),
                   "show": [[float(sp[0]), float(sp[1])] + ([str(sp[2])] if len(sp) > 2 else []) for sp in f["show"]]}
                  for f in fx if f.get("actor") in perf.get("actors", {}) and f.get("kind") != "label"]
    # (labels are drawn as screen overlays by captions(): over heads they were cut off by close-ups)
    src = "return " + long_str(json.dumps(perf, separators=(",", ":")))
    st.luau('local m = game:GetService("ReplicatedStorage").Promptimate.Performance; m.Source = ' + long_str(src) + '; return 1')


# ------------------------------------------------------------------------------------------------ pipeline
def main():
    # the whole production holds the machine-wide heavy lock: other agents' model tests wait instead of swapping RAM
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from heavy_lock import heavy
    import os
    if os.environ.get("PROMPTIMATE_HEAVY_HELD"):
        return _main()
    os.environ["PROMPTIMATE_HEAVY_HELD"] = "1"
    with heavy("episode producer"):
        return _main()


def audio_assets(ep, total: float, out: Path):
    """The mixed soundtrack and the caption file for a video of `total` seconds."""
    wav, placed, credits = mix(ep, total, out)
    cap = getattr(ep, "CAPTIONS", {})
    captions.size = cap.get("size", 84)   # sentence case Montserrat reads larger than the old all-caps Arial Black
    captions.keywords = getattr(ep, "KEYWORDS", ())
    captions.pos = cap.get("pos", "low")      # below the faces (~65% down); at the top they sat on hats
    ass = captions(placed, out / "captions.ass", titles=getattr(ep, "TITLES", []), highlight=cap.get("highlight", True),
                   max_words=cap.get("max_words", 3),
                   labels=[(float(sp[0]), float(sp[1]), str(sp[2]) if len(sp) > 2 else str(f.get("text") or ""))
                           for f in getattr(ep, "FX", []) if f.get("kind") == "label" for sp in f["show"]])
    return wav, ass, credits


def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--from", dest="start", default="cast", choices=["cast", "perform", "record", "audio"])
    ap.add_argument("--rounds", type=int, default=0, help="repair rounds in roblox_perform")
    ap.add_argument("--voice", default=None, help="override the narrator (af_heart, tv_M2, ...)")
    ap.add_argument("--suffix", default="", help="append to the output file name")
    ap.add_argument("--offline", action="store_true", help="record without Studio (Python director + GPU checks + headless render)")
    ap.add_argument("--headless", action="store_true", help="render offscreen (roblox/headless) instead of screen-recording Studio")
    ap.add_argument("--attempts", type=int, default=2, help="seeds tried per beat for facing/mark/seat")
    a = ap.parse_args()
    st_path = Path(a.episode)
    if a.episode.endswith(".py") or (HERE / "stories" / f"{a.episode}.py").exists() and not (HERE / "eps" / f"{a.episode}.py").exists():
        # a compact story (stories/<slug>.py): compiled here, in-process, into eps/<slug>.py
        import story_compile as SC
        st_path = st_path if st_path.suffix == ".py" else HERE / "stories" / f"{a.episode}.py"
        t = time.time()
        (HERE / "eps" / f"{st_path.stem}.py").write_text(SC.compile_story(SC.load(st_path), st_path.stem), encoding="utf-8")
        a.episode = st_path.stem
        log(f"compiled story {st_path.name} {time.time() - t:.1f}s")
    ep = importlib.import_module(f"eps.{a.episode}")
    if a.voice:
        ep.VOICE = a.voice
        if a.voice.startswith("tv_") and ep.SPEED < 1.2:
            ep.SPEED = 1.35
    out = BUILD / a.episode
    out.mkdir(parents=True, exist_ok=True)
    pace(ep, out)
    audio_job = None
    # every environment key this run sets exists before the audio thread starts: a key added to os.environ while
    # another thread copies it raised "dictionary changed size during iteration" (intermittent production crash)
    os.environ.setdefault("PROMPTIMATE_RBX_TAKES", "1")
    os.environ.setdefault("PROMPTIMATE_SKIP_PREVIEW", "1")
    os.environ["PROMPTIMATE_REPAIR_ROUNDS"] = str(a.rounds)
    os.environ["PROMPTIMATE_RBX_ATTEMPTS"] = str(a.attempts)
    if (a.offline or a.headless) and a.start in ("cast", "perform", "record") and getattr(ep, "LENGTH", None):
        # the soundtrack and captions only need the paced lines: mix them while the motion is generated
        import concurrent.futures as _cf
        audio_job = _cf.ThreadPoolExecutor(1).submit(audio_assets, ep, int(float(ep.LENGTH) * 30) / 30, out)
    T = {}
    t_all = time.time()
    steps = ["cast", "perform", "record", "audio"]
    todo = steps[steps.index(a.start):]
    if "perform" in todo and "cast" not in todo:
        todo.insert(0, "cast")      # rigs back on their marks: perform measures where they stand
    import server  # noqa: F401  (registers the Roblox tools: sets their server module)
    import roblox_record as RR
    if "cast" in todo and a.offline:
        log("cast: offline (looks and props come from the headless library)")
    elif "cast" in todo:
        import cast as CAST
        t = time.time()
        r = CAST.ensure(ep.CAST)
        bad = {k: v for k, v in r.items() if v != "ok"}
        if bad:
            raise SystemExit(f"cast failed: {bad}")
        if getattr(ep, "PLACE", None):      # sourced props for this story (sets.py prop library)
            import sets as SETS
            pr = SETS.place(ep.PLACE)
            if pr.get("missing"):
                raise SystemExit(f"props missing from the library: {pr['missing']}")
            log("props", len(pr["placed"]))
        T["cast"] = time.time() - t
        log("cast", r, f"{T['cast']:.0f}s")
    if "perform" in todo:
        os.environ.setdefault("PROMPTIMATE_RBX_TAKES", "1")
        os.environ.setdefault("PROMPTIMATE_SKIP_PREVIEW", "1")   # the per-clip preview sheet was 80% of perform's CPU
        # every prompt text-encoded up front under one encoder load (otherwise it reloads every few clips)
        prompts = []
        for act in ep.ACTORS:
            for bt in act.get("beats", []):
                pr = bt.get("prompt")
                prompts += pr if isinstance(pr, list) else [pr]
        try:
            t = time.time()
            import server as _srv
            res = json.loads(_srv.prefetch_prompts(sorted({p for p in prompts if p})))
            log(f"prefetch {len(set(prompts))} prompts {time.time() - t:.0f}s", {k: v for k, v in res.items() if not isinstance(v, list)}
                if isinstance(res, dict) else res)
        except Exception as e:
            log("prefetch skipped:", e)
        # a clean cue sheet: only this episode's characters perform (earlier episodes' entries would be posed too)
        from roblox_studio import studio
        if not a.offline:
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
        RT.REPAIR_ROUNDS = a.rounds      # read at import time (server was imported above): set it directly
        sys.path.insert(0, str(ROOT / "roblox" / "short"))
        import fastgrab as FG
        t = time.time()
        if a.offline:       # staging on our own geometry (roblox/headless/stage.py), no Studio
            sys.path.insert(0, str(ROOT / "roblox" / "headless"))
            import stage as WLD
            import director as DRC
            import pipeline as HL0
            st_json = json.loads(HL0.static_for(ep).read_text())
            RT.WORLD = WLD.Staging(WLD.World(st_json, DRC.props_at_home(ep, st_json)), ep.CAST)
            log(f"staging world {time.time() - t:.1f}s")
            try:
                res = RT.perform([RT.Actor(**x) for x in ep.ACTORS])
            finally:
                RT.WORLD = None
        else:
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
        import shutil
        if not a.offline:      # Studio's cue sheet, package and light (the offline path reads the episode directly)
            annotate(ep)
            # always a fresh recording: rig attributes (arms, looks) aren't part of the frame-reuse signature, and the
            # director caches clip players built from the old rigs
            shutil.rmtree(RR.STATE / "record" / a.episode / "frames_final", ignore_errors=True)
            import roblox_tools as _RT
            log("package", _RT.install())       # pushes changed player/director code to Studio
            sys.path.insert(0, str(ROOT / "roblox" / "short"))
            import town as _town
            from roblox_studio import studio as _st
            _st().luau(getattr(ep, "LIGHT", None) or _town.LIGHT)     # the shared cinematic look (an episode may bring its own)
        t = time.time()
        cams = [RR.CameraCue(**c) for c in ep.CAMERAS]
        RR.cover.cut_times = sorted(ln[0] for ln in ep.LINES)     # coverage cuts on the sentence starts
        if a.headless or a.offline:
            sys.path.insert(0, str(ROOT / "roblox" / "headless"))
            import pipeline as HL
            # sound and captions first (they only need the length): the render burns the captions and muxes the mix
            # in its own encode, so the finished video exists the moment the last frame is drawn
            t_end = getattr(ep, "LENGTH", None) or RR.Perf().end()
            total = int(t_end * 30) / 30
            if audio_job is not None and abs(total - int(float(ep.LENGTH) * 30) / 30) < 1e-6:
                wav, ass, credits = audio_job.result()
            else:
                wav, ass, credits = audio_assets(ep, total, out)
            final = out / f"{a.episode}{a.suffix}.mp4"
            if a.offline:
                r = HL.record_offline(ep, cams, a.episode, 30, t_end, final, log=log, ass=str(ass),
                                      fonts=str(BUILD / "_media" / "fonts"), wav=str(wav))
            else:
                r = HL.record(cams, a.episode, 30, t_end, final, log=log, ass=str(ass),
                              fonts=str(BUILD / "_media" / "fonts"), wav=str(wav))
            (out / "credits.txt").write_text("\n".join([getattr(ep, "TITLE", a.episode), "", *credits,
                                                        "Narration: Kokoro TTS (Apache-2.0)"]) + "\n", encoding="utf-8")
            T["record"] = time.time() - t
            log(f"record+audio (headless) {T['record']:.0f}s {r['timing']} -> {final}")
            todo = [s_ for s_ in todo if s_ != "audio"]
        else:
            r = RR.record(cams, name=a.episode, quality="final", end=getattr(ep, "LENGTH", None), fps=30)
            info = json.loads(r[0])
            for w in info.get("camera_warnings", [])[:8]:
                log("   cam!", w)
            for w in info.get("image_qa", []):
                log("   qa:", w)
            last = None
            while True:
                time.sleep(3)
                st = json.loads(RR.record([], job=info["job"])[0])
                if st.get("state") != last:      # where record time goes: lock wait, live pass, filling skipped frames
                    last = st.get("state")
                    log("   record:", last, {k: st[k] for k in ("done", "total", "live", "live_error") if k in st})
                if st.get("state") in ("done", "failed", "cancelled"):
                    log("   record done:", {k: st[k] for k in ("render_s", "mode", "live", "live_frames", "live_error", "fast_error") if k in st})
                    break
            if st["state"] != "done":
                raise SystemExit(f"record {st}")
            (out / "silent.mp4").write_bytes(Path(st["mp4"]).read_bytes())
            # the PNG frames are 3-11 GB per episode and nothing reads them after the encode (a full disk killed a record)
            shutil.rmtree(RR.STATE / "record" / a.episode / "frames_final", ignore_errors=True)
            T["record"] = time.time() - t
            log(f"record {T['record']:.0f}s")
    if "audio" in todo:
        t = time.time()
        silent = out / "silent.mp4"
        total = duration(silent)
        wav, ass, credits = audio_assets(ep, total, out)
        final = out / f"{a.episode}{a.suffix}.mp4"
        fonts = str(BUILD / "_media" / "fonts").replace("\\", "/").replace(":", "\\:")   # Montserrat (OFL, not in git)
        assp = str(ass).replace("\\", "/").replace(":", "\\:")
        run([FF, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-filter_complex",
             f"[0:v]ass='{assp}':fontsdir='{fonts}'[v]", "-map", "[v]", "-map", "1:a", *RR._venc(), "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(final)])
        (out / "credits.txt").write_text("\n".join([getattr(ep, "TITLE", a.episode), "", *credits,
                                                    "Narration: Kokoro TTS (Apache-2.0)"]) + "\n", encoding="utf-8")
        T["audio"] = time.time() - t
        log(f"audio+captions {T['audio']:.0f}s -> {final}")
    T["total"] = time.time() - t_all
    (out / "timing.json").write_text(json.dumps({k: round(v, 1) for k, v in T.items()}))
    log("timing", {k: round(v) for k, v in T.items()})


if __name__ == "__main__":
    main()
