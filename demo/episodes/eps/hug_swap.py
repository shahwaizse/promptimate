"""In this world, if you hug someone, you swap bodies. (narration-paced; a swapped mind is played by the other's rig)"""
TITLE = "In This World, If You Hug Someone, You Swap Bodies"
VOICE, SPEED = "tv_M2", 1.6
CAPTIONS = {"size": 66, "highlight": False, "max_words": 3}
KEYWORDS = ["hug", "swap", "Pop", "Timmy", "Preston", "mom", "mansion", "bakery"]

# ---- cast: classic blocky characters; one copy of a character per set (characters don't travel between lots)
# After the swap, the Timmy rig carries Preston's mind and the Preston rig carries Timmy's: their acting and faces swap.
CAST = [
    # town street, in front of the CAFE (scenes A)
    {"name": "Lady", "look": "c_lady", "at": [46, 6], "yaw": -90},
    {"name": "Man", "look": "c_man", "at": [52, 6], "yaw": 90},
    {"name": "TimmyA", "look": "c_timmy", "at": [40, 10], "yaw": -90},
    {"name": "PrestonA", "look": "c_preston", "at": [50, 9.5], "yaw": 90},
    # the bakery (B)
    {"name": "Mom", "look": "c_mom", "at": [352, -7.5]},
    {"name": "TimmyB", "look": "c_timmy", "at": [349, 1.5], "yaw": 180},
    {"name": "PrestonB", "look": "c_preston", "at": [354, 16], "yaw": 180},
    # Preston's mansion lawn (C)
    {"name": "PrestonM", "look": "c_preston", "at": [600, -142]},
    {"name": "Butler", "look": "c_butler", "at": [605, -124], "yaw": 90},
]

# shared prompt strings (identical across episodes: repeated prompts are free)
IDLE = "a person stands still, relaxed, looking around"
HAPPY = "a person stands and smiles happily"
SAD = "a person stands alone with their head down, sad"
STARE = "a person stares in surprise"
WALK = "a person walks forward casually"
RUN = "a person runs forward excitedly"
JOY = "a person jumps up and down with joy, arms in the air"
LAUGH = "a person laughs hard, bending over and holding their stomach"
TALK = "a person stands and talks, gesturing with both hands"
GIVE = "a person holds out both hands, offering something"
SHRUG = "a person shrugs"
WAVE = "a person waves with their right hand"
STOMP = "a person stomps their foot down hard"
BOW = "a person bows deeply"
WIPE = "a person stands behind a counter, working, wiping the counter"
SHOCK_BACK = "a person turns and steps back in surprise, arms down at their sides"
BACK_ACHE = "a person stands still and stretches their back, tired"
OPEN_ARMS = "a person opens their arms wide for a hug"
STUMBLE = "a person stumbles forward, arms flailing"
HUG = "a person steps forward and hugs someone tightly"
LOOK_SELF = "a person looks down at their own body in shock"
POUNCE = "a person jumps forward with arms wide"
DUCK = "a person ducks down quickly"
SIT_DOWN = "a person turns around and sits down"
SIT_SAD = "a person sits alone, head down, sad"

