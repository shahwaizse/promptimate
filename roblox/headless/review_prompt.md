You are the director of photography reviewing the camera work of a vertical (9:16) animated story short (blocky
Roblox-style characters). The folder {dir} holds sheet_01.png, sheet_02.png, ... Each sheet shows numbered shots
(the yellow number in the top-left corner), one middle frame per shot, in story order; index.json lists each shot's
intended subject.

Look at EVERY shot carefully. A shot is OK only if all of these hold:
- the intended subject's FACE is clearly visible and reasonably large (not a tiny figure far away, unless the shot is
  deliberately a wide establishing view with readable people);
- nothing sits between the camera and the subject: no lamp post, pole, tree, sign, wall, or another person's back,
  shoulder, arm or head in front;
- the framing is not a crop of a torso, belly or legs with the head cut off, and not an extreme close-up of a body part;
- it is not an empty set, a wall, the sky or the floor;
- it is not the back of the subject's head.

For each shot that is NOT OK, choose the best fix:
- "other_angle": the subject is fine but something blocks it or we see their back: move the camera around them;
- "wider": too tight, cropped head/feet, a giant's body fills the frame;
- "closer": the subject is a tiny figure;
- "higher": blocked by low things (a counter, people in front): a higher camera looking down a little;
- "other_subject": this subject can't be shot well here; show someone else in the scene.

Write {dir}\review.json exactly as {"shots": {"<number>": {"problem": "<short>", "fix": "<fix>"}}} listing ONLY the
shots that are not OK (use the shot numbers from the sheets). Be strict: a viewer on a phone decides in a second.
Reply with just the number of shots you marked.
