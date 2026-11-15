# Blind review: three versions of one Roblox story short

You are judging three renders (X, Y, Z) of the same 32-second vertical Roblox story short in the viral
"In This Town" format. Same town, same characters, same camera, same shot list, same narration. Only the character
animation differs. You only see frames, never the video or how each version was made. Judge what is on screen.

**Story (narration):** "In this town, nobody is allowed to sit down. But Timmy was so tired. So he sat. Just for one
second. Then his phone rang. 'Timmy! The Sit Police are coming!' He ran, and hid behind the crates. The officer looked
everywhere. Mrs. Lee pointed. Of course she did. Timmy held his breath. 'Boo!' But the officer didn't arrest him.
'Mind if I sit too? My feet are killing me.' Turns out, even the Sit Police get tired."

Cast: Timmy (yellow head, blue shirt, green pants), the Officer (navy uniform, cap), Mrs. Lee (pink top, grey hair).

**Files** (in `{JUDGE_DIR}`):
- `X_beats.jpg`, `Y_beats.jpg`, `Z_beats.jpg`: each story beat as 4 frames (0.6 s and 0.2 s before, then 0.2 s and
  0.6 s after the beat). The label says what should be visible.
- `X_shots.jpg`, `Y_shots.jpg`, `Z_shots.jpg`: one frame from the middle of each of the 19 shots, in order.

Open all six images (zoom in with crops if you need to; Python + PIL is available at
`D:\unity-text-to-anim\.venv\Scripts\python.exe`). Then score each version:

1. **Beat readability** for each of the 11 beats: 2 = clearly reads without narration, 1 = readable only with the
   narration, 0 = doesn't read or contradicts it. Give the 11 scores per version.
2. **Story clarity** 1-10: could a viewer follow the story from the pictures plus the narration?
3. **Naturalness** 1-10: do the poses look like plausible, intentional body language for these characters
   (Roblox-style blocky avatars, so judge the motion, not the art style)? Penalise broken poses, floating, sinking
   into the ground or furniture, limbs through objects, frozen T-pose-like stances.
4. **Continuity** 1-10: from frame to frame and shot to shot, are characters where they should be and do poses flow,
   or do they pop, teleport or contradict the previous shot?
5. **Overall rank** (best to worst) and 3-6 sentences on the biggest differences, naming specific beats and frames.

Be concrete and skeptical. Don't assume any version is better. Reply with a JSON block first:
`{"X": {"beats": [..11..], "story": n, "naturalness": n, "continuity": n}, "Y": {...}, "Z": {...}, "rank": ["?", "?", "?"]}`
then your notes.
