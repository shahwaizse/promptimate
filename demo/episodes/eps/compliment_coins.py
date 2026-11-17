"""In this town, every real compliment you get turns into a gold coin in your pocket. (narration-paced; our own
procedural sets, STATIC = "own": Bakery, Classroom, Bank, Street, Park; own prop library via PLACE)"""
TITLE = "In This Town, Compliments Are Money"
STATIC = "own"
VOICE, SPEED = "tv_M2", 1.0
CAPTIONS = {"size": 120, "highlight": False, "max_words": 2}
KEYWORDS = ["compliment", "gold", "coin", "coins", "millionaire", "buttons", "Forty", "Rosa", "Tedd", "Sterling", "vault",
            "empty", "law", "broke", "Nina", "tie", "blue", "Clink", "crying", "brave", "poorest", "earned"]

# ---- cast: one copy of a character per set (characters don't travel between sets).
# Own-set yaw: 0 faces -Z, 90 faces -X (toward the camera side of every set), 180 faces +Z, -90 faces +X.
CAST = [
    # the bakery (A, floor 0): open floor west of the pastry cases (x 7595.5..7604)
    {"name": "RosaK", "look": "c_grandma", "at": [7601, -1], "yaw": 180},
    {"name": "Gus", "look": "c_man", "at": [7597, 9], "yaw": 0},
    # the classroom (B, floor 0): the open aisle between the front desks and the board (x 6611..6615)
    {"name": "MsPark", "look": "c_teacher", "at": [6613, 1.2], "yaw": 0},
    {"name": "Tedd", "look": "tedd", "at": [6612, -9], "yaw": 180},
    # the bank (C, floor 0): Sterling comes in from the lobby to the open strip behind the tellers, in front of the vault
    {"name": "SterlingB", "look": "c_businessman", "at": [8003.5, -10], "yaw": -90},
    {"name": "NinaB", "look": "wendy", "at": [8002, -12.5], "yaw": -90},
    # the street (D, floor 0.4): the shop-side sidewalk, in the clear stretches between the trees (z -44..-36, -28..-17)
    {"name": "NinaS", "look": "wendy", "at": [7217, -36.5], "yaw": 90},
    {"name": "Walt", "look": "c_grandpa", "at": [7216.5, -27], "yaw": 180},
    {"name": "Bea", "look": "c_lady", "at": [7216.5, -16.5], "yaw": 0},
    # the park (E, floor 0.06): the paved plaza west of the fountain
    {"name": "SterlingP", "look": "c_businessman", "at": [7372, -2], "yaw": -90},
    {"name": "RosaP", "look": "c_grandma", "at": [7379, -7], "yaw": 180},
    {"name": "TeddP", "look": "tedd", "at": [7384, 3], "yaw": 90},
    {"name": "NinaP", "look": "wendy", "at": [7376.5, 3.5], "yaw": -90},
]

# shared prompt strings (identical across episodes: repeated prompts are free)
HAPPY = "a person stands and smiles happily"
SAD = "a person stands alone with their head down, sad"
STARE = "a person stares in surprise"
WALK = "a person walks forward casually"
JOY = "a person jumps up and down with joy, arms in the air"
LAUGH_AT = "a person points forward and laughs"
TALK = "a person stands and talks, gesturing with both hands"
SHRUG = "a person shrugs"
WAVE = "a person waves with their right hand"
NOD = "a person nods slowly"
SHAKE = "a person shakes their head slowly, disappointed"
POINT = "a person points forward sternly"
STOMP = "a person stomps their foot down hard"
BOW = "a person bows deeply"
CRY = "a person covers their face with both hands and cries"
LOOK_SELF = "a person looks down at their own body in shock"
REACH = "a person reaches forward slowly with their right hand"
HUG = "a person steps forward and hugs someone tightly"
POCKET = "a person reaches into their pocket and pulls something out"
FLEX = "a person flexes both arms proudly"
# new in this episode
CLAP = "a person claps their hands excitedly"
THUMBS = "a person gives a thumbs up with their right hand"
SPREAD = "a person spreads both arms wide proudly"
WALK_SAD = "a person walks forward slowly with their head down"
MARCH = "a person marches forward confidently, swinging their arms"
WALK_HAPPY = "a person walks forward happily, swinging their arms"
HIPS = "a person stands with their hands on their hips, unimpressed"
FRUSTRATED = "a person throws both arms up in frustration"
SPIN = "a person turns around in a full circle, showing off"
LOOK_BACK = "a person looks back over their right shoulder"
SHAKE_IT = "a person holds something upside down with both hands and shakes it"
HAND_OUT = "a person holds out their right hand, palm up, with their head down"
POINT_SMILE = "a person points forward with their right hand and smiles"
NO = "a person shakes their head quickly"
HOPE = "a person clasps their hands together in front of their chest"
LOOK_HAND = "a person looks down at their right hand"
HEART = "a person puts their right hand on their chest and smiles"
BELLY = "a person rubs their belly happily"
SNUB = "a person turns away and crosses their arms"

