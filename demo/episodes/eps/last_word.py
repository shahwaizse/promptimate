"""In this town, the last word you say before bed is what you wake up as. (narration-paced; at the end Timmy's mind
is played by a second grandpa rig)"""
TITLE = "In This Town, Your Last Word Before Bed Is What You Wake Up As"
VOICE, SPEED = "tv_M2", 1.6
CAPTIONS = {"size": 66, "highlight": False, "max_words": 3}
KEYWORDS = ["word", "cheetah", "Grandpa", "Timmy", "turtle", "eightieth", "sixty", "Wednesday", "two"]

# ---- cast: classic blocky characters; one copy of a character per set (characters don't travel between lots)
CAST = [
    # town street around the bench (A, C)
    {"name": "Man", "look": "c_man", "at": [5, 6.5]},
    {"name": "Lady", "look": "c_lady", "at": [-7, 6]},
    {"name": "Kid", "look": "c_kid", "at": [-14, 9.5], "yaw": -90},
    {"name": "Grandpa", "look": "c_grandpa", "at": [-0.5, 5], "yaw": 180},
    {"name": "Grandpa2", "look": "c_grandpa", "at": [24, 10], "yaw": 90},   # Timmy, the morning after (the twist)
    # Timmy's room, Grandpa sleeps here too (B)
    {"name": "GrandpaR", "look": "c_grandpa", "at": [446, -2], "yaw": -90},
    {"name": "TimmyR", "look": "c_timmy", "at": [452, -2], "yaw": 90},
]

# shared prompt strings (identical across episodes: repeated prompts are free)
IDLE = "a person stands still, relaxed, looking around"
HAPPY = "a person stands and smiles happily"
SAD = "a person stands alone with their head down, sad"
STARE = "a person stares in surprise"
WALK = "a person walks forward casually"
WALK_SAD = "a person walks forward slowly, tired, head down"
RUN = "a person runs forward excitedly"
JOY = "a person jumps up and down with joy, arms in the air"
FISTS = "a person stands still, watching sadly, then clenches their fists with determination"
LAUGH = "a person laughs hard, bending over and holding their stomach"
TALK = "a person stands and talks, gesturing with both hands"
SHRUG = "a person shrugs"
WAVE = "a person waves with their right hand"
NOD = "a person nods slowly"
STOMP = "a person stomps their foot down hard"
SHOCK_BACK = "a person turns and steps back in surprise, arms down at their sides"
BACK_ACHE = "a person stands still and stretches their back, tired"
GETUP = "a person gets up from the ground"
SIT_DOWN = "a person turns around and sits down"
SIT_SAD = "a person sits alone, head down, sad"
STAND_UP = "a person stands up slowly"
SIT_GROUND = "a person sits down on the ground"
SIT_GROUND_TALK = "a person sits on the ground and talks, gesturing with both hands"
CRAWL = "a person crawls forward slowly on hands and knees"
LIE = "a person lies down on the ground on their back"
LIE_STILL = "a person lies still on their back, sleeping"
STIFF = "a person stands stiffly with arms at their sides"
SHOUT = "a person leans forward and shouts"

BENCH = "Bench"

