"""In this town, every argument goes to court - even the tiny ones. (narration-paced; sourced sets: Hall re-dressed as
the king's court with the throne prop, Park (two spots), Classroom, BakeryShop; prop library via PLACE)"""
TITLE = "In This Town, Every Argument Goes To Court"
VOICE, SPEED = "tv_M2", 1.0
CAPTIONS = {"size": 120, "highlight": False, "max_words": 2}
KEYWORDS = ["court", "judge", "king", "Harold", "bird", "backpack", "guilty", "Timmy", "Preston", "cupcake", "lawyers",
            "Biscuit", "half", "share", "sue", "job", "smiled"]

# ---- cast: one copy of a character per set (characters don't travel between sets)
CAST = [
    # the court (A, Hall, floor 3.1): open area in front of the pews (z < -28.5); centre aisle x 3191.6..3205.7
    {"name": "King", "look": "c_king", "at": [3198.5, -32]},
    {"name": "TimmyH", "look": "c_timmy", "at": [3195, -26], "yaw": 180},
    {"name": "PrestonH", "look": "c_preston", "at": [3201, -26], "yaw": 180},
    # Preston's three lawyers in a row at the front right, facing the king (-X)
    {"name": "L1", "look": "c_butler", "at": [3206, -31], "yaw": 90},
    {"name": "L2", "look": "c_businessman", "at": [3210, -31], "yaw": 90},
    {"name": "L3", "look": "c_nerd", "at": [3214, -31], "yaw": 90},
    # the park (B, floor 0.5): open lawn east of the fountain cross
    {"name": "Maya", "look": "c_girl", "at": [2455, -10]},
    {"name": "Leo", "look": "c_kid", "at": [2461, -10]},
    # the classroom (C, floor 0.8): the open aisle right of the desks (x 1814.5..1823)
    {"name": "Teacher", "look": "c_teacher", "at": [1818, -10]},
    {"name": "LeoC", "look": "c_kid", "at": [1818.5, -2], "yaw": 180},
    {"name": "TimmyC", "look": "c_timmy", "at": [1817, 6]},
    # the bakery (D, floor 0.1): baker behind the counter (counter z -5.1..-2.1), kids on the open floor in front
    {"name": "Baker", "look": "c_chef", "at": [350, -8]},
    {"name": "TimmyB", "look": "c_timmy", "at": [347, 0.5]},
    {"name": "PrestonB", "look": "c_preston", "at": [353, 0.5]},
    # the park again (E): the king's cupcake stand, west lawn
    {"name": "KingP", "look": "c_king", "at": [2340, 36]},
    {"name": "TimmyP", "look": "c_timmy", "at": [2336, 44], "yaw": 180},
    {"name": "PrestonP", "look": "c_preston", "at": [2344, 44], "yaw": 180},
]

# shared prompt strings (identical across episodes: repeated prompts are free)
IDLE = "a person stands still, relaxed, looking around"
HAPPY = "a person stands and smiles happily"
SAD = "a person stands alone with their head down, sad"
STARE = "a person stares in surprise"
JOY = "a person jumps up and down with joy, arms in the air"
SMUG = "a person stands with arms crossed, chin raised, smug"
LAUGH = "a person laughs hard, bending over and holding their stomach"
LAUGH_AT = "a person points forward and laughs"
TALK = "a person stands and talks, gesturing with both hands"
GIVE = "a person holds out both hands, offering something"
SHRUG = "a person shrugs"
WAVE = "a person waves with their right hand"
NOD = "a person nods slowly"
SHAKE = "a person shakes their head slowly, disappointed"
SCRATCH = "a person scratches their head with their right hand, confused"
POINT = "a person points forward sternly"
ANGRY = "a person stands shaking with anger, fists clenched"
STOMP = "a person stomps their foot down hard"
BOW = "a person bows deeply"
STIFF = "a person stands stiffly with arms at their sides"
SING = "a person sings loudly, arms spread wide"
CRY = "a person covers their face with both hands and cries"
LOOK_LR = "a person looks to the left, then to the right, then to the left again"
LOOK_SELF = "a person looks down at their own body in shock"
READ = "a person holds something in both hands and reads it carefully"
REACH = "a person reaches forward slowly with their right hand"
# new in this episode
STERN = "a person stands with their hands behind their back, stern"
SPOT = "a person points forward excitedly"
BREAK = "a person holds something in both hands and pulls it apart"

