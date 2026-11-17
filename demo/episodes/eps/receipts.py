"""In this town, every receipt tells you how long the thing you bought will make you happy. (narration-paced; sourced
sets: Cafe, LivingRoom, BedroomB, Classroom, Kitchen + the old town street in front of TOYS; prop library via PLACE)"""
TITLE = "In This Town, Receipts Tell You How Long You'll Be Happy"
VOICE, SPEED = "tv_M2", 1.0
CAPTIONS = {"size": 120, "highlight": False, "max_words": 2}
KEYWORDS = ["receipt", "forever", "Timmy", "Preston", "Grandma", "Maya", "Leo", "bike", "crown", "zero", "seconds",
            "minutes", "years", "summer", "cat"]

# ---- cast: one copy of a character per set (characters don't travel between sets)
CAST = [
    # the cafe (A): x 2790..2810, counter (red) at z -3.5..0, open floor in front (z 1.5..3.5) and behind (z < -5)
    {"name": "LadyC", "look": "c_lady", "at": [2803, 2.5]},
    {"name": "Barista", "look": "c_chef", "at": [2806.5, -6]},
    # the living room (B): open floor in front of the coffee table / left of the round ottoman
    {"name": "Dad", "look": "c_man", "at": [1195.5, 8.5]},
    {"name": "Mom", "look": "c_mom", "at": [1189.5, 8.5]},
    # Timmy's bedroom (C): open floor between the top wall and the foot of the bed
    {"name": "TimmyR", "look": "c_timmy", "at": [1598, -8]},
    # the town street in front of the TOYS shop (D)
    {"name": "PrestonS", "look": "c_preston", "at": [24, 6]},
    {"name": "TimmyS", "look": "c_timmy", "at": [33, 6]},
    # the classroom (E): the open aisle right of the desks (x 1814.5..1823)
    {"name": "TimmyC", "look": "c_timmy", "at": [1817, 4], "yaw": 180},
    {"name": "Maya", "look": "c_girl", "at": [1816, -2]},
    {"name": "Leo", "look": "c_kid", "at": [1820, -1]},
    {"name": "PrestonC", "look": "c_preston", "at": [1819.5, 10], "yaw": 180},
    # Grandma's kitchen (F): open floor below the island (z 7..11)
    {"name": "Grandma", "look": "c_grandma", "at": [1401, 9], "yaw": -90},
    {"name": "TimmyK", "look": "c_timmy", "at": [1405.5, 9], "yaw": 90},
]

# shared prompt strings (identical across episodes: repeated prompts are free)
IDLE = "a person stands still, relaxed, looking around"
HAPPY = "a person stands and smiles happily"
SAD = "a person stands alone with their head down, sad"
STARE = "a person stares in surprise"
WALK = "a person walks forward casually"
JOY = "a person jumps up and down with joy, arms in the air"
FISTS = "a person stands still, watching sadly, then clenches their fists with determination"
SMUG = "a person stands with arms crossed, chin raised, smug"
LAUGH = "a person laughs hard, bending over and holding their stomach"
TALK = "a person stands and talks, gesturing with both hands"
GIVE = "a person holds out both hands, offering something"
SHRUG = "a person shrugs"
WAVE = "a person waves with their right hand"
NOD = "a person nods slowly"
WIPE = "a person stands behind a counter, working, wiping the counter"
SHOCK_BACK = "a person turns and steps back in surprise, arms down at their sides"
LOOK_SELF = "a person looks down at their own body in shock"
HUG = "a person steps forward and hugs someone tightly"
FLEX = "a person flexes both arms proudly"
# new in this episode
READ = "a person holds something in both hands and reads it carefully"
SIP = "a person drinks from a cup in their right hand"
SMASH = "a person lifts something over their head with both hands and throws it down hard"
LOOK_LR = "a person looks to the left, then to the right, then to the left again"
CRY = "a person covers their face with both hands and cries"
POCKET = "a person reaches into their pocket and pulls something out"
SHAKE = "a person shakes their head slowly, disappointed"

