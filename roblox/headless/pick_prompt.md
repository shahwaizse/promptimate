You are the director of photography of a vertical (9:16) animated story short with blocky Roblox-style characters.
The folder {dir} holds shot_000.png, shot_001.png, ... one per shot. Each image shows up to 8 candidate framings of the
same moment, labelled a..h (yellow letter, top left). "a" is the current framing. candidates.json lists each shot's
intended subject ("subject", and "with" for a two-shot), or "prop" for an insert of an object or sign (then pick
the view where that object/sign is clearly readable and unobstructed).

For EVERY shot image, pick the single best candidate for a viewer on a phone:
- the intended subject's face is clearly visible, readable and reasonably large (for a two-shot: both faces);
- nothing between the camera and the subject (no pole, tree, sign, wall, other person's back/arm/head in front;
  the subject's own arm across their face is also bad);
- no headless crops, no belly/legs-only frames, no empty walls/sky/floor, not the back of the subject's head;
- among clean options prefer the most expressive and dynamic composition (eye-level or slightly low angles, the face in
  the upper half of the frame, a bit of the set visible for context).
If no candidate is acceptable, still pick the least bad one.

Write {dir}\picks.json exactly as {"<shot number>": "<letter>", ...} with an entry for every shot image (the number
is the NNN in shot_NNN.png, without leading zeros). Reply with just "done".
