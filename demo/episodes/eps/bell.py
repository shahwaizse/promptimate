"""In this town, when the bell rings, you have to sit down. Anywhere."""
TITLE = "In this town, when the bell rings, you sit down. Anywhere."
LENGTH = 28.0
VOICE, SPEED = "af_heart", 1.06

CAST = [
    {"name": "Timmy", "look": "timmy", "at": [8, 7.5]},
    {"name": "Officer", "look": "officer", "at": [30, 11]},
    {"name": "MrsLee", "look": "lee", "at": [-9, 6]},
    {"name": "Red", "look": "red", "at": [4, 11]},
    {"name": "Green", "look": "green", "at": [16, 4]},
    {"name": "Yellow", "look": "yellow", "at": [-6, 10]},
]
RUN_SIT = ["a person runs forward quickly", "a person turns around and sits down quickly"]
SIT = "a person sits still and stares"


def _sitter(name, start, facing, bench, first):
    return {"name": name, "start": start, "facing": facing, "beats": [
        {"prompt": first, "seconds": 3.0},                                                 # 0 normal day
        {"prompt": RUN_SIT, "seconds": [2.5, 2.0], "sit": bench, "sit_from": 3.6},          # 3 the bell
        {"prompt": "a person sits and looks around", "seconds": 3.5, "sit": bench},          # 7.5
        {"prompt": SIT, "seconds": 3.0, "sit": bench},                                      # 11 stare at Timmy
        {"prompt": "a person sits and watches", "seconds": 7.0, "sit": bench},              # 14
        {"prompt": "a person sits and laughs", "seconds": 4.0, "sit": bench},               # 21
    ]}


ACTORS = [
    {"name": "Timmy", "start": [8, 7.5], "facing": "+Z", "beats": [
        {"prompt": "a person stands and looks down at a phone in their hand", "seconds": 7.5},                  # 0
        {"prompt": "a person looks up and around in a panic", "seconds": 3.5},                                  # 7.5
        {"prompt": "a person turns in a circle looking for somewhere to sit", "seconds": 3.5},                 # 11
        {"prompt": "a person sits down on the ground, cross-legged", "seconds": 3.5},                           # 14.5
        {"prompt": "a person sits on the ground cross-legged, looking up", "seconds": 4.5},                     # 18
        {"prompt": "a person stands up from the ground and shrugs, defeated", "seconds": 3.0},                 # 22.5
        {"prompt": "a person stands with their head down, sighing", "seconds": 2.5},                           # 25.5
    ]},
    _sitter("MrsLee", [-9, 6], "+X", "Bench", "a person walks forward slowly"),
    _sitter("Yellow", [-6, 10], "+X", "Bench", "a person walks forward casually"),
    _sitter("Red", [4, 11], "+X", "Bench2", "a person walks forward, swinging their arms"),
    _sitter("Green", [16, 4], "+Z", "Bench2", "a person stands, stretching their arms"),
    {"name": "Officer", "start": [30, 11], "facing": "-X", "beats": [
        {"prompt": "a person walks forward confidently, patrolling", "seconds": 3.0, "to": [26, 11]},
        {"prompt": RUN_SIT, "seconds": [2.5, 2.0], "sit": "Bench2", "sit_from": 3.6},
        {"prompt": "a person sits with their arms crossed", "seconds": 10.5, "sit": "Bench2"},       # 7.5
        {"prompt": "a person stands up and walks forward sternly", "seconds": 3.5, "to": "Timmy", "face": "Timmy"},  # 18
        {"prompt": "a person points firmly to the left with their left arm", "seconds": 2.5, "face": "Timmy"},     # 21.5
        {"prompt": "a person stands with their hands on their hips", "seconds": 4.0, "face": "Timmy"},              # 24
    ]},
]
# the Officer's seated beat runs past 10 s: split it
ACTORS[-1]["beats"][2] = {"prompt": ["a person sits with their arms crossed"] * 2, "seconds": [5.5, 5.0], "sit": "Bench2"}

CAMERAS = [
    {"name": "street", "start": 0.0, "pos": [8, 8, 28], "look": [8, 3, 6], "fov": 56, "subjects": []},
    {"name": "rush", "start": 3.0, "pos": [9, 12, 24], "look": [9, 1.5, 6], "fov": 60, "subjects": []},
    {"name": "timmy looks up", "start": 7.5, "pos": [8, 5.3, 15.5], "look": [8, 4.8, 7.5], "fov": 30, "subjects": ["Timmy"]},
    {"name": "benches full", "start": 9.5, "pos": [10, 6, 22], "look": [10, 3, 5], "fov": 52, "subjects": []},
    {"name": "they stare", "start": 11.0, "pos": [13, 5, 9.5], "look": [7, 3.2, 3], "fov": 62, "subjects": []},
    {"name": "on the ground", "start": 14.5, "pos": [11, 3.8, 13], "look": [8, 2.5, 7.5], "fov": 40, "subjects": ["Timmy"]},
    {"name": "officer comes", "start": 18.0, "pos": [13, 5.5, 17], "look": [12, 3.5, 8], "fov": 50, "subjects": []},
    {"name": "points at sign", "start": 21.5, "pos": [6, 5, 16], "look": [3, 4.5, 4], "fov": 48, "subjects": []},
    {"name": "defeated", "start": 24.0, "pos": [8, 5.2, 15], "look": [8, 4.4, 7.5], "fov": 32, "subjects": ["Timmy"]},
]

LINES = [
    (0.3, "In this town, when the bell rings, you have to sit down."),
    (3.4, "Anywhere."),
    (7.7, "Timmy was on his phone."),
    (11.1, "Every seat was taken."),
    (14.6, "So he sat on the ground."),
    (18.2, "That's when he learned the second rule."),
    (21.7, "No sitting on the ground."),
    (24.6, "Welcome to the town of no sitting."),
]
MUSIC = {"query": "funny", "pick": 0, "from": 0, "gain": 0.5}
SFX = [(3.0, "school bell", 0.9), (11.0, "crickets", 0.5), (21.6, "whistle", 0.7)]
