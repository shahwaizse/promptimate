"""In this town, mirrors show you ten years from now. But my mirror is empty. (narration-paced; the camera is the
mirror: characters looking into one face the camera)"""
TITLE = "In This Town, Mirrors Show You In 10 Years. Mine Is Empty."
VOICE, SPEED = "tv_M2", 1.0
CAPTIONS = {"size": 80, "highlight": False, "max_words": 3}
KEYWORDS = ["mirror", "empty", "ten", "Ghost", "Timmy", "Mom", "Preston", "apron", "hairnet"]

# ---- cast: classic blocky characters; one copy of a character per set (characters don't travel between lots)
CAST = [
    # town street, in front of the CAFE (A)
    {"name": "Lady", "look": "c_lady", "at": [46, 6]},
    {"name": "Man", "look": "c_man", "at": [52, 6]},
    {"name": "Mayor", "look": "c_butler", "at": [62, 12], "yaw": 90},
    {"name": "PrestonA", "look": "c_preston", "at": [50, 9.5], "yaw": 90},
    {"name": "TimmyA", "look": "c_timmy", "at": [43, 10], "yaw": -90},
    # Timmy's room (B)
    {"name": "TimmyR", "look": "c_timmy", "at": [450, -3]},
    # the bakery (C)
    {"name": "Mom", "look": "c_mom", "at": [352, -7.5]},
    {"name": "TimmyB", "look": "c_timmy", "at": [345, 2], "yaw": 180},
    {"name": "PrestonB", "look": "c_preston", "at": [354, 16], "yaw": 180},
]

# shared prompt strings (identical across episodes: repeated prompts are free)
IDLE = "a person stands still, relaxed, looking around"
HAPPY = "a person stands and smiles happily"
SAD = "a person stands alone with their head down, sad"
STARE = "a person stares in surprise"
WALK = "a person walks forward casually"
WALK_SAD = "a person walks forward slowly, tired, head down"
JOY = "a person jumps up and down with joy, arms in the air"
FISTS = "a person stands still, watching sadly, then clenches their fists with determination"
SMUG = "a person stands with arms crossed, chin raised, smug"
LAUGH_AT = "a person points forward and laughs"
LAUGH = "a person laughs hard, bending over and holding their stomach"
SHRUG = "a person shrugs"
WAVE = "a person waves with their right hand"
NOD = "a person nods slowly"
WIPE = "a person stands behind a counter, working, wiping the counter"
SHOCK_BACK = "a person turns and steps back in surprise, arms down at their sides"
LOOK_SELF = "a person looks down at their own body in shock"
HUG = "a person steps forward and hugs someone tightly"
SIT_GROUND = "a person sits down on the ground"
SIT_GROUND_SAD = "a person sits on the ground, head down, sad"
GALLOP = "a person gallops forward like a horse"
FLEX = "a person flexes both arms proudly"
STILL_SWAY = "a person stands very still, then sways tiredly"

