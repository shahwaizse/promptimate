"""In this world, sitting down costs money. (craftee-style story episode: several sets, faces, props, title cards)"""
TITLE = "In This World, Sitting Down Costs Money"
LENGTH = 83.0
VOICE, SPEED = "tv_M2", 1.35
KEYWORDS = ["PRESTON", "PRESTON.", "FREE", "FREE.", "MONEY", "TIMMY", "MOM"]
CAPTIONS = {"size": 66, "highlight": False, "max_words": 3}

# ---- cast: classic blocky characters; one copy of a character per set (characters don't travel between lots)
CAST = [
    # town street (scenes A and F)
    {"name": "Preston", "look": "c_preston", "at": [-16, 8], "yaw": -90},
    {"name": "Lady", "look": "c_lady", "at": [-6, 6]},
    {"name": "Man", "look": "c_man", "at": [5, 6.5]},
    {"name": "Worker", "look": "c_worker", "at": [8, 3.5]},
    {"name": "Kid", "look": "c_kid", "at": [-3.5, 9.5]},
    {"name": "TimmyF", "look": "c_timmy", "at": [14, 10]},
    # bakery (B, E)
    {"name": "Mom", "look": "c_mom", "at": [352, -7.5]},
    {"name": "TimmyB", "look": "c_timmy", "at": [347, 10]},
    {"name": "TimmyE", "look": "c_timmy", "at": [350, 16]},
    # Timmy's room (C)
    {"name": "TimmyC", "look": "c_timmy", "at": [456, -4.5]},
    # Preston's chair market (D)
    {"name": "PrestonD", "look": "c_preston", "at": [600, -116]},
    {"name": "TimmyD", "look": "c_timmy", "at": [600, -142]},
]