ACTORS = [
    # ---------------------------------------------------------------- A: the court
    {"name": "King", "start": [3198.5, -32], "facing": "+Z", "beats": [
        {"at": 0.0, "prompt": STERN, "seconds": 4.4},
        {"at": "@judge", "prompt": STERN, "seconds": 3.0},
        {"prompt": SHAKE, "seconds": 2.4},
        {"at": "@birdwon", "prompt": SCRATCH, "seconds": 3.0},
        {"prompt": POINT, "seconds": 2.4},
        {"at": "@guilty", "prompt": POINT, "seconds": 2.0},
        {"at": "@case", "prompt": STERN, "seconds": 4.0},
        {"at": "@turn", "prompt": STERN, "seconds": 1.4},
        {"prompt": TALK, "seconds": 2.6, "face": "TimmyH"},
        {"at": "@quiet", "prompt": STARE, "seconds": 3.6, "face": "+Z"},
        {"at": "@smile", "prompt": HAPPY, "seconds": 4.0},
        {"at": "@law", "prompt": TALK, "seconds": 3.2},
        {"prompt": NOD, "seconds": 2.0},
        {"at": "@closed", "prompt": SAD, "seconds": 4.0},
        {"at": "@job", "prompt": POINT, "seconds": 2.0},
    ]},
    {"name": "TimmyH", "start": [3195, -26], "facing": "-Z", "beats": [
        {"at": "@lawyers", "prompt": IDLE, "seconds": 3.0},
        {"at": "@dog", "prompt": HAPPY, "seconds": 2.4},
        {"prompt": SHRUG, "seconds": 2.0},
        {"at": "@case", "prompt": IDLE, "seconds": 4.0, "face": "L2"},
        {"at": "@turn+1.4", "prompt": STARE, "seconds": 2.4, "face": "King"},
        {"at": "@think", "prompt": LOOK_LR, "seconds": 3.0, "face": "-Z"},
        {"prompt": SAD, "seconds": 2.0},
        {"at": "@split", "prompt": BREAK, "seconds": 2.2},
        {"prompt": GIVE, "seconds": 2.4, "face": "PrestonH"},
        {"at": "@quiet", "prompt": IDLE, "seconds": 3.0},
        {"at": "@smile", "prompt": HAPPY, "seconds": 3.0, "face": "King"},
        {"at": "@law+2.4", "prompt": JOY, "seconds": 3.0},
    ]},
    {"name": "PrestonH", "start": [3201, -26], "facing": "-Z", "beats": [
        {"at": "@lawyers", "prompt": SMUG, "seconds": 3.6},
        {"at": "@dog+1.4", "prompt": LAUGH_AT, "seconds": 2.4, "face": "TimmyH"},
        {"at": "@case", "prompt": SMUG, "seconds": 4.0, "face": "-Z"},
        {"at": "@split+2.0", "prompt": STARE, "seconds": 2.6, "face": "TimmyH"},
        {"at": "@quiet", "prompt": STARE, "seconds": 3.0},
        {"at": "@smile", "prompt": SHRUG, "seconds": 2.0, "face": "King"},
        {"prompt": HAPPY, "seconds": 2.4},
        {"at": "@law+2.4", "prompt": HAPPY, "seconds": 3.0, "face": "TimmyH"},
    ]},
    {"name": "L1", "start": [3206, -31], "facing": "-X", "beats": [
        {"at": "@lawyers", "prompt": BOW, "seconds": 2.4},
        {"at": "@case", "prompt": TALK, "seconds": 3.4},
        {"prompt": SING, "seconds": 2.4},
        {"at": "@cried", "prompt": STARE, "seconds": 2.0, "face": "L3"},
        {"at": "@law", "prompt": SHRUG, "seconds": 2.0, "face": "-X"},
    ]},
    {"name": "L2", "start": [3210, -31], "facing": "-X", "beats": [
        {"at": "@lawyers", "prompt": STIFF, "seconds": 3.0},
        {"at": "@case", "prompt": TALK, "seconds": 3.4},
        {"prompt": SING, "seconds": 2.4},
        {"at": "@cried", "prompt": STARE, "seconds": 2.0, "face": "L3"},
        {"at": "@law", "prompt": NOD, "seconds": 2.0, "face": "-X"},
    ]},
    {"name": "L3", "start": [3214, -31], "facing": "-X", "beats": [
        {"at": "@lawyers", "prompt": NOD, "seconds": 2.0},
        {"at": "@case", "prompt": NOD, "seconds": 2.4},
        {"at": "@case+3.4", "prompt": SING, "seconds": 2.4},
        {"at": "@cried", "prompt": CRY, "seconds": 3.0},
        {"at": "@law", "prompt": HAPPY, "seconds": 2.4},
    ]},
    # ---------------------------------------------------------------- B: the park, the bird case
    {"name": "Maya", "start": [2455, -10], "facing": "+Z", "beats": [
        {"at": "@bird", "prompt": SPOT, "seconds": 2.0},
        {"prompt": ANGRY, "seconds": 2.4, "face": "Leo"},
        {"at": "@birdwon.end-1.4", "prompt": SHRUG, "seconds": 2.0, "face": "+Z"},
        {"at": "@nobody+1.4", "prompt": BOW, "seconds": 2.4, "face": "Leo"},
        {"prompt": HAPPY, "seconds": 2.0},
    ]},
    {"name": "Leo", "start": [2461, -10], "facing": "+Z", "beats": [
        {"at": "@bird+0.8", "prompt": SPOT, "seconds": 2.0},
        {"prompt": ANGRY, "seconds": 2.4, "face": "Maya"},
        {"at": "@birdwon.end-1.4", "prompt": SCRATCH, "seconds": 2.4, "face": "+Z"},
        {"at": "@nobody+0.4", "prompt": STOMP, "seconds": 2.0, "face": "Maya"},
        {"prompt": SHRUG, "seconds": 2.0},
    ]},
    # ---------------------------------------------------------------- C: the classroom, the backpack, the letter
    {"name": "LeoC", "start": [1818.5, -2], "facing": "-Z", "beats": [
        {"at": "@backpack", "prompt": POINT, "seconds": 2.4, "face": "+X"},
        {"prompt": ANGRY, "seconds": 1.6, "face": "Teacher"},
        {"at": "@guilty+0.6", "prompt": JOY, "seconds": 2.6},
    ]},
    {"name": "Teacher", "start": [1818, -10], "facing": "+Z", "beats": [
        {"at": "@backpack+1.2", "prompt": SHAKE, "seconds": 2.4},
        {"at": "@guilty+0.8", "prompt": SHRUG, "seconds": 2.0},
    ]},
    {"name": "TimmyC", "start": [1817, 6], "facing": "+Z", "beats": [
        {"at": "@letter", "prompt": READ, "seconds": 2.6},
        {"prompt": STARE, "seconds": 2.0},
        {"at": "@job", "prompt": LOOK_SELF, "seconds": 2.0},
    ]},
    # ---------------------------------------------------------------- D: the bakery, the last cupcake
    {"name": "Baker", "start": [350, -8], "facing": "+Z", "beats": [
        {"at": "@cupcake", "prompt": GIVE, "seconds": 2.6},
        {"prompt": STARE, "seconds": 2.4},
        {"at": "@sued", "prompt": SHRUG, "seconds": 2.0},
    ]},
    {"name": "TimmyB", "start": [347, 0.5], "facing": "+Z", "beats": [
        {"at": "@me", "prompt": WAVE, "seconds": 1.8},
        {"prompt": STARE, "seconds": 1.4},
        {"at": "@cupcake+1.6", "prompt": REACH, "seconds": 2.4, "face": "Baker"},
        {"prompt": STARE, "seconds": 2.0, "face": "PrestonB"},
        {"at": "@sued", "prompt": STARE, "seconds": 3.0, "face": "PrestonB"},
    ]},
    {"name": "PrestonB", "start": [353, 0.5], "facing": "+Z", "beats": [
        {"at": "@cupcake+1.6", "prompt": REACH, "seconds": 2.4, "face": "Baker"},
        {"prompt": ANGRY, "seconds": 2.0, "face": "TimmyB"},
        {"at": "@sued", "prompt": POINT, "seconds": 2.4, "face": "TimmyB"},
        {"prompt": SMUG, "seconds": 2.0},
    ]},
    # ---------------------------------------------------------------- E: the park, the king's cupcake stand
    {"name": "KingP", "start": [2340, 36], "facing": "+Z", "beats": [
        {"at": "@end", "prompt": HAPPY, "seconds": 2.4},
        {"prompt": GIVE, "seconds": 2.4, "face": "TimmyP"},
        {"prompt": LAUGH, "seconds": 2.6, "face": "+Z"},
    ]},
    {"name": "TimmyP", "start": [2336, 44], "facing": "-Z", "beats": [
        {"at": "@end+2.4", "prompt": HAPPY, "seconds": 2.4, "face": "KingP"},
        {"prompt": JOY, "seconds": 3.0, "face": "+Z"},
    ]},
    {"name": "PrestonP", "start": [2344, 44], "facing": "-Z", "beats": [
        {"at": "@end+2.4", "prompt": HAPPY, "seconds": 2.4, "face": "KingP"},
        {"prompt": LAUGH, "seconds": 2.6, "face": "+Z"},
    ]},
]

