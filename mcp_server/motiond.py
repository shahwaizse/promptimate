"""motiond: one long-lived process that owns the GPU models; every client (MCP server instances, bench, eval scripts)
talks to it over localhost instead of loading its own copy.

Why: an 8 GB card holds exactly one resident copy of the models. Per-client workers meant a cold model load (10 s to
2 min from an HDD) for every script and Claude session, and VRAM contention when two were alive at once. With one
daemon, clients share one warm engine and requests are simply queued.

It also keeps a content-addressed generation cache (.cache/gen): a request with the same engine build, engine env,
text quant, segments, steps, seed, guidance and constraints is answered from disk in milliseconds. This makes
re-validating CPU-side changes (post-processing, scoring, server logic) nearly free.

Protocol: one JSON object per line over TCP 127.0.0.1:$MOTIOND_PORT (default 47613), one JSON reply per line.
    {"op": "generate", "config": {...}, "segments": [[prompt, frames], ...], "out_dir": str, "steps": int,
     "seed": int, "transition": int, "text_cfg": float|null, "constraint_cfg": float|null,
     "constraints": str|null, "cache": bool}
    {"op": "warm", "config": {...}}   (load the models now with a tiny uncached generation; no-op if loaded)
    {"op": "status"}   {"op": "unload"}   {"op": "shutdown"}
config = {"engine_dir": str|null, "text_quant": str|null, "extra_env": {..}}; a different config restarts the engine.

Run in the foreground: .venv\\Scripts\\python mcp_server\\motiond.py   (clients also auto-start it detached).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kimodo_worker import KIMODO_BUILD, KimodoWorker, Segment  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("MOTIOND_PORT", "47613"))
CACHE = ROOT / ".cache" / "gen"
CACHE_FILES = ("root_positions.f32", "local_rotations_xyzw.f32", "foot_contacts.f32")
VERSION = 1


def _engine_fingerprint(engine_dir: Path) -> str:
    exe = engine_dir / "kmd-generate.exe"
    st = exe.stat()
    return f"{exe.resolve()}:{st.st_size}:{int(st.st_mtime)}"


class Daemon:
    def __init__(self) -> None:
        self.lock = threading.Lock()  # one generation at a time; other clients queue here
        self.worker: KimodoWorker | None = None
        self.config_key: str | None = None
        self.stats = {"requests": 0, "cache_hits": 0, "engine_starts": 0, "started_at": time.time()}

    def _ensure(self, config: dict) -> KimodoWorker:
        engine = Path(config.get("engine_dir") or KIMODO_BUILD)
        key = json.dumps({"engine": str(engine.resolve()), "quant": config.get("text_quant"),
                          "env": config.get("extra_env") or {}}, sort_keys=True)
        if self.worker is None or key != self.config_key:
            if self.worker is not None:
                self.worker.stop()
            self.worker = KimodoWorker(text_quant=config.get("text_quant"), engine_dir=engine,
                                       extra_env=config.get("extra_env") or {})
            self.config_key = key
            self.stats["engine_starts"] += 1
        return self.worker

    def _cache_key(self, req: dict, worker: KimodoWorker) -> str:
        h = hashlib.sha256()
        cons = req.get("constraints")
        payload = {k: req.get(k) for k in ("segments", "steps", "seed", "transition", "text_cfg", "constraint_cfg")}
        if req.get("holds"):  # only when used, so cache keys of requests without holds stay valid
            payload["holds"] = req["holds"]
        payload.update(engine=_engine_fingerprint(worker.engine_dir), quant=worker.text_quant,
                       env=worker.extra_env, v=VERSION)
        h.update(json.dumps(payload, sort_keys=True).encode())
        if cons:
            h.update(Path(cons).read_bytes())
        return h.hexdigest()[:24]

    def generate(self, req: dict) -> dict:
        with self.lock:
            self.stats["requests"] += 1
            worker = self._ensure(req.get("config") or {})
            out_dir = Path(req["out_dir"])
            use_cache = req.get("cache", True)
            key = self._cache_key(req, worker) if use_cache else None
            hit = CACHE / key if key else None
            if hit is not None and (hit / "info.json").exists():
                out_dir.mkdir(parents=True, exist_ok=True)
                for f in CACHE_FILES:
                    if (hit / f).exists():
                        shutil.copyfile(hit / f, out_dir / f)
                self.stats["cache_hits"] += 1
                info = json.loads((hit / "info.json").read_text())
                return {**info, "cache_hit": True, "cold_start": False, "seconds": 0.0, "engine_seconds": info["seconds"]}
            segs = [Segment(p, int(f)) for p, f in req["segments"]]
            info = worker.generate(segs, out_dir, steps=int(req["steps"]), seed=int(req["seed"]),
                                   transition=int(req.get("transition", 5)), text_cfg=req.get("text_cfg"),
                                   constraint_cfg=req.get("constraint_cfg"),
                                   constraints=Path(req["constraints"]) if req.get("constraints") else None,
                                   holds=req.get("holds"))
            if hit is not None:
                tmp = CACHE / (key + ".tmp")
                shutil.rmtree(tmp, ignore_errors=True)
                tmp.mkdir(parents=True)
                for f in CACHE_FILES:
                    if (out_dir / f).exists():
                        shutil.copyfile(out_dir / f, tmp / f)
                (tmp / "info.json").write_text(json.dumps(info))
                shutil.rmtree(hit, ignore_errors=True)
                tmp.rename(hit)
            return {**info, "cache_hit": False}

    def warm(self, req: dict) -> dict:
        """Load the engine for this config ahead of the first real request (an MCP server calls this in the
        background at startup). A real request that arrives meanwhile queues on the lock and finds it warm."""
        with self.lock:
            worker = self._ensure(req.get("config") or {})
            if worker.alive():
                return {"warmed": False, "seconds": 0.0}
            t0 = time.time()
            out = ROOT / ".cache" / "warm"
            shutil.rmtree(out, ignore_errors=True)
            worker.generate([Segment("a person stands still", 30)], out, steps=1, seed=0)
            self.stats["warmups"] = self.stats.get("warmups", 0) + 1
            return {"warmed": True, "seconds": round(time.time() - t0, 2)}

    def status(self) -> dict:
        w = self.worker
        return {**self.stats, "loaded": bool(w and w.alive()), "config": self.config_key,
                "engine_dir": str(w.engine_dir) if w else str(KIMODO_BUILD),
                "text_quant": w.text_quant if w else os.environ.get("KIMODO_TEXT_QUANT", "q4_k_m"),
                "uptime_s": round(time.time() - w.started_at, 1) if w and w.alive() and w.started_at else None,
                "pid": os.getpid()}


DAEMON = Daemon()


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        for line in self.rfile:
            try:
                req = json.loads(line)
                op = req.get("op")
                if op == "generate":
                    res = {"ok": True, "result": DAEMON.generate(req)}
                elif op == "warm":
                    res = {"ok": True, "result": DAEMON.warm(req)}
                elif op == "status":
                    res = {"ok": True, "result": DAEMON.status()}
                elif op == "unload":
                    with DAEMON.lock:
                        if DAEMON.worker:
                            DAEMON.worker.stop()
                    res = {"ok": True, "result": DAEMON.status()}
                elif op == "shutdown":
                    self.wfile.write(b'{"ok": true, "result": "bye"}\n')
                    self.wfile.flush()
                    with DAEMON.lock:
                        if DAEMON.worker:
                            DAEMON.worker.stop()
                    os._exit(0)
                else:
                    res = {"ok": False, "error": f"unknown op {op!r}"}
            except Exception as e:  # report to the client, keep serving
                res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            self.wfile.write((json.dumps(res) + "\n").encode())
            self.wfile.flush()


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False


def main() -> None:
    try:
        srv = Server(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"motiond: port {PORT} busy (already running?)", file=sys.stderr)
        sys.exit(1)
    print(f"motiond listening on 127.0.0.1:{PORT} (pid {os.getpid()})", flush=True)
    srv.serve_forever()


# ------------------------------------------------------------------------------------------------- client side

class RemoteWorker:
    """Drop-in for KimodoWorker that forwards to motiond (auto-starting it). stop() only disconnects; the daemon
    unloads on its own idle timer or when asked (unload())."""

    def __init__(self, text_quant: str | None = None, engine_dir: Path | None = None, extra_env: dict | None = None,
                 cache: bool = True):
        self.config = {"engine_dir": str(engine_dir) if engine_dir else None, "text_quant": text_quant,
                       "extra_env": dict(extra_env or {})}
        self.cache = cache
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._file = None

    # connection -------------------------------------------------------------------------------------------
    def _connect(self) -> None:
        if self._sock is not None:
            return
        for attempt in range(2):
            try:
                self._sock = socket.create_connection(("127.0.0.1", PORT), timeout=5)
                self._sock.settimeout(None)
                self._file = self._sock.makefile("rwb")
                return
            except OSError:
                if attempt == 0:
                    self._spawn()
        raise RuntimeError(f"cannot reach motiond on port {PORT}; see logs/motiond.log")

    @staticmethod
    def _spawn() -> None:
        import subprocess
        log_dir = ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        log = open(log_dir / "motiond.log", "ab")
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) \
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([sys.executable, str(Path(__file__).resolve())], stdin=subprocess.DEVNULL, stdout=log,
                         stderr=log, creationflags=flags, cwd=str(ROOT), close_fds=True)
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", PORT), timeout=1).close()
                return
            except OSError:
                time.sleep(0.2)

    def _call(self, req: dict) -> dict:
        with self._lock:
            for attempt in range(2):
                try:
                    self._connect()
                    self._file.write((json.dumps(req) + "\n").encode())
                    self._file.flush()
                    line = self._file.readline()
                    if not line:
                        raise ConnectionError("motiond closed the connection")
                    break
                except (OSError, ConnectionError):
                    self._close()
                    if attempt:
                        raise
            res = json.loads(line)
        if not res.get("ok"):
            raise RuntimeError(res.get("error", "motiond error"))
        return res["result"]

    def _close(self) -> None:
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass
        self._sock = self._file = None

    # KimodoWorker interface ---------------------------------------------------------------------------------
    def generate(self, segments: list[Segment], out_dir: Path, steps: int, seed: int, transition: int = 5,
                 text_cfg: float | None = None, constraint_cfg: float | None = None,
                 constraints: Path | None = None, holds: list | None = None) -> dict:
        return self._call({"op": "generate", "config": self.config, "cache": self.cache, "holds": holds,
                           "segments": [[s.prompt, s.frames] for s in segments], "out_dir": str(out_dir),
                           "steps": steps, "seed": seed, "transition": transition, "text_cfg": text_cfg,
                           "constraint_cfg": constraint_cfg, "constraints": str(constraints) if constraints else None})

    def status(self) -> dict:
        return self._call({"op": "status"})

    def alive(self) -> bool:
        try:
            return bool(self.status()["loaded"])
        except Exception:
            return False

    @property
    def engine_dir(self) -> str:
        return self.status()["engine_dir"]

    @property
    def text_quant(self) -> str:
        return self.status()["text_quant"]

    @property
    def started_at(self) -> float | None:
        up = self.status().get("uptime_s")
        return time.time() - up if up is not None else None

    def unload(self) -> dict:
        return self._call({"op": "unload"})

    def warm(self) -> dict:
        """Start the daemon if needed and load the models (blocks until loaded; call it from a background thread)."""
        return self._call({"op": "warm", "config": self.config})

    def stop(self) -> None:
        self._close()


if __name__ == "__main__":
    main()