ACTORS = [
    # ---------------------------------------------------------------- A: the street
    {"name": "Lady", "start": [46, 6], "facing": "+X", "beats": [
        {"at": 0.0, "prompt": OPEN_ARMS, "seconds": 2.0, "face": "Man"},
        {"prompt": SHOCK_BACK, "seconds": 2.0},
        {"prompt": IDLE, "seconds": 3.0, "face": "Man"},
        {"at": "@wave", "prompt": WAVE, "seconds": 2.0, "face": "Man"},
        {"prompt": IDLE, "seconds": 3.0, "face": "+Z"},
    ]},
    {"name": "Man", "start": [52, 6], "facing": "-X", "beats": [
        {"at": 0.6, "prompt": SHOCK_BACK, "seconds": 2.2},
        {"prompt": IDLE, "seconds": 4.0, "face": "Lady"},
        {"at": "@cat+2.6", "prompt": BACK_ACHE, "seconds": 2.4},
        {"at": "@wave", "prompt": WAVE, "seconds": 2.0, "face": "Lady"},
        {"prompt": IDLE, "seconds": 3.0, "face": "+Z"},
    ]},
    {"name": "TimmyA", "start": [40, 10], "facing": "+X", "beats": [
        # Timmy, then (after the swap) Preston inside Timmy's body, then Timmy again
        {"at": "@trip", "prompt": [WALK, STUMBLE], "seconds": [1.4, 1.0], "to": [47.5, 9.8], "face": "PrestonA"},
        {"prompt": HUG, "seconds": 1.8, "face": "PrestonA"},
        {"at": "@swap+1.4", "prompt": STOMP, "seconds": 1.6, "face": "PrestonA"},
        {"at": "@butler", "prompt": WALK, "seconds": 3.0, "to": [46, 10.5], "face": "+X"},
        {"at": "@chase+0.6", "prompt": RUN, "seconds": 2.4, "to": [62, 11]},
        {"at": "@ducked", "prompt": DUCK, "seconds": 1.6, "face": "PrestonA"},
        {"at": "@bucks+1.6", "prompt": SHRUG, "seconds": 1.5, "face": "PrestonA"},
        {"at": "@shoes", "prompt": SAD, "seconds": 2.2, "face": "PrestonA"},
        {"prompt": HUG, "seconds": 2.0, "face": "PrestonA"},
        {"prompt": JOY, "seconds": 3.0},
        {"prompt": HAPPY, "seconds": 3.0},
    ]},
    {"name": "PrestonA", "start": [50, 9.5], "facing": "-X", "beats": [
        # Preston, then Timmy inside Preston's body, then Preston again
        {"at": "@trip", "prompt": IDLE, "seconds": 1.6, "face": "TimmyA"},
        {"prompt": STARE, "seconds": 1.6, "face": "TimmyA"},
        {"at": "@swap", "prompt": LOOK_SELF, "seconds": 2.5},
        {"at": "@butler", "prompt": WALK, "seconds": 3.0, "to": [41, 10], "via": [[48, 12.8]], "face": "+X"},
        {"at": "@chase+0.6", "prompt": RUN, "seconds": 2.4, "to": [58, 10.5]},
        {"at": "@ducked", "prompt": POUNCE, "seconds": 1.6, "face": "TimmyA"},
        {"at": "@bucks", "prompt": GIVE, "seconds": 1.8, "face": "TimmyA"},
        {"at": "@truth", "prompt": TALK, "seconds": 3.0, "face": "TimmyA"},
        {"prompt": TALK, "seconds": 2.4, "face": "TimmyA"},
        {"at": "@shoes+2.2", "prompt": HUG, "seconds": 2.0, "face": "TimmyA"},
        {"prompt": SAD, "seconds": 2.5},
        {"prompt": HAPPY, "seconds": 3.0, "face": "TimmyA"},
    ]},
    # ---------------------------------------------------------------- B: the bakery
    {"name": "Mom", "start": [352, -7.5], "facing": "+Z", "beats": [
        {"at": "@me", "prompt": WIPE, "seconds": 2.5},
        {"at": "@mom", "prompt": WAVE, "seconds": 1.6, "face": "TimmyB"},
        {"prompt": OPEN_ARMS, "seconds": 1.8, "face": "TimmyB"},
        {"prompt": SAD, "seconds": 2.0},
        {"at": "@pancakes", "prompt": GIVE, "seconds": 2.2, "face": "TimmyB"},
        {"at": "@stuck", "prompt": OPEN_ARMS, "seconds": 1.8, "face": "TimmyB"},
        {"prompt": HAPPY, "seconds": 1.0},
        # around the end of the counter while the camera is on the street
        {"at": "@ducked", "prompt": WALK, "seconds": 4.0, "to": [352, 0.4], "via": [[364, -7.5], [364, 1]], "face": "+Z"},
        {"at": "@forgot", "prompt": HAPPY, "seconds": 1.6, "face": "PrestonB"},
        {"at": "@forgot+1.6", "prompt": HUG, "seconds": 2.2, "face": "PrestonB"},
        {"at": "@pop", "prompt": LOOK_SELF, "seconds": 2.5},
        {"prompt": STARE, "seconds": 2.5, "face": "TimmyB"},
    ]},
    {"name": "TimmyB", "start": [349, 1.5], "facing": "-Z", "beats": [
        {"at": "@me", "prompt": WAVE, "seconds": 1.8, "face": "Mom"},
        {"prompt": HAPPY, "seconds": 2.0, "face": "Mom"},
        {"at": "@mom+3.0", "prompt": SHOCK_BACK, "seconds": 1.8},
        {"at": "@pancakes", "prompt": HAPPY, "seconds": 2.5, "face": "Mom"},
        {"at": "@stuck", "prompt": SHOCK_BACK, "seconds": 2.0},
        {"at": "@chase", "prompt": WALK, "seconds": 2.0, "to": [348.5, 3], "face": "Mom"},
        {"at": "@forgot", "prompt": HAPPY, "seconds": 2.0, "face": "Mom"},
        {"at": "@pop", "prompt": STARE, "seconds": 1.6, "face": "Mom"},
        {"at": "@isamom+1.4", "prompt": LAUGH, "seconds": 2.6},
    ]},
    {"name": "PrestonB", "start": [354, 16], "facing": "-Z", "beats": [
        {"at": "@forgot", "prompt": WALK, "seconds": 1.6, "to": [353.5, 3.4], "face": "Mom"},
        {"prompt": HUG, "seconds": 2.2, "face": "Mom"},
        {"at": "@pop", "prompt": HAPPY, "seconds": 2.5, "face": "Mom"},     # now Mom inside Preston's body
        {"at": "@hottub", "prompt": WALK, "seconds": 2.5, "to": [356, 16]},
    ]},
    # ---------------------------------------------------------------- C: the mansion (Timmy inside Preston's body)
    {"name": "PrestonM", "start": [600, -142], "facing": "+Z", "beats": [
        {"at": "@mansion", "prompt": WALK, "seconds": 3.0, "to": [600, -116.5], "face": "-Z"},
        {"prompt": [SIT_DOWN, SIT_SAD], "seconds": [1.5, 3.5], "sit": "Throne", "sit_from": 1.2},
    ]},
    {"name": "Butler", "start": [605, -124], "facing": "-X", "beats": [
        {"at": "@butler", "prompt": BOW, "seconds": 2.0, "face": "PrestonM"},
        {"prompt": IDLE, "seconds": 2.0, "face": "PrestonM"},
    ]},
]