ACTORS = [
    # ---------------------------------------------------------------- A + C: the street
    {"name": "Man", "start": [5, 6.5], "facing": "+Z", "beats": [
        {"at": 0.0, "prompt": BACK_ACHE, "seconds": 2.6},
        {"at": "@how", "prompt": CRAWL, "seconds": 3.4, "to": [5, 9.5]},
        {"prompt": GETUP, "seconds": 2.0},
        {"at": "@lives", "prompt": WAVE, "seconds": 1.8, "face": "+Z"},
        {"at": "@ran+1.0", "prompt": SHOCK_BACK, "seconds": 2.2},
        {"at": "@laughed", "prompt": STARE, "seconds": 3.0, "face": "Grandpa"},
        {"at": "@twist", "prompt": STARE, "seconds": 3.0, "face": "Grandpa2"},
    ]},
    {"name": "Lady", "start": [-7, 6], "facing": "+Z", "beats": [
        {"at": "@small", "prompt": LIE, "seconds": 2.4},
        {"prompt": LIE_STILL, "seconds": 2.0},
        {"prompt": GETUP, "seconds": 2.0},
        {"at": "@lives", "prompt": WAVE, "seconds": 1.8, "face": "+Z"},
        {"at": "@ran+1.0", "prompt": SHOCK_BACK, "seconds": 2.2},
        {"at": "@laughed", "prompt": LAUGH, "seconds": 2.6},
        {"at": "@birthday", "prompt": WAVE, "seconds": 1.8, "face": "Grandpa"},
    ]},
    {"name": "Kid", "start": [-14, 9.5], "facing": "+X", "beats": [
        {"at": "@small+2.2", "prompt": STOMP, "seconds": 1.6, "face": "+Z"},
        {"prompt": STOMP, "seconds": 1.6, "face": "+Z"},
        {"at": "@lives", "prompt": WAVE, "seconds": 1.8, "face": "+Z"},
        {"at": "@grandpa+0.8", "prompt": RUN, "seconds": 2.8, "to": [14, 10]},
        {"prompt": IDLE, "seconds": 2.0, "face": "-X"},
        {"at": "@laughed", "prompt": JOY, "seconds": 3.0},
        {"at": "@birthday", "prompt": WAVE, "seconds": 1.8, "face": "Grandpa"},
    ]},
    {"name": "Grandpa", "start": [-0.5, 5], "facing": "-Z", "beats": [
        {"at": 0.0, "prompt": [SIT_DOWN, SIT_SAD], "seconds": [1.5, 3.0], "sit": BENCH, "sit_from": 1.2},
        {"at": "@grandpa", "prompt": SIT_SAD, "seconds": 4.0, "sit": BENCH},
        {"prompt": SIT_SAD, "seconds": 4.0, "sit": BENCH},
        {"at": "@ran", "prompt": STAND_UP, "seconds": 1.4},
        {"prompt": RUN, "seconds": 2.6, "to": [20, 8.5]},
        {"prompt": RUN, "seconds": 3.2, "to": [-3, 9], "via": [[20, 11.5]]},
        {"at": "@laughed+1.6", "prompt": LAUGH, "seconds": 2.6},
        {"at": "@birthday", "prompt": JOY, "seconds": 3.0},
        {"at": "@twist", "prompt": STARE, "seconds": 2.6, "face": "Grandpa2"},
        {"prompt": SHRUG, "seconds": 1.6, "face": "Grandpa2"},
    ]},
    {"name": "Grandpa2", "start": [24, 10], "facing": "-X", "beats": [
        {"at": "@twist_a", "prompt": WALK, "seconds": 4.0, "to": [1.5, 9.5], "face": "Grandpa"},
        {"at": "@twist", "prompt": STARE, "seconds": 2.0, "face": "Grandpa"},
        {"prompt": WAVE, "seconds": 1.6, "face": "Grandpa"},
        {"at": "@twist.end-1.6", "prompt": WALK_SAD, "seconds": 3.0, "to": [12, 10]},
    ]},
    # ---------------------------------------------------------------- B: Timmy's room, bedtime
    {"name": "TimmyR", "start": [452, -2], "facing": "-X", "beats": [
        {"at": "@me", "prompt": WAVE, "seconds": 1.8, "face": "+Z"},
        {"prompt": SHRUG, "seconds": 1.6, "face": "+Z"},
        {"at": "@sleeptalk", "prompt": TALK, "seconds": 2.6, "face": "+Z"},
        {"at": "@plan", "prompt": FISTS, "seconds": 3.0, "face": "GrandpaR"},
        {"at": "@turtle", "prompt": TALK, "seconds": 1.8, "face": "GrandpaR"},
        {"at": "@turtle+2.4", "prompt": STARE, "seconds": 2.6, "face": "GrandpaR"},
        {"at": "@the", "prompt": TALK, "seconds": 2.6, "face": "GrandpaR"},
        {"at": "@the.end-1.6", "prompt": SHRUG, "seconds": 1.6, "face": "GrandpaR"},
        {"at": "@what", "prompt": SHOUT, "seconds": 1.8, "face": "GrandpaR"},
        {"prompt": SAD, "seconds": 2.4, "face": "GrandpaR"},
        {"at": "@card", "prompt": FISTS, "seconds": 3.0, "face": "GrandpaR"},
        {"at": "@talked", "prompt": SIT_GROUND, "seconds": 1.8, "face": "GrandpaR"},
        {"prompt": SIT_GROUND_TALK, "seconds": 3.0, "face": "GrandpaR"},
        {"at": "@whisper", "prompt": SIT_GROUND_TALK, "seconds": 3.0, "face": "GrandpaR"},
    ]},
    {"name": "GrandpaR", "start": [446, -2], "facing": "+X", "beats": [
        {"at": "@plan", "prompt": BACK_ACHE, "seconds": 2.6},
        {"at": "@turtle+0.8", "prompt": TALK, "seconds": 1.6, "face": "TimmyR"},
        {"prompt": CRAWL, "seconds": 3.4, "to": [446, 2]},
        {"at": "@the", "prompt": GETUP, "seconds": 1.8, "face": "TimmyR"},
        {"prompt": NOD, "seconds": 1.8, "face": "TimmyR"},
        {"prompt": STIFF, "seconds": 2.6, "face": "+Z"},
        {"at": "@what+1.4", "prompt": SHRUG, "seconds": 1.6, "face": "TimmyR"},
        {"prompt": STIFF, "seconds": 2.0, "face": "+Z"},
        {"at": "@talked", "prompt": SIT_GROUND, "seconds": 2.0, "face": "TimmyR"},
        {"prompt": LIE, "seconds": 2.4},
        {"at": "@whisper", "prompt": LIE_STILL, "seconds": 4.0},
    ]},
]