ACTORS = [
    # ---------------------------------------------------------------- A: the cafe
    {"name": "LadyC", "start": [2803, 2.5], "facing": "+Z", "beats": [
        {"at": 0.0, "prompt": IDLE, "seconds": 2.0},
        {"at": "@coffee", "prompt": SIP, "seconds": 2.2},
        {"prompt": READ, "seconds": 2.4},
        {"at": "@nobody", "prompt": READ, "seconds": 3.0},
        {"prompt": NOD, "seconds": 2.0},
    ]},
    {"name": "Barista", "start": [2806.5, -6], "facing": "+Z", "beats": [
        {"at": 0.0, "prompt": WIPE, "seconds": 3.0},
        {"at": "@coffee", "prompt": WIPE, "seconds": 3.0},
        {"at": "@nobody", "prompt": READ, "seconds": 3.0},
        {"prompt": SHRUG, "seconds": 1.8},
    ]},
    # ---------------------------------------------------------------- B: the living room
    {"name": "Dad", "start": [1195.5, 8.5], "facing": "+Z", "beats": [
        {"at": "@couch", "prompt": FLEX, "seconds": 2.4},
        {"prompt": SMUG, "seconds": 3.4},
        {"at": "@cat", "prompt": SHRUG, "seconds": 2.0, "face": "Mom"},
    ]},
    {"name": "Mom", "start": [1189.5, 8.5], "facing": "+Z", "beats": [
        {"at": "@couch", "prompt": SHAKE, "seconds": 2.6, "face": "Dad"},
        {"at": "@cat", "prompt": READ, "seconds": 2.6},
        {"prompt": SHRUG, "seconds": 2.0},
    ]},
    # ---------------------------------------------------------------- C: Timmy's bedroom, the piggy bank
    {"name": "TimmyR", "start": [1598, -8], "facing": "+Z", "beats": [
        {"at": "@me", "prompt": WAVE, "seconds": 1.8},
        {"prompt": HAPPY, "seconds": 2.6},
        {"prompt": FISTS, "seconds": 3.0},
        {"at": "@piggy", "prompt": SMASH, "seconds": 2.4},
        {"prompt": JOY, "seconds": 3.0},
        {"at": "@forgot", "prompt": STARE, "seconds": 2.2},
        {"prompt": LOOK_SELF, "seconds": 2.4},
    ]},
    # ---------------------------------------------------------------- D: the street in front of TOYS
    {"name": "PrestonS", "start": [24, 6], "facing": "+Z", "beats": [
        {"at": "@preston", "prompt": SMUG, "seconds": 3.0},
        {"prompt": STARE, "seconds": 2.0},
        {"at": "@again", "prompt": FLEX, "seconds": 2.0},
        {"prompt": SAD, "seconds": 2.6},
    ]},
    {"name": "TimmyS", "start": [33, 6], "facing": "+Z", "beats": [
        {"at": "@bike", "prompt": STARE, "seconds": 2.0, "face": "+X"},
        {"prompt": JOY, "seconds": 3.0, "face": "+Z"},
        {"at": "@choose", "prompt": LOOK_LR, "seconds": 3.6},
        {"prompt": NOD, "seconds": 1.8},
        {"at": "@zero", "prompt": READ, "seconds": 2.6},
        {"prompt": SAD, "seconds": 3.0},
    ]},
    # ---------------------------------------------------------------- E: the classroom
    {"name": "TimmyC", "start": [1817, 4], "facing": "-Z", "beats": [
        {"at": "@ask", "prompt": TALK, "seconds": 2.4},
        {"at": "@laptop+2.4", "prompt": STARE, "seconds": 2.0, "face": "Leo"},
        {"at": "@monday", "prompt": IDLE, "seconds": 3.0, "face": "+Z"},
        {"at": "@thirty", "prompt": STARE, "seconds": 2.6, "face": "PrestonC"},
        {"at": "@nice", "prompt": LAUGH, "seconds": 2.6, "face": "PrestonC"},
    ]},
    {"name": "Maya", "start": [1816, -2], "facing": "+Z", "beats": [
        {"at": "@ask", "prompt": IDLE, "seconds": 2.0, "face": "TimmyC"},
        {"at": "@laptop", "prompt": HAPPY, "seconds": 2.4},
        {"prompt": READ, "seconds": 2.0},
        {"at": "@thirty", "prompt": JOY, "seconds": 3.0},
        {"at": "@nice", "prompt": LAUGH, "seconds": 2.6, "face": "PrestonC"},
    ]},
    {"name": "Leo", "start": [1820, -1], "facing": "+Z", "beats": [
        {"at": "@ask", "prompt": IDLE, "seconds": 2.0, "face": "TimmyC"},
        {"at": "@laptop+2.4", "prompt": HAPPY, "seconds": 1.8},
        {"prompt": LOOK_SELF, "seconds": 2.4},
        {"at": "@thirty", "prompt": JOY, "seconds": 3.0},
        {"at": "@nice", "prompt": LAUGH, "seconds": 2.6, "face": "PrestonC"},
    ]},
    {"name": "PrestonC", "start": [1819.5, 10], "facing": "-Z", "beats": [
        {"at": "@monday", "prompt": SMUG, "seconds": 3.0},
        {"at": "@thirty", "prompt": GIVE, "seconds": 2.4},
        {"prompt": SMUG, "seconds": 2.4},
        {"at": "@words", "prompt": POCKET, "seconds": 2.2},
        {"at": "@nice", "prompt": SHOCK_BACK, "seconds": 2.0},
        {"prompt": SAD, "seconds": 3.0},
    ]},
    # ---------------------------------------------------------------- F: Grandma's kitchen
    {"name": "Grandma", "start": [1401, 9], "facing": "+X", "beats": [
        {"at": "@opened", "prompt": READ, "seconds": 3.0},
        {"at": "@cried", "prompt": CRY, "seconds": 2.4},
        {"prompt": HUG, "seconds": 2.6, "face": "TimmyK"},
        {"at": "@forever", "prompt": HAPPY, "seconds": 3.0, "face": "TimmyK"},
    ]},
    {"name": "TimmyK", "start": [1405.5, 9], "facing": "-X", "beats": [
        {"at": "@sense", "prompt": GIVE, "seconds": 2.4},
        {"at": "@opened", "prompt": SAD, "seconds": 3.0, "face": "Grandma"},
        {"at": "@cried+2.4", "prompt": HUG, "seconds": 2.6, "face": "Grandma"},
        {"at": "@warm", "prompt": POCKET, "seconds": 2.2, "face": "+Z"},
        {"prompt": READ, "seconds": 2.6},
        {"at": "@forever", "prompt": JOY, "seconds": 3.0},
    ]},
]

