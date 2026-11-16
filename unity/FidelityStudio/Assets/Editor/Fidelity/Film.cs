// Offline film renderer (HDRP). FilmSpec JSON in (demo/fidelity/make_film.py), numbered frames per shot out.
//   Unity.exe -batchmode -force-d3d12 -projectPath unity/FidelityStudio -executeMethod Fidelity.Film.Run -spec <film.json>
// mode "pt": HDRP path tracer, `spp` sub-frames accumulated per frame; the actors and camera move between sub-frames
// over the open shutter, which gives true motion blur; depth of field comes from the physical camera; Intel Open
// Image Denoise cleans the result. mode "raster": fast HDRP raster preview of the same film.
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
using UnityEngine.Rendering.HighDefinition;

namespace Fidelity
{
    public static class Film
    {
        class Actor
        {
            public ActorSpec spec; public GameObject go; public Animator anim;
            public PlayableGraph graph; public AnimationMixerPlayable mixer; public List<AnimationClipPlayable> clips = new List<AnimationClipPlayable>();
            public Promptimate.PromptimateGrounding grounding; public int activeSeg = -2; public float lastT;
            public float travelScale = 1;
            public Vector3 seatOffset;
            public List<SeatState> seats = new List<SeatState>();
            public List<Prop> props = new List<Prop>();
            public List<(ReachSpec spec, Transform piece, Vector3 from, Vector3 to)> reaches = new List<(ReachSpec, Transform, Vector3, Vector3)>();
        }

        class Prop
        {
            public PropSpec spec; public GameObject go; public Vector3 grip; public bool left; public bool dropped; public float release;
        }

        public static void Run()
        {
            int code = 0;
            try
            {
                var f = Lib.Arg("-spec") ?? throw new System.Exception("missing -spec");
                Render(JsonUtility.FromJson<FilmSpec>(File.ReadAllText(f)));
            }
            catch (System.Exception e) { Debug.LogError("FID_ERROR " + e); code = 1; }
            EditorApplication.Exit(code);
        }

        static Volume volume; static VolumeProfile prof; static Exposure exposure; static PathTracing pt;

