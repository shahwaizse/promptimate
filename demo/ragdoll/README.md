# Text-to-ragdoll (prototype)

A Promptimate clip played by a **physically simulated character** that reacts to the world: thrown balls, a rolling
boulder, a crate it trips over, a staircase it misses. Each character gets a reaction **personality chosen from
text** ("a frail old man", "a trained fighter who braces", "a drunk who flops"). When a fall ends, the character
gets up with a **generated Promptimate get-up clip**, and the muscles blend back into tracking. Any simulated result
can be **baked back into an ordinary Humanoid clip** that plays with no physics at all (`physics_pass`).

Everything runs locally: Unity 6 PhysX on the CPU for the physics, and motiond on the GPU for the clips.

- Unity project: [`unity/SystemLab/`](../../unity/SystemLab) (Unity 6000.0.34, URP). It doesn't touch DemoStudio or the package.
- Video: `demo/ragdoll/build/text_to_ragdoll_demo.mp4` (gitignored). It has a title card, six shots and a measurements card.

## How it works

```
 text ──► generate_motion ──► .kimodo ──► Humanoid clip ──► invisible TARGET rig (PlayableGraph, root motion)
                                                                   │ local joint rotations, body-part positions
 text ──► personality.py ──► Personality {strength, balance, knockdown, brace, ...}
                                                                   ▼
            visible ACTIVE RAGDOLL: 14 rigidbodies + ConfigurableJoints on the same rig
              • muscles  = joint slerp drives tracking the target's local rotations (PD, per-region strength)
              • balance  = "hand of god" pins pulling each body part toward the target pose (scaled by personality)
              • reflexes = state machine: Puppet → Falling → Lying → GettingUp → Puppet
                                                                   │
                         contacts (Physics.ContactEvent) ──► Hit(part, impulse)
                                                                   ▼
                 rendered frame by frame (offline)   +   baked to a Humanoid .anim (physics_pass)
```

**Body.** There are rigidbodies for the hips, spine, chest, head, upper and lower arms (hand folded in), thighs,
shins and feet. They are built from the Humanoid bone map, so any Humanoid rig works: four Mixamo characters and the
CC0 Kenney character were tested. Colliders are capsules, a head sphere and flat foot boxes. Joints have anatomical
limits: knees and elbows are hinges with their flexion direction measured on the rig, and hips, spine and neck get
swing and twist cones. The shoulders are free. Self-collision is only on between the left and right limbs. Physics
runs at 240 Hz (8 sub-steps per 30 fps frame) with 24 solver iterations.

**Muscles.** Each joint's slerp drive targets the target rig's rotation relative to the *physics* parent. That
folds in the bones that aren't simulated (Spine1, clavicles, neck). Spring = base gain (per body part, scaled by
body size) × personality strength × region gain × hit limpness. The damper is proportional, and torque is capped at
1.6 rad worth of spring, so weak characters can't hold large deflections.

**Balance assist.** This is the honest part. Plain PD tracking can't balance (the research spike in
`docs/text-to-system.md` confirms it). A balance assist is needed: acceleration-mode PD forces on the hips, spine,
chest and legs pull toward the target pose, plus an orientation PD on the hips and chest. Arms and head get no pins,
only muscles. The assist is scaled by `balance` and by the current `pin` state. It **drops to zero as soon as a fall
is committed and stays at zero while the character lies there.** It only comes back during a get-up, ramping in over
about 1 s, so a fallen character is never hauled upright by the assist alone. The motion comes from the get-up clip.
The assist also loses most of its upward pull when no foot touches the ground, so a character who walks off a ledge
falls instead of hovering.

**Reactions** (`ActiveRagdoll.Hit`):
- A hit computes Δv = impulse / body mass. The struck part and its neighbours in the body tree go limp
  (`hitLimp`, falling off with tree distance), and the balance assist drops by `Δv × hitBalanceLoss`.
- Hits are summed over about 0.3 s, because a shove or a boulder is many contact steps. Once the sum exceeds
  `knockdown`, the character falls.
- Sustained contact (leaning on a crate, crowd pressure) only counts when it is fresh or large.
- Balance is lost without a big hit too: the hips are pushed further than `balanceRadius` off the animation, the
  trunk tips past 50°, the legs give way, or there has been no ground under the feet for 0.3 s while the hips sink.
- Stumbling: when the body is displaced but hasn't fallen, the hidden animation follows it at `stepFollow` m/s, so
  the character carries on from where it was pushed instead of rubber-banding back.
- Tripping: a leg caught on an obstacle while walking faster than 0.5 m/s sends the body over it. Characters with
  `knockdown` ≥ 2 catch themselves.
