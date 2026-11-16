# Promptimate section for the "In This Town" prompt

Paste this in place of the prompt's animation section (stock animation IDs, `Animator:LoadAnimation`,
`Humanoid:MoveTo`). It needs the `kimodo-motion` MCP server connected next to Roblox Studio's MCP server.

---

## Character animation: Promptimate (replaces stock animations)

**Rule:** for every character's performance, and for any action other than plain walking or idling, call
`roblox_perform`. Make one call per character with all of that character's beats in story order. Never write
Animator, MoveTo or animation-ID code for the cast, and never paste animation data into `execute_luau`.
The tool pushes the clips into the place itself.

**Cast:** build each character as an R15 rig (`Players:CreateHumanoidModelFromDescription`) with a unique Model
name. `roblox_perform` measures each rig and handles its size.

**Clock:** all characters share one story clock, in seconds from the start of the short. Set `at` on a character's
first beat, and on any beat that must line up with someone else.

**Writing beats**
- `prompt` describes what the body does, starting with "a person": the body part and side, the direction, the manner.
  Leave out names, story and props. Write "a person walks forward slowly and nervously, looking around", not "Timmy
  sneaks to the crates".
- Put one or two actions in each segment. A single action (wave, jump, point, fall) takes 2-3 s. Continuous activity
  (walk, talk, idle) takes as long as it needs. For a sequence inside one beat, use lists:
  `prompt: [..], seconds: [..]`.
- `to`: where the character ends up. Give an `[x, z]` point in studs or a name: `"Bench"`, `"Officer"`, or a side
  like `"Crates:+X"`. The character stops short of objects and people. Add `via` waypoints to go around obstacles.
  Top speed is a run, about 3 m/s.
- `face`: who or what the character faces at the end of the beat (`"Officer"`, `"+X"`). Set it whenever the next
  shot depends on it.
- Sitting: put `sit: "Bench"` on the sit-down beat and on every seated beat after it. Leave it off the stand-up
  beat. Characters who share a seat get separate spots, sized to their bodies. Put them in the same `roblox_perform` call (`actors: [A, B]`).
- Cover: `peek: "right"` on a beat behind cover ("a person crouches, steps to the right and leans out to look, then steps back"). The character steps out about 0.6 m, looks, and returns to cover.
- Falls: "a person gets startled and falls backward onto their back" (2.5 s), then "a person sits up on the ground
  and looks up".
- These don't work: fingers, holding or using props, facial expressions (use FaceControls), very fast footwork.

**Staging:** read `warnings` in the result. To fix one, edit that beat (`to`, `via`, `face`, `sit`, `at` or the
prompt) and call again for that character. Unchanged beats are reused.
- "passes through X": add `via` or move the mark.
- "ends facing N deg away": add `face`.
- "hovers above / sinks into Bench": check the seat object.
- "overlap": separate the marks.

**Cameras and recording:** turn the shot list into camera cues for `roblox_record`. Each cue has a `start` time,
then either `pos` + `look` or `track` + `offset`, plus `fov` and `subjects`. Call it with `check_only: true`
first. Then fix the camera warnings (camera inside a prop or body, subject hidden, out of frame, head cut off) and
look at the shot sheet. When it's clean, call `roblox_record` without `check_only`. It renders a 9:16 MP4 in the
background; poll with `job`. For a quick realtime look, press Play: the director performs every character, and you
can screen-record the window.
