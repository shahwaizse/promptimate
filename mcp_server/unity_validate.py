"""Headless Unity validation of .kimodo clips.

Uses a separate throwaway project (unity/ValidationProject) so it works while the user has the sandbox open.
CLI:  .venv\\Scripts\\python mcp_server\\unity_validate.py [file.kimodo ...]   (default: all clips in the sandbox)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
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


def _ensure_project() -> None:
    (VPROJ / "Packages").mkdir(parents=True, exist_ok=True)
    (VPROJ / "Assets").mkdir(exist_ok=True)
    manifest = {"dependencies": {
        "com.promptimate.unity": "file:" + PACKAGE.as_posix(),
        "com.unity.modules.animation": "1.0.0",
        "com.unity.modules.jsonserialize": "1.0.0",
    }}
    (VPROJ / "Packages" / "manifest.json").write_text(json.dumps(manifest, indent=2))


def validate(files: list[Path], timeout: int = 900, self_test: bool = False) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from kimodo_worker import gpu_lock  # one headless Unity at a time (the project can only be open once)
    with gpu_lock(ROOT / "logs" / "unity.lock"):
        return _validate(files, timeout, self_test)


def _validate(files: list[Path], timeout: int, self_test: bool) -> dict:
    if UNITY_EXE is None or not UNITY_EXE.exists():
        return {"exit_code": -1, "seconds": 0, "clips": 0, "failed": 0, "compile_errors": [], "self_test": [],
                "reports": [], "log": "Unity 6 editor not found; set UNITY_EXE to enable headless validation"}
    _ensure_project()
    gen = VPROJ / "Assets" / "Clips"
    if gen.exists():
        shutil.rmtree(gen)
    gen.mkdir(parents=True)
    for f in files:
        shutil.copyfile(f, gen / f.name)
    extra = ["-ttaSelfTest"] if self_test else []
    log = ROOT / "logs" / "unity_validate.log"
    log.parent.mkdir(exist_ok=True)
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
    t0 = time.time()
    r = subprocess.run([str(UNITY_EXE), "-batchmode", "-nographics", "-projectPath", str(VPROJ),
                        "-executeMethod", "Promptimate.Editor.BatchValidate.Run", "-logFile", str(log), *extra],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, env=env)
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    reports = [json.loads(line.split("TTA_REPORT ", 1)[1]) for line in text.splitlines() if line.startswith("TTA_REPORT ")]
    errors = [line for line in text.splitlines() if "error CS" in line][:20]
    selftest = [line.split("TTA_SELFTEST ", 1)[1] for line in text.splitlines() if line.startswith("TTA_SELFTEST ")]
    return {"exit_code": r.returncode, "seconds": round(time.time() - t0, 1), "clips": len(reports),
            "failed": sum(1 for x in reports if not x.get("passed")), "compile_errors": errors, "self_test": selftest,
            "reports": reports, "log": str(log)}


if __name__ == "__main__":
    self_test = "--self-test" in sys.argv
    args = [Path(a) for a in sys.argv[1:] if not a.startswith("--")] or sorted(SANDBOX_GENERATED.glob("*.kimodo"))
    res = validate(args, self_test=self_test)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["exit_code"] == 0 and res["clips"] == len(args) else 1)
