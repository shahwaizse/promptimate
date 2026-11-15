"""Compare two benchmark runs metric by metric.

    .venv\\Scripts\\python bench\\compare.py baseline_s30 my_run [--category] [--prompt] [--pp]

Arguments are run names (under bench/results/) or paths to run directories.
'+' marks an improvement of B over A, '-' a regression (direction from metrics.DIRECTION); '.' = informational.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH.parent / "mcp_server"))
from metrics import DIRECTION  # noqa: E402

KEY_ORDER = ["expectation_score", "expectation_pass_rate", "skate_speed_cms", "skate_ratio", "skate_dist_cm_per_s",
             "penetration_max_cm", "penetration_ratio", "float_ratio", "airborne_frames", "jerk_mean", "jerk_p95",
             "jerk_max", "max_joint_acc_ms2", "pop_frames", "max_speed_jump_ms", "seam_jerk_ratio", "seam_acc_ratio",
             "seam_vel_jump_ms", "root_travel_m", "root_mean_speed_ms", "root_end_speed_ms", "heading_change_abs_deg"]


def load(arg: str) -> dict:
    p = Path(arg)
    if not (p / "summary.json").exists():
        p = BENCH / "results" / arg
    return json.loads((p / "summary.json").read_text())


def fmt(v) -> str:
    if v is None:
        return "-"
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def table(a: dict, b: dict, keys: list[str] | None = None, title: str = "") -> None:
    keys = keys or [k for k in KEY_ORDER if k in a or k in b] + sorted(
        k for k in set(a) | set(b) if k not in KEY_ORDER and not k.startswith("exp_"))
    if title:
        print(f"\n== {title}")
    print(f"{'metric':28s} {'A':>10s} {'B':>10s} {'delta':>10s} {'%':>7s}")
    for k in keys:
        va, vb = a.get(k), b.get(k)
        if va is None and vb is None:
            continue
        d = (vb - va) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
        pct = f"{100 * d / abs(va):+.0f}%" if d is not None and va else ""
        s = DIRECTION.get(k, 0)
        mark = "." if not s or d is None or d == 0 else ("+" if d * s > 0 else "-")
        print(f"{k:28s} {fmt(va):>10s} {fmt(vb):>10s} {fmt(d):>10s} {pct:>7s} {mark}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--category", action="store_true", help="also compare per category (key metrics)")
    ap.add_argument("--prompt", action="store_true", help="also compare per prompt (expectation_score)")
    ap.add_argument("--pp", action="store_true", help="use post-processed metrics of B (and A if present)")
    ap.add_argument("--all", action="store_true", help="include per-check exp_* scores")
    ap.add_argument("--paired", default="expectation_score,skate_speed_cms,jerk_mean,root_end_speed_ms",
                    help="metrics for the paired (same prompt+seed) delta with a bootstrap 95%% CI; '' disables")
    args = ap.parse_args()
    A, B = load(args.a), load(args.b)
    ma = A.get("metrics_pp", A["metrics"]) if args.pp else A["metrics"]
    mb = B.get("metrics_pp", B["metrics"]) if args.pp else B["metrics"]
    print(f"A = {A['config']['name']}  (steps {A['config'].get('steps')}, cfg {A['config'].get('text_cfg')}, "
          f"env {A['config'].get('env')})")
    print(f"B = {B['config']['name']}  (steps {B['config'].get('steps')}, cfg {B['config'].get('text_cfg')}, "
          f"env {B['config'].get('env')})")
    ta, tb = A["timing"], B["timing"]
    table({"gen_seconds": ta.get("gen_seconds_mean"), "gen_seconds_p50": ta.get("gen_seconds_p50"),
           "gen_seconds_per_clip_second": ta.get("gen_seconds_per_clip_second"), "failed": ta.get("failed")},
          {"gen_seconds": tb.get("gen_seconds_mean"), "gen_seconds_p50": tb.get("gen_seconds_p50"),
           "gen_seconds_per_clip_second": tb.get("gen_seconds_per_clip_second"), "failed": tb.get("failed")},
          ["gen_seconds", "gen_seconds_p50", "gen_seconds_per_clip_second", "failed"], "timing (warm clips)")
    keys = None
    if args.all:
        keys = [k for k in KEY_ORDER] + sorted(k for k in set(ma) | set(mb) if k.startswith("exp_"))
    table(ma, mb, keys, "overall means" + (" (post-processed)" if args.pp else ""))
    if args.category:
        ca = A.get("by_category_pp" if args.pp else "by_category", {})
        cb = B.get("by_category_pp" if args.pp else "by_category", {})
        for c in sorted(set(ca) | set(cb)):
            table(ca.get(c, {}), cb.get(c, {}), ["expectation_score", "skate_speed_cms", "jerk_mean", "pop_frames",
                                                 "seam_jerk_ratio", "root_end_speed_ms"], f"category: {c}")
    if args.prompt:
        pa, pb = A.get("by_prompt", {}), B.get("by_prompt", {})
        print(f"\n== per prompt expectation_score\n{'prompt':22s} {'A':>7s} {'B':>7s} {'delta':>7s}")
        for pid in sorted(set(pa) | set(pb)):
            va, vb = pa.get(pid, {}).get("expectation_score"), pb.get(pid, {}).get("expectation_score")
            d = f"{vb - va:+.3f}" if va is not None and vb is not None else ""
            print(f"{pid:22s} {fmt(va):>7s} {fmt(vb):>7s} {d:>7s}")
    if args.paired:
        paired(args.a, args.b, args.paired.split(","), args.pp)


def _rows(arg: str) -> dict:
    p = Path(arg)
    if not (p / "results.jsonl").exists():
        p = BENCH / "results" / arg
    return {(r["id"], r["seed"]): r for r in map(json.loads, (p / "results.jsonl").read_text().splitlines())
            if r.get("ok", True)}


def paired(a: str, b: str, metrics: list[str], pp: bool = False, n_boot: int = 4000) -> None:
    """Delta B - A over clips present in both runs (same prompt and seed), with a bootstrap 95% CI. If the CI
    excludes 0 the difference is real at this sample size; if it straddles 0, more seeds or a bigger effect needed."""
    import random
    ra, rb = _rows(a), _rows(b)
    common = sorted(set(ra) & set(rb))
    if not common:
        print("\n(no common prompt/seed pairs for a paired comparison)")
        return
    print(f"\n== paired B-A over {len(common)} common clips (bootstrap 95% CI)")
    print(f"{'metric':24s} {'mean delta':>11s} {'95% CI':>22s}  verdict")
    rng = random.Random(0)
    for m in metrics:
        key = "metrics_pp" if pp else "metrics"
        d = [rb[k].get(key, rb[k]["metrics"]).get(m) - ra[k].get(key, ra[k]["metrics"]).get(m) for k in common
             if rb[k].get(key, rb[k]["metrics"]).get(m) is not None and ra[k].get(key, ra[k]["metrics"]).get(m) is not None]
        if not d:
            continue
        means = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(n_boot))
        lo, hi = means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]
        mean = sum(d) / len(d)
        better = DIRECTION.get(m, 0)
        if lo > 0 or hi < 0:
            verdict = ("better" if (mean > 0) == (better > 0) else "worse") if better else "changed"
        else:
            verdict = "no clear difference"
        print(f"{m:24s} {mean:+11.4g} [{lo:+9.4g}, {hi:+9.4g}]  {verdict}")


if __name__ == "__main__":
    main()