ACTORS = [
    # ---------------------------------------------------------------- A: the bakery
    {"name": "RosaK", "start": [7601, -1], "facing": "+Z", "beats": [
        {"at": 0.0, "prompt": HAPPY, "seconds": 2.4},
        {"at": "@rule+2.2", "prompt": CLAP, "seconds": 1.8, "face": "Gus"},
        {"prompt": JOY, "seconds": 2.4},
        {"at": "@baker+1.2", "prompt": SPREAD, "seconds": 2.0, "face": "-X"},
        {"at": "@baker.end-2.0", "prompt": HUG, "seconds": 2.6, "to": "Gus", "face": "Gus"},
        {"at": "@broke+2.2", "prompt": WALK_SAD, "seconds": 2.0, "to": [7597.5, -1], "face": "-X"},
        {"prompt": CRY, "seconds": 2.6},
        {"at": "@back+2.8", "prompt": JOY, "seconds": 3.0, "face": "-X"},
    ]},
    {"name": "Gus", "start": [7597, 9], "facing": "-Z", "beats": [
        {"at": 0.0, "prompt": WALK, "seconds": 2.2, "to": [7601, 3.6], "face": "RosaK"},
        {"prompt": TALK, "seconds": 2.4},
        {"prompt": THUMBS, "seconds": 2.0},
        {"at": "@baker+1.2", "prompt": BELLY, "seconds": 2.0, "face": "RosaK"},
        {"at": "@baker.end-2.0", "prompt": HUG, "seconds": 2.6, "face": "RosaK"},
    ]},
    # ---------------------------------------------------------------- B: the classroom, forty fake compliments
    {"name": "MsPark", "start": [6613, 1.2], "facing": "-Z", "beats": [
        {"at": "@fake", "prompt": HIPS, "seconds": 3.0},
        {"at": "@tedd", "prompt": SHAKE, "seconds": 2.4, "face": "Tedd"},
        {"prompt": LOOK_SELF, "seconds": 2.2},
        {"at": "@sewed", "prompt": SPIN, "seconds": 2.6},
        {"prompt": SHRUG, "seconds": 1.8, "face": "Tedd"},
    ]},
    {"name": "Tedd", "start": [6612, -9], "facing": "+Z", "beats": [
        {"at": "@fake-0.4", "prompt": WALK, "seconds": 2.0, "to": [6612.5, -3.2], "face": "MsPark"},
        {"prompt": THUMBS, "seconds": 1.6},
        {"at": "@tedd", "prompt": TALK, "seconds": 2.2},
        {"prompt": BOW, "seconds": 1.8},
        {"prompt": FRUSTRATED, "seconds": 2.2},
        {"at": "@sewed+1.4", "prompt": LAUGH_AT, "seconds": 2.4, "face": "MsPark"},
    ]},
    # ---------------------------------------------------------------- C: the bank
    {"name": "SterlingB", "start": [8003.5, -10], "facing": "+X", "beats": [
        {"at": "@banker-0.2", "prompt": WALK, "seconds": 2.6, "to": [8014, -13], "via": [[8013.5, -9.8]], "face": "-X"},
        {"prompt": SPREAD, "seconds": 1.8},
        {"at": "@empty", "prompt": LOOK_BACK, "seconds": 2.0},
        {"prompt": SAD, "seconds": 2.8, "face": "-X"},
        {"at": "@law", "prompt": STOMP, "seconds": 1.8},
        {"prompt": POINT, "seconds": 2.0},
        {"prompt": SHAKE_IT, "seconds": 2.6},
        {"at": "@hand", "prompt": HAND_OUT, "seconds": 3.4, "face": "+Z"},
        {"at": "@said+1.0", "prompt": STARE, "seconds": 2.6, "face": "NinaB"},
        {"at": "@clink", "prompt": LOOK_SELF, "seconds": 1.6},
        {"prompt": POCKET, "seconds": 2.2},
        {"at": "@cry", "prompt": LOOK_HAND, "seconds": 2.2},
        {"prompt": CRY, "seconds": 2.4},
        {"at": "@back", "prompt": JOY, "seconds": 2.8, "face": "-X"},
        {"at": "@brave", "prompt": POINT_SMILE, "seconds": 2.2, "face": "NinaB"},
        {"prompt": NOD, "seconds": 2.0},
        {"at": "@end+3.4", "prompt": HEART, "seconds": 3.0, "face": "-X"},
    ]},
    {"name": "NinaB", "start": [8002, -12.5], "facing": "+X", "beats": [
        {"at": "@hand-0.4", "prompt": MARCH, "seconds": 2.8, "to": [8013.5, -8.8], "via": [[8008.5, -9.8]], "face": "SterlingB"},
        {"at": "@said", "prompt": NO, "seconds": 1.6},
        {"prompt": POINT_SMILE, "seconds": 2.4, "face": "SterlingB"},
        {"at": "@clink", "prompt": HOPE, "seconds": 2.6},
        {"at": "@cry+1.6", "prompt": REACH, "seconds": 2.4},
        {"at": "@brave+1.8", "prompt": LOOK_SELF, "seconds": 1.6},
        {"prompt": JOY, "seconds": 3.0, "face": "-X"},
    ]},
    # ---------------------------------------------------------------- D: the street
    # two neighbours meet on the sidewalk and say nothing nice: they turn their backs
    {"name": "Walt", "start": [7216.5, -27], "facing": "+Z", "beats": [
        {"at": "@broke-0.2", "prompt": WALK_SAD, "seconds": 2.6, "to": [7216.5, -23.5], "face": "Bea"},
        {"prompt": SNUB, "seconds": 2.4},
        {"at": "@broke.end-1.8", "prompt": SHRUG, "seconds": 2.0, "face": "-X"},
    ]},
    {"name": "Bea", "start": [7216.5, -16.5], "facing": "-Z", "beats": [
        {"at": "@broke-0.2", "prompt": WALK_SAD, "seconds": 2.2, "to": [7216.5, -19.5], "face": "Walt"},
        {"prompt": SNUB, "seconds": 2.4},
        {"at": "@broke.end-1.6", "prompt": SHAKE, "seconds": 2.2, "face": "-X"},
    ]},
    {"name": "NinaS", "start": [7217, -36.5], "facing": "-X", "beats": [
        {"at": "@me", "prompt": WAVE, "seconds": 1.6},
        {"prompt": FLEX, "seconds": 1.4, "face": "-Z"},
        {"prompt": MARCH, "seconds": 3.0, "to": [7217, -43.5], "face": "-Z"},
    ]},
    # ---------------------------------------------------------------- E: the park, the poorest man in town
    {"name": "SterlingP", "start": [7372, -2], "facing": "+X", "beats": [
        {"at": "@end-0.2", "prompt": WALK_HAPPY, "seconds": 2.6, "to": [7380, -1.5], "face": "RosaP"},
        {"prompt": WAVE, "seconds": 1.8},
        {"prompt": POINT_SMILE, "seconds": 2.2, "face": "TeddP"},
    ]},
    {"name": "RosaP", "start": [7379, -7], "facing": "+Z", "beats": [
        {"at": "@end+1.6", "prompt": WAVE, "seconds": 1.8, "face": "SterlingP"},
        {"prompt": JOY, "seconds": 2.6},
    ]},
    {"name": "TeddP", "start": [7384, 3], "facing": "-X", "beats": [
        {"at": "@end+2.6", "prompt": CLAP, "seconds": 2.4, "face": "SterlingP"},
        {"prompt": JOY, "seconds": 2.6},
    ]},
    {"name": "NinaP", "start": [7376.5, 3.5], "facing": "+X", "beats": [
        {"at": "@end", "prompt": WAVE, "seconds": 2.0, "face": "SterlingP"},
        {"prompt": HAPPY, "seconds": 2.4},
    ]},
]

