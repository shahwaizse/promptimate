"""In this town, whoever sits on the golden throne rules everyone - until they stand up. (narration-paced)"""
TITLE = "In This Town, Whoever Sits On The Throne Rules"
VOICE, SPEED = "tv_M2", 1.0
CAPTIONS = {"size": 120, "highlight": False, "max_words": 2}
KEYWORDS = ["throne", "king", "stand", "Preston", "Timmy", "Leo", "ice", "cream"]

# ---- cast: classic blocky characters; one copy of a character per set (characters don't travel between lots)
CAST = [
    # the mansion lawn, the throne (scenes A)
    {"name": "PrestonM", "look": "c_preston", "at": [600, -116], "yaw": 180},
    {"name": "TimmyM", "look": "c_timmy", "at": [600, -142]},
    {"name": "LeoM", "look": "c_kid", "at": [596.5, -142]},
    # town street, in front of the CAFE (B)
    {"name": "TimmyS", "look": "c_timmy", "at": [44, 9]},
    {"name": "LeoS", "look": "c_kid", "at": [56, 9]},
    {"name": "Lady", "look": "c_lady", "at": [47.5, 6]},
    {"name": "Man", "look": "c_man", "at": [51.5, 6]},
    # Timmy's room (C)
    {"name": "TimmyR", "look": "c_timmy", "at": [452, -2]},
]

# shared prompt strings (identical across episodes: repeated prompts are free)
IDLE = "a person stands still, relaxed, looking around"
HAPPY = "a person stands and smiles happily"
SAD = "a person stands alone with their head down, sad"
STARE = "a person stares in surprise"
WALK = "a person walks forward casually"
WALK_SAD = "a person walks forward slowly, tired, head down"
RUN = "a person runs forward excitedly"
JOY = "a person jumps up and down with joy, arms in the air"
FISTS = "a person stands still, watching sadly, then clenches their fists with determination"
DANCE = "a person dances happily, swinging their arms"
BOW = "a person bows deeply"
SING = "a person sings loudly, arms spread wide"
TURN = "a person turns around"
ALARM = "a person waves both arms wildly, shouting"
REACH = "a person reaches forward slowly with their right hand"
BEG = "a person kneels down and begs, hands together"
CONFUSED = "a person stops and looks around, confused"
STAND_UP = "a person stands up quickly"
SIT_DOWN = "a person turns around and sits down"
SIT_SMUG = "a person sits up straight, chin raised, smug"
SIT_LAUGH = "a person sits and laughs, leaning back"
SIT_RELAX = "a person sits and smiles, relaxed"
SIT_SLEEP = "a person sits and sleeps, head drooping"
T = "Throne"