        public static void Render(FilmSpec s)
        {
            var total = System.Diagnostics.Stopwatch.StartNew();
            Setup.Project(); Setup.Ensure();
            ShaderUtil.allowAsyncCompilation = false;
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Lib.ResetCache();
            var room = Room.Build(Room.LoadLayout());
            Environment(s, room);
            var actors = s.actors.Select(a => MakeActor(a, room)).ToList();
            if (s.dust) Dust(room, s);

            var camGo = new GameObject("FilmCam");
            var cam = camGo.AddComponent<Camera>();
            var hd = camGo.AddComponent<HDAdditionalCameraData>();
            hd.antialiasing = s.mode == "pt" ? HDAdditionalCameraData.AntialiasingMode.None : HDAdditionalCameraData.AntialiasingMode.TemporalAntialiasing;
            hd.TAAQuality = HDAdditionalCameraData.TAAQualityLevel.High;
            cam.usePhysicalProperties = true; cam.sensorSize = new Vector2(36, 24); cam.gateFit = Camera.GateFitMode.Horizontal;
            cam.nearClipPlane = 0.03f; cam.farClipPlane = 300;
            var rt = Lib.Target(s.width, s.height);
            cam.targetTexture = rt;
            var tex = new Texture2D(s.width, s.height, TextureFormat.RGB24, false);
            var hdrp = RenderPipelineManager.currentPipeline as HDRenderPipeline;
            cam.Render();
            hdrp = RenderPipelineManager.currentPipeline as HDRenderPipeline;
            var pending = new List<System.Threading.Tasks.Task>();
            var log = new StringBuilder();
            Directory.CreateDirectory(s.outDir);

            if (s.layoutCheck) { LayoutCheck(s, cam, rt, room, actors); return; }

            var only = new HashSet<string>((s.only ?? "").Split(',').Where(x => x.Length > 0));
            var jobs = new List<(Shot shot, float t, string file)>();
            if (s.frames != null && s.frames.Length > 0)
            {
                var sh = s.shots.FirstOrDefault(x => x.id == s.stillsCam) ?? s.shots[0];
                for (int i = 0; i < s.frames.Length; i++)
                {
                    var shot = s.shots.FirstOrDefault(x => s.frames[i] >= x.t0 && s.frames[i] < x.t1) ?? sh;
                    jobs.Add((shot, s.frames[i], Path.Combine(s.outDir, $"still_{i:D2}_{shot.id}_{s.frames[i]:F2}.{s.format}")));
                }
            }
            else
                foreach (var shot in s.shots)
                {
                    if (only.Count > 0 && !only.Contains(shot.id)) continue;
                    var dir = Path.Combine(s.outDir, shot.id);
                    Directory.CreateDirectory(dir);
                    int n = Mathf.Max(1, Mathf.RoundToInt((shot.t1 - shot.t0) * s.fps));
                    for (int f = 0; f < n; f += Mathf.Max(1, s.frameStep))
                    {
                        var file = Path.Combine(dir, $"f{f:D4}.{s.format}");
                        if (File.Exists(file) && Lib.Arg("-resume") == "1") continue;
                        jobs.Add((shot, shot.t0 + f / (float)s.fps, file));
                    }
                }

            Shot cur = null; float lastT = float.MaxValue;
            int spp = s.mode == "pt" ? Mathf.Max(1, s.spp) : 1;
            if (s.mode == "pt") { pt.maximumSamples.Override(spp); hdrp.BeginRecording(spp, Mathf.Clamp01(s.shutter), 0.1f, 0.9f); }
            var frameSw = new System.Diagnostics.Stopwatch();
            int done = 0;
            // GPU shared memory grows every frame here (HDRP/driver leak); the runner restarts Unity in chunks.
            int maxFrames = int.TryParse(Lib.Arg("-maxFrames", "0"), out var mf) ? mf : 0;
            bool chunked = maxFrames > 0 && jobs.Count > maxFrames;
            if (chunked) jobs = jobs.Take(maxFrames).ToList();
            foreach (var job in jobs)
            {
                frameSw.Restart();
                if (job.shot != cur || job.t < lastT)
                {
                    cur = job.shot; foreach (var a in actors) Reset(a);
                    exposure.fixedExposure.Override(cur.ev);
                }
                if (s.mode == "pt")
                {
                    for (int k = 0; k < spp; k++)
                    {
                        float tt = job.t + (k + 0.5f) / spp * Mathf.Clamp01(s.shutter) / s.fps;
                        PoseAll(actors, tt);
                        PlaceCamera(cam, cur, tt);
                        hdrp.PrepareNewSubFrame();
                        cam.Render();
                    }
                }
                else
                {
                    PoseAll(actors, job.t);
                    PlaceCamera(cam, cur, job.t);
                    for (int w = 0; w < (done == 0 ? 6 : 2); w++) cam.Render();
                }
                lastT = job.t;
                if (s.frames != null && s.frames.Length > 0)
                    foreach (var a in actors)
                    {
                        var hp = a.anim.GetBoneTransform(HumanBodyBones.Hips).position;
                        var seg = a.activeSeg >= 0 ? a.spec.segs[a.activeSeg] : null;
                        Debug.Log($"FID_DEBUG t={job.t:F2} {a.spec.id} seg={a.activeSeg} clip={(seg != null ? Path.GetFileNameWithoutExtension(seg.clip) : "-")} ctime={(a.activeSeg >= 0 ? a.clips[a.activeSeg].GetTime() : -1):F2} len={(a.activeSeg >= 0 ? a.clips[a.activeSeg].GetAnimationClip().length : -1):F2} hips=({hp.x:F2},{hp.y:F2},{hp.z:F2}) root=({a.go.transform.position.x:F2},{a.go.transform.position.z:F2}) human={a.anim.isHuman} scale={a.go.transform.localScale.x:F3}");
                    }
                var raw = Lib.Read(rt, tex);
                string file = job.file; int W = s.width, H = s.height; bool jpg = s.format == "jpg";
                while (pending.Count(x => !x.IsCompleted) > 4) pending.First(x => !x.IsCompleted).Wait();
                pending.Add(System.Threading.Tasks.Task.Run(() =>
                {
                    var bytes = jpg ? ImageConversion.EncodeArrayToJPG(raw, UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8B8_SRGB, (uint)W, (uint)H, 0, 95)
                                    : ImageConversion.EncodeArrayToPNG(raw, UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8B8_SRGB, (uint)W, (uint)H);
                    File.WriteAllBytes(file, bytes);
                }));
                done++;
                if (done % 10 == 1 || done == jobs.Count)
                    Debug.Log($"FID_FRAME {done}/{jobs.Count} shot={cur.id} t={job.t:F3} sec={frameSw.Elapsed.TotalSeconds:F2} total={total.Elapsed.TotalSeconds:F0}");
                log.Append($"{{\"shot\":\"{cur.id}\",\"t\":{F(job.t)},\"sec\":{F((float)frameSw.Elapsed.TotalSeconds)}}},");
            }
            System.Threading.Tasks.Task.WaitAll(pending.ToArray());
            if (s.mode == "pt") hdrp.EndRecording();
            var report = new StringBuilder();
            report.Append("{\"frames\":[" + log.ToString().TrimEnd(',') + "],");
            report.Append("\"actors\":[" + string.Join(",", actors.Select(a => $"{{\"id\":\"{a.spec.id}\",\"travelScale\":{F(a.travelScale)},\"seats\":[{string.Join(",", a.seats.Select(Seating.Report))}]}}")) + "],");
            report.Append($"\"mode\":\"{s.mode}\",\"spp\":{spp},\"width\":{s.width},\"height\":{s.height},\"seconds\":{F((float)total.Elapsed.TotalSeconds)},\"gpu\":\"{SystemInfo.graphicsDeviceName}\"}}");
            File.WriteAllText(Path.Combine(s.outDir, Lib.Arg("-report", "report.json")), report.ToString());
            Debug.Log(chunked ? $"FID_CHUNK frames={jobs.Count} seconds={total.Elapsed.TotalSeconds:F1}" : $"FID_DONE frames={jobs.Count} seconds={total.Elapsed.TotalSeconds:F1}");
        }