LINES = [
    {"id": "rule", "text": "In this town, every time someone gives you a real compliment, a gold coin drops into your pocket."},
    {"id": "baker", "text": "That's why Grandma Rosa at the bakery is a millionaire. Everyone says her bread tastes like a hug."},
    {"id": "fake", "text": "But you have to mean it. Fake compliments pay in buttons.", "gap": 0.3},
    {"id": "tedd", "text": "My friend Tedd told our teacher he loved her sweater. Forty times. Forty buttons."},
    {"id": "sewed", "text": "She sewed them all onto the sweater. Now it's mostly buttons."},
    {"id": "banker", "text": "And then there's Mr. Sterling. He owns the bank, and the biggest vault in town.", "gap": 0.4},
    {"id": "empty", "text": "It's completely empty. In thirty years, nobody has said one nice thing to him."},
    {"id": "law", "text": "So he made a new law. Every coin in town goes into his vault. Even the ones in your piggy bank.",
     "gap": 0.3},
    {"id": "broke", "text": "By Friday, the whole town was broke. Grandma Rosa sold her oven. People stopped saying nice things. "
                            "What was the point?"},
    {"id": "me", "text": "I'm Nina. I had one coin left, and I marched it straight to the bank.", "gap": 0.4},
    {"id": "hand", "text": "Mr. Sterling held out his hand. He didn't even look up."},
    {"id": "said", "text": "But I didn't give him my coin. I said, I like your tie. It's the same blue as my grandpa's.",
     "gap": 0.3},
    {"id": "clink", "text": "Clink. A gold coin dropped into his pocket. His very first one.", "gap": 0.4},
    {"id": "cry", "text": "He stared at it for a whole minute. Then the grumpiest man in town started crying."},
    {"id": "back", "text": "That afternoon, he opened the vault and gave every coin back. Grandma Rosa bought her oven back.",
     "gap": 0.3},
    {"id": "brave", "text": "Then he looked at me and said, you're a very brave kid. And my pocket went clink."},
    {"id": "end", "text": "Now Mr. Sterling is the poorest man in town. His vault holds exactly one coin. He says it's the "
                          "first thing in there he ever earned.", "gap": 0.4},
]
TITLES = [("@rule+2.6", "@rule.end+0.3", "COMPLIMENTS"), ("@clink", "@clink.end+0.6", "CLINK")]