CAMERAS = [
    # one cue per story moment (the recorder adds coverage cuts and push-ins); fixed shots for sets
    # A: the street, the rule
    {"name": "open arms", "start": 0.0, "subject": "Lady", "shot": "medium", "angle": 20},
    {"name": "he backs off", "start": "@rule+1.2", "subject": "Man", "shot": "close", "angle": 10},
    {"name": "flash", "start": "@flash", "subject": "Lady", "with": "Man", "shot": "full", "angle": 0},
    {"name": "cat", "start": "@cat", "subject": "Lady", "shot": "close", "angle": -15},
    {"name": "grandpa", "start": "@cat+2.6", "subject": "Man", "shot": "medium", "angle": 20},
    {"name": "the street", "start": "@team", "pos": [52, 6, 26], "look": [52, 3.5, 5], "fov": 52, "subjects": []},
    {"name": "six feet", "start": "@wave", "subject": "Lady", "with": "Man", "shot": "full", "angle": 0},
    # B: the bakery
    {"name": "bakery", "start": "@me", "pos": [350, 7, 18], "look": [351, 4, -5], "fov": 52, "subjects": []},
    {"name": "timmy", "start": "@me+1.4", "subject": "TimmyB", "shot": "close", "angle": 10},
    {"name": "mom", "start": "@mom", "subject": "Mom", "shot": "close", "angle": 20},
    {"name": "by accident", "start": "@mom+1.6", "subject": "Mom", "with": "TimmyB", "shot": "medium", "angle": 0},
    # A: the trip
    {"name": "trip", "start": "@trip", "track": "TimmyA", "offset": [3, 1.6, 8], "aim": [0, 1, 0], "fov": 40},
    {"name": "into preston", "start": "@trip+1.8", "subject": "TimmyA", "with": "PrestonA", "shot": "full", "angle": 0},
    {"name": "i was preston", "start": "@swap", "subject": "PrestonA", "shot": "close", "angle": 10},
    {"name": "preston was me", "start": "@swap+1.4", "subject": "TimmyA", "shot": "close", "angle": -10},
    # C: the mansion
    {"name": "mansion", "start": "@mansion", "pos": [600, 24, -235], "look": [600, 15, -110], "fov": 48, "subjects": []},
    {"name": "walks in", "start": "@mansion+1.4", "track": "PrestonM", "offset": [3, 1.8, -9], "aim": [0, 1.2, 0], "fov": 40},
    {"name": "butler", "start": "@butler", "subject": "Butler", "with": "PrestonM", "shot": "full", "angle": 0},
    {"name": "alone", "start": "@butler+1.2", "subject": "PrestonM", "shot": "close", "angle": 15},
    # B: Preston at the bakery
    {"name": "pancakes", "start": "@pancakes", "subject": "Mom", "with": "TimmyB", "shot": "medium", "angle": 0},
    {"name": "loved", "start": "@pancakes+1.6", "subject": "TimmyB", "shot": "close", "angle": 15},
    {"name": "almost a hug", "start": "@stuck", "subject": "Mom", "shot": "medium", "angle": 20},
    {"name": "dodge", "start": "@stuck+1.0", "subject": "TimmyB", "shot": "close", "angle": -15},
    # A: three attempts, the truth, the swap back
    {"name": "chase wide", "start": "@chase", "pos": [52, 6, 26], "look": [52, 3.5, 6], "fov": 52, "subjects": []},
    {"name": "chase", "start": "@chase+0.6", "track": "PrestonA", "offset": [-3, 1.6, 9], "aim": [0, 1, 0], "fov": 42},
    {"name": "ducked", "start": "@ducked", "subject": "PrestonA", "with": "TimmyA", "shot": "full", "angle": 0},
    {"name": "hundred bucks", "start": "@bucks", "subject": "PrestonA", "shot": "medium", "angle": 15},
    {"name": "shrug", "start": "@bucks+1.6", "subject": "TimmyA", "shot": "close", "angle": 10},
    {"name": "the truth", "start": "@truth", "subject": "PrestonA", "shot": "close", "angle": 10},
    {"name": "thinks you're me", "start": "@loves", "subject": "TimmyA", "shot": "close", "angle": -10},
    {"name": "his shoes", "start": "@shoes", "subject": "TimmyA", "shot": "medium", "angle": 20},
    {"name": "hug back", "start": "@shoes+2.0", "subject": "TimmyA", "with": "PrestonA", "shot": "full", "angle": 0},
    {"name": "me again", "start": "@back", "subject": "TimmyA", "shot": "close", "angle": 10},
    # B: the twist
    {"name": "new friend", "start": "@forgot", "pos": [350, 6, 20], "look": [351, 4, 2], "fov": 46, "subjects": []},
    {"name": "mom hugs", "start": "@forgot+1.6", "subject": "Mom", "with": "PrestonB", "shot": "medium", "angle": 0},
    {"name": "pop", "start": "@pop", "subject": "Mom", "shot": "close", "angle": 15},
    {"name": "he is a mom", "start": "@isamom", "subject": "Mom", "shot": "medium", "angle": -20},
    {"name": "timmy laughs", "start": "@isamom+1.4", "subject": "TimmyB", "shot": "close", "angle": 10},
    {"name": "hot tub", "start": "@hottub", "subject": "PrestonB", "shot": "full", "angle": 20},
]

