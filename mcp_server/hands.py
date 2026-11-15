"""Finger poses from the prompt. The model generates no finger motion, so the hands would always be relaxed; this
infers what the text implies ("points" -> index finger out, "punches" -> fist, "waves" -> open hand, "claps" -> flat
hands, "holds"/"grabs" -> grip) and when, as per-hand frame ranges for the .kimodo "handPoses" field. The Unity
importer turns them into finger muscle curves (blended in and out) on rigs that have finger bones.

    hand_poses([("a person points forward with their right hand", 150)])
    -> [{"hand": "right", "pose": "point", "start": 0, "end": 149, "blend": 6}]

Rules:
- Each segment is split into clauses at "then" / "after that" / "followed by" / ";" and the clauses share the segment's
  frames evenly, so "walks forward then waves" waves in the second half.
- A side given in the text ("right hand", "with their left", "both hands") is used. Otherwise one-handed gestures
  (point, wave) go to the hand that actually does them when joint positions are given (the hand further out for a
  point, higher for a wave), else to the right hand; fists and claps go to both hands; carrying/lifting uses both
  hands, holding/grabbing the right one.
- With joint positions, a point or wave is narrowed to the frames where that arm actually points / is raised (plus a
  short margin), so the finger pose follows the gesture instead of the whole clause.
- Default (nothing matched) stays relaxed: no entry.
"""
from __future__ import annotations

import re

import numpy as np

FPS = 30
BLEND = 6        # frames (0.2 s) of blend in and out
MARGIN = 8       # frames kept around the detected gesture when narrowing with joint positions

# pose -> regex on a clause; first match position is used to find a side word nearby.
POSES = [
    ("point", r"\bpoint(s|ed|ing)?\b(?!\s+of\b)"),
    ("fist", r"\b(punch(es|ed|ing)?|fists?|box(es|ed|ing)|shadow\s?box\w*|jabs?|jabbing|uppercuts?|clench\w*|"
             r"fight(s|ing)?|throws? (a )?(punch|jab|hook)\w*|raises? (their|his|her) fists?)\b"),
    ("open", r"\b(wav(e|es|ed|ing)|high[- ]?fives?|jazz hands)\b"),
    ("flat", r"\b(clap(s|ped|ping)?|applau\w+|pray(s|ed|ing)?|salut(e|es|ed|ing)|karate[- ]chops?|chops?)\b"),
    ("grip_both", r"\b(carr(y|ies|ied|ying)|lift(s|ed|ing)? (up )?(a|an|the|something|it|heavy)|pick(s|ed|ing)? up|"
                  r"push(es|ed|ing)? (a|an|the|something)|pull(s|ed|ing)? (a|an|the|on|something)|row(s|ed|ing)?\b)"),
    ("grip", r"\b(hold(s|ing)?|held|grab(s|bed|bing)?|grip(s|ped|ping)?|clutch(es|ed|ing)?|swing(s|ing)? (a|an|the)|"
             r"drink(s|ing)?|brush(es|ing)? (their|his|her) teeth)\b"),
]
ONE_HANDED = {"point", "open", "grip"}
SPLIT = re.compile(r"\bthen\b|\bafter that\b|\bafterwards\b|\bfollowed by\b|;|\.\s", re.I)
SIDE = re.compile(r"\b(?:(left|right)\s+(?:hand|arm|fist|index|finger|palm)s?|with\s+(?:the|their|his|her|its|one)?\s*(left|right)\b|"
                  r"(both)\s+(?:hands|arms|fists)|(hands|arms|fists)\b)", re.I)


def _side_near(clause: str, pos: int) -> str | None:
    """Side word closest to the gesture word (after it preferred: "points with their right hand")."""
    best, best_d = None, 10 ** 9
    for m in SIDE.finditer(clause):
        side = (m.group(1) or m.group(2) or ("both" if m.group(3) or m.group(4) else None))
        if side is None:
            continue
        d = m.start() - pos if m.start() >= pos else (pos - m.start()) * 2  # before the verb counts double
        if d < best_d and d < 80:
            best, best_d = side.lower(), d
    return best


def _clauses(prompt: str, frames: int) -> list[tuple[str, int, int]]:
    parts = [p.strip() for p in SPLIT.split(prompt) if p and p.strip(" ,.")]
    parts = parts or [prompt]
    n = len(parts)
    return [(p, round(i * frames / n), round((i + 1) * frames / n) - 1) for i, p in enumerate(parts)]


# --- optional joint-position evidence (Kimodo space, SOMA joint order of motion.NAMES) -------------------------

def _arm_signals(pos: np.ndarray, side: str) -> tuple[np.ndarray, np.ndarray]:
    """Per frame: arm extension (shoulder->hand distance / arm length) and hand height above the shoulder (m)."""
    from motion import NAMES
    S = "Left" if side == "left" else "Right"
    sh, el, ha = (pos[:, NAMES.index(S + n)] for n in ("Arm", "ForeArm", "Hand"))
    length = np.linalg.norm(el - sh, axis=1) + np.linalg.norm(ha - el, axis=1)
    ext = np.linalg.norm(ha - sh, axis=1) / np.maximum(length, 1e-6)
    return ext, ha[:, 1] - sh[:, 1]


def _activity(pos: np.ndarray, side: str, pose: str) -> np.ndarray:
    ext, up = _arm_signals(pos, side)
    if pose == "point":
        # Arm nearly straight and raised away from the body (not hanging down).
        return (ext > 0.88) & (up > -0.25)
    if pose == "open":
        return up > -0.05  # hand around/above shoulder height
    return np.ones(len(ext), bool)


