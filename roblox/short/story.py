"""'In This Town, Nobody Can Sit Down': the one story shared by all three versions (A stock, B Promptimate,
C Roblox Prompt-to-Animation). Single source for the town layout, cast, story clock, shot list and voiceover.

Units: Roblox studs, world space, Y up, ground at y = 0. Directions as unit vectors on the ground (x, z).
Edit time == story time: shots are consecutive windows of one continuous performance, so cuts stay continuous.
"""
from __future__ import annotations

import math

FPS = 24                      # deterministic render rate (frames are captured one by one)
SIZE = (1080, 1920)           # vertical output

# studs per metre on each body (PromptimatePlayer scales the clip by the rig's standing hips height / 0.95 m)
STAND = {"timmy": 2.034, "officer": 2.393, "lee": 2.393}
SPM = {k: v / 0.95 for k, v in STAND.items()}

PX, NX, PZ, NZ = (1, 0), (-1, 0), (0, 1), (0, -1)

# ---------------------------------------------------------------------------------------------------------- layout
BENCH = {"center": (0.0, 0.6), "length": 6.0, "facing": PZ}        # seat refined from B's seated hips (see town.py)
SIGN_BENCH = (-4.6, 0.4)                                            # "NO SITTING" sign beside the bench
LEE_DOOR = (7.0, -2.6)                                              # Mrs. Lee's flower shop doorway
CRATES = (12.0, 6.5)                                                # crate stack Timmy hides behind
TIMMY_HIDE = (16.2, 6.5)
OFFICER_SCARE = (16.6, 11.2)

CAST = {
    "timmy": {"label": "Timmy", "height": 0.85, "width": 0.9,
              "colors": {"Head": (245, 205, 48), "Arms": (245, 205, 48), "Torso": (13, 105, 172), "Legs": (40, 127, 71)}},
    "officer": {"label": "Officer", "height": 1.0, "width": 1.0, "hat": "police",
                "colors": {"Head": (204, 142, 105), "Arms": (204, 142, 105), "Torso": (33, 50, 92), "Legs": (27, 36, 64)}},
    "lee": {"label": "Mrs. Lee", "height": 1.0, "width": 1.0, "hat": "bun",
            "colors": {"Head": (234, 184, 146), "Arms": (234, 184, 146), "Torso": (218, 112, 162), "Legs": (98, 71, 140)}},
}

# ---------------------------------------------------------------------------------------------------- story clock
# Beats (seconds). Every version follows the same beats and blocking; how each beat is animated differs.
T = {
    "timmy_walk": (0.0, 4.0), "timmy_sit": (4.0, 7.0), "timmy_phone": (7.0, 10.5), "timmy_up": (10.5, 11.5),
    "timmy_run": (11.5, 15.3), "timmy_hide": (15.3, 23.0), "timmy_fall": (23.0, 25.5), "timmy_ground": (25.5, 32.6),
    "officer_wait": (0.0, 7.5), "officer_walk": (7.5, 13.5), "officer_look": (13.5, 16.5), "officer_turn": (16.5, 18.5),
    "officer_walk2": (18.5, 23.0), "officer_boo": (23.0, 25.5), "officer_talk": (25.5, 29.0), "officer_sit": (29.0, 32.6),
    "lee_idle": (0.0, 16.5), "lee_point": (16.5, 19.0), "lee_arms": (19.0, 32.6),
}
END = 32.6

# Blocking: where hips go (studs). Shared by all versions (B pins them with root_path; A/C move with MoveTo-style
# straight lines between the same points at the same times).
PATHS = {
    "timmy_walk": [(0.0, (-13.0, 2.4)), (4.0, (0.0, 2.4))],
    "timmy_run": [(11.5, (0.3, 2.9)), (12.6, (7.5, 2.7)), (13.9, (15.0, 3.6)), (14.8, TIMMY_HIDE)],
    "officer_walk": [(7.5, (-24.0, 7.5)), (13.5, (-3.5, 7.5))],
    "officer_walk2": [(18.5, (-3.5, 7.5)), (20.6, (7.5, 11.6)), (22.6, OFFICER_SCARE)],
}
START = {"timmy": ((-13.0, 2.4), PX), "officer": ((-24.0, 7.5), PX), "lee": (LEE_DOOR, PZ)}