ACTORS = [
    # ---------------------------------------------------------------- A: the street
    {"name": "Lady", "start": [46, 6], "facing": "+Z", "beats": [
        {"at": 0.0, "prompt": IDLE, "seconds": 2.0},
        {"at": "@how", "prompt": STARE, "seconds": 2.4},
        {"at": "@small", "prompt": SHRUG, "seconds": 1.8},
        {"prompt": HAPPY, "seconds": 3.0, "face": "Man"},
        {"at": "@plan", "prompt": HAPPY, "seconds": 3.0, "face": "+Z"},
    ]},
    {"name": "Man", "start": [52, 6], "facing": "+Z", "beats": [
        {"at": 0.6, "prompt": IDLE, "seconds": 2.0},
        {"at": "@small+1.8", "prompt": LOOK_SELF, "seconds": 2.6},
        {"prompt": JOY, "seconds": 2.6},
        {"at": "@plan", "prompt": NOD, "seconds": 2.0, "face": "Lady"},
        {"at": "@ghost", "prompt": LAUGH, "seconds": 2.6, "face": "TimmyA"},
    ]},
    {"name": "Mayor", "start": [62, 12], "facing": "-X", "beats": [
        {"at": "@legend+1.0", "prompt": GALLOP, "seconds": 3.0, "to": [55, 12.5]},
        {"prompt": GALLOP, "seconds": 2.6, "to": [60, 13], "face": "+Z"},
        {"at": "@plan", "prompt": NOD, "seconds": 2.0, "face": "+Z"},
    ]},
    {"name": "PrestonA", "start": [50, 9.5], "facing": "-X", "beats": [
        {"at": "@plan", "prompt": SMUG, "seconds": 3.0, "face": "+Z"},
        {"at": "@ghost", "prompt": LAUGH_AT, "seconds": 2.4, "face": "TimmyA"},
        {"prompt": LAUGH, "seconds": 2.6, "face": "TimmyA"},
    ]},
    {"name": "TimmyA", "start": [43, 10], "facing": "+X", "beats": [
        {"at": "@ghost", "prompt": WALK_SAD, "seconds": 2.4, "to": [46, 10.5], "face": "PrestonA"},
        {"prompt": SAD, "seconds": 3.0, "face": "PrestonA"},
    ]},
    # ---------------------------------------------------------------- B: Timmy's room, the empty mirror (camera = mirror)
    {"name": "TimmyR", "start": [450, -3], "facing": "+Z", "beats": [
        {"at": "@me", "prompt": STARE, "seconds": 2.6},
        {"at": "@wall", "prompt": WAVE, "seconds": 1.8},
        {"prompt": SAD, "seconds": 2.6},
        {"at": "@broccoli", "prompt": FLEX, "seconds": 2.4},
        {"prompt": SAD, "seconds": 1.8},
        {"at": "@helmet", "prompt": NOD, "seconds": 1.8},
        {"prompt": SHRUG, "seconds": 1.6},
        {"at": "@stare", "prompt": STILL_SWAY, "seconds": 3.0},
        {"prompt": SIT_GROUND, "seconds": 2.0},
        {"prompt": SIT_GROUND_SAD, "seconds": 3.0},
    ]},
    # ---------------------------------------------------------------- C: the bakery
    {"name": "Mom", "start": [352, -7.5], "facing": "+Z", "beats": [
        {"at": "@mom", "prompt": HAPPY, "seconds": 3.0},
        {"prompt": WIPE, "seconds": 2.4},
        {"at": "@covered", "prompt": SHOCK_BACK, "seconds": 2.0, "face": "TimmyB"},
        {"prompt": SAD, "seconds": 3.4},
        {"at": "@card", "prompt": WIPE, "seconds": 3.0},
        {"at": "@there", "prompt": STARE, "seconds": 2.6},
        {"at": "@smile", "prompt": HUG, "seconds": 2.2, "face": "TimmyB"},
        {"at": "@mine", "prompt": HAPPY, "seconds": 3.0},
        {"at": "@uncovered", "prompt": JOY, "seconds": 3.0},
        {"at": "@preston", "prompt": HAPPY, "seconds": 2.0, "face": "PrestonB"},
        {"at": "@twist", "prompt": LAUGH, "seconds": 2.6},
        {"prompt": HAPPY, "seconds": 2.0, "face": "PrestonB"},
    ]},
    {"name": "TimmyB", "start": [345, 2], "facing": "-Z", "beats": [
        {"at": "@mom", "prompt": IDLE, "seconds": 3.0, "face": "Mom"},
        {"at": "@covered", "prompt": SAD, "seconds": 3.0, "face": "Mom"},
        # around the left end of the counter, to stand beside Mom
        {"at": "@card", "prompt": WALK, "seconds": 4.0, "to": [349, -7.5], "via": [[337, 2], [337, -7.5]], "face": "+Z"},
        {"at": "@next", "prompt": STARE, "seconds": 2.0},
        {"at": "@there", "prompt": LOOK_SELF, "seconds": 2.6},
        {"at": "@smile", "prompt": HUG, "seconds": 2.2, "face": "Mom"},
        {"at": "@mine", "prompt": HAPPY, "seconds": 3.0},
        {"at": "@uncovered", "prompt": JOY, "seconds": 3.0},
        {"at": "@preston", "prompt": STARE, "seconds": 2.0, "face": "PrestonB"},
        {"at": "@twist", "prompt": SMUG, "seconds": 3.4, "face": "PrestonB"},
    ]},
    {"name": "PrestonB", "start": [354, 16], "facing": "-Z", "beats": [
        {"at": "@preston", "prompt": WALK, "seconds": 2.2, "to": [352, 1.5], "face": "TimmyB"},
        {"prompt": LAUGH_AT, "seconds": 2.2, "face": "TimmyB"},
        {"prompt": STARE, "seconds": 1.6, "face": "-Z"},
        {"at": "@stopped", "prompt": SHOCK_BACK, "seconds": 2.0},
        {"at": "@twist", "prompt": LOOK_SELF, "seconds": 2.6},
        {"prompt": SAD, "seconds": 3.0},
    ]},
]

