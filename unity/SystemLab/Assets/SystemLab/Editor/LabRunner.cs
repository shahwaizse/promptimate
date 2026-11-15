// Offline, frame-by-frame runner for the text-to-ragdoll demo scenes: steps the animation targets and the physics at a
// fixed sub-step, renders each frame (URP) to JPG, and writes metrics.json (tracking error, stability, sim speed).
//   Unity.exe -batchmode -projectPath unity/SystemLab -executeMethod SystemLab.LabRunner.Run
//             -shots compare,personalities -out <dir> [-render 0|1] [-scale 0.5] [-personalities <json file>]
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Unity.Collections;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace SystemLab
{
    public class Shot
    {
        public string id, title;
        public float seconds = 10f;
        public int fps = 30, substeps = 8;
        public List<ActiveRagdoll> ragdolls = new List<ActiveRagdoll>();
        public List<(float t, System.Action act)> events = new List<(float, System.Action)>();
        public List<Rigidbody> threats = new List<Rigidbody>();
        public List<(ActiveRagdoll r, string text, Color color)> labels = new List<(ActiveRagdoll, string, Color)>();
        public System.Func<float, Shot, (Vector3 pos, Vector3 look, float fov)> cam;
        public HashSet<int> obstacles = new HashSet<int>();
    }

    public static class LabRunner
    {
        static readonly CultureInfo Inv = CultureInfo.InvariantCulture;
        static string F(float v) => v.ToString("0.###", Inv);

        public static void Run()
        {
            var args = System.Environment.GetCommandLineArgs();
            string Arg(string k, string d) { int i = System.Array.IndexOf(args, k); return i >= 0 && i + 1 < args.Length ? args[i + 1] : d; }
            int code = 0;
            try
            {
                LabSetup.Ensure();
                string outDir = Arg("-out", Path.GetFullPath("../../demo/ragdoll/build/frames"));
                bool render = Arg("-render", "1") != "0";
                float scale = float.Parse(Arg("-scale", "1"), Inv);
                string pfile = Arg("-personalities", "");
                if (!string.IsNullOrEmpty(pfile)) Scenes.LoadPersonalities(File.ReadAllText(pfile));
                var all = new StringBuilder("{");
                bool first = true;
                foreach (var id in Arg("-shots", "compare").Split(','))
                {
                    var json = RunShot(id.Trim(), Path.Combine(outDir, id.Trim()), render, scale);
                    all.Append(first ? "" : ",").Append($"\"{id.Trim()}\":{json}");
                    first = false;
                }
                all.Append("}");
                File.WriteAllText(Path.Combine(outDir, "metrics_" + Arg("-shots", "compare").Replace(',', '_') + ".json"), all.ToString());
            }
            catch (System.Exception e) { Debug.LogError("LAB_ERROR " + e); code = 1; }
            EditorApplication.Exit(code);
        }

        static readonly List<(int body, int other, int otherCol, Vector3 impulse, Vector3 point)> Contacts = new List<(int, int, int, Vector3, Vector3)>();

        static void OnContacts(PhysicsScene scene, NativeArray<ContactPairHeader>.ReadOnly headers)
        {
            for (int h = 0; h < headers.Length; h++)
            {
                var hd = headers[h];
                for (int k = 0; k < hd.pairCount; k++)
                {
                    ref readonly var pair = ref hd.GetContactPair(k);
                    if (pair.isCollisionExit) continue;
                    var imp = pair.impulseSum;
                    if (imp.sqrMagnitude < 1e-4f) continue;
                    Vector3 pt = pair.contactCount > 0 ? pair.GetContactPoint(0).position : Vector3.zero;
                    Contacts.Add((hd.bodyInstanceID, hd.otherBodyInstanceID, pair.otherColliderInstanceID, imp, pt));
                    Contacts.Add((hd.otherBodyInstanceID, hd.bodyInstanceID, pair.colliderInstanceID, imp, pt));
                }
            }
        }

        public static string RunShot(string id, string outDir, bool render, float scale)
        {
            var sw = System.Diagnostics.Stopwatch.StartNew();
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            ShaderUtil.allowAsyncCompilation = false;
            var shot = Scenes.Build(id);
            Debug.Log($"LAB_SHOT {id} built in {sw.Elapsed.TotalSeconds:F1}s, {shot.ragdolls.Count} ragdolls");

            int W = Mathf.RoundToInt(1280 * scale), H = Mathf.RoundToInt(720 * scale);
            var camGo = new GameObject("Cam");
            var cam = camGo.AddComponent<Camera>();
            cam.nearClipPlane = 0.05f; cam.farClipPlane = 300; cam.allowHDR = true; cam.allowMSAA = true;
            cam.clearFlags = CameraClearFlags.SolidColor; cam.backgroundColor = RenderSettings.fogColor;
            var data = camGo.AddComponent<UniversalAdditionalCameraData>();
            data.renderPostProcessing = true; data.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            data.renderShadows = true; data.requiresDepthTexture = true;
            var rt = new RenderTexture(W, H, 24, RenderTextureFormat.ARGB32) { antiAliasing = 4 };
            rt.Create();
            var outRt = new RenderTexture(W, H, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            cam.targetTexture = rt;
            var tex = new Texture2D(W, H, TextureFormat.RGB24, false);
            // floating name labels (TextMesh, built-in font, faces the camera)
            var font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            var labelObjs = new List<(TextMesh tm, ActiveRagdoll r)>();
            foreach (var (r, text, color) in shot.labels)
            {
                var lg = new GameObject("label_" + r.id);
                var tm = lg.AddComponent<TextMesh>();
                tm.font = font; tm.text = text; tm.fontSize = 96; tm.characterSize = 0.016f; tm.anchor = TextAnchor.LowerCenter;
                tm.alignment = TextAlignment.Center; tm.color = color;
                lg.GetComponent<MeshRenderer>().sharedMaterial = font.material;
                labelObjs.Add((tm, r));
            }

            if (render)
            {
                Directory.CreateDirectory(outDir);
                foreach (var f in Directory.GetFiles(outDir, "f*.jpg")) File.Delete(f);
            }
            Physics.ContactEvent += OnContacts;
            int frames = Mathf.RoundToInt(shot.seconds * shot.fps);
            float dt = 1f / (shot.fps * shot.substeps);
            float t = 0;
            int ev = 0;
            shot.events.Sort((a, b) => a.t.CompareTo(b.t));
            var pending = new List<System.Threading.Tasks.Task>();
            double simMs = 0; long steps = 0;
            var stateLog = new StringBuilder();
            var timeline = new StringBuilder();
            var baker = new Baker(shot);
            for (int f = 0; f < frames; f++)
            {
                for (int s = 0; s < shot.substeps; s++)
                {
                    var t0 = System.Diagnostics.Stopwatch.GetTimestamp();
                    while (ev < shot.events.Count && shot.events[ev].t <= t) { shot.events[ev].act(); ev++; }
                    foreach (var r in shot.ragdolls) Anticipate(r, shot.threats);
                    foreach (var r in shot.ragdolls) r.PreStep(dt, t);
                    Contacts.Clear();
                    Physics.Simulate(dt);
                    DispatchContacts(shot);
                    foreach (var r in shot.ragdolls) r.PostStep(dt);
                    simMs += (System.Diagnostics.Stopwatch.GetTimestamp() - t0) * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
                    steps++;
                    t += dt;
                }
                baker.Capture();
                if (f % 3 == 0)
                {
                    timeline.Append(timeline.Length > 0 ? "," : "").Append($"{{\"t\":{F(t)},\"r\":[");
                    timeline.Append(string.Join(",", shot.ragdolls.Select(r =>
                        $"{{\"id\":\"{r.id}\",\"s\":\"{r.state}\",\"pin\":{F(r.pin)},\"tone\":{F(r.tone)},\"hips\":[{F(r.hips.rb.position.x)},{F(r.hips.rb.position.y)},{F(r.hips.rb.position.z)}],\"err\":{F(Vector3.Distance(r.hips.rb.position, r.hips.target.position))}}}")));
                    timeline.Append("]}");
                }
                if (!render) continue;
                var (cp, look, fov) = shot.cam(t, shot);
                cam.transform.position = cp;
                cam.transform.rotation = Quaternion.LookRotation(look - cp);
                cam.fieldOfView = fov;
                foreach (var (tm, r) in labelObjs)
                {
                    var head = r.Get(HumanBodyBones.Head).rb.position;
                    tm.transform.position = head + Vector3.up * 0.32f * r.scale;
                    tm.transform.rotation = Quaternion.LookRotation(tm.transform.position - cp);
                }
                if (f == 0) for (int w = 0; w < 3; w++) cam.Render();
                cam.Render();
                Graphics.Blit(rt, outRt);
                RenderTexture.active = outRt;
                tex.ReadPixels(new Rect(0, 0, W, H), 0, 0);
                RenderTexture.active = null;
                var raw = tex.GetRawTextureData<byte>().ToArray();
                string file = Path.Combine(outDir, $"f{f:D5}.jpg");
                while (pending.Count(x => !x.IsCompleted) > 6) pending.First(x => !x.IsCompleted).Wait();
                pending.Add(System.Threading.Tasks.Task.Run(() =>
                    File.WriteAllBytes(file, ImageConversion.EncodeArrayToJPG(raw, UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8B8_SRGB, (uint)W, (uint)H, 0, 93))));
            }
            System.Threading.Tasks.Task.WaitAll(pending.ToArray());
            Physics.ContactEvent -= OnContacts;
            cam.targetTexture = null; rt.Release(); outRt.Release();
            foreach (var r in shot.ragdolls) r.track.Destroy();

            string bakeJson = baker.Save(id);
            var json = new StringBuilder("{");
            json.Append($"\"baked\":{bakeJson},");
            json.Append($"\"title\":\"{shot.title}\",\"seconds\":{F(shot.seconds)},\"fps\":{shot.fps},\"substep_hz\":{shot.fps * shot.substeps},");
            json.Append($"\"ragdolls\":{shot.ragdolls.Count(r => !r.kinematic)},\"bodies\":{shot.ragdolls.Sum(r => r.parts.Count)},");
            json.Append($"\"sim_ms_per_step\":{F((float)(simMs / steps))},\"sim_steps_per_s\":{F((float)(steps / (simMs / 1000.0)))},");
            json.Append($"\"realtime_factor\":{F((float)(shot.seconds / (simMs / 1000.0)))},\"wall_s\":{F((float)sw.Elapsed.TotalSeconds)},");
            json.Append("\"actors\":[" + string.Join(",", shot.ragdolls.Select(r => r.MetricsJson())) + "],");
            json.Append("\"log\":[" + string.Join(",", shot.ragdolls.SelectMany(r => r.log).Select(l => "\"" + l.Replace("\"", "'") + "\"")) + "],");
            json.Append("\"timeline\":[" + timeline + "]}");
            if (render) File.WriteAllText(Path.Combine(outDir, "shot.json"), json.ToString());
            Debug.Log($"LAB_DONE {id} frames={frames} wall={sw.Elapsed.TotalSeconds:F1}s sim={simMs / steps:F3}ms/step");
            foreach (var r in shot.ragdolls) foreach (var l in r.log) Debug.Log("LAB_LOG " + l);
            return json.ToString();
        }

        /// Trained characters tense up just before something visibly hits them.
        static void Anticipate(ActiveRagdoll r, List<Rigidbody> threats)
        {
            if (r.kinematic || r.p.anticipation <= 0) { r.anticipationBoost = 1f; return; }
            float want = 1f;
            var chest = r.Get(HumanBodyBones.UpperChest).rb.position;
            foreach (var b in threats)
            {
                if (!b) continue;
                var d = chest - b.position; var v = b.linearVelocity - r.hips.rb.linearVelocity;
                float closing = Vector3.Dot(v, d.normalized);
                if (closing > 2f && d.magnitude / closing < 0.35f) want = 1f + r.p.anticipation;
            }
            r.anticipationBoost = Mathf.MoveTowards(r.anticipationBoost, want, want > r.anticipationBoost ? 0.2f : 0.01f);
        }

        static void DispatchContacts(Shot shot)
        {
            if (Contacts.Count == 0) return;
            // sum impulses per (ragdoll part, other body/collider) this step
            var agg = new Dictionary<(ActiveRagdoll, ActiveRagdoll.Part, int), (Vector3 imp, Vector3 pt, string what)>();
            foreach (var c in Contacts)
            {
                foreach (var r in shot.ragdolls)
                {
                    if (r.kinematic || !r.TryPart(c.body, out var part)) continue;
                    if (r.TryPart(c.other, out _)) continue; // self
                    string what;
                    if (shot.obstacles.Contains(c.otherCol)) what = "obstacle";  // crates etc. (may be rigidbodies)
                    else if (c.other != 0) what = "body";                    // any rigidbody: ball, boulder, another ragdoll
                    else continue;                                           // floors, stairs: not a hit
                    var key = (r, part, c.other != 0 ? c.other : c.otherCol);
                    agg.TryGetValue(key, out var a);
                    // direction: into the struck part (from the contact point toward its centre of mass)
                    agg[key] = (a.imp + c.impulse.magnitude * (part.rb.worldCenterOfMass - c.point).normalized, c.point, what);
                }
            }
            foreach (var kv in agg)
            {
                var (r, part, _) = kv.Key;
                r.Hit(part, kv.Value.imp, kv.Value.pt, false, kv.Value.what);
            }
        }
    }

    /// physics_pass output: records each simulated ragdoll as an ordinary Humanoid AnimationClip (muscle curves +
    /// root motion), so the reaction plays anywhere with no runtime physics. Verified by replaying the saved clip on a
    /// fresh copy of the character and comparing body-part positions with the simulation.
    public class Baker
    {
        class Rec { public ActiveRagdoll r; public HumanPoseHandler h; public List<HumanPose> poses = new List<HumanPose>();
                    public List<Vector3[]> pos = new List<Vector3[]>(); }
        readonly List<Rec> recs = new List<Rec>();
        readonly Shot shot;
        static readonly HumanBodyBones[] Check = { HumanBodyBones.Hips, HumanBodyBones.Head, HumanBodyBones.LeftHand,
            HumanBodyBones.RightHand, HumanBodyBones.LeftFoot, HumanBodyBones.RightFoot };

        public Baker(Shot s)
        {
            shot = s;
            foreach (var r in s.ragdolls)
            {
                if (r.kinematic) continue;
                var a = r.go.GetComponent<Animator>();
                recs.Add(new Rec { r = r, h = new HumanPoseHandler(a.avatar, r.go.transform) });
            }
        }

        public void Capture()
        {
            foreach (var x in recs)
            {
                var hp = new HumanPose();
                // HumanPoseHandler measures in world space (scaled by the avatar): read the pose with the character
                // root at the origin so the clip's root motion is relative to where the character was placed
                var rt = x.r.go.transform;
                var (rp, rr) = (rt.position, rt.rotation);
                rt.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
                x.h.GetHumanPose(ref hp);
                if (x.poses.Count == 0)
                {
                    var an = x.r.go.GetComponent<Animator>();
                    Debug.Log($"LAB_BAKE {x.r.id}: humanScale={an.humanScale:F3} lossy={rt.lossyScale.x:F3} bodyY={hp.bodyPosition.y:F3} hipsY={an.GetBoneTransform(HumanBodyBones.Hips).position.y:F3}");
                }
                rt.SetPositionAndRotation(rp, rr);
                hp.muscles = (float[])hp.muscles.Clone();
                x.poses.Add(hp);
                var a = x.r.go.GetComponent<Animator>();
                var root = x.r.go.transform;
                x.pos.Add(Check.Select(b => root.InverseTransformPoint(a.GetBoneTransform(b).position)).ToArray());
            }
        }

        public string Save(string shotId)
        {
            const string dir = "Assets/SystemLab/Generated/Baked";
            if (!AssetDatabase.IsValidFolder(dir)) AssetDatabase.CreateFolder("Assets/SystemLab/Generated", "Baked");
            var outs = new List<string>();
            float fdt = 1f / shot.fps;
            foreach (var x in recs)
            {
                var clip = new AnimationClip { frameRate = shot.fps };
                int n = x.poses.Count;
                void Curve(string prop, System.Func<HumanPose, float> get)
                {
                    var keys = new Keyframe[n];
                    for (int i = 0; i < n; i++) keys[i] = new Keyframe(i * fdt, get(x.poses[i]));
                    var c = new AnimationCurve(keys);
                    for (int i = 0; i < n; i++) { AnimationUtility.SetKeyLeftTangentMode(c, i, AnimationUtility.TangentMode.Linear); AnimationUtility.SetKeyRightTangentMode(c, i, AnimationUtility.TangentMode.Linear); }
                    AnimationUtility.SetEditorCurve(clip, EditorCurveBinding.FloatCurve("", typeof(Animator), prop), c);
                }
                Curve("RootT.x", p => p.bodyPosition.x); Curve("RootT.y", p => p.bodyPosition.y); Curve("RootT.z", p => p.bodyPosition.z);
                // keep quaternion signs continuous
                for (int i = 1; i < n; i++)
                {
                    var a = x.poses[i - 1].bodyRotation; var b = x.poses[i].bodyRotation;
                    if (Quaternion.Dot(a, b) < 0) { var hp = x.poses[i]; hp.bodyRotation = new Quaternion(-b.x, -b.y, -b.z, -b.w); x.poses[i] = hp; }
                }
                Curve("RootQ.x", p => p.bodyRotation.x); Curve("RootQ.y", p => p.bodyRotation.y);
                Curve("RootQ.z", p => p.bodyRotation.z); Curve("RootQ.w", p => p.bodyRotation.w);
                for (int m = 0; m < HumanTrait.MuscleCount; m++) { int mm = m; Curve(HumanTrait.MuscleName[m], p => p.muscles[mm]); }
                // height and tilt stay in the pose (Bake Into Pose, original), only ground travel and heading drive the root
                var cs = AnimationUtility.GetAnimationClipSettings(clip);
                cs.loopBlendPositionY = true; cs.keepOriginalPositionY = true;
                cs.loopBlendOrientation = true; cs.keepOriginalOrientation = true;
                cs.loopTime = false;
                AnimationUtility.SetAnimationClipSettings(clip, cs);
                string path = $"{dir}/{shotId}_{x.r.id}.anim";
                AssetDatabase.DeleteAsset(path);
                AssetDatabase.CreateAsset(clip, path);

                // verify: replay on a fresh instance, compare to the simulated positions (root space)
                var probe = Object.Instantiate(x.r.track.go);
                probe.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
                var pa = probe.GetComponent<Animator>();
                pa.applyRootMotion = false;
                double err = 0, mx = 0; int cnt = 0;
                for (int i = 0; i < n; i += 5)
                {
                    clip.SampleAnimation(probe, i * fdt);
                    for (int k = 0; k < Check.Length; k++)
                    {
                        var got = probe.transform.InverseTransformPoint(pa.GetBoneTransform(Check[k]).position);
                        float e = Vector3.Distance(got, x.pos[i][k]);
                        err += e; mx = System.Math.Max(mx, e); cnt++;
                    }
                }
                Object.DestroyImmediate(probe);
                outs.Add($"{{\"id\":\"{x.r.id}\",\"clip\":\"{path}\",\"frames\":{n},\"replay_err_cm\":{(100 * err / System.Math.Max(1, cnt)).ToString("0.##", CultureInfo.InvariantCulture)},\"replay_err_max_cm\":{(100 * mx).ToString("0.##", CultureInfo.InvariantCulture)}}}");
            }
            AssetDatabase.SaveAssets();
            return "[" + string.Join(",", outs) + "]";
        }
    }
}
