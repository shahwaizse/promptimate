"""Visual page for one bench run (or a side-by-side of two): bench/results/<run>/index.html.

Usage:
    .venv\\Scripts\\python bench\\report_run.py RUN [--vs OTHER_RUN] [--gifs] [--pp]
Shows the summary, then one row per clip: preview (or animated GIF with --gifs) and key metrics; with --vs, the two
runs' clips side by side with metric deltas, worst regressions first. Self-contained apart from the image files.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "bench"
sys.path.insert(0, str(ROOT / "mcp_server"))

KEYS = ["expectation_score", "skate_speed_cms", "jerk_mean", "pop_frames", "root_end_speed_ms", "root_travel_m"]
BETTER = {"expectation_score": 1, "skate_speed_cms": -1, "jerk_mean": -1, "pop_frames": -1}


def run_dir(arg: str) -> Path:
    p = Path(arg)
    return p if (p / "results.jsonl").exists() else BENCH / "results" / arg


def rows(d: Path) -> dict:
    return {(r["id"], r["seed"]): r for r in map(json.loads, (d / "results.jsonl").read_text().splitlines())}


def media(d: Path, r: dict, gifs: bool, pp: bool) -> str:
    clip = d / "clips" / f"{r['id']}_s{r['seed']}"
    if gifs:
        gif = clip / ("anim_pp.gif" if pp else "anim.gif")
        if not gif.exists():
            import motion
            import numpy as np
            import render
            pre = "pp_" if pp and (clip / "pp_root_positions.f32").exists() else ""
            root = np.fromfile(clip / f"{pre}root_positions.f32", dtype="<f4").reshape(-1, 3)
            rot = np.fromfile(clip / f"{pre}local_rotations_xyzw.f32", dtype="<f4").reshape(len(root), motion.J, 4)
            render.render_gif(motion.fk(root, rot), gif, titles=[f"{r['id']} s{r['seed']}"], fps=15)
        return gif.relative_to(BENCH / "results").as_posix()
    return (clip / "preview.png").relative_to(BENCH / "results").as_posix()


def fmt(v) -> str:
    return "-" if v is None else (f"{v:.3g}" if isinstance(v, float) else str(v))


def cell(m: dict, other: dict | None = None) -> str:
    out = []
    for k in KEYS:
        v = m.get(k)
        cls = ""
        if other is not None and v is not None and other.get(k) is not None and k in BETTER:
            d = (v - other[k]) * BETTER[k]
            cls = " class='good'" if d > 1e-9 else (" class='bad'" if d < -1e-9 else "")
        out.append(f"<tr><td>{k}</td><td{cls}>{fmt(v)}</td></tr>")
    return "<table class='m'>" + "".join(out) + "</table>"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--vs", default=None, help="baseline run to compare against (shown on the left)")
    ap.add_argument("--gifs", action="store_true", help="render animated GIFs (slower, ~1 s per clip)")
    ap.add_argument("--pp", action="store_true", help="show post-processed clips/metrics")
    args = ap.parse_args()
    b = run_dir(args.run)
    rb = rows(b)
    ra = rows(run_dir(args.vs)) if args.vs else {}
    a = run_dir(args.vs) if args.vs else None
    key = "metrics_pp" if args.pp else "metrics"
    order = sorted(rb, key=lambda k: (rb[k].get(key, rb[k].get("metrics", {})).get("expectation_score", 1)
                                      - (ra[k].get(key, ra[k].get("metrics", {})).get("expectation_score", 1)
                                         if k in ra else 0), k))
    body = []
    for k in order:
        r = rb[k]
        if not r.get("ok", True):
            body.append(f"<tr><td colspan=3>{html.escape(str(k))} FAILED: {html.escape(r.get('error', ''))}</td></tr>")
            continue
        mb = r.get(key, r.get("metrics", {}))
        title = f"<b>{html.escape(r['id'])}</b> seed {r['seed']}<br><small>{html.escape(' | '.join(r['prompts']))}</small>"
        left = ""
        if k in ra:
            ma = ra[k].get(key, ra[k].get("metrics", {}))
            left = f"<td><img src='{media(a, ra[k], args.gifs, args.pp)}'>{cell(ma)}</td>"
            right = f"<td><img src='{media(b, r, args.gifs, args.pp)}'>{cell(mb, ma)}</td>"
        else:
            right = f"<td><img src='{media(b, r, args.gifs, args.pp)}'>{cell(mb)}</td>"
        body.append(f"<tr><td class='t'>{title}</td>{left}{right}</tr>")
    summ = json.loads((b / "summary.json").read_text()) if (b / "summary.json").exists() else {}
    m = summ.get("metrics_pp" if args.pp else "metrics", {})
    head = " ".join(f"<span class='k'>{k}: <b>{fmt(m.get(k))}</b></span>" for k in KEYS)
    cols = (f"<th>{html.escape(args.vs)}</th>" if args.vs else "") + f"<th>{html.escape(args.run)}</th>"
    page = f"""<!doctype html><html><head><meta charset='utf-8'><title>Bench {html.escape(args.run)}</title>
<style>body{{font:14px system-ui,sans-serif;margin:16px;background:#fff;color:#111}}
img{{max-width:640px;width:100%;display:block}} td{{vertical-align:top;padding:6px;border-top:1px solid #ddd}}
.t{{width:220px}} table.m td{{border:0;padding:1px 6px;font-size:12px}} .good{{color:#0a7a2f;font-weight:600}}
.bad{{color:#b3261e;font-weight:600}} .k{{margin-right:14px}}
@media (prefers-color-scheme: dark){{body{{background:#111;color:#eee}} td{{border-color:#333}}}}</style></head>
<body><h2>{html.escape(args.run)}{(' vs ' + html.escape(args.vs)) if args.vs else ''}</h2><p>{head}</p>
<p><small>Rows sorted by expectation-score change (worst first). Green/red = better/worse than the left run.</small></p>
<table><tr><th></th>{cols}</tr>{''.join(body)}</table></body></html>"""
    out = BENCH / "results" / (f"{args.run}_vs_{args.vs}.html" if args.vs else f"{args.run}.html")
    out.write_text(page, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
