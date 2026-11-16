"""In this town, if you stop walking, you freeze. Forever."""
TITLE = "In this town, if you stop walking, you freeze forever"
LENGTH = 28.0
VOICE, SPEED = "bm_george", 1.02

# the "statues": people who stopped, held in odd frozen poses for the whole episode
STATUES = [
    ("MrsLee", "lee", [-14, 4.5], "+Z", "a person freezes mid-wave with their right hand raised high, completely still"),
    ("Red", "red", [-2, 9.5], "-X", "a person freezes in the middle of a big sneeze, bent forward, completely still"),
    ("Green", "green", [6, 4], "+Z", "a person freezes while looking down at a phone, completely still"),
    ("Tedd", "tedd", [-24, 10], "+X", "a person freezes in the middle of a stretch, both arms raised, completely still"),
]
CAST = [{"name": "Timmy", "look": "timmy", "at": [-34, 7]}, {"name": "Officer", "look": "officer", "at": [24, 11]}] + \
       [{"name": n, "look": lk, "at": at} for n, lk, at, _f, _p in STATUES]

ACTORS = [
    {"name": "Timmy", "start": [-34, 7], "facing": "+X", "beats": [
        {"prompt": "a person walks forward steadily", "seconds": 5.0, "to": [-20, 7]},                       # 0
        {"prompt": "a person walks forward nervously, looking to the side", "seconds": 4.0, "to": [-9, 7]},  # 5
        {"prompt": "a person walks forward carefully, glancing around", "seconds": 3.5, "to": [0, 6.5]},     # 9
        {"prompt": "a person walks forward slowly while looking down at their feet", "seconds": 3.5, "to": [7, 7]},  # 12.5
        {"prompt": "a person walks in a small circle while bending down, reaching for their shoe", "seconds": 4.0,
         "to": [9, 8.5]},                                                                                    # 16
        {"prompt": "a person kneels down on one knee to tie their shoe", "seconds": 2.0},                     # 20
        {"prompt": "a person kneels on one knee, frozen completely still", "seconds": 6.0},                  # 22
    ]},
    {"name": "Officer", "start": [24, 11], "facing": "-X", "beats": [
        {"prompt": ["a person stands still"] * 3, "seconds": [8.0, 8.0, 7.0]},
        {"prompt": "a person walks forward casually, whistling, without stopping", "seconds": 5.0, "to": [2, 12.5],
         "via": [[16, 12]]},
    ]},
] + [{"name": n, "start": at, "facing": f, "beats": [{"prompt": [p] * 3, "seconds": [10.0, 10.0, 8.0]}]} for n, _lk, at, f, p in STATUES]

CAMERAS = [
    {"name": "street of statues", "start": 0.0, "pos": [-16, 8, 28], "look": [-14, 3, 5], "fov": 56, "subjects": []},
    {"name": "walk", "start": 4.5, "track": "Timmy", "offset": [2, 1.6, 9], "aim": [0, 1.5, 0], "fov": 46},
    {"name": "mrs lee", "start": 6.5, "pos": [-12, 5.5, 12], "look": [-14, 5, 4.5], "fov": 30, "subjects": ["MrsLee"]},
    {"name": "walk 2", "start": 9.0, "track": "Timmy", "offset": [-1, 1.6, 9], "aim": [0, 1.5, 0], "fov": 46},
    {"name": "sneeze guy", "start": 10.0, "pos": [-2, 5, 15], "look": [-2, 4, 9.5], "fov": 30, "subjects": ["Red"]},
    {"name": "shoelace", "start": 12.5, "track": "Timmy", "offset": [3, 1.0, 5], "aim": [0, -1.5, 0], "fov": 40},
    {"name": "hopping", "start": 16.0, "pos": [9, 5.5, 19], "look": [8, 3.5, 8], "fov": 40, "subjects": ["Timmy"]},
    {"name": "kneels", "start": 20.0, "pos": [11.5, 3.5, 13], "look": [9, 2.8, 8.5], "fov": 36, "subjects": ["Timmy"]},
    {"name": "frozen push", "start": 22.0, "pos": [10, 3.3, 11.5], "look": [9, 3.0, 8.5], "fov": 30, "subjects": ["Timmy"]},
    {"name": "officer passes", "start": 24.0, "pos": [8, 6, 22], "look": [8, 3, 9], "fov": 52, "subjects": []},
]

LINES = [
    (0.3, "In this town, if you stop walking... you freeze. Forever."),
    (6.6, "That's Mrs. Lee. She stopped to wave."),
    (10.1, "That guy stopped to sneeze."),
    (12.7, "Then Timmy's shoelace came undone."),
    (16.2, "He tried to tie it while walking."),
    (20.2, "He stopped."),
    (22.4, "Rest in peace, Timmy."),
    (24.4, "The officer never stops. Not even to help."),
]
MUSIC = {"query": "suspense", "pick": 1, "from": 0, "gain": 0.6}
SFX = [(20.9, "ice freeze", 0.9), (22.2, "bell", 0.5), (24.2, "whistle", 0.5)]
