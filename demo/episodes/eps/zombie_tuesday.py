"""In this town, on Tuesdays, everybody walks like a zombie."""
TITLE = "In this town, on Tuesdays, everybody walks like a zombie"
LENGTH = 28.0
VOICE, SPEED = "af_heart", 1.06

ZWALK = "a person walks forward slowly like a zombie, arms stretched out in front, dragging their feet"
TURN = "a person stops and slowly turns their head to stare"
CAST = [
    {"name": "Timmy", "look": "timmy", "at": [-30, 8]},
    {"name": "Tedd", "look": "tedd", "at": [-12, 4]},
    {"name": "Wendy", "look": "wendy", "at": [6, 10.5]},
    {"name": "Marilyn", "look": "marilyn", "at": [-2, 2.5]},
    {"name": "Officer", "look": "officer", "at": [14, 11.5]},
    {"name": "MrsLee", "look": "lee", "at": [-20, 2]},
]


def _z(name, start, facing, to1, to2, to3):
    return {"name": name, "start": start, "facing": facing, "beats": [
        {"prompt": ZWALK, "seconds": 7.0, "to": to1},                       # 0 zombie Tuesday
        {"prompt": TURN, "seconds": 2.5, "face": "Timmy"},                   # 7 someone's walking normally
        {"prompt": ZWALK, "seconds": 4.0, "to": to2, "face": "Timmy"},       # 9.5 closing in
        {"prompt": "a person stands still and watches, arms crossed", "seconds": 5.0, "face": "Timmy"},  # 13.5
        {"prompt": ZWALK, "seconds": 5.0, "to": to3},                        # 18.5 all together
        {"prompt": "a person stops, confused, and looks at their wrist", "seconds": 4.5},  # 23.5 wait...
    ]}


ACTORS = [
    {"name": "Timmy", "start": [-30, 8], "facing": "+X", "beats": [
        {"prompt": "a person walks forward briskly and happily, whistling", "seconds": 7.0, "to": [-8, 8]},   # 0
        {"prompt": "a person stops and looks around, nervous", "seconds": 2.5},                               # 7
        {"prompt": "a person backs away slowly, scared", "seconds": 4.0},                                     # 9.5
        {"prompt": ZWALK, "seconds": 5.0, "to": [-2, 8]},                                                     # 13.5
        {"prompt": ZWALK, "seconds": 5.0, "to": [12, 8.5]},                                                   # 18.5
        {"prompt": "a person stops and looks at a phone in their hand, then facepalms", "seconds": 4.5,
         "face": "+Z"},                                                                                        # 23.5
    ]},
    _z("Tedd", [-12, 4], "+X", [-9, 5], [-9, 6.5], [6, 5.5]),
    _z("Wendy", [6, 10.5], "-X", [-2, 10.5], [-5, 10], [10, 11]),
    _z("Marilyn", [-2, 2.5], "-X", [-4, 4], [-6, 5.5], [8, 3.5]),
    _z("Officer", [14, 11.5], "-X", [2, 11.5], [-4.5, 11], [14, 11.5]),
    _z("MrsLee", [-20, 2], "+X", [-14, 3], [-11, 5], [3, 2.5]),
]

CAMERAS = [
    {"name": "zombie street", "start": 0.0, "pos": [-6, 8, 28], "look": [-6, 3, 6], "fov": 56, "subjects": []},
    {"name": "timmy arrives", "start": 3.5, "track": "Timmy", "offset": [4, 1.6, 9], "aim": [0, 1.5, 0], "fov": 44},
    {"name": "they turn", "start": 7.0, "pos": [-9, 5.5, 13], "look": [-4, 4.5, 6], "fov": 58, "subjects": []},
    {"name": "uh oh", "start": 9.5, "pos": [-8, 5.3, 16], "look": [-8, 4.8, 8], "fov": 30, "subjects": ["Timmy"]},
    {"name": "surrounded", "start": 11.0, "pos": [-7, 13, 16], "look": [-7, 1.5, 7], "fov": 58, "subjects": []},
    {"name": "timmy zombie", "start": 13.5, "track": "Timmy", "offset": [3, 1.6, 8], "aim": [0, 1.5, 0], "fov": 42},
    {"name": "parade", "start": 18.5, "pos": [4, 7, 25], "look": [4, 3, 6], "fov": 58, "subjects": []},
    {"name": "wednesday", "start": 23.5, "pos": [12, 5.3, 16.5], "look": [12, 4.8, 8.5], "fov": 30, "subjects": ["Timmy"]},
    {"name": "everyone checks", "start": 25.8, "pos": [6, 7, 24], "look": [6, 3, 6], "fov": 56, "subjects": []},
]

LINES = [
    (0.3, "In this town, on Tuesdays, everybody walks like a zombie."),
    (3.8, "Timmy forgot it was Tuesday."),
    (7.1, "Everyone noticed."),
    (9.8, "Walk like a zombie, Timmy. Walk like a zombie!"),
    (13.8, "Phew."),
    (18.8, "Nailed it. Nobody suspects a thing."),
    (23.7, "Then he checked his phone."),
    (25.9, "It was Wednesday."),
]
MUSIC = {"query": "spooky", "pick": 0, "from": 0, "gain": 0.55}
SFX = [(7.0, "zombie groan", 0.7), (9.6, "gasp", 0.7), (25.8, "record scratch", 0.8)]
