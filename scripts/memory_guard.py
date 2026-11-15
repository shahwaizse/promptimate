r"""Memory guard for unattended multi-agent runs: logs RAM and commit headroom every 20 s; when commit headroom falls
below a threshold it asks motiond to unload its models (frees up to ~6 GB; the next request reloads them). Exits
(non-zero) only if headroom stays low after the valve, so a supervisor can step in.

    .venv\Scripts\python scripts\memory_guard.py [--low-mb 900] [--interval 20]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import socket
import sys
import time
from pathlib import Path

LOG = Path(__file__).resolve().parents[1] / "logs" / "sysmon.log"


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def memory() -> tuple[int, int]:
    """(available physical MB, available commit MB)"""
    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(st)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return st.ullAvailPhys // 2**20, st.ullAvailPageFile // 2**20


def unload_motiond() -> str:
    try:
        with socket.create_connection(("127.0.0.1", 47613), timeout=3) as s:
            s.settimeout(120)   # waits for an in-flight generation to finish first
            s.sendall(b'{"op": "unload"}\n')
            return s.makefile().readline().strip()[:120]
    except OSError as e:
        return f"no daemon ({e})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--low-mb", type=int, default=900)
    ap.add_argument("--interval", type=float, default=20)
    a = ap.parse_args()
    strikes = 0
    while True:
        phys, commit = memory()
        line = f"{time.strftime('%H:%M:%S')} free_mb={phys} commit_free_mb={commit}"
        if commit < a.low_mb:
            reply = unload_motiond()
            time.sleep(5)
            phys2, commit2 = memory()
            line += f" LOW -> unloaded motiond ({reply}) -> commit_free_mb={commit2}"
            strikes = strikes + 1 if commit2 < a.low_mb else 0
        else:
            strikes = 0
        LOG.parent.mkdir(exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if strikes >= 3:
            print(f"MEMORY STILL LOW after unloading motiond: {line}", flush=True)
            sys.exit(2)
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
