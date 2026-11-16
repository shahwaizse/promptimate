"""In this town, every time you say I'm fine, a rain cloud follows you until you tell the truth. (narration-paced)"""
TITLE = "In This Town, Saying I'm Fine Makes It Rain On You"
VOICE, SPEED = "tv_M2", 1.6
CAPTIONS = {"size": 66, "highlight": False, "max_words": 3}
KEYWORDS = ["fine", "cloud", "rain", "thunder", "Timmy", "Mom", "Preston", "bakery", "snowing"]

# ---- cast: classic blocky characters; one copy of a character per set (characters don't travel between lots)
CAST = [
    # town street, in front of the BAKERY / BOOKS shopfronts (A)
    {"name": "Kid", "look": "c_kid", "at": [-30, 7]},
    {"name": "Man", "look": "c_man", "at": [-24.5, 5], "yaw": 90},
    {"name": "Lady", "look": "c_lady", "at": [-28, 4.5], "yaw": -90},
    {"name": "Mayor", "look": "c_butler", "at": [-34, 10], "yaw": -90},
    # the bakery (B)
    {"name": "Mom", "look": "c_mom", "at": [352, -7.5]},
    {"name": "TimmyB", "look": "c_timmy", "at": [349, 1.5], "yaw": 180},
    {"name": "PrestonB", "look": "c_preston", "at": [354, 16], "yaw": 180},
    {"name": "Worker", "look": "c_worker", "at": [345, 16], "yaw": 180},
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
LAUGH = "a person laughs hard, bending over and holding their stomach"
TALK = "a person stands and talks, gesturing with both hands"
GIVE = "a person holds out both hands, offering something"
SHRUG = "a person shrugs"
WAVE = "a person waves with their right hand"
NOD = "a person nods slowly"
WIPE = "a person stands behind a counter, working, wiping the counter"
SHOCK_BACK = "a person turns and steps back in surprise, arms down at their sides"
BACK_ACHE = "a person stands still and stretches their back, tired"
DUCK = "a person ducks down quickly"
LOOK_UP = "a person looks up at the sky, worried"

ACTORS = [
    # ---------------------------------------------------------------- A: the street
    {"name": "Kid", "start": [-30, 7], "facing": "+Z", "beats": [
        {"at": 0.0, "prompt": IDLE, "seconds": 3.0},
        {"at": "@pop", "prompt": LOOK_UP, "seconds": 2.6},
        {"prompt": SAD, "seconds": 3.0},
        {"at": "@honest", "prompt": IDLE, "seconds": 4.0},
    ]},
    {"name": "Man", "start": [-24.5, 5], "facing": "-X", "beats": [
        {"at": 0.4, "prompt": IDLE, "seconds": 3.0, "face": "+Z"},
        {"at": "@small+1.6", "prompt": SHOCK_BACK, "seconds": 2.2},
        {"prompt": LOOK_UP, "seconds": 2.4},
        {"at": "@honest+1.4", "prompt": BACK_ACHE, "seconds": 2.4, "face": "Lady"},
        {"prompt": TALK, "seconds": 2.4, "face": "Lady"},
    ]},
    {"name": "Lady", "start": [-28, 4.5], "facing": "+X", "beats": [
        {"at": "@honest", "prompt": TALK, "seconds": 1.8, "face": "Man"},
        {"prompt": NOD, "seconds": 2.0, "face": "Man"},
        {"prompt": HAPPY, "seconds": 3.0, "face": "Man"},
    ]},
    {"name": "Mayor", "start": [-34, 10], "facing": "+X", "beats": [
        {"at": "@mayor", "prompt": WALK_SAD, "seconds": 3.0, "to": [-31, 10.5]},
        {"prompt": LOOK_UP, "seconds": 2.6},
        {"prompt": SAD, "seconds": 3.0},
    ]},
    # ---------------------------------------------------------------- B: the bakery
    {"name": "Mom", "start": [352, -7.5], "facing": "+Z", "beats": [
        {"at": "@mom", "prompt": WIPE, "seconds": 3.0},
        {"prompt": LOOK_UP, "seconds": 2.0},
        {"at": "@ask+1.2", "prompt": HAPPY, "seconds": 1.6, "face": "TimmyB"},
        {"prompt": LOOK_UP, "seconds": 2.0},
        {"at": "@soggy", "prompt": WIPE, "seconds": 2.5},
        {"prompt": SAD, "seconds": 3.0},
        {"at": "@breakfast+1.0", "prompt": NOD, "seconds": 1.8, "face": "TimmyB"},
        {"at": "@detector+1.2", "prompt": SHOCK_BACK, "seconds": 2.0},
        {"prompt": NOD, "seconds": 1.6, "face": "TimmyB"},
        {"at": "@voice+1.6", "prompt": SHRUG, "seconds": 1.6, "face": "TimmyB"},
        {"at": "@cloud", "prompt": STARE, "seconds": 2.6, "face": "TimmyB"},
        {"at": "@dropped", "prompt": TALK, "seconds": 3.0, "face": "TimmyB"},
        {"prompt": TALK, "seconds": 2.6, "face": "TimmyB"},
        {"at": "@sun", "prompt": JOY, "seconds": 3.0},
        {"at": "@line", "prompt": HAPPY, "seconds": 3.0, "face": "Worker"},
        {"at": "@preston+1.0", "prompt": STARE, "seconds": 2.2, "face": "PrestonB"},
        {"at": "@snow", "prompt": SHRUG, "seconds": 1.6, "face": "TimmyB"},
        {"prompt": HAPPY, "seconds": 3.0, "face": "PrestonB"},
    ]},
    {"name": "TimmyB", "start": [349, 1.5], "facing": "-Z", "beats": [
        {"at": "@me", "prompt": WAVE, "seconds": 1.8, "face": "+Z"},
        {"prompt": HAPPY, "seconds": 2.4, "face": "+Z"},
        {"at": "@ask", "prompt": TALK, "seconds": 1.6, "face": "Mom"},
        {"prompt": SAD, "seconds": 2.4, "face": "Mom"},
        {"at": "@fix", "prompt": FISTS, "seconds": 3.0, "face": "Mom"},
        {"at": "@breakfast", "prompt": GIVE, "seconds": 2.0, "face": "Mom"},
        {"prompt": SAD, "seconds": 1.6, "face": "Mom"},
        {"at": "@detector", "prompt": GIVE, "seconds": 1.4, "face": "Mom"},
        {"prompt": SHOCK_BACK, "seconds": 2.0},
        {"at": "@voice", "prompt": DUCK, "seconds": 2.6, "face": "Mom"},
        {"at": "@card", "prompt": FISTS, "seconds": 3.0, "face": "Mom"},
        {"at": "@said", "prompt": TALK, "seconds": 1.6, "face": "Mom"},
        {"at": "@cloud", "prompt": LOOK_UP, "seconds": 2.4},
        {"at": "@scared", "prompt": SAD, "seconds": 2.6, "face": "Mom"},
        {"at": "@truth", "prompt": NOD, "seconds": 2.0, "face": "Mom"},
        {"at": "@sun", "prompt": JOY, "seconds": 3.0},
        {"prompt": HAPPY, "seconds": 3.0, "face": "Mom"},
        {"at": "@preston+1.0", "prompt": STARE, "seconds": 2.2, "face": "PrestonB"},
        {"at": "@twist", "prompt": SHRUG, "seconds": 1.6, "face": "+Z"},
    ]},
    {"name": "Worker", "start": [345, 16], "facing": "-Z", "beats": [
        {"at": "@line", "prompt": WALK, "seconds": 2.4, "to": [345.5, 4.5], "face": "Mom"},
        {"prompt": HAPPY, "seconds": 3.0, "face": "Mom"},
        {"at": "@snow", "prompt": LAUGH, "seconds": 2.6},
        {"prompt": HAPPY, "seconds": 3.0, "face": "PrestonB"},
    ]},
    {"name": "PrestonB", "start": [354, 16], "facing": "-Z", "beats": [
        {"at": "@preston", "prompt": WALK, "seconds": 2.2, "to": [353.5, 4.5], "face": "Mom"},
        {"prompt": SMUG, "seconds": 3.0},
        {"at": "@snow", "prompt": LOOK_UP, "seconds": 2.4},
        {"prompt": SMUG, "seconds": 4.0},
    ]},
]

CAMERAS = [
    # one cue per story moment (the recorder adds coverage cuts and push-ins); fixed shots for sets
    # A: the street, the rule
    {"name": "rule", "start": 0.0, "subject": "Man", "shot": "medium", "angle": 20},
    {"name": "pop", "start": "@pop", "subject": "Kid", "shot": "close", "angle": 15},
    {"name": "drizzle", "start": "@small", "subject": "Kid", "shot": "medium", "angle": -20},
    {"name": "thunder", "start": "@small+1.6", "subject": "Man", "shot": "close", "angle": 10},
    {"name": "mayor", "start": "@mayor", "subject": "Mayor", "shot": "full", "angle": 30},
    {"name": "boat", "start": "@mayor+3.2", "subject": "Mayor", "shot": "close", "angle": -15},
    {"name": "the street", "start": "@honest", "pos": [-28, 6, 26], "look": [-28, 3.5, 5], "fov": 52, "subjects": []},
    {"name": "back hurts", "start": "@honest+1.4", "subject": "Man", "with": "Lady", "shot": "full", "angle": 0},
    # B: the bakery
    {"name": "bakery", "start": "@me", "pos": [350, 7, 18], "look": [351, 4, -5], "fov": 52, "subjects": []},
    {"name": "timmy", "start": "@me+1.2", "subject": "TimmyB", "shot": "close", "angle": 10},
    {"name": "mom", "start": "@mom", "subject": "Mom", "shot": "medium", "angle": 20},
    {"name": "raining", "start": "@mom.end-1.4", "subject": "Mom", "shot": "close", "angle": -10},
    {"name": "every morning", "start": "@ask", "subject": "TimmyB", "with": "Mom", "shot": "medium", "angle": 0},
    {"name": "pours", "start": "@ask.end-1.0", "subject": "Mom", "shot": "close", "angle": 15},
    {"name": "soggy", "start": "@soggy", "pos": [350, 6, 20], "look": [351, 4, 2], "fov": 46, "subjects": []},
    {"name": "fix it", "start": "@fix", "subject": "TimmyB", "shot": "close", "angle": -15},
    {"name": "breakfast", "start": "@breakfast", "subject": "TimmyB", "with": "Mom", "shot": "full", "angle": 0},
    {"name": "splash", "start": "@breakfast.end-1.0", "subject": "Mom", "shot": "close", "angle": 20},
    {"name": "toaster", "start": "@detector", "subject": "TimmyB", "shot": "medium", "angle": 25},
    {"name": "thunder again", "start": "@detector.end-1.0", "subject": "Mom", "shot": "close", "angle": -15},
    {"name": "deep voice", "start": "@voice", "subject": "TimmyB", "shot": "full", "angle": 30},
    {"name": "hail", "start": "@voice.end-1.0", "subject": "Mom", "shot": "close", "angle": 10},
    {"name": "last card", "start": "@card", "subject": "TimmyB", "shot": "close", "angle": 0},
    {"name": "i'm fine", "start": "@said", "subject": "TimmyB", "with": "Mom", "shot": "medium", "angle": 0},
    {"name": "my cloud", "start": "@cloud", "subject": "TimmyB", "shot": "close", "angle": 20},
    {"name": "scared", "start": "@scared", "subject": "TimmyB", "shot": "close", "angle": -10},
    {"name": "she stares", "start": "@dropped", "subject": "Mom", "shot": "close", "angle": 15},
    {"name": "the truth", "start": "@truth", "subject": "Mom", "with": "TimmyB", "shot": "medium", "angle": 0},
    {"name": "sunshine", "start": "@sun", "pos": [350, 7, 18], "look": [351, 4, -5], "fov": 52, "subjects": []},
    {"name": "the line", "start": "@line", "subject": "Worker", "shot": "full", "angle": 20},
    {"name": "preston", "start": "@preston", "subject": "PrestonB", "shot": "full", "angle": 20},
    {"name": "he's fine", "start": "@preston.end-1.4", "subject": "PrestonB", "shot": "close", "angle": 10},
    {"name": "snow", "start": "@snow", "subject": "PrestonB", "shot": "medium", "angle": -20},
    {"name": "still fine", "start": "@twist", "subject": "PrestonB", "shot": "close", "angle": -10},
]

LINES = [
    {"id": "rule", "text": "In this town, every time you say I'm fine, a rain cloud follows you until you tell the truth."},
    {"id": "pop", "text": "Say it, and pop. A little gray cloud, raining on you. Only you."},
    {"id": "small", "text": "A small fib gets you drizzle. I'm totally fine? Thunder."},
    {"id": "mayor", "text": "In 1998, the mayor said it at his own wedding. It rained on him for three weeks. The town built him a boat."},
    {"id": "honest", "text": "So here, nobody lies. How are you? My back hurts and I hate Mondays."},
    {"id": "me", "text": "And me? I'm Timmy. And I'm actually fine. Every single day.", "gap": 0.3},
    {"id": "mom", "text": "That's my mom. Best bread in town. And for forty-one days, it's been raining on her."},
    {"id": "ask", "text": "Every morning I ask how she is. She smiles. I'm fine. And it pours."},
    {"id": "soggy", "text": "The bread got soggy. The customers stopped coming."},
    {"id": "fix", "text": "If she won't tell me what's wrong, I can't fix it."},
    {"id": "breakfast", "text": "I made her breakfast. Thank you, sweetie. I'm fine. Splash.", "gap": 0.3},
    {"id": "detector", "text": "I built a lie detector out of a toaster. It caught fire. I'm fine. Thunder."},
    {"id": "voice", "text": "I hid behind the counter and asked in a deep voice. I'm fine, Timmy. Hail."},
    {"id": "card", "text": "So I did the one thing I had never done in my life. I lied.", "gap": 0.3},
    {"id": "said", "text": "Mom, I'm fine."},
    {"id": "cloud", "text": "Pop. A cloud. Over me. For the very first time."},
    {"id": "scared", "text": "Because I wasn't fine. I was scared for her."},
    {"id": "dropped", "text": "She stared at my little cloud. And finally, she told me the truth."},
    {"id": "truth", "text": "The bakery was broke. She was scared too."},
    {"id": "sun", "text": "Both clouds vanished. And the sun came out. Inside the bakery."},
    {"id": "line", "text": "Word got out. Next morning, half the town lined up for sunny bread."},
    {"id": "preston", "text": "Then Preston walked in. Richest kid in town. He looked around and said, I'm fine.", "gap": 0.3},
    {"id": "snow", "text": "It started snowing."},
    {"id": "twist", "text": "That was three days ago. He's still standing there. Still snowing. Still fine."},
]
TITLES = [("@mom.end-1.6", "@mom.end+0.3", "41 days of rain"), ("@said", "@said.end+0.4", "\"I'm fine.\"")]

FACES = {
    "Kid": [(0, "neutral"), ("@pop", "shocked"), ("@pop+2.0", "sad"), ("@small", "tired"), ("@honest", "neutral")],
    "Man": [(0, "smug"), ("@small+1.6", "shocked"), ("@small+3.4", "scared"), ("@honest+1.4", "tired"), ("@honest+3.4", "angry")],
    "Lady": [(0, "neutral"), ("@honest", "happy"), ("@honest+2.0", "grin")],
    "Mayor": [(0, "happy"), ("@mayor+1.4", "shocked"), ("@mayor+3.0", "sad"), ("@mayor.end-1.2", "tired")],
    "Mom": [(0, "happy"), ("@mom", "happy"), ("@mom.end-1.6", "sad"), ("@ask+1.2", "happy"), ("@ask.end-1.0", "tired"),
            ("@soggy", "sad"), ("@breakfast+1.0", "happy"), ("@breakfast.end-0.6", "tired"), ("@detector+1.2", "shocked"),
            ("@detector.end-0.8", "tired"), ("@voice+1.6", "happy"), ("@voice.end-0.6", "sad"), ("@cloud", "shocked"),
            ("@dropped+1.6", "crying"), ("@truth", "sad"), ("@sun", "grin"), ("@line", "happy"), ("@preston+1.0", "shocked"),
            ("@snow", "smug")],
    "TimmyB": [(0, "happy"), ("@me+2.6", "grin"), ("@ask", "happy"), ("@ask.end-1.0", "sad"), ("@fix", "angry"),
               ("@breakfast", "happy"), ("@breakfast.end-0.6", "sad"), ("@detector", "grin"), ("@detector+1.6", "scared"),
               ("@voice", "smug"), ("@voice.end-0.6", "tired"), ("@card", "neutral"), ("@said", "happy"), ("@cloud", "shocked"),
               ("@scared", "sad"), ("@dropped+1.6", "crying"), ("@sun", "grin"), ("@line", "happy"), ("@preston+1.0", "shocked"),
               ("@twist", "smug")],
    "Worker": [(0, "happy"), ("@snow", "grin"), ("@snow+2.6", "happy")],
    "PrestonB": [(0, "smug"), ("@preston.end-0.8", "happy"), ("@snow", "shocked"), ("@snow.end", "smug"), ("@twist+1.6", "tired")],
}

# objects from other episodes' sets that must stay out of shot (an object with no show spans is hidden)
HIDE = [["Workspace", "Sets", n] for n in ("PaidBench", "SaleChair0", "SaleChair1", "SaleChair2", "SaleChair3", "CarryChair",
                                           "MomChair")] + \
       [["Workspace", "Sets", "ChairMarket", "Sign"], ["Workspace", "Sets", "ChairMarket", "Price"]]
PROPS = [{"path": p, "show": []} for p in HIDE]
MUSIC = {"query": "funny", "pick": 1, "from": 0, "gain": 0.45}
SFX = [("@rule+1.2", "thunder", 0.5), ("@pop+0.3", "pop", 0.7), ("@pop+1.0", "rain", 0.4), ("@small+1.8", "thunder", 0.6),
       ("@mayor+1.4", "wedding bells", 0.4), ("@mayor.end-1.0", "boat horn", 0.6), ("@honest+1.6", "groan", 0.5),
       ("@me", "shop bell", 0.5), ("@ask.end-0.8", "rain", 0.6), ("@soggy+0.6", "squish", 0.6), ("@breakfast.end-0.6", "splash", 0.7),
       ("@detector+1.2", "fire", 0.5), ("@detector.end-0.6", "thunder", 0.6), ("@voice.end-0.6", "hail", 0.6),
       ("@card", "heartbeat", 0.5), ("@cloud", "pop", 0.8), ("@dropped+1.6", "sad violin", 0.4), ("@sun", "choir", 0.5),
       ("@line", "crowd cheer", 0.4), ("@preston+1.6", "door bell", 0.5), ("@snow", "wind", 0.6), ("@twist.end-0.8", "record scratch", 0.6)]
