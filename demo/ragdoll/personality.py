r"""Text -> physical personality for the active ragdoll (the `personality` argument of simulate_reaction).

    .venv\Scripts\python demo\ragdoll\personality.py "a frail old man" "a trained fighter who braces" "a drunk who flops"
    .venv\Scripts\python demo\ragdoll\personality.py --json out.json "..."   # file for run_lab.py --personalities

A small, inspectable mapping: presets anchor the extremes, adjectives nudge individual fields, and everything is
clamped to the ranges the controller is stable in. Claude can also fill the JSON fields directly (same schema as
unity/SystemLab/Assets/SystemLab/Runtime/Personality.cs); this mapping is the fallback and the documentation of
what each word means physically.
"""
from __future__ import annotations

import json
import re
import sys

DEFAULT = dict(strength=1.0, legs=1.0, spine=1.0, arms=1.0, neck=1.0, damping=1.0, balance=1.0, knockdown=0.8,
               balanceRadius=0.35, hitBalanceLoss=0.9, hitLimp=0.7, reactionTime=0.12, recovery=2.5, brace=0.8,
               anticipation=0.0, fallTone=0.25, stepFollow=1.2, sway=0.0, getUpDelay=1.0, getUpSpeed=1.0)

# preset anchors (same numbers as Personality.Preset in C#)
PRESETS = {
    "frail_elder": dict(strength=0.55, legs=0.8, arms=0.6, neck=0.7, damping=1.3, balance=0.75, knockdown=0.55,
                        balanceRadius=0.2, hitBalanceLoss=1.1, hitLimp=0.85, reactionTime=0.3, recovery=1.0,
                        brace=0.35, fallTone=0.18, stepFollow=0.5, getUpDelay=2.2, getUpSpeed=0.7),
    "trained_fighter": dict(strength=1.35, legs=1.3, spine=1.2, arms=1.2, neck=1.3, balance=1.0, knockdown=2.4,
                            balanceRadius=0.55, hitBalanceLoss=0.3, hitLimp=0.4, reactionTime=0.06, recovery=5.0,
                            brace=1.0, anticipation=0.6, fallTone=0.45, stepFollow=2.2, getUpDelay=0.4,
                            getUpSpeed=1.25),
    "drunk": dict(strength=0.7, legs=0.75, spine=0.6, arms=0.5, neck=0.4, damping=0.7, balance=0.55, knockdown=0.45,
                  balanceRadius=0.3, hitBalanceLoss=1.2, hitLimp=0.95, reactionTime=0.45, recovery=0.8, brace=0.05,
                  fallTone=0.08, stepFollow=0.9, sway=0.05, getUpDelay=2.8, getUpSpeed=0.8),
    "ragdoll": dict(knockdown=0.01, hitLimp=1.0, reactionTime=9.0, recovery=0.0, brace=0.0, fallTone=0.02,
                    getUpDelay=-1.0),
}

# word -> preset to start from
PRESET_WORDS = [
    (r"\b(frail|elderly|old|aged|grandma|grandpa|grandmother|grandfather|senior)\b", "frail_elder"),
    (r"\b(fighter|boxer|soldier|martial|trained|athlete|brawler|warrior|bodyguard)\b", "trained_fighter"),
    (r"\b(drunk|tipsy|intoxicated|wasted|sloshed|dizzy)\b", "drunk"),
    (r"\b(unconscious|dead|knocked out|lifeless|ragdoll)\b", "ragdoll"),
]

# word -> multiplicative / absolute nudges on top
NUDGES = [
    (r"\b(braces?|bracing|catches? (him|her|them)sel(f|ves))\b", dict(brace=("set", 1.0), reactionTime=("mul", 0.7))),
    (r"\b(flops?|floppy|limp|noodle)\b", dict(brace=("set", 0.0), fallTone=("mul", 0.4), hitLimp=("set", 1.0))),
    (r"\b(strong|muscular|burly|heavy[- ]set)\b", dict(strength=("mul", 1.25), knockdown=("mul", 1.3))),
    (r"\b(weak|tired|exhausted|injured|sick|wounded)\b", dict(strength=("mul", 0.7), knockdown=("mul", 0.7), getUpSpeed=("mul", 0.8), recovery=("mul", 0.6))),
    (r"\b(stiff|rigid|robot(ic)?|tense)\b", dict(damping=("mul", 1.5), strength=("mul", 1.2), hitLimp=("mul", 0.6))),
    (r"\b(relaxed|loose|chill)\b", dict(damping=("mul", 0.8), strength=("mul", 0.85))),
    (r"\b(child|kid|small|light)\b", dict(knockdown=("mul", 0.75), getUpSpeed=("mul", 1.2), getUpDelay=("mul", 0.6))),
    (r"\b(clumsy)\b", dict(balanceRadius=("mul", 0.6), knockdown=("mul", 0.7))),
    (r"\b(alert|ready|careful|cautious)\b", dict(anticipation=("set", 0.5), reactionTime=("mul", 0.7))),
    (r"\b(slow|sluggish)\b", dict(reactionTime=("mul", 1.6), getUpSpeed=("mul", 0.8))),
    (r"\b(quick|nimble|agile)\b", dict(reactionTime=("mul", 0.6), getUpSpeed=("mul", 1.2), stepFollow=("mul", 1.4))),
    (r"\b(stays? down|doesn'?t get up|won'?t get up)\b", dict(getUpDelay=("set", -1.0))),
    (r"\b(very|extremely|really)\b", None),  # intensifier, handled below
]

RANGES = dict(strength=(0.2, 2.0), legs=(0.3, 2.0), spine=(0.3, 2.0), arms=(0.2, 2.0), neck=(0.2, 2.0),
              damping=(0.4, 2.5), balance=(0.0, 1.0), knockdown=(0.01, 4.0), balanceRadius=(0.1, 0.8),
              hitBalanceLoss=(0.1, 2.0), hitLimp=(0.0, 1.0), reactionTime=(0.03, 9.0), recovery=(0.0, 8.0),
              brace=(0.0, 1.0), anticipation=(0.0, 1.0), fallTone=(0.0, 0.8), stepFollow=(0.0, 3.0),
              sway=(0.0, 0.15), getUpDelay=(-1.0, 6.0), getUpSpeed=(0.5, 1.6))


def from_text(text: str, name: str | None = None) -> dict:
    t = text.lower()
    p = dict(DEFAULT)
    base = "average"
    for pat, key in PRESET_WORDS:
        if re.search(pat, t):
            p.update(PRESETS[key])
            base = key
            break
    strength = 1.5 if re.search(r"\b(very|extremely|really)\b", t) else 1.0
    applied = []
    for pat, nudge in NUDGES:
        if nudge and re.search(pat, t):
            applied.append(pat)
            for k, (op, v) in nudge.items():
                if op == "set":
                    p[k] = v
                else:
                    p[k] = p[k] * (v ** strength)
    for k, (lo, hi) in RANGES.items():
        if p[k] >= 0 or k != "getUpDelay":
            p[k] = max(lo, min(hi, p[k]))
    p["name"] = name or re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:40]
    p["_from"] = {"text": text, "preset": base, "nudges": len(applied)}
    return p


if __name__ == "__main__":
    args = sys.argv[1:]
    out = None
    if args and args[0] == "--json":
        out, args = args[1], args[2:]
    items = [from_text(a) for a in args]
    s = json.dumps({"items": items}, indent=1)
    if out:
        open(out, "w", encoding="utf-8").write(s)
    print(s)