# ---- own prop library (D:\tmp\headless\own\props.json), cloned to workspace.Sets.EpisodeProps.<name>; y = the set's
# floor_y. Props are obstacles for staging even while hidden, so held props wait at home off every walking line.
COIN = 0.35      # one gold coin: a coin pile scaled down to a single small stack
PLACE = [
    # A: the bakery. Rosa's fortune piles up at her feet; Gus's loaf of bread
    {"prop": "coin_pile", "at": [7603, -2.6], "y": 0.0, "yaw": 20, "name": "CoinsR1"},
    {"prop": "coin_pile", "at": [7602.8, -5.6], "y": 0.0, "yaw": -30, "name": "CoinsR2"},
    {"prop": "gold_bars", "at": [7598.6, -3.8], "y": 0.0, "yaw": 15, "name": "BarsR"},
    {"prop": "cash_stack", "at": [7598.6, 1.8], "y": 0.0, "yaw": -10, "name": "CashR"},
    {"prop": "bread", "at": [7596.5, -7], "y": 0.0, "yaw": 0, "name": "Bread"},
    # C: the bank. The law fills the floor in front of the vault; the piggy bank; the coins in the story
    {"prop": "coin_pile", "at": [8013.8, -4.6], "y": 0.0, "yaw": 0, "name": "VaultC1"},
    {"prop": "coin_pile", "at": [8011.2, -4.6], "y": 0.0, "yaw": 40, "name": "VaultC2"},
    {"prop": "gold_bars", "at": [8012.5, -5.6], "y": 0.0, "yaw": 90, "name": "VaultBars"},
    {"prop": "piggy_bank", "at": [8010.6, -6.4], "y": 0.0, "yaw": 90, "name": "Piggy"},
    {"prop": "coin_pile", "at": [8014.5, -15.4], "y": 0.0, "yaw": 0, "height": COIN, "name": "CoinS"},
    {"prop": "coin_pile", "at": [8001, -14], "y": 0.0, "yaw": 0, "height": COIN, "name": "CoinNB"},
    {"prop": "coin_pile", "at": [8014.5, -10.4], "y": 0.0, "yaw": 0, "height": COIN, "name": "CoinV"},
    # D: the street, Nina's last coin
    {"prop": "coin_pile", "at": [7215, -5], "y": 0.4, "yaw": 0, "height": COIN, "name": "CoinN"},
]