CAMERAS = [
    # one cue per story moment (the recorder adds coverage cuts and push-ins); fixed shots for sets
    # A: the street, the rule (the camera is the mirror)
    {"name": "rule", "start": 0.0, "subject": "Lady", "shot": "medium", "angle": 0},
    {"name": "older", "start": "@how", "subject": "Lady", "shot": "close", "angle": 10},
    {"name": "gray hairs", "start": "@small", "subject": "Lady", "shot": "close", "angle": -15},
    {"name": "mustache", "start": "@small+1.8", "subject": "Man", "shot": "full", "angle": 15},
    {"name": "the mayor", "start": "@legend", "subject": "Mayor", "shot": "medium", "angle": 20},
    {"name": "gallop", "start": "@legend+1.0", "track": "Mayor", "offset": [3, 1.6, 9], "aim": [0, 1, 0], "fov": 42},
    {"name": "the street", "start": "@plan", "pos": [52, 6, 26], "look": [52, 3.5, 6], "fov": 52, "subjects": []},
    # B: Timmy's room
    {"name": "room", "start": "@me", "pos": [450, 7, 16], "look": [450, 3.5, -2], "fov": 52, "subjects": []},
    {"name": "nobody there", "start": "@me+1.6", "subject": "TimmyR", "shot": "close", "angle": 0},
    {"name": "just the wall", "start": "@wall", "subject": "TimmyR", "shot": "medium", "angle": 20},
    # A: Ghost
    {"name": "ghost", "start": "@ghost", "subject": "PrestonA", "with": "TimmyA", "shot": "full", "angle": 0},
    {"name": "preston laughs", "start": "@ghost+2.0", "subject": "PrestonA", "shot": "close", "angle": 15},
    {"name": "ghost timmy", "start": "@ghost.end-1.0", "subject": "TimmyA", "shot": "close", "angle": -10},
    # C: the bakery, mom
    {"name": "bakery", "start": "@mom", "pos": [350, 7, 18], "look": [351, 4, -5], "fov": 52, "subjects": []},
    {"name": "mom smiles", "start": "@mom+1.4", "subject": "Mom", "shot": "close", "angle": 0},
    {"name": "covered", "start": "@covered", "subject": "Mom", "with": "TimmyB", "shot": "medium", "angle": 0},
    {"name": "nine days", "start": "@covered.end-1.6", "subject": "Mom", "shot": "close", "angle": 15},
    # B: three attempts
    {"name": "broccoli", "start": "@broccoli", "subject": "TimmyR", "shot": "full", "angle": 15},
    {"name": "empty", "start": "@broccoli.end-0.8", "subject": "TimmyR", "shot": "close", "angle": 0},
    {"name": "helmet", "start": "@helmet", "subject": "TimmyR", "shot": "medium", "angle": -20},
    {"name": "nine hours", "start": "@stare", "subject": "TimmyR", "shot": "close", "angle": 10},
    {"name": "legs asleep", "start": "@stare+2.4", "subject": "TimmyR", "shot": "full", "angle": -25},
    # C: the last card, the big moment, the twist
    {"name": "last card", "start": "@card", "subject": "TimmyB", "shot": "full", "angle": 30},
    {"name": "next to mom", "start": "@next", "subject": "TimmyB", "with": "Mom", "shot": "medium", "angle": 0},
    {"name": "there i was", "start": "@there", "subject": "TimmyB", "shot": "close", "angle": 0},
    {"name": "her apron", "start": "@there.end-1.2", "subject": "Mom", "shot": "close", "angle": 10},
    {"name": "smiling at me", "start": "@smile", "subject": "Mom", "with": "TimmyB", "shot": "medium", "angle": 0},
    {"name": "it's in hers", "start": "@mine", "subject": "TimmyB", "shot": "close", "angle": -10},
    {"name": "uncovered", "start": "@uncovered", "pos": [350, 7, 18], "look": [351, 4, -5], "fov": 52, "subjects": []},
    {"name": "preston walks in", "start": "@preston", "subject": "PrestonB", "shot": "full", "angle": 20},
    {"name": "laughs at me", "start": "@preston+2.2", "subject": "PrestonB", "with": "TimmyB", "shot": "medium", "angle": 0},
    {"name": "stopped", "start": "@stopped", "subject": "PrestonB", "shot": "close", "angle": 15},
    {"name": "working here", "start": "@twist", "subject": "PrestonB", "shot": "medium", "angle": -15},
    {"name": "for me", "start": "@twist+1.4", "subject": "TimmyB", "shot": "close", "angle": 10},
    {"name": "hairnet", "start": "@twist.end-1.0", "subject": "PrestonB", "shot": "close", "angle": 0},
]

