"""Render a DemoStudio shot JSON to MP4: Unity (GPU, batchmode) -> PNG frames -> ffmpeg (H.264)."""
import json, os, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
UNITY = os.environ.get("UNITY_EXE", r"D:\Unity\Editors\6000.0.34f1\Editor\Unity.exe")
FFMPEG = r"D:\tools\ffmpeg\bin\ffmpeg.exe"
PROJECT = ROOT / "unity" / "DemoStudio"

def render(shot_path: Path) -> Path:
    shot = json.loads(shot_path.read_text())
    name = shot_path.stem
    frames = ROOT / "demo" / "frames" / name
    shot["outDir"] = str(frames)
    resolved = ROOT / "demo" / "frames" / f"{name}.resolved.json"
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(shot))
    env = os.environ.copy(); env["TEMP"] = env["TMP"] = r"D:\tmp"
    log = ROOT / "logs" / f"render_{name}.log"
    t0 = time.time()
    r = subprocess.run([UNITY, "-batchmode", "-projectPath", str(PROJECT), "-executeMethod", "DemoRenderer.Run",
                        "-shot", str(resolved), "-logFile", str(log)], stdin=subprocess.DEVNULL, env=env)
    text = log.read_text(encoding="utf-8", errors="replace")
    if r.returncode != 0 or "DEMO_DONE" not in text:
        errs = [l for l in text.splitlines() if "DEMO_ERROR" in l or "error CS" in l or "Exception" in l][:15]
        raise SystemExit(f"render failed ({r.returncode}); see {log}\n" + "\n".join(errs))
    out = ROOT / "demo" / "renders" / f"{name}.mp4"
    out.parent.mkdir(exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-framerate", str(shot.get("fps", 30)), "-i", str(frames / "f%05d.png"),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", str(out)], check=True)
    print(f"{name}: {time.time()-t0:.0f}s -> {out}")
    return out

if __name__ == "__main__":
    for p in sys.argv[1:]:
        render(Path(p))
