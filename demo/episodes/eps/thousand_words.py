"""In this world, you're born with exactly 1,000 words. Use them up and you're silent forever. (narration-paced)"""
TITLE = "In This World, You Only Get 1,000 Words"
VOICE, SPEED = "tv_M2", 1.0
CAPTIONS = {"size": 80, "highlight": False, "max_words": 3}
KEYWORDS = ["words", "thousand", "silent", "Timmy", "Mom", "Preston", "Leo", "birthday"]

# ---- cast: classic blocky characters; one copy of a character per set (characters don't travel between lots)
CAST = [
    # town street, in front of the CAFE (scene A)
    {"name": "Lady", "look": "c_lady", "at": [46, 6], "yaw": -90},
    {"name": "Man", "look": "c_man", "at": [49, 6], "yaw": 90},
    {"name": "Timmy", "look": "c_timmy", "at": [41, 10], "yaw": -90},
    {"name": "Preston", "look": "c_preston", "at": [53.5, 9.5], "yaw": 90},
    {"name": "Leo", "look": "c_kid", "at": [52, 5.5]},
    # the bakery (B)
    {"name": "Mom", "look": "c_mom", "at": [352, -7.5]},
    {"name": "TimmyB", "look": "c_timmy", "at": [347.5, 3], "yaw": 180},
    # Timmy's room (C)
    {"name": "TimmyC", "look": "c_timmy", "at": [456, -4.5], "yaw": 180},
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
TALK = "a person stands and talks, gesturing with both hands"
GIVE = "a person holds out both hands, offering something"
NOD = "a person nods slowly"
SHRUG = "a person shrugs"
WAVE = "a person waves with their right hand"
STOMP = "a person stomps their foot down hard"
ANGRY = "a person stands shaking with anger, fists clenched"
NERVOUS = "a person stands still, holding their breath, nervous"
POINT = "a person points forward sternly"
WIPE = "a person stands behind a counter, working, wiping the counter"
SHOCK_BACK = "a person turns and steps back in surprise, arms down at their sides"
COUNT = "a person stands and counts something on the table, concentrating"

ACTORS = [
    # ---------------------------------------------------------------- A: the street
    {"name": "Lady", "start": [46, 6], "facing": "+X", "beats": [
        {"at": 0.0, "prompt": TALK, "seconds": 4.0, "face": "Man"},
        {"prompt": TALK, "seconds": 3.0, "face": "Man"},
        {"at": "@hi", "prompt": STARE, "seconds": 2.5},
        {"prompt": IDLE, "seconds": 3.0},
        {"at": "@bodies+2.6", "prompt": SHRUG, "seconds": 2.0},
        {"prompt": IDLE, "seconds": 4.0, "face": "+Z"},
        {"at": "@dumb", "prompt": STARE, "seconds": 2.5, "face": "Timmy"},
    ]},
    {"name": "Man", "start": [49, 6], "facing": "-X", "beats": [
        {"at": 0.0, "prompt": NOD, "seconds": 2.0, "face": "Lady"},
        {"prompt": IDLE, "seconds": 2.0, "face": "Lady"},
        {"at": "@hi", "prompt": WAVE, "seconds": 2.0, "face": "Lady"},
        {"prompt": IDLE, "seconds": 4.0},
        {"at": "@bodies+1.6", "prompt": NOD, "seconds": 2.0},
        {"prompt": IDLE, "seconds": 4.0, "face": "+Z"},
        {"at": "@dumb", "prompt": STARE, "seconds": 2.5, "face": "Timmy"},
    ]},
    {"name": "Timmy", "start": [41, 10], "facing": "+X", "beats": [
        {"at": "@me", "prompt": WALK, "seconds": 2.5, "to": [50.5, 10], "face": "+Z"},
        {"prompt": HAPPY, "seconds": 2.5, "face": "+Z"},
        {"at": "@found", "prompt": IDLE, "seconds": 3.0, "face": "Preston"},
        {"at": "@shoe", "prompt": STARE, "seconds": 1.6, "face": "Preston"},
        {"at": "@mute", "prompt": FISTS, "seconds": 2.6, "face": "Preston"},
        {"at": "@dumb", "prompt": SAD, "seconds": 3.0, "face": "Leo"},
        {"at": "@scream", "prompt": ANGRY, "seconds": 1.7, "face": "Preston"},
        {"at": "@away", "prompt": WALK_SAD, "seconds": 3.0, "to": [62, 11.5]},
    ]},
    {"name": "Preston", "start": [53.5, 9.5], "facing": "-X", "beats": [
        {"at": "@found", "prompt": TALK, "seconds": 3.0, "face": "Timmy"},
        {"at": "@shoe", "prompt": STOMP, "seconds": 1.8, "face": "Timmy"},
        {"at": "@mute", "prompt": LAUGH_AT, "seconds": 2.5, "face": "Timmy"},
        {"at": "@dumb", "prompt": TALK, "seconds": 3.5, "face": "+Z"},
        {"prompt": SMUG, "seconds": 4.0, "face": "Timmy"},
    ]},
    {"name": "Leo", "start": [52, 5.5], "facing": "+Z", "beats": [
        {"at": "@dumb+1.8", "prompt": STARE, "seconds": 2.5, "face": "Timmy"},
        {"prompt": SHRUG, "seconds": 2.0, "face": "Timmy"},
    ]},
    # ---------------------------------------------------------------- B: the bakery
    {"name": "Mom", "start": [352, -7.5], "facing": "+Z", "beats": [
        {"at": "@mom", "prompt": WIPE, "seconds": 3.0},
        {"prompt": WAVE, "seconds": 1.8, "face": "TimmyB"},
        {"prompt": HAPPY, "seconds": 2.0, "face": "TimmyB"},
        {"prompt": SAD, "seconds": 3.0},
        {"at": "@midnight", "prompt": WIPE, "seconds": 2.5},
        {"at": "@gave", "prompt": SHOCK_BACK, "seconds": 2.0},
        {"prompt": STARE, "seconds": 1.8, "face": "TimmyB"},
        {"at": "@said", "prompt": TALK, "seconds": 2.6, "face": "TimmyB"},
        {"at": "@clean", "prompt": POINT, "seconds": 1.4, "face": "TimmyB"},
        {"at": "@laughed", "prompt": LAUGH, "seconds": 2.6},
        {"prompt": HAPPY, "seconds": 7.5, "face": "TimmyB"},
    ]},
    {"name": "TimmyB", "start": [347.5, 3], "facing": "-Z", "beats": [
        {"at": "@mom", "prompt": HAPPY, "seconds": 3.0, "face": "Mom"},
        {"prompt": WAVE, "seconds": 1.8, "face": "Mom"},
        {"prompt": SAD, "seconds": 3.0, "face": "Mom"},
        {"at": "@found", "prompt": WALK, "seconds": 3.0, "to": [350, 16]},
        {"at": "@midnight", "prompt": WALK, "seconds": 2.0, "to": [351, 1.5], "face": "Mom"},
        {"prompt": GIVE, "seconds": 2.0, "face": "Mom"},
        {"at": "@mouth", "prompt": STARE, "seconds": 2.5, "face": "Mom"},
        {"at": "@breath", "prompt": NERVOUS, "seconds": 1.4, "face": "Mom"},
        {"at": "@laughed", "prompt": JOY, "seconds": 3.0},
        {"prompt": HAPPY, "seconds": 7.5, "face": "Mom"},
    ]},
    # ---------------------------------------------------------------- C: Timmy's room
    {"name": "TimmyC", "start": [456, -4.5], "facing": "-Z", "beats": [
        {"at": "@loophole", "prompt": COUNT, "seconds": 3.0},
        {"prompt": NOD, "seconds": 2.0, "face": "+Z"},
        {"prompt": JOY, "seconds": 2.6, "face": "+Z"},
        {"at": "@never", "prompt": SAD, "seconds": 4.5, "face": "+Z"},
    ]},
]

CAMERAS = [
    # one cue per story moment (the recorder adds coverage cuts and push-ins); fixed shots for sets
    # A: the street
    {"name": "talking", "start": 0.0, "subject": "Lady", "shot": "close", "angle": 0},
    {"name": "click", "start": "@click", "subject": "Lady", "with": "Man", "shot": "medium", "angle": 0},
    {"name": "hi", "start": "@hi", "subject": "Man", "shot": "medium", "angle": 20},
    {"name": "wedding", "start": "@hi+1.4", "subject": "Lady", "shot": "close", "angle": -15},
    {"name": "the street", "start": "@weather", "pos": [52, 6, 26], "look": [52, 3.5, 5], "fov": 52, "subjects": []},
    {"name": "nod", "start": "@bodies+1.6", "subject": "Man", "shot": "close", "angle": 10},
    {"name": "shrug", "start": "@bodies+2.6", "subject": "Lady", "shot": "medium", "angle": -20},
    {"name": "timmy", "start": "@me", "subject": "Timmy", "shot": "full", "angle": 30},
    {"name": "all thousand", "start": "@me+2.4", "subject": "Timmy", "shot": "close", "angle": 0},
    # B: the bakery
    {"name": "bakery", "start": "@mom", "pos": [350, 7, 18], "look": [351, 4, -5], "fov": 52, "subjects": []},
    {"name": "mom", "start": "@mom+1.2", "subject": "Mom", "shot": "close", "angle": 20},
    {"name": "named me", "start": "@name", "subject": "Mom", "with": "TimmyB", "shot": "medium", "angle": 0},
    {"name": "not once", "start": "@since", "subject": "TimmyB", "shot": "close", "angle": 10},
    # C: Timmy's room
    {"name": "room", "start": "@loophole", "pos": [450, 7, 16], "look": [452, 3.5, 0], "fov": 52, "subjects": []},
    {"name": "at once", "start": "@once", "subject": "TimmyC", "shot": "close", "angle": 30},
    {"name": "tomorrow", "start": "@tomorrow", "subject": "TimmyC", "shot": "full", "angle": 10},
    # A again: Preston
    {"name": "preston", "start": "@found", "subject": "Preston", "shot": "medium", "angle": -15},
    {"name": "shoe", "start": "@shoe", "subject": "Preston", "with": "Timmy", "shot": "full", "angle": 0},
    {"name": "fists", "start": "@mute", "subject": "Timmy", "shot": "close", "angle": 15},
    {"name": "whole street", "start": "@dumb", "subject": "Preston", "shot": "medium", "angle": 20},
    {"name": "leo looks", "start": "@dumb+2.0", "subject": "Leo", "shot": "close", "angle": 10},
    {"name": "scream", "start": "@scream", "subject": "Timmy", "shot": "close", "angle": -10},
    {"name": "walks away", "start": "@away", "track": "Timmy", "offset": [3, 1.6, 8], "aim": [0, 1, 0], "fov": 40},
    # C again
    {"name": "never speak", "start": "@never", "subject": "TimmyC", "shot": "close", "angle": 0},
    # B again: midnight
    {"name": "midnight", "start": "@midnight", "pos": [350, 6, 20], "look": [351, 4, 2], "fov": 46, "subjects": []},
    {"name": "the gift", "start": "@gave", "subject": "TimmyB", "with": "Mom", "shot": "medium", "angle": 0},
    {"name": "her mouth", "start": "@mouth", "subject": "Mom", "shot": "close", "angle": 15},
    {"name": "she said", "start": "@said", "subject": "Mom", "shot": "medium", "angle": -20},
    {"name": "held breath", "start": "@breath", "subject": "TimmyB", "shot": "close", "angle": 10},
    {"name": "clean your room", "start": "@clean", "subject": "Mom", "shot": "close", "angle": 0},
    {"name": "she laughs", "start": "@laughed", "subject": "Mom", "shot": "close", "angle": 10},
    {"name": "timmy grins", "start": "@laughed+1.6", "subject": "TimmyB", "shot": "close", "angle": -15},
    {"name": "984", "start": "@left", "subject": "Mom", "with": "TimmyB", "shot": "medium", "angle": 0},   # holds on both faces to the end
]

LINES = [
    {"id": "rule", "text": "In this world, you're born with exactly one thousand words. Use them up, and you're silent forever."},
    {"id": "click", "text": "Every word you say makes a tiny click in your throat. Click. Click. Click."},
    {"id": "hi", "text": "Saying hi costs one word. A wedding speech? Three hundred."},
    {"id": "weather", "text": "In 2004, a weatherman talked so fast he ran out by Tuesday."},
    {"id": "bodies", "text": "So people here talk with their bodies. A nod means yes. A shrug means whatever."},
    {"id": "me", "text": "And me? I'm Timmy. I haven't said a single word in ten years. I still have all one thousand."},
    {"id": "mom", "text": "That's my mom. She used her last word the day I was born.", "gap": 0.3},
    {"id": "name", "text": "She used it to name me."},
    {"id": "since", "text": "She hasn't spoken since. Not once."},
    {"id": "loophole", "text": "But there's one loophole. On someone's birthday, you can give them all your words.", "gap": 0.3},
    {"id": "once", "text": "All of them. At once. If you've used even one, it doesn't work."},
    {"id": "tomorrow", "text": "Mom's birthday is tomorrow."},
    {"id": "found", "text": "Then Preston found out. His dad buys him extra words. Fifty thousand of them.", "gap": 0.3},
    {"id": "shoe", "text": "He stepped on my shoe. I said nothing."},
    {"id": "mute", "text": "He called my mom a mute. I clenched my fists. Nothing."},
    {"id": "dumb", "text": "He told the whole street I'm silent because I'm dumb. Even Leo looked at me funny."},
    {"id": "scream", "text": "I wanted to scream. Just one word."},
    {"id": "away", "text": "I walked away."},
    {"id": "never", "text": "Because once I give them away, I'll never speak. Ever. Not even to say I love you.", "gap": 0.3},
    {"id": "midnight", "text": "At midnight, I walked into the bakery. I held out my hands.", "gap": 0.3},
    {"id": "gave", "text": "And gave her all one thousand."},
    {"id": "mouth", "text": "She opened her mouth. For the first time in ten years."},
    {"id": "said", "text": "Timmy, she said. I've waited ten years to tell you this."},
    {"id": "breath", "text": "I held my breath."},
    {"id": "clean", "text": "Clean your room.", "gap": 0.4},
    {"id": "laughed", "text": "Then she laughed so hard she cried. And said, I love you."},
    {"id": "left", "text": "Nine hundred and eighty-four words left. She's saving every one for me."},
]
TITLES = [("@me+2.6", "@me.end+0.3", "Timmy: 1,000 words left"), ("@left", "@left.end+0.4", "Mom: 984 words left")]

FACES = {
    "Lady": [(0, "happy"), ("@click", "neutral"), ("@hi+1.4", "shocked"), ("@weather", "neutral"), ("@bodies+2.6", "tired"),
             ("@dumb", "sad")],
    "Man": [(0, "neutral"), ("@hi", "happy"), ("@weather", "neutral"), ("@bodies+1.6", "happy"), ("@dumb", "shocked")],
    "Timmy": [(0, "neutral"), ("@me+1.0", "happy"), ("@found", "neutral"), ("@shoe", "shocked"), ("@mute", "angry"),
              ("@dumb", "sad"), ("@scream", "angry"), ("@away", "sad")],
    "Preston": [(0, "smug"), ("@found", "grin"), ("@shoe", "angry"), ("@mute", "grin"), ("@dumb", "smug")],
    "Leo": [(0, "neutral"), ("@dumb+1.8", "shocked"), ("@dumb+3.6", "sad")],
    "Mom": [(0, "tired"), ("@mom+3.0", "happy"), ("@since", "sad"), ("@midnight", "tired"), ("@gave", "shocked"),
            ("@said", "happy"), ("@clean", "smug"), ("@laughed", "grin"), ("@left", "love")],
    "TimmyB": [(0, "happy"), ("@since", "sad"), ("@midnight", "neutral"), ("@gave", "happy"), ("@mouth", "shocked"),
               ("@breath", "scared"), ("@clean", "shocked"), ("@laughed", "grin"), ("@left", "love")],
    "TimmyC": [(0, "neutral"), ("@once", "scared"), ("@tomorrow", "grin"), ("@never", "sad")],
}

# objects from other episodes' sets that must stay out of shot (an object with no show spans is hidden)
HIDE = [["Workspace", "Sets", n] for n in ("PaidBench", "SaleChair0", "SaleChair1", "SaleChair2", "SaleChair3", "CarryChair",
                                           "Jar", "MomChair")] + \
       [["Workspace", "Sets", "ChairMarket", "Sign"], ["Workspace", "Sets", "ChairMarket", "Price"],
        ["Workspace", "Sets", "TimmyRoom", "Poster"]]
PROPS = [{"path": p, "show": []} for p in HIDE]
FX = [
    {"actor": "Mom", "kind": "sparkle", "show": [["@gave", "@mouth.end"]]},
    {"actor": "Mom", "kind": "hearts", "show": [["@laughed", "@left.end"]]},
    {"actor": "Timmy", "kind": "label", "show": [["@me+2.4", "@me.end", "1000 WORDS"]]},
    {"actor": "Mom", "kind": "label", "show": [["@mom+1.2", "@since.end", "0 WORDS"], ["@gave", "@mouth.end", "1000 WORDS"], ["@left", "@left.end", "984 WORDS"]]},
    {"actor": "Preston", "kind": "label", "show": [["@found", "@found.end", "50K WORDS"]]},
]
MUSIC = {"query": "piano", "pick": 0, "from": 0, "gain": 0.45}
SFX = [("@click+2.6", "click", 0.7), ("@click+3.0", "click", 0.7), ("@click+3.4", "click", 0.7), ("@hi", "pop", 0.5),
       ("@weather+1.0", "radio static", 0.5), ("@me", "whoosh", 0.4), ("@mom", "shop bell", 0.5), ("@loophole", "magic", 0.5),
       ("@shoe+0.4", "stomp", 0.6), ("@mute", "gasp", 0.5), ("@scream", "heartbeat", 0.6), ("@gave", "magic chime", 0.7),
       ("@mouth", "gasp", 0.5), ("@clean", "record scratch", 0.7), ("@laughed", "laugh", 0.5), ("@left", "aww", 0.5)]
