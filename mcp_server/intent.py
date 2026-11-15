"""What does the prompt ask for, in machine-checkable terms? Used to pick the take that actually does what was asked
(not just the cleanest one) and to reword phrasings the model is known to follow poorly.

expectations(segments) -> (whole_clip_expect, per_segment_expect) in metrics.expectation_checks format.
rewrite(prompt) -> prompt with known-better phrasing (measured with bench/prompt_variants.py).
Rules are deliberately conservative: a rule only fires on unambiguous wording, and checks are lenient (they
should rule out takes that clearly ignore the prompt, not nitpick good ones).
"""
from __future__ import annotations

import re

STAND_HIPS = 0.85   # hips height when standing upright (SOMA ~0.95-1.0)


def _has(p: str, pattern: str) -> bool:
    return re.search(pattern, p, re.I) is not None


def segment_expect(prompt: str, seconds: float, is_first: bool = True) -> dict:
    p = prompt.lower()
    e: dict = {}
    side = "right" if _has(p, r"\bright (hand|arm|fist)\b") else "left" if _has(p, r"\bleft (hand|arm|fist)\b") else None
    # posture changes
    if _has(p, r"\b(sits? down|sitting down|sits on the (floor|ground)|sits (and|still|quietly))\b") and \
            not _has(p, r"\bstands? up\b"):
        e["hips_end_max"] = 0.6
    if _has(p, r"\b(stands? up|gets? up|rises?)\b") and not _has(p, r"\bsits? down\b.*$"):
        e["hips_end_min"] = STAND_HIPS
    if _has(p, r"\b(squats?|crouch(es)? down|bends? down|kneels?)\b") and _has(p, r"\b(stands? (back )?up|gets? up|and up)\b"):
        e["hips_drop_min"] = 0.25
        e["hips_end_min"] = STAND_HIPS
    if _has(p, r"\b(falls?( down)?( to the (ground|floor))?|collapses?|faints?|lies? down)\b") and \
            not _has(p, r"\b(knees|stands? up|gets? up)\b"):
        e["hips_end_max"] = 0.45
    if _has(p, r"\bfalls? to (his|her|their) knees\b|\bkneels?\b") and not _has(p, r"\bstands? up\b"):
        e["hips_end_max"] = 0.7
    # locomotion and direction
    if _has(p, r"\b(in place|on the spot|without moving)\b"):
        e["travel_max"] = 1.0
    if _has(p, r"\bturns? around\b"):
        e["turn_min_deg"] = 120
    elif _has(p, r"\bturns?\b[^,.]*\b(left|right)\b") and not _has(p, r"\b(walks?|runs?|jogs?)\b"):
        e["turn_min_deg"] = 45
    if _has(p, r"\b(walks?|jogs?|runs?|sprints?|marches?|sneaks?|staggers?|crawls?) (forward|ahead)\b") and seconds >= 2:
        e["forward_min"] = (0.15 if _has(p, r"\b(slowly|sneaks?|crawls?|tiptoes?)\b") else 0.4) * seconds
    if _has(p, r"\b(stops?|stands? still|comes? to a stop)\b") and not _has(p, r"\b(stops?|still)\b.*\b(walks?|runs?|jogs?)\b"):
        e["ends_stationary"] = True
    if _has(p, r"\b(walks?|steps?|moves?) backwards?\b"):
        e["backward_min"] = 0.25 * seconds
    if _has(p, r"\b(side ?steps?|strafes?|shuffles?) (to the )?left\b"):
        e["left_min"] = 0.5
    if _has(p, r"\b(side ?steps?|strafes?|shuffles?) (to the )?right\b"):
        e["right_min"] = 0.5
    if _has(p, r"\b(bends? down|picks? [a-z ]*up from the (floor|ground))\b"):
        e["hips_drop_min"] = 0.2
    if _has(p, r"\bkicks?\b"):
        e["foot_raise_min"] = 0.3
    if _has(p, r"\b(jumps?|hops?|leaps?)\b"):
        e["hips_rise_min"] = 0.08
    # arms
    if _has(p, r"\b(waves?|raises?)\b") and side:
        e[f"{side}_hand_up_frac"] = 0.15
    if _has(p, r"\b(both (arms|hands) (raised|up)|raises both (arms|hands)|arms raised above)\b"):
        e["both_hands_up_frac"] = 0.2
    if _has(p, r"\b(punch(es)?|jab|points?)\b") and side:
        e[f"{side}_arm_extended_frac"] = 0.04
    if _has(p, r"\b(phone|to (his|her|their) ear|scratch(es)? (his|her|their) head|head in (his|her|their) hands|covers? (his|her|their) face)\b"):
        e["hand_near_head_frac"] = 0.2
    if _has(p, r"\bclaps?\b"):
        e["clap_count_min"] = 1
    return e


def expectations(segments: list[tuple[str, float]]) -> tuple[dict, list[dict]]:
    """segments: [(prompt, seconds)]. Single segment -> whole-clip expectations; several -> per segment."""
    starts_down = _has(segments[0][0], r"\b(sits?|sitting|seated|lies|lying|kneels?|kneeling|crawls?|crawling|"
                                       r"on (his|her|their) (back|knees|stomach)|gets? up|stands? up)\b") and \
        not _has(segments[0][0], r"\bsits? down\b")
    if len(segments) == 1:
        e = segment_expect(segments[0][0], segments[0][1])
        if not starts_down:
            e["hips_start_min"] = 0.8
        return e, []
    se = [segment_expect(p, s, i == 0) for i, (p, s) in enumerate(segments)]
    if not starts_down:
        se[0]["hips_start_min"] = 0.8
    return {}, se


# Phrasings the model follows measurably better (bench/prompt_variants.py, 3 seeds each). Applied only when the
# prompt matches the left side closely; the user's words are otherwise kept.
_REWRITES = [
    (re.compile(r"\bthrows? a punch with (his|her|their) (right|left) (fist|hand|arm)\b", re.I),
     lambda m: f"punches forward with their {m.group(2).lower()} hand"),
    (re.compile(r"\bthrows? a (right|left) (jab|punch)\b", re.I), lambda m: f"punches forward with their {m.group(1).lower()} hand"),
    (re.compile(r"\bmakes a phone call\b", re.I), lambda m: "talks on the phone"),
    (re.compile(r"\bdashes forward\b", re.I), lambda m: "sprints forward at full speed"),
]


def rewrite(prompt: str) -> str:
    out = prompt
    for pat, rep in _REWRITES:
        out = pat.sub(rep, out)
    return out
