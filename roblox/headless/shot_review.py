"""Vision review of an episode's camera work: every final shot's middle frame, rendered for real and numbered on
contact sheets, for a reviewer (a fresh Claude agent) to mark; the marks are applied on the next recording.

    python roblox/headless/shot_review.py sheets <episode>      -> D:\\tmp\\headless\\<ep>\\review\\sheet_NN.png + index.json
    PROMPTIMATE_SHOT_REVIEW=<review.json> produce.py <ep> --offline --from record     (pipeline applies it)

review.json: {"shots": {"<index>": {"problem": "...", "fix": "other_angle|wider|closer|higher|other_subject|ok"}}}
The index refers to index.json (key = shot name + start), so a review stays valid for a re-plan of the same episode.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "mcp_server"))
import local_config as LC  # noqa: E402
CACHE = LC.HEADLESS_CACHE
FIXES = ("ok", "other_angle", "wider", "closer", "higher", "other_subject")


def key_of(c) -> str:
    return f"{c.get('name') or ''}|{float(c['start']):.2f}"


def sheets(ep: str, per_sheet: int = 12, cols: int = 6) -> dict:
    import hlrender as RD
    from PIL import Image, ImageDraw, ImageFont
    d = CACHE / ep
    shots = json.loads((d / "shots.json").read_text())
    dyn = json.loads((d / "dynamic.json").read_text())
    fr = np.load(d / "frames.npz")
    cams = np.load(d / "cams.npy")
    R = RD.Renderer(d, w=270, h=480)
    out = d / "review"
    out.mkdir(exist_ok=True)
    for f in out.glob("sheet_*.png"):
        f.unlink()
    t_end = len(cams) / 30
    index, ims = {}, []
    font = ImageFont.truetype(str(HERE.parents[1] / "demo" / "episodes" / "build" / "_media" / "fonts" / "Montserrat-Black.ttf"), 34)
    for i, c in enumerate(shots):
        b = shots[i + 1]["start"] if i + 1 < len(shots) else t_end
        if b - c["start"] < 0.25:
            continue
        t = (c["start"] + b) / 2
        k = min(int(t * 30), len(cams) - 1)
        img = R.frame(cams[k, :3], cams[k, 3:6], cams[k, 6], RD.dyn_draws(R, fr["pose"][k], fr["face"][k], dyn["order"],
                                                                             scale_row=fr["scale"][k] if "scale" in fr.files else None))
        im = Image.frombytes("RGB", (270, 480), img).transpose(Image.FLIP_TOP_BOTTOM)
        dr = ImageDraw.Draw(im)
        n = len(index)
        dr.rectangle([0, 0, 64, 42], fill=(0, 0, 0))
        dr.text((6, 2), str(n), font=font, fill=(255, 230, 60))
        index[str(n)] = {"key": key_of(c), "start": round(c["start"], 2), "end": round(b, 2), "subject": c.get("subject"),
                         "with": c.get("with_") or c.get("with"), "prop": c.get("prop"), "shot": c.get("shot"),
                         "name": c.get("name")}
        ims.append(im)
    rows = (per_sheet + cols - 1) // cols
    for s in range(0, len(ims), per_sheet):
        sh = Image.new("RGB", (270 * cols, 480 * rows), (40, 40, 40))
        for j, im in enumerate(ims[s:s + per_sheet]):
            sh.paste(im, (270 * (j % cols), 480 * (j // cols)))
        sh.save(out / f"sheet_{s // per_sheet + 1:02d}.png")
    (out / "index.json").write_text(json.dumps(index, indent=1))
    return {"shots": len(index), "sheets": (len(ims) + per_sheet - 1) // per_sheet, "dir": str(out)}


def apply(shots, review_path, perf, t_end, ck, log=print):
    """Re-frame the shots a reviewer marked, by their fix (a constrained search; see audit.search)."""
    import audit as AU
    rv = json.loads(Path(review_path).read_text())
    idx = json.loads((Path(review_path).parent / "index.json").read_text()) if (Path(review_path).parent / "index.json").exists() else {}
    marks = {}
    for n, m in (rv.get("shots") or {}).items():
        fix = m.get("fix", "ok")
        if fix == "ok" or str(n) not in idx:
            continue
        marks[idx[str(n)]["key"]] = fix
    out, done = list(shots), 0
    for i, c in enumerate(out):
        k = key_of({"name": c.name, "start": c.start})
        fix = marks.get(k)
        if not fix:
            continue
        if fix == "other_subject" or c.prop or not c.subject:
            b = out[i + 1].start if i + 1 < len(out) else t_end
            tm = (c.start + b) / 2
            vis = [n for n in ck.names if n not in ck.alias and n != c.subject and ck.actor_index(n, "Head") is not None
                   and ck.pose[ck._frame(tm), ck.actor_index(n, "Head"), 1] > -500]
            near = [out[j].subject for j in list(range(i - 1, -1, -1)) + list(range(i + 1, len(out))) if out[j].subject in vis]
            subj = near[0] if near else (vis[0] if vis else None)
            if subj is None:
                continue
            out[i] = c = c.model_copy(update={"subject": subj, "with_": None, "prop": None, "subjects": [subj], "shot": "medium",
                                              "pos": None, "look": None})
            fix = "any"
        cur = AU._score(out, i, perf, t_end, ck)
        r = AU.search(out, i, perf, t_end, ck, design=True, fix=fix, avoid=None if fix == "any" else (c.pos, c.look))
        if r is not None and r[1] > 0:       # the asked fix has no clean view: any clean view of this subject
            r2 = AU.search(out, i, perf, t_end, ck, design=True)
            if r2 is not None and r2[1] < r[1]:
                r = r2
        if r is not None and r[1] > 0 and fix != "any":     # still nothing: someone else in the scene
            b = out[i + 1].start if i + 1 < len(out) else t_end
            tm = (c.start + b) / 2
            for n in [out[j].subject for j in list(range(i - 1, -1, -1)) + list(range(i + 1, len(out)))]:
                if not n or n == c.subject or n not in ck.names or n in ck.alias:
                    continue
                hi_ = ck.actor_index(n, "Head")
                if hi_ is None or ck.pose[ck._frame(tm), hi_, 1] < -500:
                    continue
                trial = out[:i] + [c.model_copy(update={"subject": n, "with_": None, "subjects": [n], "shot": "medium"})] + out[i + 1:]
                r3 = AU.search(trial, i, perf, t_end, ck, design=True)
                if r3 is not None and r3[1] < r[1]:
                    out[i] = c = trial[i]
                    r = r3
                    if r3[1] == 0:
                        break
        if r is not None and r[1] <= cur:
            (p_, l_, f_), nb, cand = r
            out[i] = c.model_copy(update={"pos": [round(float(v), 3) for v in p_], "look": [round(float(v), 3) for v in l_],
                                          "fov": float(f_)})
            done += 1
    log(f"shot review: {len(marks)} marked, {done} re-framed")
    return out


if __name__ == "__main__":
    if sys.argv[1] == "sheets":
        print(json.dumps(sheets(sys.argv[2])))
        sys.stdout.flush()
        os._exit(0)
