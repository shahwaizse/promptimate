// Headless shot renderer for marketing/demo footage.
//   Unity.exe -batchmode -projectPath DemoStudio -executeMethod DemoRenderer.Run -shot <shot.json> -quit
// (no -nographics: we need the GPU). Builds a scene from JSON, samples Humanoid clips per frame, renders PNGs.
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Animations;
using UnityEngine.Playables;

public static class DemoRenderer
{
    [System.Serializable] public class Cam
    {
        public float[] pos = { 0, 1.6f, -6 };
        public float[] lookAt = { 0, 1, 0 };
        public float fov = 35;
        public float orbitDegPerSec = 0;   // orbit around lookAt
        public float[] endPos;             // optional linear dolly to this position
        public float[] endLookAt;
        public string followActor;         // optional: lookAt tracks this actor's hips (by id)
        public string followBone;          // optional with followActor: track this HumanBodyBones bone in 3D instead
    }
    [System.Serializable] public class Actor
    {
        public string id;
        public string model;               // Assets/Characters/... .fbx
        public string skin;                // optional texture to apply (Kenney skins)
        public string clip;                // Assets/Clips/....kimodo
        public float[] pos = { 0, 0, 0 };
        public float yaw;
        public float timeOffset;
        public float speed = 1;
        public bool loop = true;
        public float scale = 1;
        public float height = 1.75f;       // target standing height in metres
        public bool playable;              // play through an Animator/PlayableGraph (Foot IK, root motion) instead of SampleAnimation
        public bool footIK;                // playable only: Apply Foot IK
        public bool rootMotion;            // playable only: Apply Root Motion (frames must be rendered in order)
        public bool grounding;             // playable only: add Promptimate Grounding (seat / soles / hands above the floor)
    }
    [System.Serializable] public class Shot
    {
        public string outDir;
        public int width = 1920, height = 1080, fps = 30, supersample = 2;
        public float seconds = 5;
        public string background = "#1b1f2a";
        public string ground = "#2a3040";
        public float groundSize = 80;
        public bool grid = true;
        public string sky = "procedural";  // "procedural" (daylight sky) or "solid" (background colour)
        public float skyExposure = 1.1f, atmosphere = 0.9f;
        public float sunYaw = -35, sunPitch = 50, sunIntensity = 1.15f;
        public Cam camera = new Cam();
        public Actor[] actors = new Actor[0];
    }

    static Vector3 V(float[] a) => a == null ? Vector3.zero : new Vector3(a[0], a[1], a[2]);
    static Color C(string hex) { ColorUtility.TryParseHtmlString(hex, out var c); return c; }

    public static void Run()
    {
        var args = System.Environment.GetCommandLineArgs();
        int i = System.Array.IndexOf(args, "-shot");
        int code = 0;
        try
        {
            if (i < 0) throw new System.Exception("missing -shot <file.json>");
            Render(JsonUtility.FromJson<Shot>(File.ReadAllText(args[i + 1])));
        }
        catch (System.Exception e) { Debug.LogError("DEMO_ERROR " + e); code = 1; }
        EditorApplication.Exit(code);
    }