def EP(n):
    return ["Workspace", "Sets", "EpisodeProps", n]


HAND = [0, -0.6, -0.3, 0, 0, 0]

CAMERAS = [
    # A: the bakery. Hook: Rosa beaming at a compliment, from frame one
    {"name": "hook", "start": 0.0, "subject": "RosaK", "shot": "close", "angle": 0},
    {"name": "compliment", "start": "@rule+1.8", "subject": "Gus", "with": "RosaK", "shot": "medium", "angle": 30},
    {"name": "gold coin", "start": "@rule+3.1", "prop": "CoinsR1", "shot": "close", "angle": 0},
    {"name": "bakery", "start": "@baker", "pos": [7590, 7.5, -1], "look": [7601, 3, -1], "fov": 55, "subjects": []},
    {"name": "millionaire", "start": "@baker+1.6", "prop": "BarsR", "shot": "close", "angle": 0},
    {"name": "tastes like a hug", "start": "@baker.end-2.2", "subject": "RosaK", "with": "Gus", "shot": "full", "angle": 0},
    # B: the classroom
    {"name": "classroom", "start": "@fake", "pos": [6596, 8, -1], "look": [6612.5, 3, -1], "fov": 52, "subjects": []},
    {"name": "fake", "start": "@fake+1.8", "subject": "Tedd", "shot": "medium", "angle": 20},
    {"name": "teacher", "start": "@tedd", "subject": "MsPark", "shot": "close", "angle": 0},
    {"name": "forty times", "start": "@tedd+2.2", "subject": "Tedd", "shot": "medium", "angle": -15},
    {"name": "forty buttons", "start": "@tedd.end-1.4", "subject": "MsPark", "shot": "medium", "angle": 10},
    {"name": "sewed", "start": "@sewed", "subject": "MsPark", "with": "Tedd", "shot": "full", "angle": 0},
    {"name": "tedd laughs", "start": "@sewed.end-1.2", "subject": "Tedd", "shot": "close", "angle": 10},
    # C: the bank. Sterling walks in to the vault
    {"name": "the bank", "start": "@banker", "pos": [8000, 8, -9.5], "look": [8013, 4, -10.5], "fov": 58, "subjects": []},
    {"name": "biggest vault", "start": "@banker.end-1.6", "subject": "SterlingB", "shot": "full", "angle": 0},
    {"name": "empty", "start": "@empty", "subject": "SterlingB", "shot": "medium", "angle": 30},
    {"name": "nobody", "start": "@empty+2.0", "subject": "SterlingB", "shot": "close", "angle": 0},
    {"name": "new law", "start": "@law", "subject": "SterlingB", "shot": "close", "angle": -10},
    {"name": "every coin", "start": "@law+1.8", "prop": "VaultBars", "shot": "medium", "angle": 0},
    {"name": "piggy bank", "start": "@law.end-1.8", "prop": "Piggy", "shot": "close", "angle": 0},
    # D: the street, A: the bakery. Broke
    {"name": "street", "start": "@broke", "pos": [7194, 8, -21.5], "look": [7216.5, 3.5, -21.5], "fov": 55, "subjects": []},
    {"name": "oven", "start": "@broke+2.2", "subject": "RosaK", "shot": "medium", "angle": 20},
    {"name": "rosa cries", "start": "@broke+4.2", "subject": "RosaK", "shot": "close", "angle": 0},
    {"name": "what was the point", "start": "@broke.end-1.6", "subject": "Walt", "with": "Bea", "shot": "full", "angle": 0},
    # D: the street. Nina
    {"name": "i'm nina", "start": "@me", "subject": "NinaS", "shot": "close", "angle": 0},
    {"name": "one coin", "start": "@me+1.4", "prop": "CoinN", "shot": "close", "angle": 0},
    {"name": "marched", "start": "@me+2.6", "pos": [7190, 8, -40], "look": [7217, 3.5, -40], "fov": 55, "subjects": []},
    # C: the bank. The compliment
    {"name": "held out his hand", "start": "@hand", "subject": "SterlingB", "shot": "medium", "angle": 20},
    {"name": "didn't look up", "start": "@hand.end-1.4", "subject": "SterlingB", "shot": "close", "angle": 0},
    {"name": "my coin", "start": "@said", "prop": "CoinNB", "shot": "close", "angle": 0},
    {"name": "i like your tie", "start": "@said+1.6", "subject": "NinaB", "shot": "close", "angle": 0},
    {"name": "same blue", "start": "@said.end-2.4", "subject": "SterlingB", "shot": "medium", "angle": 0},
    {"name": "clink", "start": "@clink", "subject": "SterlingB", "shot": "close", "angle": 0},
    {"name": "first coin", "start": "@clink+2.0", "prop": "CoinS", "shot": "close", "angle": 0},
    {"name": "stared", "start": "@cry", "subject": "SterlingB", "with": "NinaB", "shot": "full", "angle": 30},
    {"name": "crying", "start": "@cry+2.4", "subject": "SterlingB", "shot": "close", "angle": -10},
    {"name": "vault open", "start": "@back", "pos": [8000, 8, -9.5], "look": [8013, 4, -8.5], "fov": 58, "subjects": []},
    # A: the bakery. The oven comes back
    {"name": "rosa's oven", "start": "@back+2.8", "subject": "RosaK", "shot": "medium", "angle": 0},
    # C: the bank. Brave
    {"name": "brave kid", "start": "@brave", "subject": "SterlingB", "shot": "close", "angle": 15},
    {"name": "my pocket", "start": "@brave+2.0", "subject": "NinaB", "shot": "medium", "angle": 0},
    {"name": "clink again", "start": "@brave.end-1.4", "subject": "NinaB", "shot": "close", "angle": 10},
    # E: the park, then the vault
    {"name": "park", "start": "@end", "pos": [7362, 7, -1], "look": [7380, 3, -1], "fov": 55, "subjects": []},
    {"name": "poorest man", "start": "@end+1.8", "subject": "SterlingP", "with": "RosaP", "shot": "medium", "angle": 0},
    {"name": "one coin left", "start": "@end+2.8", "prop": "CoinV", "shot": "close", "angle": 0},
    {"name": "ever earned", "start": "@end+4.4", "subject": "SterlingB", "shot": "close", "angle": 0},
]