TIRED = "a person stands still, exhausted, shifting their weight"
ACTORS = [
    # ---------------------------------------------------------------- A + F: the street
    {"name": "Preston", "start": [-16, 8], "facing": "+X", "beats": [
        {"at": 5.8, "prompt": ["a person walks forward proudly", "a person turns around and sits down"], "seconds": [3.0, 2.0],
         "sit": "Bench", "sit_from": 3.6},
        {"prompt": "a person sits and leans back, relaxing smugly", "seconds": 4.0, "sit": "Bench"},
        {"at": 74.5, "prompt": "a person stands up suddenly in shock", "seconds": 2.5},
        {"prompt": "a person stands alone with their head down, sad", "seconds": 5.0},
    ]},
    {"name": "Lady", "start": [-6, 6], "facing": "+Z", "beats": [
        {"at": 0.0, "prompt": TIRED, "seconds": 8.0},
        {"at": 70.0, "prompt": "a person stares in surprise", "seconds": 2.5, "face": "TimmyF"},
        {"prompt": "a person sits down on the ground", "seconds": 3.0},
        {"prompt": "a person sits on the ground, relaxed and happy", "seconds": 6.0},
    ]},
    {"name": "Man", "start": [5, 6.5], "facing": "+Z", "beats": [
        {"at": 0.0, "prompt": "a person stands still and stretches their back, tired", "seconds": 8.0},
        {"at": 70.0, "prompt": "a person stares in surprise", "seconds": 2.5, "face": "TimmyF"},
        {"at": 73.5, "prompt": "a person sits down on the ground", "seconds": 3.0},
        {"prompt": "a person sits on the ground, relaxed and happy", "seconds": 6.0},
    ]},
    {"name": "Worker", "start": [8, 3.5], "facing": "-X", "beats": [
        {"at": 0.0, "prompt": "a person stands still, rubbing their leg, tired", "seconds": 8.0},
        {"at": 70.0, "prompt": "a person stares in surprise", "seconds": 2.5, "face": "TimmyF"},
        {"at": 74.5, "prompt": "a person sits down on the ground", "seconds": 3.0},
        {"prompt": "a person sits on the ground, relaxed and happy", "seconds": 5.0},
    ]},
    {"name": "Kid", "start": [-3.5, 9.5], "facing": "+Z", "beats": [
        {"at": 0.0, "prompt": TIRED, "seconds": 8.0},
        {"at": 70.0, "prompt": "a person stares in surprise", "seconds": 2.5, "face": "TimmyF"},
        {"prompt": "a person sits down on the ground excitedly", "seconds": 3.0},
        {"prompt": "a person sits on the ground and claps happily", "seconds": 6.0},
    ]},
    {"name": "TimmyF", "start": [14, 10], "facing": "-X", "beats": [
        {"at": 64.0, "prompt": "a person walks forward slowly, tired, head down", "seconds": 3.0, "to": [9, 8.5]},
        {"prompt": "a person sits down on the ground", "seconds": 3.0},
        {"prompt": "a person sits on the ground and looks around", "seconds": 6.0},
        {"prompt": "a person sits on the ground, smiling", "seconds": 7.0},
    ]},
    # ---------------------------------------------------------------- B + E: the bakery
    {"name": "Mom", "start": [352, -7.5], "facing": "+Z", "beats": [
        {"at": 14.0, "prompt": "a person stands behind a counter, working, wiping the counter", "seconds": 3.0},
        {"prompt": "a person stands still, exhausted, shoulders slumped", "seconds": 3.0},
        {"prompt": "a person stands with their legs trembling, exhausted", "seconds": 3.5},
        {"prompt": TIRED, "seconds": 3.5},
        {"at": 52.0, "prompt": "a person turns and steps back in surprise, arms down at their sides", "seconds": 3.0},
        {"prompt": ["a person turns around and sits down slowly", "a person sits with their hands resting on their lap, smiling happily"],
         "seconds": [2.5, 4.0], "sit": "MomChair", "sit_from": 2.2},
        {"prompt": "a person sits and smiles, relaxed", "seconds": 4.0, "sit": "MomChair"},
    ]},
    {"name": "TimmyB", "start": [347, 10], "facing": "-Z", "beats": [
        {"at": 23.4, "prompt": "a person stands still, watching sadly, then clenches their fists with determination",
         "seconds": 3.6, "face": "Mom"},
    ]},
    {"name": "TimmyE", "start": [350, 16], "facing": "-Z", "beats": [
        {"at": 51.5, "prompt": "a person walks forward carrying something heavy in both arms", "seconds": 3.0, "to": [351, 1.5],
         "face": "Mom"},
        {"prompt": "a person stands and presents something proudly with both hands", "seconds": 3.0, "face": "Mom"},
        {"prompt": "a person stands and smiles happily", "seconds": 4.0, "face": "Mom"},
    ]},
    # ---------------------------------------------------------------- C: Timmy's room
    {"name": "TimmyC", "start": [456, -4.5], "facing": "-Z", "beats": [
        {"at": 27.0, "prompt": "a person stands and drops coins into a jar on the table with their right hand", "seconds": 4.0},
        {"prompt": "a person stands and counts something on the table, concentrating", "seconds": 3.0},
        {"prompt": "a person jumps up and down with joy, arms in the air", "seconds": 3.0, "face": "+Z"},
        {"prompt": "a person runs forward excitedly", "seconds": 3.0, "to": [450, 12]},
    ]},
    # ---------------------------------------------------------------- D: Preston's chair market
    {"name": "PrestonD", "start": [600, -116], "facing": "-Z", "beats": [
        {"at": 40.0, "prompt": ["a person turns around and sits down", "a person sits up straight, chin raised, smug"],
         "seconds": [1.5, 4.0], "sit": "Throne", "sit_from": 1.2},
        {"prompt": "a person sits and reaches out a hand to take something", "seconds": 3.0, "sit": "Throne"},
        {"prompt": "a person sits and laughs, leaning back", "seconds": 4.0, "sit": "Throne"},
    ]},
    {"name": "TimmyD", "start": [600, -142], "facing": "+Z", "beats": [
        {"at": 42.5, "prompt": "a person walks forward nervously, holding something in both hands", "seconds": 3.5,
         "to": [600, -123], "face": "PrestonD"},
        {"prompt": "a person holds out both hands, offering something", "seconds": 3.0, "face": "PrestonD"},
        {"prompt": "a person turns around and walks away carrying something heavy in both arms, happy", "seconds": 3.5,
         "to": [600, -140]},
    ]},
]