# ------------------------------------------------------------------------------------------------------- shot list
# camera: {"pos": (x,y,z), "look": (x,y,z)} static, or {"track": who, "offset": (dx,dy,dz), "aim": (dx,dy,dz)}
# relative to that character's hips (smoothed); fov = vertical field of view of the 9:16 frame (degrees).
SHOTS = [
    ("s01", 0.0, 1.6, {"pos": (-6.0, 12.0, 30.0), "look": (-6.0, 2.0, 3.0), "fov": 62}, "wide: the street, the bench, the NO SITTING sign"),
    ("s02", 1.6, 3.0, {"pos": (-4.0, 4.6, 7.5), "look": (-4.6, 4.4, 0.4), "fov": 40}, "sign close-up"),
    ("s03", 3.0, 4.4, {"track": "timmy", "offset": (6.5, 1.6, 5.5), "aim": (0, 1.0, 0), "fov": 55}, "follow Timmy, tired walk"),
    ("s04", 4.4, 6.4, {"pos": (1.5, 3.8, 12.5), "look": (0.0, 2.2, 1.2), "fov": 50}, "Timmy turns and sits on the bench"),
    ("s05", 6.4, 7.3, {"pos": (2.2, 3.2, 6.8), "look": (0.0, 2.8, 1.2), "fov": 45}, "close: Timmy relaxes"),
    ("s06", 7.3, 8.7, {"pos": (2.6, 3.1, 5.2), "look": (0.0, 3.0, 1.1), "fov": 42}, "close: phone call"),
    ("s07", 8.7, 10.4, {"track": "officer", "offset": (8.5, 0.6, 7.0), "aim": (0, 1.2, 0), "fov": 52}, "low angle: the officer marches in"),
    ("s08", 10.4, 11.6, {"pos": (-1.5, 3.6, 11.0), "look": (0.0, 2.6, 2.0), "fov": 52}, "Timmy jumps up"),
    ("s09", 11.6, 15.1, {"track": "timmy", "offset": (0.0, 6.0, 17.0), "aim": (0, 1.0, 0), "fov": 60}, "side track: Timmy runs and stops behind the crates"),
    ("s10", 15.1, 16.5, {"pos": (-4.5, 4.2, 15.0), "look": (-3.5, 3.0, 7.5), "fov": 50}, "the officer looks around"),
    ("s11", 16.5, 18.3, {"pos": (6.0, 4.2, 6.5), "look": (7.0, 3.6, -2.6), "fov": 50}, "Mrs. Lee points"),
    ("s12", 18.3, 19.7, {"pos": (21.5, 4.8, 5.0), "look": (6.0, 3.0, 8.0), "fov": 55}, "over Timmy's shoulder: officer coming"),
    ("s13", 19.7, 21.3, {"pos": (11.0, 3.6, 14.5), "look": (15.8, 2.8, 6.9), "fov": 42}, "close: Timmy peeks"),
    ("s14", 21.3, 23.0, {"track": "officer", "offset": (3.5, 1.0, 5.0), "aim": (0, 1.8, 0), "fov": 55}, "officer rounds the crates"),
    ("s15", 23.0, 24.3, {"pos": (24.0, 4.0, 12.5), "look": (16.8, 2.4, 8.4), "fov": 55}, "BOO: Timmy falls"),
    ("s16", 24.3, 26.0, {"pos": (21.0, 8.5, 9.8), "look": (17.4, 0.8, 6.8), "fov": 50}, "high angle: Timmy on the ground"),
    ("s17", 26.0, 29.0, {"pos": (19.0, 1.4, 4.8), "look": (16.6, 4.2, 11.2), "fov": 60}, "low angle: officer talks"),
    ("s18", 29.0, 30.8, {"pos": (25.0, 4.2, 14.5), "look": (17.0, 1.8, 8.6), "fov": 52}, "officer sits down too"),
    ("s19", 30.8, END, {"pos": (30.0, 13.0, 27.0), "look": (14.0, 2.0, 6.0), "fov": 55}, "wide: both sitting under the sign"),
]

# ------------------------------------------------------------------------------------------------------- voiceover
VOICE = {"narrator": "af_heart", "mom": "af_nova", "officer": "am_michael"}
VO = [
    (0.3, "narrator", "In this town, nobody is allowed to sit down."),
    (3.2, "narrator", "But Timmy was so tired."),
    (4.9, "narrator", "So he sat. Just for one second."),
    (7.3, "narrator", "Then his phone rang."),
    (8.5, "mom", "Timmy! The Sit Police are coming!"),
    (10.7, "narrator", "He ran,"),
    (12.0, "narrator", "and hid behind the crates."),
    (13.8, "narrator", "The officer looked everywhere."),
    (16.6, "narrator", "Mrs. Lee pointed. Of course she did."),
    (19.6, "narrator", "Timmy held his breath."),
    (23.0, "officer", "Boo!"),
    (24.0, "narrator", "But the officer didn't arrest him."),
    (26.2, "officer", "Mind if I sit too? My feet are killing me."),
    (29.6, "narrator", "Turns out, even the Sit Police get tired."),
]
TITLE = "In this town, you can't sit down."

# Beats a judge should be able to read (for the evaluation packets): (id, story time, what should be visible)
BEATS = [
    ("tired_walk", 3.6, "Timmy walks in, visibly tired"),
    ("sit_bench", 5.8, "Timmy sits down on the bench"),
    ("phone", 8.0, "Timmy answers a phone call"),
    ("jump_up", 11.0, "Timmy jumps up in a panic"),
    ("run_stop", 14.9, "Timmy runs and stops behind the crates"),
    ("look_around", 15.8, "the officer searches, looking around"),
    ("point", 17.4, "Mrs. Lee points toward the crates"),
    ("peek", 20.5, "Timmy hides and peeks out from behind the crates"),
    ("scare_fall", 24.0, "Timmy gets scared and falls down"),
    ("talk", 27.5, "the officer talks to Timmy with gestures"),
    ("sit_ground", 31.5, "the officer sits down next to Timmy"),
]


def shot_at(t: float):
    for s in SHOTS:
        if s[1] <= t < s[2]:
            return s
    return SHOTS[-1]


def yaw_of(d) -> float:
    """Roblox yaw (radians, CFrame.Angles(0, yaw, 0)) of a character facing ground direction d=(x, z)."""
    return math.atan2(-d[0], -d[1])