CAMERAS = [
    # one cue per story moment (the recorder adds coverage cuts and push-ins); fixed shots for sets
    # A: the street, the rule
    {"name": "rule", "start": 0.0, "pos": [0, 6, 26], "look": [0, 3.5, 5], "fov": 52, "subjects": []},
    {"name": "said cat", "start": "@how", "subject": "Man", "shot": "full", "angle": 20},
    {"name": "whiskers", "start": "@how+2.0", "subject": "Man", "shot": "close", "angle": -10},
    {"name": "pillow", "start": "@small", "subject": "Lady", "shot": "full", "angle": 25},
    {"name": "dinosaur", "start": "@small+2.2", "subject": "Kid", "shot": "medium", "angle": -15},
    {"name": "wednesday", "start": "@legend", "pos": [0, 6, 26], "look": [0, 3.5, 5], "fov": 52, "subjects": []},
    {"name": "that week", "start": "@legend+2.6", "subject": "Man", "shot": "close", "angle": 15},
    {"name": "me", "start": "@lives", "subject": "Lady", "with": "Man", "shot": "full", "angle": 0},
    # B: the room
    {"name": "room", "start": "@me", "pos": [450, 7, 16], "look": [450, 3.5, -2], "fov": 52, "subjects": []},
    {"name": "timmy", "start": "@me+1.2", "subject": "TimmyR", "shot": "close", "angle": 10},
    {"name": "my own mom", "start": "@sleeptalk", "subject": "TimmyR", "shot": "medium", "angle": -20},
    # A: grandpa on the bench
    {"name": "grandpa", "start": "@grandpa", "subject": "Grandpa", "shot": "full", "angle": 15},
    {"name": "he watches", "start": "@grandpa+0.8", "subject": "Grandpa", "with": "Kid", "shot": "full", "angle": 20},
    {"name": "one wish", "start": "@wish", "subject": "Grandpa", "shot": "close", "angle": 10},
    # B: three nights
    {"name": "the plan", "start": "@plan", "subject": "TimmyR", "with": "GrandpaR", "shot": "medium", "angle": 0},
    {"name": "cheetah plan", "start": "@plan+1.4", "subject": "TimmyR", "shot": "close", "angle": -15},
    {"name": "turtle", "start": "@turtle", "subject": "GrandpaR", "shot": "medium", "angle": 15},
    {"name": "crossing the kitchen", "start": "@turtle+2.4", "subject": "GrandpaR", "shot": "full", "angle": 30},
    {"name": "story", "start": "@the", "subject": "TimmyR", "with": "GrandpaR", "shot": "medium", "angle": 0},
    {"name": "a the", "start": "@the+2.6", "subject": "GrandpaR", "shot": "close", "angle": 10},
    {"name": "yelled", "start": "@what", "subject": "TimmyR", "shot": "close", "angle": 20},
    {"name": "a what", "start": "@what+1.4", "subject": "GrandpaR", "shot": "medium", "angle": -10},
    {"name": "last night", "start": "@card", "subject": "TimmyR", "shot": "close", "angle": 0},
    {"name": "three hours", "start": "@talked", "pos": [450, 7, 16], "look": [449, 2.5, -1], "fov": 48, "subjects": []},
    {"name": "mid-sentence", "start": "@talked.end-1.8", "subject": "GrandpaR", "shot": "medium", "angle": 30},
    {"name": "whisper", "start": "@whisper", "subject": "TimmyR", "shot": "close", "angle": 15},
    {"name": "said it back", "start": "@whisper.end-1.6", "subject": "GrandpaR", "shot": "close", "angle": 20},
    # C: the run, the twist
    {"name": "grandpa ran", "start": "@ran", "subject": "Grandpa", "shot": "full", "angle": 20},
    {"name": "sixty", "start": "@ran+1.4", "track": "Grandpa", "offset": [3, 1.6, 9], "aim": [0, 1, 0], "fov": 42},
    {"name": "mailboxes", "start": "@laughed", "pos": [0, 6, 26], "look": [2, 3.5, 6], "fov": 54, "subjects": []},
    {"name": "he laughed", "start": "@laughed+1.6", "subject": "Grandpa", "shot": "close", "angle": 10},
    {"name": "happy eightieth", "start": "@birthday", "subject": "Grandpa", "shot": "medium", "angle": -15},
    {"name": "next morning", "start": "@twist_a", "subject": "Grandpa2", "shot": "full", "angle": 25},
    {"name": "two grandpas", "start": "@twist", "subject": "Grandpa", "with": "Grandpa2", "shot": "full", "angle": 0},
    {"name": "go to school", "start": "@twist.end-1.6", "subject": "Grandpa2", "shot": "close", "angle": 10},
]

