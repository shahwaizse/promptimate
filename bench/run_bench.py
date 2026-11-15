"""Promptimate benchmark: run one engine/config over the prompt suite and score every clip.

    .venv\\Scripts\\python bench\\run_bench.py --name baseline_s30 --steps 30 --seeds 0,1
    .venv\\Scripts\\python bench\\run_bench.py --name cfg3 --engine-dir third_party\\kimodo.cpp\\build\\promptimate --text-cfg 3
    .venv\\Scripts\\python bench\\run_bench.py --name pp --postprocess --prompts walk,jog
    .venv\\Scripts\\python bench\\run_bench.py --name rescore_x --rescore bench\\results\\baseline_s30   (no GPU)

Writes bench/results/<name>/: clips/<id>_s<seed>/ (raw f32 output), results.jsonl, summary.json, contact_sheet.png.
Compare two runs with bench/compare.py.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path

import numpy as np

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parent
sys.path.insert(0, str(ROOT / "mcp_server"))

import metrics  # noqa: E402
import motion  # noqa: E402

TRANSITION = 5


def load_suite(path: Path, subset: list[str] | None) -> list[dict]:
    prompts = json.loads(path.read_text(encoding="utf-8"))["prompts"]
    if subset:
        known = {p["id"] for p in prompts}
        missing = [s for s in subset if s not in known]
        if missing:
            raise SystemExit(f"unknown prompt ids: {missing}")
        prompts = [p for p in prompts if p["id"] in subset]
    return prompts


def seg_frames(p: dict) -> list[int]:
    return [max(2, min(300, round(s["seconds"] * motion.FPS))) for s in p["segments"]]


def score(root: np.ndarray, rot: np.ndarray, p: dict, frames: list[int]) -> dict:
    return metrics.compute(root, rot, expect=p.get("expect"), segment_expect=p.get("segment_expect"),
                           segment_frames=frames)


def save_raw(d: Path, root: np.ndarray, rot: np.ndarray, prefix: str = "") -> None:
    root.astype("<f4").tofile(d / f"{prefix}root_positions.f32")
    rot.astype("<f4").tofile(d / f"{prefix}local_rotations_xyzw.f32")


def try_import_postprocess():
    try:
        import postprocess  # type: ignore
        return postprocess
    except Exception as e:  # module is being written by another agent; never kill the bench over it
        print(f"[bench] postprocess unavailable ({type(e).__name__}: {e}); scoring raw only", flush=True)
        return None


def contact_sheet(pngs: list[tuple[str, Path]], out: Path, cols: int) -> Path | None:
    from PIL import Image, ImageDraw
    ims = [(lbl, Image.open(p).convert("RGB")) for lbl, p in pngs if p.exists()]
    if not ims:
        return None
    w = max(im.width for _, im in ims)
    h = max(im.height for _, im in ims)
    scale = 0.6
    tw, th = int(w * scale), int(h * scale)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (lbl, im) in enumerate(ims):
        x, y = (i % cols) * tw, (i // cols) * th
        sheet.paste(im.resize((tw, th)), (x, y))
        draw.text((x + 4, y + 2), lbl, fill=(200, 0, 0))
    sheet.save(out)
    return out


def summarize(rows: list[dict], cfg: dict) -> dict:
    ok = [r for r in rows if r.get("ok")]

    def means(rs: list[dict], key: str = "metrics") -> dict:
        keys = sorted({k for r in rs for k, v in r.get(key, {}).items() if isinstance(v, (int, float))})
        out = {}
        for k in keys:
            vals = [r[key][k] for r in rs if isinstance(r.get(key, {}).get(k), (int, float))]
            if vals:
                out[k] = round(float(np.mean(vals)), 4)
        return out

    warm = [r["gen_seconds"] for r in ok if not r.get("cold_start")]
    clip_s = [r["gen_seconds"] / r["clip_seconds"] for r in ok if not r.get("cold_start")]
    timing = {
        "clips": len(rows), "ok": len(ok), "failed": len(rows) - len(ok),
        "gen_seconds_mean": round(float(np.mean(warm)), 2) if warm else None,
        "gen_seconds_p50": round(float(np.median(warm)), 2) if warm else None,
        "gen_seconds_p90": round(float(np.percentile(warm, 90)), 2) if warm else None,
        "gen_seconds_per_clip_second": round(float(np.mean(clip_s)), 3) if clip_s else None,
        "wall_seconds_total": round(sum(r.get("wall_seconds", 0) for r in rows), 1),
        "cold_start_clips": sum(1 for r in ok if r.get("cold_start")),
    }
    cats = sorted({r["category"] for r in ok})
    summ = {"config": cfg, "timing": timing, "metrics": means(ok),
            "by_category": {c: means([r for r in ok if r["category"] == c]) for c in cats},
            "by_prompt": {pid: {k: v for k, v in means([r for r in ok if r["id"] == pid]).items()
                                if k in ("expectation_score", "skate_speed_cms", "jerk_mean", "seam_jerk_ratio",
                                         "root_travel_m", "root_end_speed_ms", "heading_change_abs_deg")}
                          for pid in sorted({r["id"] for r in ok})}}
    if any("metrics_pp" in r for r in ok):
        summ["metrics_pp"] = means([r for r in ok if "metrics_pp" in r], "metrics_pp")
        summ["by_category_pp"] = {c: means([r for r in ok if r["category"] == c and "metrics_pp" in r], "metrics_pp")
                                  for c in cats}
    return summ


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--engine-dir", default=None, help="kimodo.cpp build dir (default: KimodoWorker default)")
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--text-cfg", type=float, default=None, help="text guidance weight (patched engine only)")
    ap.add_argument("--tier", default=None, choices=["smoke", "standard", "full"],
                    help="suite size (bench/tiers.py); --prompts/--seeds override it")
    ap.add_argument("--seeds", default=None, help="comma-separated seeds (default: tier's, else 0,1)")
    ap.add_argument("--prompts", default=None, help="comma-separated prompt ids (default: tier's, else all)")
    ap.add_argument("--direct", action="store_true", help="own engine process instead of the shared motiond")
    ap.add_argument("--no-cache", action="store_true", help="bypass motiond's generation cache")
    ap.add_argument("--suite", default=str(BENCH / "prompts.json"))
    ap.add_argument("--env", action="append", default=[], metavar="KEY=VAL", help="extra worker env (repeatable)")
    ap.add_argument("--text-quant", default=None, choices=[None, "q4_k_m", "q8_0"])
    ap.add_argument("--transition", type=int, default=TRANSITION)
    ap.add_argument("--postprocess", action="store_true", help="also score postprocess.clean() output")
    ap.add_argument("--no-warmup", action="store_true", help="skip the short warm-up generation")
    ap.add_argument("--rescore", default=None, metavar="RUN_DIR",
                    help="no generation: re-score raw clips of an existing run (e.g. after metric changes)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing results dir")
    args = ap.parse_args()

    os.environ.setdefault("TEMP", r"D:\tmp")
    os.environ.setdefault("TMP", r"D:\tmp")
    out = BENCH / "results" / args.name
    if out.exists() and any(out.iterdir()):
        if not args.force:
            raise SystemExit(f"{out} exists; pass --force or pick another --name")
        shutil.rmtree(out)
    (out / "clips").mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(BENCH))
    import tiers
    prompt_ids, seeds = tiers.resolve(args.tier, args.prompts, args.seeds)
    suite = load_suite(Path(args.suite), prompt_ids)
    extra_env = dict(kv.split("=", 1) for kv in args.env)
    pp = try_import_postprocess() if args.postprocess else None

    worker = None
    cfg = {"name": args.name, "steps": args.steps, "text_cfg": args.text_cfg, "seeds": seeds,
           "env": extra_env, "transition": args.transition, "postprocess": bool(pp),
           "prompts": [p["id"] for p in suite], "host": platform.node(),
           "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    if args.rescore:
        src = Path(args.rescore)
        cfg.update({k: v for k, v in json.loads((src / "config.json").read_text()).items() if k not in ("prompts", "seeds")})
        cfg.update(name=args.name, rescored_from=str(src), postprocess=bool(pp))
        prev = {(r["id"], r["seed"]): r for r in map(json.loads, (src / "results.jsonl").read_text().splitlines())}
    else:
        from kimodo_worker import KimodoWorker, Segment
        kw = dict(text_quant=args.text_quant, engine_dir=Path(args.engine_dir) if args.engine_dir else None,
                  extra_env=extra_env)
        if args.direct:
            worker = KimodoWorker(**kw)
        else:
            from motiond import RemoteWorker
            worker = RemoteWorker(cache=not args.no_cache, **kw)
        cfg.update(engine_dir=str(worker.engine_dir), text_quant=worker.text_quant, direct=args.direct,
                   cache=not args.no_cache and not args.direct)
    (out / "config.json").write_text(json.dumps(cfg, indent=2))

    rows: list[dict] = []
    pngs: list[tuple[str, Path]] = []
    try:
        if worker and not args.no_warmup:
            t0 = time.time()
            print("[bench] warm-up (model load) ...", flush=True)
            info = worker.generate([Segment("a person stands still", 60)], out / "_warmup", steps=2, seed=0,
                                   transition=args.transition, **({"text_cfg": args.text_cfg} if args.text_cfg is not None else {}))
            cfg["warmup"] = {"wall_seconds": round(time.time() - t0, 1), **info}
            (out / "config.json").write_text(json.dumps(cfg, indent=2))
            print(f"[bench] warm-up done in {time.time() - t0:.1f}s", flush=True)
        with open(out / "results.jsonl", "w", encoding="utf-8") as jl:
            for p in suite:
                frames = seg_frames(p)
                for seed in seeds:
                    cid = f"{p['id']}_s{seed}"
                    d = out / "clips" / cid
                    row = {"id": p["id"], "seed": seed, "category": p["category"],
                           "prompts": [s["prompt"] for s in p["segments"]], "segment_frames": frames,
                           "clip_seconds": round(sum(frames) / motion.FPS, 3),
                           "config": {k: cfg[k] for k in ("name", "steps", "text_cfg", "env", "postprocess")}}
                    t0 = time.time()
                    try:
                        if worker:
                            kw = {"text_cfg": args.text_cfg} if args.text_cfg is not None else {}
                            info = worker.generate([Segment(s["prompt"], f) for s, f in zip(p["segments"], frames)],
                                                   d, steps=args.steps, seed=seed, transition=args.transition, **kw)
                            hit = bool(info.get("cache_hit"))
                            row.update(gen_seconds=info.get("engine_seconds", info["seconds"]) if hit else info["seconds"],
                                       cold_start=info["cold_start"], cache_hit=hit,
                                       wall_seconds=round(time.time() - t0, 2))
                        else:
                            r0 = prev[(p["id"], seed)]
                            shutil.copytree(src / "clips" / cid, d)
                            row.update({k: r0.get(k) for k in ("gen_seconds", "cold_start", "wall_seconds")})
                        root, rot = motion.load(d)
                        row["metrics"] = score(root, rot, p, frames)
                        if pp is not None:
                            try:
                                t1 = time.time()
                                c_root, c_rot, pinfo = pp.clean(root.copy(), rot.copy(),
                                                                contacts=pp.load_contacts(d) if hasattr(pp, "load_contacts") else None)
                                row["pp_seconds"] = round(time.time() - t1, 3)
                                row["pp_info"] = pinfo if isinstance(pinfo, dict) else str(pinfo)
                                save_raw(d, np.asarray(c_root), np.asarray(c_rot), "pp_")
                                row["metrics_pp"] = score(np.asarray(c_root), np.asarray(c_rot), p, frames)
                            except Exception as e:
                                row["pp_error"] = f"{type(e).__name__}: {e}"
                        pos = motion.fk(root, rot)
                        png = motion.render_preview(pos, d / "preview.png",
                                                    f"{cid} | " + " | ".join(row["prompts"])
                                                    + f" | exp={row['metrics'].get('expectation_score', 0):.2f}")
                        pngs.append((cid, png))
                        row["ok"] = True
                    except Exception as e:
                        row.update(ok=False, error=f"{type(e).__name__}: {e}", wall_seconds=round(time.time() - t0, 2))
                        traceback.print_exc()
                    rows.append(row)
                    jl.write(json.dumps(row, default=float) + "\n")
                    jl.flush()
                    m = row.get("metrics", {})
                    print(f"[bench] {cid:24s} gen={row.get('gen_seconds')}s{' (cached)' if row.get('cache_hit') else ''} exp={m.get('expectation_score')} "
                          f"skate={m.get('skate_speed_cms')} jerk={m.get('jerk_mean')} "
                          f"travel={m.get('root_travel_m')}" + (" FAILED " + row["error"] if not row["ok"] else ""),
                          flush=True)
    finally:
        if worker:
            worker.stop()

    summ = summarize(rows, cfg)
    (out / "summary.json").write_text(json.dumps(summ, indent=2))
    sheet = contact_sheet(pngs, out / "contact_sheet.png", cols=max(1, len(seeds)))
    t = summ["timing"]
    m = summ["metrics"]
    print(f"\n[bench] {args.name}: {t['ok']}/{t['clips']} ok, gen mean {t['gen_seconds_mean']}s p50 "
          f"{t['gen_seconds_p50']}s ({t['gen_seconds_per_clip_second']} s per clip-second)")
    for k in ("expectation_score", "expectation_pass_rate", "skate_speed_cms", "skate_ratio", "penetration_max_cm",
              "float_ratio", "jerk_mean", "jerk_p95", "pop_frames", "seam_jerk_ratio", "seam_vel_jump_ms"):
        if k in m:
            print(f"  {k:24s} {m[k]}" + (f"   (pp: {summ['metrics_pp'][k]})" if "metrics_pp" in summ and k in summ["metrics_pp"] else ""))
    print(f"[bench] wrote {out} (contact sheet: {sheet})")


if __name__ == "__main__":
    main()
