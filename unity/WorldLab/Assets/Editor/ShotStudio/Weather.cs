// Mood layers on top of a lighting preset: rain (stretched particle streaks simulated deterministically per frame,
// wet glossy ground that picks up lamp highlights), fog (denser haze) and light cones under practical lamps, which is
// what makes night street lighting read on a small vertical screen.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace ShotStudio
{
    public class WeatherRig
    {
        public ParticleSystem rain; public float dt;
        public void Step(float seconds) { if (rain) rain.Simulate(seconds, true, false, false); }
    }

    public static class Weather
    {
        public static bool Rain(string w) => !string.IsNullOrEmpty(w) && w.Contains("rain");
        public static bool Fog(string w) => !string.IsNullOrEmpty(w) && w.Contains("fog");

        public static WeatherRig Apply(LightSpec spec, Look look, Vector3 camPos, Vector3 camFwd, float fps)
        {
            var rig = new WeatherRig { dt = 1f / Mathf.Max(1, fps) };
            string w = spec.weather ?? "";
            float amt = Mathf.Clamp(spec.weatherAmount <= 0 ? 1 : spec.weatherAmount, 0.1f, 2f);
            if (Fog(w))
            {
                RenderSettings.fog = true;
                RenderSettings.fogDensity = Mathf.Max(RenderSettings.fogDensity, 0.012f) * (1.8f + 0.9f * amt);
            }
            else if (Rain(w)) RenderSettings.fogDensity = Mathf.Max(RenderSettings.fogDensity, 0.01f) * 1.35f;
            if (Rain(w))
            {
                rig.rain = MakeRain(camPos, camFwd, amt);
                rig.rain.Simulate(1.5f, true, true, false); // pre-warm: rain already falling on frame 0
                WetGround();
            }
            return rig;
        }

        static ParticleSystem MakeRain(Vector3 camPos, Vector3 camFwd, float amt)
        {
            var go = new GameObject("Rain");
            var f = Vector3.ProjectOnPlane(camFwd, Vector3.up).normalized;
            if (f.sqrMagnitude < 1e-4f) f = Vector3.forward;
            go.transform.position = new Vector3(camPos.x, 0, camPos.z) + f * 10f + Vector3.up * 9f; // 3..17 m out: no lens-filling streaks
            go.transform.rotation = Quaternion.LookRotation(f, Vector3.up);
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            ps.useAutoRandomSeed = false; ps.randomSeed = 7331;
            var main = ps.main;
            main.loop = true; main.playOnAwake = false; main.duration = 4;
            main.startLifetime = 1.15f; main.startSpeed = 0; main.startSize = 0.011f;
            main.startColor = new Color(0.72f, 0.78f, 0.9f, 0.42f);
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.maxParticles = 40000;
            main.gravityModifier = 0;
            var em = ps.emission; em.rateOverTime = 9000f * amt;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Box; sh.scale = new Vector3(20, 0.1f, 14);
            var vel = ps.velocityOverLifetime; vel.enabled = true; vel.space = ParticleSystemSimulationSpace.World;
            vel.x = new ParticleSystem.MinMaxCurve(0.6f, 1.4f); vel.y = new ParticleSystem.MinMaxCurve(-11f, -9f); vel.z = new ParticleSystem.MinMaxCurve(-0.2f, 0.2f);
            var r = go.GetComponent<ParticleSystemRenderer>();
            r.renderMode = ParticleSystemRenderMode.Stretch; r.velocityScale = 0.045f; r.lengthScale = 1.5f;
            r.material = Additive(StreakTexture());
            r.shadowCastingMode = ShadowCastingMode.Off; r.receiveShadows = false;
            return ps;
        }

        static Texture2D StreakTexture()
        {
            var t = new Texture2D(8, 64, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
            for (int y = 0; y < 64; y++)
                for (int x = 0; x < 8; x++)
                {
                    float u = Mathf.Abs(x - 3.5f) / 3.5f, v = Mathf.Abs(y - 31.5f) / 31.5f;
                    float a = (1 - u * u) * (1 - v * v);
                    t.SetPixel(x, y, new Color(1, 1, 1, a));
                }
            t.Apply();
            return t;
        }

        public static Material Additive(Texture tex, float alpha = 1)
        {
            var sh = Shader.Find("Universal Render Pipeline/Particles/Unlit") ?? Shader.Find("Sprites/Default");
            var m = new Material(sh);
            if (tex) { m.SetTexture("_BaseMap", tex); m.mainTexture = tex; }
            m.SetColor("_BaseColor", new Color(1, 1, 1, alpha));
            m.SetFloat("_Surface", 1); m.SetFloat("_Blend", 2); // transparent, additive
            m.SetOverrideTag("RenderType", "Transparent");
            m.SetInt("_SrcBlend", (int)BlendMode.SrcAlpha); m.SetInt("_DstBlend", (int)BlendMode.One);
            m.SetInt("_ZWrite", 0);
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            return m;
        }

        /// Rain-soaked ground: the large flat surfaces get glossy (lamp highlights streak across them) and darker.
        static void WetGround()
        {
            var done = new HashSet<Material>();
            foreach (var r in Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None))
            {
                var n = r.name;
                if (!(n == "Ground" || n == "Road" || n.StartsWith("Curb") || n == "Lane" || n == "Crossing" || n == "Path")) continue;
                foreach (var m in r.sharedMaterials)
                {
                    if (m == null || !done.Add(m) || !m.HasProperty("_Smoothness")) continue;
                    m.SetFloat("_Smoothness", 0.82f);
                    if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", m.GetColor("_BaseColor") * 0.72f);
                }
            }
        }

        /// A soft additive cone of light under a lamp head (haze catching the light). Brighter in fog and rain.
        public static void LightCone(Vector3 head, Color c, float strength, float angleDeg = 34, float height = -1)
        {
            float h = height > 0 ? height : Mathf.Max(0.5f, head.y);
            float r1 = h * Mathf.Tan(angleDeg * Mathf.Deg2Rad), r0 = 0.12f;
            const int N = 32;
            var mesh = new Mesh { name = "LightCone" };
            var v = new List<Vector3>(); var col = new List<Color>(); var uv = new List<Vector2>(); var tri = new List<int>();
            for (int i = 0; i <= N; i++)
            {
                float a = i / (float)N * Mathf.PI * 2;
                var d = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                v.Add(d * r0); v.Add(d * r1 + Vector3.down * h);
                col.Add(new Color(c.r, c.g, c.b, strength)); col.Add(new Color(c.r, c.g, c.b, 0));
                uv.Add(new Vector2(0.5f, 0.5f)); uv.Add(new Vector2(0.5f, 0.5f));
            }
            for (int i = 0; i < N; i++)
            {
                int k = i * 2;
                tri.AddRange(new[] { k, k + 2, k + 1, k + 1, k + 2, k + 3 });
                tri.AddRange(new[] { k, k + 1, k + 2, k + 1, k + 3, k + 2 }); // both faces
            }
            mesh.SetVertices(v); mesh.SetColors(col); mesh.SetUVs(0, uv); mesh.SetTriangles(tri, 0); mesh.RecalculateBounds();
            var go = new GameObject("LightCone");
            go.transform.position = head;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = Additive(Texture2D.whiteTexture);
            mr.sharedMaterial.EnableKeyword("_VERTEX_COLORS");
            mr.shadowCastingMode = ShadowCastingMode.Off; mr.receiveShadows = false;
        }
    }
}