LINES = [
    {"id": "rule", "text": "In this world, if you hug someone, you swap bodies."},
    {"id": "flash", "text": "Arms around each other, a flash, a pop, and you're staring at your own face."},
    {"id": "cat", "text": "Hug your cat? You spend a day licking your paws. Hug your grandpa? Your back hurts for a week."},
    {"id": "team", "text": "In 2011, a whole football team hugged after a win. It took four months to swap back."},
    {"id": "wave", "text": "So nobody here hugs. People wave. From six feet away."},
    {"id": "me", "text": "And me? I'm Timmy. Poorest kid in town. I live above a bakery.", "gap": 0.3},
    {"id": "mom", "text": "That's my mom. Best hugger in the world, before the rule. She still opens her arms by accident."},
    {"id": "trip", "text": "Then, one Monday, I tripped. Right into Preston. Richest, meanest kid in town.", "gap": 0.3},
    {"id": "swap", "text": "Pop. I was Preston. And Preston was me."},
    {"id": "mansion", "text": "His mansion was huge. And empty. His parents have been away since 2019.", "gap": 0.3},
    {"id": "butler", "text": "The butler bowed. Nobody asked how my day was."},
    {"id": "pancakes", "text": "And Preston? He went to my house. My mom made him pancakes.", "gap": 0.3},
    {"id": "stuck", "text": "One accidental hug from her, and he'd be stuck as my mom."},
    {"id": "chase", "text": "I had to swap back. I chased him down the street. He ran.", "gap": 0.3},
    {"id": "ducked", "text": "I hid and jumped out. He ducked."},
    {"id": "bucks", "text": "I offered him a hundred bucks. His bucks. He shrugged."},
    {"id": "truth", "text": "So I did the thing I never wanted to do. I told him the truth."},
    {"id": "loves", "text": "She loves you. But only because she thinks you're me."},
    {"id": "shoes", "text": "He looked at his shoes for a long time. Then he hugged me."},
    {"id": "back", "text": "Pop. I was me again."},
    {"id": "forgot", "text": "Mom was so happy to meet my new friend, she forgot the rule.", "gap": 0.3},
    {"id": "hugged", "text": "She hugged him."},
    {"id": "pop", "text": "Pop.", "gap": 0.3},
    {"id": "isamom", "text": "Now Preston has a mom. Well, he is a mom."},
    {"id": "hottub", "text": "And my mom? She's at the mansion. Trying the hot tub."},
]
TITLES = [("@swap", "@swap.end+0.3", "Swapped!"), ("@pop", "@isamom+1.0", "Swapped again")]