FACES = {
    "RosaK": [(0, "happy"), ("@rule+2.2", "grin"), ("@rule.end-0.4", "love"), ("@baker+0.6", "smug"),
              ("@baker.end-2.4", "love"), ("@broke+2.2", "sad"), ("@broke+4.2", "crying"), ("@back+2.8", "grin")],
    "Gus": [(0, "happy"), ("@rule+2.0", "grin"), ("@baker+2.0", "love"), ("@baker.end-2.2", "happy")],
    "MsPark": [(0, "neutral"), ("@fake", "smug"), ("@tedd", "tired"), ("@tedd+2.4", "shocked"), ("@sewed", "happy"),
               ("@sewed+2.6", "smug")],
    "Tedd": [(0, "neutral"), ("@fake", "grin"), ("@fake+2.0", "wink"), ("@tedd+2.2", "happy"), ("@tedd.end-1.6", "angry"),
             ("@sewed+1.4", "grin")],
    "SterlingB": [(0, "smug"), ("@banker+3.0", "smug"), ("@empty", "neutral"), ("@empty+2.0", "sad"), ("@law", "angry"),
                  ("@law.end-1.8", "smug"), ("@hand", "tired"), ("@said+1.0", "shocked"), ("@clink", "shocked"),
                  ("@cry", "neutral"), ("@cry+2.2", "crying"), ("@back", "grin"), ("@brave", "happy"), ("@end", "love")],
    "NinaB": [(0, "neutral"), ("@hand-0.4", "angry"), ("@said", "neutral"), ("@said+1.6", "happy"), ("@clink", "shocked"),
              ("@cry+1.6", "sad"), ("@brave", "shocked"), ("@brave+3.4", "grin")],
    "Walt": [(0, "sad"), ("@broke+2.4", "angry"), ("@broke.end-1.8", "tired")],
    "Bea": [(0, "sad"), ("@broke+2.0", "angry"), ("@broke.end-1.6", "tired")],
    "NinaS": [(0, "happy"), ("@me+1.4", "neutral"), ("@me+2.6", "angry")],
    "SterlingP": [(0, "grin"), ("@end+2.6", "happy")],
    "RosaP": [(0, "happy"), ("@end+1.6", "grin")],
    "TeddP": [(0, "happy"), ("@end+2.6", "grin")],
    "NinaP": [(0, "happy"), ("@end+2.0", "love")],
}