LINES = [
    {"id": "rule", "text": "In this town, every receipt tells you how long the thing you bought will make you happy. Mine says forever."},
    {"id": "coffee", "text": "A coffee? Eleven minutes. A double shot? Fourteen."},
    {"id": "couch", "text": "My dad's couch said six years. That was nine years ago. He still sits on it out of spite.", "gap": 0.3},
    {"id": "cat", "text": "Mom adopted a cat. Her receipt just said, depends on the cat."},
    {"id": "nobody", "text": "So nobody here buys anything without reading the receipt first. Some people read them like horoscopes.", "gap": 0.3},
    {"id": "me", "text": "I'm Timmy. I saved my allowance for a whole year. And I wanted the longest receipt in town.", "gap": 0.3},
    {"id": "preston", "text": "Preston, the richest kid in school, bought a solid gold crown. Nine seconds.", "gap": 0.3},
    {"id": "again", "text": "So he bought another crown. Four seconds. He's still trying."},
    {"id": "ask", "text": "So I asked around at school. What lasts the longest?", "gap": 0.3},
    {"id": "laptop", "text": "Maya's laptop? Two weeks. Leo's new phone? Three days. Then he dropped it."},
    {"id": "bike", "text": "Then, at the toy store, I found it. A red bike. One whole summer. The best receipt I had ever seen.", "gap": 0.3},
    {"id": "piggy", "text": "That night, I smashed my piggy bank. Forty-two dollars and a button. Exactly enough.", "gap": 0.3},
    {"id": "forgot", "text": "Then I remembered. Tomorrow was Grandma's eightieth birthday. And I had nothing for her."},
    {"id": "choose", "text": "I stood in that store for an hour. Bike. Grandma. Bike. Grandma.", "gap": 0.3},
    {"id": "zero", "text": "So I bought her a present instead. A tiny photo frame. My receipt said zero seconds."},
    {"id": "sense", "text": "Makes sense, I guess. It wasn't for me.", "gap": 0.3},
    {"id": "opened", "text": "Grandma opened it. A photo of us two, from when I was a baby."},
    {"id": "cried", "text": "She cried. Then she hugged me for a really long time. She smelled like cookies."},
    {"id": "warm", "text": "That's when my pocket felt warm. I pulled out the receipt. It had changed.", "gap": 0.3},
    {"id": "forever", "text": "Forever."},
    {"id": "monday", "text": "By Monday, the whole school knew about my receipt. Including Preston.", "gap": 0.4},
    {"id": "thirty", "text": "He bought a present for every single kid in class. Thirty presents. Then he waited."},
    {"id": "words", "text": "Then he checked his receipt. It said two words."},
    {"id": "nice", "text": "Nice try."},
]
TITLES = [("@rule+3.0", "@rule.end+0.3", "RECEIPTS"), ("@forever", "@forever.end+0.8", "FOREVER")]

