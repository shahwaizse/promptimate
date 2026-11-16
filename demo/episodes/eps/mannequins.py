"""In this town, you never turn your back on the mannequins."""
TITLE = "In this town, you never turn your back on the mannequins"
LENGTH = 28.0
VOICE, SPEED = "bm_george", 1.0
STILL = "a person stands perfectly still and stiff like a mannequin, arms straight at their sides"

CAST = [
    {"name": "Timmy", "look": "timmy", "at": [-34, 8], "yaw": -90},
    {"name": "M1", "look": "mannequin", "at": [-22, 0.6]},
    {"name": "M2", "look": "mannequin2", "at": [-19, 0.6]},
    {"name": "M3", "look": "mannequin", "at": [-16, 0.6]},
]


def _m(name, start, a, b):
    """A mannequin: frozen in the window, moves only while the camera is on Timmy."""
    return {"name": name, "start": start, "facing": "+Z", "beats": [
        {"prompt": STILL, "seconds": 8.0},
        {"prompt": "a person walks forward stiffly and quickly", "seconds": 3.0, "to": a, "face": "Timmy"},
        {"prompt": STILL, "seconds": 5.0, "face": "Timmy"},
        {"prompt": "a person walks forward stiffly and quickly", "seconds": 3.0, "to": b, "face": "Timmy"},
        {"prompt": STILL, "seconds": 3.5, "face": "Timmy"},
        {"prompt": "a person stands perfectly still and slowly turns their head", "seconds": 5.5, "face": [1.5, 18]},
    ]}


ACTORS = [
    {"name": "Timmy", "start": [-34, 8], "facing": "+X", "beats": [
        {"prompt": "a person walks forward casually, looking around", "seconds": 8.0, "to": [-6, 8]},
        {"prompt": "a person stands and looks down at a phone in their right hand", "seconds": 5.0, "face": "+X"},
        {"prompt": "a person slowly turns around and looks behind them nervously", "seconds": 3.0, "face": "-X"},
        {"prompt": "a person turns around and walks forward quickly and nervously", "seconds": 3.0, "to": [4, 9]},
        {"prompt": "a person stops and looks back over their shoulder, scared", "seconds": 3.0, "face": "-X"},
        {"prompt": "a person runs forward in panic", "seconds": 3.5, "to": [30, 12], "via": [[10, 12]]},
        {"prompt": "a person stands still, breathing heavily", "seconds": 2.5},
    ]},
    _m("M1", [-22, 0.6], [-14, 6], [0, 8]),
    _m("M2", [-19, 0.6], [-12, 9.5], [1.5, 10.5]),
    _m("M3", [-16, 0.6], [-11, 4.5], [-0.5, 6]),
]

CAMERAS = [
    {"name": "street", "start": 0.0, "pos": [-16, 7, 30], "look": [-18, 3, 3], "fov": 55},
    {"name": "walk past", "start": 4.0, "track": "Timmy", "offset": [0, 1.5, 10], "aim": [0, 1.5, 0], "fov": 45},
    {"name": "phone close", "start": 8.0, "pos": [-6, 5.4, 16], "look": [-6, 5.0, 8], "fov": 26, "subjects": ["Timmy"]},
    {"name": "they moved", "start": 11.0, "pos": [-2, 5, 8.5], "look": [-12.5, 3.5, 6.5], "fov": 42, "subjects": ["M1", "M2", "M3"]},
    {"name": "turns", "start": 13.0, "pos": [-9.5, 5.5, 11.5], "look": [-6, 5, 8], "fov": 34, "subjects": ["Timmy"]},
    {"name": "walk away tight", "start": 16.0, "track": "Timmy", "offset": [0, 1.8, 7], "aim": [0, 1.8, 0], "fov": 28, "subjects": ["Timmy"]},
    {"name": "right behind", "start": 19.0, "pos": [9, 5, 13], "look": [1, 4, 8.5], "fov": 46},
    {"name": "runs", "start": 22.0, "pos": [8, 7, 26], "look": [8, 3, 8], "fov": 56, "subjects": []},
    {"name": "looking at you", "start": 24.5, "pos": [1.5, 6.2, 18], "look": [1.5, 5.6, 10.5], "fov": 22, "subjects": ["M2"]},
]

LINES = [
    (0.4, "In this town, you never turn your back on the mannequins."),
    (4.9, "Timmy didn't know that."),
    (8.5, "He stopped. Just for a second."),
    (11.4, "Big mistake."),
    (16.3, "Every time he looked away..."),
    (19.3, "they got closer."),
    (24.9, "And now... they're looking at you."),
]
MUSIC = {"query": "creepy", "pick": 0, "from": 4, "gain": 0.55}
SFX = [(11.0, "whoosh", 0.7), (19.0, "horror sting", 0.8), (22.2, "scream", 0.6), (24.6, "heartbeat", 0.9)]