        static string F(float v) => float.IsNaN(v) || float.IsInfinity(v) ? "0" : v.ToString("0.####", CultureInfo.InvariantCulture);

        // ---------------------------------------------------------------- lighting and look
        static void Environment(FilmSpec s, RoomInfo room)
        {
            var go = new GameObject("Volume");
            volume = go.AddComponent<Volume>(); volume.isGlobal = true;
            prof = ScriptableObject.CreateInstance<VolumeProfile>(); volume.sharedProfile = prof;
            var ve = prof.Add<VisualEnvironment>(true); ve.skyType.Override((int)SkyType.HDRI); ve.skyAmbientMode.Override(SkyAmbientMode.Dynamic);
            var hs = prof.Add<HDRISky>(true); hs.hdriSky.Override(Lib.HDRI(s.hdri)); hs.skyIntensityMode.Override(SkyIntensityMode.Lux);
            hs.desiredLuxValue.Override(s.skyLux); hs.rotation.Override(((s.skyRot % 360) + 360) % 360); hs.upperHemisphereOnly.Override(false);
            var dpl = prof.Add<DiffusionProfileList>(true);
            var skin = AssetDatabase.FindAssets("SkinDiffusionProfile t:DiffusionProfileSettings").Select(g => AssetDatabase.LoadAssetAtPath<DiffusionProfileSettings>(AssetDatabase.GUIDToAssetPath(g))).FirstOrDefault();
            if (skin) dpl.diffusionProfiles.Override(new[] { skin });
            exposure = prof.Add<Exposure>(true); exposure.mode.Override(ExposureMode.Fixed); exposure.fixedExposure.Override(10);
            var tm = prof.Add<Tonemapping>(true); tm.mode.Override(TonemappingMode.ACES);
            var bloom = prof.Add<Bloom>(true); bloom.intensity.Override(0.035f); bloom.scatter.Override(0.55f); bloom.threshold.Override(2.0f);
            var vig = prof.Add<Vignette>(true); vig.intensity.Override(0.22f); vig.smoothness.Override(0.5f);
            var wb = prof.Add<WhiteBalance>(true); wb.temperature.Override(4f);
            var ca = prof.Add<ColorAdjustments>(true); ca.contrast.Override(6f); ca.saturation.Override(-4f);
            var smh = prof.Add<ShadowsMidtonesHighlights>(true);
            smh.shadows.Override(new Vector4(0.96f, 1.0f, 1.06f, 0f)); smh.highlights.Override(new Vector4(1.05f, 1.0f, 0.94f, 0f));
            var dof = prof.Add<DepthOfField>(true); dof.focusMode.Override(DepthOfFieldMode.UsePhysicalCamera); dof.focusDistanceMode.Override(FocusDistanceMode.Camera);
            dof.quality.Override(2);
            var mb = prof.Add<MotionBlur>(true); mb.intensity.Override(s.mode == "pt" ? 0f : 0.5f);
            pt = prof.Add<PathTracing>(true);
            pt.enable.Override(s.mode == "pt"); pt.maximumSamples.Override(Mathf.Max(1, s.spp)); pt.maximumDepth.Override(s.maxDepth);
            pt.maximumIntensity.Override(6f);
            pt.denoising.Override(s.denoise == "oidn" ? HDDenoiserType.OpenImageDenoise : HDDenoiserType.None);
            pt.useAOVs.Override(true); pt.asyncDenoising.Override(false); pt.temporal.Override(false);
            pt.seedMode.Override(SeedMode.NonRepeating);
            if (s.fogMfp > 0)
            {
                var fog = prof.Add<Fog>(true);
                fog.enabled.Override(true); fog.enableVolumetricFog.Override(true); fog.meanFreePath.Override(s.fogMfp);
                fog.maximumHeight.Override(4f); fog.baseHeight.Override(0f); fog.albedo.Override(new Color(1f, 0.95f, 0.88f));
                fog.anisotropy.Override(0.6f); fog.colorMode.Override(FogColorMode.SkyColor);
                fog.depthExtent.Override(20f); fog.denoisingMode.Override(FogDenoisingMode.Both);
            }
            // Raster preview helpers (ignored by the path tracer).
            var ssgi = prof.Add<GlobalIllumination>(true); ssgi.enable.Override(true);
            var ssao = prof.Add<ScreenSpaceAmbientOcclusion>(true); ssao.intensity.Override(1.2f);
            var cs = prof.Add<ContactShadows>(true); cs.enable.Override(true); cs.length.Override(0.12f);
            var ssr = prof.Add<ScreenSpaceReflection>(true); ssr.enabled.Override(true);
            var ind = prof.Add<IndirectLightingController>(true); ind.indirectDiffuseLightingMultiplier.Override(1f);

            float el = s.sunElev * Mathf.Deg2Rad, az = s.sunAzim * Mathf.Deg2Rad;
            // Direction the light travels: azimuth is the compass direction the sun is IN (0 = +Z, 90 = +X).
            var toSun = new Vector3(Mathf.Sin(az) * Mathf.Cos(el), Mathf.Sin(el), Mathf.Cos(az) * Mathf.Cos(el));
            Lib.Sun(-toSun, s.sunLux, s.sunKelvin, s.sunAngle);
        }

