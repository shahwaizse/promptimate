r"""Runs SystemLab headless under the machine-wide heavy lock (one Unity session at a time), then exits Unity.

    .venv\Scripts\python demo\ragdoll\run_lab.py tests
    .venv\Scripts\python demo\ragdoll\run_lab.py shots compare,stairs [--no-render] [--scale 0.5] [--personalities f.json]

Frames land in demo/ragdoll/build/frames/<shot>/ with shot.json (metrics, state log, timeline) next to them.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from heavy_lock import heavy  # noqa: E402

UNITY = os.environ.get("UNITY_EXE_SYSTEMLAB", r"D:\Unity\Editors\6000.0.34f1\Editor\Unity.exe")
PROJECT = ROOT / "unity" / "SystemLab"
BUILD = ROOT / "demo" / "ragdoll" / "build"


def unity(method: str, extra: list[str], who: str, log: Path) -> int:
    env = dict(os.environ, TEMP=r"D:\tmp", TMP=r"D:\tmp")
    cmd = [UNITY, "-batchmode", "-projectPath", str(PROJECT), "-executeMethod", method, "-logFile", str(log), *extra]
    with heavy(f"ragdoll: {who}"):
        t0 = time.time()
        code = subprocess.call(cmd, env=env)
        print(f"[run_lab] {who}: exit {code} in {time.time() - t0:.0f}s (log {log})", flush=True)
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    for line in text.splitlines():
        if re.search(r"LAB_|error CS|Exception", line):
            print(line[:400])
    return code


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["tests", "shots"])
    ap.add_argument("shots", nargs="?", default="compare")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--scale", default="1")
    ap.add_argument("--personalities", default="")
    a = ap.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    logs = BUILD / "logs"
    logs.mkdir(exist_ok=True)
    if a.what == "tests":
        sys.exit(unity("SystemLab.LabTests.Run", [], "physics tests", logs / "tests.log"))
    extra = ["-shots", a.shots, "-out", str(BUILD / "frames"), "-render", "0" if a.no_render else "1",
             "-scale", a.scale]
    if a.personalities:
        extra += ["-personalities", str(Path(a.personalities).resolve())]
    sys.exit(unity("SystemLab.LabRunner.Run", extra, f"shots {a.shots}", logs / f"shots_{a.shots.replace(',', '_')}.log"))


if __name__ == "__main__":
    main()