TO_END = "@end.end+2.0"
PROPS = [
    # A: one coin lands at Rosa's feet, then a fortune; the law takes it all; it comes back with the vault
    {"path": EP("CoinsR1"), "show": [["@rule+3.0", "@law+3.0"], ["@back+2.6", TO_END]]},
    {"path": EP("CoinsR2"), "show": [["@baker+0.6", "@law+3.0"], ["@back+2.6", TO_END]]},
    {"path": EP("BarsR"), "show": [["@baker+0.6", "@law+3.0"], ["@back+2.6", TO_END]]},
    {"path": EP("CashR"), "show": [["@baker+0.6", "@law+3.0"], ["@back+2.6", TO_END]]},
    {"path": EP("Bread"), "show": [["@baker+1.6", "@fake"]], "attach": {"actor": "Gus", "hand": "Left", "offset": HAND}},
    # C: the vault fills up with the town's money under the new law, and empties when he gives it back
    {"path": EP("VaultC1"), "show": [["@law+1.6", "@back+1.2"]]},
    {"path": EP("VaultC2"), "show": [["@law+1.6", "@back+1.2"]]},
    {"path": EP("VaultBars"), "show": [["@law+1.6", "@back+1.2"]]},
    {"path": EP("Piggy"), "show": [["@law+3.4", "@law.end+0.4"]], "attach": {"actor": "SterlingB", "hand": "Right", "offset": HAND}},
    # D, C: Nina's last coin in her hand on the street and in the bank
    {"path": EP("CoinN"), "show": [["@me", "@me.end+0.5"]], "attach": {"actor": "NinaS", "hand": "Right", "offset": HAND}},
    {"path": EP("CoinNB"), "show": [["@hand-0.4", TO_END]], "attach": {"actor": "NinaB", "hand": "Right", "offset": HAND}},
    # C: Sterling's first coin out of his pocket; later the only coin in the vault
    {"path": EP("CoinS"), "show": [["@clink+1.6", "@cry+2.2"]], "attach": {"actor": "SterlingB", "hand": "Right", "offset": HAND}},
    {"path": EP("CoinV"), "show": [["@end", TO_END]]},
]

