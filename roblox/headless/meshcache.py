"""Roblox mesh files from Studio's local asset cache (%LOCALAPPDATA%/Roblox/rbx-storage), decoded to numpy arrays.

The headless renderer needs the geometry of MeshParts and accessories, but Studio refuses to hand it over for assets
the user doesn't own (EditableMesh: "no permission"). Studio has already downloaded every mesh it renders, though,
into rbx-storage, named by content hash with no asset id. A MeshPart reports its mesh's original bounds
(MeshPart.MeshSize), so meshes are indexed by their bounding-box size and matched to parts that way.

Formats: v1 (text), v2, v3, v4/v5 (binary, LOD 0 only) and v6/v7 (chunked; COREMESH v1 raw or v2 Draco).
    python roblox/headless/meshcache.py            # build the index (<headless cache>/meshes/*.npz + index.json)
"""
from __future__ import annotations

import json
import os
import re
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

CACHE = Path(os.environ.get("LOCALAPPDATA", "")) / "Roblox" / "rbx-storage"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mcp_server"))
import local_config as LC  # noqa: E402
OUT = LC.HEADLESS_CACHE / "meshes"


def _body(b: bytes) -> bytes:
    i = b.find(b"version ")
    return b[i:] if i >= 0 else b""


def _lod0(faces: np.ndarray, lods: list[int]) -> np.ndarray:
    if len(lods) >= 2 and 0 < lods[1] <= len(faces):
        return faces[lods[0]:lods[1]]
    return faces


def _v1(text: str, scale: float):
    nums = re.findall(r"\[([^\]]*)\]", text)
    v = np.array([[float(x) for x in n.split(",")[:3]] for n in nums], np.float32)
    pos, nrm, uv = v[0::3] * scale, v[1::3], v[2::3, :2]
    uv[:, 1] = 1 - uv[:, 1]
    faces = np.arange(len(pos), dtype=np.uint32).reshape(-1, 3)
    return pos, nrm, uv, faces


def _verts(buf: bytes, off: int, n: int, size: int):
    raw = np.frombuffer(buf, np.uint8, n * size, off).reshape(n, size)
    f = raw[:, :32].copy().view(np.float32).reshape(n, 8)
    return f[:, 0:3].copy(), f[:, 3:6].copy(), f[:, 6:8].copy()


def parse(b: bytes):
    """(positions, normals, uvs, faces) of LOD 0, or None for an unknown format."""
    b = _body(b)
    nl = b.find(b"\n")
    if nl < 0:
        return None
    head = b[:nl].decode(errors="ignore").strip()
    ver = head.split(" ")[1] if " " in head else ""
    d = b[nl + 1:]
    if ver.startswith("1."):
        return _v1(d.decode(errors="ignore"), 0.5 if ver == "1.00" else 1.0)
    if ver.startswith("2."):
        hs, vs, fs, nv, nf = struct.unpack_from("<HBBII", d, 0)
        p, n, uv = _verts(d, hs, nv, vs)
        faces = np.frombuffer(d, np.uint32, nf * 3, hs + nv * vs).reshape(nf, 3)
        return p, n, uv, faces
    if ver.startswith("3."):
        hs, vs, fs, ls, nl_, nv, nf = struct.unpack_from("<HBBHHII", d, 0)
        p, n, uv = _verts(d, hs, nv, vs)
        fo = hs + nv * vs
        faces = np.frombuffer(d, np.uint32, nf * 3, fo).reshape(nf, 3)
        lods = list(np.frombuffer(d, np.uint32, nl_, fo + nf * 12)) if nl_ else []
        return p, n, uv, _lod0(faces, lods)
    if ver.startswith("4.") or ver.startswith("5."):
        hs, _lt, nv, nf, nl_, nb = struct.unpack_from("<HHIIHH", d, 0)
        p, n, uv = _verts(d, hs, nv, 40)
        o = hs + nv * 40 + (nv * 8 if nb else 0)
        faces = np.frombuffer(d, np.uint32, nf * 3, o).reshape(nf, 3)
        lods = list(np.frombuffer(d, np.uint32, nl_, o + nf * 12)) if nl_ else []
        return p, n, uv, _lod0(faces, lods)
    if ver.startswith("6.") or ver.startswith("7."):
        p = 0
        core = lods = None
        while p + 16 <= len(d):
            typ = d[p:p + 8].rstrip(b"\0")
            cv, size = struct.unpack_from("<II", d, p + 8)
            data = d[p + 16:p + 16 + size]
            if typ == b"COREMESH":
                core = (cv, data)
            elif typ == b"LODS":
                _lt, _hq, no = struct.unpack_from("<HBI", data, 0)
                lods = list(np.frombuffer(data, np.uint32, no, 7))
            p += 16 + size
        if not core:
            return None
        cv, data = core
        if cv == 1:
            nv = struct.unpack_from("<I", data, 0)[0]
            pp, n, uv = _verts(data, 4, nv, 40)
            nf = struct.unpack_from("<I", data, 4 + nv * 40)[0]
            faces = np.frombuffer(data, np.uint32, nf * 3, 8 + nv * 40).reshape(nf, 3)
            return pp, n, uv, _lod0(faces, lods or [])
        import DracoPy
        i = data.find(b"DRACO")
        m = DracoPy.decode(data[i:])
        pos = np.asarray(m.points, np.float32).reshape(-1, 3)
        faces = np.asarray(m.faces, np.uint32).reshape(-1, 3)
        nrm = np.asarray(m.normals, np.float32).reshape(-1, 3) if getattr(m, "normals", None) is not None and len(m.normals) else None
        uv = np.asarray(m.tex_coord, np.float32).reshape(-1, 2) if getattr(m, "tex_coord", None) is not None and len(m.tex_coord) else np.zeros((len(pos), 2), np.float32)
        if nrm is None or len(nrm) != len(pos):
            nrm = vertex_normals(pos, faces)
        return pos, nrm, uv, _lod0(faces, lods or [])
    return None