LINES = [
    {"id": "rule", "text": "In this town, every argument goes to court. Even the tiny ones."},
    {"id": "judge", "text": "And the judge is always the same guy. King Harold. Forty years on that throne, and he has never smiled once."},
    {"id": "bird", "text": "Last week, Maya and Leo sued each other over who saw a bird first.", "gap": 0.3},
    {"id": "birdwon", "text": "The king thought about it for an hour. Then he ruled that the bird saw them first. The bird won."},
    {"id": "backpack", "text": "Leo once sued his own backpack. For being too heavy.", "gap": 0.3},
    {"id": "guilty", "text": "Guilty. Two weeks in the lost and found."},
    {"id": "nobody", "text": "So nobody here argues. Ever. If someone steps on your foot, you say sorry to them.", "gap": 0.3},
    {"id": "me", "text": "I'm Timmy. And last Saturday, I got sued.", "gap": 0.4},
    {"id": "cupcake", "text": "It was the last cupcake in the bakery. Preston and I grabbed it at the exact same second."},
    {"id": "sued", "text": "He looked me right in the eye and said, see you in court."},
    {"id": "lawyers", "text": "Preston showed up with three lawyers. Three. He's ten.", "gap": 0.4},
    {"id": "dog", "text": "I showed up with my dog, Biscuit. He's not a lawyer. He just didn't want to stay home."},
    {"id": "case", "text": "Preston's lawyers talked for forty minutes. They had charts. They had a song.", "gap": 0.3},
    {"id": "turn", "text": "Then the king looked at me. Timmy. What do you have to say?"},
    {"id": "think", "text": "I had nothing. No lawyers. No charts. Just a dog, and the cupcake."},
    {"id": "split", "text": "So I broke the cupcake in half. And I gave Preston the bigger piece.", "gap": 0.3},
    {"id": "quiet", "text": "The whole court went quiet."},
    {"id": "cried", "text": "One of his lawyers started crying."},
    {"id": "smile", "text": "And then, for the first time in forty years, King Harold smiled.", "gap": 0.4},
    {"id": "law", "text": "He made a brand new law, right there. If you can share it, you can't sue over it."},
    {"id": "closed", "text": "By Monday, the court was empty. Nobody had anything left to fight about.", "gap": 0.3},
    {"id": "letter", "text": "Then on Tuesday, I got a letter. The king was suing me.", "gap": 0.3},
    {"id": "job", "text": "For taking his job."},
    {"id": "end", "text": "We settled. Now he runs a cupcake stand in the park. And every cupcake comes already cut in half.", "gap": 0.4},
]
TITLES = [("@rule+2.4", "@rule.end+0.3", "COURT"), ("@job", "@job.end+0.8", "SUED")]