ACTORS = [
    # ---------------------------------------------------------------- A: the mansion lawn
    {"name": "PrestonM", "start": [600, -116], "facing": "-Z", "beats": [
        {"at": 0.0, "prompt": SIT_SMUG, "seconds": 3.5, "sit": T, "sit_from": 0.0},   # already enthroned at t=0 (hook close-up)
        {"prompt": SIT_SMUG, "seconds": 2.5, "sit": T},
        {"prompt": SIT_LAUGH, "seconds": 2.6, "sit": T},
        {"prompt": SIT_SMUG, "seconds": 2.0, "sit": T},
        {"prompt": SIT_RELAX, "seconds": 2.4, "sit": T},
        {"prompt": SIT_SLEEP, "seconds": 2.5, "sit": T},
        {"prompt": SIT_SMUG, "seconds": 2.0, "sit": T},
        {"at": "@rules", "prompt": SIT_RELAX, "seconds": 6.0, "sit": T},
        {"prompt": SIT_RELAX, "seconds": 5.0, "sit": T},
        {"at": "@went", "prompt": SIT_SMUG, "seconds": 2.5, "sit": T},
        {"at": "@alarm+1.2", "prompt": SIT_SMUG, "seconds": 2.0, "sit": T},
        {"at": "@spider+1.5", "prompt": SIT_SMUG, "seconds": 2.0, "sit": T},
        {"at": "@begged+1.0", "prompt": SIT_LAUGH, "seconds": 2.5, "sit": T},
        {"prompt": SIT_RELAX, "seconds": 2.5, "sit": T},
        {"at": "@morning+2.2", "prompt": SIT_SMUG, "seconds": 2.5, "sit": T},
        {"at": "@jumped", "prompt": [STAND_UP, RUN], "seconds": [1.2, 2.3], "to": [605, -138], "via": [[604.5, -124]]},
        {"at": "@notruck", "prompt": CONFUSED, "seconds": 2.5, "face": "TimmyM"},
        {"prompt": SAD, "seconds": 2.5},
        {"at": "@truck+1.0", "prompt": STARE, "seconds": 1.5, "face": "-Z"},
        {"at": "@both+0.8", "prompt": RUN, "seconds": 1.4, "to": [602.5, -146]},
        {"at": "@nobody", "prompt": HAPPY, "seconds": 7.5, "face": "-Z"},
    ]},
    {"name": "TimmyM", "start": [600, -142], "facing": "+Z", "beats": [
        {"at": "@went", "prompt": WALK, "seconds": 2.5, "to": [601.5, -128], "face": "PrestonM"},
        {"at": "@spider", "prompt": REACH, "seconds": 2.0, "face": "PrestonM"},
        {"at": "@begged", "prompt": BEG, "seconds": 2.5, "face": "PrestonM"},
        {"prompt": WALK_SAD, "seconds": 3.0, "to": [600, -150]},
        {"at": "@morning", "prompt": WALK, "seconds": 2.5, "to": [600, -126.5], "face": "PrestonM"},
        {"at": "@bowed", "prompt": BOW, "seconds": 1.6, "face": "PrestonM"},
        {"prompt": [TURN, SING], "seconds": [1.0, 3.0], "face": "-Z"},
        {"at": "@gone", "prompt": WALK, "seconds": 2.0, "to": [600, -116.5], "face": "-Z"},
        {"prompt": [SIT_DOWN, SIT_SMUG], "seconds": [1.5, 3.0], "sit": T, "sit_from": 1.2},
        {"prompt": SIT_RELAX, "seconds": 2.0, "sit": T},
        {"at": "@both", "prompt": [STAND_UP, RUN], "seconds": [1.0, 1.4], "to": [597.5, -146], "via": [[595.5, -124]]},
        {"at": "@nobody", "prompt": HAPPY, "seconds": 7.5, "face": "-Z"},
    ]},
    {"name": "LeoM", "start": [596.5, -142], "facing": "+Z", "beats": [
        {"at": "@went", "prompt": WALK, "seconds": 2.2, "to": [598, -128], "face": "PrestonM"},
        {"at": "@alarm", "prompt": ALARM, "seconds": 2.0, "face": "PrestonM"},
        {"at": "@begged", "prompt": BEG, "seconds": 2.5, "face": "PrestonM"},
        {"prompt": WALK_SAD, "seconds": 3.0, "to": [597, -165]},
    ]},
    # ---------------------------------------------------------------- B: the street
    {"name": "Man", "start": [51.5, 6], "facing": "+Z", "beats": [
        {"at": "@rules", "prompt": [DANCE, STARE], "seconds": [1.4, 1.6]},
        {"at": "@summer", "prompt": SAD, "seconds": 3.0},
        {"at": "@newrules", "prompt": DANCE, "seconds": 4.0},
        {"prompt": DANCE, "seconds": 3.0},
    ]},
    {"name": "Lady", "start": [47.5, 6], "facing": "+Z", "beats": [
        {"at": "@rules", "prompt": SAD, "seconds": 3.0},
        {"at": "@summer", "prompt": STARE, "seconds": 2.5},
        {"at": "@newrules", "prompt": JOY, "seconds": 3.0},
        {"prompt": DANCE, "seconds": 4.0},
    ]},
    {"name": "TimmyS", "start": [44, 9], "facing": "+Z", "beats": [
        {"at": "@rules+1.6", "prompt": BOW, "seconds": 1.5, "face": "-Z"},
        {"at": "@me", "prompt": HAPPY, "seconds": 3.0, "face": "+Z"},
        {"at": "@summer", "prompt": SAD, "seconds": 3.0},
        {"at": "@went", "prompt": WALK, "seconds": 4.0, "to": [24, 9.5]},     # off the cafe front before the party
    ]},
    {"name": "LeoS", "start": [56, 9], "facing": "+Z", "beats": [
        {"at": "@rules+1.6", "prompt": BOW, "seconds": 1.5, "face": "-Z"},
        {"at": "@leo", "prompt": JOY, "seconds": 2.6, "face": "+Z"},
        {"at": "@summer", "prompt": SAD, "seconds": 3.0},
        {"at": "@newrules", "prompt": JOY, "seconds": 3.0},
        {"prompt": DANCE, "seconds": 4.0},
    ]},
    # ---------------------------------------------------------------- C: Timmy's room
    {"name": "TimmyR", "start": [452, -2], "facing": "+Z", "beats": [
        {"at": "@night", "prompt": SAD, "seconds": 3.0},
        {"prompt": FISTS, "seconds": 3.6},
    ]},
]

