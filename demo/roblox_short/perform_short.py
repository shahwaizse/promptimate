"""Re-make the 'In this town, you can't sit down' short with only the new Promptimate Roblox tools, driven the way a
creator's Claude drives them: an MCP client session to the kimodo-motion server, a shot list per character, staging
warnings read and fixed, then camera cues checked and recorded. Every tool call and every token sent/returned is
counted (.cache/roblox_short/v2/calls.json).

    .venv\\Scripts\\python.exe demo\\roblox_short\\perform_short.py setup        # creator's own step: cast + benches
    .venv\\Scripts\\python.exe demo\\roblox_short\\perform_short.py perform 1    # round 1 shot lists (first draft)
    .venv\\Scripts\\python.exe demo\\roblox_short\\perform_short.py perform 2    # round 2 (fixes for round-1 warnings)
    .venv\\Scripts\\python.exe demo\\roblox_short\\perform_short.py cameras 1|2  # camera checks (check_only)
    .venv\\Scripts\\python.exe demo\\roblox_short\\perform_short.py record       # final render (+ status polls)
    .venv\\Scripts\\python.exe demo\\roblox_short\\perform_short.py report       # token/call summary
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".cache" / "roblox_short" / "v2"
LOG = OUT / "calls.json"
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

# ------------------------------------------------------------------------------------------------ the shot lists
# Round 1 = what a creator's Claude writes first from the story (positions read off the place).
TIMMY = {"name": "Timmy", "start": [-13, 2.4], "facing": "+X", "beats": [
    {"prompt": "a person walks forward slowly and tiredly with their head down", "seconds": 4.0, "to": "Bench"},
    {"prompt": ["a person turns around and sits down", "a person sits and leans back, relaxing"], "seconds": [2.0, 1.0],
     "sit": "Bench"},
    {"prompt": "a person sits and holds a phone to their right ear with their right hand", "seconds": 3.5, "sit": "Bench"},
    {"prompt": ["a person stands up quickly and turns to the left", "a person runs forward, then stops"],
     "seconds": [1.0, 3.8], "via": [[7.5, 1.6], [15.8, 1.6]], "to": [15.8, 3.2], "face": "-X"},
    {"prompt": "a person crouches down low and hides", "seconds": 2.2, "face": "-X"},
    {"prompt": "a person crouches and leans to the right to peek out", "seconds": 2.5, "peek": "right"},
    {"prompt": "a person crouches low and stays still, hiding", "seconds": 3.0, "face": "-X"},
    {"prompt": "a person gets startled and falls backward onto their back", "seconds": 2.5},
    {"prompt": "a person sits up on the ground and looks up", "seconds": 3.5},
    {"prompt": ["a person gets up from the ground", "a person walks forward", "a person turns around and sits down"],
     "seconds": [1.5, 2.0, 1.5], "sit": "Bench2", "sit_from": 4.0},
    {"prompt": "a person sits and leans back, relaxing", "seconds": 2.5, "sit": "Bench2"},
]}
OFFICER = {"name": "Officer", "start": [-24, 7.5], "facing": "+X", "beats": [
    {"at": 7.5, "prompt": ["a person walks forward confidently", "a person stops and stands still"],
     "seconds": [4.8, 1.2], "to": [-3.5, 7.5]},
    {"prompt": ["a person looks around to the left and to the right, searching", "a person turns to the left and looks"],
     "seconds": [2.5, 1.5], "face": "MrsLee"},
    {"prompt": ["a person walks forward quickly", "a person stops"], "seconds": [4.8, 0.7],
     "via": [[8.0, 12.6], [16.0, 12.6]], "to": "Timmy", "face": "Timmy"},
    {"prompt": ["a person leans forward, raising both arms to scare someone",
                "a person stands with their hands on their hips"], "seconds": [1.2, 1.3], "face": "Timmy"},
    {"prompt": "a person talks and gestures with both hands", "seconds": 3.5, "face": "Timmy"},
    {"prompt": ["a person turns and walks forward", "a person turns around and sits down"], "seconds": [2.5, 2.0],
     "sit": "Bench2", "sit_from": 3.0},
    {"prompt": "a person sits and leans back, relaxing", "seconds": 3.0, "sit": "Bench2"},
]}
LEE = {"name": "MrsLee", "start": [7, -2.6], "facing": "+Z", "beats": [
    {"prompt": ["a person stands still and shifts their weight", "a person stands still and looks around"],
     "seconds": [8.0, 8.5]},
    {"prompt": "a person turns to the left and points forward with their left arm", "seconds": 2.5, "face": "Crates"},
    {"prompt": ["a person crosses their arms", "a person stands with their arms crossed and taps their foot"],
     "seconds": [3.0, 14.5]},
]}

# Round 2 = edits after reading round 1's warnings (filled in from the round-1 result; see README)
FIXES: dict = {
    # warnings: SignSmall/NoSitting beside the bench's left end -> walk to the middle of the bench, sit there
    # (+ the creator moved Bench2 off the lamp post the Officer walked through; see creator_setup.luau)
    "Timmy": {"beats": {"0": {"to": [-0.5, 3.6]},
                        # "seat off by 39 cm" on get up -> walk -> sit: more time for the walk
                        "9": {"seconds": [1.5, 2.5, 1.5], "sit_from": 4.5},
                        "10": {"at": 34.5}}},
    "Officer": {},
    # Mrs. Lee drifted 12 studs through the shop door while idling: the tool now keeps stationary beats in place
    "MrsLee": {},
}

# Round 3 = edits after round 2's warnings ("passes through TrashCan" on the walk-in, "passes through CrateDBand" on
# the run); the tool itself also gained in-place stationary beats, a landing check for falls and the seat/mark warp.
FIXES3: dict = {
    "Timmy": {"start": [-13, 3.4],
              "beats": {"0": {"to": [-0.5, 3.6]}, "3": {"via": [[7.5, 0.8], [16.3, 0.8]]},
                        "9": {"seconds": [1.5, 2.5, 1.5], "sit_from": 4.5}, "10": {"at": 34.5}}},
    # "passes through CrateA" while scaring/talking: his gesturing arm reaches the crates -> come round from +X
    # (first try via (19.5, 8.5) cut through Bench2's end: "LeftFoot sinks 1.0 studs" -> waypoint west of the bench)
    # (then "passes through Bench2.BackLeg" once Bench2 was lengthened -> waypoint at x 16.3; and "passes through
    # LampPole" on the way to sit -> round the bench's far (east) end)
    "Officer": {"beats": {"2": {"via": [[8.0, 12.6], [15.5, 12.6], [16.3, 8.0]]},
                          "5": {"via": [[26.5, 8.0], [26.5, 11.3]]}}},
    # "passes through Door/DoorGlass/Base" for the whole short: her mark was inside the shop doorway
    "MrsLee": {"start": [7, -1.2]},
}

# camera cues: story time, static pos/look or tracking; fov = vertical fov of the 9:16 frame
CAMERAS_1 = [
    {"start": 0.0, "pos": [-6, 12, 30], "look": [-6, 2, 3], "fov": 62, "name": "wide street"},
    {"start": 1.6, "pos": [-4, 4.6, 7.5], "look": [-4.6, 4.4, 0.4], "fov": 40, "name": "sign", "subjects": []},
    {"start": 3.0, "track": "Timmy", "offset": [6.5, 1.6, 5.5], "aim": [0, 1, 0], "fov": 55, "name": "follow Timmy"},
    {"start": 4.4, "pos": [-1.5, 3.8, 12.5], "look": [-2.5, 2.2, 1.6], "fov": 50, "name": "sits"},
    {"start": 7.0, "pos": [-0.5, 3.0, 5.5], "look": [-2.6, 2.6, 1.4], "fov": 45, "name": "phone close"},
    {"start": 8.7, "track": "Officer", "offset": [8.5, 0.6, 7.0], "aim": [0, 1.2, 0], "fov": 52, "name": "officer marches"},
    {"start": 10.4, "pos": [-1.5, 3.6, 11.0], "look": [-1.5, 2.6, 2.0], "fov": 52, "name": "jumps up"},
    {"start": 11.6, "track": "Timmy", "offset": [0, 6, 17], "aim": [0, 1, 0], "fov": 60, "name": "run side track"},
    {"start": 15.1, "pos": [-4.5, 4.2, 15], "look": [-3.5, 3.0, 7.5], "fov": 50, "name": "officer looks"},
    {"start": 16.5, "pos": [6.0, 4.2, 6.5], "look": [7.0, 3.6, -2.6], "fov": 50, "name": "Lee points"},
    {"start": 18.3, "pos": [21.5, 4.8, 3.0], "look": [8.0, 3.0, 10.0], "fov": 55, "name": "over Timmy"},
    {"start": 19.7, "pos": [17.5, 3.4, -4.5], "look": [15.4, 2.2, 2.6], "fov": 42, "name": "peek close"},
    {"start": 21.3, "track": "Officer", "offset": [3.5, 1.0, 5.0], "aim": [0, 1.8, 0], "fov": 55, "name": "officer rounds"},
    {"start": 23.0, "pos": [24, 4, 4], "look": [16, 2.4, 4.5], "fov": 55, "name": "BOO"},
    {"start": 24.3, "pos": [21, 8.5, 1.5], "look": [17, 0.8, 3.8], "fov": 50, "name": "Timmy on the ground"},
    {"start": 26.0, "pos": [19, 1.4, 0.5], "look": [16, 4.2, 5.8], "fov": 60, "name": "officer talks"},
    {"start": 29.0, "pos": [27, 4.5, 21], "look": [19, 2, 8], "fov": 55, "name": "walk to the bench"},
    {"start": 32.5, "pos": [21, 3.4, 18.0], "look": [21, 2.2, 10.0], "fov": 48, "name": "both sit"},
    {"start": 34.8, "pos": [33, 13, 28], "look": [19, 2, 8], "fov": 55, "name": "wide ending"},
]
# Round 2: fixes for round 1's camera warnings and what the shot sheet showed (tight framing, stale look points)
_C2 = {
    "sits": {"look": [-0.6, 2.2, 1.6]},                                          # aimed at the old seat spot
    "phone close": {"pos": [1.6, 3.0, 5.5], "look": [-0.6, 2.4, 1.4]},           # Timmy at the frame edge
    # "Timmy hidden behind CrateB" (still at 13 studs up): steep top-down track over the crates
    "run side track": {"offset": [0, 22, 8], "aim": [0, 0, 0], "fov": 50},
    # "Officer hidden behind CrateB": the crates block Timmy's line of sight by design -> show the Officer from the street
    "over Timmy": {"track": "Officer", "offset": [-2.5, 1.5, 9.5], "aim": [0, 1, 0], "pos": None, "look": None,
                   "subjects": ["Officer"]},
    "peek close": {"pos": [19.0, 3.2, -2.5], "look": [15.6, 1.8, 2.6], "subjects": ["Timmy"]},  # "inside Body"
    "officer rounds": {"offset": [6, 2, 8]},                                     # sheet: too tight
    "BOO": {"pos": [26, 4.5, 1], "look": [16.3, 2.2, 4.2], "fov": 50},
    "Timmy on the ground": {"pos": [20, 9, -1], "look": [16, 0.5, 3.2]},
    "officer talks": {"pos": [22, 1.6, -1], "look": [16.5, 3.6, 5.3], "fov": 55},
    # (round 2b: "Timmy hidden behind Officer" / "out of frame" -> high angle; "Officer hidden behind LampPole" ->
    # centre the camera on the pair so the post falls between them)
    "walk to the bench": {"pos": [21, 10, 26], "look": [21, 1.5, 7], "fov": 58, "subjects": ["Timmy", "Officer"]},
    "both sit": {"pos": [21, 3.6, 20.5], "look": [21, 2.2, 10], "fov": 56},
    "wide ending": {"subjects": ["Timmy", "Officer"]},
}
CAMERAS_2: list = [dict(c, **_C2.get(c["name"], {})) for c in CAMERAS_1]


# ------------------------------------------------------------------------------------------------ MCP client
def _log() -> list:
    return json.loads(LOG.read_text()) if LOG.exists() else []


def tokens_text(s: str) -> int:
    return max(1, round(len(s) / 3.6))


def tokens_image(b64: str) -> tuple[int, tuple[int, int]]:
    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(b64)))
    w, h = im.size
    s = min(1.0, 1568 / max(w, h))            # Claude downsizes images with a long edge over 1568 px
    w, h = int(w * s), int(h * s)
    return round(w * h / 750), (w, h)


async def call_tools(calls: list[tuple[str, dict]], stage: str):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    env = dict(os.environ, TEMP=r"D:\tmp", TMP=r"D:\tmp", PYTHONIOENCODING="utf-8",
               UNITY_PROJECT=str(ROOT / ".cache" / "no_unity_project"), PROMPTIMATE_PREWARM="0")
    params = StdioServerParameters(command=PY, args=[str(ROOT / "mcp_server" / "server.py")], env=env,
                                   cwd=str(ROOT / "mcp_server"))
    log = _log()
    results = []
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w, read_timeout_seconds=None) as s:
            await s.initialize()
            for tool, args in calls:
                t0 = time.time()
                res = await s.call_tool(tool, args, read_timeout_seconds=None)
                dt = time.time() - t0
                text = "".join(c.text for c in res.content if getattr(c, "type", "") == "text")
                imgs = [c.data for c in res.content if getattr(c, "type", "") == "image"]
                img_tok = [tokens_image(b) for b in imgs]
                OUT.mkdir(parents=True, exist_ok=True)
                for k, b in enumerate(imgs):
                    (OUT / f"{stage}_{len(log)}_{k}.png").write_bytes(base64.b64decode(b))
                entry = {"stage": stage, "tool": tool, "seconds": round(dt, 1), "sent_tokens": tokens_text(json.dumps(args)),
                         "returned_text_chars": len(text), "returned_text_tokens": tokens_text(text),
                         "returned_image_tokens": sum(t for t, _ in img_tok), "images": [list(sz) for _, sz in img_tok],
                         "is_error": res.isError, "text": text}
                log.append(entry)
                LOG.write_text(json.dumps(log, indent=1))
                print(f"[{stage}] {tool} {dt:.0f}s  returned {entry['returned_text_tokens']} text + "
                      f"{entry['returned_image_tokens']} image tokens\n{text[:3000]}\n", flush=True)
                results.append((text, imgs))
    return results


def apply_fixes(actor: dict, fixes: dict) -> dict:
    a = json.loads(json.dumps(actor))
    for k, v in fixes.get(a["name"], {}).items():
        if k == "beats":
            for i, patch in v.items():
                a["beats"][int(i)].update(patch)
        else:
            a[k] = v
    return a


def studio_setup():
    sys.path.insert(0, str(ROOT / "mcp_server"))
    from roblox_studio import studio
    print(studio().luau((ROOT / "demo" / "roblox_short" / "creator_setup.luau").read_text(encoding="utf-8")))


def main():
    cmd = sys.argv[1]
    if cmd == "setup":
        studio_setup()
    elif cmd == "perform":
        rnd = int(sys.argv[2])
        cast = [TIMMY, OFFICER, LEE]
        if rnd == 2:
            cast = [apply_fixes(a, FIXES) for a in cast if a["name"] in FIXES]
        elif rnd == 3:
            cast = [apply_fixes(a, FIXES3) for a in cast if a["name"] in FIXES3]
        only = sys.argv[3].split(",") if len(sys.argv) > 3 else None
        if rnd == 4:   # final pass: the two bench-sharers in one call (seat spots assigned together), then Lee
            cast = [apply_fixes(a, FIXES3) for a in [TIMMY, OFFICER, LEE]]
            calls = [("roblox_perform", {"actors": cast[:2]}), ("roblox_perform", {"actors": cast[2:]})]
        else:
            calls = [("roblox_perform", {"actors": [a]}) for a in cast if not only or a["name"] in only]
        asyncio.run(call_tools(calls, f"perform{rnd}"))
    elif cmd == "cameras":
        rnd = int(sys.argv[2])
        cams = CAMERAS_1 if rnd == 1 else CAMERAS_2
        asyncio.run(call_tools([("roblox_record", {"shots": cams, "check_only": True, "name": "sitdown_v2"})],
                               f"cameras{rnd}"))
    elif cmd == "record":
        cams = CAMERAS_2 or CAMERAS_1
        quality = sys.argv[2] if len(sys.argv) > 2 else "final"
        asyncio.run(record_and_poll(cams, quality))
    elif cmd == "report":
        report()


async def record_and_poll(cams, quality):
    """One session: start the render, then poll like an agent would (every ~10 minutes)."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    env = dict(os.environ, TEMP=r"D:\tmp", TMP=r"D:\tmp", PYTHONIOENCODING="utf-8",
               UNITY_PROJECT=str(ROOT / ".cache" / "no_unity_project"), PROMPTIMATE_PREWARM="0")
    params = StdioServerParameters(command=PY, args=[str(ROOT / "mcp_server" / "server.py")], env=env,
                                   cwd=str(ROOT / "mcp_server"))
    log = _log()

    async def one(s, tool, args, stage):
        t0 = time.time()
        res = await s.call_tool(tool, args, read_timeout_seconds=None)
        text = "".join(c.text for c in res.content if getattr(c, "type", "") == "text")
        imgs = [c.data for c in res.content if getattr(c, "type", "") == "image"]
        img_tok = [tokens_image(b) for b in imgs]
        for k, b in enumerate(imgs):
            (OUT / f"{stage}_{len(log)}_{k}.png").write_bytes(base64.b64decode(b))
        log.append({"stage": stage, "tool": tool, "seconds": round(time.time() - t0, 1),
                    "sent_tokens": tokens_text(json.dumps(args)), "returned_text_chars": len(text),
                    "returned_text_tokens": tokens_text(text), "returned_image_tokens": sum(t for t, _ in img_tok),
                    "images": [list(sz) for _, sz in img_tok], "is_error": res.isError, "text": text})
        LOG.write_text(json.dumps(log, indent=1))
        print(f"[{stage}] {tool}: {text[:1500]}", flush=True)
        return text

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w, read_timeout_seconds=None) as s:
            await s.initialize()
            text = await one(s, "roblox_record", {"shots": cams, "quality": quality, "name": "sitdown_v2",
                                                  "sheet": False}, "record")
            job = json.loads(text)["job"]
            while True:
                await asyncio.sleep(600)
                st = json.loads(await one(s, "roblox_record", {"job": job}, "record_poll"))
                if st.get("state") in ("done", "failed", "cancelled"):
                    break