def vertex_normals(pos: np.ndarray, faces: np.ndarray) -> np.ndarray:
    n = np.zeros_like(pos)
    tri = pos[faces]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for k in range(3):
        np.add.at(n, faces[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    return (n / np.maximum(ln, 1e-9)).astype(np.float32)


CSG_KEY = bytes([86, 46, 110, 88, 49, 32, 48, 4, 52, 105, 12, 119, 12, 1, 94, 0, 26, 96, 55, 105, 29, 82, 43, 7, 79,
                 36, 89, 101, 83, 4, 122])


def parse_csg(md: bytes):
    """Union render mesh (PartOperationAsset.MeshData, "CSGMDL" v2/v4, XOR-obfuscated): (pos, nrm, uv, faces, rgba)."""
    if md[:6] != b"CSGMDL":
        k = np.frombuffer((CSG_KEY * (len(md) // len(CSG_KEY) + 1))[:len(md)], np.uint8)
        md = (np.frombuffer(md, np.uint8) ^ k).tobytes()
    if md[:6] != b"CSGMDL":
        return None
    ver = struct.unpack_from("<I", md, 6)[0]
    if ver not in (2, 4):
        return None
    nv, stride = struct.unpack_from("<II", md, 42)
    if stride != 84 or 50 + nv * 84 + 4 > len(md):
        return None
    raw = np.frombuffer(md, np.uint8, nv * 84, 50).reshape(nv, 84)
    f = raw[:, :24].copy().view(np.float32).reshape(nv, 6)
    rgba = raw[:, 24:28].copy()
    uv = raw[:, 32:40].copy().view(np.float32).reshape(nv, 2)
    o = 50 + nv * 84
    ni = struct.unpack_from("<I", md, o)[0]
    idx = np.frombuffer(md, np.uint32, ni, o + 4)
    if len(idx) == 0 or idx.max() >= nv:
        return None
    return f[:, :3].copy(), f[:, 3:6].copy(), uv, idx.reshape(-1, 3).copy(), rgba


def size_key(size) -> str:
    return ",".join(f"{v:.2f}" for v in size)


def build_index() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    index, bad = {}, 0

    def put(key, pos, nrm, uv, faces, rgba=None):
        lo, hi = pos.min(0), pos.max(0)
        extra = {"rgba": rgba} if rgba is not None else {}
        np.savez(OUT / f"{key}.npz", pos=pos, nrm=nrm.astype(np.float32), uv=uv.astype(np.float32),
                 faces=faces.astype(np.uint32), lo=lo, hi=hi, **extra)
        index[key] = {"size": [float(v) for v in hi - lo], "centre": [float(v) for v in (hi + lo) / 2],
                      "verts": int(len(pos)), "tris": int(len(faces)), "csg": rgba is not None}

    import rbxm
    # unions whose mesh is inlined in the place file (SharedStrings)
    place = Path(__file__).resolve().parents[1] / "places" / "PromptimateTest.rbxlx"
    if place.exists():
        import base64
        x = place.read_text(encoding="utf-8", errors="ignore")
        for h, b64 in re.findall(r'<SharedString md5="([^"]+)">([^<]{40,})</SharedString>', x):
            try:
                m = parse_csg(base64.b64decode(b64))
            except Exception:
                m = None
            if m and len(m[3]):
                put("place_" + re.sub(r"[^A-Za-z0-9]", "_", h), *m)
    for r, _, fs in os.walk(CACHE):
        for f in fs:
            path = Path(r) / f
            raw = path.read_bytes()
            if b"PartOperationAsset" in raw[:65536] or b"<roblox!" in raw[:64]:
                try:
                    for inst in rbxm.read(raw):
                        if inst.get("MeshData"):
                            m = parse_csg(inst["MeshData"])
                            if m and len(m[3]):
                                put("csg_" + f, *m)
                                break
                except Exception:
                    pass
                continue
            if b"version " not in raw[:4096]:
                continue
            try:
                m = parse(raw)
            except Exception:
                m = None
            if not m or len(m[0]) == 0 or len(m[3]) == 0:
                bad += 1
                continue
            put(f, *m)
    (OUT / "index.json").write_text(json.dumps(index))
    return {"meshes": len(index), "unreadable": bad}


_ARR = {}


def match(mesh_size, index: dict, tol: float = 0.012):
    """Cache entries whose bounds equal MeshPart.MeshSize (relative tolerance), best first."""
    a = _ARR.get(id(index))
    if a is None:
        keys = list(index)
        a = _ARR[id(index)] = (keys, np.array([index[k]["size"] for k in keys], float))
    keys, sizes = a
    ms = np.asarray(mesh_size, float)
    err = np.max(np.abs(sizes - ms) / np.maximum(ms, 1e-3), axis=1)
    hit = np.nonzero(err < tol)[0]
    return [keys[i] for i in hit[np.argsort(err[hit])]]


if __name__ == "__main__":
    print(build_index())
    sys.exit(0)