CAMERAS = [
    # one cue per story moment (the recorder adds coverage cuts and push-ins); fixed shots for sets
    # A: the throne
    {"name": "he sits", "start": 0.0, "subject": "PrestonM", "shot": "close", "angle": 0},
    {"name": "the seat", "start": "@seat", "subject": "PrestonM", "shot": "medium", "angle": 30},
    {"name": "sneeze king", "start": "@shortest", "subject": "PrestonM", "shot": "close", "angle": -20},
    {"name": "three years", "start": "@longest", "subject": "PrestonM", "shot": "low", "angle": 0},
    {"name": "mansion", "start": "@legend", "pos": [600, 24, -235], "look": [600, 15, -110], "fov": 48, "subjects": []},
    {"name": "sleeps there", "start": "@eats", "subject": "PrestonM", "shot": "medium", "angle": 20},
    {"name": "worse rules", "start": "@eats+2.6", "subject": "PrestonM", "shot": "close", "angle": -10},
    # B: the street under Preston's rules
    {"name": "street", "start": "@rules", "pos": [50, 6, 26], "look": [50, 3.5, 5], "fov": 52, "subjects": []},
    {"name": "no dancing", "start": "@rules+0.2", "subject": "Man", "shot": "medium", "angle": 15},
    {"name": "kids bow", "start": "@rules+1.6", "subject": "TimmyS", "with": "LeoS", "shot": "full", "angle": 0},
    {"name": "timmy", "start": "@me", "subject": "TimmyS", "shot": "close", "angle": 15},
    {"name": "leo", "start": "@leo", "subject": "LeoS", "shot": "medium", "angle": 10},
    {"name": "all summer", "start": "@summer", "subject": "TimmyS", "shot": "close", "angle": -15},
    # A: three attempts
    {"name": "to the mansion", "start": "@went", "pos": [600, 8, -152], "look": [600, 4, -120], "fov": 50, "subjects": []},
    {"name": "fire alarm", "start": "@alarm", "subject": "LeoM", "shot": "medium", "angle": 20},
    {"name": "didn't move", "start": "@alarm+1.2", "subject": "PrestonM", "shot": "close", "angle": 10},
    {"name": "spider", "start": "@spider", "subject": "TimmyM", "shot": "medium", "angle": 30},
    {"name": "didn't blink", "start": "@spider+1.5", "subject": "PrestonM", "shot": "close", "angle": -15},
    {"name": "begging", "start": "@begged", "subject": "TimmyM", "with": "LeoM", "shot": "full", "angle": 0},
    {"name": "he laughed", "start": "@begged+1.0", "subject": "PrestonM", "shot": "medium", "angle": 10},
    # C: the room
    {"name": "room", "start": "@night", "pos": [450, 7, 16], "look": [452, 3.5, 0], "fov": 52, "subjects": []},
    {"name": "sing", "start": "@sing", "subject": "TimmyR", "shot": "close", "angle": 0},
    # A: the big moment
    {"name": "walks up", "start": "@morning", "subject": "TimmyM", "shot": "full", "angle": 20},
    {"name": "bow peasant", "start": "@morning+2.2", "subject": "PrestonM", "shot": "close", "angle": 15},
    {"name": "bows", "start": "@bowed", "subject": "TimmyM", "shot": "full", "angle": 30},
    {"name": "sings", "start": "@bowed+1.4", "subject": "TimmyM", "shot": "medium", "angle": -20},
    {"name": "ding ding", "start": "@ding", "subject": "TimmyM", "shot": "close", "angle": 0},
    {"name": "jumps up", "start": "@jumped", "subject": "PrestonM", "with": "TimmyM", "shot": "full", "angle": 15},
    {"name": "empty throne", "start": "@gone", "pos": [600, 8, -140], "look": [600, 5, -117], "fov": 40, "subjects": []},
    {"name": "no truck", "start": "@notruck", "subject": "PrestonM", "shot": "close", "angle": 15},
    {"name": "timmy sits", "start": "@notruck+1.2", "subject": "TimmyM", "shot": "full", "angle": 15},
    # B: King Timmy's rules
    {"name": "party", "start": "@newrules", "pos": [50, 6, 26], "look": [50, 3.5, 5], "fov": 52, "subjects": []},
    {"name": "dancing is back", "start": "@newrules+1.6", "subject": "Man", "shot": "full", "angle": 20},
    # A: the twist
    {"name": "real truck", "start": "@truck", "subject": "TimmyM", "shot": "close", "angle": 10},
    {"name": "timmy runs", "start": "@both", "subject": "TimmyM", "shot": "full", "angle": 30},
    {"name": "preston runs", "start": "@both+0.9", "subject": "PrestonM", "shot": "full", "angle": -20},
    {"name": "nobody king", "start": "@nobody", "subject": "TimmyM", "with": "PrestonM", "shot": "medium", "angle": 10},
]