FACES = {
    "Lady": [(0, "love"), ("@rule+1.4", "shocked"), ("@cat", "neutral"), ("@cat+2.6", "happy"), ("@wave", "neutral")],
    "Man": [(0, "neutral"), (0.6, "scared"), ("@flash", "neutral"), ("@cat+2.6", "tired"), ("@wave", "neutral")],
    "TimmyA": [(0, "happy"), ("@trip+1.6", "shocked"), ("@swap+1.4", "angry"), ("@mansion", "smug"), ("@chase+0.6", "grin"),
               ("@ducked", "smug"), ("@bucks+1.6", "smug"), ("@truth", "neutral"), ("@loves", "sad"), ("@shoes+2.2", "crying"),
               ("@back", "grin")],
    "PrestonA": [(0, "smug"), ("@trip+1.6", "shocked"), ("@swap", "scared"), ("@chase", "angry"), ("@ducked", "shocked"),
                 ("@bucks", "neutral"), ("@truth", "sad"), ("@shoes+2.2", "happy"), ("@back", "sad"), ("@back+1.6", "happy")],
    "Mom": [(0, "happy"), ("@mom+1.6", "love"), ("@mom+3.2", "sad"), ("@pancakes", "happy"), ("@stuck", "love"),
            ("@forgot", "grin"), ("@forgot+1.6", "love"), ("@pop", "shocked"), ("@isamom", "scared")],
    "TimmyB": [(0, "happy"), ("@mom+3.0", "scared"), ("@pancakes", "love"), ("@stuck", "shocked"), ("@stuck+1.6", "neutral"),
               ("@forgot", "happy"), ("@pop", "shocked"), ("@isamom+1.4", "grin")],
    "PrestonB": [(0, "happy"), ("@forgot+1.6", "shocked"), ("@pop", "love"), ("@hottub", "grin")],
    "PrestonM": [(0, "shocked"), ("@mansion+1.4", "happy"), ("@butler", "neutral"), ("@butler+1.2", "sad")],
    "Butler": [(0, "neutral")],
}