        /// Dust motes drifting in the sunbeam (tiny lit spheres; they only show where the sun catches them).
        static GameObject dustRoot; static List<(Transform t, Vector3 p, Vector3 v, float ph)> motes = new List<(Transform, Vector3, Vector3, float)>();
        static void Dust(RoomInfo room, FilmSpec s)
        {
            dustRoot = new GameObject("Dust"); motes.Clear();
            var rng = new System.Random(7);
            var mat = Lib.Lit(new Color(0.9f, 0.85f, 0.78f), 0.2f);
            var L = room.layout;
            for (int i = 0; i < 420; i++)
            {
                var g = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                Object.DestroyImmediate(g.GetComponent<Collider>());
                g.transform.SetParent(dustRoot.transform);
                var p = new Vector3(Mathf.Lerp(L.window.x[0] - 0.6f, L.window.x[1] + 0.8f, (float)rng.NextDouble()), Mathf.Lerp(0.4f, 2.4f, (float)rng.NextDouble()), Mathf.Lerp(-0.5f, L.room.z[1] - 0.15f, (float)rng.NextDouble()));
                g.transform.position = p; g.transform.localScale = Vector3.one * Mathf.Lerp(0.0016f, 0.0035f, (float)rng.NextDouble());
                var r = g.GetComponent<Renderer>(); r.sharedMaterial = mat; r.shadowCastingMode = ShadowCastingMode.Off;
                motes.Add((g.transform, p, new Vector3((float)rng.NextDouble() - 0.5f, (float)rng.NextDouble() - 0.6f, (float)rng.NextDouble() - 0.5f) * 0.03f, (float)rng.NextDouble() * 10));
            }
        }

        static void DustAt(float t)
        {
            foreach (var m in motes)
                m.t.position = m.p + m.v * t + new Vector3(Mathf.Sin(t * 0.37f + m.ph), Mathf.Sin(t * 0.29f + m.ph * 1.3f), Mathf.Cos(t * 0.31f + m.ph * 0.7f)) * 0.04f;
        }

        // ---------------------------------------------------------------- camera
        static void PlaceCamera(Camera cam, Shot sh, float t)
        {
            float lt = t - sh.t0;
            var keys = sh.keys;
            Vector3 P(float[] a) => new Vector3(a[0], a[1], a[2]);
            Vector3 pos, look; float focal, focus, ap, roll;
            if (keys.Length == 1 || lt <= keys[0].t) { var k = keys[0]; pos = P(k.pos); look = P(k.look); focal = k.focal; focus = k.focus; ap = k.aperture; roll = k.roll; }
            else if (lt >= keys[keys.Length - 1].t) { var k = keys[keys.Length - 1]; pos = P(k.pos); look = P(k.look); focal = k.focal; focus = k.focus; ap = k.aperture; roll = k.roll; }
            else
            {
                int i = 0; while (i < keys.Length - 2 && lt > keys[i + 1].t) i++;
                var a = keys[i]; var b = keys[i + 1];
                float u = Mathf.Clamp01((lt - a.t) / Mathf.Max(1e-4f, b.t - a.t));
                if (sh.ease == "smooth") u = Mathf.Lerp(u, u * u * (3 - 2 * u), keys.Length == 2 ? 0.7f : 0.35f);
                var a0 = keys[Mathf.Max(0, i - 1)]; var b1 = keys[Mathf.Min(keys.Length - 1, i + 2)];
                pos = CR(P(a0.pos), P(a.pos), P(b.pos), P(b1.pos), u);
                look = CR(P(a0.look), P(a.look), P(b.look), P(b1.look), u);
                focal = Mathf.Lerp(a.focal, b.focal, u); ap = Mathf.Lerp(a.aperture, b.aperture, u); roll = Mathf.Lerp(a.roll, b.roll, u);
                float fa = a.focus > 0 ? a.focus : Vector3.Distance(P(a.pos), P(a.look));
                float fb = b.focus > 0 ? b.focus : Vector3.Distance(P(b.pos), P(b.look));
                focus = Mathf.Lerp(fa, fb, u * u * (3 - 2 * u));
            }
            if (focus <= 0) focus = Vector3.Distance(pos, look);
            var rot = Quaternion.LookRotation(look - pos, Vector3.up) * Quaternion.Euler(0, 0, roll);
            if (sh.handheld > 0)
            {
                float h = sh.handheld;
                rot *= Quaternion.Euler((Mathf.PerlinNoise(t * 0.45f, 3.1f) - 0.5f) * 0.9f * h, (Mathf.PerlinNoise(7.7f, t * 0.4f) - 0.5f) * 1.1f * h, (Mathf.PerlinNoise(t * 0.3f, 11f) - 0.5f) * 0.5f * h);
                pos += new Vector3(Mathf.PerlinNoise(t * 0.5f, 21f) - 0.5f, Mathf.PerlinNoise(31f, t * 0.5f) - 0.5f, 0) * 0.012f * h;
            }
            cam.transform.SetPositionAndRotation(pos, rot);
            cam.focalLength = focal; cam.aperture = ap; cam.focusDistance = focus;
            DustAt(t);
        }

        static Vector3 CR(Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3, float t)
        {
            float t2 = t * t, t3 = t2 * t;
            return 0.5f * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3);
        }