LINES = [
    {"id": "rule", "text": "In this town, whoever sits on the golden throne rules everyone. Until they stand up."},
    {"id": "seat", "text": "The moment you leave the seat, you're done. Not a king. Just a guy."},
    {"id": "shortest", "text": "The shortest king lasted nine seconds. He stood up to sneeze."},
    {"id": "longest", "text": "The longest? Preston. Three years and counting."},
    {"id": "legend", "text": "In 1998, a king sat so long, they built a mansion around him."},
    {"id": "eats", "text": "Preston eats on the throne. Sleeps on the throne. And his rules get worse every week."},
    {"id": "rules", "text": "No dancing. No ice cream. Every kid bows to the mansion twice a day.", "gap": 0.3},
    {"id": "me", "text": "And me? I'm Timmy. Shortest kid in town. Secretly the loudest singer. Only in the shower."},
    {"id": "leo", "text": "That's Leo, my best friend. He'd do anything for one scoop of ice cream."},
    {"id": "summer", "text": "Then Preston made rule number three hundred. Kids can't go outside. All summer."},
    {"id": "went", "text": "So we went to the mansion to make him stand up.", "gap": 0.3},
    {"id": "alarm", "text": "Leo faked a fire alarm. Preston didn't move."},
    {"id": "spider", "text": "I put a fake spider on the armrest. He didn't blink."},
    {"id": "begged", "text": "We begged on our knees. He laughed."},
    {"id": "night", "text": "That night, I thought of the one thing I never wanted to do.", "gap": 0.3},
    {"id": "sing", "text": "Sing. Out loud. In front of people."},
    {"id": "morning", "text": "Next morning, I walked up to the throne. Preston smirked. Bow, peasant.", "gap": 0.3},
    {"id": "bowed", "text": "So I bowed. Then I turned around and sang the ice cream truck song."},
    {"id": "ding", "text": "Ding ding, ice cream!"},
    {"id": "jumped", "text": "Preston jumped up before his brain could stop him."},
    {"id": "gone", "text": "Three years. Gone in one second."},
    {"id": "notruck", "text": "There was no truck. And I sat down."},
    {"id": "newrules", "text": "Rule one: kids go outside. Rule two: dancing is back.", "gap": 0.3},
    {"id": "truck", "text": "Then, at four o'clock, a real ice cream truck drove by.", "gap": 0.3},
    {"id": "both", "text": "I jumped up. So did Preston."},
    {"id": "nobody", "text": "Now nobody sits on the throne. Turns out, nobody is the best king this town ever had."},
]
TITLES = [("@longest+1.0", "@longest.end+0.3", "3 years. 0 stand-ups."), ("@newrules", "@newrules.end+0.3", "King Timmy")]