# ---- sourced props (sets.py prop library), cloned to workspace.Sets.EpisodeProps.<name>; y = the set's floor_y
PLACE = [
    # A: the court
    {"prop": "throne", "at": [3198.5, -36.5], "y": 3.1, "yaw": 0, "name": "Throne"},
    {"prop": "dog", "at": [3194, -29], "y": 3.1, "yaw": 90, "name": "Biscuit"},
    {"prop": "chalkboard", "at": [3184, -36], "y": 3.1, "yaw": 0, "name": "Chart", "text": "CUPCAKE LAW: A HISTORY"},
    {"prop": "cake", "at": [3196, -23], "y": 3.1, "yaw": 0, "name": "CakeH"},
    {"prop": "cake", "at": [3196, -22], "y": 3.1, "yaw": 0, "name": "CakeHT"},
    {"prop": "cake", "at": [3200, -22], "y": 3.1, "yaw": 0, "name": "CakeHP"},
    # B: the park, the bird on the grass between the kids
    {"prop": "bird", "at": [2458, -6.5], "y": 0.5, "yaw": 180, "name": "Bird"},
    # C: the classroom
    {"prop": "backpack", "at": [1821, -1.5], "y": 0.8, "yaw": 0, "name": "Backpack"},
    {"prop": "newspaper", "at": [1815.5, 6], "y": 0.8, "yaw": 0, "name": "Letter"},
    # D: the bakery
    {"prop": "cake", "at": [350, -6.5], "y": 0.1, "yaw": 0, "name": "CakeB"},
    # E: the cupcake stand in the park
    {"prop": "kitchen_counter", "at": [2340, 39.5], "y": 0.5, "yaw": 0, "name": "Stand"},
    {"prop": "cake", "at": [2339.2, 39.5], "y": 3.7, "yaw": 0, "name": "CakeS1"},
    {"prop": "cake", "at": [2340.8, 39.5], "y": 3.7, "yaw": 20, "name": "CakeS2"},
    {"prop": "cake", "at": [2336, 42], "y": 0.5, "yaw": 0, "name": "CakePT"},
    {"prop": "cake", "at": [2344, 42], "y": 0.5, "yaw": 0, "name": "CakePP"},
]


