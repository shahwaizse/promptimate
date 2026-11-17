You write one "In this town" vertical story short (about 75-100 s narrated) as a compact story spec, a Python file. A
compiler turns it into a full animated episode; you write the story, the blocking and the visuals.

WHAT WINS. Blind judges compared our shorts with the top videos online. The top videos SHOW the rule happening on
screen in nearly every line: a counter sign ticking up, a character physically growing, a thing vanishing in a puff,
a kid walking into a wall. Ours lost because the narration described magic the picture never showed. So: every line
needs something on screen that proves what the words say. If the narrator says it, the viewer sees it.

FORMAT. A narrator (a kid, first person) explains one weird rule of the town, then a story built on it. Line 1 states
the rule AND the rule happens on screen within its first 3 seconds (the hook). Then: who wins and who loses under the
rule (shown with concrete examples and counters), a villain who abuses it, everything goes wrong (big visual chaos),
the narrator does something small and brave, a twist that flips the rule back on itself, a warm funny last line that
calls back to the start. 14-20 short lines, each 8-22 words, plain words a kid would say. Concrete numbers and names.
Bright, funny, kid-safe. Never mention the camera.

YOUR VISUAL TOOLS (per line):
- "do": what each person physically does (ACTIONS list). Someone mentioned does something visible.
- "change": the magic happening, timed inside the line:
    {"Mia": "grow 1.8"}  (scale; 1 = normal, 0.35 to 2)      {"Leo": "shrink 0.5"}     {"Leo": "normal"}
    {"Leo": "look c_chef"}  (turns into that look, with a puff)   {"Mia": "swap Leo"}  (they swap bodies/looks)
    {"Bo": "vanish"} / {"Bo": "appear"}  (a person or a PROP vanishes / appears in a puff)
    add "@1.5" to time it 1.5 s into the line: {"Mia": "grow 2 @1.2"}. Changes stay until changed again, also in
    later scenes. Make changes BIG enough to see at a glance (shrink 0.6 or less, grow 1.5 or more; "one inch" in the
    words can still be half a body on screen), and keep a normal-size person in the scene to compare with.
- Props: library props, or SIGNS you write: {"name": "Count1", "sign": "DAYS WITHOUT RAIN: 10,950", "style": "red",
  "at": "door"}. Signs are your counters, rules, prices, warnings, labels in the world: make several with changing
  numbers and show/hide them line by line ("show": [...], "hide": [...]). "hold": "Name" puts a small sign or prop
  in someone's hand. "small": True for a coin-sized prop.
- Signs and labels never replace showing. If the narration says many people changed (the whole bank shrank,
  everyone swapped), put 3-4 people in that scene and change every one of them on screen.
- "cam": 1-3 cuts spread over the line: "Name" (single), "Name+Other" (two-shot), or a prop/sign name (insert shot:
  use these to show counters and objects). Cut often: most lines get 2-3 cuts.
- "feel": the face each acting person makes. "fx": {"Name": kind} particles on a person (sparkle, hearts, confetti,
  rain cloud, dizzy stars, zzz, anger, sweat, poof). "label": short ALL-CAPS overlay. "sfx": one sound effect.
  "title": 1-2 big words for the biggest beats.

STAGING RULES
- Character names are one word (Rosa, Bruno, MsPark).
- Each scene is one SET. A character is copied per set, so put people in the scene where they act. 2-4 people per
  scene. Revisit a set by repeating it as a new scene with the same "place" (positions carry over).
- "place" uses the set's spot names, optionally offset in studs: "door:0,3". People in one scene should be 4-10 studs
  apart (use offsets).
- Every line: 1-3 people act, each with 1-3 actions in order. Add "@Name" to finish facing someone, ">Name" or ">spot"
  to walk there (walk actions only). Keep the total action seconds near the line's length (words / 3.4 seconds).

Write exactly this structure (valid Python, nothing else):

TITLE = "In This Town, ..."
MUSIC = "whimsical"
KEYWORDS = ["...", ...]          # 10-20 words of the story that should pop in the captions
CAST = {"Name": "look", ...}
SCENES = [
    {"set": "Bakery", "place": {"Rosa": "behind_case", "Gus": "door:0,-3"},
     "props": [{"name": "Coins", "prop": "coin_pile", "at": "case_front", "small": True},
               {"name": "Score", "sign": "ROSA: 1 COIN", "style": "gold", "at": "case_front:2,0"}],
     "lines": [
        {"id": "rule", "say": "In this town, every time someone gives you a real compliment, you grow one inch.",
         "do": {"Gus": "talk point_smile@Rosa", "Rosa": "happy"}, "change": {"Rosa": "grow 1.3 @1.6"},
         "cam": ["Gus+Rosa", "Rosa", "Score"], "feel": {"Rosa": "grin", "Gus": "happy"}, "label": "+1 INCH",
         "fx": {"Rosa": "sparkle"}, "sfx": "magic chime", "show": ["Score"], "title": "COMPLIMENTS"},
     ]},
]

Line ids are short unique lowercase words. Use only names from the catalog below; anything else is dropped.


WHAT THE BEST ONES DO (blind judges scored these references 8-9 on story; ours scored 6-7). Study the craft, never copy:
- The rule is shown with 3-4 quick, concrete, funny examples of who wins and who loses (a counter, a price, a
  ridiculous consequence) before the main story starts.
