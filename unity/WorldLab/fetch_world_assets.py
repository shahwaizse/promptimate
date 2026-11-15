"""Download the text-to-world asset library (world_assets.json) into unity/WorldLab/Assets/WorldAssets/ (gitignored).

    .venv\\Scripts\\python.exe unity\\WorldLab\\fetch_world_assets.py [--only id,id] [--force] [--hdri-res 2k]

Everything is CC0 and needs no login:
  * Poly Haven (api.polyhaven.com): scanned models as glTF with 1k textures, PBR textures (diffuse, GL normal,
    roughness), HDRIs (.hdr).
  * ambientCG: PBR materials (1K-JPG zips).
  * Kenney Furniture Kit, Quaternius characters and props: copied from unity/DemoStudio/Assets/ThirdParty when that
    is there (the render_shot kits), else downloaded with DemoStudio's fetch_render_assets.py.
A LICENSES.md with the source of every file is written next to them. Nothing third-party is committed.
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = HERE / "world_assets.json"
DEST = HERE / "Assets" / "WorldAssets"
THIRD = HERE / "Assets" / "ThirdParty"
DEMO_THIRD = ROOT / "unity" / "DemoStudio" / "Assets" / "ThirdParty"
UA = "PromptimateWorldLab/0.1 (asset fetch)"


def _get(url: str, timeout: int = 180) -> bytes:
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # flaky CDN: retry
            last = e
            time.sleep(1.5 + 2 * attempt)
    raise RuntimeError(f"download failed: {url}: {last}")


def _json(url: str) -> dict:
    return json.loads(_get(url))


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


# --- Poly Haven -------------------------------------------------------------------------------------------------------

def ph_model(ref: str, force: bool) -> Path:
    """glTF + .bin + 1k textures, keeping the relative layout the .gltf expects."""
    d = DEST / "Models" / ref
    gltf = d / f"{ref}.gltf"
    if gltf.exists() and not force:
        return gltf
    files = _json(f"https://api.polyhaven.com/files/{ref}")
    g = files["gltf"]
    res = "1k" if "1k" in g else sorted(g)[0]
    entry = g[res]["gltf"]
    for rel, inc in entry.get("include", {}).items():
        _write(d / rel, _get(inc["url"]))
    _write(gltf, _get(entry["url"]))
    return gltf


def ph_texture(ref: str, force: bool) -> Path:
    d = DEST / "Materials" / ref
    if (d / f"{ref}_diff.jpg").exists() and not force:
        return d
    files = _json(f"https://api.polyhaven.com/files/{ref}")
    for key, suffix in (("Diffuse", "diff"), ("nor_gl", "nor_gl"), ("Rough", "rough")):
        if key in files:
            _write(d / f"{ref}_{suffix}.jpg", _get(files[key]["1k"]["jpg"]["url"]))
    return d


def ph_hdri(ref: str, res: str, force: bool) -> Path:
    out = DEST / "HDRI" / f"{ref}.hdr"
    if out.exists() and not force:
        return out
    files = _json(f"https://api.polyhaven.com/files/{ref}")
    h = files["hdri"]
    r = res if res in h else ("1k" if "1k" in h else sorted(h)[0])
    _write(out, _get(h[r]["hdr"]["url"]))
    return out


# --- ambientCG ----------------------------------------------------------------------------------------------------------

def acg_material(ref: str, force: bool) -> Path:
    d = DEST / "Materials" / ref
    if (d / f"{ref}_diff.jpg").exists() and not force:
        return d
    z = zipfile.ZipFile(io.BytesIO(_get(f"https://ambientcg.com/get?file={ref}_1K-JPG.zip", timeout=300)))
    names = {"_Color.jpg": "diff", "_NormalGL.jpg": "nor_gl", "_Roughness.jpg": "rough"}
    for n in z.namelist():
        for tail, suffix in names.items():
            if n.endswith(tail):
                _write(d / f"{ref}_{suffix}.jpg", z.read(n))
    return d


# --- Kenney / Quaternius kits ---------------------------------------------------------------------------------------------

def kits(force: bool, log) -> None:
    want = ["Kenney/Furniture", "Kenney/AnimatedCharacters1", "Kenney/AnimatedCharacters2", "Kenney/AnimatedCharacters3",
            "Quaternius", "Props"]
    if DEMO_THIRD.is_dir():
        for w in want:
            src, dst = DEMO_THIRD / w, THIRD / w
            if src.is_dir() and (force or not dst.exists()):
                log(f"copy kit {w}")
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.meta"))
        lic = DEMO_THIRD / "LICENSES.md"
        if lic.exists():
            THIRD.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(lic, THIRD / "LICENSES.md")
        return
    # No DemoStudio kits on this machine: fetch them with its downloader, pointed at our folder.
    sys.path.insert(0, str(ROOT / "unity" / "DemoStudio"))
    import fetch_render_assets as fra
    fra.DEST = THIRD
    fra.fetch(log=log)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--hdri-res", default="2k")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--skip-kits", action="store_true")
    a = ap.parse_args(argv)
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    only = {x for x in a.only.split(",") if x}
    log = lambda m: print(m, flush=True)
    if not a.skip_kits:
        kits(a.force, log)
    jobs = []
    for m in man["models"]:
        if m["src"] == "polyhaven" and (not only or m["id"] in only):
            jobs.append(("model", m))
    for m in man["materials"]:
        if not only or m["id"] in only:
            jobs.append(("material", m))
    for m in man["hdris"]:
        if not only or m["id"] in only:
            jobs.append(("hdri", m))
    ok, failed = [], []

    def run(job):
        kind, m = job
        t0 = time.time()
        try:
            if kind == "model":
                p = ph_model(m["ref"], a.force)
            elif kind == "hdri":
                p = ph_hdri(m["ref"], a.hdri_res, a.force)
            elif m["src"] == "ambientcg":
                p = acg_material(m["ref"], a.force)
            else:
                p = ph_texture(m["ref"], a.force)
            ok.append((kind, m))
            log(f"ok   {kind:8s} {m['id']:28s} {time.time() - t0:5.1f}s")
        except Exception as e:
            failed.append((kind, m, str(e)))
            log(f"FAIL {kind:8s} {m['id']:28s} {e}")

    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(run, jobs))
    # Licenses file: every downloaded asset with its source page.
    lines = ["# WorldLab third-party assets", "", "All CC0 1.0 (public domain). Downloaded by fetch_world_assets.py; not committed.", ""]
    for kind, m in sorted(ok, key=lambda x: (x[0], x[1]["id"])):
        src = man["sources"][m["src"]]
        lines.append(f"- {kind} `{m['id']}`: {m['src']} `{m['ref']}`, {src['license']}, {src['page'].format(ref=m['ref'])}")
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / "LICENSES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"done: {len(ok)} ok, {len(failed)} failed in {time.time() - t0:.0f}s")
    for kind, m, e in failed:
        log(f"  failed {kind} {m['id']} ({m['ref']}): {e}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
