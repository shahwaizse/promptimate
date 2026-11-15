"""Pick the take that best does what the prompt asks.

The first version scored takes on physics only (jerk, skating, pops), which rewards the stillest take: jerk and
skating grow with movement. Judges found it picking a guard pose over an actual punch, a frozen cheer over a pumping
one, a seated take for "sits down and stands up". This version:
  - penalises real defects only (automatic check failures, pops, floating, floor penetration),
  - penalises unmet prompt-derived expectations (intent.py),
  - penalises a late start (standing idle before the action) for action prompts,
  - for action prompts, rewards doing more than the other takes (relative motion energy), so "barely moves" loses.
"""
from __future__ import annotations

import re

import numpy as np

import intent
import metrics
import motion

FPS = motion.FPS
_IDLE = re.compile(r"\b(stands? still|idles?|waits?|breathes?|stays? still|sits and waits|motionless)\b", re.I)
_BODY = [6, 13, 19, 24, 28, 0]   # head, hands, feet, hips


def energy(pos: np.ndarray) -> np.ndarray:
    """Per-frame motion of head/hands/feet relative to the hips plus hips travel (m/s)."""
    rel = pos[:, _BODY] - pos[:, :1] * np.array([1, 0, 1])
    v = np.linalg.norm(np.diff(rel, axis=0), axis=2) * FPS
    return v.mean(axis=1)


def onset_s(pos: np.ndarray) -> float:
    """Seconds until the motion first rises clearly above its starting level."""
    e = energy(pos)
    if len(e) < 10:
        return 0.0
    base = np.median(e[:5])
    thr = base + 0.35 * (np.percentile(e, 90) - base)
    idx = np.argmax(e > thr) if (e > thr).any() else len(e)
    return idx / FPS


def score_takes(takes: list[dict], segments: list[tuple[str, int]], prompt_text: str) -> list[dict]:
    """takes: [{"pos": (F,J,3), "checks": motion.checks(...)}]. Adds "score" (lower = better) and "score_parts"."""
    e, se = intent.expectations([(p, f / FPS) for p, f in segments])
    frames = [f for _, f in segments]
    action = not all(_IDLE.search(p) for p, _ in segments)
    energies = [float(energy(t["pos"]).mean()) for t in takes]
    emax = max(energies) or 1.0
    for t, en in zip(takes, energies):
        m = metrics.compute(pos=t["pos"], expect=e, segment_expect=se or None, segment_frames=frames)
        exp_vals = [v for k, v in m.items() if k.startswith("exp_")]
        parts = {
            "checks": 10.0 * len(t["checks"]["failures"]),
            "pops": 2.0 * m.get("pop_frames", 0),
            "float": 5.0 * m.get("float_ratio", 0),
            "penetration": 0.5 * m.get("penetration_max_cm", 0),
            "intent": 12.0 * float(np.sum(1.0 - np.array(exp_vals))) if exp_vals else 0.0,
            "late_start": 2.0 * max(0.0, onset_s(t["pos"]) - 0.8) if action else 0.0,
            "too_still": 4.0 * (1.0 - en / emax) if action else 0.0,
            "low_slide": 0.5 * low_slide_m(t["pos"]),  # tie-breaker only: settle_low removes most of it
        }
        t["score_parts"] = {k: round(v, 3) for k, v in parts.items() if v}
        t["score"] = round(sum(parts.values()), 3)
        t["intent_expect"] = {"whole": e, "segments": se}
    return takes


_END_STATE = re.compile(r"\b(falls?|collapses?|faints?|lies?|lying|sits?|sitting|kneels?|kneeling|stops?|"
                        r"stands? still|holds?|points?|freezes?|waits?|dies)\b", re.I)


def action_end_s(pos: np.ndarray) -> float:
    """Seconds at which the last clear movement ends (after that the character only stands/holds)."""
    e = energy(pos)
    thr = 0.15 * np.percentile(e, 95) + 0.05
    active = np.where(e > thr)[0]
    return (active[-1] + 1 if len(active) else 0) / FPS


def idle_tail_hint(pos: np.ndarray, segments: list[tuple[str, int]]) -> str | None:
    """A hint for the director when a single action finishes early and the rest of the clip is standing still
    (the model performs one action in ~1-2 s regardless of the requested length)."""
    last_prompt = segments[-1][0]
    if _END_STATE.search(last_prompt) or _IDLE.search(last_prompt):
        return None
    dur = len(pos) / FPS
    end = action_end_s(pos)
    if dur - end >= max(1.0, 0.4 * dur):
        return (f"the action ends at {end:.1f} s and the last {dur - end:.1f} s are standing still. If that isn't "
                f"wanted, regenerate with the last segment ~{max(1.5, end - sum(f for _, f in segments[:-1]) / FPS + 0.5):.1f} s, "
                "or add a segment for what happens next (e.g. the same action again).")
    return None


def low_slide_m(pos: np.ndarray, low_m: float = 0.4) -> float:
    """Metres the hips travel horizontally while sitting/lying on the floor (they shouldn't)."""
    low = pos[1:, 0, 1] < low_m
    step = np.linalg.norm(np.diff(pos[:, 0, [0, 2]], axis=0), axis=1)
    return float(step[low].sum())
