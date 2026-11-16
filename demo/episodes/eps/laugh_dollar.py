"""In this world, if you laugh at someone, you owe them a dollar. (craftee-style story episode, narration-paced)"""
TITLE = "In This World, Laughing At Someone Costs A Dollar"
VOICE, SPEED = "tv_M2", 1.6
CAPTIONS = {"size": 66, "highlight": False, "max_words": 3}
KEYWORDS = ["laugh", "dollar", "Timmy", "Preston", "Leo", "bakery", "free", "clown"]

# ---- cast: classic blocky characters; one copy of a character per set (characters don't travel between lots)
CAST = [
    # town street, in front of the BAKERY / BOOKS shopfronts (scenes A and D)
    {"name": "Timmy", "look": "c_timmy", "at": [-32, 10.5], "yaw": -90},
    {"name": "Preston", "look": "c_preston", "at": [-21, 8], "yaw": 90},
    {"name": "Leo", "look": "c_kid", "at": [-30, 7]},
    {"name": "Mom", "look": "c_mom", "at": [-28.5, 2.5]},
    {"name": "Lady", "look": "c_lady", "at": [-34, 6.5], "yaw": -90},
    {"name": "Man", "look": "c_man", "at": [-24.5, 5]},
    # Timmy's room (B)
    {"name": "TimmyR", "look": "c_timmy", "at": [456, -4.5], "yaw": 180},
    # Preston's mansion lawn, the throne (C)
    {"name": "PrestonM", "look": "c_preston", "at": [600, -116], "yaw": 180},
    {"name": "TimmyM", "look": "c_timmy", "at": [600, -132]},
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
TRIP = "a person trips and falls forward onto the ground"
GETUP = "a person gets up from the ground"
SLIP = "a person slips and falls backward onto the ground"
DANCE_BAD = "a person dances clumsily like a robot, arms stiff"
BOW = "a person bows deeply"
TOSS = "a person tosses something forward with their right hand"
GIVE = "a person holds out both hands, offering something"
NOD = "a person nods slowly"
WASH = "a person wipes something in front of them in big circles"
HOLD_LAUGH = "a person stands stiffly, shaking, trying not to laugh"
SHOCK_BACK = "a person turns and steps back in surprise, arms down at their sides"
COUNT = "a person stands and counts something on the table, concentrating"
SIT_DOWN = "a person turns around and sits down"
SIT_SMUG = "a person sits up straight, chin raised, smug"
SIT_LAUGH = "a person sits and laughs, leaning back"
STAND_SHOCK = "a person stands up suddenly in shock"
SIT_GROUND = "a person sits down on the ground"
SIT_GROUND_SAD = "a person sits on the ground, head down, sad"
SIT_GROUND_TALK = "a person sits on the ground and talks, gesturing with both hands"
SIT_GROUND_LAUGH = "a person sits on the ground and laughs"
SIT_GROUND_HAPPY = "a person sits on the ground, relaxed and happy"

ACTORS = [
    # ---------------------------------------------------------------- A + D: the street
    {"name": "Man", "start": [-24.5, 5], "facing": "-X", "beats": [
        {"at": 0.0, "prompt": TRIP, "seconds": 2.5},
        {"prompt": GETUP, "seconds": 2.0},
        {"prompt": HAPPY, "seconds": 3.0, "face": "Lady"},
        {"prompt": IDLE, "seconds": 6.0, "face": "+Z"},
        {"at": "@cent", "prompt": LAUGH, "seconds": 3.0},
        {"prompt": HAPPY, "seconds": 4.0},
    ]},
    {"name": "Lady", "start": [-34, 6.5], "facing": "+X", "beats": [
        {"at": 0.6, "prompt": LAUGH_AT, "seconds": 2.6, "face": "Man"},
        {"prompt": STARE, "seconds": 2.5},
        {"prompt": SAD, "seconds": 4.0},
        {"prompt": IDLE, "seconds": 5.0, "face": "+Z"},
        {"at": "@cent", "prompt": LAUGH, "seconds": 3.0},
        {"prompt": HAPPY, "seconds": 4.0},
    ]},
    {"name": "Timmy", "start": [-32, 10.5], "facing": "+X", "beats": [
        {"at": "@me", "prompt": WALK, "seconds": 2.0, "to": [-28, 10.5]},
        {"prompt": TRIP, "seconds": 2.5},
        {"prompt": GETUP, "seconds": 2.0, "face": "Preston"},
        {"prompt": SAD, "seconds": 3.0, "face": "Preston"},
        {"at": "@lemonade", "prompt": GIVE, "seconds": 1.5, "face": "+Z"},
        {"prompt": WASH, "seconds": 1.6, "face": "+Z"},
        {"prompt": WALK, "seconds": 1.5, "to": [-23.5, 8.5], "face": "Preston"},
        {"prompt": GIVE, "seconds": 2.0, "face": "Preston"},
        {"prompt": SAD, "seconds": 3.0, "face": "Preston"},
        {"at": "@found", "prompt": WALK, "seconds": 2.4, "to": [-24.2, 12], "face": "+Z"},
        {"prompt": SIT_GROUND, "seconds": 2.5},
        {"prompt": SIT_GROUND_TALK, "seconds": 2.5},
        {"prompt": SIT_GROUND_LAUGH, "seconds": 3.0},
        {"prompt": SIT_GROUND_HAPPY, "seconds": 6.0},
    ]},
    {"name": "Preston", "start": [-21, 8], "facing": "-X", "beats": [
        {"at": "@preston", "prompt": SMUG, "seconds": 2.0},
        {"prompt": LAUGH_AT, "seconds": 2.2, "face": "Timmy"},
        {"prompt": TOSS, "seconds": 1.6, "face": "Timmy"},
        {"prompt": SMUG, "seconds": 3.0},
        {"at": "@loan+0.8", "prompt": LAUGH, "seconds": 2.2, "face": "Timmy"},
        {"prompt": TOSS, "seconds": 1.5, "face": "Timmy"},
        {"at": "@show", "prompt": WALK_SAD, "seconds": 3.0, "to": [-22, 12], "face": "+Z"},
        {"prompt": SIT_GROUND, "seconds": 3.0},
        {"prompt": SIT_GROUND_SAD, "seconds": 6.0},
        {"at": "@found", "prompt": SIT_GROUND_SAD, "seconds": 3.0},
        {"at": "@laughed", "prompt": SIT_GROUND_LAUGH, "seconds": 3.0},
        {"prompt": SIT_GROUND_HAPPY, "seconds": 6.0},
    ]},
    {"name": "Leo", "start": [-30, 7], "facing": "+Z", "beats": [
        {"at": "@leo", "prompt": HOLD_LAUGH, "seconds": 3.5},
        {"prompt": IDLE, "seconds": 4.0},
        {"at": "@found", "prompt": WALK, "seconds": 2.0, "to": [-27.5, 11], "face": "Timmy"},
        {"at": "@leo_laughs", "prompt": LAUGH, "seconds": 3.0},
        {"prompt": JOY, "seconds": 3.0},
        {"prompt": HAPPY, "seconds": 3.0},
    ]},
    {"name": "Mom", "start": [-28.5, 2.5], "facing": "+Z", "beats": [
        {"at": "@letter", "prompt": SHOCK_BACK, "seconds": 3.0},
        {"prompt": SAD, "seconds": 4.0},
        {"at": "@cent", "prompt": LAUGH, "seconds": 3.0},
        {"prompt": HAPPY, "seconds": 4.0},
    ]},
    # ---------------------------------------------------------------- B: Timmy's room
    {"name": "TimmyR", "start": [456, -4.5], "facing": "-Z", "beats": [
        {"at": "@night", "prompt": COUNT, "seconds": 2.4},
        {"prompt": FISTS, "seconds": 3.6, "face": "+Z"},
        {"prompt": NOD, "seconds": 2.0, "face": "+Z"},
    ]},
    # ---------------------------------------------------------------- C: Preston's mansion, the show
    {"name": "PrestonM", "start": [600, -116], "facing": "-Z", "beats": [
        {"at": "@night", "prompt": [SIT_DOWN, SIT_SMUG], "seconds": [1.5, 5.0], "sit": "Throne", "sit_from": 1.2},
        {"at": "@robot+1.0", "prompt": SIT_LAUGH, "seconds": 2.4, "sit": "Throne"},
        {"prompt": SIT_LAUGH, "seconds": 2.4, "sit": "Throne"},
        {"prompt": SIT_LAUGH, "seconds": 2.4, "sit": "Throne"},
        {"at": "@saved", "prompt": STAND_SHOCK, "seconds": 2.5},
        {"prompt": SAD, "seconds": 3.0},
    ]},
    {"name": "TimmyM", "start": [600, -132], "facing": "+Z", "beats": [
        {"at": "@show", "prompt": BOW, "seconds": 1.6, "face": "PrestonM"},
        {"at": "@robot", "prompt": DANCE_BAD, "seconds": 2.8, "face": "PrestonM"},
        {"prompt": SLIP, "seconds": 2.4},
        {"prompt": GETUP, "seconds": 1.6, "face": "PrestonM"},
        {"prompt": [BOW, TRIP], "seconds": [1.4, 2.0], "face": "PrestonM"},
        {"prompt": GETUP, "seconds": 2.0, "face": "PrestonM"},
        {"prompt": JOY, "seconds": 3.0},
    ]},
]

CAMERAS = [
    # one cue per story moment (the recorder adds coverage cuts and push-ins); fixed shots for sets
    # A: the street
    {"name": "man trips", "start": 0.0, "subject": "Man", "shot": "full", "angle": 20},
    {"name": "lady laughs", "start": "@rule+1.4", "subject": "Lady", "shot": "medium", "angle": 15},
    {"name": "dollar jumps", "start": "@pocket", "subject": "Lady", "with": "Man", "shot": "full", "angle": 0},
    {"name": "giggle", "start": "@giggle", "subject": "Lady", "shot": "close", "angle": -20},
    {"name": "the street", "start": "@clown", "pos": [-28, 6, 26], "look": [-28, 3.5, 5], "fov": 52, "subjects": []},
    {"name": "straight faces", "start": "@nobody", "subject": "Man", "shot": "close", "angle": 10},
    {"name": "timmy trips", "start": "@me", "subject": "Timmy", "shot": "full", "angle": 35},
    {"name": "preston", "start": "@preston", "subject": "Preston", "shot": "close", "angle": -15},
    {"name": "tosses a dollar", "start": "@tosses", "subject": "Preston", "with": "Timmy", "shot": "full", "angle": 0},
    {"name": "leo", "start": "@leo", "subject": "Leo", "shot": "medium", "angle": 10},
    {"name": "mom's letter", "start": "@letter", "subject": "Mom", "shot": "close", "angle": 15},
    {"name": "ten thousand", "start": "@pay", "subject": "Mom", "shot": "medium", "angle": -25},
    {"name": "lemonade", "start": "@lemonade", "subject": "Timmy", "shot": "medium", "angle": 20},
    {"name": "cars", "start": "@cars", "subject": "Timmy", "shot": "full", "angle": -30},
    {"name": "the loan", "start": "@loan", "subject": "Timmy", "with": "Preston", "shot": "full", "angle": 0},
    # B: Timmy's room
    {"name": "room", "start": "@night", "pos": [450, 7, 16], "look": [452, 3.5, 0], "fov": 52, "subjects": []},
    {"name": "counting", "start": "@night+1.3", "subject": "TimmyR", "shot": "medium", "angle": 40},
    {"name": "swore", "start": "@swore", "subject": "TimmyR", "shot": "close", "angle": 10},
    {"name": "on purpose", "start": "@purpose", "subject": "TimmyR", "shot": "close", "angle": -20},
    # C: the mansion
    {"name": "mansion", "start": "@show", "pos": [600, 24, -235], "look": [600, 15, -110], "fov": 48, "subjects": []},
    {"name": "robot dance", "start": "@robot", "subject": "TimmyM", "shot": "full", "angle": 25},
    {"name": "snort", "start": "@robot+1.6", "subject": "PrestonM", "shot": "medium", "angle": 10},
    {"name": "slip", "start": "@slip", "subject": "TimmyM", "shot": "full", "angle": -30},
    {"name": "cried laughing", "start": "@slip+1.3", "subject": "PrestonM", "shot": "close", "angle": 15},
    {"name": "bow and fall", "start": "@bow", "subject": "TimmyM", "shot": "full", "angle": 40},
    {"name": "47 minutes", "start": "@straight", "subject": "PrestonM", "shot": "medium", "angle": -10},
    {"name": "ten thousand twelve", "start": "@twelve", "subject": "TimmyM", "with": "PrestonM", "shot": "full", "angle": 0},
    {"name": "broke", "start": "@saved", "subject": "PrestonM", "shot": "close", "angle": 20},
    # D: the street again
    {"name": "on the sidewalk", "start": "@found", "subject": "Preston", "shot": "full", "angle": 20},
    {"name": "the joke", "start": "@sat", "subject": "Timmy", "with": "Preston", "shot": "full", "angle": 0},
    {"name": "he laughed", "start": "@laughed", "subject": "Preston", "shot": "close", "angle": -15},
    {"name": "i laughed", "start": "@laughed+0.7", "subject": "Timmy", "shot": "close", "angle": 15},
    {"name": "leo laughs", "start": "@leo_laughs", "subject": "Leo", "shot": "medium", "angle": 10},
    {"name": "whole street", "start": "@cent", "pos": [-26, 6, 26], "look": [-26, 3, 7], "fov": 52, "subjects": []},
    {"name": "free", "start": "@free", "subject": "Timmy", "with": "Preston", "shot": "medium", "angle": 0},
]

LINES = [
    {"id": "rule", "text": "In this world, if you laugh at someone, you owe them a dollar."},
    {"id": "pocket", "text": "Laugh, and a dollar jumps out of your pocket, straight into theirs."},
    {"id": "giggle", "text": "A giggle costs one dollar. A real belly laugh? Fifty."},
    {"id": "clown", "text": "In 2019, a clown moved to town. By lunch, he owned the bank."},
    {"id": "nobody", "text": "So nobody here laughs. Not at weddings. Not at cartoons. Never."},
    {"id": "me", "text": "And me? I'm Timmy. I trip about forty times a day."},
    {"id": "preston", "text": "This is Preston. Richest kid in town."},
    {"id": "tosses", "text": "He laughs at me every day, then tosses me a dollar like it's nothing."},
    {"id": "leo", "text": "That's Leo, my best friend. Loudest laugh in the world. He's held it in for six years."},
    {"id": "letter", "text": "Then Mom's bakery got a letter.", "gap": 0.3},
    {"id": "pay", "text": "Pay ten thousand dollars by Friday, or it closes. Forever."},
    {"id": "lemonade", "text": "I sold lemonade. Eleven dollars."},
    {"id": "cars", "text": "I washed cars. Twenty-three."},
    {"id": "loan", "text": "I asked Preston for a loan. He laughed in my face. One dollar."},
    {"id": "night", "text": "That night, I counted it all. Thirty-five dollars.", "gap": 0.3},
    {"id": "swore", "text": "So I decided to do the one thing I swore I'd never do."},
    {"id": "purpose", "text": "Let people laugh at me. On purpose."},
    {"id": "show", "text": "Thursday, I put on a show at Preston's mansion.", "gap": 0.3},
    {"id": "robot", "text": "I danced like a broken robot. Preston snorted. Five dollars."},
    {"id": "slip", "text": "I slipped on nothing. He cried laughing. Two hundred."},
    {"id": "bow", "text": "I bowed and fell flat on my face."},
    {"id": "straight", "text": "He laughed for forty-seven minutes straight."},
    {"id": "twelve", "text": "Ten thousand and twelve dollars."},
    {"id": "saved", "text": "The bakery was saved. And Preston was broke."},
    {"id": "found", "text": "Next day, I found him sitting on the sidewalk.", "gap": 0.3},
    {"id": "sat", "text": "So I sat down next to him and told him the dumbest joke I know."},
    {"id": "laughed", "text": "He laughed. I laughed."},
    {"id": "leo_laughs", "text": "And Leo laughed for the first time in six years."},
    {"id": "cent", "text": "Nobody paid a cent."},
    {"id": "free", "text": "Turns out, laughing at someone costs a dollar. Laughing with them is free."},
]
TITLES = [("@pay", "@pay.end+0.3", "$10,000 by Friday"), ("@twelve", "@twelve.end+0.4", "$10,012")]

FACES = {
    "Man": [(0, "shocked"), (2.5, "tired"), ("@pocket", "grin"), ("@clown", "neutral"), ("@cent", "grin")],
    "Lady": [(0, "neutral"), (0.6, "grin"), ("@pocket", "shocked"), ("@giggle", "sad"), ("@clown", "neutral"), ("@cent", "happy")],
    "Timmy": [(0, "neutral"), ("@me+1.4", "shocked"), ("@preston", "sad"), ("@lemonade", "happy"), ("@cars", "tired"),
              ("@loan", "scared"), ("@loan+1.2", "sad"), ("@found", "neutral"), ("@sat", "happy"), ("@laughed", "grin")],
    "Preston": [(0, "smug"), ("@tosses", "grin"), ("@tosses+2.0", "smug"), ("@loan+0.8", "grin"), ("@show", "sad"),
                ("@found", "crying"), ("@laughed", "grin"), ("@free", "happy")],
    "Leo": [(0, "neutral"), ("@leo+1.0", "scared"), ("@leo.end", "neutral"), ("@found", "sad"), ("@leo_laughs", "grin")],
    "Mom": [(0, "happy"), ("@letter", "shocked"), ("@pay", "crying"), ("@cent", "grin")],
    "TimmyR": [(0, "tired"), ("@swore", "sad"), ("@purpose", "angry"), ("@purpose.end", "smug")],
    "PrestonM": [(0, "smug"), ("@robot+1.0", "grin"), ("@slip+1.3", "crying"), ("@straight", "grin"), ("@saved", "shocked"),
                 ("@saved+1.8", "sad")],
    "TimmyM": [(0, "happy"), ("@robot", "grin"), ("@slip", "shocked"), ("@bow+1.4", "tired"), ("@twelve", "shocked"),
               ("@saved", "grin")],
}

# objects from other episodes' sets that must stay out of shot (an object with no show spans is hidden)
HIDE = [["Workspace", "Sets", n] for n in ("PaidBench", "SaleChair0", "SaleChair1", "SaleChair2", "SaleChair3", "CarryChair")] + \
       [["Workspace", "Sets", "ChairMarket", "Sign"], ["Workspace", "Sets", "ChairMarket", "Price"],
        ["Workspace", "Sets", "TimmyRoom", "Poster"]]
PROPS = [{"path": p, "show": []} for p in HIDE] + [
    {"path": ["Workspace", "Sets", "Jar"], "show": [[0, 999]]},          # the money jar on Timmy's desk
]
FX = [
    {"actor": "Man", "kind": "sparkle", "show": [["@pocket", "@pocket.end"]]},
    {"actor": "TimmyM", "kind": "sparkle", "show": [["@robot+1.6", "@twelve.end"]]},
    {"actor": "Leo", "kind": "confetti", "show": [["@leo_laughs", "@leo_laughs.end"]]},
    {"actor": "Timmy", "kind": "hearts", "show": [["@free", "@free.end"]]},
    {"actor": "Mom", "kind": "label", "show": [["@pay", "@pay.end", "$10K DUE"]]},
    {"actor": "Timmy", "kind": "label", "show": [["@lemonade", "@cars", "$11"], ["@cars", "@loan", "$34"], ["@loan", "@loan.end", "$35"]]},
    {"actor": "TimmyM", "kind": "label", "show": [["@twelve", "@saved", "$10,012"]]},
    {"actor": "PrestonM", "kind": "label", "show": [["@saved", "@saved.end", "BROKE"]]},
]
MUSIC = {"query": "funny", "pick": 0, "from": 0, "gain": 0.45}
SFX = [("@rule+0.9", "laugh", 0.5), ("@pocket+0.6", "coin", 0.7), ("@clown+0.4", "clown horn", 0.6), ("@me+2.0", "thud", 0.6),
       ("@tosses+2.4", "coin", 0.6), ("@letter+0.5", "gasp", 0.6), ("@pay+0.2", "boom", 0.5), ("@loan+1.4", "coin", 0.6),
       ("@night+1.5", "coins", 0.6), ("@purpose", "whoosh", 0.5), ("@robot+1.6", "pop", 0.6), ("@slip+0.3", "slip", 0.6),
       ("@bow+1.2", "thud", 0.7), ("@twelve", "cash register", 0.7), ("@saved+1.6", "sad trombone", 0.5),
       ("@laughed", "laugh", 0.5), ("@cent", "cheer", 0.5)]
