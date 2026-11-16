"""In this town, at exactly 3 PM, everyone dances."""
TITLE = "In this town, at exactly 3 PM, everyone dances"
LENGTH = 28.0
VOICE, SPEED = "af_heart", 1.06

DANCE = "a person dances energetically, pumping their arms and bouncing to the beat"
STOP = "a person stops suddenly and stands still"
STARE = "a person stands completely still and stares"
ZOMBIE = "a person walks forward slowly and menacingly, staring"

CAST = [
    {"name": "Timmy", "look": "timmy", "at": [-4, 8]},
    {"name": "Officer", "look": "officer", "at": [-20, 10]},
    {"name": "MrsLee", "look": "lee", "at": [7, 0.8]},
    {"name": "Red", "look": "red", "at": [10, 9]},
    {"name": "Green", "look": "green", "at": [-14, 3]},
    {"name": "Yellow", "look": "yellow", "at": [3, 11.5]},
]


def _dancer(name, start, facing, walk_to, close_to, first):
    return {"name": name, "start": start, "facing": facing, "beats": [
        {"prompt": first, "seconds": 3.5, "to": walk_to},                               # 0   going about the day
        {"prompt": STOP, "seconds": 2.0, "face": "+Z"},                                 # 3.5 3 PM
        {"prompt": DANCE, "seconds": 8.0, "face": "+Z"},                                # 5.5
        {"prompt": STARE, "seconds": 2.5, "face": "Timmy"},                             # 13.5 Timmy isn't dancing
        {"prompt": ZOMBIE, "seconds": 3.5, "to": close_to, "face": "Timmy"},            # 16
        {"prompt": "a person stands still with arms crossed, watching", "seconds": 4.5, "face": "Timmy"},  # 19.5
        {"prompt": DANCE, "seconds": 4.0, "face": "+Z"},                                # 24
    ]}


ACTORS = [
    {"name": "Timmy", "start": [-4, 8], "facing": "+Z", "beats": [
        {"prompt": "a person stands and looks at a phone in their hand", "seconds": 5.5},                     # 0
        {"prompt": "a person looks around confused at the people around them", "seconds": 8.0},              # 5.5
        {"prompt": "a person freezes and stands very still, nervous", "seconds": 2.5},                        # 13.5
        {"prompt": "a person steps backward nervously, looking around", "seconds": 3.5},                      # 16
        {"prompt": "a person dances awkwardly and nervously, flailing their arms", "seconds": 4.5, "face": "+Z"},  # 19.5
        {"prompt": DANCE, "seconds": 4.0, "face": "+Z"},                                                     # 24
    ]},
    _dancer("Officer", [-20, 10], "+X", [-12, 10], [-6.5, 9.5], "a person walks forward confidently, patrolling"),
    _dancer("MrsLee", [7, 0.8], "+Z", [7, 2.0], [0.5, 5.5], "a person stands in a doorway, looking out at the street"),
    _dancer("Red", [10, 9], "-X", [6, 9.5], [0, 10.5], "a person walks forward casually"),
    _dancer("Green", [-14, 3], "+X", [-10, 4], [-7, 5.5], "a person walks forward slowly, looking at the shops"),
    _dancer("Yellow", [3, 11.5], "-X", [1, 11.5], [-2.5, 11.5], "a person walks forward, swinging their arms"),
]

CAMERAS = [
    {"name": "street", "start": 0.0, "pos": [-3, 8, 28], "look": [-3, 3, 5], "fov": 56, "subjects": []},
    {"name": "freeze", "start": 3.5, "pos": [2, 5.5, 20], "look": [-1, 4, 7], "fov": 44, "subjects": []},
    {"name": "dance wide", "start": 5.5, "pos": [-3, 9, 27], "look": [-3, 3, 6], "fov": 54, "subjects": []},
    {"name": "officer dances", "start": 9.0, "track": "Officer", "offset": [0, 1.5, 9], "aim": [0, 1.5, 0], "fov": 36},
    {"name": "timmy confused", "start": 11.5, "pos": [-4, 5.2, 16], "look": [-4, 4.8, 8], "fov": 28, "subjects": ["Timmy"]},
    {"name": "they stare", "start": 13.5, "pos": [-4, 5.5, 9.5], "look": [0, 4, 6], "fov": 60, "subjects": []},
    {"name": "closing in", "start": 16.0, "pos": [-4, 12, 18], "look": [-3, 2, 7], "fov": 56, "subjects": []},
    {"name": "timmy dances", "start": 19.5, "pos": [-4, 5, 15], "look": [-4, 4.2, 8.5], "fov": 36, "subjects": ["Timmy"]},
    {"name": "all dance", "start": 24.0, "pos": [-3, 8, 25], "look": [-3, 3.5, 7], "fov": 52, "subjects": []},
]

LINES = [
    (0.3, "In this town, at exactly three P.M.,"),
    (3.6, "everyone stops..."),
    (5.7, "and dances."),
    (8.6, "Everyone. Even the police."),
    (13.6, "Timmy didn't dance."),
    (16.4, "Bad idea."),
    (19.8, "Dance, Timmy. Dance!"),
    (24.3, "Welcome to three P.M."),
]
MUSIC = {"query": "dance", "pick": 0, "from": 0, "gain": 0.55}
SFX = [(3.3, "clock chime", 0.8), (13.4, "record scratch", 0.9), (16.0, "drum", 0.5)]