- Falling: the animation freezes, muscle tone drops to `fallTone`, and after `reactionTime` the arms brace toward
  the fall direction (strength `brace`) and the neck stiffens.
- Lying starts once the body has been still for 0.5 s. After `getUpDelay`, the get-up clip is chosen by which way
  the chest faces: `getup_back` ("a person lies on their back on the ground, then gets up and stands") or
  `getup_front` ("a person lies face down on the ground, then pushes up with their arms and stands up"). The clip
  starts 0.6 s before its hips begin to rise. The target is placed so its hips sit on the body's hips, at the same
  heading (hips→head), on the static ground under them. Crates and other dynamic objects are ignored for this.
  Tone ramps back in over 0.5 s and the assist over 1 s. The clip plays at `getUpSpeed`, then crossfades into
  `stand_idle`.
- Anticipation: characters with `anticipation` > 0 tense up (muscles and assist × 1 + anticipation) when a tracked
  projectile will reach them within 0.35 s.

## Personality parameters

| field | meaning | frail elder | fighter | drunk | average |
|---|---|---|---|---|---|
| `strength` (+ `legs/spine/arms/neck`) | muscle gain | 0.55 | 1.35 | 0.7 | 1 |
| `damping` | heavier / slower | 1.3 | 1 | 0.7 | 1 |
| `balance` | balance assist while idle (0 = pure physics) | 0.75 | 1 | 0.55 | 1 |
| `knockdown` | summed Δv (m/s) that floors them | 0.55 | 2.4 | 0.45 | 0.8 |
| `balanceRadius` | metres the hips may be pushed off before falling | 0.2 | 0.55 | 0.3 | 0.35 |
| `hitBalanceLoss` | assist lost per m/s of hit | 1.1 | 0.3 | 1.2 | 0.9 |
| `hitLimp` | how limp the struck region goes | 0.85 | 0.4 | 0.95 | 0.7 |
| `reactionTime` | s before reflexes and recovery | 0.3 | 0.06 | 0.45 | 0.12 |
| `recovery` | muscle and assist recovery per s | 1 | 5 | 0.8 | 2.5 |
| `brace` | arms catch the fall (0 = flops) | 0.35 | 1 | 0.05 | 0.8 |
| `anticipation` | tenses before a visible impact | 0 | 0.6 | 0 | 0 |
| `fallTone` | muscle tone while falling and lying | 0.18 | 0.45 | 0.08 | 0.25 |
| `stepFollow` | m/s the animation follows a displaced body | 0.5 | 2.2 | 0.9 | 1.2 |
| `sway` | random sway force (fraction of weight) | 0 | 0 | 0.05 | 0 |
| `getUpDelay` / `getUpSpeed` | lie this long, then get up at this speed (−1 = stays down) | 2.2 / 0.7 | 0.4 / 1.25 | 2.8 / 0.8 | 1 / 1 |

