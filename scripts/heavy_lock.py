r"""Machine-wide lock for heavy jobs, so agents working in parallel take turns instead of overloading the GPU
(8 GB VRAM) or RAM (16 GB).

Hold it while running anything heavy: Unity editor/batch renders, ML model inference outside motiond, Blender,
large builds. Light work (editing, Python scripts, motiond generation requests, small downloads) doesn't need it.
motiond serialises its own GPU work; Unity + motiond together is fine.

CLI (waits for the lock, runs the command, releases):
    .venv\Scripts\python scripts\heavy_lock.py --who "fidelity render" -- <command> [args...]
    .venv\Scripts\python scripts\heavy_lock.py --status
Python:
    from heavy_lock import heavy
    with heavy("ragdoll unity test"):
        ...
"""
from __future__ import annotations

import contextlib
import json
import msvcrt
import os
import subprocess
import sys
import time
from pathlib import Path

LOCK = Path(__file__).resolve().parents[1] / "logs" / "heavy.lock"
INFO = LOCK.with_suffix(".holder.json")


@contextlib.contextmanager
def heavy(who: str = "", poll_s: float = 2.0, max_wait_s: float | None = None):
    LOCK.parent.mkdir(exist_ok=True)
    t0 = time.time()
    with open(LOCK, "a+b") as fh:
        fh.seek(0)
        announced = False
        while True:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if not announced:
                    holder = INFO.read_text(encoding="utf-8") if INFO.exists() else "?"
                    print(f"[heavy_lock] waiting for: {holder}", file=sys.stderr, flush=True)
                    announced = True
                if max_wait_s is not None and time.time() - t0 > max_wait_s:
                    raise TimeoutError("heavy lock busy")
                time.sleep(poll_s)
        INFO.write_text(json.dumps({"who": who, "pid": os.getpid(), "since": time.strftime("%H:%M:%S")}),
                        encoding="utf-8")
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                INFO.unlink()
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--status":
        print(INFO.read_text(encoding="utf-8") if INFO.exists() else "free")
        return
    who = ""
    if args and args[0] == "--who":
        who, args = args[1], args[2:]
    if args and args[0] == "--":
        args = args[1:]
    with heavy(who or " ".join(args)[:80]):
        sys.exit(subprocess.call(args))


if __name__ == "__main__":
    main()
