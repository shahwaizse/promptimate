"""Long-lived kimodo.cpp worker (kmd-generate --server) with models kept resident between requests.

Protocol (one line per request, tab-separated):
    TRANSITION  STEPS  SEED  OUTPUT_DIR  FRAMES_1  PROMPT_FILE_1  [FRAMES_2  PROMPT_FILE_2 ...]
  or, with the Promptimate engine patches:
    V2  [cfg=F]  [ccfg=F]  [constraints=PATH]  --  TRANSITION  STEPS  SEED  OUTPUT_DIR  FRAMES_1  PROMPT_FILE_1  [...]
  (cfg = text guidance weight, ccfg = constraint guidance weight, constraints = file from constraints.Constraints.save).
  The patched engine also writes foot_contacts.f32 [frames x 4].
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
_engine_candidates += [ROOT / "engine", ROOT / "third_party" / "kimodo.cpp" / "build" / "promptimate",
                       ROOT / "third_party" / "kimodo.cpp" / "build" / "release"]
KIMODO_BUILD = next((p for p in _engine_candidates if (p / "kmd-generate.exe").exists()), _engine_candidates[-1])
MODELS = ROOT / "models"
MOTION_GGUF = MODELS / "models" / "kimodo-soma-rp-v1.1-f32.gguf"
TEXT_GGUF = {
    "q4_k_m": MODELS / "Llama-3-Kimodo-Q4_K_M.gguf",
    "q8_0": MODELS / "Llama-3-Kimodo-Q8_0.gguf",
}
LOG_DIR = ROOT / "logs"
GPU_LOCK = ROOT / "logs" / "gpu.lock"
# Touched by an instance waiting for the GPU: whoever keeps models resident unloads them (8 GB cannot hold two
# copies; a second resident copy spills into shared memory and everything slows down ~20x).
RELEASE_REQUEST = ROOT / "logs" / "gpu.release_request"
IDLE_UNLOAD_S = float(os.environ.get("KIMODO_IDLE_UNLOAD_S", "600"))
TEXT_RELEASE_S = float(os.environ.get("KIMODO_TEXT_RELEASE_S", "180"))  # idle seconds before freeing the text encoder
TEXT_RELEASE_OVERRIDE = ROOT / "logs" / "motiond.text_release_s"   # optional live override (seconds)


def text_release_s() -> float:
    try:
        return float(TEXT_RELEASE_OVERRIDE.read_text().strip())
    except (OSError, ValueError):
        return TEXT_RELEASE_S
IDLE_OVERRIDE = ROOT / "logs" / "motiond.idle_s"   # optional file with seconds; re-read live (e.g. low-RAM nights)


def idle_unload_s() -> float:
    try:
        return float(IDLE_OVERRIDE.read_text().strip())
    except (OSError, ValueError):
        return IDLE_UNLOAD_S


@contextlib.contextmanager
def gpu_lock(path: Path = GPU_LOCK):
    """Machine-wide lock so several MCP server instances never run generations on the 8 GB GPU at once."""
    LOG_DIR.mkdir(exist_ok=True)
    with open(path, "a+b") as fh:
        fh.seek(0)
        while True:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                if path == GPU_LOCK:  # (again) after acquiring: any other resident instance unloads now
                    with contextlib.suppress(OSError):
                        RELEASE_REQUEST.touch()
                break
            except OSError:
                if path == GPU_LOCK:
                    with contextlib.suppress(OSError):
                        RELEASE_REQUEST.touch()
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


EMBED_CACHE = ROOT / ".cache" / "embeddings"
PREFETCH_BATCH = 16       # engine limit: 16 segments per sequence request
PREFETCH_FRAMES = 6       # shortest segment the default 5-frame transition allows


def embedding_cache_file(prompt: str, text_quant: str, extra_env: dict | None = None) -> Path:
    """Where the Promptimate engine stores the embedding of `prompt` (FNV-1a 64 of prompt + 0x1f + text model path,
    mirrors model.cpp generate_text_sequence)."""
    cache_dir = Path((extra_env or {}).get("KIMODO_EMBED_CACHE_DIR") or os.environ.get("KIMODO_EMBED_CACHE_DIR")
                     or EMBED_CACHE)
    h = 1469598103934665603
    for c in (prompt + "\x1f" + str(TEXT_GGUF[text_quant])).encode("utf-8"):
        h = ((h ^ c) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return cache_dir / f"{h:016x}.f32"


def prefetch_embeddings(generate, prompts: list[str], text_quant: str, extra_env: dict | None = None,
                        out_dir: Path | None = None) -> dict:
    """Encode every prompt that has no cached embedding yet, PREFETCH_BATCH prompts per engine request.

    Why: the text encoder (~4.4 GB) is loaded lazily and released when idle, and loading it costs 30 s from the HDD
    (minutes when RAM is tight) while encoding one prompt costs ~0.8 s. A job that generates its clips one by one,
    with renders in between, reloads the encoder every few prompts. Prefetching pays one load per job.
    The embeddings are produced by the same engine code path as a normal generation (written to the engine's disk
    cache), so later generations are bit-identical to ones that encoded the prompt themselves.
    `generate(segments, out_dir, steps, seed, transition)` runs one uncached engine request."""
    t0 = time.time()
    seen, todo = set(), []
    for p in prompts:
        p = (p or "").strip()
        if p and p not in seen:
            seen.add(p)
            if not embedding_cache_file(p, text_quant, extra_env).exists():
                todo.append(p)
    out_dir = Path(out_dir or ROOT / ".cache" / "prefetch")
    errors = {}

    def run(batch: list[str]) -> None:
        generate([Segment(p, PREFETCH_FRAMES) for p in batch], out_dir, 1, 0, 5)

    for i in range(0, len(todo), PREFETCH_BATCH):
        batch = todo[i:i + PREFETCH_BATCH]
        try:
            run(batch)
        except RuntimeError:  # one bad prompt fails the whole request: isolate it
            for p in batch:
                try:
                    run([p])
                except RuntimeError as e:
                    errors[p] = str(e)
    encoded = sum(embedding_cache_file(p, text_quant, extra_env).exists() for p in todo)
    return {"prompts": len(seen), "already_cached": len(seen) - len(todo), "encoded": encoded,
            "errors": errors, "seconds": round(time.time() - t0, 2)}


class KimodoWorker:
    def __init__(self, text_quant: str | None = None, engine_dir: Path | None = None, extra_env: dict | None = None):
        self.text_quant = text_quant or os.environ.get("KIMODO_TEXT_QUANT", "q4_k_m")
        self.engine_dir = Path(engine_dir) if engine_dir else KIMODO_BUILD
        self.extra_env = dict(extra_env or {})
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.started_at: float | None = None
        self.last_used = time.time()
        threading.Thread(target=self._idle_reaper, daemon=True).start()

    def _idle_reaper(self) -> None:
        """Unload the models (free ~6 GB VRAM) after IDLE_UNLOAD_S without requests, or as soon as another
        instance is waiting for the GPU (it touched RELEASE_REQUEST after our last request finished)."""
        n = 0
        while True:
            time.sleep(1)
            n += 1
            if not self.alive():
                continue
            try:
                requested = RELEASE_REQUEST.stat().st_mtime > self.last_used
            except OSError:
                requested = False
            # low-memory mode: free the text encoder after a short idle period (motion model stays warm)
            if (self.alive() and not getattr(self, "_text_released", True)
                    and time.time() - self.last_used > text_release_s()):
                if self.lock.acquire(blocking=False):
                    try:
                        if self.alive():
                            self.proc.stdin.write("RELEASE_TEXT\n")
                            self.proc.stdin.flush()
                            self.proc.stdout.readline()
                            self._text_released = True
                    except OSError:
                        pass
                    finally:
                        self.lock.release()
            if requested or n % 15 == 0:
                if self.lock.acquire(blocking=False):  # never interrupt a running generation
                    try:
                        if self.alive() and (requested or time.time() - self.last_used > idle_unload_s()):
                            self.stop()
                    finally:
                        self.lock.release()

    def _start(self) -> None:
        text = TEXT_GGUF[self.text_quant]
        for p in (self.engine_dir / "kmd-generate.exe", MOTION_GGUF, text):
            if not p.exists():
                raise RuntimeError(f"missing {p}")
        env = os.environ.copy()
        env["PATH"] = f"{self.engine_dir / 'bin'};{self.engine_dir};{env.get('PATH', '')}"
        env.setdefault("KIMODO_BACKEND", "vulkan")
        tmp = Path(os.environ.get("TTA_TEMP") or ROOT / ".cache" / "tmp")  # temp files stay next to the install
        tmp.mkdir(parents=True, exist_ok=True)
        env["TEMP"] = env["TMP"] = str(tmp)
        # Text encoder on the CPU (Promptimate engine): encoding a prompt takes ~0.6 s there and is cached per prompt,
        # and it leaves the GPU to the motion model (~1.1 GB VRAM total instead of ~6 GB, room for Unity).
        env.setdefault("KIMODO_TEXT_BACKEND", "cpu")
        # Low-memory mode: the ~5 GB text encoder is loaded only for prompts that aren't cached and released right
        # after encoding; embeddings persist on disk. Engine RAM between encodes drops from ~6.5 GB to ~1.5 GB,
        # which matters when Unity/Roblox Studio run alongside on a 16 GB machine. (Ignored by older engines.)
        env.setdefault("KIMODO_TEXT_LAZY", "1")
        env.setdefault("KIMODO_EMBED_CACHE_DIR", str(EMBED_CACHE))
        env.setdefault("KIMODO_TEXT_LAYER_CHUNK", "32")  # (only matters if the encoder runs on the GPU)
        # The motion graph cache keeps per-stage allocators that make larger graphs (constrained batch-3 passes,
        # 10 s clips) 3-5x slower on this driver; without it a plain 5 s clip is ~10% slower. Net win.
        env.setdefault("KIMODO_MOTION_GRAPH_CACHE", "0")
        env.setdefault("KIMODO_PROFILE", "1")
        env.update(self.extra_env)
        LOG_DIR.mkdir(exist_ok=True)
        self._stderr = open(LOG_DIR / "worker.stderr.log", "ab")
        self.proc = subprocess.Popen(
            [str(self.engine_dir / "kmd-generate.exe"), "--server", str(MOTION_GGUF), str(text)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
            env=env, text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.started_at = time.time()

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def generate(self, segments: list[Segment], out_dir: Path, steps: int, seed: int,
                 transition: int = 5, text_cfg: float | None = None, constraint_cfg: float | None = None,
                 constraints: Path | None = None, holds: list | None = None) -> dict:
        """text_cfg / constraint_cfg: guidance weights (engine default 2.0). constraints: binary constraint file.
        holds: [(first, last)] global frames where the engine holds the root still at the position the motion
        reaches when the range starts (ranges must start after the first segment; needs engine v0.3).
        These options need the Promptimate-patched engine (V2 protocol)."""
        out_dir.mkdir(parents=True, exist_ok=True)
        fields = [str(transition), str(steps), str(seed), str(out_dir)]
        opts = []
        if text_cfg is not None and float(text_cfg) != 2.0:  # 2.0 = engine default; works on stock engines too
            opts.append(f"cfg={float(text_cfg):g}")
        if constraint_cfg is not None and float(constraint_cfg) != 2.0:
            opts.append(f"ccfg={float(constraint_cfg):g}")
        if constraints is not None:
            opts.append(f"constraints={constraints}")
        if holds:
            opts.append("holds=" + ",".join(f"{int(a)}:{int(b)}" for a, b in holds))
        if opts:
            fields = ["V2", *opts, "--", *fields]
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
            self._text_released = False
        if not reply:
            code = self.proc.poll()
            self.proc = None
            raise RuntimeError(f"worker died (exit {code}); see logs/worker.stderr.log")
        parts = reply.split("\t")
        if parts[0] != "OK":
            msg = " ".join(parts[1:])
            if opts and ("stoul" in msg or "invalid server request" in msg):
                raise RuntimeError("this kimodo engine is too old for text_cfg / root_path / loop (needs the Promptimate "
                                   "engine build); re-run setup.ps1 to update engine/. Engine said: " + msg)
            raise RuntimeError("kimodo error: " + msg)
        return {"frames": int(parts[1]), "joints": int(parts[2]), "seconds": round(dt, 2),
                "cold_start": cold, "text_quant": self.text_quant, "text_cfg": text_cfg}

    def prefetch(self, prompts: list[str]) -> dict:
        """Encode all uncached prompts of a job in a few batched requests (see prefetch_embeddings)."""
        return prefetch_embeddings(
            lambda segs, d, steps, seed, tr: self.generate(segs, d, steps=steps, seed=seed, transition=tr),
            prompts, self.text_quant, self.extra_env)

    def warm(self) -> dict:
        """Load the models now with a tiny generation (no-op if already loaded)."""
        if self.alive():
            return {"warmed": False, "seconds": 0.0}
        t0 = time.time()
        self.generate([Segment("a person stands still", 30)], ROOT / ".cache" / "warm", steps=1, seed=0)
        return {"warmed": True, "seconds": round(time.time() - t0, 2)}

    def stop(self) -> None:
        if self.alive():
            self.proc.stdin.close()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