def baseline() -> dict:
    """What the demo's hand-built Promptimate pipeline (version B) costs if the creator's Claude drives it through
    generate_motion + Studio's MCP, from the demo's own artefacts: one generate_motion call per clip attempt (meta
    JSON + preview + takes sheet returned), every clip uploaded as a ModuleScript through execute_luau (the clip
    data has to be written by the model as tool input), the calibration and director setup calls, and one
    execute_luau + 3 screen_captures per frame for the stitched 9:16 render (each capture returns an image)."""
    from PIL import Image
    gens = [d for d in sorted((ROOT / "output").glob("rs_*")) if (d / "meta.json").exists()]
    meta_tok, img_tok = 0, 0
    for d in gens:
        meta_tok += tokens_text(json.dumps(json.loads((d / "meta.json").read_text()), indent=2))
        for im in ("preview.png", "takes.png"):
            if (d / im).exists():
                w, h = Image.open(d / im).size
                sc = min(1.0, 1568 / max(w, h))
                img_tok += round(w * sc * h * sc / 750)
    lua = sorted((ROOT / "roblox" / "out").glob("rs_*.lua"))
    lua_chars = sum(f.stat().st_size for f in lua)
    frames = round(32.6 * 24)
    cap_tok = round(1452 * 793 / 750)
    return {"generate_motion_calls": len(gens), "generate_returned_tokens": meta_tok + img_tok,
            "upload_calls": len(lua) + 4, "upload_sent_tokens": tokens_text("x" * lua_chars),
            "upload_note": f"{len(lua)} clip modules, {lua_chars:,} chars of clip data (2 over the 200k source limit, "
                           "hand-chunked)",
            "setup_calibration_calls": 12,
            "render_calls": frames * 4, "render_returned_tokens": frames * 3 * cap_tok,
            "total_calls": len(gens) + len(lua) + 4 + 12 + frames * 4,
            "total_returned_tokens_excl_render": meta_tok + img_tok,
            "total_sent_tokens": tokens_text("x" * lua_chars)}


def report():
    log = _log()
    tot = {"calls": len(log), "sent": sum(e["sent_tokens"] for e in log),
           "returned_text": sum(e["returned_text_tokens"] for e in log),
           "returned_images": sum(e["returned_image_tokens"] for e in log)}
    by = {}
    for e in log:
        b = by.setdefault(f"{e['stage']}:{e['tool']}", {"calls": 0, "sent": 0, "text": 0, "img": 0, "s": 0})
        b["calls"] += 1
        b["sent"] += e["sent_tokens"]
        b["text"] += e["returned_text_tokens"]
        b["img"] += e["returned_image_tokens"]
        b["s"] += e["seconds"]
    rep = {"tool_driven": {"total": tot, "by_stage": by}, "hand_built_baseline": baseline()}
    print(json.dumps(rep, indent=1))
    (OUT / "token_report.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
