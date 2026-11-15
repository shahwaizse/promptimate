// Headless world renderer (URP): WorldJob JSON in, stills + camera-move frames + report.json out.
//   Unity.exe -batchmode -projectPath unity/WorldLab -executeMethod WorldLab.WorldRenderer.Run -world <job.json>
// WorldServer keeps one editor warm and runs world jobs and character shots (ShotStudio) from a queue.
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace WorldLab
{
    public static class WorldRenderer
    {
        static readonly CultureInfo IC = CultureInfo.InvariantCulture;
        static string F(float v) => float.IsNaN(v) || float.IsInfinity(v) ? "null" : v.ToString("0.####", IC);
        static string Vv(Vector3 v) => $"[{F(v.x)},{F(v.y)},{F(v.z)}]";

        public static void Run()
        {
            var a = System.Environment.GetCommandLineArgs();
            int i = System.Array.IndexOf(a, "-world");
            int code = 0;
            try { Dispatch(File.ReadAllText(a[i + 1])); }
            catch (System.Exception e) { Debug.LogError("WORLD_ERROR " + e); code = 1; }
            EditorApplication.Exit(code);
        }

        public static void Dispatch(string json)
        {
            var job = JsonUtility.FromJson<WorldJob>(json);
            if (job.kind == "measure") Measure(job);
            else Render(job);
        }

        /// The world for a character shot (ShotStudio): built without its own camera/post (the shot renderer owns those).
        public static (BuiltWorld world, EffectsRig fx, LightRig rig) BuildForShot(string path)
        {
            var job = JsonUtility.FromJson<WorldJob>(File.ReadAllText(path));
            var w = WorldBuilder.Build(job);
            var fx = WorldEffects.Apply(job, w);
            var rig = WorldLighting.Apply(job, w, fx);
            fx.Prewarm();
            rig.probe.RenderProbe();
            return (w, fx, rig);
        }

        public static void Render(WorldJob job)
        {
            var sw = System.Diagnostics.Stopwatch.StartNew();
            var timing = new StringBuilder();
            void Mark(string what) => timing.Append($"\"{what}\":{sw.Elapsed.TotalSeconds:F2},");
            ShotStudio.Pipeline.Ensure();
            ShotStudio.Materials.Reset();
            ShaderUtil.allowAsyncCompilation = false;
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Mark("setup");
            var w = WorldBuilder.Build(job);
            Mark("build");
            var fx = WorldEffects.Apply(job, w);
            var rig = WorldLighting.Apply(job, w, fx);
            fx.Prewarm();
            Mark("light");

            var camGo = new GameObject("WorldCam");
            var cam = camGo.AddComponent<Camera>();
            cam.nearClipPlane = 0.03f; cam.farClipPlane = 600; cam.allowHDR = true; cam.allowMSAA = true;
            cam.clearFlags = RenderSettings.skybox ? CameraClearFlags.Skybox : CameraClearFlags.SolidColor;
            cam.backgroundColor = WorldBuilder.C(job.env?.skyColor, Color.black);
            var data = camGo.AddComponent<UniversalAdditionalCameraData>();
            data.renderPostProcessing = true; data.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            data.antialiasingQuality = AntialiasingQuality.High; data.renderShadows = true; data.requiresDepthTexture = true;
            float ss = Mathf.Clamp(job.supersample, 1, 2);
            int W = Mathf.RoundToInt(job.width * ss), H = Mathf.RoundToInt(job.height * ss);
            var rt = new RenderTexture(W, H, 24, RenderTextureFormat.ARGBHalf) { antiAliasing = 4, name = "world_rt" }; rt.Create();
            var outRt = new RenderTexture(job.width, job.height, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB); outRt.Create();
            cam.targetTexture = rt;
            var tex = new Texture2D(job.width, job.height, TextureFormat.RGB24, false);
            Directory.CreateDirectory(job.outDir);
            foreach (var f in Directory.GetFiles(job.outDir, "*.*").Where(f => f.EndsWith(".png") || f.EndsWith(".jpg"))) File.Delete(f);

            // Reflection probe once, from the room centre, with the room's own lights.
            rig.probe.RenderProbe();
            var pending = new List<System.Threading.Tasks.Task>();
            var camReport = new StringBuilder("[");
            void Shoot(Vector3 p, Vector3 look, float fov, string file, bool jpg, string name)
            {
                cam.transform.position = p;
                cam.transform.rotation = Quaternion.LookRotation((look - p).normalized, Vector3.up);
                cam.fieldOfView = fov;
                WorldBuilder.Cull(w, p);
                WorldLighting.Focus(rig, Vector3.Distance(p, look), fov, job.post?.dof ?? 0);
                cam.Render();
                Graphics.Blit(rt, outRt);
                RenderTexture.active = outRt;
                tex.ReadPixels(new Rect(0, 0, job.width, job.height), 0, 0);
                RenderTexture.active = null;
                var raw = tex.GetRawTextureData<byte>().ToArray();
                int w0 = job.width, h0 = job.height;
                while (pending.Count(x => !x.IsCompleted) > 6) pending.First(x => !x.IsCompleted).Wait();
                pending.Add(System.Threading.Tasks.Task.Run(() =>
                {
                    var bytes = jpg ? ImageConversion.EncodeArrayToJPG(raw, UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8B8_SRGB, (uint)w0, (uint)h0, 0, 94)
                                    : ImageConversion.EncodeArrayToPNG(raw, UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8B8_SRGB, (uint)w0, (uint)h0);
                    File.WriteAllBytes(file, bytes);
                }));
                if (name != null)
                {
                    // Is the camera inside the room and outside every model? (validation)
                    bool inside = w.roomBounds.Contains(p);
                    string inItem = w.items.Values.Where(x => x.go && x.bounds.Contains(p)).Select(x => x.spec.id).FirstOrDefault() ?? "";
                    camReport.Append(camReport.Length > 1 ? "," : "").Append($"{{\"name\":\"{name}\",\"pos\":{Vv(p)},\"look\":{Vv(look)},\"fov\":{F(fov)},\"insideRoom\":{(inside ? "true" : "false")},\"insideItem\":\"{inItem}\"}}");
                }
            }
            // Warm-up renders (shader variants, shadow maps).
            if (job.stills.Length > 0) for (int k = 0; k < 3; k++) { cam.transform.position = WorldBuilder.V(job.stills[0].pos); cam.transform.LookAt(WorldBuilder.V(job.stills[0].look)); cam.Render(); }
            foreach (var s in job.stills)
            {
                // effects time for this still (lightning flash, smoke shape)
                float dtS = Mathf.Max(0, s.t - fx.t);
                while (dtS > 1e-4f) { float st = Mathf.Min(1 / 30f, dtS); fx.Step(st); dtS -= st; }
                Shoot(WorldBuilder.V(s.pos), WorldBuilder.V(s.look), s.fov, Path.Combine(job.outDir, s.name + ".png"), false, s.name);
            }
            Mark("stills");
            int frames = 0;
            var mv = job.move;
            if (mv != null && mv.seconds > 0 && mv.pos0 != null && mv.pos0.Length >= 3)
            {
                frames = Mathf.Max(1, Mathf.RoundToInt(mv.seconds * mv.fps));
                fx.t = 0;
                for (int f = 0; f < frames; f++)
                {
                    if (f > 0) fx.Step(1f / mv.fps);
                    float u = frames > 1 ? f / (float)(frames - 1) : 0;
                    float e = u * u * (3 - 2 * u); // ease in/out
                    var p = Vector3.Lerp(WorldBuilder.V(mv.pos0), WorldBuilder.V(mv.pos1), e);
                    var look = Vector3.Lerp(WorldBuilder.V(mv.look0), WorldBuilder.V(mv.look1), e);
                    Shoot(p, look, Mathf.Lerp(mv.fov0, mv.fov1, e), Path.Combine(job.outDir, $"f{f:D5}.jpg"), true, f == 0 ? "move_start" : f == frames - 1 ? "move_end" : null);
                }
            }
            System.Threading.Tasks.Task.WaitAll(pending.ToArray());
            Mark("move");
            var lights = string.Join(",", rig.lights.Select(l => $"{{\"name\":\"{l.name}\",\"type\":\"{l.type}\",\"pos\":{Vv(l.transform.position)},\"intensity\":{F(l.intensity)},\"color\":[{F(l.color.r)},{F(l.color.g)},{F(l.color.b)}],\"range\":{F(l.range)}}}"));
            var report = $"{{\"id\":\"{job.id}\",\"items\":{WorldBuilder.Report(w)},\"lights\":[{lights}],\"cameras\":{camReport}],\"frames\":{frames},\"fps\":{mv?.fps ?? 30}," +
                         $"\"room\":{{\"min\":{Vv(w.roomBounds.min)},\"max\":{Vv(w.roomBounds.max)}}},\"timing\":{{{timing.ToString().TrimEnd(',')}}},\"unity\":\"{Application.unityVersion}\"}}";
            File.WriteAllText(Path.Combine(job.outDir, "report.json"), report);
            cam.targetTexture = null; rt.Release(); outRt.Release(); Object.DestroyImmediate(tex);
            Debug.Log($"WORLD_DONE id={job.id} stills={job.stills.Length} frames={frames} seconds={sw.Elapsed.TotalSeconds:F1}");
        }

        /// Measures every library model (size at yaw 0 after its size rule and front correction) and optionally renders
        /// a front-view lineup, so the solver lays out real sizes and model fronts can be checked.
        public static void Measure(WorldJob job)
        {
            ShotStudio.Pipeline.Ensure();
            ShotStudio.Materials.Reset();
            ShaderUtil.allowAsyncCompilation = false;
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Directory.CreateDirectory(job.outDir);
            var root = new GameObject("Measure").transform;
            var sb = new StringBuilder("{");
            var placed = new List<(GameObject go, Bounds b, string id)>();
            foreach (var it in job.items)
            {
                string entry;
                try
                {
                    it.yaw = 0;
                    var go = WorldBuilder.Spawn(it, root);
                    var b = WorldBuilder.Bounds(go);
                    var lift = new Vector3(-b.center.x, -b.min.y, -b.center.z);
                    go.transform.position += lift;
                    entry = $"\"{it.asset}\":{{\"size\":{Vv(b.size)},\"ok\":true,\"pivotToBottomCenter\":{Vv(lift)}}}";
                    placed.Add((go, WorldBuilder.Bounds(go), it.asset));
                }
                catch (System.Exception e) { entry = $"\"{it.asset}\":{{\"ok\":false,\"error\":\"{e.Message.Replace("\"", "'").Replace("\\", "/")}\"}}"; }
                sb.Append(sb.Length > 1 ? "," : "").Append(entry);
            }
            File.WriteAllText(Path.Combine(job.outDir, "sizes.json"), sb.Append("}").ToString());
            // HDRI radiance (mean and the band around the horizon that windows mostly show), for exposure matching.
            var hs = new StringBuilder("{");
            foreach (var hp in job.hdris ?? new string[0])
            {
                var t = AssetDatabase.LoadAssetAtPath<Texture>(hp);
                if (!t) continue;
                var hrt = RenderTexture.GetTemporary(128, 64, 0, RenderTextureFormat.ARGBFloat, RenderTextureReadWrite.Linear);
                Graphics.Blit(t, hrt);
                var tx = new Texture2D(128, 64, TextureFormat.RGBAFloat, false, true);
                RenderTexture.active = hrt; tx.ReadPixels(new Rect(0, 0, 128, 64), 0, 0); RenderTexture.active = null;
                RenderTexture.ReleaseTemporary(hrt);
                var px = tx.GetPixels();
                double sum = 0, band = 0; int nb = 0;
                for (int y = 0; y < 64; y++)
                    for (int x = 0; x < 128; x++)
                    {
                        var c = px[y * 128 + x];
                        float l = 0.2126f * c.r + 0.7152f * c.g + 0.0722f * c.b;
                        float w0 = Mathf.Cos(((y + 0.5f) / 64f - 0.5f) * Mathf.PI); // solid-angle weight
                        sum += l * w0;
                        if (Mathf.Abs(y - 31.5f) <= 7) { band += l; nb++; }
                    }
                double wsum = 0; for (int y = 0; y < 64; y++) wsum += 128 * Mathf.Cos(((y + 0.5f) / 64f - 0.5f) * Mathf.PI);
                Object.DestroyImmediate(tx);
                hs.Append(hs.Length > 1 ? "," : "").Append($"\"{hp}\":{{\"mean\":{F((float)(sum / wsum))},\"horizon\":{F((float)(band / Mathf.Max(1, nb)))}}}");
            }
            File.WriteAllText(Path.Combine(job.outDir, "hdri.json"), hs.Append("}").ToString());
            if (job.lineup && placed.Count > 0)
            {
                // Rows of up to 8 models, fronts toward +Z, camera on the +Z side: a correct model shows its front.
                var key = new GameObject("Key").AddComponent<Light>(); key.type = LightType.Directional; key.intensity = 1.6f; key.transform.rotation = Quaternion.Euler(35, 200, 0); key.shadows = LightShadows.Soft;
                RenderSettings.ambientMode = AmbientMode.Flat; RenderSettings.ambientLight = new Color(0.45f, 0.45f, 0.48f);
                var floor = WorldBuilder.Box("Floor", new Vector3(0, -0.05f, 0), new Vector3(200, 0.1f, 200), Quaternion.identity, ShotStudio.Materials.Make(new Color(0.35f, 0.36f, 0.38f), null, 0.2f), 1, root);
                var cam = new GameObject("Cam").AddComponent<Camera>(); cam.clearFlags = CameraClearFlags.SolidColor; cam.backgroundColor = new Color(0.16f, 0.17f, 0.2f);
                cam.gameObject.AddComponent<UniversalAdditionalCameraData>().renderPostProcessing = false;
                var rt = new RenderTexture(1920, 1080, 24) { antiAliasing = 4 }; cam.targetTexture = rt;
                var tex = new Texture2D(1920, 1080, TextureFormat.RGB24, false);
                int page = 0;
                for (int s = 0; s < placed.Count; s += 8, page++)
                {
                    var batch = placed.Skip(s).Take(8).ToList();
                    foreach (var p in placed) p.go.SetActive(false);
                    float x = 0; float maxH = 0.3f;
                    foreach (var p in batch)
                    {
                        p.go.SetActive(true);
                        float wdt = Mathf.Max(0.3f, p.b.size.x);
                        p.go.transform.position = new Vector3(x + wdt / 2 - p.b.center.x + p.go.transform.position.x, p.go.transform.position.y, -p.b.center.z + p.go.transform.position.z);
                        x += wdt + 0.35f; maxH = Mathf.Max(maxH, p.b.size.y);
                    }
                    float cx = x / 2, span = Mathf.Max(x, maxH * 1.9f);
                    cam.fieldOfView = 30;
                    float dist = span * 0.5f / Mathf.Tan(15 * Mathf.Deg2Rad * 1.778f) + 1.5f;
                    cam.transform.position = new Vector3(cx, maxH * 0.6f + 0.4f, dist);
                    cam.transform.LookAt(new Vector3(cx, maxH * 0.4f, 0));
                    cam.Render(); cam.Render();
                    RenderTexture.active = rt; tex.ReadPixels(new Rect(0, 0, 1920, 1080), 0, 0); RenderTexture.active = null;
                    File.WriteAllBytes(Path.Combine(job.outDir, $"lineup_{page:D2}.jpg"), tex.EncodeToJPG(90));
                    File.WriteAllText(Path.Combine(job.outDir, $"lineup_{page:D2}.txt"), string.Join(" | ", batch.Select(b => b.id)));
                }
            }
            Debug.Log($"WORLD_MEASURED {job.items.Length}");
        }
    }
}