LINES = [
    {"id": "rule", "text": "In this town, the last word you say before bed is what you wake up as."},
    {"id": "how", "text": "Say cat, and you wake up a cat. Tail, whiskers, everything. It wears off by lunch."},
    {"id": "small", "text": "Say pillow, and you get a soft morning. Say dinosaur, and you wake up through the roof."},
    {"id": "legend", "text": "In 1994, a man fell asleep saying Wednesday. He woke up as Wednesday. Nobody remembers that week."},
    {"id": "lives", "text": "So every night, the whole town says the same last word. Me."},
    {"id": "me", "text": "And me? I'm Timmy. And I talk in my sleep.", "gap": 0.3},
    {"id": "sleeptalk", "text": "This month I woke up as a lamp, a sock, and once, my own mom."},
    {"id": "grandpa", "text": "That's my grandpa. Fastest runner in town, fifty years ago. Now his knees are so bad, he just watches.", "gap": 0.3},
    {"id": "wish", "text": "Sunday is his eightieth birthday. He has one wish. To run. Just one more time."},
    {"id": "plan", "text": "So I made a plan. Get Grandpa to fall asleep saying cheetah.", "gap": 0.3},
    {"id": "turtle", "text": "Night one, I asked his favorite animal. Turtle. It took him all morning to cross the room."},
    {"id": "the", "text": "Night two, I read him a cheetah story. He fell asleep on the word the. Nobody knows what a the is."},
    {"id": "what", "text": "Night three, I yelled cheetah as he dozed off. He said, what? He woke up as a what."},
    {"id": "card", "text": "Saturday. Last chance. So I did the one thing I swore I'd never do. I stayed up all night.", "gap": 0.3},
    {"id": "talked", "text": "I talked to him for three hours. About nothing. Until he fell asleep mid-sentence."},
    {"id": "whisper", "text": "Then I whispered, cheetah. And in his sleep, he said it back."},
    {"id": "ran", "text": "Sunday morning, Grandpa ran. Through the whole town. Sixty miles an hour.", "gap": 0.3},
    {"id": "laughed", "text": "Mailboxes flew. Dogs gave up. He laughed the whole way."},
    {"id": "birthday", "text": "Happy eightieth, Grandpa."},
    {"id": "twist_a", "text": "That night, I fell asleep telling everyone about him.", "gap": 0.3},
    {"id": "twist", "text": "Next morning, there were two grandpas. And one of them had to go to school."},
]
TITLES = [("@wish+1.0", "@wish.end+0.3", "One wish: run again"), ("@ran+2.2", "@ran.end+0.3", "60 MPH")]