# ---- sourced props (sets.py prop library), cloned to workspace.Sets.EpisodeProps.<name>; y = the set's floor_y
PLACE = [
    {"prop": "coffee_cup", "at": [2801, 3.5], "y": 1.3, "yaw": 0, "name": "Coffee"},
    {"prop": "cat", "at": [1191.5, 10.5], "y": 1.1, "yaw": 160, "name": "Cat"},
    {"prop": "piggy_bank", "at": [1600.5, -8], "y": 0.4, "yaw": 200, "name": "Piggy"},
    {"prop": "coin_pile", "at": [1598.5, -5.8], "y": 0.4, "yaw": 0, "name": "Coins"},
    {"prop": "crown", "at": [22, 8], "yaw": 0, "name": "CrownA"},
    {"prop": "crown", "at": [26, 8], "yaw": 30, "name": "CrownB"},
    {"prop": "bicycle", "at": [37.5, 8.5], "yaw": 0, "name": "Bike"},
    {"prop": "gift_box", "at": [29.5, 8], "yaw": 15, "name": "GiftT"},
    {"prop": "gift_box", "at": [1407.5, 11], "y": 0.5, "yaw": 0, "name": "GiftK"},
    {"prop": "photo_frame", "at": [1399, 11], "y": 0.5, "yaw": 0, "name": "Photo"},
    {"prop": "laptop", "at": [1814.5, -3], "y": 0.8, "yaw": 0, "name": "Laptop"},
    {"prop": "phone", "at": [1821.5, -3], "y": 0.8, "yaw": 0, "name": "Phone"},
    {"prop": "gift_box", "at": [1822, 12.5], "y": 0.8, "yaw": 0, "name": "GiftP1"},
    {"prop": "gift_box", "at": [1822, 12.5], "y": 2.2, "yaw": 25, "name": "GiftP2"},
    {"prop": "gift_box", "at": [1822, 12.5], "y": 3.6, "yaw": -15, "name": "GiftP3"},
    {"prop": "gift_box", "at": [1821, 14], "y": 0.8, "yaw": 40, "name": "GiftP4"},
    {"prop": "gift_box", "at": [1822.8, 14], "y": 0.8, "yaw": -30, "name": "GiftP5"},
    {"prop": "gift_box", "at": [1814.5, 0], "y": 0.8, "yaw": 0, "name": "GiftM"},
    {"prop": "gift_box", "at": [1821.5, 1], "y": 0.8, "yaw": 0, "name": "GiftL"},
]


def EP(n):
    return ["Workspace", "Sets", "EpisodeProps", n]


HAND = [0, -0.6, -0.3, 0, 0, 0]