# objects from other episodes' sets that must stay out of shot (an object with no show spans is hidden)
HIDE = [["Workspace", "Sets", n] for n in ("PaidBench", "SaleChair0", "SaleChair1", "SaleChair2", "SaleChair3", "CarryChair",
                                           "MomChair")] + \
       [["Workspace", "Sets", "ChairMarket", "Sign"], ["Workspace", "Sets", "ChairMarket", "Price"]]
PROPS = [{"path": p, "show": []} for p in HIDE]
FX = [
    {"actor": "Lady", "kind": "sparkle", "show": [["@flash", "@flash.end"]]},
    {"actor": "Man", "kind": "sparkle", "show": [["@flash", "@flash.end"]]},
    {"actor": "TimmyA", "kind": "sparkle", "show": [["@swap", "@swap.end"], ["@back", "@back.end"]]},
    {"actor": "PrestonA", "kind": "sparkle", "show": [["@swap", "@swap.end"], ["@back", "@back.end"]]},
    {"actor": "Mom", "kind": "confetti", "show": [["@pop", "@isamom.end"]]},
    {"actor": "PrestonB", "kind": "confetti", "show": [["@pop", "@isamom.end"]]},
    {"actor": "TimmyB", "kind": "label", "show": [["@me+1.4", "@me.end", "POOREST"]]},
    {"actor": "PrestonA", "kind": "label", "show": [["@trip+1.8", "@trip.end", "RICHEST"]]},
]
MUSIC = {"query": "happy", "pick": 1, "from": 0, "gain": 0.45}
SFX = [("@rule+1.0", "gasp", 0.5), ("@flash+1.6", "pop", 0.7), ("@cat+0.8", "meow", 0.6), ("@cat+3.0", "groan", 0.5),
       ("@team+1.4", "crowd cheer", 0.4), ("@wave", "whistle", 0.4), ("@me", "shop bell", 0.5), ("@mom+1.8", "aww", 0.5),
       ("@trip+1.6", "whoosh", 0.6), ("@swap", "pop", 0.8), ("@mansion+1.0", "echo", 0.4), ("@pancakes+2.0", "sizzle", 0.5),
       ("@stuck+0.4", "gasp", 0.6), ("@chase+0.6", "running footsteps", 0.5), ("@ducked+1.2", "boing", 0.6),
       ("@bucks", "cash register", 0.6), ("@truth", "heartbeat", 0.5), ("@back", "pop", 0.8), ("@forgot", "aww", 0.5),
       ("@pop", "pop", 0.9), ("@isamom+1.0", "record scratch", 0.6), ("@hottub+2.0", "bubbles", 0.5)]