FACES = {
    "Man": [(0, "tired"), ("@how", "shocked"), ("@how+1.4", "happy"), ("@lives", "happy"), ("@ran+1.0", "shocked"),
            ("@laughed", "grin"), ("@twist", "shocked")],
    "Lady": [(0, "neutral"), ("@small", "sleeping"), ("@small+4.4", "happy"), ("@lives", "happy"), ("@ran+1.0", "shocked"),
             ("@laughed", "grin"), ("@birthday", "love")],
    "Kid": [(0, "neutral"), ("@small+2.2", "angry"), ("@lives", "happy"), ("@grandpa+0.8", "grin"), ("@laughed", "grin"),
            ("@birthday", "happy")],
    "Grandpa": [(0, "tired"), ("@grandpa", "happy"), ("@grandpa+2.6", "sad"), ("@wish", "tired"), ("@wish+3.0", "sad"),
                ("@ran", "shocked"), ("@ran+1.4", "grin"), ("@laughed+1.6", "grin"), ("@birthday", "love"),
                ("@twist", "shocked"), ("@twist.end-1.0", "smug")],
    "Grandpa2": [(0, "neutral"), ("@twist_a", "tired"), ("@twist", "shocked"), ("@twist.end-1.6", "sad")],
    "TimmyR": [(0, "neutral"), ("@me", "happy"), ("@me+1.6", "tired"), ("@sleeptalk", "shocked"), ("@plan", "smug"),
               ("@turtle", "happy"), ("@turtle+2.4", "shocked"), ("@the", "happy"), ("@the.end-1.6", "tired"), ("@what", "angry"),
               ("@what+2.2", "sad"), ("@card", "angry"), ("@talked", "tired"), ("@whisper", "happy"), ("@whisper.end-1.4", "grin")],
    "GrandpaR": [(0, "tired"), ("@plan", "tired"), ("@turtle+0.8", "happy"), ("@turtle+2.4", "tired"), ("@the", "neutral"),
                 ("@the+2.6", "shocked"), ("@what+1.4", "scared"), ("@talked", "happy"), ("@talked.end-1.8", "sleeping"),
                 ("@whisper.end-1.6", "happy")],
}

# objects from other episodes' sets that must stay out of shot (an object with no show spans is hidden)
HIDE = [["Workspace", "Sets", n] for n in ("PaidBench", "SaleChair0", "SaleChair1", "SaleChair2", "SaleChair3", "CarryChair",
                                           "MomChair", "Jar")] + \
       [["Workspace", "Sets", "ChairMarket", "Sign"], ["Workspace", "Sets", "ChairMarket", "Price"],
        ["Workspace", "Sets", "TimmyRoom", "Poster"]]
PROPS = [{"path": p, "show": []} for p in HIDE]
FX = [
    {"actor": "GrandpaR", "kind": "sparkle", "show": [["@whisper.end-1.6", "@whisper.end"]]},
    {"actor": "Grandpa", "kind": "sparkle", "show": [["@ran", "@laughed.end"]]},
    {"actor": "Grandpa", "kind": "confetti", "show": [["@birthday", "@birthday.end"]]},
    {"actor": "Grandpa2", "kind": "sparkle", "show": [["@twist", "@twist+1.6"]]},
]
MUSIC = {"query": "funny", "pick": 2, "from": 0, "gain": 0.45}
SFX = [("@rule+1.4", "yawn", 0.5), ("@how+0.6", "meow", 0.7), ("@small+0.8", "snore", 0.5), ("@small+2.4", "dinosaur roar", 0.6),
       ("@legend+1.6", "whoosh", 0.5), ("@lives.end-0.6", "pop", 0.5), ("@me+1.4", "snore", 0.5), ("@sleeptalk+1.0", "boing", 0.5),
       ("@grandpa+0.8", "running footsteps", 0.4), ("@wish+1.0", "birthday", 0.4), ("@plan+1.6", "ding", 0.5),
       ("@turtle+2.4", "slow motion", 0.4), ("@the+2.6", "record scratch", 0.5), ("@what+1.4", "huh", 0.6),
       ("@card", "clock ticking", 0.5), ("@talked.end-1.6", "snore", 0.6), ("@whisper.end-1.4", "magic", 0.6),
       ("@ran+1.0", "whoosh", 0.8), ("@laughed", "dog bark", 0.5), ("@laughed+1.6", "laugh", 0.4), ("@birthday", "cheer", 0.5),
       ("@twist", "record scratch", 0.7), ("@twist.end-1.2", "school bell", 0.5)]