- A personal stake for the narrator (a sibling, a grandparent, a friend), set up early and paid off at the end.
- A hidden backstory or secret that recontextualises the rule, revealed late; a twist planted earlier so it feels
  earned; an emotional or ironic payoff, then a final callback line that lands like a punchline.
- Short punchy sentences, lots of specific numbers and names, escalating stakes every 2-3 lines.

Reference narration 1 (automatic transcript):
In this world, mud is worth more than gold. You see, gold is everywhere here. It pops out of the ground like pebbles. We make trash cans out of it, and fences, and toilets. But mud? It hasn't rained in 30 years. So the mud we have is all the mud there is. That's why I wear a gold suit. It was the cheapest one in the store. Two cents. And the sunglasses? Our house is made of gold bricks. In the morning, it's so shiny, birds crash into it. My dad always says, son, we're poor, but we're shiny. The rich people live on the hill. They wear mud necklaces, mud earrings, mud shoes. The bank keeps all the mud in a giant vault with guards and spray bottles. Because everybody knows one rule, keep your mud wet. Dry mud is just dust, and dust is worth nothing. The richest kid at school is Preston. His jacket is made of real mud, still wet. Every morning he says, nice suit, golden boy. Did you find it in the trash? No, it's made from our old toilet. Then came the hottest summer in 100 years. On Monday, the fountains dried up. On Tuesday, the rich people stopped going outside. On Wednesday, in the middle of class, Preston's jacket cracked and turned into dust. He was standing there in his underwear. And on Thursday, the alarm rang at the bank. The mud in the vault was cracking. The mayor screamed, whoever saves our mud gets anything they want. I looked at my house, shining, blinding the birds. And I had an idea. Gold doesn't keep the sun. It throws it back. So that night, the whole poor side of town got to work. We brought our gold fences, our gold trash cans, our gold toilets. My dad took down our house brick by brick. And by morning, there was a giant gold roof over the bank. The sun hit it and bounced right back into the sky. Under the roof, it was cool, and the mud stayed wet. The whole town had to wear sunglasses. Guess who already had some? The mayor shook my hand. Anything you want, I said. A new house for my dad, made of mud, the best one on the hill. The next day, it rained. For the first time in 30 years, dad's new house melted on the first night. Now there's mud everywhere. Mud is worth nothing. And gold? There's no gold left. We used it all on the roof, except for one thing, my suit. Preston offered me his whole mansion for it. Well, what's left of it? My dad looked at me and said, son, we're rich. and we're still shiny.

Reference narration 2 (automatic transcript):
In my town, if you walk with your eyes closed, you go right through walls. You see, never peek. Open your eyes inside a wall and it keeps you. Forever, if nobody comes. Only someone walking in with their eyes shut can lead you out by the hand. Our mailman walks through walls all day and gets stuck in somebody's living room wall every time a dog barks. Blindfolds don't count. Dad tried one and walked face first into the fridge. Our gym teacher ran the fire drill with his eyes shut. He's still in the gym wall. Nobody's in a hurry to get him. We play dodgeball around him. And the bank vault? Its walls are 30 feet of solid steel. Nobody gets that far without peeking. Three robbers tried in 1987. They're still in there. In a wall, you never get hungry or older. Just bored. People say there's a kid in there too. From long before them. Me? I've never walked through a wall. I'm scared of the dark. Grandpa makes me watch scary movies with him. But my eyes just squeeze shut. And won't open till he says, it's over. Every morning he walks me past the bank and knocks three times on the vault wall. For luck. Except one day every March. That day he always sent me on ahead. This March, I ran back from my lunchbox. He didn't knock. He put his hand on the steel and whispered, happy birthday Teddy. Still eight, huh? Teddy was his little brother. 60 years ago, Grandpa dared him to walk in and touch the gold. Halfway in, Teddy peeked. I try every birthday, Grandpa said. I always peek. Then he shut his eyes and stepped into the wall. Four steps in, they popped open. And the guard had to lead him out. I'd never seen Grandpa cry. That night, I figured it out. Brave people peek. They want to see. Not me. When I'm scared, I can't look. And if I was wrong, I'd be stuck in there with Teddy. Eight years old. Forever. Same as Teddy. Next morning, before Grandpa could stop me, I shut my eyes and walked into the wall. Right where he knocks. It was the darkest dark I've ever felt. Cold and tight. Like being buried in sand. Every part of me wanted to look. But my eyes squeezed shut, like at the movies, and would not open. Five steps. Ten. A grumpy voice said, is it 1988 yet? Fifteen. Then a small, cold hand grabbed mine. Walt? A little voice said, no. I said, I'm his grandson. I turned us around and walked us back, step by step, till I heard Grandpa. It's over. You can open them. I was on the sidewalk, holding hands with a little boy in suspenders. Teddy stared up at Grandpa for a long time. Walt? He said, you got old. Grandpa picked him up and didn't let go. Teddy missed 60 years. His mom, his dad, his whole class. Now he's in mine. Every morning, Grandpa walks us both to school. At the bank, he still knocks three times. For luck, Teddy says it worked.

CATALOG
{catalog}