def EP(n):
    return ["Workspace", "Sets", "EpisodeProps", n]


HAND = [0, -0.6, -0.3, 0, 0, 0]

CAMERAS = [
    # A: the court. Hook: the judge's face from frame one
    {"name": "hook", "start": 0.0, "subject": "King", "shot": "close", "angle": 0},
    {"name": "court", "start": "@rule+2.2", "pos": [3198.5, 12, -8], "look": [3198.5, 6, -31], "fov": 55, "subjects": []},
    {"name": "the judge", "start": "@judge", "subject": "King", "shot": "medium", "angle": 15},
    {"name": "never smiled", "start": "@judge.end-2.4", "subject": "King", "shot": "close", "angle": -10},
    # B: the park, the bird case
    {"name": "park", "start": "@bird", "pos": [2458, 6.5, 8], "look": [2458, 2.5, -10], "fov": 50, "subjects": []},
    {"name": "the bird", "start": "@bird+1.8", "prop": "Bird", "shot": "close", "angle": 0},
    {"name": "who saw it", "start": "@bird.end-1.6", "subject": "Maya", "with": "Leo", "shot": "full", "angle": 0},
    # A: the verdict
    {"name": "thinking", "start": "@birdwon", "subject": "King", "shot": "medium", "angle": -15},
    {"name": "ruled", "start": "@birdwon+2.8", "subject": "King", "shot": "close", "angle": 0},
    # B: the winner
    {"name": "bird won", "start": "@birdwon.end-1.2", "prop": "Bird", "shot": "close", "angle": 30},
    # C: the backpack
    {"name": "classroom", "start": "@backpack", "pos": [1818.5, 7.5, 14], "look": [1818.5, 3, -3], "fov": 50, "subjects": []},
    {"name": "backpack", "start": "@backpack+1.6", "prop": "Backpack", "shot": "close", "angle": 0},
    # A -> C: guilty
    {"name": "guilty", "start": "@guilty", "subject": "King", "shot": "close", "angle": 10},
    {"name": "leo wins", "start": "@guilty+1.0", "subject": "LeoC", "shot": "medium", "angle": 10},
    # B: sorry
    {"name": "nobody argues", "start": "@nobody", "subject": "Leo", "with": "Maya", "shot": "full", "angle": 10},
    {"name": "say sorry", "start": "@nobody.end-2.0", "subject": "Maya", "shot": "medium", "angle": 15},
    # D: the bakery
    {"name": "i'm timmy", "start": "@me", "subject": "TimmyB", "shot": "close", "angle": 0},
    {"name": "bakery", "start": "@cupcake", "pos": [350, 7, 10], "look": [350, 3.5, -5], "fov": 60, "subjects": []},
    {"name": "last cupcake", "start": "@cupcake+1.4", "subject": "Baker", "shot": "close", "angle": 10},
    {"name": "same second", "start": "@cupcake.end-2.2", "subject": "TimmyB", "with": "PrestonB", "shot": "medium", "angle": 35},
    {"name": "see you in court", "start": "@sued", "subject": "PrestonB", "shot": "close", "angle": 0},
    {"name": "timmy gulps", "start": "@sued.end-1.0", "subject": "TimmyB", "shot": "close", "angle": 0},
    # A: the trial
    {"name": "three lawyers", "start": "@lawyers", "subject": "L2", "with": "L3", "shot": "full", "angle": 0},
    {"name": "he's ten", "start": "@lawyers.end-1.2", "subject": "PrestonH", "shot": "close", "angle": 0},
    {"name": "my dog", "start": "@dog", "subject": "TimmyH", "shot": "medium", "angle": 15},
    {"name": "biscuit", "start": "@dog+1.6", "prop": "Biscuit", "shot": "close", "angle": 0},
    {"name": "preston laughs", "start": "@dog.end-2.0", "subject": "PrestonH", "shot": "medium", "angle": -10},
    {"name": "forty minutes", "start": "@case", "subject": "L2", "shot": "medium", "angle": 0},
    {"name": "charts", "start": "@case+2.4", "prop": "Chart", "shot": "close", "angle": 0},
    {"name": "a song", "start": "@case.end-1.6", "subject": "L1", "with": "L3", "shot": "full", "angle": 0},
    {"name": "king asks", "start": "@turn", "subject": "King", "shot": "close", "angle": 0},
    {"name": "nothing", "start": "@think", "subject": "TimmyH", "shot": "close", "angle": 0},
    {"name": "the cupcake", "start": "@think.end-1.6", "subject": "TimmyH", "shot": "medium", "angle": -15},
    {"name": "in half", "start": "@split", "subject": "TimmyH", "shot": "medium", "angle": 20},
    {"name": "bigger piece", "start": "@split+2.2", "subject": "PrestonH", "shot": "medium", "angle": 0},
    {"name": "quiet", "start": "@quiet", "pos": [3198.5, 12, -8], "look": [3198.5, 6, -30], "fov": 50, "subjects": []},
    {"name": "lawyer cries", "start": "@cried", "subject": "L3", "shot": "close", "angle": 0},
    {"name": "smile", "start": "@smile", "subject": "King", "shot": "medium", "angle": 0},
    {"name": "smiled", "start": "@smile.end-1.8", "subject": "King", "shot": "close", "angle": 10},
    {"name": "new law", "start": "@law", "subject": "King", "shot": "medium", "angle": 15},
    {"name": "share it", "start": "@law.end-2.4", "subject": "TimmyH", "with": "PrestonH", "shot": "full", "angle": 0},
    {"name": "empty court", "start": "@closed", "subject": "King", "shot": "close", "angle": -10},
    # C: the letter
    {"name": "letter", "start": "@letter", "subject": "TimmyC", "shot": "medium", "angle": 0},
    {"name": "suing me", "start": "@letter.end-1.6", "subject": "TimmyC", "shot": "close", "angle": 10},
    # A: the twist
    {"name": "his job", "start": "@job", "subject": "King", "shot": "close", "angle": 0},
    # E: the cupcake stand
    {"name": "stand", "start": "@end", "pos": [2340, 6, 54], "look": [2340, 3.5, 38], "fov": 50, "subjects": []},
    {"name": "cut in half", "start": "@end+3.2", "prop": "CakeS1", "shot": "close", "angle": 0},
    {"name": "happy ending", "start": "@end.end-1.8", "subject": "KingP", "with": "TimmyP", "shot": "medium", "angle": 0},
]