def _pick_side(pos: np.ndarray | None, pose: str, a: int, b: int) -> str:
    if pos is None or pose not in ("point", "open"):
        return "right"
    seg = slice(a, b + 1)
    score = {s: float(_activity(pos[seg], s, pose).mean()) for s in ("left", "right")}
    if pose == "open":  # tie-break on how high the hand gets
        for s in score:
            score[s] += 0.01 * float(_arm_signals(pos[seg], s)[1].max())
    return max(score, key=score.get) if score["left"] != score["right"] else "right"


def _narrow(pos: np.ndarray | None, side: str, pose: str, a: int, b: int) -> tuple[int, int]:
    if pos is None or pose not in ("point", "open"):
        return a, b
    act = np.flatnonzero(_activity(pos[a:b + 1], side, pose))
    if len(act) < 5:  # gesture not visible in the motion: keep the clause's range
        return a, b
    return max(a, a + int(act[0]) - MARGIN), min(b, a + int(act[-1]) + MARGIN)


# --- public ----------------------------------------------------------------------------------------------------

def hand_poses(segments: list[tuple[str, int]], pos: np.ndarray | None = None, frames: int | None = None,
               blend: int = BLEND) -> list[dict]:
    """segments: (prompt, frames) per segment, in order. pos: optional (T, 30, 3) global joint positions (Kimodo
    space, e.g. motion.fk(root, rot)) to pick the gesturing hand and narrow the range. frames: actual clip length if it
    differs from the sum of segment frames (ranges are rescaled). Returns per-hand ranges (frames, inclusive) for the
    .kimodo "handPoses" field; empty when the text implies nothing but relaxed hands."""
    total = sum(int(n) for _, n in segments)
    out_frames = int(frames) if frames else total
    if pos is not None and len(pos) != out_frames:
        pos = None  # positions don't line up with the frame numbering: text only
    scale = out_frames / total if total else 1.0
    ranges: list[dict] = []
    off = 0
    for prompt, n in segments:
        n = int(n)
        for clause, ca, cb in _clauses(prompt or "", n):
            low = clause.lower()
            found = []
            for pose, rx in POSES:
                m = re.search(rx, low)
                # one grip per clause ("carries" beats "holds": both hands)
                if m and not (pose.startswith("grip") and any(p.startswith("grip") for p, _ in found)):
                    found.append((pose, m.start()))
            for pose, at in found:
                side = _side_near(low, at)
                base = "grip" if pose == "grip_both" else pose
                a = round((off + ca) * scale)
                b = min(out_frames - 1, round((off + cb) * scale))
                if side is None:
                    side = "both" if base in ("fist", "flat") or pose == "grip_both" else _pick_side(pos, base, a, b)
                for s in (("left", "right") if side == "both" else (side,)):
                    sa, sb = _narrow(pos, s, base, a, b)
                    ranges.append({"hand": s, "pose": base, "start": int(sa), "end": int(sb), "blend": int(blend)})
        off += n
    return _merge(ranges)


def _merge(ranges: list[dict]) -> list[dict]:
    """Joins touching ranges of the same hand and pose (consecutive segments that say the same thing)."""
    out: list[dict] = []
    for r in sorted(ranges, key=lambda r: (r["hand"], r["start"])):
        prev = next((o for o in reversed(out) if o["hand"] == r["hand"]), None)
        if prev and prev["pose"] == r["pose"] and r["start"] <= prev["end"] + 1:
            prev["end"] = max(prev["end"], r["end"])
        else:
            out.append(dict(r))
    return sorted(out, key=lambda r: (r["start"], r["hand"]))


if __name__ == "__main__":  # quick self-check:  .venv\Scripts\python mcp_server\hands.py
    cases = [
        ([("a person points forward with their right hand", 150)], [("right", "point", 0, 149)]),
        ([("a person points to the left with their left arm", 90)], [("left", "point", 0, 89)]),
        ([("a person punches forward with both fists", 120)], [("left", "fist", 0, 119), ("right", "fist", 0, 119)]),
        ([("a person shadowboxes", 60)], [("left", "fist", 0, 59), ("right", "fist", 0, 59)]),
        ([("a person waves with their left hand", 100)], [("left", "open", 0, 99)]),
        ([("a person claps their hands", 120)], [("left", "flat", 0, 119), ("right", "flat", 0, 119)]),
        ([("a person walks forward then waves with their right hand", 200)], [("right", "open", 100, 199)]),
        ([("a person walks forward", 150), ("a person turns right", 90)], []),
        ([("a person carries a heavy box", 120)], [("left", "grip", 0, 119), ("right", "grip", 0, 119)]),
        ([("a person grabs something with the left hand", 60)], [("left", "grip", 0, 59)]),
        ([("a person jogs", 60), ("a person points forward", 60)], [("right", "point", 60, 119)]),
        ([("a person boxes", 60), ("a person punches with their right fist", 60)],
         [("left", "fist", 0, 59), ("right", "fist", 0, 119)]),
    ]
    bad = 0
    for segs, want in cases:
        got = [(r["hand"], r["pose"], r["start"], r["end"]) for r in hand_poses(segs)]
        ok = sorted(got) == sorted(want)
        bad += not ok
        print("OK  " if ok else "BAD ", [p for p, _ in segs], "->", got, "" if ok else f"(want {want})")
    print("rescaled:", hand_poses([("a person points", 100)], frames=50))
    raise SystemExit(1 if bad else 0)