LINES = [
    {"id": "rule", "text": "In this town, mirrors show you ten years from now. But my mirror is empty."},
    {"id": "how", "text": "You look in, and there you are. Older. Taller. Sometimes balder."},
    {"id": "small", "text": "Mrs. Park saw three gray hairs. Mr. Lopez saw a mustache down to his belt."},
    {"id": "legend", "text": "In 1987, the mayor's mirror showed a horse. He still gallops to work every morning. Just in case."},
    {"id": "plan", "text": "So nobody here worries about the future. You just check the mirror."},
    {"id": "me", "text": "And me? I'm Timmy. Twelve years old. And when I look in, nobody's there.", "gap": 0.3},
    {"id": "wall", "text": "No old me. No bald me. Just the wall behind me."},
    {"id": "ghost", "text": "Preston says empty means you're gone in ten years. Now everyone calls me Ghost."},
    {"id": "mom", "text": "That's my mom. In her mirror, she's running the bakery, smiling at somebody you can't see.", "gap": 0.3},
    {"id": "covered", "text": "When she saw my empty mirror, she covered every mirror in the house. She hasn't smiled in nine days."},
    {"id": "broccoli", "text": "So I tried to fix my future. I ate broccoli for a month. Empty.", "gap": 0.3},
    {"id": "helmet", "text": "I wore a helmet everywhere. Even in the bath. Empty."},
    {"id": "stare", "text": "I stared at that mirror for nine hours straight. My legs fell asleep. Still empty."},
    {"id": "card", "text": "So I did the one thing nobody here ever does. I looked into someone else's mirror.", "gap": 0.3},
    {"id": "next", "text": "I stood next to Mom, and looked into hers."},
    {"id": "there", "text": "And there I was. Ten years older. Right next to her. Wearing her apron."},
    {"id": "smile", "text": "The somebody she was smiling at? It was me."},
    {"id": "mine", "text": "My future isn't in my mirror. It's in hers."},
    {"id": "uncovered", "text": "That night, Mom took the covers off every mirror. She smiled for an hour straight."},
    {"id": "preston", "text": "Next day, Preston came to the bakery to laugh at me. He looked in our mirror.", "gap": 0.3},
    {"id": "stopped", "text": "He stopped laughing."},
    {"id": "twist", "text": "In ten years, he's working here. For me. In a hairnet."},
]
TITLES = [("@rule+2.6", "@rule.end+0.3", "EMPTY"), ("@there+1.0", "@there.end+0.3", "10 years from now")]

