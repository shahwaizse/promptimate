"""Visual shot picking: for every subject shot of a recorded episode, render 8 different candidate framings (the real
renderer, the shot's middle instant) on one labelled sheet; a vision reviewer picks the best per shot; the next
recording uses the picks.

    python roblox/headless/shot_pick.py candidates <episode>   -> D:\\tmp\\headless\\<ep>\\pick\\shot_NNN.png + candidates.json
    PROMPTIMATE_SHOT_PICKS=<picks.json> produce.py <ep> --offline --from record          (pipeline applies them)

picks.json: {"<shot number>": "a".."h" or "keep"}
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "mcp_server"))
CACHE = Path(os.environ.get("PROMPTIMATE_HEADLESS_CACHE", r"D:\tmp\headless"))
LETTERS = "abcdefgh"


def key_of(name, start) -> str:
    return f"{name or ''}|{float(start):.2f}"


def candidates(ep: str, n_pick: int = 8) -> dict:
    import checks as CK
    import hlrender as RD
    import roblox_record as RR
    import audit as AU
    from PIL import Image, ImageDraw, ImageFont
    d = CACHE / ep
    shots = [RR.CameraCue(**c) for c in json.loads((d / "shots.json").read_text())]
    dyn = json.loads((d / "dynamic.json").read_text())
    names = dyn["order"]
    ck = CK.Checks(d, names, d / "frames.npz", 30)
    fr = np.load(d / "frames.npz")
    cams_final = np.load(d / "cams.npy")
    t_end = len(cams_final) / 30
    R = RD.Renderer(d, w=270, h=480)
    out = d / "pick"
    out.mkdir(exist_ok=True)
    for f in out.glob("shot_*.png"):
        f.unlink()
    font = ImageFont.truetype(str(HERE.parents[1] / "demo" / "episodes" / "build" / "_media" / "fonts" / "Montserrat-Black.ttf"), 40)
    table = {}
    for i, c in enumerate(shots):
        b = shots[i + 1].start if i + 1 < len(shots) else t_end
        if b - c.start < 0.25:
            continue
        if c.prop and not c.subject:
            # an insert: 8 views around the prop (front arc first), at two distances
            k = min(int(((c.start + b) / 2) * 30), len(cams_final) - 1)
            idx_p = [j for j, pp in enumerate(dyn["parts"]) if pp.get("owner") == "prop:" + c.prop]
            if not idx_p:
                continue
            P_ = fr["pose"][k, idx_p, :3].astype(float)
            P_ = P_[P_[:, 1] > -500]
            if not len(P_):
                continue
            cen = P_.mean(0) + np.array([0, 0.3, 0])
            base = cams_final[k, :3].astype(float) - cen
            base[1] = 0
            r0 = float(np.linalg.norm(base)) or 4.0
            base /= r0
            opts = [(cams_final[k, :3].tolist(), cams_final[k, 3:6].tolist(), float(cams_final[k, 6]))]
            for ang in (25, -25, 50, -50):
                for dist in (r0 * 0.8, r0 * 1.25):
                    a_ = math.radians(ang)
                    dvec = np.array([base[0] * math.cos(a_) - base[2] * math.sin(a_), 0, base[0] * math.sin(a_) + base[2] * math.cos(a_)])
                    cp = cen + dvec * dist + np.array([0, 0.6, 0])
                    opts.append((cp.tolist(), cen.tolist(), float(cams_final[k, 6])))
            opts = opts[:8]
            tm = (c.start + b) / 2
        elif not c.subject or c.subject not in names:
            continue
        else:
            opts = None
        if opts is not None:
            sheet = Image.new("RGB", (270 * 4, 480 * 2), (30, 30, 30))
            for m_, (p_, l_, fv) in enumerate(opts):
                img = R.frame(np.asarray(p_), np.asarray(l_), fv, RD.dyn_draws(R, fr["pose"][k], fr["face"][k], names,
                                                                                  scale_row=fr["scale"][k] if "scale" in fr.files else None))
                im = Image.frombytes("RGB", (270, 480), img).transpose(Image.FLIP_TOP_BOTTOM)
                dr = ImageDraw.Draw(im)
                dr.rectangle([0, 0, 46, 48], fill=(0, 0, 0))
                dr.text((8, 0), LETTERS[m_], font=font, fill=(255, 230, 60))
                sheet.paste(im, (270 * (m_ % 4), 480 * (m_ // 4)))
            num = len(table)
            sheet.save(out / f"shot_{num:03d}.png")
            table[str(num)] = {"key": key_of(c.name, c.start), "prop": c.prop, "start": round(c.start, 2), "end": round(b, 2),
                               "options": opts}
            continue
        tm = (c.start + b) / 2
        q = [[c.subject, tm]] + ([[c.with_, tm]] if c.with_ and c.with_ in names else [])
        poses = ck.poses(q)
        if not poses or not poses[0]:
            continue
        other = poses[1] if len(poses) > 1 else None
        cands = [(sz, ang, lift) for sz in ("medium", "full", "close", "wide") for lift in (0.0, 0.6)
                 for ang in range(0, 360, 30)]
        cams = [RR._cam_for(poses[0], other, sz, c.angle + ang, lift) for sz, ang, lift in cands]
        subs = [c.subject] + ([c.with_] if other else [])
        bad = np.zeros(len(cams))
        for f in (0.25, 0.5, 0.75):
            t = c.start + (b - c.start) * f
            ids, dep, _ = ck._render(t, cams)
            for j, cam in enumerate(cams):
                bad[j] += AU.judge(ck, ids[j], dep[j], *cam, subs, None, t)[0] is not None
        near = ck.near_batch([cm[0] for cm in cams], 0.6, tm)
        order = sorted(range(len(cams)), key=lambda j: (bad[j] + (3 if near[j] else 0), j))
        picked, used = [], set()
        for j in order:                   # diverse: one per (size, 60-degree sector)
            sz, ang, lift = cands[j]
            bucket = (sz, ((ang + 30) % 360) // 60)
            if bucket in used or bad[j] >= 3 or near[j]:
                continue
            used.add(bucket)
            picked.append(j)
            if len(picked) == n_pick - 1:
                break
        k = min(int(tm * 30), len(cams_final) - 1)
        opts = [(cams_final[k, :3].tolist(), cams_final[k, 3:6].tolist(), float(cams_final[k, 6]))] + \
               [(list(map(float, cams[j][0])), list(map(float, cams[j][1])), float(cams[j][2])) for j in picked]
        sheet = Image.new("RGB", (270 * 4, 480 * 2), (30, 30, 30))
        for m, (p_, l_, fv) in enumerate(opts):
            img = R.frame(np.asarray(p_), np.asarray(l_), fv, RD.dyn_draws(R, fr["pose"][k], fr["face"][k], names,
                                                                              scale_row=fr["scale"][k] if "scale" in fr.files else None))
            im = Image.frombytes("RGB", (270, 480), img).transpose(Image.FLIP_TOP_BOTTOM)
            dr = ImageDraw.Draw(im)
            dr.rectangle([0, 0, 46, 48], fill=(0, 0, 0))
            dr.text((8, 0), LETTERS[m], font=font, fill=(255, 230, 60))
            sheet.paste(im, (270 * (m % 4), 480 * (m // 4)))
        num = len(table)
        sheet.save(out / f"shot_{num:03d}.png")
        table[str(num)] = {"key": key_of(c.name, c.start), "subject": c.subject, "with": c.with_, "start": round(c.start, 2),
                           "end": round(b, 2), "options": opts}
    (out / "candidates.json").write_text(json.dumps(table))
    return {"shots": len(table), "dir": str(out)}


def apply(shots, picks_path, log=print):
    p = Path(picks_path)
    picks = json.loads(p.read_text())
    table = json.loads((p.parent / "candidates.json").read_text())
    by_key = {}
    for n, ch in picks.items():
        e = table.get(str(n))
        if not e or ch not in LETTERS:
            continue
        m = LETTERS.index(ch)
        if m == 0 or m >= len(e["options"]):
            continue                      # "a" is the current framing
        by_key[e["key"]] = e["options"][m]
    out, done = [], 0
    for c in shots:
        o = by_key.get(key_of(c.name, c.start))
        if o:
            c = c.model_copy(update={"pos": o[0], "look": o[1], "fov": o[2], "push": 0.06})
            done += 1
        out.append(c)
    log(f"shot picks: {done} of {len(by_key)} applied")
    return out


if __name__ == "__main__":
    if sys.argv[1] == "candidates":
        print(json.dumps(candidates(sys.argv[2])))
        sys.stdout.flush()
        os._exit(0)