CAMERAS = [
    # A: the cafe
    # hook: a face on screen from frame one (the references all open on a close-up), then the room
    {"name": "hook", "start": 0.0, "subject": "LadyC", "shot": "close", "angle": 10},
    {"name": "rule", "start": "@rule+2.2", "subject": "LadyC", "shot": "medium", "angle": 30},
    {"name": "mine says forever", "start": "@rule.end-1.4", "subject": "LadyC", "shot": "close", "angle": -10},
    {"name": "coffee cup", "start": "@coffee", "prop": "Coffee", "shot": "close", "angle": 0},
    {"name": "eleven minutes", "start": "@coffee+1.2", "subject": "LadyC", "shot": "close", "angle": 15},
    # B: the living room
    {"name": "living room", "start": "@couch", "pos": [1205, 8, 14], "look": [1194, 3, -1], "fov": 55, "subjects": []},
    {"name": "dad", "start": "@couch+1.6", "subject": "Dad", "shot": "medium", "angle": 15},
    {"name": "out of spite", "start": "@couch.end-2.0", "subject": "Dad", "shot": "close", "angle": -10},
    {"name": "mom and cat", "start": "@cat", "subject": "Mom", "with": "Dad", "shot": "full", "angle": 0},
    {"name": "the cat", "start": "@cat+1.4", "prop": "Cat", "shot": "close", "angle": 0},
    {"name": "depends", "start": "@cat.end-1.4", "subject": "Mom", "shot": "close", "angle": 10},
    # A: back to the cafe
    {"name": "nobody", "start": "@nobody", "subject": "Barista", "with": "LadyC", "shot": "full", "angle": 15},
    {"name": "reading", "start": "@nobody+2.0", "subject": "LadyC", "shot": "close", "angle": 0},
    # C: the bedroom
    {"name": "bedroom", "start": "@me", "pos": [1606, 7.5, 2], "look": [1598, 2.5, -8], "fov": 55, "subjects": []},
    {"name": "i'm timmy", "start": "@me+1.0", "subject": "TimmyR", "shot": "medium", "angle": 0},
    {"name": "longest receipt", "start": "@me.end-2.0", "subject": "TimmyR", "shot": "close", "angle": 10},
    # D: the street, Preston
    {"name": "street", "start": "@preston", "pos": [29, 6, 24], "look": [29, 4, 0], "fov": 52, "subjects": []},
    {"name": "gold crown", "start": "@preston+1.4", "subject": "PrestonS", "shot": "medium", "angle": 15},
    {"name": "nine seconds", "start": "@preston.end-1.2", "subject": "PrestonS", "shot": "close", "angle": 0},
    {"name": "another crown", "start": "@again", "subject": "PrestonS", "shot": "full", "angle": -20},
    {"name": "four seconds", "start": "@again.end-1.0", "subject": "PrestonS", "shot": "close", "angle": 10},
    # E: the classroom
    {"name": "classroom", "start": "@ask", "pos": [1809, 8, 16], "look": [1818, 3, 1], "fov": 55, "subjects": []},
    {"name": "maya", "start": "@laptop", "subject": "Maya", "shot": "medium", "angle": 10},
    {"name": "leo", "start": "@laptop+2.4", "subject": "Leo", "shot": "medium", "angle": -10},
    {"name": "dropped it", "start": "@laptop.end-1.2", "subject": "Leo", "shot": "close", "angle": 0},
    # D: the bike
    {"name": "toy store", "start": "@bike", "subject": "TimmyS", "shot": "full", "angle": 20},
    {"name": "red bike", "start": "@bike+2.2", "prop": "Bike", "shot": "close", "angle": 0},
    {"name": "one whole summer", "start": "@bike+4.0", "subject": "TimmyS", "shot": "close", "angle": 0},
    # C: the piggy bank
    {"name": "smash", "start": "@piggy", "subject": "TimmyR", "shot": "full", "angle": -15},
    {"name": "coins", "start": "@piggy+2.0", "prop": "Coins", "shot": "close", "angle": 0},
    {"name": "exactly enough", "start": "@piggy.end-1.4", "subject": "TimmyR", "shot": "medium", "angle": 10},
    {"name": "remembered", "start": "@forgot", "subject": "TimmyR", "shot": "close", "angle": 0},
    {"name": "nothing for her", "start": "@forgot.end-1.6", "subject": "TimmyR", "shot": "medium", "angle": -20},
    # D: bike or grandma
    {"name": "store an hour", "start": "@choose", "pos": [33.5, 4.5, 20], "look": [33.5, 3, 7], "fov": 45, "subjects": []},
    {"name": "bike grandma", "start": "@choose+2.0", "subject": "TimmyS", "shot": "close", "angle": 0},
    {"name": "present", "start": "@zero", "subject": "TimmyS", "shot": "medium", "angle": 15},
    {"name": "zero seconds", "start": "@zero.end-1.4", "subject": "TimmyS", "shot": "close", "angle": -10},
    # F: Grandma's kitchen
    {"name": "kitchen", "start": "@sense", "pos": [1412, 8, 11.5], "look": [1402, 3, 2], "fov": 55, "subjects": []},
    {"name": "not for me", "start": "@sense+1.0", "subject": "TimmyK", "with": "Grandma", "shot": "medium", "angle": 0},
    {"name": "opened", "start": "@opened", "subject": "Grandma", "shot": "medium", "angle": 15},
    {"name": "the photo", "start": "@opened+1.6", "subject": "Grandma", "shot": "close", "angle": 0},
    {"name": "cried", "start": "@cried", "subject": "Grandma", "shot": "close", "angle": -10},
    {"name": "hug", "start": "@cried+2.4", "subject": "Grandma", "with": "TimmyK", "shot": "full", "angle": 0},
    {"name": "pocket", "start": "@warm", "subject": "TimmyK", "shot": "medium", "angle": 15},
    {"name": "it had changed", "start": "@warm.end-1.4", "subject": "TimmyK", "shot": "close", "angle": 0},
    {"name": "forever", "start": "@forever", "subject": "TimmyK", "with": "Grandma", "shot": "medium", "angle": 0},
    # E: Monday, Preston's thirty presents
    {"name": "monday", "start": "@monday", "pos": [1809, 8, 16], "look": [1818, 3, 4], "fov": 55, "subjects": []},
    {"name": "including preston", "start": "@monday.end-1.4", "subject": "PrestonC", "shot": "medium", "angle": 15},
    {"name": "gift pile", "start": "@thirty", "prop": "GiftP2", "shot": "medium", "angle": 0},
    {"name": "thirty presents", "start": "@thirty+2.2", "subject": "Maya", "with": "Leo", "shot": "full", "angle": 0},
    {"name": "checks receipt", "start": "@words", "subject": "PrestonC", "shot": "medium", "angle": -10},
    {"name": "nice try", "start": "@nice", "subject": "PrestonC", "shot": "close", "angle": 0},
    {"name": "class laughs", "start": "@nice+1.2", "subject": "TimmyC", "with": "PrestonC", "shot": "full", "angle": 20},
]

