"""Headless Unity validation of .kimodo clips.

Uses a separate throwaway project (unity/ValidationProject) so it works while the user has the sandbox open.
CLI:  .venv\\Scripts\\python mcp_server\\unity_validate.py [--self-test] [--no-warm] [file.kimodo ...]
      (default: all clips in the sandbox)
      .venv\\Scripts\\python mcp_server\\unity_validate.py --warm-status | --warm-stop

Warm mode (default; TTA_WARM=0 or --no-warm disables it): one batch-mode Unity stays alive on the validation
project running Promptimate.Editor.ValidationServer and answers requests through files in
unity/ValidationProject/Temp/ttaq/, so a check takes ~1 s instead of a 10-60 s editor launch. It is started on
demand, exits after TTA_WARM_IDLE_S seconds without requests (default 900) or when the process that started it
from validate() is gone, and is restarted when the package's files change (fingerprint). Any warm failure (start
or request timeout, crash, compile errors, protocol error) stops it and falls back to the one-shot launch, which
also reports compile errors. Both paths run the same BatchValidate.RunCore, so results are identical.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def _find_unity() -> Path | None:
    """$UNITY_EXE, else the newest Unity 6 editor installed via Unity Hub (default or secondary install path)."""
    if os.environ.get("UNITY_EXE"):
        return Path(os.environ["UNITY_EXE"])
    roots = [Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Unity" / "Hub" / "Editor"]
    sec = Path(os.environ.get("APPDATA", "")) / "UnityHub" / "secondaryInstallPath.json"
    if sec.exists():
        try:
            roots.insert(0, Path(json.loads(sec.read_text(encoding="utf-8"))))
        except Exception:
            pass
    found = sorted((p for r in roots if r.is_dir() for p in r.glob("6000.*/Editor/Unity.exe")), reverse=True)
    return found[0] if found else None


UNITY_EXE = _find_unity()
VPROJ = ROOT / "unity" / "ValidationProject"
PACKAGE = ROOT / "unity" / "com.promptimate.unity"
SANDBOX_GENERATED = ROOT / "unity" / "PromptimateSandbox" / "Assets" / "Promptimate" / "Generated"
LOG_DIR = ROOT / "logs"
LOCK = LOG_DIR / "unity.lock"
QDIR = VPROJ / "Temp" / "ttaq"
WARM_LOG = LOG_DIR / "unity_warm.log"
WARM_START_TIMEOUT = 600   # cold editor start incl. a possible first Library import
LAST_MODE = ""             # "warm" | "one-shot" | "" — how the last validate() ran (for tooling/benchmarks)


def _log(msg: str) -> None:
    print(f"[unity_validate] {msg}", file=sys.stderr, flush=True)


def _ensure_project() -> None:
    (VPROJ / "Packages").mkdir(parents=True, exist_ok=True)
    (VPROJ / "Assets").mkdir(exist_ok=True)
    manifest = {"dependencies": {
        "com.promptimate.unity": "file:" + PACKAGE.as_posix(),
        "com.unity.modules.animation": "1.0.0",
        "com.unity.modules.jsonserialize": "1.0.0",
    }}
    text = json.dumps(manifest, indent=2)
    mf = VPROJ / "Packages" / "manifest.json"
    if not mf.exists() or mf.read_text() != text:  # don't touch it needlessly (a running editor would re-resolve)
        mf.write_text(text)


def _unity_env() -> dict:
    # MCP stdio clients may launch us with a minimal environment; Unity's Package Manager needs these.
    env = os.environ.copy()
    for k, v in {"PROGRAMDATA": r"C:\ProgramData", "ALLUSERSPROFILE": r"C:\ProgramData",
                 "SYSTEMROOT": r"C:\WINDOWS", "WINDIR": r"C:\WINDOWS",
                 "PROGRAMFILES": r"C:\Program Files", "PROGRAMFILES(X86)": r"C:\Program Files (x86)",
                 "COMMONPROGRAMFILES": r"C:\Program Files\Common Files"}.items():
        env.setdefault(k, v)
    tmp = Path(os.environ.get("TTA_TEMP") or ROOT / ".cache" / "tmp")  # temp files stay next to the install
    tmp.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = env["TMP"] = str(tmp)
    return env


def _parse(text_lines: list[str], exit_code: int, seconds: float, log: Path) -> dict:
    reports = [json.loads(line.split("TTA_REPORT ", 1)[1]) for line in text_lines if line.startswith("TTA_REPORT ")]
    errors = [line for line in text_lines if "error CS" in line][:20]
    selftest = [line.split("TTA_SELFTEST ", 1)[1] for line in text_lines if line.startswith("TTA_SELFTEST ")]
    return {"exit_code": exit_code, "seconds": seconds, "clips": len(reports),
            "failed": sum(1 for x in reports if not x.get("passed")), "compile_errors": errors, "self_test": selftest,
            "reports": reports, "log": str(log)}


def validate(files: list[Path], timeout: int = 900, self_test: bool = False) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from kimodo_worker import gpu_lock  # one headless Unity at a time (the project can only be open once)
    global LAST_MODE
    with gpu_lock(LOCK):
        if UNITY_EXE is None or not UNITY_EXE.exists():
            return {"exit_code": -1, "seconds": 0, "clips": 0, "failed": 0, "compile_errors": [], "self_test": [],
                    "reports": [], "log": "Unity 6 editor not found; set UNITY_EXE to enable headless validation"}
        if os.environ.get("TTA_WARM", "1") != "0":
            try:
                res = _validate_warm(files, timeout, self_test)
                if res is not None:
                    LAST_MODE = "warm"
                    return res
            except Exception as e:  # never let the fast path break validation
                _log(f"warm validator failed ({type(e).__name__}: {e}); falling back to a one-shot launch")
            _warm_kill()
        else:
            _warm_shutdown()  # the project can only be open once
        LAST_MODE = "one-shot"
        return _validate(files, timeout, self_test)


def _sync_clips(files: list[Path], gen: Path, clean: bool) -> None:
    """Make Assets/Clips hold exactly `files`. clean=True wipes it (one-shot); otherwise unchanged files (and their
    .meta) are kept so a running editor only notices real changes. Every clip is force-reimported either way."""
    if clean and gen.exists():
        shutil.rmtree(gen)
    gen.mkdir(parents=True, exist_ok=True)
    wanted = {f.name: f for f in files}  # same-name files: the last one wins (as before)
    for p in gen.iterdir():
        name = p.name[:-5] if p.name.endswith(".meta") else p.name
        if name not in wanted:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    for name, f in wanted.items():
        dst = gen / name
        data = f.read_bytes()
        if not dst.exists() or dst.read_bytes() != data:
            dst.write_bytes(data)


def _validate(files: list[Path], timeout: int, self_test: bool) -> dict:
    _ensure_project()
    _sync_clips(files, VPROJ / "Assets" / "Clips", clean=True)
    extra = ["-ttaSelfTest"] if self_test else []
    log = LOG_DIR / "unity_validate.log"
    log.parent.mkdir(exist_ok=True)
    t0 = time.time()
    r = subprocess.run([str(UNITY_EXE), "-batchmode", "-nographics", "-projectPath", str(VPROJ),
                        "-executeMethod", "Promptimate.Editor.BatchValidate.Run", "-logFile", str(log), *extra],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, env=_unity_env())
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    return _parse(text.splitlines(), r.returncode, round(time.time() - t0, 1), log)


# ---------------------------------------------------------------------------------------------- warm validator

_k32 = ctypes.WinDLL("kernel32", use_last_error=True) if os.name == "nt" else None


def _unity_pid_alive(pid: int) -> bool:
    """True if `pid` is a running Unity.exe (guards against PID reuse)."""
    if not pid or _k32 is None:
        return False
    h = _k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        if not _k32.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
            return False
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if not _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return False
        return Path(buf.value).name.lower() == "unity.exe"
    finally:
        _k32.CloseHandle(h)


def _fingerprint() -> str:
    """Changes whenever the package (scripts, asmdef, package.json), the manifest or the editor changes."""
    h = hashlib.sha1(str(UNITY_EXE).encode())
    for p in sorted(PACKAGE.rglob("*")):
        if p.is_file():  # content, not mtime: a touch without an edit doesn't force a restart
            h.update(p.relative_to(PACKAGE).as_posix().encode() + b"\0" + hashlib.sha1(p.read_bytes()).digest())
    mf = VPROJ / "Packages" / "manifest.json"
    if mf.exists():
        h.update(mf.read_bytes())
    return h.hexdigest()[:16]


def _read_status() -> dict | None:
    try:
        return json.loads((QDIR / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _live_status() -> dict | None:
    st = _read_status()
    return st if st and st.get("state") == "ready" and _unity_pid_alive(st.get("pid", 0)) else None


def _warm_start() -> dict | None:
    _ensure_project()
    with_status = _read_status()
    if with_status and _unity_pid_alive(with_status.get("pid", 0)):
        _warm_kill()
    QDIR.mkdir(parents=True, exist_ok=True)
    for p in QDIR.glob("*"):
        p.unlink(missing_ok=True)
    fp = _fingerprint()
    parent = os.environ.get("TTA_WARM_PARENT_PID", str(os.getpid() if __name__ != "__main__" else 0))
    cmd = [str(UNITY_EXE), "-batchmode", "-nographics", "-projectPath", str(VPROJ),
           "-executeMethod", "Promptimate.Editor.ValidationServer.Start", "-logFile", str(WARM_LOG),
           "-ttaServer", "-ttaParentPid", parent, "-ttaIdleSeconds", os.environ.get("TTA_WARM_IDLE_S", "900"),
           "-ttaFingerprint", fp]
    LOG_DIR.mkdir(exist_ok=True)
    # Detached so it outlives a CLI call; break away from the caller's job object when allowed.
    base = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_unity_env(),
              close_fds=True)
    try:
        proc = subprocess.Popen(cmd, creationflags=base | 0x01000000, **kw)  # CREATE_BREAKAWAY_FROM_JOB
    except OSError:
        proc = subprocess.Popen(cmd, creationflags=base, **kw)
    _log(f"starting warm Unity (pid {proc.pid}, log {WARM_LOG})")
    t0 = time.time()
    while time.time() - t0 < WARM_START_TIMEOUT:
        if proc.poll() is not None:
            _log(f"warm Unity exited during startup (code {proc.returncode}); see {WARM_LOG}")
            return None
        st = _read_status()
        if st and st.get("pid") == proc.pid and st.get("state") == "ready":
            _log(f"warm Unity ready after {time.time() - t0:.1f}s")
            return st
        time.sleep(0.1)
    _log(f"warm Unity not ready after {WARM_START_TIMEOUT}s")
    return None


def _request(cmd: str, timeout: float, self_test: bool = False, pid: int = 0) -> dict | None:
    rid = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    req = QDIR / f"{rid}.req.json"
    resp = QDIR / f"{rid}.resp.json"
    tmp = QDIR / f"{rid}.req.tmp"
    tmp.write_text(json.dumps({"id": rid, "cmd": cmd, "selfTest": self_test}), encoding="utf-8")
    os.replace(tmp, req)
    t0, last_check = time.time(), time.time()
    while time.time() - t0 < timeout:
        if resp.exists():
            try:
                data = json.loads(resp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                time.sleep(0.01)
                continue
            resp.unlink(missing_ok=True)
            return data
        if pid and time.time() - last_check > 0.5:
            last_check = time.time()
            if not _unity_pid_alive(pid):
                _log("warm Unity died while serving a request")
                break
        time.sleep(0.01)
    req.unlink(missing_ok=True)
    return None


def _validate_warm(files: list[Path], timeout: int, self_test: bool) -> dict | None:
    t0 = time.time()
    _ensure_project()
    st = _live_status()
    if st and st.get("fingerprint") != _fingerprint():
        _log("package changed since the warm Unity started; restarting it")
        _warm_shutdown()
        st = None
    if st is None:
        st = _warm_start()
        if st is None:
            return None
    _sync_clips(files, VPROJ / "Assets" / "Clips", clean=False)
    req_timeout = min(timeout, 120 + 15 * len(files) + (180 if self_test else 0))
    data = _request("validate", req_timeout, self_test, pid=st["pid"])
    if data is None:
        if _unity_pid_alive(st["pid"]):
            _log(f"no answer from the warm Unity within {req_timeout}s")
        return None
    if data.get("status") != "ok":
        _log(f"warm Unity answered '{data.get('status')}'" + (" (falling back to collect compile errors)"
             if data.get("status") == "compile_failed" else ""))
        return None
    lines = data.get("lines") or []
    log = LOG_DIR / "unity_validate.log"
    log.write_text(f"# warm validator (pid {st['pid']}; full editor log: {WARM_LOG})\n" + "\n".join(lines) + "\n",
                   encoding="utf-8")
    return _parse(lines, int(data.get("exitCode", -1)), round(time.time() - t0, 1), log)


def _wait_gone(pid: int, timeout: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not _unity_pid_alive(pid):
            return True
        time.sleep(0.1)
    return False


def _warm_kill() -> None:
    """Hard stop (used before falling back): kill the warm editor and its helper processes."""
    st = _read_status()
    pid = st.get("pid", 0) if st else 0
    if pid and _unity_pid_alive(pid):
        _log(f"killing warm Unity pid {pid}")
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
        _wait_gone(pid, 30)
    (QDIR / "status.json").unlink(missing_ok=True)


def _warm_shutdown(timeout: float = 30) -> bool:
    """Graceful stop; returns True if a warm editor was running."""
    st = _live_status()
    if st is None:
        return False
    data = _request("stop", timeout=10, pid=st["pid"])
    if data is None or not _wait_gone(st["pid"], timeout):
        _warm_kill()
    return True


def warm_status() -> dict:
    st = _read_status()
    alive = bool(st) and _unity_pid_alive(st.get("pid", 0))
    out = {"running": alive and st.get("state") == "ready", "status_file": str(QDIR / "status.json"),
           "log": str(WARM_LOG)}
    if st:
        out.update(pid=st.get("pid"), state=st.get("state") if alive else f"{st.get('state')} (process gone)",
                   fingerprint=st.get("fingerprint"), fingerprint_current=st.get("fingerprint") == _fingerprint())
        if alive:
            out["armed_seconds_ago"] = round(time.time() - st.get("since", 0) / 1000, 1)
            t0 = time.time()
            pong = _request("ping", timeout=10, pid=st["pid"])
            out["ping_ms"] = round((time.time() - t0) * 1000) if pong else None
    return out


def warm_stop() -> bool:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from kimodo_worker import gpu_lock
    with gpu_lock(LOCK):  # never stop it in the middle of someone's validation
        return _warm_shutdown()


if __name__ == "__main__":
    if "--warm-status" in sys.argv:
        print(json.dumps(warm_status(), indent=2))
        sys.exit(0)
    if "--warm-stop" in sys.argv:
        print("stopped" if warm_stop() else "not running")
        sys.exit(0)
    if "--no-warm" in sys.argv:
        os.environ["TTA_WARM"] = "0"
    self_test = "--self-test" in sys.argv
    args = [Path(a) for a in sys.argv[1:] if not a.startswith("--")] or sorted(SANDBOX_GENERATED.glob("*.kimodo"))
    res = validate(args, self_test=self_test)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["exit_code"] == 0 and res["clips"] == len(args) else 1)
