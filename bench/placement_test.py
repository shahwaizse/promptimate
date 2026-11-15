"""Where do the models land (dedicated VRAM vs shared system memory), and how fast is a warm 5 s clip?
Usage: .venv\\Scripts\\python bench\\placement_test.py [--env KEY=VAL ...] [--reps 3]"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
from kimodo_worker import KimodoWorker, Segment  # noqa: E402

PS = r"""$s=(Get-Counter '\GPU Process Memory(pid_{pid}*)\Dedicated Usage','\GPU Process Memory(pid_{pid}*)\Shared Usage').CounterSamples
$s | % {{ "{{0}} {{1}}" -f (($_.Path -split '\\')[-1]), [int]($_.CookedValue/1MB) }}"""


def gpu_mem(pid: int) -> dict:
    out = subprocess.run(["powershell", "-NoProfile", "-Command", PS.format(pid=pid)], capture_output=True,
                         text=True, stdin=subprocess.DEVNULL).stdout
    res = {}
    for line in out.splitlines():
        parts = line.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            key = "dedicated_mb" if "dedicated" in parts[0] else "shared_mb"
            res[key] = res.get(key, 0) + int(parts[1])
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--engine-dir", default=str(ROOT / "third_party" / "kimodo.cpp" / "build" / "promptimate"))
    args = ap.parse_args()
    env = dict(kv.split("=", 1) for kv in args.env)
    w = KimodoWorker(engine_dir=Path(args.engine_dir), extra_env=env)
    out = ROOT / "bench" / "results" / "placement"
    t0 = time.time()
    w.generate([Segment("a person stands still", 30)], out / "warm", steps=1, seed=0)
    cold = time.time() - t0
    mem = gpu_mem(w.proc.pid)
    times = []
    for i in range(args.reps):
        info = w.generate([Segment("a person walks forward and waves with their right hand", 150)], out / f"r{i}",
                          steps=30, seed=i)
        times.append(info["seconds"])
    mem_after = gpu_mem(w.proc.pid)
    w.stop()
    res = {"env": env, "cold_s": round(cold, 1), "mem_after_load": mem, "mem_after_runs": mem_after,
           "clip5s_steps30_s": times}
    print(json.dumps(res))


if __name__ == "__main__":
    main()