FACES = {
    "King": [(0, "neutral"), ("@judge+2.0", "angry"), ("@birdwon", "tired"), ("@birdwon+3.0", "neutral"),
             ("@guilty", "angry"), ("@case", "tired"), ("@turn", "neutral"), ("@quiet", "shocked"), ("@smile", "happy"),
             ("@law", "grin"), ("@closed", "sad"), ("@job", "angry")],
    "TimmyH": [(0, "neutral"), ("@dog", "happy"), ("@case", "tired"), ("@turn+1.4", "scared"), ("@think", "sad"),
               ("@split", "neutral"), ("@split+2.0", "happy"), ("@smile", "shocked"), ("@smile+1.6", "grin")],
    "PrestonH": [(0, "smug"), ("@dog+1.4", "grin"), ("@case", "smug"), ("@split+2.0", "shocked"), ("@smile", "neutral"),
                 ("@smile+2.0", "happy"), ("@law+2.4", "grin")],
    "L1": [(0, "neutral"), ("@case+3.4", "grin"), ("@cried", "shocked")],
    "L2": [(0, "smug"), ("@case+3.4", "grin"), ("@cried", "shocked")],
    "L3": [(0, "neutral"), ("@case+3.4", "grin"), ("@cried", "crying"), ("@law", "happy")],
    "Maya": [(0, "neutral"), ("@bird", "happy"), ("@bird+2.0", "angry"), ("@birdwon.end-1.4", "shocked"),
             ("@nobody+1.4", "happy")],
    "Leo": [(0, "neutral"), ("@bird+0.8", "happy"), ("@bird+2.8", "angry"), ("@birdwon.end-1.4", "shocked"),
            ("@nobody", "grin")],
    "LeoC": [(0, "neutral"), ("@backpack", "angry"), ("@guilty+0.6", "grin")],
    "Teacher": [(0, "neutral"), ("@backpack+1.2", "tired"), ("@guilty+0.8", "neutral")],
    "TimmyC": [(0, "neutral"), ("@letter", "happy"), ("@letter+2.4", "shocked"), ("@job", "scared")],
    "Baker": [(0, "happy"), ("@cupcake+3.0", "shocked"), ("@sued", "tired")],
    "TimmyB": [(0, "happy"), ("@me.end-1.4", "shocked"), ("@cupcake", "happy"), ("@cupcake+4.0", "angry"),
               ("@sued", "scared")],
    "PrestonB": [(0, "smug"), ("@cupcake+4.0", "angry"), ("@sued", "smug")],
    "KingP": [(0, "happy"), ("@end+2.4", "grin")],
    "TimmyP": [(0, "happy"), ("@end+4.8", "grin")],
    "PrestonP": [(0, "happy"), ("@end+4.8", "grin")],
}

