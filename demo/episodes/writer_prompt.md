You write one "In this town" vertical story short (about 75-90 s narrated) as a compact story spec, a Python file. A
compiler turns it into a full episode; you only write the story and the blocking.

FORMAT. A narrator (a kid, first person) explains one weird rule of the town, then a story built on it. Line 1 states
the rule and is the hook. Then: who wins and who loses under the rule, a villain who abuses it, everything goes wrong,
the narrator does something small and brave, a twist that flips the rule back on itself, and a warm, funny last line.
14-18 short lines, each 8-22 words, plain words a kid would say. Concrete numbers and names. Never mention the camera.

STAGING RULES
- Character names are one word (Rosa, Bruno, MsPark).
- Each scene is one SET. A character is copied per set, so put people in the scene where they act. 2-4 people per
  scene. Revisit a set by repeating it as a new scene with the same "place" (positions carry over).
- "place" uses the set's spot names, optionally offset in studs: "door:0,3". People in one scene should be 4-10 studs
  apart (use offsets) and roughly face each other or the camera side.
- Every line: 1-3 people act ("do"), each with 1-3 actions in order. Actions must be physical and match the words:
  someone mentioned does something visible. Add "@Name" to finish facing someone, ">Name" or ">spot" to walk there
  (walk actions only). Keep the total action seconds near the line's length (words / 2.5 seconds).
- "cam": 1-3 cuts spread over the line: "Name" (single), "Name+Other" (two-shot), or a prop name (insert shot).
  Start a set with the person the line is about. Cut often: most lines get 2-3 cuts.
- "feel": the face each acting person makes. Use labels (short ALL-CAPS on-screen text like "+1 COIN", "0 COINS") on
  about half the lines, FX for big moments, 1 SFX on most lines, 1-2 "title" words for the biggest beats.
- Props: "at" a spot (or a person's name: placed in front of them), "hold": a person carries it, "small": true for a
  coin-sized prop. Show/hide them by line ("show": [...], "hide": [...]); shown stays on until hidden.

Write exactly this structure (valid Python, nothing else):

TITLE = "In This Town, ..."
MUSIC = "whimsical"
KEYWORDS = ["...", ...]          # 10-20 words of the story that should pop in the captions
CAST = {"Name": "look", ...}
SCENES = [
    {"set": "Bakery", "place": {"Rosa": "behind_case", "Gus": "door:0,-3"},
     "props": [{"name": "Coins", "prop": "coin_pile", "at": "case_front", "small": True}],
     "lines": [
        {"id": "rule", "say": "In this town, every time someone gives you a real compliment, a gold coin drops into your pocket.",
         "do": {"Gus": "walk>Rosa talk", "Rosa": "happy clap@Gus"}, "cam": ["Rosa", "Gus+Rosa", "Coins"],
         "feel": {"Rosa": "grin", "Gus": "happy"}, "label": "+1 COIN", "fx": {"Rosa": "sparkle"}, "sfx": "coin drop",
         "show": ["Coins"], "title": "COMPLIMENTS"},
     ]},
]

Line ids are short unique lowercase words. Use only names from the catalog below; anything else is dropped.

CATALOG
{catalog}
