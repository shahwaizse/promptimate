"""Minimal reader for Roblox binary model files (.rbxm / cached assets): instances with their string and
binary-string properties, enough to pull MeshData/ChildData/AssetId out of union (PartOperationAsset) assets."""
from __future__ import annotations

import struct

MAGIC = b"<roblox!\x89\xff\r\n\x1a\n"


def _chunks(b: bytes):
    p = b.find(MAGIC)
    if p < 0:
        raise ValueError("not a binary rbxm")
    p += len(MAGIC) + 2 + 4 + 4 + 8
    while p + 16 <= len(b):
        name = b[p:p + 4].rstrip(b"\0")
        clen, ulen = struct.unpack_from("<II", b, p + 4)
        p += 16
        if clen == 0:
            data = b[p:p + ulen]; p += ulen
        else:
            raw = b[p:p + clen]; p += clen
            if raw[:4] == b"\x28\xb5\x2f\xfd":
                import zstandard
                data = zstandard.ZstdDecompressor().decompress(raw, max_output_size=ulen)
            else:
                import lz4.block
                data = lz4.block.decompress(raw, uncompressed_size=ulen)
        yield name, data
        if name == b"END":
            break


def _ints(data: bytes, p: int, n: int) -> list[int]:
    """Roblox interleaved, zigzag-encoded big-endian int32 array."""
    if n == 0:
        return []
    raw = data[p:p + 4 * n]
    vals = []
    for i in range(n):
        u = (raw[i] << 24) | (raw[n + i] << 16) | (raw[2 * n + i] << 8) | raw[3 * n + i]
        vals.append((u >> 1) ^ -(u & 1))
    return vals


def read(b: bytes) -> list[dict]:
    """Instances as dicts {ClassName, <string/binary props>}."""
    classes, insts = {}, {}
    for name, d in _chunks(b):
        if name == b"INST":
            tid, ln = struct.unpack_from("<II", d, 0)
            cls = d[8:8 + ln].decode(errors="ignore")
            p = 8 + ln
            _svc, cnt = struct.unpack_from("<BI", d, p)
            p += 5
            ids = _ints(d, p, cnt)
            acc = 0
            refs = []
            for v in ids:
                acc += v
                refs.append(acc)
            classes[tid] = (cls, refs)
            for r in refs:
                insts[r] = {"ClassName": cls}
        elif name == b"PROP":
            tid, ln = struct.unpack_from("<II", d, 0)
            pname = d[8:8 + ln].decode(errors="ignore")
            p = 8 + ln
            vtype = d[p]
            p += 1
            if vtype != 0x01 or tid not in classes:      # strings / binary strings only
                continue
            for r in classes[tid][1]:
                n = struct.unpack_from("<I", d, p)[0]
                insts[r][pname] = d[p + 4:p + 4 + n]
                p += 4 + n
    return list(insts.values())
