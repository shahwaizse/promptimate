"""Build the sourced prop library in Studio (ServerStorage.PromptimateProps) from free Creator Store models.
Heights are in studs against a ~5-stud classic character (head top ~5.2, waist ~2.6, counter height ~3).
    .venv\\Scripts\\python.exe demo\\episodes\\props_lib.py [key ...]     (no keys: everything missing)
Picks come from a public toolbox search (no login); scripts, sounds and click handlers are stripped on import."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# key: (asset id, height in studs)
PROPS = {
    "throne": (4830795885, 7.0),
    "crown": (8269921264, 0.9), "office_chair": (200285525, 4.2), "park_bench": (185280084, 3.0),
    "sofa": (7053075271, 3.2), "bed": (8148059102, 3.0), "dining_table": (1550118355, 3.0),
    "school_desk": (7079944649, 3.2), "chalkboard": (13983642118, 5.5), "lockers": (1073041751, 6.5),
    "polaroid_camera": (5420772380, 0.7), "photo_frame": (4750098709, 1.2), "cash_register": (1351831051, 1.2),
    "piggy_bank": (79484619507581, 1.2), "cash_stack": (439712421, 0.6), "gold_bars": (5520842371, 1.0),
    "coin_pile": (13011134700, 1.0), "trophy": (1331624495, 1.6), "gift_box": (14498058212, 1.4),
    "phone": (11428924945, 0.55), "laptop": (13883428132, 0.9), "tv": (4499132766, 5.0), "fridge": (16953722369, 6.5),
    "kitchen_counter": (467378925, 3.2), "door": (9343670755, 7.0), "mailbox": (10297434383, 4.0),
    "streetlight": (404475960, 14.0), "tree": (580221169, 16.0), "bush": (8344171779, 2.6), "car": (14215126016, 5.0),
    "bicycle": (91358100215341, 3.4), "cat": (1718821907, 1.4), "dog": (17105403700, 2.0), "bird": (13656715867, 0.8),
    "cake": (11308679828, 1.0), "pizza": (9776020935, 0.4), "coffee_cup": (6168992247, 0.6), "books": (9749867161, 1.0),
    "backpack": (18953625782, 1.8), "umbrella": (298057724, 3.0), "clock": (126528572, 2.0, (90, 0, 0)), "sign_board": (7855022170, 6.0),
    "newspaper": (None, 0.08),
}


def candidates_for(key: str) -> list[int]:
    import os
    p = Path(os.environ.get("PROMPTIMATE_PROPS_CANDIDATES", Path(__file__).resolve().parents[2] / ".cache" / "props" / "candidates.json"))
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    v = d.get(key) or d.get(key.replace("_", " ")) or []
    if isinstance(v, dict):
        v = v.get("picks", [])
    return [int(x["id"]) for x in v if isinstance(x, dict) and x.get("id")]


def main(keys: list[str]):
    import sets as SETS
    for k in SETS.BUILT:
        if not keys or k in keys:
            print(k, SETS.build(k))
    have = SETS.library()
    out = {}
    for k, spec in PROPS.items():
        if keys and k not in keys or (not keys and k in have):
            continue
        ids = ([spec[0]] if spec and spec[0] else []) + [i for i in candidates_for(k) if not spec or i != spec[0]]
        h = spec[1] if spec else 1.0
        rot = spec[2] if spec and len(spec) > 2 else None
        for aid in ids[:3]:
            try:
                r = SETS.prop(k, str(aid), h, rot=rot)
                if r.get("parts", 0) > 0:
                    out[k] = r
                    break
                out[k] = {"error": "no parts", "id": aid}
            except Exception as e:      # deleted / private / not a model: try the next pick
                out[k] = {"error": str(e)[:160], "id": aid}
        print(k, json.dumps(out[k])[:200] if k in out else "-", flush=True)
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