FACES = {
    "LadyC": [(0, "neutral"), ("@coffee", "happy"), ("@coffee+1.4", "tired"), ("@nobody", "neutral")],
    "Barista": [(0, "happy"), ("@nobody", "neutral"), ("@nobody+2.6", "smug")],
    "Dad": [(0, "neutral"), ("@couch", "grin"), ("@couch+2.4", "smug"), ("@cat", "neutral")],
    "Mom": [(0, "neutral"), ("@couch", "tired"), ("@cat", "happy"), ("@cat.end-1.4", "shocked")],
    "TimmyR": [(0, "neutral"), ("@me", "happy"), ("@me.end-2.0", "angry"), ("@piggy", "angry"), ("@piggy+2.0", "grin"),
               ("@forgot", "shocked"), ("@forgot.end-1.6", "scared")],
    "PrestonS": [(0, "smug"), ("@preston.end-1.2", "shocked"), ("@again", "grin"), ("@again.end-1.0", "crying")],
    "TimmyS": [(0, "neutral"), ("@bike", "shocked"), ("@bike+2.2", "love"), ("@choose", "tired"), ("@choose+2.6", "neutral"),
               ("@zero", "happy"), ("@zero.end-1.4", "sad")],
    "TimmyC": [(0, "neutral"), ("@ask", "happy"), ("@laptop.end-1.2", "shocked"), ("@monday", "neutral"),
               ("@thirty", "shocked"), ("@nice", "grin")],
    "Maya": [(0, "neutral"), ("@laptop", "happy"), ("@thirty", "grin"), ("@nice", "grin")],
    "Leo": [(0, "neutral"), ("@laptop+2.4", "happy"), ("@laptop.end-1.2", "crying"), ("@thirty", "grin"), ("@nice", "grin")],
    "PrestonC": [(0, "smug"), ("@thirty", "grin"), ("@words", "smug"), ("@nice", "shocked"), ("@nice+1.4", "crying")],
    "Grandma": [(0, "neutral"), ("@sense", "happy"), ("@opened", "shocked"), ("@opened+1.6", "love"), ("@cried", "crying"),
                ("@cried+2.4", "love"), ("@forever", "happy")],
    "TimmyK": [(0, "neutral"), ("@sense", "sad"), ("@opened", "neutral"), ("@cried+2.4", "love"), ("@warm", "shocked"),
               ("@forever", "grin")],
}

