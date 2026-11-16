"""In this town, everyone copies the new kid."""
TITLE = "In this town, everyone copies the new kid"
LENGTH = 27.0
VOICE, SPEED = "af_heart", 1.08

FOLK = {"Red": ([-3.5, 5.5], "red"), "Green": ([1, 5.0], "green"), "Yellow": ([5, 6.0], "yellow"),
        "MrsLee": ([-7.5, 6.5], "lee")}
CAST = [{"name": "Timmy", "look": "timmy", "at": [-24, 9], "yaw": -90}] + \
       [{"name": n, "look": lk, "at": at} for n, (at, lk) in FOLK.items()]

WAVE = "a person waves hello with their right hand"
SCRATCH = "a person scratches their head with their right hand, confused"
DANCE = "a person does a silly little dance, wiggling their arms and hips"
FALL = "a person trips and falls backward onto their back"
STARE = "a person stands still and stares"


def _folk(name, at):
    return {"name": name, "start": at, "facing": "Timmy", "beats": [
        {"prompt": "a person stands still, idly shifting their weight", "seconds": 7.0, "face": "Timmy"},
        {"prompt": WAVE, "seconds": 2.5, "face": "Timmy"},                 # 7.0
        {"prompt": STARE, "seconds": 2.5, "face": "Timmy"},                # 9.5
        {"prompt": SCRATCH, "seconds": 2.5, "face": "Timmy"},              # 12.0
        {"prompt": STARE, "seconds": 2.5, "face": "Timmy"},                # 14.5
        {"prompt": DANCE, "seconds": 3.0, "face": "Timmy"},                # 17.0
        {"prompt": STARE, "seconds": 3.0, "face": "Timmy"},                # 20.0
        {"prompt": FALL, "seconds": 2.5},                                  # 23.0
        {"prompt": "a person lies still on their back", "seconds": 1.5},   # 25.5
    ]}


ACTORS = [
    {"name": "Timmy", "start": [-24, 9], "facing": "+X", "beats": [
        {"prompt": "a person walks forward happily", "seconds": 4.0, "to": [-1, 11], "face": "-Z"},
        {"prompt": WAVE, "seconds": 2.5, "face": "-Z"},                                      # 4.0
        {"prompt": "a person stands still and watches, surprised", "seconds": 3.0, "face": "-Z"},  # 6.5
        {"prompt": SCRATCH, "seconds": 2.5, "face": "-Z"},                                   # 9.5
        {"prompt": "a person stands still and watches, puzzled", "seconds": 2.5, "face": "-Z"},    # 12.0
        {"prompt": DANCE, "seconds": 3.0, "face": "-Z"},                                     # 14.5
        {"prompt": "a person laughs and claps their hands", "seconds": 4.5, "face": "-Z"},   # 17.5
        {"prompt": FALL, "seconds": 2.5},                                                    # 22.0
        {"prompt": "a person lies on their back and lifts their head to look", "seconds": 2.5},  # 24.5
    ]},
] + [_folk(n, at) for n, (at, _lk) in FOLK.items()]

CAMERAS = [
    # Timmy (z 11) faces the shops; the townsfolk (z 5-6.5) face him. His actions are shot from the folks' side
    # (low, between them), their copies from his side.
    {"name": "arrives", "start": 0.0, "pos": [-12, 6, 26], "look": [-6, 3, 7], "fov": 55},
    {"name": "timmy waves", "start": 4.0, "pos": [-1.5, 4.8, 3.2], "look": [-1, 4.6, 11], "fov": 34, "subjects": ["Timmy"]},
    {"name": "they wave", "start": 7.0, "pos": [-1, 6, 20], "look": [-1, 4, 5.5], "fov": 50, "subjects": ["Red", "Green", "Yellow", "MrsLee"]},
    {"name": "scratch", "start": 9.5, "pos": [3, 4.8, 3.2], "look": [-1, 4.8, 11], "fov": 32, "subjects": ["Timmy"]},
    {"name": "they scratch", "start": 12.0, "pos": [-1, 5.5, 18], "look": [-1, 4.2, 5.5], "fov": 46},
    {"name": "dance", "start": 14.5, "pos": [-1, 9.5, 3.5], "look": [-1, 4, 11], "fov": 40, "subjects": ["Timmy"]},
    {"name": "everyone dances", "start": 17.0, "pos": [-1, 7, 24], "look": [-1, 3.5, 7], "fov": 54},
    {"name": "trip", "start": 22.0, "pos": [3, 4, 18], "look": [-1, 2.5, 11], "fov": 40, "subjects": ["Timmy"]},
    {"name": "all down", "start": 23.5, "pos": [-1, 13, 21], "look": [-1, 0, 8], "fov": 55, "subjects": []},
]

LINES = [
    (0.3, "In this town, everyone copies the new kid."),
    (4.2, "He waved."),
    (7.2, "Everyone waved."),
    (9.7, "He scratched his head."),
    (12.2, "So did they."),
    (14.7, "So he tested it."),
    (17.3, "Okay. This is actually fun."),
    (22.2, "Then he tripped."),
    (24.0, "Nobody got hurt. Probably."),
]
MUSIC = {"query": "happy", "pick": 0, "from": 0, "gain": 0.5}
SFX = [(7.0, "pop", 0.6), (12.0, "pop", 0.6), (17.0, "pop", 0.6), (22.6, "thud", 0.9), (23.6, "crash", 0.5)]
