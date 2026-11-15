// WorldLab copy of unity/DemoStudio/Assets/Editor/ShotStudio (characters, props, seats, camera language), patched so a
// shot can use a generated world as its stage ("world:<json>"). Keep in sync with DemoStudio when ShotStudio changes.
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
            public List<HeldProp> props = new List<HeldProp>();
            public List<(PropSpec spec, Props.FingerSet fs)> fingers = new List<(PropSpec, Props.FingerSet)>();
            public List<SeatState> seats = new List<SeatState>();
            public float travelScale = 1;
        }

        static readonly Dictionary<string, FurnitureInfo> furniture = new Dictionary<string, FurnitureInfo>();
        static WorldLab.BuiltWorld world;      // WorldLab: the generated room when the stage is "world:..."
        static WorldLab.EffectsRig worldFx;

        static void Cull(StageInfo stage, Vector3 cam, bool overhead)
        {
            if (world != null) WorldLab.WorldBuilder.Cull(world, cam);
            else Stages.CullForCamera(stage, cam, overhead);
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

            // Set dressing placed by the shot (seats are measured), then actors and their clip timelines.
            furniture.Clear();
            var furnitureClear = new List<Vector3>();
            foreach (var f in s.furniture ?? new FurnitureSpec[0])
            {
                var fi = Stages.Furniture(f);
                furniture[string.IsNullOrEmpty(f.id) ? fi.go.name : f.id] = fi;
                for (int q = 0; q < 9; q++) furnitureClear.Add(fi.bounds.center + new Vector3((q % 3 - 1) * fi.bounds.extents.x, 0, (q / 3 - 1) * fi.bounds.extents.z));
            }
            var actors = new List<Actor>();
            foreach (var a in s.actors ?? new ActorSpec[0]) actors.Add(MakeActor(a));
            Mark("actors");

            // Pre-pass: sample the body over the shot for the camera solver, the stage (keep-clear area) and validation.
            float dt = 0.1f;
            int ns = Mathf.Max(2, Mathf.CeilToInt(s.seconds / dt) + 1);
            var tracks = actors.Select(x => new Track { id = x.spec.id, height = x.spec.height }).ToList();
            var keepClear = new List<Vector3>(furnitureClear);
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
            // WorldLab: "world:<resolved world json>" builds a generated room with its own physically derived lighting
            // instead of a stage preset + look.
            Look look; Looks.Rig rig; StageInfo stage;
            if (s.stage != null && s.stage.StartsWith("world:"))
            {
                var built = WorldLab.WorldRenderer.BuildForShot(s.stage.Substring(6));
                world = built.world; worldFx = built.fx;
                look = new Look { name = "world", practicals = false, sky = RenderSettings.skybox != null, rimIntensity = 0, dof = built.rig.volume ? 0.6f : 0, fog = RenderSettings.fog };
                rig = new Looks.Rig { look = look, volume = built.rig.volume };
                stage = new StageInfo { name = "world", area = world.roomBounds };
            }
            else
            {
                world = null; worldFx = null;
                look = Looks.Get(s.lighting?.preset);
                rig = Looks.Apply(look, s.lighting ?? new LightSpec(), camTrack.yaw);
                stage = Stages.Build(s.stage, s.seed, keepClear);
            }
            var lightSpec = s.lighting ?? new LightSpec();
            if (lightSpec.rim >= 0 && rig.rim) rig.rim.intensity = lightSpec.rim;
            else if (lightSpec.rim > 0)
            {
                rig.rim = new GameObject("Rim").AddComponent<Light>();
                rig.rim.type = LightType.Directional; rig.rim.color = look.rimColor; rig.rim.intensity = lightSpec.rim;
                rig.rim.transform.rotation = Quaternion.Euler(25, camTrack.yaw + 180 + 35, 0);
            }
            bool haze = Weather.Rain(lightSpec.weather) || Weather.Fog(lightSpec.weather);
            var lampHeads = new List<(Vector3 p, Color c)>();
            foreach (var f in s.furniture ?? new FurnitureSpec[0])
                if (f.lamp != null && f.lamp.Length >= 3 && furniture.TryGetValue(f.id ?? "", out var fl) && look.practicals)
                {
                    var head = fl.go.transform.position + Quaternion.Euler(0, f.yaw, 0) * new Vector3(f.lamp[0], f.lamp[1], f.lamp[2]);
                    Looks.Point(head, look.practicalColor, look.practicalIntensity * 1.6f, look.practicalRange * 1.1f, true);
                    lampHeads.Add((head, look.practicalColor));
                    Glow(head, look.practicalColor, 0.3f);
                }
            foreach (var pr in s.practicals ?? new PracticalSpec[0])
            {
                var pp = new Vector3(pr.pos[0], pr.pos[1], pr.pos[2]);
                var c = pr.color != null && pr.color.Length >= 3 ? new Color(pr.color[0], pr.color[1], pr.color[2]) : look.practicalColor;
                var l = Looks.Point(pp, c, pr.intensity, pr.range, pr.shadows);
                if (pr.type == "spot")
                {
                    l.type = LightType.Spot; l.spotAngle = pr.angle; l.innerSpotAngle = pr.angle * 0.5f;
                    var d = pr.dir != null && pr.dir.Length >= 3 ? new Vector3(pr.dir[0], pr.dir[1], pr.dir[2]) : Vector3.down;
                    l.transform.rotation = Quaternion.LookRotation(d.normalized, Mathf.Abs(d.normalized.y) > 0.95f ? Vector3.forward : Vector3.up);
                }
                if (pr.glow) Glow(pp, c, 0.22f);
            }            if (look.practicals)
            {
                // Nearest lamps first (URP lights 8 per object), each with a glowing head for bloom outdoors.
                var centre = tracks.Count > 0 ? tracks[0].Ground(0) : Vector3.zero;
                int shadowed = 0;
                var camAt = camTrack.pos[0];
                bool wet = Weather.Rain(s.lighting?.weather);
                foreach (var lp in stage.lamps.Where(p => stage.name == "interior" || p.y > 4.5f || (!wet && Vector3.Distance(p, camAt) > 8f))
                                              .OrderBy(p => Vector3.Distance(p, centre)).Take(6))
                {   // low outdoor lights right by the camera only paint glare blobs on wet ground
                    Looks.Point(lp, look.practicalColor, look.practicalIntensity, look.practicalRange, shadowed++ < 2);
                    if (stage.name != "interior" && lp.y > 4.5f) lampHeads.Add((lp, look.practicalColor));
                    if (stage.name != "interior" && lp.y > 4.5f) // bulbs on lamp heads only (shop-window lights stay unseen)
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
            // Haze catching the lamp light: cones under the street lamps (subtle on a clear night, strong in rain/fog).
            if (look.practicals && stage.name != "interior")
                foreach (var (p, c) in lampHeads) Weather.LightCone(p, c, haze ? 0.075f : 0.035f);
            var (c0, r0, _) = camTrack.At(0);
            var weather = Weather.Apply(lightSpec, look, c0, r0 * Vector3.forward, s.fps);
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
                Cull(stage, wp, camTrack.overhead);
                for (int w = 0; w < 3; w++) cam.Render();
            }
            var report = new StringBuilder();
            report.Append("{\"frames\":[");
            bool firstRep = true;
            var bake = new Mesh();
            var pending = new List<System.Threading.Tasks.Task>();
            var prevHips = new Vector3[actors.Count];
            var maxJump = new float[actors.Count];
            for (int f = 0; f < frames; f++)
            {
                float t = f / (float)s.fps;
                if (f > 0) { weather.Step(1f / s.fps); worldFx?.Step(1f / s.fps); }
                bool rep = s.reportEvery > 0 && (f % s.reportEvery == 0 || f == frames - 1);
                for (int j = 0; j < actors.Count; j++)
                {
                    Pose(actors[j], t, rep);
                    if (rep) foreach (var hp in actors[j].props) Props.Measure(hp, actors[j].anim, actors[j].spec.height);
                    var h = actors[j].anim.GetBoneTransform(HumanBodyBones.Hips).position;
                    if (f > 0) maxJump[j] = Mathf.Max(maxJump[j], Vector3.Distance(h, prevHips[j]));
                    prevHips[j] = h;
                }
                var (cp, cr, fov) = camTrack.At(t);
                cam.transform.SetPositionAndRotation(cp, cr);
                cam.fieldOfView = fov;
                Cull(stage, cp, camTrack.overhead);
                cam.Render();
                Graphics.Blit(rt, outRt);
                RenderTexture.active = outRt;
                tex.ReadPixels(new Rect(0, 0, s.width, s.height), 0, 0);
                RenderTexture.active = null;
                // Encode and write on worker threads (thread-safe array encoders); the main thread renders on.
                var raw = tex.GetRawTextureData<byte>().ToArray();
                string file = Path.Combine(s.outDir, $"f{f:D5}.{(s.format == "jpg" ? "jpg" : "png")}");
                bool jpg = s.format == "jpg"; int w0 = s.width, h0 = s.height;
                while (pending.Count(x => !x.IsCompleted) > 6) pending.First(x => !x.IsCompleted).Wait();
                pending.Add(System.Threading.Tasks.Task.Run(() =>
                {
                    var bytes = jpg ? ImageConversion.EncodeArrayToJPG(raw, UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8B8_SRGB, (uint)w0, (uint)h0, 0, 95)
                                    : ImageConversion.EncodeArrayToPNG(raw, UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8B8_SRGB, (uint)w0, (uint)h0);
                    File.WriteAllBytes(file, bytes);
                }));

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
            System.Threading.Tasks.Task.WaitAll(pending.ToArray());
            Mark("render");
            report.Append("],");
            report.Append($"\"camera\":{{\"preset\":\"{camTrack.preset}\",\"yaw\":{F(camTrack.yaw)},\"focus\":{F(camTrack.focus)}}},");
            report.Append("\"actors\":[" + string.Join(",", actors.Select((x, j) => $"{{\"id\":\"{x.spec.id}\",\"maxHipStepM\":{F(maxJump[j])},\"segments\":{x.spec.segs?.Length ?? 0}," +
                $"\"props\":[{string.Join(",", x.props.Select(Props.Report))}],\"seats\":[{string.Join(",", x.seats.Select(Seating.Report))}]}}")) + "],");
            report.Append("\"furniture\":[" + string.Join(",", furniture.Values.Select(fi => $"{{\"id\":\"{fi.id}\",\"seatTopM\":{F(fi.seatTop)},\"seatCenter\":[{V(fi.seatCenter)}],\"scaleY\":{F(fi.scaleY)},\"boundsMin\":[{V(fi.bounds.min)}],\"boundsMax\":[{V(fi.bounds.max)}]}}")) + "],");
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
            // Props and finger poses are calibrated in the bind pose, before anything animates the rig.
            foreach (var ps in a.props ?? new PropSpec[0])
            {
                if (string.IsNullOrEmpty(ps.model)) continue;
                x.props.Add(Props.Attach(ps, x.go, x.anim, a.height));
                var fs = Props.FingerTargets(x.anim, (ps.hand ?? "right").ToLower().StartsWith("l"), ps.fingers);
                if (fs != null) x.fingers.Add((ps, fs));
            }
            foreach (var ss in a.seats ?? new SeatSpec[0])
            {
                if (!furniture.TryGetValue(ss.furniture ?? "", out var fi)) throw new System.Exception($"actor {a.id}: seat on unknown furniture '{ss.furniture}'");
                x.seats.Add(new SeatState { spec = ss, seat = fi });
            }
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
                CalibrateTravel(x);
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
        static void Pose(Actor x, float t, bool measure = false)
        {
            PoseBody(x, t);
            // Fingers for held props, then the seat contact, then the props follow the final hand.
            foreach (var (ps, fs) in x.fingers)
            {
                const float b = 0.2f;
                float w = t < ps.start ? 1 - (ps.start - t) / b : t > ps.end ? 1 - (t - ps.end) / b : 1;
                Props.ApplyFingers(fs, w);
            }
            foreach (var st in x.seats) Seating.Apply(st, x.anim, x.grounding, t, measure);
            foreach (var hp in x.props) Props.Place(hp, t);
        }

        static void Glow(Vector3 p, Color c, float size)
        {
            var bulb = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            bulb.name = "LampGlow"; Object.DestroyImmediate(bulb.GetComponent<Collider>());
            bulb.transform.position = p; bulb.transform.localScale = Vector3.one * size;
            var br = bulb.GetComponent<Renderer>(); br.sharedMaterial = Materials.Emissive(c, 6f); br.shadowCastingMode = ShadowCastingMode.Off;
        }

        /// Evaluates the graph and rescales this step's root travel (horizontal) to metres: Humanoid retargeting
        /// scales root motion with the avatar, so without this a 1.66 m character covers ~6 % less ground than the
        /// generated clip and staged end points (walk-ins, seats) miss.
        static void Eval(Actor x, float dt)
        {
            var before = x.go.transform.position;
            x.graph.Evaluate(dt);
            if (Mathf.Abs(x.travelScale - 1) > 1e-4f)
            {
                var after = x.go.transform.position;
                var d = after - before;
                x.go.transform.position = before + new Vector3(d.x * x.travelScale, d.y, d.z * x.travelScale);
            }
        }

        /// Travel scale from the actor's longest-travel clip: metric distance (from Python, from the motion data) over
        /// the distance the clip moves this character in Unity.
        static void CalibrateTravel(Actor x)
        {
            var c = x.spec.travelCal;
            if (c == null || c.Length < 2 || c[1] < 0.3f || x.clips.Count == 0) return;
            int k = Mathf.Clamp((int)c[0], 0, x.clips.Count - 1);
            var clip = x.clips[k];
            float len = (float)clip.GetAnimationClip().length;
            for (int i = 0; i < x.clips.Count; i++) { x.mixer.SetInputWeight(i, i == k ? 1 : 0); if (i == k) x.clips[i].Play(); else x.clips[i].Pause(); }
            x.go.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            clip.SetSpeed(1); clip.SetTime(0); clip.SetTime(0);
            x.graph.Evaluate(0);
            var p0 = x.go.transform.position;
            for (float t = 0; t < len - 1e-4f; t += 1 / 30f) x.graph.Evaluate(Mathf.Min(1 / 30f, len - t));
            var d = x.go.transform.position - p0; d.y = 0;
            if (d.magnitude > 0.2f) x.travelScale = Mathf.Clamp(c[1] / d.magnitude, 0.7f, 1.4f);
            Debug.Log($"SHOT_TRAVEL {x.spec.id} metric={c[1]:F3} unity={d.magnitude:F3} scale={x.travelScale:F3}");
            x.go.transform.SetPositionAndRotation(P(x.spec.pos), Quaternion.Euler(0, x.spec.yaw, 0));
        }

        static void PoseBody(Actor x, float t)
        {
            var segs = x.spec.segs;
            if (segs == null || segs.Length == 0) return;
            int k = 0;
            for (int i = 0; i < segs.Length; i++) if (t >= segs[i].start - 1e-4f) k = i;
            var s = segs[k];
            if (k != x.activeSeg)
            {
                // Finish the previous clip's travel up to the join, so no root motion is lost between frames.
                if (x.activeSeg >= 0 && s.start > x.lastT) Eval(x, s.start - x.lastT);
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
                if (ct > 1e-4f) Eval(x, ct); // entering mid-clip: carry the clip's travel up to ct
                x.clips[k].SetSpeed(s.speed);
                x.activeSeg = k;
            }
            else Eval(x, Mathf.Max(0, t - x.lastT));
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
                var stage = GameObject.Find("Stage_world") ?? GameObject.Find("Stage_" + "street") ?? GameObject.Find("Stage_interior") ?? GameObject.Find("Stage_park") ?? GameObject.Find("Stage_studio") ?? GameObject.Find("Stage_void");
                // Large solid props only (buildings, walls, trees, furniture taller than 1.2 m); the ground plane is excluded.
                _occ = stage ? stage.GetComponentsInChildren<Renderer>().Where(r => r.name != "Ground" && r.name != "Road" && r.name != "Floor" && r.name != "Ceiling" && !r.name.StartsWith("Wall") && r.bounds.size.y > 1.2f && r.bounds.size.y < 60).ToArray() : new Renderer[0];
                _occScene = sc;
            }
            return _occ;
        }
    }
}
