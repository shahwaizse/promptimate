r"""Fetch FidelityStudio's third-party assets (Poly Haven CC0 models/HDRIs/textures, Microsoft Rocketbox MIT avatars)
into Assets/ThirdParty/, which is gitignored. Nothing third-party is committed; this script plus fidelity_assets.json
recreate the set on a fresh clone. No accounts or logins are needed.

    .venv\Scripts\python unity\FidelityStudio\fetch_assets.py [--only id1,id2] [--force]

Textures get an HDRP mask map (R metal, G AO, B detail, A smoothness) built from Poly Haven's ARM map.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "Assets" / "ThirdParty"
UA = {"User-Agent": "promptimate-fidelity-fetch/1.0"}
RB_RAW = "https://raw.githubusercontent.com/microsoft/Microsoft-Rocketbox/master/Assets/Avatars"
RB_API = "https://api.github.com/repos/microsoft/Microsoft-Rocketbox/contents/Assets/Avatars"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def save(url: str, dest: Path, force: bool) -> str:
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return f"skip {dest.name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = get(url)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return f"got  {dest.relative_to(OUT)} ({len(data) // 1024} KB)"


def files(asset_id: str) -> dict:
    return json.loads(get(f"https://api.polyhaven.com/files/{asset_id}"))


def jobs_model(m: dict) -> list[tuple[str, Path]]:
    g = files(m["id"])["gltf"][m["res"]]["gltf"]
    root = OUT / "PolyHaven" / "Models" / m["id"]
    out = [(g["url"], root / Path(g["url"]).name)]
    out += [(v["url"], root / k) for k, v in g["include"].items()]
    return out


def jobs_hdri(h: dict) -> list[tuple[str, Path]]:
    f = files(h["id"])["hdri"][h["res"]][h.get("fmt", "hdr")]
    return [(f["url"], OUT / "PolyHaven" / "HDRI" / Path(f["url"]).name)]


def jobs_texture(t: dict) -> list[tuple[str, Path]]:
    f = files(t["id"])
    root = OUT / "PolyHaven" / "Textures" / t["id"]
    out = []
    for key in ("Diffuse", "nor_gl", "arm"):
        if key in f and t["res"] in f[key]:
            fmt = "png" if key == "nor_gl" and "png" in f[key][t["res"]] else "jpg"
            u = f[key][t["res"]][fmt]["url"]
            out.append((u, root / Path(u).name))
    return out


def jobs_rocketbox(r: dict) -> list[tuple[str, Path]]:
    base = f"{r['group']}/{r['id']}"
    root = OUT / "Rocketbox" / r["id"]
    out = []
    for sub in ("Export", "Textures"):
        for e in json.loads(get(f"{RB_API}/{base}/{sub}")):
            name = e["name"]
            # Only meshes and images: the repo's .shader/.mat files are for its own sample project.
            if not name.lower().endswith((".fbx", ".tga", ".png", ".jpg")):
                continue
            if sub == "Export" and not name.endswith("_facial.fbx"):
                continue  # the facial variant has the same body plus face blendshapes (blinks)
            out.append((f"{RB_RAW}/{base}/{sub}/{name}", root / sub / name))
    return out


def mask_maps(force: bool) -> None:
    """HDRP Lit mask map from Poly Haven ARM (R=AO, G=roughness, B=metal)."""
    from PIL import Image, ImageChops

    arms = list((OUT / "PolyHaven" / "Textures").glob("*/*_arm_*.jpg")) + list((OUT / "PolyHaven" / "Models").glob("*/textures/*_arm_*.jpg"))
    for arm in arms:
        dest = arm.with_name(arm.name.replace("_arm_", "_mask_")).with_suffix(".png")
        if dest.exists() and not force:
            continue
        a = Image.open(arm).convert("RGB")
        ao, rough, metal = a.split()
        detail = Image.new("L", a.size, 0)
        smooth = ImageChops.invert(rough)
        Image.merge("RGBA", (metal, ao, detail, smooth)).save(dest)
        print("mask", dest.relative_to(OUT))


def read_hdr(path: Path):
    import numpy as np
    f = path.read_bytes()
    i = f.index(b"\n\n") + 2
    j = f.index(b"\n", i)
    dims = f[i:j].decode().split()
    H, W = int(dims[1]), int(dims[3])
    data, k = f[j + 1:], 0
    img = np.zeros((H, W, 4), np.uint8)
    for y in range(H):  # new-style RLE scanlines
        k += 4
        for c in range(4):
            x, row = 0, bytearray(W)
            while x < W:
                n = data[k]; k += 1
                if n > 128:
                    n -= 128; row[x:x + n] = bytes([data[k]]) * n; k += 1
                else:
                    row[x:x + n] = data[k:k + n]; k += n
                x += n
            img[y, :, c] = np.frombuffer(bytes(row), np.uint8)
    e = img[..., 3].astype(np.int32)
    rgb = (img[..., :3].astype(np.float32) + 0.5) * np.ldexp(1.0, e - 136)[..., None]
    rgb[e == 0] = 0
    return rgb


def write_hdr(path: Path, rgb) -> None:
    import numpy as np
    H, W, _ = rgb.shape
    m = rgb.max(-1)
    ex = np.where(m > 1e-32, np.floor(np.log2(np.maximum(m, 1e-32))) + 1, -128).astype(np.int32)
    scale = np.where(m > 1e-32, 256.0 / np.ldexp(1.0, ex), 0)
    out = np.zeros((H, W, 4), np.uint8)
    out[..., :3] = np.clip(rgb * scale[..., None], 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(ex + 128, 0, 255).astype(np.uint8)
    out[m <= 1e-32] = 0
    head = f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {H} +X {W}\n".encode()
    path.write_bytes(head + out.tobytes())  # flat (uncompressed) scanlines


def derive_nosun(force: bool) -> None:
    """Sky-only copy of each HDRI (the sun's hot spot clamped, downsampled to 2k): the film lights the room with a
    directional sun whose angle it chooses, so the HDRI must not add a second sun from another direction."""
    import numpy as np
    for src in (OUT / "PolyHaven" / "HDRI").glob("*_4k.hdr"):
        dest = src.with_name(src.name.replace("_4k.hdr", "_nosun_2k.hdr"))
        if dest.exists() and not force:
            continue
        rgb = read_hdr(src)
        rgb = rgb.reshape(rgb.shape[0] // 2, 2, rgb.shape[1] // 2, 2, 3).mean((1, 3))
        lum = rgb.mean(-1, keepdims=True)
        cap = 24.0
        rgb = np.where(lum > cap, rgb * (cap / np.maximum(lum, 1e-6)), rgb)
        write_hdr(dest, rgb)
        print("nosun", dest.relative_to(OUT), "max", float(rgb.max()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    man = json.loads((HERE / "fidelity_assets.json").read_text(encoding="utf-8"))
    only = set(filter(None, a.only.split(",")))
    jobs: list[tuple[str, Path]] = []
    plan = [(jobs_model, man.get("polyhaven_models", [])), (jobs_hdri, man.get("polyhaven_hdris", [])),
            (jobs_texture, man.get("polyhaven_textures", [])), (jobs_rocketbox, man.get("rocketbox", []))]
    with cf.ThreadPoolExecutor(8) as ex:
        listed = [ex.submit(fn, item) for fn, items in plan for item in items if not only or item["id"] in only]
        for f in listed:
            jobs += f.result()
        errors = 0
        for f in cf.as_completed([ex.submit(save, u, d, a.force) for u, d in jobs]):
            try:
                print(f.result(), flush=True)
            except Exception as e:  # keep going; report at the end
                errors += 1
                print("FAIL", e, file=sys.stderr)
    mask_maps(a.force)
    derive_nosun(a.force)
    print(f"done: {len(jobs)} files, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