FACES = {
    "PrestonM": [(0, "smug"), ("@shortest", "grin"), ("@longest", "smug"), ("@eats", "sleeping"), ("@eats+2.6", "smug"),
                 ("@alarm+1.2", "neutral"), ("@spider+1.5", "smug"), ("@begged+1.0", "grin"), ("@morning+2.2", "smug"),
                 ("@ding", "shocked"), ("@jumped", "happy"), ("@notruck", "shocked"), ("@notruck+1.4", "sad"),
                 ("@truck+1.0", "shocked"), ("@both+0.8", "grin"), ("@nobody", "happy")],
    "TimmyM": [(0, "neutral"), ("@went", "angry"), ("@spider", "scared"), ("@begged", "sad"), ("@morning", "neutral"),
               ("@bowed+1.0", "wink"), ("@ding", "grin"), ("@gone", "shocked"), ("@notruck+1.2", "smug"),
               ("@truck", "shocked"), ("@both", "grin"), ("@nobody", "happy")],
    "LeoM": [(0, "neutral"), ("@alarm", "scared"), ("@begged", "crying")],
    "Man": [(0, "tired"), ("@rules", "happy"), ("@rules+1.4", "scared"), ("@summer", "sad"), ("@newrules", "grin")],
    "Lady": [(0, "sad"), ("@summer", "shocked"), ("@newrules", "happy")],
    "TimmyS": [(0, "sad"), ("@me", "happy"), ("@summer", "shocked"), ("@summer+1.6", "sad")],
    "LeoS": [(0, "sad"), ("@leo", "love"), ("@summer", "crying"), ("@newrules", "grin")],
    "TimmyR": [(0, "sad"), ("@night+2.0", "scared"), ("@sing", "angry")],
}

# objects from other episodes' sets that must stay out of shot (an object with no show spans is hidden)
HIDE = [["Workspace", "Sets", n] for n in ("PaidBench", "SaleChair0", "SaleChair1", "SaleChair2", "SaleChair3", "CarryChair",
                                           "Jar")] + \
       [["Workspace", "Sets", "ChairMarket", "Sign"], ["Workspace", "Sets", "ChairMarket", "Price"],
        ["Workspace", "Sets", "TimmyRoom", "Poster"]]
PROPS = [{"path": p, "show": []} for p in HIDE]
FX = [
    {"actor": "TimmyM", "kind": "sparkle", "show": [["@notruck+1.2", "@notruck.end"]]},
    {"actor": "Man", "kind": "confetti", "show": [["@newrules", "@newrules.end"]]},
    {"actor": "Lady", "kind": "confetti", "show": [["@newrules", "@newrules.end"]]},
    {"actor": "LeoS", "kind": "confetti", "show": [["@newrules", "@newrules.end"]]},
    {"actor": "PrestonM", "kind": "label", "show": [["@rule", "@longest", "KING"], ["@longest", "@longest.end", "3 YEARS"], ["@longest.end", "@jumped", "KING"], ["@jumped", "@notruck.end", "JUST A GUY"]]},
    {"actor": "TimmyM", "kind": "label", "show": [["@notruck+1.2", "@both", "KING"], ["@both", "@nobody.end", "JUST A GUY"]]},
]
MUSIC = {"query": "funny", "pick": 1, "from": 0, "gain": 0.45}
SFX = [("@rule+0.6", "fanfare", 0.5), ("@seat+2.4", "pop", 0.5), ("@shortest+2.0", "sneeze", 0.6), ("@legend", "construction", 0.4),
       ("@eats+1.4", "snore", 0.5), ("@rules+0.6", "record scratch", 0.6), ("@summer+2.0", "door slam", 0.6),
       ("@alarm", "fire alarm", 0.5), ("@spider", "boing", 0.5), ("@begged+1.2", "laugh", 0.5), ("@night", "crickets", 0.4),
       ("@ding", "ice cream truck", 0.7), ("@jumped", "whoosh", 0.6), ("@notruck+1.2", "fanfare", 0.6),
       ("@newrules", "cheer", 0.5), ("@truck", "ice cream truck", 0.7), ("@both", "whoosh", 0.6), ("@nobody+2.0", "boom", 0.4)]