Text maps to these numbers through [`personality.py`](personality.py). Preset words anchor the extremes (old/frail,
fighter/trained/boxer, drunk/tipsy, unconscious/ragdoll), adjectives nudge single fields ("braces", "flops", "stiff",
"weak", "clumsy", "alert", "very ..."), and everything is clamped to the stable ranges. Claude can also fill the JSON
directly; the C# class `Personality` uses the same schema. The personality shows up twice: in the **clip** the text
asks for (the frail man plays "an old person walks forward slowly, hunched over", the fighter "a person stands in a
boxing stance") and in the **physics**.

```
.venv\Scripts\python demo\ragdoll\personality.py --json build\p.json "a very drunk man who flops" "a stiff, alert bodyguard"
.venv\Scripts\python demo\ragdoll\run_lab.py shots personalities --personalities build\p.json   # overrides presets by name
```

## As an MCP tool

The prototype's runner is the same shape as the tool:

```
simulate_reaction(
  motion: str,                         # a generate_motion result name (or segments to generate first)
  events: [ {t, kind: "throw"|"shove"|"trip"|"drop"|"boulder", body?: "chest"|"head"|"hips"|..., direction?: [x,y,z],
             impulse_ns?: float, object?: {mass, radius, speed}} ],
  personality: str | {strength, balance, knockdown, brace, ...},   # text goes through personality.py; JSON passes through
  stage?: {stairs?: {...}, obstacles?: [...]},                      # static geometry for trips and falls
  get_up: bool = true,                 # chain generate_motion("a person lies on their back ... gets up") clips
  output: "clip" | "video" | "both" = "clip",
) -> { clip: <name>.anim / .kimodo,     # baked physics_pass result: an ordinary clip, no runtime physics needed
       timeline: [{t, state, pin, tone}],  log: ["2.76 knocked down by ball (dv 0.87 >= 0.80)", ...],
       metrics: {track_err_cm, max_ang_vel, nan, replay_err_cm}, preview / video path }
```

Flow inside: resolve the motion's `.kimodo` (and generate the two get-up clips once per project, cached), map the
personality, build a lean scene (floor + stage geometry + one ragdoll), run the fixed-step simulation headless (about
4–10× real time), bake, verify by replaying the baked clip, and return the clip plus the state log. Claude reads the
log ("tripped over an obstacle", "came to rest", "stood up") and the preview, then adjusts events or personality the
way it already regenerates bad takes. `physics_check(motion)` (no events: does the clip stay up when simulated?) falls
out of the same code: run it with no events and report falls or large tracking errors.

## Running it

```
.venv\Scripts\python demo\ragdoll\gen_clips.py                 # 8 clips via motiond -> unity/SystemLab/Assets/Promptimate/Generated
.venv\Scripts\python demo\ragdoll\run_lab.py tests             # joint sign + contact-event self-tests
.venv\Scripts\python demo\ragdoll\run_lab.py shots track,compare,personalities,trip,stairs,crowd,baked
.venv\Scripts\python demo\ragdoll\make_video.py                # -> build/text_to_ragdoll_demo.mp4
```

`run_lab.py` takes the machine-wide heavy lock and closes Unity after each run. `--no-render` runs metrics only;
`--scale 0.5` renders at half resolution for quick looks. Every shot writes `build/frames/<shot>/shot.json` with the
metrics, the state-machine log and a 10 Hz timeline. Characters: local Mixamo models are copied into
`unity/SystemLab/Assets/Characters/` (gitignored, never committed); the Kenney one is CC0.

## Measurements

See the end card of the video and `build/frames/*/shot.json`. These numbers are from the final full-resolution run.

| shot | ragdolls | ms / 240 Hz step | × real time | per character: undisturbed error cm / joint deg · peak ang vel rad/s · lying hip RMS m/s · NaN | bake replay mean / max cm |
|---|---|---|---|---|---|
| track | 4 | 0.85 | 4.9 | walk: 7.1/12.5 · 13 · - · 0<br>walk_old: 4.2/9.3 · 5 · - · 0<br>stance: 4.3/3.8 · 26 · - · 0<br>drunk: 3.9/6.3 · 7 · - · 0 | 0.03/0.3, 0.01/0.1, 0.02/0.1, 0.01/0.2 |
| compare | 1 | 0.56 | 7.5 | kinematic: kinematic<br>physics: 4.2/7.5 · 43 · 0.235 · 0 | 0.02/0.3 |
| personalities | 3 | 0.69 | 6.0 | frail_elder: 2.4/7.9 · 20 · 0.001 · 0<br>trained_fighter: 4.3/3.8 · 26 · - · 0<br>drunk: 4.4/6.9 · 41 · 0.004 · 0 | 0.02/0.7, 0.02/0.1, 0.01/0.5 |
| trip | 1 | 0.44 | 9.5 | walker: 7.0/10.7 · 15 · 0.004 · 0 | 0.03/0.3 |
| stairs | 1 | 0.44 | 9.6 | walker: 7.7/12.4 · 33 · 0.190 · 0 | 0.05/1.2 |
| crowd | 5 | 0.99 | 4.2 | c0_average: 3.8/3.7 · 59 · 0.420 · 0<br>c1_frail_elder: 2.0/4.7 · 86 · 0.130 · 0<br>c2_trained_fighter: 5.0/4.6 · 24 · - · 0<br>c3_drunk: 3.6/4.4 · 51 · 0.178 · 0<br>c4_average: 1.9/3.9 · 37 · - · 0 | 0.02/2.2, 0.06/1.1, 0.06/1.0, 0.02/1.3, 0.03/1.7 |
| baked | 0 | 0.45 | 9.2 | baked0: kinematic<br>baked1: kinematic<br>baked2: kinematic | - |

"× real time" is simulated seconds per CPU second for the controller plus PhysX (rendering excluded). Undisturbed error is sampled only in Puppet state, at least 2 s after any hit and 1.5 s after a state change. "Peak ang vel" above 40 rad/s comes from direct boulder strikes and ball impacts (single-step spikes). Lying hip RMS covers the whole lying span, including bodies still being nudged by a second boulder (crowd c0).

## What works

- Generated clips drive the active ragdoll on five different Humanoid rigs, with no per-rig setup.
- Reactions read clearly and differ by personality. The same 6 kg ball floors the frail man and the drunk, while the
  fighter absorbs it. Two boulders rolling through a crowd knock down the average man, the frail elder and the drunk; the fighter is clipped and stays up.
- Trip, fall down stairs (support loss), brace, rest, then a Promptimate get-up from either side, back into
  tracking. Every scene finishes with each character standing (or mid get-up for the slowest).
- The balance assist turns off once a fall is committed, and recovery comes from the get-up clip (the coordinator's point 1).
- Stable: no NaNs, no explosions. Peak body angular velocity stays within the 40 rad/s cap except under direct
  boulder strikes. Lying bodies have no visible jitter, but they keep settling slowly (hips drift a few cm over a few tenths of a second, RMS 0.001–0.4 m/s), because the weak lying muscle tone still pulls toward the frozen pose. A sleep threshold or a "go fully limp after 1 s" rule would remove it.
- Baking works. The simulated result becomes an ordinary Humanoid `.anim` (muscle curves + root motion) that replays
  with about 0.03 cm mean, < 2 cm max body-part error, and retargets onto other characters (the "baked" shot).
- It's cheap: 0.4–1.0 ms per 240 Hz step for 1–5 ragdolls on the CPU, so 4–10× real time.

## What doesn't (yet)

- **The balance is assisted.** Characters stay up because of pin forces toward the animation, not because a
  controller balances them, and losing balance is decided by rules (radius, tilt, support, summed Δv). It looks
  right for hits and falls. There's no real **stepping response**: a fighter "absorbs" a hit rather than taking a
  recovery step. The `stepFollow` drift is a cheap stand-in. A learned tracker (ProtoMotions' SOMA tracker in
  MuJoCo, see `docs/text-to-system.md`) is the real fix and wasn't tried tonight.
- **Undisturbed tracking is 4–7 cm** mean body-part error (4–13° joint error). Most of it comes from the bones that
  aren't simulated (spine middle, clavicles, neck stay at bind pose) and from pins and muscles sharing the work.
  The visible result is slightly stiffer arms and a less expressive upper body than the pure clip.
- The **get-up starts from the clip's lying pose**, not the body's actual pose. The first ~0.5 s is the muscles
  pulling the limbs into the clip's lying layout, visible as a quick "arrange" before rising. Fix: generate the
  get-up with the fallen pose as a start constraint (`continue_from`-style, from the baked pose).
- Hands are folded into the forearms (no wrist), and fingers, feet and toes are rigid.
- Bracing is a fixed arm-reach heuristic, not a learned or IK reach, so hands don't plant precisely.
- Stairs are only *fallen down*. Walking up or down them still needs foot IK on the target. The target walks on flat
  ground at the platform height.
- Casting comes from the local Mixamo set: the "frail old man" is not an old-looking model.
- Personality mapping is a keyword table; Claude choosing the JSON directly is untested at scale.
- The bake is Unity-only (`.anim`). A `.kimodo`/Roblox export needs the Humanoid → SOMA 30-joint mapping, which the
  repo has in the other direction (the importer), and it's mechanical to invert.

## What it would take to productize

1. **`physics_pass` in the MCP server, headless.** Either keep Unity (lean scene, as here, about 30 s per call
   including editor start; a warm ShotServer-style editor brings that to a few seconds) or port the controller to
   MuJoCo on the CPU (`bench/spikes/ragdoll_track_spike.py` already builds the SOMA body), which removes the Unity
   dependency and works on raw `.kimodo` before retargeting.
2. **Bake to `.kimodo`** (SOMA joints) so the same reaction exports to Unity, Roblox, GLB and BVH through the
   existing pipeline. Validate the bake the way clips are validated now (`unity_validate.py`).
3. **Get-up from the actual pose**: pass the fallen body's pose as a start constraint to `generate_motion`, and pick
   among two or three takes with the existing prompt-aware selection plus "how much did physics have to fight it".
4. **A balance controller worth trusting**: a stepping heuristic (capture point → target-root step) first, then the
   ProtoMotions SOMA tracker as the drop-in for the hand-tuned PD and assist.
5. **Runtime component for games** (optional): `ActiveRagdoll` + `MotionTrack` as a package Runtime component with an
   Animator-driven target instead of a PlayableGraph, for live reactions. Most users will prefer baked clips.
6. **Tests**: the `track` shot as a regression (tracking error, NaN, rest jitter) and the joint-sign and contact
   self-tests, run in CI with `-batchmode`.
