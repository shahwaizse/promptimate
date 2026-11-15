// Headless shot renderer (URP): ShotSpec JSON in, numbered frames + report.json out.
//   Unity.exe -batchmode -projectPath unity/DemoStudio -executeMethod ShotStudio.ShotRenderer.Run -shot <spec.json>
// (no -nographics: rendering needs the GPU). ShotServer keeps one editor warm and runs many shots.
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace ShotStudio
{
    public static class ShotRenderer
    {
        class Actor
        {
            public ActorSpec spec; public GameObject go; public Animator anim;
            public PlayableGraph graph; public AnimationMixerPlayable mixer; public List<AnimationClipPlayable> clips = new List<AnimationClipPlayable>();
            public Promptimate.PromptimateGrounding grounding; public int activeSeg = -2; public float lastT;
            public SkinnedMeshRenderer[] smrs;
        }

        public static void Run()
        {
            var args = System.Environment.GetCommandLineArgs();
            int i = System.Array.IndexOf(args, "-shot");
            int code = 0;
            try
            {
                if (i < 0) throw new System.Exception("missing -shot <file.json>");
                foreach (var p in args[i + 1].Split(';')) Render(JsonUtility.FromJson<ShotSpec>(File.ReadAllText(p)));
            }
            catch (System.Exception e) { Debug.LogError("SHOT_ERROR " + e); code = 1; }
            EditorApplication.Exit(code);
        }

        public static string Render(ShotSpec s)
        {
            var sw = System.Diagnostics.Stopwatch.StartNew();
            var timing = new StringBuilder();
            void Mark(string what) { timing.Append($"\"{what}\":{sw.Elapsed.TotalSeconds:F2},"); }
            Pipeline.Ensure();
            Materials.Reset();
            ShaderUtil.allowAsyncCompilation = false; // otherwise the first frames render with placeholder shaders
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Mark("setup");

            // Actors and their clip timelines.
            var actors = new List<Actor>();
            foreach (var a in s.actors ?? new ActorSpec[0]) actors.Add(MakeActor(a));
            Mark("actors");

            // Pre-pass: sample the body over the shot for the camera solver, the stage (keep-clear area) and validation.
            float dt = 0.1f;
            int ns = Mathf.Max(2, Mathf.CeilToInt(s.seconds / dt) + 1);
            var tracks = actors.Select(x => new Track { id = x.spec.id, height = x.spec.height }).ToList();
            var keepClear = new List<Vector3>();
            for (int k = 0; k < ns; k++)
            {
                float t = Mathf.Min(k * dt, s.seconds);
                for (int j = 0; j < actors.Count; j++)
                {
                    Pose(actors[j], t);
                    var an = actors[j].anim; var tr = tracks[j];
                    Vector3 B(HumanBodyBones b) { var x = an.GetBoneTransform(b); return x ? x.position : actors[j].go.transform.position; }
                    tr.hips.Add(B(HumanBodyBones.Hips)); tr.head.Add(B(HumanBodyBones.Head));
                    tr.chest.Add(an.GetBoneTransform(HumanBodyBones.Chest) ? B(HumanBodyBones.Chest) : B(HumanBodyBones.Spine));
                    tr.lsh.Add(B(HumanBodyBones.LeftUpperArm)); tr.rsh.Add(B(HumanBodyBones.RightUpperArm));
                    tr.lhand.Add(B(HumanBodyBones.LeftHand)); tr.rhand.Add(B(HumanBodyBones.RightHand));
                    tr.lfoot.Add(B(HumanBodyBones.LeftFoot)); tr.rfoot.Add(B(HumanBodyBones.RightFoot));
                    keepClear.Add(tr.Ground(tr.hips.Count - 1));
                }
            }
            foreach (var a in actors) Reset(a);
            Mark("prepass");

            float aspect = s.width / (float)s.height;
            var camTrack = CameraRig.Build(s.camera ?? new CamSpec(), tracks, dt, aspect, s.seconds);
            // Keep the camera's spot and its view of every actor free of props.
            for (int i = 0; i < camTrack.pos.Count; i += 4)
            {
                var cp0 = camTrack.pos[i]; keepClear.Add(new Vector3(cp0.x, 0, cp0.z));
                foreach (var tr in tracks)
                {
                    var g = tr.Ground(Mathf.Min(i, tr.hips.Count - 1));
                    var c2 = new Vector3(cp0.x, 0, cp0.z);
                    int steps = Mathf.CeilToInt(Vector3.Distance(c2, g) / 0.8f);
                    for (int q = 1; q < steps; q++) keepClear.Add(Vector3.Lerp(c2, g, q / (float)steps));
                }
            }
            var look = Looks.Get(s.lighting?.preset);
            var rig = Looks.Apply(look, s.lighting ?? new LightSpec(), camTrack.yaw);
            var stage = Stages.Build(s.stage, s.seed, keepClear);
            if (look.practicals)
            {
                // Nearest lamps first (URP lights 8 per object), each with a glowing head for bloom outdoors.
                var centre = tracks.Count > 0 ? tracks[0].Ground(0) : Vector3.zero;
                int shadowed = 0;
                foreach (var lp in stage.lamps.OrderBy(p => Vector3.Distance(p, centre)).Take(6))
                {
                    Looks.Point(lp, look.practicalColor, look.practicalIntensity, look.practicalRange, shadowed++ < 2);
                    if (stage.name != "interior")
                    {
                        var bulb = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                        bulb.name = "LampGlow"; Object.DestroyImmediate(bulb.GetComponent<Collider>());
                        bulb.transform.position = lp; bulb.transform.localScale = Vector3.one * 0.35f;
                        var br = bulb.GetComponent<Renderer>(); br.sharedMaterial = Materials.Emissive(look.practicalColor, 6f); br.shadowCastingMode = ShadowCastingMode.Off;
                    }
                }
            }
            if (look.sceneKey > 0 && tracks.Count > 0)
            {
                // A practical just off-screen beside the actors (street lamp / shop sign), on the key side.
                var c = Vector3.zero; foreach (var tr in tracks) c += tr.Ground(tr.hips.Count / 2); c /= tracks.Count;
                var side = Quaternion.Euler(0, camTrack.yaw - 60, 0) * Vector3.back;
                Looks.Point(c + side * 2.6f + Vector3.up * 3.4f, look.practicalColor, look.sceneKey, 9f, true);
            }
            Looks.Focus(rig, camTrack.focus, camTrack.fov[0]);
            Mark("stage");

            // Camera and targets. Supersampling: render larger, box-filter down.
            var camGo = new GameObject("ShotCam");
            var cam = camGo.AddComponent<Camera>();
            cam.nearClipPlane = 0.05f; cam.farClipPlane = 400;
            cam.allowHDR = true; cam.allowMSAA = true;
            cam.clearFlags = look.sky ? CameraClearFlags.Skybox : CameraClearFlags.SolidColor;
            cam.backgroundColor = look.background;
            var data = camGo.AddComponent<UniversalAdditionalCameraData>();
            data.renderPostProcessing = true;
            data.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            data.antialiasingQuality = AntialiasingQuality.High;
            data.renderShadows = true;
            data.requiresDepthTexture = true;
            float ss = Mathf.Clamp(s.supersample, 1, 2);
            int W = Mathf.RoundToInt(s.width * ss), H = Mathf.RoundToInt(s.height * ss);
            var rt = new RenderTexture(W, H, 24, RenderTextureFormat.ARGB32) { antiAliasing = 4, name = "shot_rt" };
            rt.Create();
            var outRt = new RenderTexture(s.width, s.height, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB) { name = "shot_out" };
            cam.targetTexture = rt;
            var tex = new Texture2D(s.width, s.height, TextureFormat.RGB24, false);

            Directory.CreateDirectory(s.outDir);
            foreach (var f in Directory.GetFiles(s.outDir, "f*.*")) File.Delete(f);
            int frames = Mathf.Max(1, Mathf.RoundToInt(s.seconds * s.fps));
            // Warm-up renders (shader variants, texture uploads, shadow maps) before the first real frame.
            {
                foreach (var a in actors) { Pose(a, 0); Reset(a); }
                var (wp, wr, wf) = camTrack.At(0);
                cam.transform.SetPositionAndRotation(wp, wr); cam.fieldOfView = wf;
                Stages.CullForCamera(stage, wp, camTrack.overhead);
                for (int w = 0; w < 3; w++) cam.Render();
            }
            var report = new StringBuilder();
            report.Append("{\"frames\":[");
            bool firstRep = true;
            var bake = new Mesh();
            var prevHips = new Vector3[actors.Count];
            var maxJump = new float[actors.Count];
            for (int f = 0; f < frames; f++)
            {
                float t = f / (float)s.fps;
                for (int j = 0; j < actors.Count; j++)
                {
                    Pose(actors[j], t);
                    var h = actors[j].anim.GetBoneTransform(HumanBodyBones.Hips).position;
                    if (f > 0) maxJump[j] = Mathf.Max(maxJump[j], Vector3.Distance(h, prevHips[j]));
                    prevHips[j] = h;
                }
                var (cp, cr, fov) = camTrack.At(t);
                cam.transform.SetPositionAndRotation(cp, cr);
                cam.fieldOfView = fov;
                Stages.CullForCamera(stage, cp, camTrack.overhead);
                cam.Render();
                Graphics.Blit(rt, outRt);
                RenderTexture.active = outRt;
                tex.ReadPixels(new Rect(0, 0, s.width, s.height), 0, 0);
                tex.Apply(false);
                RenderTexture.active = null;
                var bytes = s.format == "jpg" ? tex.EncodeToJPG(95) : tex.EncodeToPNG();
                File.WriteAllBytes(Path.Combine(s.outDir, $"f{f:D5}.{(s.format == "jpg" ? "jpg" : "png")}"), bytes);

                if (s.reportEvery > 0 && (f % s.reportEvery == 0 || f == frames - 1))
                {
                    report.Append(firstRep ? "" : ",");
                    firstRep = false;
                    report.Append($"{{\"f\":{f},\"t\":{F(t)},\"cam\":[{V(cp)}],\"fov\":{F(fov)},\"actors\":[");
                    for (int j = 0; j < actors.Count; j++)
                    {
                        Measure(actors[j], actors, cam, bake, out var vmin, out var vmax, out float inside, out float minY, out float visible);
                        var hv = cam.WorldToViewportPoint(actors[j].anim.GetBoneTransform(HumanBodyBones.Head).position);
                        int headIn = hv.z > 0 && hv.x > 0.02f && hv.x < 0.98f && hv.y > 0.02f && hv.y < 0.98f ? 1 : 0;
                        report.Append(j > 0 ? "," : "");
                        report.Append($"{{\"id\":\"{actors[j].spec.id}\",\"bbox\":[{F(vmin.x)},{F(vmin.y)},{F(vmax.x)},{F(vmax.y)}],\"inFrame\":{F(inside)},\"visible\":{F(visible)},\"headIn\":{headIn},\"head\":[{F(hv.x)},{F(hv.y)}],\"minY\":{F(minY)},\"hips\":[{V(prevHips[j])}],\"depth\":{F(vmin.z)}}}");
                    }
                    report.Append("]}");
                }
            }
            Mark("render");
            report.Append("],");
            report.Append($"\"camera\":{{\"preset\":\"{camTrack.preset}\",\"yaw\":{F(camTrack.yaw)},\"focus\":{F(camTrack.focus)}}},");
            report.Append("\"actors\":[" + string.Join(",", actors.Select((x, j) => $"{{\"id\":\"{x.spec.id}\",\"maxHipStepM\":{F(maxJump[j])},\"segments\":{x.spec.segs?.Length ?? 0}}}")) + "],");
            report.Append($"\"width\":{s.width},\"height\":{s.height},\"fps\":{s.fps},\"frameCount\":{frames},\"stage\":\"{stage.name}\",\"lighting\":\"{look.name}\",");
            report.Append("\"timing\":{" + timing.ToString().TrimEnd(',') + "}}");
            File.WriteAllText(Path.Combine(s.outDir, "report.json"), report.ToString());

            foreach (var a in actors) if (a.graph.IsValid()) a.graph.Destroy();
            Object.DestroyImmediate(bake);
            cam.targetTexture = null; rt.Release(); outRt.Release();
            Object.DestroyImmediate(tex);
            Debug.Log($"SHOT_DONE id={s.id} frames={frames} seconds={sw.Elapsed.TotalSeconds:F1} out={s.outDir}");
            return s.outDir;
        }

        static string F(float v) => float.IsNaN(v) || float.IsInfinity(v) ? "0" : v.ToString("0.####", CultureInfo.InvariantCulture);
        static string V(Vector3 v) => $"{F(v.x)},{F(v.y)},{F(v.z)}";

        static Actor MakeActor(ActorSpec a)
        {
            var x = new Actor { spec = a, go = Cast.Spawn(a) };
            x.anim = x.go.GetComponent<Animator>();
            x.anim.applyRootMotion = true;
            x.smrs = x.go.GetComponentsInChildren<SkinnedMeshRenderer>();
            x.go.transform.SetPositionAndRotation(P(a.pos), Quaternion.Euler(0, a.yaw, 0));
            if (a.grounding)
            {
                x.grounding = x.go.AddComponent<Promptimate.PromptimateGrounding>();
                x.grounding.Calibrate(); // bind pose, final scale
            }
            if (a.segs != null && a.segs.Length > 0)
            {
                x.graph = PlayableGraph.Create(x.go.name);
                x.graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
                x.mixer = AnimationMixerPlayable.Create(x.graph, a.segs.Length);
                for (int k = 0; k < a.segs.Length; k++)
                {
                    var clip = LoadClip(a.segs[k].clip);
                    var cp = AnimationClipPlayable.Create(x.graph, clip);
                    cp.SetApplyFootIK(a.footIK);
                    cp.Pause();
                    x.graph.Connect(cp, 0, x.mixer, k);
                    x.clips.Add(cp);
                }
                AnimationPlayableOutput.Create(x.graph, "out", x.anim).SetSourcePlayable(x.mixer);
                x.graph.Play();
            }
            return x;
        }

        static Vector3 P(float[] a) => a == null || a.Length < 3 ? Vector3.zero : new Vector3(a[0], a[1], a[2]);

        static AnimationClip LoadClip(string path)
        {
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
            if (clip == null)
            {
                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
                clip = AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().FirstOrDefault();
            }
            return clip ?? throw new System.Exception("missing clip " + path);
        }

        static void Reset(Actor x) { x.activeSeg = -2; x.lastT = 0; }

        /// Poses an actor at shot time t (non-decreasing since the last Reset). Clips play with Apply Root Motion, the
        /// way Unity chains Promptimate clips: the first segment is placed at its world spot, later segments carry on
        /// from wherever the previous clip left the character (continue_from clips start in its last pose).
        static void Pose(Actor x, float t)
        {
            var segs = x.spec.segs;
            if (segs == null || segs.Length == 0) return;
            int k = 0;
            for (int i = 0; i < segs.Length; i++) if (t >= segs[i].start - 1e-4f) k = i;
            var s = segs[k];
            if (k != x.activeSeg)
            {
                // Finish the previous clip's travel up to the join, so no root motion is lost between frames.
                if (x.activeSeg >= 0 && s.start > x.lastT) x.graph.Evaluate(s.start - x.lastT);
                float ct = s.clipStart + Mathf.Max(0, t - s.start) * s.speed;
                for (int i = 0; i < segs.Length; i++)
                {
                    x.mixer.SetInputWeight(i, i == k ? 1 : 0);
                    if (i == k) x.clips[i].Play(); else x.clips[i].Pause();
                }
                if (x.activeSeg < 0 || s.place)
                    x.go.transform.SetPositionAndRotation(P(s.pos), Quaternion.Euler(0, s.yaw, 0));
                x.clips[k].SetSpeed(1);
                x.clips[k].SetTime(0);
                x.clips[k].SetTime(0); // twice: also resets the previous time, so the jump adds no root motion
                x.graph.Evaluate(0);
                if (ct > 1e-4f) x.graph.Evaluate(ct); // entering mid-clip: carry the clip's travel up to ct
                x.clips[k].SetSpeed(s.speed);
                x.activeSeg = k;
            }
            else x.graph.Evaluate(Mathf.Max(0, t - x.lastT));
            x.lastT = t;
            if (x.grounding) x.grounding.Solve();
        }

        /// Projects the skinned meshes into the camera: viewport bbox, share of vertices inside the frame, share not
        /// hidden behind stage geometry (centre ray test against stage renderers' bounds), lowest world point.
        static void Measure(Actor x, List<Actor> all, Camera cam, Mesh bake, out Vector3 vmin, out Vector3 vmax, out float inside, out float minY, out float visible)
        {
            vmin = new Vector3(float.MaxValue, float.MaxValue, float.MaxValue); vmax = new Vector3(float.MinValue, float.MinValue, float.MinValue);
            int total = 0, inn = 0; minY = float.MaxValue;
            foreach (var smr in x.smrs)
            {
                if (!smr.enabled) continue;
                smr.BakeMesh(bake, true);
                var m = smr.transform.localToWorldMatrix;
                var verts = bake.vertices;
                for (int i = 0; i < verts.Length; i += 3)
                {
                    var w = m.MultiplyPoint3x4(verts[i]);
                    minY = Mathf.Min(minY, w.y);
                    var vp = cam.WorldToViewportPoint(w);
                    total++;
                    if (vp.z <= 0.01f) continue; // behind the camera: no meaningful projection
                    if (vp.x >= 0 && vp.x <= 1 && vp.y >= 0 && vp.y <= 1) inn++;
                    vp.x = Mathf.Clamp(vp.x, -1, 2); vp.y = Mathf.Clamp(vp.y, -1, 2);
                    vmin = Vector3.Min(vmin, vp); vmax = Vector3.Max(vmax, vp);
                }
            }
            inside = total > 0 ? inn / (float)total : 0;
            if (vmin.x > vmax.x) { vmin = new Vector3(-1, -1, 0); vmax = new Vector3(-1, -1, 0); } // entirely behind
            // Occlusion: sample a few body points and raycast against stage renderer bounds is too coarse; use physics-free
            // depth test via renderer bounds along the ray to the hips and head.
            visible = 1;
            var head = x.anim.GetBoneTransform(HumanBodyBones.Head).position;
            var hips = x.anim.GetBoneTransform(HumanBodyBones.Hips).position;
            int blocked = 0, tests = 0;
            foreach (var target in new[] { head, hips, Vector3.Lerp(head, hips, 0.5f) })
            {
                tests++;
                var ray = new Ray(cam.transform.position, target - cam.transform.position);
                float d = Vector3.Distance(cam.transform.position, target);
                bool hitSomething = false;
                foreach (var r in Occluders())
                    if (r.enabled && r.bounds.IntersectRay(ray, out var hit) && hit < d - 0.3f && hit > 0.05f && !r.bounds.Contains(target)) { hitSomething = true; break; }
                // Other characters in front of this one (bounds shrunk a little: skinned bounds are generous).
                if (!hitSomething)
                    foreach (var o in all)
                    {
                        if (o == x) continue;
                        foreach (var smr in o.smrs)
                        {
                            var b = smr.bounds; b.extents *= 0.8f;
                            if (b.IntersectRay(ray, out var h2) && h2 < d - 0.3f && h2 > 0.05f && !b.Contains(target)) { hitSomething = true; break; }
                        }
                        if (hitSomething) break;
                    }
                if (hitSomething) blocked++;
            }
            visible = 1 - blocked / (float)tests;
        }

        static Renderer[] _occ;
        static int _occScene = -1;
        static IEnumerable<Renderer> Occluders()
        {
            var sc = EditorSceneManager.GetActiveScene().handle;
            if (_occ == null || _occScene != sc)
            {
                var stage = GameObject.Find("Stage_" + "street") ?? GameObject.Find("Stage_interior") ?? GameObject.Find("Stage_park") ?? GameObject.Find("Stage_studio") ?? GameObject.Find("Stage_void");
                // Large solid props only (buildings, walls, trees, furniture taller than 1.2 m); the ground plane is excluded.
                _occ = stage ? stage.GetComponentsInChildren<Renderer>().Where(r => r.name != "Ground" && r.name != "Road" && r.bounds.size.y > 1.2f && r.bounds.size.y < 60).ToArray() : new Renderer[0];
                _occScene = sc;
            }
            return _occ;
        }
    }
}
