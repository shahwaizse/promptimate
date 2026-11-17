"""In this town, every compliment you give becomes a gold sticker on the other person's forehead. (narration-paced)"""
TITLE = "In This Town, Compliments Become Gold Stars On Your Forehead"
VOICE, SPEED = "tv_M2", 1.0
CAPTIONS = {"size": 80, "highlight": False, "max_words": 3}
KEYWORDS = ["compliment", "star", "stars", "ding", "Leo", "Timmy", "Preston", "zero", "pizza", "sweep"]

# ---- cast: classic blocky characters; one copy of a character per set (characters don't travel between lots)
CAST = [
    # town street around the bench (A, C)
    {"name": "Lady", "look": "c_lady", "at": [-12, 6], "yaw": -90},
    {"name": "Man", "look": "c_man", "at": [-8.5, 6], "yaw": 90},
    {"name": "Girl", "look": "c_girl", "at": [4, 9.5]},
    {"name": "Preston", "look": "c_preston", "at": [7, 6.5], "yaw": 90},
    {"name": "Leo", "look": "c_kid", "at": [-0.5, 5], "yaw": 180},
    {"name": "Timmy", "look": "c_timmy", "at": [-6, 9.5], "yaw": -90},
    # Timmy's room (B)
    {"name": "TimmyR", "look": "c_timmy", "at": [456, -4.5], "yaw": 180},
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
BOW = "a person bows deeply"
COUNT = "a person stands and counts something on the table, concentrating"
SIT_DOWN = "a person turns around and sits down"
SIT_SAD = "a person sits alone, head down, sad"
STAND_UP = "a person stands up slowly"
SWEEP = "a person sweeps the ground with a broom, moving slowly"

BENCH = "Bench"

ACTORS = [
    # ---------------------------------------------------------------- A + C: the street
    {"name": "Lady", "start": [-12, 6], "facing": "+X", "beats": [
        {"at": 0.0, "prompt": TALK, "seconds": 2.6, "face": "Man"},
        {"prompt": HAPPY, "seconds": 3.0, "face": "Man"},
        {"at": "@legend", "prompt": TALK, "seconds": 2.6, "face": "Man"},
        {"prompt": JOY, "seconds": 3.0},
        {"at": "@suit", "prompt": TALK, "seconds": 2.0, "face": "Leo"},
        {"at": "@joke+1.4", "prompt": STARE, "seconds": 3.0, "face": "Leo"},
        {"at": "@everyone", "prompt": TALK, "seconds": 2.0, "face": "Leo"},
        {"prompt": HAPPY, "seconds": 3.0, "face": "Leo"},
    ]},
    {"name": "Man", "start": [-8.5, 6], "facing": "-X", "beats": [
        {"at": "@rule+1.2", "prompt": STARE, "seconds": 2.0, "face": "Lady"},
        {"prompt": HAPPY, "seconds": 3.0, "face": "Lady"},
        {"at": "@size", "prompt": WAVE, "seconds": 1.6, "face": "Lady"},
        {"at": "@legend+1.6", "prompt": JOY, "seconds": 3.0},
        {"at": "@suit", "prompt": TALK, "seconds": 2.0, "face": "Leo"},
        {"at": "@joke+1.4", "prompt": STARE, "seconds": 3.0, "face": "Leo"},
        {"at": "@everyone+0.8", "prompt": TALK, "seconds": 2.0, "face": "Leo"},
        {"prompt": HAPPY, "seconds": 3.0, "face": "Leo"},
    ]},
    {"name": "Girl", "start": [4, 9.5], "facing": "+Z", "beats": [
        {"at": "@fake", "prompt": STARE, "seconds": 1.6, "face": "Preston"},
        {"prompt": SHRUG, "seconds": 1.6, "face": "Preston"},
        {"at": "@legend+1.6", "prompt": JOY, "seconds": 3.0},
        {"at": "@preston", "prompt": TALK, "seconds": 2.0, "face": "Preston"},
        {"at": "@joke+1.4", "prompt": STARE, "seconds": 3.0, "face": "Leo"},
        {"at": "@pigeon", "prompt": TALK, "seconds": 2.4, "face": "Leo"},
        {"prompt": HAPPY, "seconds": 3.0, "face": "Leo"},
        {"at": "@count", "prompt": IDLE, "seconds": 3.0, "face": "Leo"},
    ]},
    {"name": "Preston", "start": [7, 6.5], "facing": "-X", "beats": [
        {"at": "@fake", "prompt": TALK, "seconds": 1.6, "face": "Girl"},
        {"prompt": SHRUG, "seconds": 1.6, "face": "Girl"},
        {"at": "@preston", "prompt": SMUG, "seconds": 3.0, "face": "Girl"},
        {"at": "@paid", "prompt": WALK, "seconds": 1.6, "to": [2.5, 5.5], "face": "Leo"},
        {"prompt": TALK, "seconds": 2.0, "face": "Leo"},
        {"prompt": SHRUG, "seconds": 1.6, "face": "Leo"},
        {"at": "@joke+1.4", "prompt": STARE, "seconds": 3.0, "face": "Leo"},
        {"at": "@everyone+1.6", "prompt": NOD, "seconds": 2.0, "face": "Leo"},
        {"at": "@count", "prompt": SMUG, "seconds": 3.0, "face": "Leo"},
        {"at": "@fewest+1.2", "prompt": LAUGH, "seconds": 2.6, "face": "Timmy"},
    ]},
    {"name": "Leo", "start": [-0.5, 5], "facing": "-Z", "beats": [
        {"at": "@lunch", "prompt": [SIT_DOWN, SIT_SAD], "seconds": [1.5, 3.0], "sit": BENCH, "sit_from": 1.2},
        {"prompt": SIT_SAD, "seconds": 4.0, "sit": BENCH},
        {"at": "@leo", "prompt": SIT_SAD, "seconds": 4.0, "sit": BENCH},
        {"prompt": SIT_SAD, "seconds": 4.0, "sit": BENCH},
        {"at": "@paid+1.6", "prompt": SIT_SAD, "seconds": 3.0, "sit": BENCH},
        {"at": "@suit", "prompt": STAND_UP, "seconds": 1.6, "face": "+Z"},
        {"prompt": HAPPY, "seconds": 2.4, "face": "Lady"},
        {"at": "@joke", "prompt": TALK, "seconds": 2.6, "face": "+Z"},
        {"prompt": SAD, "seconds": 2.6, "face": "+Z"},
        {"at": "@best", "prompt": STARE, "seconds": 2.6, "face": "Timmy"},
        {"at": "@ding2", "prompt": JOY, "seconds": 3.0},
        {"at": "@pigeon", "prompt": HAPPY, "seconds": 2.6, "face": "Girl"},
        {"at": "@everyone", "prompt": BOW, "seconds": 1.8, "face": "Lady"},
        {"prompt": HAPPY, "seconds": 2.6, "face": "+Z"},
        {"at": "@count", "prompt": JOY, "seconds": 3.0},
        {"at": "@sweep", "prompt": SWEEP, "seconds": 4.0, "face": "+X"},
        {"at": "@twist+1.2", "prompt": JOY, "seconds": 3.0, "face": "Timmy"},
    ]},
    {"name": "Timmy", "start": [-6, 9.5], "facing": "+X", "beats": [
        {"at": "@me", "prompt": WAVE, "seconds": 1.8, "face": "+Z"},
        {"prompt": HAPPY, "seconds": 2.0, "face": "+Z"},
        {"at": "@friday", "prompt": FISTS, "seconds": 3.4, "face": "Leo"},
        {"at": "@paid", "prompt": GIVE, "seconds": 1.6, "face": "Preston"},
        {"at": "@paid.end-1.0", "prompt": SAD, "seconds": 2.0, "face": "Leo"},
        {"at": "@suit+2.2", "prompt": JOY, "seconds": 1.8},
        {"prompt": SHRUG, "seconds": 1.6, "face": "Leo"},
        {"at": "@joke+1.4", "prompt": STARE, "seconds": 3.0, "face": "Leo"},
        {"at": "@card+2.0", "prompt": WALK, "seconds": 1.8, "to": [-3.5, 4.5], "face": "Leo"},
        {"at": "@best", "prompt": TALK, "seconds": 2.6, "face": "Leo"},
        {"prompt": TALK, "seconds": 2.0, "face": "Leo"},
        {"at": "@ding2", "prompt": HAPPY, "seconds": 3.0, "face": "Leo"},
        {"at": "@count", "prompt": HAPPY, "seconds": 3.0, "face": "Leo"},
        {"at": "@fewest", "prompt": STARE, "seconds": 1.6, "face": "+Z"},
        {"prompt": SAD, "seconds": 2.4, "face": "+Z"},
        {"at": "@sweep", "prompt": SWEEP, "seconds": 4.0, "face": "+X"},
        {"at": "@twist", "prompt": TALK, "seconds": 2.0, "face": "Leo"},
        {"prompt": HAPPY, "seconds": 3.0, "face": "Leo"},
    ]},
    # ---------------------------------------------------------------- B: Timmy's room, Thursday night
    {"name": "TimmyR", "start": [456, -4.5], "facing": "-Z", "beats": [
        {"at": "@night", "prompt": COUNT, "seconds": 2.6},
        {"prompt": SAD, "seconds": 2.0, "face": "+Z"},
        {"at": "@card", "prompt": FISTS, "seconds": 3.4, "face": "+Z"},
    ]},
]

CAMERAS = [
    # one cue per story moment (the recorder adds coverage cuts and push-ins); fixed shots for sets
    # A: the rule
    {"name": "compliment", "start": 0.0, "subject": "Lady", "with": "Man", "shot": "medium", "angle": 0},
    {"name": "ding", "start": "@ding", "subject": "Man", "shot": "close", "angle": 15},
    {"name": "fake", "start": "@fake", "subject": "Preston", "with": "Girl", "shot": "medium", "angle": 0},
    {"name": "falls off", "start": "@fake.end-1.0", "subject": "Girl", "shot": "close", "angle": -15},
    {"name": "nice shoes", "start": "@size", "subject": "Man", "shot": "close", "angle": -20},
    {"name": "marching band", "start": "@legend", "pos": [-2, 6, 26], "look": [-2, 3.5, 5], "fov": 54, "subjects": []},
    {"name": "glowed", "start": "@legend+1.6", "subject": "Girl", "shot": "full", "angle": 25},
    {"name": "eat alone", "start": "@lunch", "subject": "Leo", "shot": "full", "angle": 20},
    {"name": "timmy", "start": "@me", "subject": "Timmy", "shot": "medium", "angle": 15},
    {"name": "leo", "start": "@leo", "subject": "Leo", "shot": "close", "angle": 10},
    {"name": "pigeons", "start": "@pigeons", "subject": "Leo", "shot": "medium", "angle": -25},
    {"name": "star count", "start": "@friday", "subject": "Timmy", "shot": "close", "angle": -10},
    {"name": "two hundred", "start": "@preston", "subject": "Preston", "shot": "medium", "angle": 20},
    {"name": "paid", "start": "@paid", "subject": "Timmy", "with": "Preston", "shot": "full", "angle": 0},
    {"name": "nice hair", "start": "@paid+2.2", "subject": "Preston", "with": "Leo", "shot": "medium", "angle": 0},
    {"name": "fell off", "start": "@paid.end-1.0", "subject": "Leo", "shot": "close", "angle": 15},
    {"name": "suit", "start": "@suit", "subject": "Leo", "with": "Lady", "shot": "full", "angle": 0},
    {"name": "landed on me", "start": "@suit+2.2", "subject": "Timmy", "shot": "close", "angle": 10},
    {"name": "the joke", "start": "@joke", "subject": "Leo", "shot": "full", "angle": 20},
    {"name": "silence", "start": "@joke+1.4", "pos": [-2, 6, 26], "look": [-2, 3.5, 5], "fov": 54, "subjects": []},
    {"name": "cricket", "start": "@joke.end-1.6", "subject": "Leo", "shot": "close", "angle": -15},
    # B: the room
    {"name": "room", "start": "@night", "pos": [450, 7, 16], "look": [452, 3.5, 0], "fov": 52, "subjects": []},
    {"name": "counting", "start": "@night+1.3", "subject": "TimmyR", "shot": "medium", "angle": 40},
    {"name": "last card", "start": "@card", "subject": "TimmyR", "shot": "close", "angle": 10},
    # C: the street, the big moment
    {"name": "best friend", "start": "@best", "subject": "Timmy", "with": "Leo", "shot": "medium", "angle": 0},
    {"name": "listens", "start": "@best+2.2", "subject": "Timmy", "shot": "close", "angle": 15},
    {"name": "pizza star", "start": "@ding2", "subject": "Leo", "shot": "close", "angle": 10},
    {"name": "pigeon wing", "start": "@pigeon", "subject": "Girl", "with": "Leo", "shot": "medium", "angle": 0},
    {"name": "another", "start": "@everyone", "subject": "Lady", "with": "Leo", "shot": "full", "angle": 0},
    {"name": "even preston", "start": "@everyone+1.6", "subject": "Preston", "shot": "close", "angle": 20},
    {"name": "friday", "start": "@count", "pos": [-2, 6, 26], "look": [-2, 3.5, 5], "fov": 54, "subjects": []},
    {"name": "forty seven", "start": "@count+1.4", "subject": "Leo", "shot": "medium", "angle": 15},
    {"name": "fewest", "start": "@fewest", "subject": "Timmy", "shot": "close", "angle": -10},
    {"name": "preston laughs", "start": "@fewest+1.4", "subject": "Preston", "shot": "medium", "angle": 15},
    {"name": "too busy", "start": "@busy", "subject": "Timmy", "shot": "close", "angle": 10},
    {"name": "sweeping", "start": "@sweep", "subject": "Timmy", "with": "Leo", "shot": "full", "angle": 20},
    {"name": "nicest thing", "start": "@twist", "subject": "Timmy", "with": "Leo", "shot": "medium", "angle": 0},
    {"name": "forty eight", "start": "@twist.end-1.2", "subject": "Leo", "shot": "close", "angle": 15},
]

LINES = [
    {"id": "rule", "text": "In this town, every compliment you give becomes a gold sticker on the other person's forehead."},
    {"id": "ding", "text": "Say something nice, and ding. A shiny gold star. It stays until midnight."},
    {"id": "fake", "text": "Fake compliments don't count. The star just falls off."},
    {"id": "size", "text": "Nice shoes gets you a tiny one. You saved my life? A star the size of a pizza."},
    {"id": "legend", "text": "In 2003, a grandma complimented an entire marching band. They glowed so bright, a plane tried to land on them."},
    {"id": "lunch", "text": "So here, stars are everything. Lots of stars, you're popular. Zero stars, you eat alone."},
    {"id": "me", "text": "And me? I'm Timmy. Totally average. About six stars a day.", "gap": 0.3},
    {"id": "leo", "text": "That's Leo. My best friend. Zero stars. In his whole life."},
    {"id": "pigeons", "text": "He's quiet. He talks to pigeons. Nobody knows what to say to him."},
    {"id": "friday", "text": "And Friday is Star Count. Whoever has the fewest stars sweeps every street in town. For a year.", "gap": 0.3},
    {"id": "preston", "text": "Preston already has two hundred. Kids tell him he's rich. It's true, so it sticks."},
    {"id": "paid", "text": "So I paid Preston five dollars to compliment Leo. Nice... hair? It fell right off.", "gap": 0.3},
    {"id": "suit", "text": "I put Leo in a fancy suit. Everyone said, great suit. The stars landed on me. I picked the suit."},
    {"id": "joke", "text": "I taught him a joke. He told it to the whole street. Silence. Somewhere, a cricket got a star."},
    {"id": "night", "text": "Thursday night, I counted. Leo, zero. Preston, two hundred and twelve.", "gap": 0.3},
    {"id": "card", "text": "So I did the one thing I never do. I said what I really think. Out loud. In front of everyone."},
    {"id": "best", "text": "Leo is the best friend I've ever had. He's the only one who actually listens."},
    {"id": "ding2", "text": "Ding. The biggest star I've ever seen. The size of a pizza."},
    {"id": "pigeon", "text": "Then a girl said, he fixed a pigeon's wing once. Ding."},
    {"id": "everyone", "text": "Then another. And another. Even Preston said one. It stuck."},
    {"id": "count", "text": "Friday came. Leo had forty-seven stars.", "gap": 0.3},
    {"id": "fewest", "text": "And the fewest stars in town? Me. Zero."},
    {"id": "busy", "text": "Everyone was too busy complimenting Leo."},
    {"id": "sweep", "text": "So now I sweep the streets. And Leo sweeps with me. Every single day."},
    {"id": "twist", "text": "I told him it's the nicest thing anyone's ever done for me. Ding. Forty-eight."},
]
TITLES = [("@friday", "@friday.end+0.3", "STAR COUNT: FRIDAY"), ("@fewest+1.4", "@busy.end", "Timmy: 0 stars")]

FACES = {
    "Lady": [(0, "happy"), ("@rule+1.2", "grin"), ("@legend", "happy"), ("@legend+1.6", "grin"), ("@suit", "happy"),
             ("@joke+1.4", "shocked"), ("@everyone", "love"), ("@sweep", "happy")],
    "Man": [(0, "neutral"), ("@rule+1.2", "shocked"), ("@ding", "grin"), ("@size", "happy"), ("@legend+1.6", "grin"),
            ("@suit", "happy"), ("@joke+1.4", "tired"), ("@everyone+0.8", "happy")],
    "Girl": [(0, "neutral"), ("@fake", "smug"), ("@fake.end-1.0", "sad"), ("@legend+1.6", "grin"), ("@preston", "happy"),
             ("@joke+1.4", "shocked"), ("@pigeon", "love"), ("@count", "happy")],
    "Preston": [(0, "smug"), ("@fake", "grin"), ("@fake.end-1.0", "neutral"), ("@preston", "smug"), ("@paid", "grin"),
                ("@paid.end-1.0", "neutral"), ("@joke+1.4", "tired"), ("@everyone+1.6", "sad"), ("@everyone.end-0.6", "happy"),
                ("@count", "smug"), ("@fewest+1.2", "grin")],
    "Leo": [(0, "neutral"), ("@lunch", "sad"), ("@leo", "tired"), ("@pigeons", "neutral"), ("@paid+2.4", "happy"),
            ("@paid.end-1.0", "sad"), ("@suit", "happy"), ("@suit+2.2", "neutral"), ("@joke", "happy"), ("@joke+1.4", "scared"),
            ("@joke.end-1.6", "sad"), ("@best", "shocked"), ("@ding2", "love"), ("@pigeon", "grin"), ("@count", "grin"),
            ("@sweep", "happy"), ("@twist+1.2", "love")],
    "Timmy": [(0, "neutral"), ("@me", "happy"), ("@friday", "scared"), ("@friday+1.8", "angry"), ("@paid", "smug"),
              ("@paid.end-1.0", "sad"), ("@suit+2.2", "grin"), ("@suit.end-1.0", "tired"), ("@joke+1.4", "scared"),
              ("@best", "neutral"), ("@best+2.2", "happy"), ("@ding2", "grin"), ("@count", "happy"), ("@fewest", "shocked"),
              ("@busy", "sad"), ("@sweep", "tired"), ("@twist", "happy"), ("@twist.end-1.0", "grin")],
    "TimmyR": [(0, "tired"), ("@night+2.6", "sad"), ("@card", "neutral"), ("@card+1.8", "angry")],
}

# objects from other episodes' sets that must stay out of shot (an object with no show spans is hidden)
HIDE = [["Workspace", "Sets", n] for n in ("PaidBench", "SaleChair0", "SaleChair1", "SaleChair2", "SaleChair3", "CarryChair",
                                           "MomChair", "Jar")] + \
       [["Workspace", "Sets", "ChairMarket", "Sign"], ["Workspace", "Sets", "ChairMarket", "Price"],
        ["Workspace", "Sets", "TimmyRoom", "Poster"]]
PROPS = [{"path": p, "show": []} for p in HIDE]
FX = [
    {"actor": "Man", "kind": "sparkle", "show": [["@ding", "@ding.end"]]},
    {"actor": "Preston", "kind": "sparkle", "show": [["@preston", "@preston.end"]]},
    {"actor": "Timmy", "kind": "sparkle", "show": [["@suit+2.2", "@suit.end"]]},
    {"actor": "Leo", "kind": "sparkle", "show": [["@ding2", "@everyone.end"], ["@count+1.4", "@count.end"], ["@twist.end-1.2", "@twist.end"]]},
    {"actor": "Leo", "kind": "label", "show": [["@leo", "@pigeons.end", "★ 0"], ["@count+1.4", "@count.end", "★ 47"], ["@twist.end-1.2", "@twist.end", "★ 48"]]},
    {"actor": "Preston", "kind": "label", "show": [["@preston", "@preston.end", "★ 200"]]},
    {"actor": "Timmy", "kind": "label", "show": [["@me", "@me.end", "★ 6"], ["@fewest", "@busy.end", "★ 0"]]},
]
MUSIC = {"query": "happy", "pick": 2, "from": 0, "gain": 0.45}
SFX = [("@rule+1.2", "ding", 0.6), ("@ding+1.0", "ding", 0.7), ("@fake.end-1.0", "slide whistle", 0.5),
       ("@size.end-1.4", "ding", 0.6), ("@legend+1.6", "marching band", 0.4), ("@legend.end-1.4", "airplane", 0.5),
       ("@lunch.end-1.0", "sad trombone", 0.4), ("@me+0.4", "pop", 0.5), ("@pigeons+1.0", "pigeon", 0.5),
       ("@friday", "boom", 0.5), ("@preston+1.6", "cash register", 0.5), ("@paid.end-1.0", "slide whistle", 0.6),
       ("@suit.end-2.0", "ding", 0.6), ("@joke+1.6", "crickets", 0.6), ("@night+1.0", "clock ticking", 0.4),
       ("@card", "heartbeat", 0.5), ("@ding2", "ding", 0.9), ("@pigeon.end-0.6", "ding", 0.7), ("@everyone", "ding", 0.6),
       ("@count", "drumroll", 0.5), ("@fewest+1.2", "record scratch", 0.6), ("@sweep", "broom", 0.5),
       ("@twist.end-1.2", "ding", 0.9)]