CAMERAS = [
    # shots of characters are framed from where they really are (subject/shot/angle); sets and signs are fixed shots
    # A: the street. Paid benches, Preston sits.
    {"name": "price sign", "start": 0.0, "pos": [-0.5, 5.6, 7], "look": [-0.5, 5.2, 0.2], "fov": 34, "subjects": []},
    {"name": "everyone stands", "start": 3.2, "pos": [1, 6, 22], "look": [0, 3.5, 5], "fov": 50, "subjects": []},
    {"name": "preston arrives", "start": 6.0, "track": "Preston", "offset": [3, 1.6, 9], "aim": [0, 1, 0], "fov": 40},
    {"name": "preston sits", "start": 9.0, "subject": "Preston", "shot": "full", "angle": 15},
    {"name": "smug close", "start": 11.3, "subject": "Preston", "shot": "close", "angle": -20},
    # B: the bakery
    {"name": "bakery wide", "start": 14.0, "pos": [350, 7, 18], "look": [351, 4, -5], "fov": 52, "subjects": []},
    {"name": "mom tired", "start": 17.0, "subject": "Mom", "shot": "close", "angle": 20},
    {"name": "trembling", "start": 20.0, "subject": "Mom", "shot": "medium", "angle": -35},
    {"name": "timmy watches", "start": 23.4, "subject": "TimmyB", "shot": "close", "angle": 10},
    # C: Timmy's room
    {"name": "coins", "start": 27.0, "subject": "TimmyC", "shot": "medium", "angle": 30},
    {"name": "jar close", "start": 29.3, "pos": [459.8, 5.0, -5.6], "look": [456, 3.7, -7.4], "fov": 30, "subjects": []},
    {"name": "counting", "start": 31.0, "subject": "TimmyC", "shot": "close", "angle": 55},
    {"name": "joy", "start": 34.0, "subject": "TimmyC", "shot": "full", "angle": 10},
    {"name": "runs out", "start": 37.0, "pos": [450, 7, 16], "look": [452, 3.5, 0], "fov": 52, "subjects": []},
    # D: Preston's chair market
    {"name": "mansion", "start": 40.0, "pos": [600, 24, -235], "look": [600, 15, -110], "fov": 48, "subjects": []},
    {"name": "timmy walks up", "start": 42.5, "subject": "TimmyD", "shot": "full", "angle": 30},
    {"name": "throne", "start": 44.5, "subject": "PrestonD", "shot": "medium", "angle": 10},
    {"name": "the deal", "start": 46.0, "subject": "TimmyD", "with": "PrestonD", "shot": "full", "angle": 0},
    {"name": "carries chair", "start": 49.0, "subject": "TimmyD", "shot": "full", "angle": 25},
    # E: back at the bakery
    {"name": "enters", "start": 51.5, "pos": [350, 6, 20], "look": [351, 4, 2], "fov": 46, "subjects": []},
    {"name": "mom shocked", "start": 53.0, "subject": "Mom", "shot": "close", "angle": 15},
    {"name": "she sits", "start": 55.0, "subject": "Mom", "shot": "full", "angle": 30},
    {"name": "happy tears", "start": 58.5, "subject": "Mom", "shot": "close", "angle": -20},
    {"name": "timmy smiles", "start": 61.0, "subject": "TimmyE", "shot": "close", "angle": 10},
    # F: the street again. The twist.
    {"name": "nothing left", "start": 64.0, "track": "TimmyF", "offset": [0, 1.8, 9], "aim": [0, 1.2, 0], "fov": 40},
    {"name": "on the ground", "start": 67.0, "subject": "TimmyF", "shot": "full", "angle": 30},
    {"name": "they stare", "start": 70.0, "pos": [10, 4.2, 10], "look": [0, 4, 6], "fov": 58, "subjects": []},
    {"name": "everyone sits", "start": 72.5, "pos": [2, 6, 21], "look": [1, 2, 6], "fov": 54, "subjects": []},
    {"name": "town on the ground", "start": 76.0, "pos": [0, 12, 24], "look": [0, 1, 4], "fov": 56, "subjects": []},
    {"name": "only one standing", "start": 79.0, "subject": "Preston", "shot": "close", "angle": 15},
]

