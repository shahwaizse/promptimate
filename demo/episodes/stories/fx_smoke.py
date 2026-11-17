TITLE = "In This Town, FX Smoke Test"
MUSIC = "happy"
KEYWORDS = ["grow", "swap", "vanish"]
CAST = {"Mia": "c_girl", "Leo": "c_boy2", "Bo": "c_grandpa"}
SCENES = [
    {"set": "Park", "place": {"Mia": "fountain_south:0,-6", "Leo": "fountain_south:5,-6", "Bo": "fountain_south:-5,-6"},
     "props": [{"name": "Count1", "sign": "COMPLIMENTS TODAY: 1", "style": "gold", "at": "fountain_south:0,-11"},
               {"name": "Count2", "sign": "COMPLIMENTS TODAY: 300", "style": "red", "at": "fountain_south:0,-11"},
               {"name": "Cake", "prop": "cake", "at": "Mia"}],
     "lines": [
        {"id": "rule", "say": "In this town, every time someone compliments you, you grow a whole foot taller.",
         "do": {"Leo": "talk point_smile@Mia", "Mia": "happy"}, "change": {"Mia": "grow 1.6 @1.5"},
         "cam": ["Leo+Mia", "Mia", "Count1"], "feel": {"Mia": "grin"}, "label": "+1 FOOT", "fx": {"Mia": "sparkle"},
         "sfx": "magic chime", "show": ["Count1"], "title": "TALLER"},
        {"id": "more", "say": "By lunch, Mia had three hundred compliments and could see over the whole park.",
         "do": {"Mia": "spread"}, "change": {"Mia": "grow 2.6", "Count1": "vanish", "Count2": "appear"},
         "cam": ["Mia", "Count2", "Leo+Mia"], "feel": {"Mia": "smug", "Leo": "shocked"}, "sfx": "boing"},
        {"id": "swap", "say": "Then Grandpa Bo sneezed, and he and Leo swapped bodies. Leo started complaining about his back.",
         "do": {"Leo": "shrug", "Bo": "stare"}, "change": {"Leo": "swap Bo @1.0"}, "cam": ["Leo+Bo", "Leo", "Bo"],
         "feel": {"Leo": "tired", "Bo": "grin"}, "fx": {"Leo": "dizzy"}, "sfx": "pop"},
        {"id": "cake", "say": "And the cake? It vanished. Nobody knows where. Bo is still looking for it.",
         "do": {"Bo": "look_self think"}, "change": {"Cake": "vanish @1.2"}, "show": ["Cake"], "cam": ["Cake", "Bo"],
         "feel": {"Bo": "sad"}, "fx": {"Bo": "rain"}, "sfx": "sad trombone"},
     ]},
]
