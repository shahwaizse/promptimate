"""Render before/after GIFs for the hill-climb report into .cache/report/ (stock engine raw output vs. the new default
pipeline, same prompt, seed-0 family)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
import motion  # noqa: E402
import render  # noqa: E402

OUT = ROOT / ".cache" / "report"
BASE = ROOT / "bench" / "results" / "baseline_s30" / "clips"
FINAL = json.loads((ROOT / "bench" / "results" / "server_final_default.json").read_text())
PICKS = ["walk_stop", "seq_walk_stop_wave", "seq_jog_jump", "jog", "walk", "zombie", "turn_around", "sit_floor"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = {(r["id"], r["seed"]): r for r in FINAL["rows"]}
    made = {}
    for pid in PICKS:
        new = rows.get((pid, 0))
        old = BASE / f"{pid}_s0"
        if not new or not old.exists():
            continue
        pa = motion.fk(*motion.load(old))
        pb = motion.fk(*motion.load(Path(new["dir"])))
        gif = OUT / f"{pid}.gif"
        render.render_gif([pa, pb], gif, titles=["before (v0.1 stock engine)", "after (new default pipeline)"],
                          fps=15)
        made[pid] = gif.name
        print(pid, gif.stat().st_size // 1024, "KiB", flush=True)
    (OUT / "assets.json").write_text(json.dumps(made, indent=2))


if __name__ == "__main__":
    main()