FX = [
    {"actor": "RosaK", "kind": "label", "show": [["@rule+3.0", "@rule.end+0.3", "+1 COIN"],
                                                  ["@baker+1.0", "@baker+3.6", "MILLIONAIRE"],
                                                  ["@broke+2.4", "@broke+5.4", "OVEN: SOLD"],
                                                  ["@back+3.0", "@back.end+0.3", "OVEN: BACK"]]},
    {"actor": "RosaK", "kind": "sparkle", "show": [["@rule+3.0", "@baker+3.6"]]},
    {"actor": "RosaK", "kind": "rain", "show": [["@broke+4.2", "@broke.end"]]},
    {"actor": "RosaK", "kind": "confetti", "show": [["@back+3.0", "@back.end+0.6"]]},
    {"actor": "Gus", "kind": "hearts", "show": [["@baker.end-1.8", "@baker.end+0.4"]]},
    {"actor": "Tedd", "kind": "label", "show": [["@fake+2.0", "@fake.end+0.3", "FAKE = BUTTON"]]},
    {"actor": "MsPark", "kind": "label", "show": [["@tedd+2.6", "@tedd.end+0.4", "40 BUTTONS"],
                                                   ["@sewed+1.0", "@sewed.end+0.3", "MOSTLY BUTTONS"]]},
    {"actor": "SterlingB", "kind": "label", "show": [["@empty+0.4", "@empty.end+0.3", "0 COINS"],
                                                      ["@law+1.6", "@law.end-1.8", "ALL COINS: MINE"],
                                                      ["@clink+2.0", "@clink.end+0.4", "1 COIN"],
                                                      ["@end+4.4", "@end.end+1.6", "1 COIN"]]},
    {"actor": "SterlingB", "kind": "rain", "show": [["@empty+2.0", "@empty.end+0.3"]]},
    {"actor": "SterlingB", "kind": "sparkle", "show": [["@clink", "@clink.end+0.4"], ["@end+4.4", "@end.end+1.6"]]},
    {"actor": "SterlingB", "kind": "confetti", "show": [["@back", "@back+2.6"]]},
    {"actor": "Walt", "kind": "label", "show": [["@broke+0.4", "@broke+2.2", "0 COINS"]]},
    {"actor": "NinaS", "kind": "label", "show": [["@me+1.4", "@me+3.2", "1 COIN"]]},
    {"actor": "NinaB", "kind": "label", "show": [["@said+1.6", "@said.end-2.4", "I LIKE YOUR TIE"],
                                                  ["@brave+2.6", "@brave.end+0.6", "+1 COIN"]]},
    {"actor": "NinaB", "kind": "hearts", "show": [["@cry+1.6", "@cry.end+0.3"]]},
    {"actor": "NinaB", "kind": "sparkle", "show": [["@brave+2.6", "@brave.end+0.6"]]},
    {"actor": "SterlingP", "kind": "label", "show": [["@end+0.6", "@end+2.8", "POOREST MAN IN TOWN"]]},
    {"actor": "SterlingP", "kind": "hearts", "show": [["@end+1.8", "@end+2.8"]]},
]
MUSIC = {"query": "whimsical", "pick": 0, "from": 0, "gain": 0.45}
SFX = [("@rule+0.4", "shop bell", 0.5), ("@rule+3.0", "coin drop", 0.7), ("@baker+0.8", "cash register", 0.6),
       ("@baker.end-1.8", "aww", 0.5), ("@fake+2.0", "boing", 0.5), ("@tedd+2.6", "buzzer", 0.5),
       ("@sewed+1.4", "laugh", 0.4), ("@banker+3.0", "fanfare", 0.4), ("@empty+0.6", "crickets", 0.5),
       ("@law", "stomp", 0.6), ("@law+1.6", "coins", 0.6), ("@law.end-1.6", "coins", 0.5),
       ("@broke", "sad trombone", 0.5), ("@broke+4.2", "sad violin", 0.4), ("@me+2.6", "drumroll", 0.4),
       ("@hand.end-1.4", "clock ticking", 0.4), ("@said+1.6", "record scratch", 0.5), ("@clink", "coin drop", 0.8),
       ("@clink+2.0", "shimmer", 0.6), ("@cry+2.4", "sad violin", 0.4), ("@back", "cheer", 0.5),
       ("@back+3.0", "ding", 0.5), ("@brave.end-1.2", "coin drop", 0.8), ("@end+0.6", "whistle", 0.4),
       ("@end+4.4", "angel choir", 0.5)]