LINES = [
    (0.3, "In this world, sitting down costs money."),
    (3.4, "Every bench charges by the minute."),
    (6.2, "So most people just stand. Everyone except Preston."),
    (10.4, "He owns every chair in town."),
    (14.2, "Timmy's mom works at the bakery."),
    (17.2, "Twelve hours a day. Standing."),
    (20.2, "She hadn't sat down in three years."),
    (23.6, "So Timmy made a promise."),
    (27.2, "Every coin he found went in the jar."),
    (31.2, "Two years later..."),
    (34.2, "he finally had enough."),
    (40.2, "There was only one place to buy a chair."),
    (43.0, "Preston's."),
    (46.2, "It cost every coin he had."),
    (52.2, "Happy birthday, Mom."),
    (55.2, "For the first time in three years... she sat down."),
    (64.2, "But Timmy had nothing left."),
    (67.2, "So he sat down... on the ground."),
    (70.2, "Nobody had ever tried that."),
    (72.8, "The ground was free."),
    (76.2, "By morning, nobody in town paid to sit ever again."),
    (79.4, "And Preston? He's the only one still standing."),
]
TITLES = [(27.0, 29.2, "Day 1"), (31.0, 33.6, "2 years later")]

FACES = {
    "Lady": [(0, "tired"), (70, "shocked"), (73, "happy")],
    "Man": [(0, "tired"), (70, "shocked"), (74, "grin")],
    "Worker": [(0, "tired"), (70, "shocked"), (75, "happy")],
    "Kid": [(0, "sad"), (70, "shocked"), (72.5, "grin")],
    "Preston": [(0, "smug"), (74.5, "shocked"), (77, "sad")],
    "TimmyF": [(0, "tired"), (66, "tired"), (69, "neutral"), (72, "happy")],
    "Mom": [(0, "tired"), (52, "shocked"), (55, "crying"), (59, "love")],
    "TimmyB": [(0, "sad"), (25, "angry")],
    "TimmyE": [(0, "happy"), (55, "grin")],
    "TimmyC": [(0, "neutral"), (31, "tired"), (34, "grin")],
    "PrestonD": [(0, "smug"), (46, "grin")],
    "TimmyD": [(0, "scared"), (46, "sad"), (49, "happy")],
}

J = ["Workspace", "Sets", "Jar"]
C = ["Workspace", "Sets", "CarryChair"]
PROPS = [
    {"path": J, "show": [[0, 37.0]]},                                                              # on the desk
    {"path": J, "show": [[37.0, 40.0]], "attach": {"actor": "TimmyC", "hand": "Right", "offset": [0, -0.7, -0.4, 0, 0, 0]}},
    {"path": J, "show": [[40.0, 47.5]], "attach": {"actor": "TimmyD", "hand": "Right", "offset": [0, -0.7, -0.4, 0, 0, 0]}},
    {"path": J, "show": [[47.5, 52.0]], "attach": {"actor": "PrestonD", "hand": "Right", "offset": [0, -0.7, -0.4, 0, 0, 0]}},
    {"path": C, "show": [[48.5, 51.5]], "attach": {"actor": "TimmyD", "hand": "Right", "offset": [-0.8, -0.6, -1.4, 0, 180, 0]}},
    {"path": C, "show": [[51.5, 54.6]], "attach": {"actor": "TimmyE", "hand": "Right", "offset": [-0.8, -0.6, -1.4, 0, 180, 0]}},
    {"path": ["Workspace", "Sets", "MomChair"], "show": [[54.6, 999]]},
]
MUSIC = {"query": "piano", "pick": 0, "from": 0, "gain": 0.45}
SFX = [(0.2, "coin", 0.6), (27.4, "coins", 0.7), (34.0, "cheer", 0.5), (46.4, "cash register", 0.7), (52.4, "gasp", 0.6),
       (67.4, "thud", 0.5), (76.0, "applause", 0.4)]