    public static void Render(Shot s)
    {
        AssetDatabase.Refresh();
        // The launch-film shots use built-in Standard materials; ShotStudio switches the project to URP for its renders.
        GraphicsSettings.defaultRenderPipeline = null;
        QualitySettings.renderPipeline = null;
        HumanoidModelPostprocessor.EnsureTextures();
        EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        QualitySettings.shadows = ShadowQuality.All;
        QualitySettings.shadowResolution = ShadowResolution.VeryHigh;
        QualitySettings.shadowDistance = 60;
        QualitySettings.shadowCascades = 4;

        // Lighting: warm key sun + cool gradient ambient.
        RenderSettings.ambientMode = AmbientMode.Trilight;
        RenderSettings.ambientSkyColor = new Color(0.55f, 0.62f, 0.78f);
        RenderSettings.ambientEquatorColor = new Color(0.36f, 0.38f, 0.44f);
        RenderSettings.ambientGroundColor = new Color(0.18f, 0.17f, 0.18f);
        RenderSettings.fog = true;
        RenderSettings.fogMode = FogMode.Linear;
        RenderSettings.fogColor = C(s.background);
        RenderSettings.fogStartDistance = 25; RenderSettings.fogEndDistance = 70;
        var sun = new GameObject("Sun").AddComponent<Light>();
        sun.type = LightType.Directional; sun.intensity = s.sunIntensity; sun.color = new Color(1f, 0.95f, 0.88f);
        sun.shadows = LightShadows.Soft; sun.shadowStrength = 0.75f;
        sun.transform.rotation = Quaternion.Euler(s.sunPitch, s.sunYaw, 0);
        var rim = new GameObject("Rim").AddComponent<Light>();
        rim.type = LightType.Directional; rim.intensity = 0.45f; rim.color = new Color(0.6f, 0.75f, 1f);
        rim.transform.rotation = Quaternion.Euler(25, s.sunYaw + 160, 0);

        // Ground.
        var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
        ground.transform.localScale = Vector3.one * (s.groundSize / 10f);
        var gm = new Material(Shader.Find("Standard")) { color = C(s.ground) };
        gm.SetFloat("_Glossiness", 0.15f);
        if (s.grid) { gm.mainTexture = GridTexture(); gm.mainTextureScale = Vector2.one * s.groundSize; }
        ground.GetComponent<Renderer>().sharedMaterial = gm;

        // Actors.
        var actors = new List<(Actor a, GameObject go, AnimationClip clip, Animator anim)>();
        foreach (var a in s.actors)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(a.model) ?? throw new System.Exception("missing model " + a.model);
            // Empty clip = leave the character in its bind pose (T-pose), e.g. for "before animation" shots.
            var clip = string.IsNullOrEmpty(a.clip) ? null : AssetDatabase.LoadAssetAtPath<AnimationClip>(a.clip) ?? throw new System.Exception("missing clip " + a.clip);
            var go = (GameObject)Object.Instantiate(prefab);
            go.name = a.id ?? prefab.name;
            go.transform.SetPositionAndRotation(V(a.pos), Quaternion.Euler(0, a.yaw, 0));
            var anim = go.GetComponent<Animator>() ?? go.AddComponent<Animator>();
            anim.applyRootMotion = false;
            // Normalise every character to a human height (models ship in wildly different units), times a.scale.
            var head = anim.GetBoneTransform(HumanBodyBones.Head);
            var lf = anim.GetBoneTransform(HumanBodyBones.LeftFoot);
            float restHeight = head && lf ? (head.position.y - lf.position.y) * 1.13f + 0.08f * go.transform.lossyScale.y : 0;
            go.transform.localScale = restHeight > 0.01f ? go.transform.localScale * (a.height * a.scale / restHeight) : Vector3.one * a.scale;
            if (!string.IsNullOrEmpty(a.skin))
            {
                var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(a.skin);
                foreach (var r in go.GetComponentsInChildren<Renderer>())
                {
                    var m = new Material(Shader.Find("Standard")) { mainTexture = tex };
                    m.SetFloat("_Glossiness", 0.2f);
                    r.sharedMaterials = Enumerable.Repeat(m, r.sharedMaterials.Length).ToArray();
                }
            }
            foreach (var r in go.GetComponentsInChildren<Renderer>()) { r.shadowCastingMode = ShadowCastingMode.On; r.receiveShadows = true; }
            if (a.grounding) go.AddComponent<Promptimate.PromptimateGrounding>().Calibrate(); // bind pose, final scale
            actors.Add((a, go, clip, anim));
        }

        // Manual Camera.Render() bypasses Unity's per-frame skinning update, so the visible mesh showed a stale pose
        // (only the shadow pass picked up the new one). Force skinning to be recomputed on every render.
        foreach (var smr in actors.SelectMany(x => x.go.GetComponentsInChildren<SkinnedMeshRenderer>()))
        {
            smr.updateWhenOffscreen = true;
            smr.forceMatrixRecalculationPerRender = true;
        }

        // Camera + render target.
        var cam = new GameObject("Cam").AddComponent<Camera>();
        cam.clearFlags = CameraClearFlags.SolidColor; cam.backgroundColor = C(s.background);
        if (s.sky == "procedural")
        {
            var sky = new Material(Shader.Find("Skybox/Procedural"));
            sky.SetFloat("_SunSize", 0.03f); sky.SetFloat("_AtmosphereThickness", s.atmosphere);
            sky.SetFloat("_Exposure", s.skyExposure); sky.SetColor("_GroundColor", new Color(0.45f, 0.48f, 0.52f));
            RenderSettings.skybox = sky; RenderSettings.sun = sun;
            cam.clearFlags = CameraClearFlags.Skybox;
            RenderSettings.fogColor = new Color(0.62f, 0.70f, 0.80f);
            RenderSettings.fogStartDistance = 20; RenderSettings.fogEndDistance = 55;
        }
        cam.fieldOfView = s.camera.fov; cam.nearClipPlane = 0.05f; cam.farClipPlane = 200;
        int W = s.width * s.supersample, H = s.height * s.supersample;
        var rt = new RenderTexture(W, H, 24, RenderTextureFormat.ARGB32) { antiAliasing = 8 };
        var outRt = new RenderTexture(s.width, s.height, 0, RenderTextureFormat.ARGB32);
        cam.targetTexture = rt;
        var tex2d = new Texture2D(s.width, s.height, TextureFormat.RGB24, false);
        Directory.CreateDirectory(s.outDir);
        foreach (var f in Directory.GetFiles(s.outDir, "*.png")) File.Delete(f);