# objects from other episodes' street/bakery sets that must stay out of shot (an object with no show spans is hidden)
HIDE = [["Workspace", "Sets", n] for n in ("PaidBench", "SaleChair0", "SaleChair1", "SaleChair2", "SaleChair3", "CarryChair",
                                           "MomChair", "Jar")] + \
       [["Workspace", "Sets", "ChairMarket", "Sign"], ["Workspace", "Sets", "ChairMarket", "Price"],
        ["Workspace", "Sets", "TimmyRoom", "Poster"]]
TO_END = "@end.end+2.0"
PROPS = [{"path": p, "show": []} for p in HIDE] + [
    # A: the court is dressed the whole time; the dog and the chart arrive with the trial
    {"path": EP("Throne"), "show": [[0.0, TO_END]]},
    {"path": EP("Biscuit"), "show": [["@lawyers", TO_END]]},
    {"path": EP("Chart"), "show": [["@lawyers", TO_END]]},
    # the cupcake (evidence) in Timmy's hand, broken in half, the bigger half handed to Preston
    {"path": EP("CakeH"), "show": [["@lawyers", "@split+1.2"]], "attach": {"actor": "TimmyH", "hand": "Right", "offset": HAND}},
    {"path": EP("CakeHT"), "show": [["@split+1.2", TO_END]], "attach": {"actor": "TimmyH", "hand": "Right", "offset": HAND}},
    {"path": EP("CakeHP"), "show": [["@split+1.2", "@split+2.4"]], "attach": {"actor": "TimmyH", "hand": "Left", "offset": HAND}},
    {"path": EP("CakeHP"), "show": [["@split+2.4", TO_END]], "attach": {"actor": "PrestonH", "hand": "Right", "offset": HAND}},
    # B: the bird on the grass
    {"path": EP("Bird"), "show": [["@bird", "@nobody.end+0.5"]]},
    # C: the backpack on the floor by Leo; the letter in Timmy's hands
    {"path": EP("Backpack"), "show": [["@backpack", "@guilty.end+0.5"]]},
    {"path": EP("Letter"), "show": [["@letter", "@job.end+0.5"]], "attach": {"actor": "TimmyC", "hand": "Right", "offset": HAND}},
    # D: the last cupcake, held out by the baker, then in Timmy's hand
    {"path": EP("CakeB"), "show": [["@me", "@cupcake+3.2"]], "attach": {"actor": "Baker", "hand": "Right", "offset": HAND}},
    {"path": EP("CakeB"), "show": [["@cupcake+3.2", "@sued.end+0.5"]], "attach": {"actor": "TimmyB", "hand": "Right", "offset": HAND}},
    # E: the stand with its halves; each kid gets one
    {"path": EP("Stand"), "show": [["@end", TO_END]]},
    {"path": EP("CakeS1"), "show": [["@end", TO_END]]},
    {"path": EP("CakeS2"), "show": [["@end", TO_END]]},
    {"path": EP("CakePT"), "show": [["@end+3.0", TO_END]], "attach": {"actor": "TimmyP", "hand": "Right", "offset": HAND}},
    {"path": EP("CakePP"), "show": [["@end+3.0", TO_END]], "attach": {"actor": "PrestonP", "hand": "Right", "offset": HAND}},
]

