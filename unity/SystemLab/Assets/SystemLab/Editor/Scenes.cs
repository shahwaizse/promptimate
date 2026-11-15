// Scripted demo scenes for text-to-ragdoll. Each builds a stage, spawns active ragdolls (a visible simulated character
// plus an invisible target playing a Promptimate clip), schedules events (thrown balls, a rolling boulder) and a camera.
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace SystemLab
{
    public static class Scenes
    {
        // Local Mixamo characters (never committed). Kenney characterMedium + skins are CC0.
        const string Mix = "Assets/Characters/Mixamo/";
        public static readonly string[] Models = { Mix + "Ch24_nonPBR.fbx", Mix + "Ch34_nonPBR.fbx", Mix + "Ch43_nonPBR.fbx", Mix + "Erika Archer.fbx" };
        const string Kenney = "Assets/Characters/Kenney/characterMedium.fbx";

        static readonly Dictionary<string, Personality> Custom = new Dictionary<string, Personality>();

        /// Optional overrides from text (demo/ragdoll/personality.py output): {"items":[{...Personality...}]}
        public static void LoadPersonalities(string json)
        {
            var w = JsonUtility.FromJson<PList>(json);
            foreach (var p in w.items ?? new Personality[0]) Custom[p.name] = p;
        }
        [System.Serializable] class PList { public Personality[] items; }

        static Personality P(string key) => Custom.TryGetValue(key, out var p) ? p.Clone() : Personality.Preset(key);

        public static Shot Build(string id)
        {
            LabSetup.Look();
            switch (id)
            {
                case "lineup": return Lineup();
                case "compare": return Compare();
                case "personalities": return Personalities();
                case "stairs": return Stairs();
                case "trip": return Trip();
                case "crowd": return Crowd();
                case "track": return TrackTest();
                case "baked": return Baked();
                default: throw new System.Exception("unknown shot " + id);
            }
        }

        // ------------------------------------------------------------------ helpers
        static AnimationClip Clip(string key)
        {
            if (key.EndsWith(".anim"))
            {
                var a = AssetDatabase.LoadAssetAtPath<AnimationClip>(key);
                if (!a) throw new System.Exception("missing baked clip " + key + " (render the source shot first)");
                return a;
            }
            var path = $"Assets/Promptimate/Generated/{key}.kimodo";
            var c = AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().FirstOrDefault(x => !x.name.StartsWith("__preview"));
            if (!c) throw new System.Exception("missing clip " + path + " (run demo/ragdoll/gen_clips.py)");
            return c;
        }

        static readonly Dictionary<string, float> LyingStart = new Dictionary<string, float>();

        /// Time in a get-up clip where the character lies lowest (the clips start lying or lie down first).
        static float GetUpStart(string key, string model)
        {
            if (LyingStart.TryGetValue(key, out var s)) return s;
            var go = (GameObject)Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(model));
            var mt = new MotionTrack(go);
            var clip = Clip(key);
            var hips = mt.anim.GetBoneTransform(HumanBodyBones.Hips);
            // start shortly before the hips begin to rise (the clips lie still for a while first)
            var ys = new List<float>();
            for (float t = 0; t < clip.length; t += 1f / 30) { mt.Play(clip, t); ys.Add(hips.position.y - go.transform.position.y); }
            float bestY = ys.Take(Mathf.Max(1, ys.Count * 6 / 10)).Min();
            int rise = ys.FindIndex(y => y > bestY + 0.08f);
            float best = Mathf.Max(0f, (rise < 0 ? 0 : rise) / 30f - 0.6f);
            mt.Destroy(); Object.DestroyImmediate(go);
            Debug.Log($"LAB_GETUP {key}: lying at {best:F2}s (hips {bestY:F2} m)");
            return LyingStart[key] = best;
        }

        static GameObject Instance(string model, Vector3 pos, float yaw, float height, Texture skin)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(model);
            if (!prefab) throw new System.Exception("missing character " + model);
            var go = (GameObject)Object.Instantiate(prefab);
            go.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            var anim = go.GetComponent<Animator>();
            anim.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            var head = anim.GetBoneTransform(HumanBodyBones.Head);
            if (height > 0 && head) go.transform.localScale *= height * 0.88f / Mathf.Max(0.1f, head.position.y);
            go.transform.SetPositionAndRotation(pos, Quaternion.Euler(0, yaw, 0));
            LabSetup.ConvertMaterials(go, skin);
            return go;
        }

        static ActiveRagdoll Spawn(Shot shot, string id, string model, Vector3 pos, float yaw, Personality p, string clip,
                                   bool loop = true, bool kinematic = false, float height = 1.75f, Texture skin = null,
                                   float clipStart = 0f)
        {
            var vis = Instance(model, pos, yaw, height, skin); vis.name = id;
            var tgt = Instance(model, pos, yaw, height, skin); tgt.name = id + "_target";
            var r = new ActiveRagdoll(id, vis, tgt, p, kinematic, shot.obstacles);
            r.track.footIK = !clip.EndsWith(".anim");
            r.track.Play(Clip(clip), clipStart, 1f, 0f, loop);
            // first target pose is the ragdoll's start pose: snap the bodies there before the first step
            foreach (var part in r.parts)
            {
                part.rb.position = part.target.position; part.rb.rotation = part.target.rotation;
                part.t.SetPositionAndRotation(part.target.position, part.target.rotation);
                part.prevTargetPos = part.target.position;
            }
            float bs = GetUpStart("getup_back", model), fs = GetUpStart("getup_front", model);
            var back = Clip("getup_back"); var front = Clip("getup_front");
            r.chooseGetUp = rd => rd.ChestForward().y > 0 ? (back, bs) : (front, fs);
            r.afterGetUp = Clip("stand_idle"); r.afterGetUpLoop = true;
            r.groundAt = GroundAt;
            shot.ragdolls.Add(r);
            return r;
        }

        public static float GroundAt(Vector3 p)
        {
            int mask = ~((1 << ActiveRagdoll.Layer) | (1 << (ActiveRagdoll.Layer + 1)));
            // static ground only: a crate or ball the body lies on is not the floor to stand up on
            float best = float.NegativeInfinity;
            foreach (var hit in Physics.RaycastAll(p + Vector3.up * 0.6f, Vector3.down, 5f, mask, QueryTriggerInteraction.Ignore))
                if (hit.rigidbody == null && hit.point.y > best) best = hit.point.y;
            return float.IsNegativeInfinity(best) ? 0f : best;
        }

        static PhysicsMaterial floorMat;
        static GameObject Block(string name, Vector3 center, Vector3 size, Material m)
        {
            var g = GameObject.CreatePrimitive(PrimitiveType.Cube);
            g.name = name; g.transform.position = center; g.transform.localScale = size;
            g.GetComponent<Renderer>().sharedMaterial = m;
            if (!floorMat) floorMat = new PhysicsMaterial("floor") { dynamicFriction = 0.8f, staticFriction = 0.9f };
            g.GetComponent<Collider>().sharedMaterial = floorMat;
            return g;
        }

        static Material floorM;
        static void Floor(float size = 240f)
        {
            if (!floorM)
            {
                floorM = LabSetup.Mat(Color.white, LabSetup.Grid(new Color(0.36f, 0.355f, 0.34f), new Color(0.27f, 0.265f, 0.26f)), 0.15f);
                floorM.SetTextureScale("_BaseMap", new Vector2(size / 4f, size / 4f));
            }
            Block("Floor", new Vector3(0, -0.25f, 0), new Vector3(size, 0.5f, size), floorM);
        }

        static Rigidbody Ball(string name, float radius, float mass, Color c)
        {
            var g = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            g.name = name; g.transform.localScale = Vector3.one * radius * 2;
            g.transform.position = new Vector3(0, -50, 0);
            g.GetComponent<Renderer>().sharedMaterial = LabSetup.Mat(c, null, 0.45f);
            g.GetComponent<Collider>().sharedMaterial = new PhysicsMaterial("ball") { bounciness = 0.3f, dynamicFriction = 0.5f, staticFriction = 0.6f };
            var rb = g.AddComponent<Rigidbody>();
            rb.mass = mass; rb.collisionDetectionMode = CollisionDetectionMode.ContinuousDynamic;
            rb.isKinematic = true; // parked until thrown
            g.SetActive(false);
            return rb;
        }

        /// Throws `ball` from `from` so it reaches ragdoll r's chest (predicted from the animation) after `flight` s.
        static void Throw(Rigidbody ball, Vector3 from, ActiveRagdoll r, float flight, float heightOffset = 0f)
        {
            ball.gameObject.SetActive(true);
            ball.isKinematic = false;
            var chest = r.Get(HumanBodyBones.UpperChest);
            var aim = chest.target.position + chest.targetVel * flight + Vector3.up * heightOffset;
            ball.position = from; ball.transform.position = from;
            ball.linearVelocity = (aim - from) / flight - 0.5f * Physics.gravity * flight;
            ball.angularVelocity = Random.insideUnitSphere * 5f;
        }

        static (Vector3, Vector3, float) Follow(ref Vector3 state, Vector3 focus, Vector3 offset, float fov, float smooth = 0.06f)
        {
            state = state == Vector3.zero ? focus : Vector3.Lerp(state, focus, smooth);
            return (state + offset, state, fov);
        }

        static Vector3 Mid(Shot s) { var v = Vector3.zero; int n = 0; foreach (var r in s.ragdolls) { v += r.hips.rb.position; n++; } return v / Mathf.Max(1, n); }

        // ------------------------------------------------------------------ shots
        static Shot Lineup()
        {
            Floor();
            var shot = new Shot { id = "lineup", title = "Cast", seconds = 3f };
            var skins = new[] { "humanMaleA", "criminalMaleA" };
            for (int i = 0; i < Models.Length; i++)
                Spawn(shot, "m" + i, Models[i], new Vector3((i - 2.5f) * 1.2f, 0, 0), 180, P("average"), "idle");
            Spawn(shot, "kenney", Kenney, new Vector3(2.4f, 0, 0), 180, P("average"), "idle", skin: AssetDatabase.LoadAssetAtPath<Texture>("Assets/Characters/Kenney/Skins/humanMaleA.png"));
            shot.cam = (t, s) => (new Vector3(0, 1.4f, -7.5f), new Vector3(0, 0.95f, 0), 40f);
            return shot;
        }

        static Shot TrackTest()
        {
            // undisturbed tracking: walking, idling and a fighter stance, no events (metrics only)
            Floor();
            var shot = new Shot { id = "track", title = "Undisturbed tracking", seconds = 9f };
            Spawn(shot, "walk", Models[0], new Vector3(-2, 0, -4), 0, P("average"), "walk", loop: false);
            Spawn(shot, "walk_old", Models[1], new Vector3(0, 0, -4), 0, P("frail_elder"), "walk_old", loop: false);
            Spawn(shot, "stance", Models[2], new Vector3(2, 0, 0), 180, P("trained_fighter"), "stance_fighter");
            Spawn(shot, "drunk", Models[3], new Vector3(4, 0, -4), 0, P("drunk"), "walk_drunk", loop: false);
            shot.cam = (t, s) => (new Vector3(1, 2.2f, -9f), new Vector3(1, 0.9f, 0), 50f);
            return shot;
        }

        static Shot Baked()
        {
            // physics_pass output: the compare shot's simulated reaction, baked to an ordinary Humanoid clip, played
            // with no physics at all on three different characters (retargeted by Mecanim)
            Floor();
            var shot = new Shot { id = "baked", title = "Baked: the reaction as an ordinary clip", seconds = 10f };
            const string clip = "Assets/SystemLab/Generated/Baked/compare_physics.anim";
            var cast = new[] { (Models[3], 0f, (Texture)null), (Models[1], 0f, (Texture)null),
                (Kenney, 0f, AssetDatabase.LoadAssetAtPath<Texture>("Assets/Characters/Kenney/Skins/skaterFemaleA.png")) };
            for (int i = 0; i < cast.Length; i++)
            {
                var r = Spawn(shot, "baked" + i, cast[i].Item1, new Vector3((i - 1) * 2.4f, 0, -3.5f), 0, P("average"), clip,
                    loop: false, kinematic: true, skin: cast[i].Item3);
                shot.labels.Add((r, "baked clip, no physics", new Color(0.75f, 0.9f, 1f)));
            }
            var st = Vector3.zero;
            shot.cam = (t, s) => Follow(ref st, new Vector3(0, 0.8f, Mid(s).z), new Vector3(1.5f, 1.1f, 6.2f), 46f, 0.05f);
            return shot;
        }

        static Shot Compare()
        {
            Floor();
            var shot = new Shot { id = "compare", title = "Same clip: kinematic vs physics-reactive", seconds = 12f };
            var a = Spawn(shot, "kinematic", Models[0], new Vector3(-1.4f, 0, -3.5f), 0, P("average"), "walk", loop: false, kinematic: true);
            var b = Spawn(shot, "physics", Models[0], new Vector3(1.4f, 0, -3.5f), 0, P("average"), "walk", loop: false);
            shot.labels.Add((a, "kinematic clip", new Color(1f, 1f, 1f)));
            shot.labels.Add((b, "physics-reactive", new Color(1f, 0.85f, 0.4f)));
            var ballA = Ball("ballA", 0.13f, 7f, new Color(0.9f, 0.35f, 0.15f));
            var ballB = Ball("ballB", 0.13f, 7f, new Color(0.9f, 0.35f, 0.15f));
            shot.threats.Add(ballB);
            shot.events.Add((2.4f, () => Throw(ballA, a.hips.target.position + new Vector3(-5.5f, 0.6f, 1.5f), a, 0.38f)));
            shot.events.Add((2.4f, () => Throw(ballB, b.hips.target.position + new Vector3(5.5f, 0.6f, 1.5f), b, 0.38f)));
            var st = Vector3.zero;
            shot.cam = (t, s) =>
            {
                float w = Mathf.SmoothStep(0, 1, (t - 3.2f) / 1.5f);
                var m = Vector3.Lerp((a.hips.target.position + b.hips.rb.position) * 0.5f, b.hips.rb.position, w);
                return Follow(ref st, new Vector3(m.x * w, 0.9f, m.z), new Vector3(2.6f, 0.7f, 5.4f), 42f, 0.04f);
            };
            return shot;
        }

        static Shot Personalities()
        {
            Floor();
            var shot = new Shot { id = "personalities", title = "One hit, three personalities", seconds = 13f };
            var specs = new (string key, string label, string clip, int model)[]
            {
                ("frail_elder", "\"a frail old man\"", "walk_old", 1),
                ("trained_fighter", "\"a trained fighter who braces\"", "stance_fighter", 2),
                ("drunk", "\"a drunk who flops\"", "walk_drunk", 3),
            };
            for (int i = 0; i < specs.Length; i++)
            {
                var sp = specs[i];
                var r = Spawn(shot, sp.key, Models[sp.model], new Vector3((i - 1) * 2.6f, 0, sp.clip == "walk_drunk" ? 1.4f : 0f), 180, P(sp.key), sp.clip, loop: false);
                shot.labels.Add((r, sp.label, new Color(1f, 0.92f, 0.7f)));
                var ball = Ball("ball" + i, 0.13f, 6f, new Color(0.9f, 0.35f, 0.15f));
                shot.threats.Add(ball);
                var rr = r;
                shot.events.Add((2.2f, () => Throw(ball, rr.hips.target.position + new Vector3(1.2f, 0.7f, -6f), rr, 0.42f)));
            }
            shot.cam = (t, s) => (new Vector3(0, 1.45f, -6.4f), new Vector3(0, 0.85f, 0.5f), 44f);
            return shot;
        }

        static Shot Stairs()
        {
            var shot = new Shot { id = "stairs", title = "Missing the top step", seconds = 13f };
            Floor();
            var stone = LabSetup.Mat(new Color(0.62f, 0.6f, 0.57f), null, 0.1f);
            float top = 1.6f; int n = 8; float rise = top / n, run = 0.34f;
            Block("Platform", new Vector3(0, top / 2, -4f), new Vector3(3f, top, 8f), stone);
            for (int i = 0; i < n; i++)
            {
                float h = top - (i + 1) * rise;
                if (h <= 0.001f) break;
                Block("Step" + i, new Vector3(0, h / 2, i * run + run / 2), new Vector3(3f, h, run), stone);
            }
            var r = Spawn(shot, "walker", Models[0], new Vector3(0, top, -3.6f), 0, P("average"), "walk", loop: false);
            shot.labels.Add((r, "\"a person walks forward\"", new Color(1f, 0.92f, 0.7f)));
            var st = Vector3.zero;
            shot.cam = (t, s) => Follow(ref st, r.hips.rb.position * 0.6f + new Vector3(0, 0.5f, 1.2f), new Vector3(7.5f, 0.4f, -2.5f), 42f, 0.05f);
            return shot;
        }

        static Shot Trip()
        {
            var shot = new Shot { id = "trip", title = "Tripping over a crate", seconds = 12f };
            Floor();
            var wood = LabSetup.Mat(new Color(0.55f, 0.38f, 0.22f), null, 0.2f);
            var crate = Block("Crate", new Vector3(0.05f, 0.14f, 0.2f), new Vector3(0.9f, 0.28f, 0.35f), wood);
            shot.obstacles.Add(crate.GetComponent<Collider>().GetInstanceID());
            var crb = crate.AddComponent<Rigidbody>(); crb.mass = 20f; // light enough to be kicked aside
            var r = Spawn(shot, "walker", Models[2], new Vector3(0, 0, -3.2f), 0, P("average"), "walk", loop: false);
            shot.labels.Add((r, "\"a person walks forward\"", new Color(1f, 0.92f, 0.7f)));
            var st = Vector3.zero;
            shot.cam = (t, s) => Follow(ref st, r.hips.rb.position, new Vector3(4.8f, 0.6f, 2.6f), 45f, 0.05f);
            return shot;
        }

        static Shot Crowd()
        {
            var shot = new Shot { id = "crowd", title = "A crowd, five personalities", seconds = 14f };
            Floor();
            var cast = new (string p, string label, string clip, int model, Vector3 pos, float yaw)[]
            {
                ("average", "average", "idle", 0, new Vector3(-1.6f, 0, 0.3f), 160),
                ("frail_elder", "frail elder", "idle", 1, new Vector3(-0.3f, 0, -0.5f), 200),
                ("trained_fighter", "fighter", "stance_fighter", 2, new Vector3(0.9f, 0, 0.6f), 150),
                ("drunk", "drunk", "idle", 3, new Vector3(2.0f, 0, -0.4f), 210),
                ("average", "average", "idle", 0, new Vector3(3.1f, 0, 0.5f), 180),
            };
            var skins = new[] { "humanMaleA", "criminalMaleA", "humanFemaleA", "skaterFemaleA", "cyborgFemaleA" };
            for (int i = 0; i < cast.Length; i++)
            {
                var c = cast[i];
                bool ken = i == 4;
                var r = Spawn(shot, $"c{i}_{c.p}", ken ? Kenney : Models[c.model], c.pos, c.yaw, P(c.p), c.clip,
                    skin: ken ? AssetDatabase.LoadAssetAtPath<Texture>($"Assets/Characters/Kenney/Skins/{skins[i]}.png") : null,
                    clipStart: i * 0.7f);
                shot.labels.Add((r, c.label, new Color(1f, 0.92f, 0.7f)));
            }
            var boulder = Ball("boulder", 0.55f, 320f, new Color(0.45f, 0.43f, 0.4f));
            shot.threats.Add(boulder);
            shot.events.Add((2.0f, () =>
            {
                boulder.gameObject.SetActive(true); boulder.isKinematic = false;
                boulder.position = new Vector3(-7f, 0.56f, 0.1f); boulder.transform.position = boulder.position;
                boulder.linearVelocity = new Vector3(6.5f, 0, 0.05f); boulder.angularVelocity = new Vector3(0, 0, -6.5f / 0.55f);
            }));
            var boulder2 = Ball("boulder2", 0.5f, 260f, new Color(0.5f, 0.47f, 0.43f));
            shot.threats.Add(boulder2);
            shot.events.Add((3.6f, () =>
            {
                boulder2.gameObject.SetActive(true); boulder2.isKinematic = false;
                boulder2.position = new Vector3(8.5f, 0.51f, 0.0f); boulder2.transform.position = boulder2.position;
                boulder2.linearVelocity = new Vector3(-6.5f, 0, 0.05f); boulder2.angularVelocity = new Vector3(0, 0, 6.5f / 0.5f);
            }));
            shot.cam = (t, s) => (new Vector3(1.0f, 2.4f, -6.2f), new Vector3(0.7f, 0.7f, 0.2f), 48f);
            return shot;
        }
    }
}