# objects from other episodes' street/bakery sets that must stay out of shot (an object with no show spans is hidden)
HIDE = [["Workspace", "Sets", n] for n in ("PaidBench", "SaleChair0", "SaleChair1", "SaleChair2", "SaleChair3", "CarryChair",
                                           "MomChair", "Jar")] + \
       [["Workspace", "Sets", "ChairMarket", "Sign"], ["Workspace", "Sets", "ChairMarket", "Price"],
        ["Workspace", "Sets", "TimmyRoom", "Poster"]]
PROPS = [{"path": p, "show": []} for p in HIDE] + [
    # A: coffee in the lady's hand the whole cafe scene
    {"path": EP("Coffee"), "show": [[0.0, "@nobody.end+0.5"]], "attach": {"actor": "LadyC", "hand": "Right", "offset": HAND}},
    # B: the cat sits at Mom's feet (always there)
    {"path": EP("Cat"), "show": [["@couch", "@cat.end+0.5"]]},
    # C: piggy bank in Timmy's hands, smashed into a coin pile
    {"path": EP("Piggy"), "show": [["@me", "@piggy+1.2"]], "attach": {"actor": "TimmyR", "hand": "Right", "offset": HAND}},
    {"path": EP("Coins"), "show": [["@piggy+1.2", "@forgot.end+0.5"]]},
    # D: crowns in Preston's hands, the bike, the present
    {"path": EP("CrownA"), "show": [["@preston+1.0", "@again.end+0.5"]], "attach": {"actor": "PrestonS", "hand": "Right", "offset": HAND}},
    {"path": EP("CrownB"), "show": [["@again", "@again.end+0.5"]], "attach": {"actor": "PrestonS", "hand": "Left", "offset": HAND}},
    {"path": EP("Bike"), "show": [["@preston", "@zero.end+0.5"]]},
    {"path": EP("GiftT"), "show": [["@choose", "@zero"]]},
    {"path": EP("GiftT"), "show": [["@zero", "@zero.end+0.5"]], "attach": {"actor": "TimmyS", "hand": "Right", "offset": HAND}},
    # F: the present goes from Timmy to Grandma; she opens it and holds the photo
    {"path": EP("GiftK"), "show": [["@sense", "@sense.end"]], "attach": {"actor": "TimmyK", "hand": "Right", "offset": HAND}},
    {"path": EP("GiftK"), "show": [["@sense.end", "@opened+1.0"]], "attach": {"actor": "Grandma", "hand": "Right", "offset": HAND}},
    {"path": EP("Photo"), "show": [["@opened+1.0", "@cried+2.4"]], "attach": {"actor": "Grandma", "hand": "Right", "offset": [0, -0.5, -0.4, 0, 180, 0]}},
    # E: laptop and phone, then Preston's pile of presents and a present for each kid
    {"path": EP("Laptop"), "show": [["@ask", "@laptop.end+0.5"]], "attach": {"actor": "Maya", "hand": "Right", "offset": HAND}},
    {"path": EP("Phone"), "show": [["@ask", "@laptop.end+0.5"]], "attach": {"actor": "Leo", "hand": "Right", "offset": HAND}},
] + [{"path": EP(f"GiftP{k}"), "show": [["@monday", "@nice.end+2.0"]]} for k in range(1, 6)] + [
    {"path": EP("GiftM"), "show": [["@thirty+1.0", "@nice.end+2.0"]], "attach": {"actor": "Maya", "hand": "Right", "offset": HAND}},
    {"path": EP("GiftL"), "show": [["@thirty+1.0", "@nice.end+2.0"]], "attach": {"actor": "Leo", "hand": "Right", "offset": HAND}},
]

