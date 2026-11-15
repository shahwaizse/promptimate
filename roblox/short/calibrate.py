"""Calibrate seat/ground contact for the comparison short (run after gen_b.py and gen_c.py).

1. B: pose Timmy in his generated seated clips, measure the thighs' underside and hips -> build the bench there
   (one shared bench for all versions; B's sit lands where its root_path put it).
2. A: stock sit pose on a Seat: HRP offset so the thighs rest on that bench; stock sit on the ground for the officer.
3. C: each generated clip that sits/falls/crouches: HRP offset so it rests on the bench or the ground at its key time
   (the per-clip tweak a creator would make by hand; root motion inside the clips is left as generated).
Writes .cache/roblox_short/calibration.json and rebuilds the bench (town.py --bench-only logic).
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "roblox" / "tools"))
import perf  # noqa: E402
import render  # noqa: E402
import story as S  # noqa: E402
import town  # noqa: E402
from studio_mcp import StudioSession  # noqa: E402

CACHE = ROOT / ".cache" / "roblox_short"
THIGHS = ["LowerTorso", "LeftUpperLeg", "RightUpperLeg"]
BODY = ["Head", "UpperTorso", "LowerTorso", "LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm", "RightLowerArm",
        "RightHand", "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperLeg", "RightLowerLeg", "RightFoot"]


async def lowest(s, who, parts):
    r = await s.luau(f"return _G.ShortDirector.lowest({json.dumps(who)}, {render._long(json.dumps(parts))})")
    v = r["content"][0].split(",")
    return float(v[0]), v[1], (float(v[2]), float(v[3]), float(v[4]))


async def pose_anim(s, who, key, t, x, y, z, yaw):
    await render.apply(s, {who: {"cf": [x, y, z, yaw, 0], "tracks": [[key, t, 1.0, False]], "phone": False}})


async def main():
    cal = json.loads((CACHE / "calibration.json").read_text()) if (CACHE / "calibration.json").exists() else {}
    PZ = S.yaw_of(S.PZ)
    async with StudioSession() as s:
        await asyncio.sleep(3)
        # ---------------- B: bench from the generated seated poses
        info = await render.setup(s, "B")
        chars = perf.build("B", info)
        lows, lts = [], []
        for t in (6.2, 6.9, 7.8, 9.0, 10.3):
            inst, _ = perf.frame({"timmy": chars["timmy"]}, t)
            await render.apply(s, inst)
            lo, part, lt = await lowest(s, "timmy", THIGHS)
            lows.append(lo)
            lts.append(lt)
        seat_top = round(min(lows), 3)
        bx = round(sum(p[0] for p in lts) / len(lts), 3)
        bz = round(sum(p[2] for p in lts) / len(lts) + 0.3, 3)       # bench centre slightly in front of the hips
        cal["bench"] = {"seat_top": seat_top, "x": bx, "z": bz, "b_thigh_lows": lows, "b_hips": lts}
        print("bench", cal["bench"], flush=True)
        S.BENCH["center"] = (bx, bz)
        print((await s.luau(town.bench_code(seat_top)))["content"], flush=True)
        target_lt = (bx, bz - 0.3)

        # ---------------- A: stock sit on the bench, stock sit on the ground
        info = await render.setup(s, "A")
        A = {}
        hy = info["timmy"]["hrpY"]
        await pose_anim(s, "timmy", perf.ID["sit"], 0.3, 0, hy, 0, PZ)
        lo, _, lt = await lowest(s, "timmy", THIGHS)
        A["a_sit_y"] = round(seat_top - lo, 3)
        A["seat"] = [round(target_lt[0] - lt[0], 3), round(target_lt[1] - lt[2], 3)]
        A["seat_dz"] = round(A["seat"][1] - S.BENCH["center"][1], 3)
        hy_o = info["officer"]["hrpY"]
        await pose_anim(s, "officer", perf.ID["sit"], 0.3, 0, hy_o, 0, PZ)
        lo, _, _ = await lowest(s, "officer", THIGHS)
        A["a_gsit_y"] = round(0.0 - lo, 3)
        cal["A"] = A
        print("A", A, flush=True)

        # ---------------- C: generated clips
        g = json.loads((CACHE / "c_gens.json").read_text())
        C = {}
        stand = S.PATHS["timmy_walk"][-1][1]
        info = await render.setup(s, "C")
        hy = info["timmy"]["hrpY"]
        for key, t_key, mode in (("t_sit", 2.8, "seat"), ("t_phone", 1.7, "seat"), ("t_up", 0.0, "seat")):
            if not g.get(key, {}).get("clip"):
                continue
            await pose_anim(s, "timmy", "kfs:" + g[key]["clip"], t_key, stand[0], hy, stand[1], PZ)
            lo, _, lt = await lowest(s, "timmy", THIGHS)
            short = key[2:]
            C[f"c_{short}_y"] = round(seat_top - lo, 3)
            C[f"c_{short}_dz"] = round(target_lt[1] - lt[2], 3)
        for key, who, times, name in (("t_hide", "timmy", (0.5, 2.0, 4.0, 6.0, 7.5), "c_hide_y"),
                                      ("t_fall", "timmy", (2.3, 2.45), "c_fall_y"),
                                      ("t_ground", "timmy", (1.0, 3.5, 6.5), "c_ground_y"),
                                      ("o_sit", "officer", (3.3, 3.5), "c_osit_y")):
            if not g.get(key, {}).get("clip"):
                continue
            h = info[who]["hrpY"]
            vals = []
            for t in times:
                await pose_anim(s, who, "kfs:" + g[key]["clip"], t, 0, h, 0, PZ)
                lo, _, _ = await lowest(s, who, BODY)
                vals.append(lo)
            C[name] = round(-min(vals), 3)
            C[name + "_lows"] = [round(v, 3) for v in vals]
        cal["C"] = C
        print("C", C, flush=True)
    (CACHE / "calibration.json").write_text(json.dumps(cal, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
