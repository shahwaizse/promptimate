"""Suite tiers so iteration runs stay short. Pick the smallest tier that answers the question.

smoke    6 prompts x 1 seed: one per failure mode we care about (locomotion, stop, gesture, full-body, sequences).
         ~15-30 s warm through run_bench; use for every iteration.
standard all 18 prompts x 2 seeds.
full     all 18 prompts x 3 seeds: final numbers only.
"""
SMOKE = ["walk", "walk_stop", "wave", "jump", "seq_walk_stop_wave", "seq_jog_jump"]
TIERS = {
    "smoke": {"prompts": SMOKE, "seeds": [0]},
    "standard": {"prompts": None, "seeds": [0, 1]},
    "full": {"prompts": None, "seeds": [0, 1, 2]},
}


def resolve(tier: str | None, prompts: str | None, seeds: str | None) -> tuple[list[str] | None, list[int]]:
    """Explicit --prompts/--seeds override the tier's."""
    t = TIERS[tier] if tier else {"prompts": None, "seeds": [0, 1]}
    p = prompts.split(",") if prompts else t["prompts"]
    s = [int(x) for x in seeds.split(",") if x.strip()] if seeds else t["seeds"]
    return p, s
