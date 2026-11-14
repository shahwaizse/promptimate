"""Package the prebuilt kimodo.cpp Vulkan engine for Windows into dist/kimodo-engine-win64-vulkan.zip (for GitHub Releases)."""
import hashlib, subprocess, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "third_party" / "kimodo.cpp"
BUILD = SRC / "build" / "release"
OUT = ROOT / "dist" / "kimodo-engine-win64-vulkan.zip"
files = {BUILD / "kmd-generate.exe": "kmd-generate.exe"}
files.update({p: p.name for p in (BUILD / "bin").glob("ggml*.dll")})
files.update({SRC / "LICENSE": "LICENSE-kimodo.cpp.txt", SRC / "NOTICE": "NOTICE-kimodo.cpp.txt", SRC / "ggml" / "LICENSE": "LICENSE-ggml.txt"})
rev = subprocess.run(["git", "-C", str(SRC), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
OUT.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for src, name in files.items():
        z.write(src, name)
    z.writestr("BUILD-INFO.txt", f"kimodo.cpp {rev}, ggml Vulkan backend, MSVC x64 Release. Requires a Vulkan GPU driver and the VC++ 2015-2022 runtime.\n")
print(OUT, OUT.stat().st_size // 1024, "KiB sha256", hashlib.sha256(OUT.read_bytes()).hexdigest())
