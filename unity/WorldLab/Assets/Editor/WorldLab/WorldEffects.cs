// Atmosphere: cigarette smoke and steam (particles), dust motes and fake volumetric shafts (additive extruded window
// light), rain/snow outside the windows, rain running down the glass, lightning flashes and flickering practicals.
// Everything is simulated deterministically per rendered frame (batch rendering has no realtime clock).
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace WorldLab
{
    public class EffectsRig
    {
        public readonly List<ParticleSystem> systems = new List<ParticleSystem>();
        public readonly List<(Light l, float baseI, float amount, int seed)> flicker = new List<(Light, float, float, int)>();
        public readonly List<Material> glass = new List<Material>();
        public Light lightning; public float lightningPeak; public float[] flashes = new float[0];
        public Material sky; public float skyBase = 1;
        public float t;

        public void Prewarm()
        {
            foreach (var ps in systems) ps.Simulate(3f, true, true, false);
        }

        public void Step(float dt)
        {
            t += dt;
            foreach (var ps in systems) ps.Simulate(dt, true, false, false);
            foreach (var (l, b, a, s) in flicker)
                if (l) l.intensity = b * (1 + a * (Mathf.PerlinNoise(t * 7.3f, s * 0.37f) - 0.5f) * 2f + a * 0.5f * (Mathf.PerlinNoise(t * 23f, s) - 0.5f));
            float f = Flash(t);
            if (lightning) lightning.intensity = lightningPeak * f;
            if (sky) sky.SetFloat("_Exposure", skyBase * (1 + 5 * f));
            foreach (var g in glass) g.SetTextureOffset("_BumpMap", new Vector2(0, t * 0.035f));
        }

        float Flash(float time)
        {
            float v = 0;
            foreach (var ft in flashes)
            {
                float d = time - ft;
                if (d < 0 || d > 0.6f) continue;
                // double strike: a bright flash, a dip, a second weaker flash
                v = Mathf.Max(v, Mathf.Exp(-d * 28f) + 0.55f * Mathf.Exp(-Mathf.Pow((d - 0.16f) * 30f, 2)));
            }
            return v;
        }
    }

    public static class WorldEffects
    {
        public static EffectsRig Apply(WorldJob job, BuiltWorld w)
        {
            var rig = new EffectsRig();
            rig.glass.AddRange(w.glass);
            foreach (var e in job.effects ?? new EffectSpec[0])
            {
                var p = WorldBuilder.V(e.pos);
                if (!string.IsNullOrEmpty(e.target) && w.items.TryGetValue(e.target, out var it) && it.go)
                    p = new Vector3(it.bounds.center.x, it.bounds.max.y, it.bounds.center.z) + p;
                var col = WorldBuilder.C(e.color, Color.white);
                switch (e.type)
                {
                    case "smoke": rig.systems.Add(Smoke(p, col, e.amount, 0.012f, 0.7f, 7f)); break;
                    case "steam": rig.systems.Add(Smoke(p, col, e.amount * 0.6f, 0.02f, 0.35f, 2.4f)); break;
                    case "dust": rig.systems.Add(Dust(p, WorldBuilder.V(e.size, 1), col, e.amount)); break;
                    case "shaft": Shaft(p, WorldBuilder.V(e.size, 1), WorldBuilder.V(e.dir), WorldBuilder.V(e.axis), col, e.amount); break;
                    case "rain_outside": rig.systems.Add(Precip(p, WorldBuilder.V(e.size, 1), WorldBuilder.V(e.dir), col, e.amount, false)); break;
                    case "snow_outside": rig.systems.Add(Precip(p, WorldBuilder.V(e.size, 1), WorldBuilder.V(e.dir), col, e.amount, true)); break;
                    case "lightning":
                    {
                        var l = new GameObject("Lightning").AddComponent<Light>();
                        l.type = LightType.Directional; l.color = col; l.intensity = 0; l.shadows = LightShadows.Hard; l.shadowStrength = 0.9f;
                        var d = WorldBuilder.V(e.dir); if (d.sqrMagnitude < 1e-4f) d = new Vector3(0.3f, -0.6f, 0.7f);
                        l.transform.rotation = Quaternion.LookRotation(d.normalized);
                        rig.lightning = l; rig.lightningPeak = e.amount; rig.flashes = e.times ?? new float[0];
                        break;
                    }
                }
            }
            return rig;
        }

        static Texture2D _soft;
        static Texture2D Soft()
        {
            if (_soft) return _soft;
            const int N = 64;
            _soft = new Texture2D(N, N, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Clamp };
            for (int y = 0; y < N; y++)
                for (int x = 0; x < N; x++)
                {
                    float dx = (x - N / 2 + 0.5f) / (N / 2), dy = (y - N / 2 + 0.5f) / (N / 2);
                    float r = Mathf.Sqrt(dx * dx + dy * dy);
                    float a = Mathf.Clamp01(1 - r); a = a * a * (0.65f + 0.35f * Mathf.PerlinNoise(x * 0.15f, y * 0.15f));
                    _soft.SetPixel(x, y, new Color(1, 1, 1, a));
                }
            _soft.Apply(true);
            return _soft;
        }

        static Material Alpha(Texture tex)
        {
            var m = new Material(Shader.Find("Universal Render Pipeline/Particles/Unlit"));
            m.SetTexture("_BaseMap", tex); m.mainTexture = tex;
            m.SetFloat("_Surface", 1); m.SetFloat("_Blend", 0);
            m.SetOverrideTag("RenderType", "Transparent");
            m.SetInt("_SrcBlend", (int)BlendMode.SrcAlpha); m.SetInt("_DstBlend", (int)BlendMode.OneMinusSrcAlpha); m.SetInt("_ZWrite", 0);
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            return m;
        }

        /// A thin rising plume that widens and curls (noise), for a cigarette or a hot drink.
        static ParticleSystem Smoke(Vector3 p, Color col, float amount, float size0, float rise, float life)
        {
            var go = new GameObject("Smoke"); go.transform.position = p; go.transform.rotation = Quaternion.LookRotation(Vector3.up);
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            ps.useAutoRandomSeed = false; ps.randomSeed = 4242;
            var main = ps.main; main.loop = true; main.playOnAwake = false; main.startLifetime = life; main.startSpeed = rise * 0.25f;
            main.startSize = new ParticleSystem.MinMaxCurve(size0, size0 * 2.5f); main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.startColor = new Color(col.r, col.g, col.b, 0.22f * Mathf.Clamp(amount, 0.2f, 2f)); main.maxParticles = 3000;
            main.startRotation = new ParticleSystem.MinMaxCurve(0, 6.28f);
            var em = ps.emission; em.rateOverTime = 22 * amount;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Cone; sh.angle = 3; sh.radius = 0.003f;
            var vel = ps.velocityOverLifetime; vel.enabled = true; vel.space = ParticleSystemSimulationSpace.World;
            vel.x = new ParticleSystem.MinMaxCurve(0.0f, 0.03f); vel.y = new ParticleSystem.MinMaxCurve(rise * 0.8f, rise); vel.z = new ParticleSystem.MinMaxCurve(-0.01f, 0.02f);
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.09f; noise.frequency = 1.1f; noise.scrollSpeed = 0.25f; noise.damping = true;
            var sol = ps.sizeOverLifetime; sol.enabled = true; sol.size = new ParticleSystem.MinMaxCurve(1, AnimationCurve.Linear(0, 0.4f, 1, 9f));
            var col2 = ps.colorOverLifetime; col2.enabled = true;
            var g = new Gradient(); g.SetKeys(new[] { new GradientColorKey(Color.white, 0), new GradientColorKey(Color.white, 1) },
                                              new[] { new GradientAlphaKey(0, 0), new GradientAlphaKey(1, 0.08f), new GradientAlphaKey(0.45f, 0.5f), new GradientAlphaKey(0, 1) });
            col2.color = g;
            var r = go.GetComponent<ParticleSystemRenderer>(); r.material = Alpha(Soft()); r.shadowCastingMode = ShadowCastingMode.Off; r.receiveShadows = false;
            r.sortMode = ParticleSystemSortMode.Distance;
            return ps;
        }

        /// Floating dust catching the light inside a box volume (place it in a light shaft).
        static ParticleSystem Dust(Vector3 p, Vector3 size, Color col, float amount)
        {
            var go = new GameObject("Dust"); go.transform.position = p;
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            ps.useAutoRandomSeed = false; ps.randomSeed = 99;
            var main = ps.main; main.loop = true; main.playOnAwake = false; main.startLifetime = 8; main.startSpeed = 0;
            main.startSize = new ParticleSystem.MinMaxCurve(0.003f, 0.007f); main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.startColor = new Color(col.r, col.g, col.b, 0.8f); main.maxParticles = 4000;
            var em = ps.emission; em.rateOverTime = 120 * amount;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Box; sh.scale = size;
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.03f; noise.frequency = 0.4f; noise.scrollSpeed = 0.1f;
            var r = go.GetComponent<ParticleSystemRenderer>(); r.material = ShotStudio.Weather.Additive(Soft(), 1); r.shadowCastingMode = ShadowCastingMode.Off;
            return ps;
        }

        /// Fake volumetric light: the window rectangle (centre p, size x = width, y = height) extruded along the light
        /// direction, additive, fading out with distance. URP has no volumetric fog; this is the classic film trick.
        static void Shaft(Vector3 p, Vector3 size, Vector3 dir, Vector3 axis, Color col, float amount)
        {
            dir = dir.sqrMagnitude < 1e-4f ? Vector3.down : dir.normalized;
            var right = Vector3.Cross(Vector3.up, dir); if (right.sqrMagnitude < 1e-4f) right = Vector3.right; right.Normalize();
            var wallT = axis.sqrMagnitude > 1e-4f ? axis.normalized : (Mathf.Abs(dir.x) > Mathf.Abs(dir.z) ? Vector3.forward : Vector3.right);
            float len = 4.5f;
            var mesh = new Mesh { name = "Shaft" };
            var v = new List<Vector3>(); var c = new List<Color>(); var tri = new List<int>();
            Vector3[] q = { -wallT * size.x / 2 - Vector3.up * size.y / 2, wallT * size.x / 2 - Vector3.up * size.y / 2, wallT * size.x / 2 + Vector3.up * size.y / 2, -wallT * size.x / 2 + Vector3.up * size.y / 2 };
            for (int i = 0; i < 4; i++) { v.Add(q[i]); c.Add(new Color(col.r, col.g, col.b, 0.06f * amount)); }
            for (int i = 0; i < 4; i++) { v.Add(q[i] + dir * len); c.Add(new Color(col.r, col.g, col.b, 0)); }
            int[][] sides = { new[] { 0, 1 }, new[] { 1, 2 }, new[] { 2, 3 }, new[] { 3, 0 } };
            foreach (var s in sides)
            {
                int a = s[0], b = s[1];
                tri.AddRange(new[] { a, b, b + 4, a, b + 4, a + 4, a, b + 4, b, a, a + 4, b + 4 });
            }
            mesh.SetVertices(v); mesh.SetColors(c); mesh.SetTriangles(tri, 0); mesh.RecalculateBounds();
            var go = new GameObject("Shaft"); go.transform.position = p;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = ShotStudio.Weather.Additive(Texture2D.whiteTexture);
            mr.sharedMaterial.EnableKeyword("_VERTEX_COLORS");
            mr.shadowCastingMode = ShadowCastingMode.Off; mr.receiveShadows = false;
        }

        /// Rain or snow falling in a box just outside a window (seen through the glass).
        static ParticleSystem Precip(Vector3 p, Vector3 size, Vector3 wind, Color col, float amount, bool snow)
        {
            var go = new GameObject(snow ? "Snow" : "Rain"); go.transform.position = p;
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            ps.useAutoRandomSeed = false; ps.randomSeed = snow ? 555u : 777u;
            var main = ps.main; main.loop = true; main.playOnAwake = false; main.startLifetime = snow ? 6 : 0.9f; main.startSpeed = 0;
            main.startSize = snow ? new ParticleSystem.MinMaxCurve(0.012f, 0.03f) : new ParticleSystem.MinMaxCurve(0.006f, 0.01f);
            main.simulationSpace = ParticleSystemSimulationSpace.World; main.maxParticles = 20000;
            main.startColor = new Color(col.r, col.g, col.b, snow ? 0.9f : 0.35f);
            var em = ps.emission; em.rateOverTime = (snow ? 600 : 5000) * amount;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Box; sh.scale = new Vector3(size.x, 0.1f, size.z);
            go.transform.position = p + Vector3.up * size.y / 2;
            var vel = ps.velocityOverLifetime; vel.enabled = true; vel.space = ParticleSystemSimulationSpace.World;
            float fall = snow ? 0.9f : 9.5f;
            vel.x = new ParticleSystem.MinMaxCurve(wind.x - 0.2f, wind.x + 0.2f); vel.y = new ParticleSystem.MinMaxCurve(-fall * 1.15f, -fall * 0.85f); vel.z = new ParticleSystem.MinMaxCurve(wind.z - 0.2f, wind.z + 0.2f);
            if (snow) { var n = ps.noise; n.enabled = true; n.strength = 0.4f; n.frequency = 0.5f; }
            var r = go.GetComponent<ParticleSystemRenderer>();
            if (!snow) { r.renderMode = ParticleSystemRenderMode.Stretch; r.velocityScale = 0.04f; r.lengthScale = 1.2f; }
            r.material = snow ? Alpha(Soft()) : ShotStudio.Weather.Additive(Soft(), 1);
            r.shadowCastingMode = ShadowCastingMode.Off; r.receiveShadows = false;
            return ps;
        }

        /// Normal map of raindrops and running streaks for window glass (scrolled over time by the rig).
        public static Texture2D RainNormal(int size, int seed)
        {
            var h = new float[size * size];
            var rnd = new System.Random(seed);
            for (int k = 0; k < 260; k++)
            {
                float cx = (float)rnd.NextDouble() * size, cy = (float)rnd.NextDouble() * size, r = 1.5f + (float)rnd.NextDouble() * 4.5f;
                bool streak = rnd.NextDouble() < 0.25;
                float len = streak ? 20 + (float)rnd.NextDouble() * 60 : 0;
                for (int y = (int)(cy - r - len); y <= cy + r; y++)
                    for (int x = (int)(cx - r); x <= cx + r; x++)
                    {
                        int xx = ((x % size) + size) % size, yy = ((y % size) + size) % size;
                        float dy = y > cy ? y - cy : (streak ? 0 : cy - y);
                        float rr = streak && y < cy ? r * 0.45f : r;
                        float d = Mathf.Sqrt((x - cx) * (x - cx) + dy * dy) / rr;
                        if (d < 1) h[yy * size + xx] = Mathf.Max(h[yy * size + xx], Mathf.Sqrt(1 - d * d) * (streak && y < cy ? 0.5f : 1));
                    }
            }
            var t = new Texture2D(size, size, TextureFormat.RGBA32, true, true) { wrapMode = TextureWrapMode.Repeat };
            for (int y = 0; y < size; y++)
                for (int x = 0; x < size; x++)
                {
                    float hx = h[y * size + (x + 1) % size] - h[y * size + (x - 1 + size) % size];
                    float hy = h[((y + 1) % size) * size + x] - h[((y - 1 + size) % size) * size + x];
                    var n = new Vector3(-hx * 2.5f, -hy * 2.5f, 1).normalized;
                    t.SetPixel(x, y, new Color(n.x * 0.5f + 0.5f, n.y * 0.5f + 0.5f, n.z * 0.5f + 0.5f, 1));
                }
            t.Apply(true);
            return t;
        }
    }
}
