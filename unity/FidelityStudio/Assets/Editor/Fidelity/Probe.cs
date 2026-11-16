// Capability probe: renders a small test set rasterised and path traced and logs timings.
//   Unity.exe -batchmode -force-d3d12 -projectPath unity/FidelityStudio -executeMethod Fidelity.Probe.Run -out <dir>
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

namespace Fidelity
{
    public static class Probe
    {
        public static void Run()
        {
            int code = 0;
            try { Do(); }
            catch (System.Exception e) { Debug.LogError("FID_ERROR " + e); code = 1; }
            EditorApplication.Exit(code);
        }

        public static void Reimport()
        {
            var guids = AssetDatabase.FindAssets("", new[] { "Assets/ThirdParty" });
            AssetDatabase.StartAssetEditing();
            try
            {
                foreach (var g in guids)
                {
                    var p = AssetDatabase.GUIDToAssetPath(g);
                    var ext = Path.GetExtension(p).ToLowerInvariant();
                    if (ext == ".jpg" || ext == ".png" || ext == ".tga" || ext == ".fbx") AssetDatabase.ImportAsset(p, ImportAssetOptions.ForceUpdate);
                }
            }
            finally { AssetDatabase.StopAssetEditing(); }
        }

        static void Do()
        {
            string outDir = Lib.Arg("-out", Path.Combine(Lib.Root, "logs", "fid", "probe"));
            Directory.CreateDirectory(outDir);
            Setup.Project();
            Setup.Ensure();
            if (Lib.Arg("-reimport") == "1") Reimport();
            ShaderUtil.allowAsyncCompilation = false;
            Debug.Log($"FID_PROBE device={SystemInfo.graphicsDeviceType} rt={SystemInfo.supportsRayTracing} gpu={SystemInfo.graphicsDeviceName} vram={SystemInfo.graphicsMemorySize}");
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            var floor = Lib.Box("Floor", new Vector3(0, -0.05f, 0), new Vector3(8, 0.1f, 8), Lib.Surface("rectangular_parquet"), null, 1.5f);
            Lib.Box("Wall", new Vector3(0, 1.4f, 2.0f), new Vector3(8, 2.8f, 0.1f), Lib.Surface("plastered_wall_04"), null, 2f);
            var ball = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            ball.transform.position = new Vector3(1.4f, 0.35f, 0.3f); ball.transform.localScale = Vector3.one * 0.7f;
            ball.GetComponent<Renderer>().sharedMaterial = Lib.Lit(new Color(0.9f, 0.9f, 0.9f), 0.95f, 1f);
            Lib.Model("ArmChair_01", new Vector3(-1.4f, 0, 0.8f), 160);
            Lib.Model("round_wooden_table_01", new Vector3(0.4f, 0, 0.6f), 0, null, 0.68f);
            Lib.Model("chess_set", new Vector3(0.4f, 0.68f, 0.6f), 10);

            var ch = Characters.Spawn("Male_Adult_03", new Vector3(-0.3f, 0, 0.0f), 200, 1.78f);
            foreach (var smr in ch.GetComponentsInChildren<SkinnedMeshRenderer>())
                Debug.Log($"FID_SMR {smr.name} verts={smr.sharedMesh.vertexCount} blend={smr.sharedMesh.blendShapeCount} mats=" + string.Join("|", smr.sharedMaterials.Select(m => m ? m.name + ":" + m.shader.name : "null")));

            var sky = Lib.HDRI("ehingen_hillside_4k.hdr");
            var volGo = new GameObject("Volume");
            var vol = volGo.AddComponent<Volume>(); vol.isGlobal = true;
            var prof = ScriptableObject.CreateInstance<VolumeProfile>(); vol.sharedProfile = prof;
            var ve = Lib.Add<VisualEnvironment>(prof); ve.skyType.Override((int)SkyType.HDRI); ve.skyAmbientMode.Override(SkyAmbientMode.Dynamic);
            var hs = Lib.Add<HDRISky>(prof); hs.hdriSky.Override(sky); hs.skyIntensityMode.Override(SkyIntensityMode.Lux); hs.desiredLuxValue.Override(12000); hs.rotation.Override(0);
            var dpl = Lib.Add<DiffusionProfileList>(prof);
            var skin = AssetDatabase.FindAssets("SkinDiffusionProfile t:DiffusionProfileSettings").Select(g => AssetDatabase.LoadAssetAtPath<DiffusionProfileSettings>(AssetDatabase.GUIDToAssetPath(g))).FirstOrDefault();
            Debug.Log("FID_SKIN " + (skin ? AssetDatabase.GetAssetPath(skin) : "none"));
            if (skin) dpl.diffusionProfiles.Override(new[] { skin });
            var ex = Lib.Add<Exposure>(prof); ex.mode.Override(ExposureMode.Fixed); ex.fixedExposure.Override(11.5f);
            var tm = Lib.Add<Tonemapping>(prof); tm.mode.Override(TonemappingMode.ACES);
            var pt = Lib.Add<PathTracing>(prof); pt.enable.Override(false); pt.maximumSamples.Override(64); pt.maximumDepth.Override(6);
            pt.asyncDenoising.Override(false);
            Lib.Sun(new Vector3(-0.4f, -0.35f, 1f), 30000, 4200);

            var camGo = new GameObject("Cam");
            var cam = camGo.AddComponent<Camera>();
            var hd = camGo.AddComponent<HDAdditionalCameraData>();
            hd.antialiasing = HDAdditionalCameraData.AntialiasingMode.TemporalAntialiasing;
            cam.fieldOfView = 40; cam.nearClipPlane = 0.05f; cam.farClipPlane = 200;
            camGo.transform.position = new Vector3(0.2f, 1.45f, -3.2f);
            camGo.transform.LookAt(new Vector3(0, 0.95f, 0.4f));
            var rt = Lib.Target(1280, 720);
            cam.targetTexture = rt;

            var sw = System.Diagnostics.Stopwatch.StartNew();
            for (int i = 0; i < 8; i++) cam.Render();
            Debug.Log($"FID_TIME raster_warm8={sw.Elapsed.TotalSeconds:F2}");
            sw.Restart();
            for (int i = 0; i < 16; i++) cam.Render();
            Debug.Log($"FID_TIME raster_16={sw.Elapsed.TotalSeconds:F2}");
            Lib.SavePng(rt, Path.Combine(outDir, "raster.png"));

            if (!SystemInfo.supportsRayTracing) { Debug.LogError("FID_PROBE no ray tracing"); return; }
            pt.enable.Override(true);
            var hdrp = RenderPipelineManager.currentPipeline as HDRenderPipeline;
            foreach (var (spp, den) in new[] { (16, HDDenoiserType.None), (64, HDDenoiserType.None), (32, HDDenoiserType.OpenImageDenoise) })
            {
                pt.denoising.Override(den);
                pt.maximumSamples.Override(spp);
                hdrp.BeginRecording(spp, 0f);
                sw.Restart();
                for (int s = 0; s < spp; s++) { hdrp.PrepareNewSubFrame(); cam.Render(); }
                Debug.Log($"FID_TIME pt spp={spp} den={den} total={sw.Elapsed.TotalSeconds:F2}");
                Lib.SavePng(rt, Path.Combine(outDir, $"pt_{spp}_{den}.png"));
                hdrp.EndRecording();
            }
            Debug.Log("FID_PROBE done");
        }
    }
}
