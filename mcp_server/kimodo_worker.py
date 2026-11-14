"""Long-lived kimodo.cpp worker (kmd-generate --server) with models kept resident between requests.

Protocol (one line per request, tab-separated):
    TRANSITION  STEPS  SEED  OUTPUT_DIR  FRAMES_1  PROMPT_FILE_1  [FRAMES_2  PROMPT_FILE_2 ...]
Reply: "OK\t<frames>\t<joints>" or "ERR\t<message>".
"""
from __future__ import annotations

import contextlib
import msvcrt
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Engine location: $KIMODO_ENGINE_DIR, else engine/ (prebuilt, from setup.ps1), else a local source build.
_engine_candidates = [Path(os.environ["KIMODO_ENGINE_DIR"])] if os.environ.get("KIMODO_ENGINE_DIR") else []
_engine_candidates += [ROOT / "engine", ROOT / "third_party" / "kimodo.cpp" / "build" / "release"]
KIMODO_BUILD = next((p for p in _engine_candidates if (p / "kmd-generate.exe").exists()), _engine_candidates[-1])
MODELS = ROOT / "models"
MOTION_GGUF = MODELS / "models" / "kimodo-soma-rp-v1.1-f32.gguf"
TEXT_GGUF = {
    "q4_k_m": MODELS / "Llama-3-Kimodo-Q4_K_M.gguf",
    "q8_0": MODELS / "Llama-3-Kimodo-Q8_0.gguf",
}
LOG_DIR = ROOT / "logs"
GPU_LOCK = ROOT / "logs" / "gpu.lock"
IDLE_UNLOAD_S = float(os.environ.get("KIMODO_IDLE_UNLOAD_S", "600"))


@contextlib.contextmanager
def gpu_lock(path: Path = GPU_LOCK):
    """Machine-wide lock so several MCP server instances never run generations on the 8 GB GPU at once."""
    LOG_DIR.mkdir(exist_ok=True)
    with open(path, "a+b") as fh:
        fh.seek(0)
        while True:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.5)
        try:
            yield
        finally:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


@dataclass
class Segment:
    prompt: str
    frames: int


class KimodoWorker:
    def __init__(self, text_quant: str | None = None):
        self.text_quant = text_quant or os.environ.get("KIMODO_TEXT_QUANT", "q4_k_m")
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.started_at: float | None = None
        self.last_used = time.time()
        threading.Thread(target=self._idle_reaper, daemon=True).start()

    def _idle_reaper(self) -> None:
        """Unload the models (free ~6 GB VRAM) after IDLE_UNLOAD_S without requests."""
        while True:
            time.sleep(15)
            with self.lock:
                if self.alive() and time.time() - self.last_used > IDLE_UNLOAD_S:
                    self.stop()

    def _start(self) -> None:
        text = TEXT_GGUF[self.text_quant]
        for p in (KIMODO_BUILD / "kmd-generate.exe", MOTION_GGUF, text):
            if not p.exists():
                raise RuntimeError(f"missing {p}")
        env = os.environ.copy()
        env["PATH"] = f"{KIMODO_BUILD / 'bin'};{KIMODO_BUILD};{env.get('PATH', '')}"
        env.setdefault("KIMODO_BACKEND", "vulkan")
        tmp = Path(os.environ.get("TTA_TEMP") or ROOT / ".cache" / "tmp")  # temp files stay next to the install
        tmp.mkdir(parents=True, exist_ok=True)
        env["TEMP"] = env["TMP"] = str(tmp)
        # Keep the whole encoder in VRAM (Q4_K_M ~5 GB + motion ~1.1 GB fits in 8 GB).
        env.setdefault("KIMODO_TEXT_LAYER_CHUNK", "32")
        env.setdefault("KIMODO_PROFILE", "1")
        LOG_DIR.mkdir(exist_ok=True)
        self._stderr = open(LOG_DIR / "worker.stderr.log", "ab")
        self.proc = subprocess.Popen(
            [str(KIMODO_BUILD / "kmd-generate.exe"), "--server", str(MOTION_GGUF), str(text)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
            env=env, text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.started_at = time.time()

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def generate(self, segments: list[Segment], out_dir: Path, steps: int, seed: int,
                 transition: int = 5) -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        fields = [str(transition), str(steps), str(seed), str(out_dir)]
        for i, seg in enumerate(segments):
            pf = out_dir / f"prompt_{i}.txt"
            pf.write_text(seg.prompt, encoding="utf-8")
            fields += [str(seg.frames), str(pf)]
        with self.lock, gpu_lock():
            cold = not self.alive()
            if cold:
                self._start()
            t0 = time.time()
            self.proc.stdin.write("\t".join(fields) + "\n")
            self.proc.stdin.flush()
            reply = self.proc.stdout.readline().strip()
            dt = time.time() - t0
            self.last_used = time.time()
        if not reply:
            code = self.proc.poll()
            self.proc = None
            raise RuntimeError(f"worker died (exit {code}); see logs/worker.stderr.log")
        parts = reply.split("\t")
        if parts[0] != "OK":
            raise RuntimeError("kimodo error: " + " ".join(parts[1:]))
        return {"frames": int(parts[1]), "joints": int(parts[2]), "seconds": round(dt, 2),
                "cold_start": cold, "text_quant": self.text_quant}

    def stop(self) -> None:
        if self.alive():
            self.proc.stdin.close()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
