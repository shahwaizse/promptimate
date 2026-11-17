TITLE = "In This Town, Your Birthday Lets You Swap Bodies"
MUSIC = "whimsical"
KEYWORDS = ["birthday", "swap", "can't say no", "Timmy", "forty tickets", "homework", "Birthday Book", "Mayor's hand",
            "hides", "zero guests", "Grandma", "eighty", "Preston", "eleven steals", "everybody's birthday", "forever",
            "nine times", "invite", "312", "twice"]
CAST = {
    "Mia": "c_girl",
    "Grandma": "c_grandma",
    "Preston": "c_preston",
    "Mayor": "c_mayor",
    "Rex": "c_guard",
    "Timmy": "c_timmy",
    "Chief": "c_police",
    "Jen": "c_girl2",
    "MsPark": "c_teacher",
    "Bo": "c_boy2",
    "Hal": "c_businessman",
    "Dad": "c_dad2",
    "Gus": "c_chef",
    "Dukes": "c_police_f",
}
SCENES = [
    # 1. The hook: a birthday kid swaps with the police chief on screen.
    {"set": "Street", "place": {"Timmy": "bus_stop:-3,0", "Chief": "bus_stop:3,0"},
     "props": [{"name": "Card", "sign": "IT'S MY BIRTHDAY!", "style": "gold", "hold": "Timmy", "at": "bus_stop:-3,1"},
               {"name": "Tickets", "sign": "BROCCOLI TICKETS: 40", "style": "red", "at": "bus_stop:0,4"}],
     "lines": [
        {"id": "rule", "say": "In this town, on your birthday, you can swap bodies with anyone you want for one day. "
                              "And they can't say no.",
         "do": {"Timmy": "point_smile@Chief look_self cheer", "Chief": "stare look_self"},
         "change": {"Timmy": "swap Chief @1.8"},
         "cam": ["Timmy+Chief", "Chief", "Timmy"], "feel": {"Timmy": "grin", "Chief": "shocked"},
         "fx": {"Timmy": "confetti"}, "sfx": "magic", "label": "SWAP!", "title": "BIRTHDAY SWAP",
         "show": ["Card"], "hide": ["Tickets"]},
        {"id": "tickets", "say": "Timmy turned nine and picked the Police Chief. He wrote forty tickets for eating "
                                 "broccoli. The real Chief got recess.",
         "do": {"Timmy": "write laugh_at@Chief", "Chief": "stomp angry frustrated"},
         "cam": ["Timmy", "Tickets", "Chief"], "feel": {"Timmy": "smug", "Chief": "angry"},
         "fx": {"Chief": "anger"}, "sfx": "whistle", "label": "40 TICKETS", "show": ["Tickets"]},
     ]},
    # 2. Winners and losers: homework cancelled, teacher takes the test.
    {"set": "Classroom", "place": {"MsPark": "board_front", "Jen": "aisle_front:-3,0", "Mia": "aisle_back:3,0"},
     "props": [{"name": "Homework", "sign": "HOMEWORK: CANCELED FOR 1 YEAR", "style": "white", "at": "board_front:4,0"}],
     "lines": [
        {"id": "homework", "say": "Jen picked our teacher and canceled homework for a whole year. Miss Park had to "
                                  "take the spelling test.",
         "do": {"Jen": "point_smile cheer", "MsPark": "look_self sad", "Mia": "joy"},
         "change": {"Jen": "swap MsPark @1.0"},
         "cam": ["Jen+MsPark", "Homework", "MsPark"], "feel": {"Jen": "grin", "MsPark": "sad", "Mia": "happy"},
         "fx": {"MsPark": "rain"}, "sfx": "school bell", "label": "NO HOMEWORK", "show": ["Homework"]},
     ]},
    # 3. The plant: the Birthday Book, only the Mayor's hand can write in it.
    {"set": "Office", "place": {"Mayor": "boss_desk_front", "Rex": "water_cooler"},
     "props": [{"name": "Book", "prop": "books", "at": "boss_desk_front:0,2", "small": True},
               {"name": "BookSign", "sign": "BIRTHDAY BOOK: MAYOR'S HAND ONLY", "style": "gold", "at": "whiteboard"}],
     "lines": [
        {"id": "book", "say": "Every birthday is written in the Birthday Book at Town Hall. Only the Mayor's hand "
                              "can write in it.",
         "do": {"Mayor": "write point", "Rex": "salute"},
         "cam": ["Mayor", "BookSign", "Mayor+Rex"], "feel": {"Mayor": "smug", "Rex": "neutral"},
         "fx": {"Mayor": "sparkle"}, "sfx": "paper rustle", "label": "MAYOR ONLY", "show": ["BookSign"]},
     ]},
    # 4. The catch and the personal stake: everyone hides, zero guests, Grandma never swaps.
    {"set": "LivingRoom", "place": {"Mia": "sofa_front", "Bo": "centre:0,-3", "Grandma": "window"},
     "props": [{"name": "Hat", "sign": "BIRTHDAY GIRL", "style": "gold", "hold": "Mia", "at": "sofa_front:0,1"},
               {"name": "Guests0", "sign": "MIA'S PARTY GUESTS: 0", "style": "red", "at": "tv_front"},
               {"name": "Cake", "prop": "cake", "at": "centre"},
               {"name": "Count80", "sign": "GRANDMA: 80 BIRTHDAYS, 0 SWAPS", "style": "gold", "at": "bookshelf"}],
     "lines": [
        {"id": "hide", "say": "But here's the catch. On your birthday, everybody hides from you, just in case you "
                              "pick them.",
         "do": {"Mia": "wave@Bo sad", "Bo": "scared run>door"},
         "change": {"Bo": "vanish @4.2"},
         "cam": ["Mia+Bo", "Bo", "Mia"], "feel": {"Mia": "sad", "Bo": "scared"},
         "fx": {"Bo": "sweat"}, "sfx": "scream", "label": "HIDE!",
         "show": ["Hat"], "hide": ["Guests0", "Cake", "Count80"]},
        {"id": "zero", "say": "My parties have had zero guests, three years in a row. Only Grandma Rosa comes, with "
                              "a cake.",
         "do": {"Mia": "sad happy", "Grandma": "walk_happy>sofa_front:4,0 give@Mia"},
         "change": {"Cake": "appear @3.6"},
         "cam": ["Guests0", "Grandma", "Mia+Grandma"], "feel": {"Mia": "sad", "Grandma": "happy"},
         "fx": {"Mia": "rain"}, "sfx": "crickets", "label": "0 GUESTS", "show": ["Guests0"]},
        {"id": "never", "say": "Grandma's had eighty birthdays and never swapped once. She says she's never met "
                               "anyone she'd rather be.",
         "do": {"Grandma": "heart nod@Mia", "Mia": "think hope"},
         "cam": ["Count80", "Grandma", "Mia+Grandma"], "feel": {"Grandma": "love", "Mia": "neutral"},
         "fx": {"Grandma": "hearts"}, "sfx": "aww", "label": "0 SWAPS", "show": ["Count80"]},
     ]},
    # 5. The villain: Preston steals a body every birthday.
    {"set": "Bank", "place": {"Preston": "lobby", "Hal": "vault:3,-3"},
     "props": [{"name": "Gold", "prop": "gold_bars", "at": "vault"},
               {"name": "Steals", "sign": "PRESTON: 11 BIRTHDAYS, 11 STEALS", "style": "red", "at": "queue_start"}],
     "lines": [
        {"id": "preston", "say": "Then there's Preston. Every birthday, he picks whoever has what he wants. Last year, "
                                 "the bank boss.",
         "do": {"Preston": "point_smile@Hal laugh_at@Hal", "Hal": "scared look_self"},
         "change": {"Preston": "swap Hal @2.6", "Gold": "vanish @4.2"},
         "cam": ["Preston", "Preston+Hal", "Gold"], "feel": {"Preston": "smug", "Hal": "shocked"},
         "sfx": "cash register", "label": "SWAP!", "hide": ["Steals"]},
        {"id": "steals", "say": "At midnight he popped back, with the bank's gold in his bedroom. Eleven birthdays, "
                                "eleven steals.",
         "do": {"Preston": "flex laugh_at@Hal", "Hal": "cry frustrated"},
         "change": {"Preston": "look c_preston @0.8", "Hal": "look c_businessman @0.8"},
         "cam": ["Preston+Hal", "Steals", "Hal"], "feel": {"Preston": "smug", "Hal": "crying"},
         "fx": {"Hal": "rain"}, "sfx": "clock chime", "show": ["Steals"]},
     ]},
    # 6. Preston takes the Mayor's body and rewrites the Book.
    {"set": "Office", "place": {"Mayor": "boss_desk_front", "Preston": "door", "Rex": "water_cooler"},
     "props": [{"name": "Today", "sign": "TODAY'S BIRTHDAYS: MIA, PRESTON", "style": "gold", "at": "aisle"},
               {"name": "Forever", "sign": "TODAY IS EVERYBODY'S BIRTHDAY. FOREVER.", "style": "red",
                "at": "whiteboard"}],
     "lines": [
        {"id": "same", "say": "This year, Preston and I had the same birthday. At eight a.m., he marched into Town "
                              "Hall and picked the Mayor.",
         "do": {"Preston": "march>boss_desk_front:0,-4 point@Mayor", "Mayor": "stare look_self"},
         "change": {"Preston": "swap Mayor @4.6"},
         "cam": ["Today", "Preston", "Preston+Mayor"], "feel": {"Preston": "smug", "Mayor": "shocked"},
         "sfx": "magic", "label": "SWAP!", "show": ["Today"], "hide": ["Forever", "BookSign"]},
        {"id": "forever", "say": "He grabbed the Birthday Book and wrote: today is everybody's birthday. Every single "
                                 "day. Forever.",
         "do": {"Preston": "write laugh_at@Mayor", "Mayor": "beg", "Rex": "gasp"},
         "cam": ["Preston", "Forever", "Mayor"], "feel": {"Preston": "smug", "Mayor": "scared", "Rex": "shocked"},
         "fx": {"Preston": "anger"}, "sfx": "thunder", "title": "FOREVER", "show": ["Forever"], "hide": ["Today"]},
     ]},
    # 7. Chaos: the whole street swapping.
    {"set": "Street", "place": {"Dad": "crosswalk_near:-7,0", "Gus": "crosswalk_near:-2,0",
                                "Dukes": "crosswalk_near:3,0", "Grandma": "crosswalk_near:8,0"},
     "props": [{"name": "Swaps1", "sign": "SWAPS TODAY: 48", "style": "red", "at": "crosswalk_near:0,5"},
               {"name": "Swaps2", "sign": "SWAPS TODAY: 3,412", "style": "red", "at": "crosswalk_near:0,5"}],
     "lines": [
        {"id": "chaos", "say": "So everyone picked everyone. Dad became the baker. The baker became a cop. The cop "
                               "became Grandma!",
         "do": {"Dad": "look_self frustrated", "Gus": "shrug stare", "Dukes": "point gasp"},
         "change": {"Dad": "look c_chef @1.2", "Gus": "look c_police @2.4", "Dukes": "look c_grandma @3.6"},
         "cam": ["Dad", "Gus", "Dukes+Grandma"], "feel": {"Dad": "shocked", "Gus": "shocked", "Dukes": "scared"},
         "fx": {"Dad": "dizzy"}, "sfx": "pop", "label": "SWAP! SWAP! SWAP!", "title": "CHAOS",
         "show": ["Swaps1"], "hide": ["Swaps2", "Tickets", "Card"]},
        {"id": "knees", "say": "Nobody could say no, so nobody could stop. Grandma got picked nine times. She just "
                               "wanted her knees back.",
         "do": {"Grandma": "look_self frustrated angry", "Dad": "spin", "Gus": "faint"},
         "change": {"Dad": "look c_king @0.8", "Gus": "look c_nurse @1.6", "Grandma": "look c_mailman @2.6"},
         "cam": ["Swaps2", "Dad+Gus", "Grandma"], "feel": {"Grandma": "angry", "Dad": "shocked", "Gus": "tired"},
         "fx": {"Grandma": "dizzy"}, "sfx": "slide whistle", "label": "PICKED: 9 TIMES",
         "show": ["Swaps2"], "hide": ["Swaps1"]},
     ]},
    # 8. The brave act, the hidden backstory, the twist.
    {"set": "Office", "place": {"Mia": "door", "Preston": "boss_desk_front", "Mayor": "boss_desk_front:-5,0"},
     "props": [{"name": "Forever", "sign": "TODAY IS EVERYBODY'S BIRTHDAY. FOREVER.", "style": "red",
                "at": "whiteboard"},
               {"name": "GuestsP", "sign": "PRESTON'S PARTY GUESTS: 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0",
                "style": "white", "at": "aisle"},
               {"name": "NewRule", "sign": "ON YOUR BIRTHDAY, INVITE ANYONE. THEY CAN'T SAY NO.", "style": "gold",
                "at": "whiteboard"}],
     "lines": [
        {"id": "brave", "say": "I hadn't used my swap yet. So I walked into Town Hall, shaking, and picked the "
                               "Mayor's body. Preston couldn't say no.",
         "do": {"Mia": "walk>boss_desk_front:0,-5 point@Preston look_self", "Preston": "stare look_self"},
         "change": {"Mia": "swap Preston @4.6"},
         "cam": ["Mia", "Mia+Preston", "Preston"], "feel": {"Mia": "scared", "Preston": "shocked"},
         "fx": {"Mia": "sweat"}, "sfx": "magic chime", "label": "SWAP!",
         "show": ["Forever"], "hide": ["GuestsP", "NewRule", "Today"]},
        {"id": "page", "say": "Then I saw Preston's page. Party guests, every year: zero. If everybody has a "
                              "birthday, he whispered, nobody hides from me.",
         "do": {"Mia": "look_hand gasp", "Preston": "sad whisper@Mia"},
         "cam": ["GuestsP", "Mia", "Preston"], "feel": {"Mia": "shocked", "Preston": "crying"},
         "fx": {"Preston": "rain"}, "sfx": "heartbeat", "label": "0 GUESTS. EVERY YEAR.", "show": ["GuestsP"]},
        {"id": "invite", "say": "So I used the Mayor's hand. I crossed out swap bodies with, and wrote invite.",
         "do": {"Mia": "write nod@Preston", "Preston": "stare hope"},
         "cam": ["Mia", "NewRule", "Preston"], "feel": {"Mia": "happy", "Preston": "shocked"},
         "fx": {"Mia": "sparkle"}, "sfx": "magic chime", "title": "INVITE",
         "show": ["NewRule"], "hide": ["Forever", "GuestsP"]},
     ]},
    # 9. The payoff: everyone pops back, 312 guests, Grandma's callback, punchline.
    {"set": "LivingRoom", "place": {"Mia": "sofa_front", "Preston": "centre:-4,0", "Grandma": "centre:4,0",
                                    "Bo": "door"},
     "props": [{"name": "Cake", "prop": "cake", "at": "centre"},
               {"name": "Guests312", "sign": "MIA + PRESTON'S PARTY GUESTS: 312", "style": "gold", "at": "tv_front"},
               {"name": "Count81", "sign": "GRANDMA: 81 BIRTHDAYS, 0 SWAPS", "style": "gold", "at": "bookshelf"},
               {"name": "Invite", "sign": "INVITED: EVERYONE (TWICE)", "style": "gold", "hold": "Preston",
                "at": "centre:-4,1"}],
     "lines": [
        {"id": "party", "say": "At midnight, everybody popped back. Next morning, our party had three hundred and "
                               "twelve guests. They couldn't say no.",
         "do": {"Mia": "look_self dance", "Preston": "look_self cheer", "Grandma": "clap"},
         "change": {"Mia": "look c_girl @0.4", "Preston": "look c_preston @0.4", "Grandma": "look c_grandma @0.4",
                    "Bo": "appear @2.8"},
         "cam": ["Mia+Preston", "Guests312", "Mia"], "feel": {"Mia": "grin", "Preston": "happy", "Grandma": "happy"},
         "fx": {"Mia": "confetti", "Preston": "confetti"}, "sfx": "crowd cheer", "title": "312 GUESTS",
         "show": ["Guests312", "Cake"], "hide": ["Guests0", "Count80", "Hat", "Count81", "Invite"]},
        {"id": "slices", "say": "Grandma cut three hundred and twelve slices. Eighty-one birthdays, still zero swaps. "
                                "She finally met everyone she'd rather be with.",
         "do": {"Grandma": "give@Preston hug@Mia", "Preston": "eat happy", "Mia": "heart"},
         "cam": ["Grandma+Preston", "Count81", "Grandma+Mia"],
         "feel": {"Grandma": "love", "Preston": "happy", "Mia": "love"},
         "fx": {"Grandma": "hearts"}, "sfx": "aww", "show": ["Count81"]},
        {"id": "callback", "say": "So now, on your birthday, you can invite anyone you want, and they can't say no. "
                                  "Preston invited the whole town. Twice.",
         "do": {"Preston": "spread point_smile@Mia", "Mia": "facepalm laugh_at@Preston", "Bo": "clap"},
         "cam": ["Preston", "Invite", "Mia+Preston"], "feel": {"Preston": "grin", "Mia": "happy", "Bo": "happy"},
         "fx": {"Preston": "sparkle"}, "sfx": "laugh", "label": "INVITED x2", "show": ["Invite"]},
     ]},
]