        int frames = Mathf.RoundToInt(s.seconds * s.fps);
        Transform followHips = null;
        bool follow3D = false;
        if (!string.IsNullOrEmpty(s.camera.followActor))
        {
            var fa = actors.FirstOrDefault(x => x.a.id == s.camera.followActor).anim;
            follow3D = !string.IsNullOrEmpty(s.camera.followBone);
            followHips = fa?.GetBoneTransform(follow3D ? (HumanBodyBones)System.Enum.Parse(typeof(HumanBodyBones), s.camera.followBone) : HumanBodyBones.Hips);
        }

        var graphs = new Dictionary<GameObject, (PlayableGraph g, AnimationClipPlayable cp)>();
        for (int f = 0; f < frames; f++)
        {
            float t = f / (float)s.fps, u = frames > 1 ? f / (float)(frames - 1) : 0;
            foreach (var (a, go, clip, anim) in actors)
            {
                if (clip == null) continue;
                if (a.playable)
                {
                    if (!graphs.TryGetValue(go, out var gp))
                    {
                        anim.applyRootMotion = a.rootMotion; anim.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                        var g = PlayableGraph.Create(go.name); g.SetTimeUpdateMode(DirectorUpdateMode.Manual);
                        var cp = AnimationClipPlayable.Create(g, clip); cp.SetApplyFootIK(a.footIK);
                        AnimationPlayableOutput.Create(g, "out", anim).SetSourcePlayable(cp);
                        g.Play(); cp.SetTime(a.timeOffset); g.Evaluate(0);
                        graphs[go] = gp = (g, cp);
                    }
                    else gp.g.Evaluate(a.speed / s.fps);
                    go.GetComponent<Promptimate.PromptimateGrounding>()?.Solve(); // LateUpdate doesn't run here
                    continue;
                }
                float ct = a.timeOffset + t * a.speed;
                ct = a.loop ? Mathf.Repeat(ct, clip.length) : Mathf.Clamp(ct, 0, clip.length);
                clip.SampleAnimation(go, ct);
            }
            var look = V(s.camera.lookAt);
            if (s.camera.endLookAt != null) look = Vector3.Lerp(look, V(s.camera.endLookAt), Smooth(u));
            if (followHips != null) look = follow3D ? followHips.position : new Vector3(followHips.position.x, look.y, followHips.position.z);
            var pos = V(s.camera.pos);
            if (s.camera.endPos != null) pos = Vector3.Lerp(pos, V(s.camera.endPos), Smooth(u));
            if (followHips != null) pos += look - V(s.camera.lookAt);
            if (s.camera.orbitDegPerSec != 0)
                pos = look + Quaternion.Euler(0, s.camera.orbitDegPerSec * t, 0) * (pos - look);
            cam.transform.position = pos;
            cam.transform.LookAt(look);

            cam.Render();
            Graphics.Blit(rt, outRt); // bilinear downsample = supersampling AA
            RenderTexture.active = outRt;
            tex2d.ReadPixels(new Rect(0, 0, s.width, s.height), 0, 0);
            tex2d.Apply();
            RenderTexture.active = null;
            File.WriteAllBytes(Path.Combine(s.outDir, $"f{f:D5}.png"), tex2d.EncodeToPNG());
        }
        foreach (var gp in graphs.Values) gp.g.Destroy();
        Debug.Log($"DEMO_DONE frames={frames} out={s.outDir}");
    }

    static float Smooth(float u) => u * u * (3 - 2 * u);

    static Texture2D GridTexture()
    {
        const int N = 64;
        var t = new Texture2D(N, N, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Repeat, filterMode = FilterMode.Trilinear, anisoLevel = 8 };
        for (int y = 0; y < N; y++)
            for (int x = 0; x < N; x++)
            {
                bool line = x < 1 || y < 1;
                float v = line ? 1f : 0.82f;
                t.SetPixel(x, y, new Color(v, v, v, 1));
            }
        t.Apply();
        return t;
    }
}
