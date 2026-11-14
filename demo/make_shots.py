"""Author the demo shot JSONs (crowd, horde, vignettes, retarget lineup, hero sequence)."""
import json, math, random
from pathlib import Path

OUT = Path(__file__).parent / "shots"
K = "Assets/Characters/Kenney/characterMedium.fbx"
SK = "Assets/Characters/Kenney/Skins/"
HUMAN_SKINS = ["criminalMaleA", "cyborgFemaleA", "skaterFemaleA", "skaterMaleA", "survivorFemaleA", "survivorMaleB", "humanFemaleA", "humanMaleA"]
ZOMBIE_SKINS = ["zombieA", "zombieC", "zombieFemaleA", "zombieMaleA"]
MIX = ["Assets/Characters/Mixamo/Ch24_nonPBR.fbx", "Assets/Characters/Mixamo/Ch34_nonPBR.fbx",
       "Assets/Characters/Mixamo/Ch43_nonPBR.fbx", "Assets/Characters/Mixamo/Erika Archer.fbx"]
C = lambda k: f"Assets/Clips/{k}.kimodo"
BASE = {"supersample": 2, "ground": "#6b6862", "fps": 30}


def kenney(skin, clip, pos, yaw=0, t=0.0, h=1.5):
    return {"model": K, "skin": SK + skin + ".png", "clip": C(clip), "pos": pos, "yaw": yaw, "timeOffset": t, "height": h, "loop": False}


def mix(i, clip, pos, yaw=0, t=0.0, h=1.75, id=None):
    a = {"model": MIX[i % len(MIX)], "clip": C(clip), "pos": pos, "yaw": yaw, "timeOffset": t, "height": h, "loop": False}
    if id: a["id"] = id
    return a


def save(name, shot):
    (OUT / f"{name}.json").write_text(json.dumps({**BASE, **shot}, indent=1))


def crowd():
    rnd = random.Random(3)
    idles = ["idle_talk_1", "idle_talk_2", "idle_phone", "idle_wait", "idle_look", "idle_cross", "idle_stretch", "clap"]
    actors = []
    # Conversation clusters: 2-4 people facing the cluster centre.
    for cx, cz in [(-4, -2), (-1, 1), (2.5, -1.5), (5, 2), (-5, 3), (1, 4.5), (-2.5, -5), (4, -5), (7, -2), (-7, -1)]:
        n = rnd.randint(2, 4)
        for k in range(n):
            ang = 2 * math.pi * k / n + rnd.uniform(-.3, .3)
            r = rnd.uniform(.55, .8)
            x, z = cx + r * math.sin(ang), cz + r * math.cos(ang)
            yaw = math.degrees(math.atan2(cx - x, cz - z)) + rnd.uniform(-15, 15)
            clip, t = rnd.choice(idles), rnd.uniform(0, 3)
            if rnd.random() < 0.3:
                actors.append(mix(rnd.randrange(4), clip, [x, 0, z], yaw, t))
            else:
                actors.append(kenney(rnd.choice(HUMAN_SKINS), clip, [x, 0, z], yaw, t, h=rnd.uniform(1.4, 1.6)))
    # Walkers crossing the plaza.
    for k in range(8):
        z = rnd.uniform(-6, 6); left = rnd.random() < .5
        x0, yaw = (-11, 90) if left else (11, -90)
        clip = rnd.choice(["walk_1", "walk_2", "walk_3", "walk_phone", "jog"])
        actors.append(kenney(rnd.choice(HUMAN_SKINS), clip, [x0 + (k % 3) * (2 if left else -2), 0, z], yaw, rnd.uniform(0, 1.5)))
    cam = {"pos": [8, 3.0, 11], "lookAt": [0, 0.9, 0], "orbitDegPerSec": 3, "fov": 40}
    save("crowd_plaza", {"seconds": 8, "camera": cam, "actors": actors})
    # Same plaza, same camera, everyone frozen in T-pose ("before animation").
    frozen = [{**a, "clip": ""} for a in actors if a["clip"].split("/")[-1].split(".")[0] not in ("walk_1", "walk_2", "walk_3", "walk_phone", "jog")]
    save("crowd_frozen", {"seconds": 4, "camera": cam, "actors": frozen})
    # Wide establishing shot of the alive plaza from the same angle the frozen one starts at.


def horde():
    rnd = random.Random(7)
    actors = []
    for k in range(28):
        x, z = rnd.uniform(-5, 5), rnd.uniform(-10, -1)
        clip = rnd.choice(["zombie_1", "zombie_2", "zombie_3"])
        actors.append(kenney(rnd.choice(ZOMBIE_SKINS), clip, [x, 0, z], rnd.uniform(-12, 12), rnd.uniform(0, 2.5), h=rnd.uniform(1.4, 1.6)))
    save("zombie_horde", {"seconds": 7, "sunPitch": 25, "sunIntensity": 0.9, "skyExposure": 0.7, "atmosphere": 1.6,
                          "camera": {"pos": [1.5, 1.2, 6], "endPos": [0.8, 1.0, 4.5], "lookAt": [0, 1.0, -3], "fov": 40},
                          "actors": actors})


def vignette(name, clip, i, cam_side=1, follow=True, seconds=5, t=0.5):
    cam = {"pos": [1.4 * cam_side, 1.3, 4.0], "lookAt": [0, 0.95, 0], "orbitDegPerSec": -4 * cam_side, "fov": 34}
    if follow: cam["followActor"] = "hero"
    save(f"v_{name}", {"seconds": seconds, "camera": cam, "actors": [mix(i, clip, [0, 0, 0], 0, t, id="hero")]})


def retarget():
    actors = [mix(i, "boxer", [x, 0, 0], 0, 1.0) for i, x in zip(range(4), [-2.25, -0.75, 0.75, 2.25])]
    actors.append(kenney("cyborgFemaleA", "boxer", [3.75, 0, -0.3], -10, 1.0))
    actors.insert(0, kenney("zombieMaleA", "boxer", [-3.75, 0, -0.3], 10, 1.0))
    save("retarget_boxer", {"seconds": 6, "camera": {"pos": [0, 1.5, 8.2], "endPos": [0, 1.4, 7.2], "lookAt": [0, 0.95, 0], "fov": 40}, "actors": actors})


def hero_sequence():
    save("hero_sequence", {"seconds": 10, "camera": {"pos": [3.0, 1.5, 3.0], "lookAt": [0, 1.0, 0], "followActor": "hero", "fov": 36},
                           "actors": [mix(3, "sequence_hero", [0, 0, -2], 0, 0.0, id="hero")]})


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    crowd(); horde(); retarget(); hero_sequence()
    for name, clip, i, side, t in [("boxer", "boxer", 0, 1, 1.0), ("point", "point_shout", 1, -1, 0.8), ("limp", "injured_limp", 2, 1, 1.0),
                                   ("wave", "wave_hello", 3, -1, 4.6), ("moonwalk", "moonwalk", 0, -1, 0.5), ("stretch", "idle_stretch", 2, 1, 1.0),
                                   ("phone", "walk_phone", 3, 1, 1.0), ("zombie", "zombie_1", 1, -1, 1.0), ("clap", "clap", 0, 1, 1.0)]:
        vignette(name, clip, i, side, t=t)
    print(sorted(p.name for p in OUT.glob("*.json")))
