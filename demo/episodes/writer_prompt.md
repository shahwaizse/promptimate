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

CATALOG
{catalog}