FX = [
    {"actor": "Maya", "kind": "label", "show": [["@bird+1.0", "@bird.end+0.3", "I SAW IT FIRST"]]},
    {"actor": "King", "kind": "label", "show": [["@birdwon+3.0", "@birdwon.end", "THE BIRD WINS"],
                                                 ["@guilty", "@guilty.end+0.3", "GUILTY"],
                                                 ["@law+1.4", "@law.end+0.3", "SHARE IT = NO SUING"],
                                                 ["@closed+1.0", "@closed.end+0.3", "CLOSED"]]},
    {"actor": "King", "kind": "sparkle", "show": [["@smile+1.6", "@smile.end+0.6"]]},
    {"actor": "PrestonB", "kind": "label", "show": [["@sued+1.6", "@sued.end+0.3", "SEE YOU IN COURT"]]},
    {"actor": "TimmyH", "kind": "label", "show": [["@split+0.8", "@split.end", "HALF"]]},
    {"actor": "TimmyH", "kind": "confetti", "show": [["@law+2.4", "@law.end+0.8"]]},
    {"actor": "L3", "kind": "rain", "show": [["@cried", "@cried.end+0.6"]]},
    {"actor": "TimmyC", "kind": "label", "show": [["@letter+2.4", "@letter.end+0.3", "YOU'RE BEING SUED"]]},
    {"actor": "KingP", "kind": "hearts", "show": [["@end+3.0", "@end.end+1.6"]]},
]
MUSIC = {"query": "whimsical", "pick": 0, "from": 0, "gain": 0.45}
SFX = [("@rule+0.4", "gavel", 0.6), ("@judge+2.0", "fanfare", 0.4), ("@bird+1.8", "bird chirp", 0.6),
       ("@birdwon+0.6", "clock ticking", 0.4), ("@birdwon.end-1.2", "gavel", 0.6), ("@backpack+1.6", "boing", 0.4),
       ("@guilty", "gavel", 0.7), ("@nobody+0.6", "stomp", 0.5), ("@me.end-1.0", "record scratch", 0.6),
       ("@cupcake", "shop bell", 0.5), ("@cupcake+2.0", "whoosh", 0.4), ("@sued+1.6", "boom", 0.5),
       ("@lawyers+1.6", "gasp", 0.4), ("@dog+0.6", "dog bark", 0.6), ("@case+3.4", "choir", 0.4),
       ("@turn", "drumroll", 0.4), ("@think", "crickets", 0.5), ("@split+0.8", "squish", 0.5),
       ("@cried", "sad violin", 0.4), ("@smile", "angel choir", 0.5), ("@law", "gavel", 0.7), ("@law+2.4", "cheer", 0.5),
       ("@closed+1.0", "crickets", 0.4), ("@letter+2.4", "record scratch", 0.6), ("@job", "gavel", 0.6),
       ("@end", "ding", 0.4), ("@end.end-1.2", "laugh", 0.4)]