# receipts read out as labels over the buyer's head
FX = [
    {"actor": "LadyC", "kind": "label", "show": [["@coffee+1.0", "@coffee.end+0.4", "11 MINUTES"]]},
    {"actor": "Dad", "kind": "label", "show": [["@couch+0.6", "@couch.end", "6 YEARS"]]},
    {"actor": "Mom", "kind": "label", "show": [["@cat+1.4", "@cat.end+0.4", "DEPENDS ON THE CAT"]]},
    {"actor": "PrestonS", "kind": "label", "show": [["@preston.end-1.2", "@preston.end+0.3", "9 SECONDS"],
                                                     ["@again.end-1.2", "@again.end+0.4", "4 SECONDS"]]},
    {"actor": "Maya", "kind": "label", "show": [["@laptop", "@laptop+2.4", "2 WEEKS"]]},
    {"actor": "Leo", "kind": "label", "show": [["@laptop+2.4", "@laptop.end+0.3", "3 DAYS"]]},
    {"actor": "TimmyS", "kind": "label", "show": [["@bike+3.0", "@bike.end+0.3", "1 SUMMER"],
                                                   ["@zero.end-1.4", "@zero.end+0.3", "0 SECONDS"]]},
    {"actor": "TimmyS", "kind": "sparkle", "show": [["@bike+3.0", "@bike.end"]]},
    {"actor": "TimmyR", "kind": "confetti", "show": [["@piggy+1.2", "@piggy+3.4"]]},
    {"actor": "Grandma", "kind": "hearts", "show": [["@cried+2.4", "@cried.end+0.4"]]},
    {"actor": "TimmyK", "kind": "label", "show": [["@forever", "@forever.end+0.8", "FOREVER"]]},
    {"actor": "TimmyK", "kind": "sparkle", "show": [["@warm.end-1.4", "@forever.end+0.8"]]},
    {"actor": "PrestonC", "kind": "label", "show": [["@nice", "@nice.end+1.6", "NICE TRY"]]},
    {"actor": "PrestonC", "kind": "rain", "show": [["@nice+0.8", "@nice.end+1.6"]]},
]
MUSIC = {"query": "whimsical", "pick": 0, "from": 0, "gain": 0.45}
SFX = [("@rule+0.6", "cash register", 0.5), ("@rule.end-1.2", "shimmer", 0.6), ("@coffee+1.0", "receipt printer", 0.5),
       ("@couch+0.6", "receipt printer", 0.5), ("@couch.end-1.4", "laugh", 0.4), ("@cat+1.4", "cat meow", 0.6),
       ("@preston+1.0", "coins", 0.5), ("@preston.end-1.2", "buzzer", 0.5), ("@again.end-1.2", "buzzer", 0.6),
       ("@laptop+0.4", "ding", 0.4), ("@laptop.end-1.0", "glass break", 0.5), ("@bike+2.2", "bicycle bell", 0.6),
       ("@bike+3.0", "angel choir", 0.5), ("@piggy+1.0", "ceramic smash", 0.7), ("@piggy+1.4", "coins", 0.6),
       ("@forgot", "record scratch", 0.6), ("@choose+1.2", "tick tock", 0.4), ("@zero.end-1.4", "sad trombone", 0.6),
       ("@opened+0.6", "paper rustle", 0.5), ("@cried+2.4", "aww", 0.5), ("@warm", "heartbeat", 0.5),
       ("@forever", "shimmer", 0.7), ("@thirty", "cheer", 0.4), ("@nice", "record scratch", 0.7),
       ("@nice+0.8", "thunder", 0.5)]