FACES = {
    "Lady": [(0, "neutral"), ("@how", "shocked"), ("@how+1.8", "happy"), ("@small", "tired"), ("@small+1.8", "grin"), ("@plan", "happy")],
    "Man": [(0, "neutral"), ("@small+1.8", "shocked"), ("@small+3.4", "grin"), ("@plan", "happy"), ("@ghost", "grin")],
    "Mayor": [(0, "neutral"), ("@legend", "shocked"), ("@legend+1.0", "grin"), ("@plan", "happy")],
    "PrestonA": [(0, "smug"), ("@ghost", "grin"), ("@ghost.end-1.0", "smug")],
    "TimmyA": [(0, "neutral"), ("@ghost", "sad"), ("@ghost.end-1.0", "crying")],
    "TimmyR": [(0, "neutral"), ("@me+1.6", "shocked"), ("@wall", "happy"), ("@wall+1.6", "sad"), ("@broccoli", "angry"),
               ("@broccoli.end-0.8", "sad"), ("@helmet", "smug"), ("@helmet.end-0.8", "tired"), ("@stare", "angry"),
               ("@stare+2.4", "tired"), ("@stare.end-0.8", "crying")],
    "Mom": [(0, "happy"), ("@mom", "happy"), ("@mom+1.8", "love"), ("@covered", "shocked"), ("@covered+1.4", "crying"),
            ("@covered.end-1.6", "sad"), ("@card", "sad"), ("@there", "shocked"), ("@smile", "love"), ("@mine", "happy"),
            ("@uncovered", "grin"), ("@preston", "happy"), ("@twist", "grin")],
    "TimmyB": [(0, "neutral"), ("@mom+1.8", "happy"), ("@covered", "sad"), ("@card", "angry"), ("@card+2.0", "neutral"),
               ("@next", "scared"), ("@there", "shocked"), ("@there+1.6", "happy"), ("@smile", "love"), ("@mine", "grin"),
               ("@preston", "shocked"), ("@twist", "smug")],
    "PrestonB": [(0, "smug"), ("@preston+2.2", "grin"), ("@preston.end-1.0", "neutral"), ("@stopped", "shocked"),
                 ("@twist", "scared"), ("@twist.end-1.0", "crying")],
}

# objects from other episodes' sets that must stay out of shot (an object with no show spans is hidden)
HIDE = [["Workspace", "Sets", n] for n in ("PaidBench", "SaleChair0", "SaleChair1", "SaleChair2", "SaleChair3", "CarryChair",
                                           "MomChair", "Jar")] + \
       [["Workspace", "Sets", "ChairMarket", "Sign"], ["Workspace", "Sets", "ChairMarket", "Price"],
        ["Workspace", "Sets", "TimmyRoom", "Poster"]]
PROPS = [{"path": p, "show": []} for p in HIDE]
FX = [
    {"actor": "Mom", "kind": "sparkle", "show": [["@smile", "@mine.end"]]},
    {"actor": "Mom", "kind": "hearts", "show": [["@uncovered", "@uncovered.end"]]},
    {"actor": "TimmyB", "kind": "sparkle", "show": [["@twist+1.4", "@twist.end"]]},
    {"actor": "Mom", "kind": "label", "show": [["@covered.end-1.6", "@covered.end", "9 DAYS"]]},
    {"actor": "TimmyR", "kind": "label", "show": [["@stare", "@stare.end", "9 HOURS"]]},
]
MUSIC = {"query": "mysterious", "pick": 0, "from": 0, "gain": 0.45}
SFX = [("@rule+2.6", "whoosh", 0.5), ("@how+0.6", "shimmer", 0.5), ("@small+2.0", "boing", 0.6), ("@legend+1.2", "horse neigh", 0.6),
       ("@legend.end-1.4", "galloping", 0.5), ("@me+1.6", "wind", 0.5), ("@wall+0.4", "cricket", 0.4), ("@ghost+1.0", "ghost", 0.5),
       ("@ghost+2.2", "laugh", 0.5), ("@mom", "shop bell", 0.5), ("@covered+1.2", "gasp", 0.6), ("@broccoli.end-0.6", "buzzer", 0.5),
       ("@helmet.end-0.6", "buzzer", 0.6), ("@stare+2.6", "thud", 0.6), ("@stare.end-0.6", "buzzer", 0.7), ("@card", "heartbeat", 0.5),
       ("@there", "shimmer", 0.7), ("@smile", "aww", 0.5), ("@uncovered", "cheer", 0.4), ("@preston", "door bell", 0.5),
       ("@stopped", "record scratch", 0.7), ("@twist.end-0.8", "boom", 0.5)]