        // ---------------------------------------------------------------- actors (ported from DemoStudio ShotStudio)
        static Actor MakeActor(ActorSpec a, RoomInfo room)
        {
            var x = new Actor { spec = a, go = Characters.Spawn(a.model, Vector3.zero, 0, a.height) };
            x.anim = x.go.GetComponent<Animator>();
            x.anim.applyRootMotion = true;
            foreach (var ss in a.seats ?? new SeatSpec[0])
            {
                if (!room.furniture.TryGetValue(ss.furniture ?? "", out var fi)) throw new System.Exception($"actor {a.id}: unknown seat furniture {ss.furniture}");
                x.seats.Add(new SeatState { spec = ss, seat = fi });
            }
            foreach (var ps in a.props ?? new PropSpec[0]) x.props.Add(MakeProp(ps, x));
            foreach (var rs in a.reaches ?? new ReachSpec[0])
            {
                var piece = room.chess ? room.chess.GetComponentsInChildren<Transform>().FirstOrDefault(q => q.name == rs.piece) : null;
                if (piece == null) { Debug.LogWarning("FID_REACH no piece " + rs.piece); continue; }
                var to = piece.position + room.chess.transform.TransformVector(new Vector3(rs.move[0], rs.move[1], rs.move[2]));
                x.reaches.Add((rs, piece, piece.position, to));
            }
            x.go.transform.SetPositionAndRotation(V(a.pos), Quaternion.Euler(0, a.yaw, 0));
            if (a.grounding)
            {
                x.grounding = x.go.AddComponent<Promptimate.PromptimateGrounding>();
                x.grounding.Calibrate();
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

        static Vector3 V(float[] a) => a == null || a.Length < 3 ? Vector3.zero : new Vector3(a[0], a[1], a[2]);

        static AnimationClip LoadClip(string path)
        {
            var clip = AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().FirstOrDefault(c => !c.name.StartsWith("__preview"));
            if (clip == null)
            {
                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
                clip = AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().FirstOrDefault(c => !c.name.StartsWith("__preview"));
            }
            return clip ?? throw new System.Exception("missing clip " + path);
        }

        static void Reset(Actor x) { x.activeSeg = -2; x.lastT = 0; foreach (var p in x.props) p.dropped = false; }

        static void PoseAll(List<Actor> actors, float t)
        {
            foreach (var a in actors)
            {
                // The Animator re-applies its evaluated pose at render time, which would wipe out every edit made
                // after the graph evaluation (seat contact, arm IK, carry pose, grounding). Evaluate with it on, then
                // switch it off so the edited bones are what gets skinned.
                a.anim.enabled = true;
                PoseBody(a, t);
                HeadLevel(a);
                SeatXZ(a, t);
                foreach (var st in a.seats) Seating.Apply(st, a.anim, a.grounding, t, false);
                foreach (var p in a.props) PlaceProp(p, a, t);
                foreach (var r in a.reaches) Reach(a, r.spec, r.piece, r.from, r.to, t);
                Characters.ApplyBlink(a.go, Characters.Blink(t, a.spec.blinkSeed));
                if (System.Environment.GetEnvironmentVariable("FID_IKTEST") == "1")
                {
                    var ua = a.anim.GetBoneTransform(HumanBodyBones.RightUpperArm);
                    ua.rotation = Quaternion.AngleAxis(120, a.go.transform.right) * ua.rotation;
                }
                a.anim.enabled = false;
            }
        }

        static void Eval(Actor x, float dt)
        {
            var before = x.go.transform.position;
            x.graph.Evaluate(dt);
            if (Mathf.Abs(x.travelScale - 1) > 1e-4f)
            {
                var d = x.go.transform.position - before;
                x.go.transform.position = before + new Vector3(d.x * x.travelScale, d.y, d.z * x.travelScale);
            }
        }

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
            Debug.Log($"FID_TRAVEL {x.spec.id} metric={c[1]:F3} unity={d.magnitude:F3} scale={x.travelScale:F3}");
            x.go.transform.SetPositionAndRotation(V(x.spec.pos), Quaternion.Euler(0, x.spec.yaw, 0));
        }

        static void PoseBody(Actor x, float t)
        {
            var segs = x.spec.segs;
            if (segs == null || segs.Length == 0) return;
            if (x.seatOffset != Vector3.zero) { x.go.transform.position -= x.seatOffset; x.seatOffset = Vector3.zero; }
            if (t < x.lastT - 1e-5f) Reset(x);
            int k = 0;
            for (int i = 0; i < segs.Length; i++) if (t >= segs[i].start - 1e-4f) k = i;
            var s = segs[k];
            if (k != x.activeSeg)
            {
                if (x.activeSeg >= 0 && s.start > x.lastT) Eval(x, s.start - x.lastT);
                float ct = s.clipStart + Mathf.Max(0, t - s.start) * s.speed;
                for (int i = 0; i < segs.Length; i++)
                {
                    x.mixer.SetInputWeight(i, i == k ? 1 : 0);
                    if (i == k) x.clips[i].Play(); else x.clips[i].Pause();
                }
                if (x.activeSeg < 0 || s.place)
                    x.go.transform.SetPositionAndRotation(V(s.pos), Quaternion.Euler(0, s.yaw, 0));
                x.clips[k].SetSpeed(1);
                x.clips[k].SetTime(0);
                x.clips[k].SetTime(0);
                x.graph.Evaluate(0);
                if (ct > 1e-4f) Eval(x, ct);
                x.clips[k].SetSpeed(s.speed);
                x.activeSeg = k;
            }
            else Eval(x, Mathf.Max(0, t - x.lastT));
            x.lastT = t;
            if (x.grounding) x.grounding.Solve();
        }

        // ---------------------------------------------------------------- props
        static Prop MakeProp(PropSpec ps, Actor a)
        {
            var go = Lib.Model(ps.model, Vector3.zero, 0);
            if (!string.IsNullOrEmpty(ps.part))
                foreach (var r in go.GetComponentsInChildren<Renderer>()) if (!r.name.ToLowerInvariant().Contains(ps.part.ToLowerInvariant())) r.gameObject.SetActive(false);
            foreach (var r in go.GetComponentsInChildren<Renderer>()) r.rayTracingMode = UnityEngine.Experimental.Rendering.RayTracingMode.DynamicTransform;
            var b = Lib.WorldBounds(go);
            float longest = Mathf.Max(b.size.x, b.size.y, b.size.z);
            go.transform.localScale *= ps.size / Mathf.Max(1e-3f, longest);
            // Re-centre: a child holder whose origin is the handle (top centre of the visible bounds).
            b = Lib.WorldBounds(go);
            var holder = new GameObject("Prop_" + ps.model);
            holder.transform.position = new Vector3(b.center.x, b.max.y, b.center.z);
            go.transform.SetParent(holder.transform, true);
            var p = new Prop { spec = ps, go = holder, left = (ps.hand ?? "right").ToLower().StartsWith("l"), release = ps.release };
            p.grip = go.transform.localPosition; // unused (holder origin is the handle)
            foreach (var r in go.GetComponentsInChildren<Renderer>()) Debug.Log($"FID_PROP part {r.name} active={r.gameObject.activeInHierarchy}");
            return p;
        }

        static void PlaceProp(Prop p, Actor a, float t)
        {
            if (p.spec.carryUntil > 0 && t < p.spec.carryUntil + p.spec.carryBlend) CarryArm(a, p, t);
            var hand = a.anim.GetBoneTransform(p.left ? HumanBodyBones.LeftHand : HumanBodyBones.RightHand);
            var mid = a.anim.GetBoneTransform(p.left ? HumanBodyBones.LeftMiddleProximal : HumanBodyBones.RightMiddleProximal);
            var fwd = a.go.transform.forward; fwd.y = 0; fwd.Normalize();
            var rot = Quaternion.LookRotation(fwd, Vector3.up) * Quaternion.Euler(p.spec.rot[0], p.spec.rot[1], p.spec.rot[2]);
            if (t < p.release)
            {
                var palm = mid ? Vector3.Lerp(hand.position, mid.position, 0.85f) : hand.position;
                p.go.transform.SetPositionAndRotation(palm + Vector3.down * 0.015f, rot);
                p.dropped = false;
            }
            else if (!p.dropped)
            {
                // Put down: keep where it is horizontally, stand it on the floor upright.
                p.go.transform.rotation = rot;
                var b = Lib.WorldBounds(p.go);
                p.go.transform.position += Vector3.up * (0.0f - b.min.y);
                p.dropped = true;
            }
        }

        /// Humanoid root motion follows the centre of mass, which sits well in front of the pelvis when seated, so a
        /// clip that sits exactly on its seat in the motion data lands ~0.3 m short of the chair in Unity. While sitting
        /// down and seated, the body is eased horizontally so the pelvis is over the back half of the seat. Non-
        /// cumulative: removed again before the next root-motion step.
        static void SeatXZ(Actor a, float t)
        {
            float best = 0; SeatState bs = null;
            foreach (var st in a.seats)
            {
                var s = st.spec; float pre = 1.1f, post = 0.6f, w;
                if (t < s.start - pre || t > s.end + post) continue;
                w = t < s.start ? Smooth((t - (s.start - pre)) / pre) : t > s.end ? Smooth(1 - (t - s.end) / post) : 1;
                if (w > best) { best = w; bs = st; }
            }
            if (bs == null || best <= 1e-4f) return;
            var hips = a.anim.GetBoneTransform(HumanBodyBones.Hips).position;
            var fwd = bs.seat.go.transform.forward; fwd.y = 0; fwd.Normalize();
            var target = bs.seat.seatCenter - fwd * 0.1f;
            var off = target - hips; off.y = 0; off *= best;
            a.go.transform.position += off; a.seatOffset = off;
        }

        static float Smooth(float x) { x = Mathf.Clamp01(x); return x * x * (3 - 2 * x); }

        /// The Rocketbox rigs come out of Humanoid retargeting with the head pitched ~20 deg up (chin raised in every
        /// clip, "looks down" reads as looking at the ceiling); tip the neck and head back down.
        static void HeadLevel(Actor a)
        {
            float deg = a.spec.headPitch;
            if (Mathf.Abs(deg) < 0.01f) return;
            var axis = a.go.transform.right;
            var hips = a.anim.GetBoneTransform(HumanBodyBones.Hips);
            var head = a.anim.GetBoneTransform(HumanBodyBones.Head);
            var fwd = hips.forward; // rig-dependent; use the body's facing from the shoulders instead
            var ls = a.anim.GetBoneTransform(HumanBodyBones.LeftUpperArm); var rs = a.anim.GetBoneTransform(HumanBodyBones.RightUpperArm);
            if (ls && rs) axis = (ls.position - rs.position).normalized; // character's left: rotating about it tips the head forward
            var neck = a.anim.GetBoneTransform(HumanBodyBones.Neck);
            if (neck) neck.rotation = Quaternion.AngleAxis(-deg * 0.45f, axis) * neck.rotation;
            if (head) head.rotation = Quaternion.AngleAxis(-deg * 0.55f, axis) * head.rotation;
        }

        static float lastReachLog = -10;
        static void Reach(Actor a, ReachSpec r, Transform piece, Vector3 from, Vector3 to, float t)
        {
            float s = Smooth((t - r.grab) / Mathf.Max(0.05f, r.place - r.grab));
            piece.position = Vector3.Lerp(from, to, s) + Vector3.up * (0.045f * Mathf.Sin(Mathf.PI * s));
            float w = t < r.grab ? Smooth(1 - (r.grab - t) / r.blend) : t > r.place ? Smooth(1 - (t - r.place) / r.blend) : 1;
            if (w <= 1e-4f) return;
            bool left = (r.hand ?? "right").ToLower().StartsWith("l");
            var up = a.anim.GetBoneTransform(left ? HumanBodyBones.LeftUpperArm : HumanBodyBones.RightUpperArm);
            var lo = a.anim.GetBoneTransform(left ? HumanBodyBones.LeftLowerArm : HumanBodyBones.RightLowerArm);
            var hand = a.anim.GetBoneTransform(left ? HumanBodyBones.LeftHand : HumanBodyBones.RightHand);
            var idx = a.anim.GetBoneTransform(left ? HumanBodyBones.LeftIndexDistal : HumanBodyBones.RightIndexDistal);
            var thb = a.anim.GetBoneTransform(left ? HumanBodyBones.LeftThumbDistal : HumanBodyBones.RightThumbDistal);
            // Pinch point between index and thumb tips goes to the top of the piece.
            var pinch = idx && thb ? (idx.position + thb.position) * 0.5f : hand.position + hand.up * 0.08f;
            var top = piece.position + Vector3.up * 0.05f;
            // Lean the upper body toward the board first (people lean in to move a piece), then solve the arm.
            var fwd = top - a.anim.GetBoneTransform(HumanBodyBones.Hips).position; fwd.y = 0; fwd.Normalize();
            var axis = Vector3.Cross(Vector3.up, fwd);
            foreach (var b in new[] { HumanBodyBones.Spine, HumanBodyBones.Chest, HumanBodyBones.UpperChest })
            {
                var bt = a.anim.GetBoneTransform(b);
                if (bt) bt.rotation = Quaternion.AngleAxis(13f * w, axis) * bt.rotation;
            }
            var q = hand.rotation;
            var pinch0 = idx && thb ? (idx.position + thb.position) * 0.5f : hand.position + hand.up * 0.08f;
            // Hand palm-down over the piece, fingers pointing at it and tipped down: measured from the bones (the
            // rig's local axes vary), as a rotation taking the current finger/palm frame to the wanted one.
            var midP = a.anim.GetBoneTransform(left ? HumanBodyBones.LeftMiddleProximal : HumanBodyBones.RightMiddleProximal);
            var idxP = a.anim.GetBoneTransform(left ? HumanBodyBones.LeftIndexProximal : HumanBodyBones.RightIndexProximal);
            var litP = a.anim.GetBoneTransform(left ? HumanBodyBones.LeftLittleProximal : HumanBodyBones.RightLittleProximal);
            Quaternion want = q;
            if (midP && idxP && litP)
            {
                var f = (midP.position - hand.position).normalized;
                var acr = (idxP.position - litP.position).normalized;
                var n = Vector3.Cross(f, acr).normalized * (left ? -1 : 1); // out of the palm
                var df = (fwd * 0.9f + Vector3.down * 0.42f).normalized;
                var dn = Vector3.ProjectOnPlane(Vector3.down, df).normalized;
                var cur = Quaternion.LookRotation(f, n); var dst = Quaternion.LookRotation(df, dn);
                want = Quaternion.Slerp(q, dst * Quaternion.Inverse(cur) * q, w);
            }
            hand.rotation = want;
            pinch = idx && thb ? (idx.position + thb.position) * 0.5f : hand.position + hand.up * 0.08f;
            var target = Vector3.Lerp(pinch0, top, w) - (pinch - hand.position);
            Seating.TwoBoneArm(up, lo, hand, target);
            hand.rotation = want;
            if (Mathf.Abs(t - lastReachLog) > 0.2f)
            {
                lastReachLog = t;
                var pinch2 = (idx && thb) ? (idx.position + thb.position) * 0.5f : hand.position;
                Debug.Log($"FID_REACH t={t:F2} w={w:F2} miss={Vector3.Distance(pinch2, top) * 100:F1}cm top={top} pinchBefore={pinch} hand={hand.position} shoulder={up.position} reach={Vector3.Distance(up.position, top):F2} arm={(Vector3.Distance(up.position, lo.position) + Vector3.Distance(lo.position, hand.position)):F2}");
            }
        }

        /// Arm hanging straight down from the shoulder, a little out from the body and behind the hip (a heavy case).
        static void CarryArm(Actor a, Prop p, float t)
        {
            float w = t <= p.spec.carryUntil ? 1 : Smooth(1 - (t - p.spec.carryUntil) / p.spec.carryBlend);
            if (w <= 1e-4f) return;
            var up = a.anim.GetBoneTransform(p.left ? HumanBodyBones.LeftUpperArm : HumanBodyBones.RightUpperArm);
            var lo = a.anim.GetBoneTransform(p.left ? HumanBodyBones.LeftLowerArm : HumanBodyBones.RightLowerArm);
            var hand = a.anim.GetBoneTransform(p.left ? HumanBodyBones.LeftHand : HumanBodyBones.RightHand);
            var hips = a.anim.GetBoneTransform(HumanBodyBones.Hips);
            var side = (up.position - hips.position); side.y = 0; side = side.normalized;
            var fwd = a.go.transform.forward; fwd.y = 0; fwd.Normalize();
            float sway = Mathf.Sin(t * 5.6f) * 0.03f; // a little swing with the steps
            var dir = (Vector3.down + side * 0.16f + fwd * (sway - 0.03f)).normalized;
            var cur = lo.position - up.position;
            up.rotation = Quaternion.Slerp(Quaternion.identity, Quaternion.FromToRotation(cur, dir), w) * up.rotation;
            var cur2 = hand.position - lo.position;
            var dir2 = (dir + fwd * 0.08f).normalized;
            lo.rotation = Quaternion.Slerp(Quaternion.identity, Quaternion.FromToRotation(cur2, dir2), w) * lo.rotation;
            // Hand in line with the forearm, palm facing the leg.
            var hq = Quaternion.LookRotation(fwd, -dir2);
            hand.rotation = Quaternion.Slerp(hand.rotation, Quaternion.FromToRotation(hand.rotation * Vector3.up, -dir2) * hand.rotation, w * 0.5f);
        }

        // ---------------------------------------------------------------- set check
        static void LayoutCheck(FilmSpec s, Camera cam, RenderTexture rt, RoomInfo room, List<Actor> actors)
        {
            exposure.fixedExposure.Override(s.shots.Length > 0 ? s.shots[0].ev : 9.5f);
            var views = new List<(string name, Vector3 pos, Vector3 look, float focal)>
            {
                ("top", new Vector3(0, 9.5f, 0.0f), new Vector3(0, 0, 0.01f), 18),
                ("from_door", new Vector3(-1.2f, 1.6f, -2.5f), new Vector3(0.3f, 1.0f, 1.8f), 22),
                ("to_door", new Vector3(0.6f, 1.55f, 2.4f), new Vector3(-1.4f, 1.1f, -2.6f), 22),
                ("east", new Vector3(2.8f, 1.6f, -2.4f), new Vector3(-0.6f, 0.9f, 1.4f), 20),
                ("west", new Vector3(-2.9f, 1.6f, -2.4f), new Vector3(1.4f, 0.9f, 1.6f), 20),
            };
            foreach (var sh in s.shots)
                if (sh.keys.Length > 0) views.Add(("cam_" + sh.id, new Vector3(sh.keys[0].pos[0], sh.keys[0].pos[1], sh.keys[0].pos[2]), new Vector3(sh.keys[0].look[0], sh.keys[0].look[1], sh.keys[0].look[2]), sh.keys[0].focal));
            float t = s.frames != null && s.frames.Length > 0 ? s.frames[0] : 0;
            PoseAll(actors, t);
            var hdrp = RenderPipelineManager.currentPipeline as HDRenderPipeline;
            int spp = s.mode == "pt" ? Mathf.Max(1, s.spp) : 1;
            foreach (var v in views)
            {
                cam.transform.SetPositionAndRotation(v.pos, Quaternion.LookRotation(v.look - v.pos, v.name == "top" ? Vector3.forward : Vector3.up));
                cam.focalLength = v.focal; cam.aperture = 16; cam.focusDistance = Vector3.Distance(v.pos, v.look);
                var shv = s.shots.FirstOrDefault(q => "cam_" + q.id == v.name);
                exposure.fixedExposure.Override(shv != null ? shv.ev : (s.shots.Length > 0 ? s.shots[0].ev : 9.5f));
                if (s.mode == "pt")
                {
                    pt.maximumSamples.Override(spp);
                    hdrp.BeginRecording(spp, 0);
                    for (int k = 0; k < spp; k++) { hdrp.PrepareNewSubFrame(); cam.Render(); }
                    hdrp.EndRecording();
                }
                else for (int k = 0; k < 8; k++) cam.Render();
                Lib.SavePng(rt, Path.Combine(s.outDir, "layout_" + v.name + ".png"));
            }
            Debug.Log("FID_LAYOUT done");
        }
    }
}
