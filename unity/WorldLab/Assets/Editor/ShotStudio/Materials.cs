// Converts whatever materials a model was imported with (built-in Standard, glTFast shaders, Kenney FBX) into URP Lit
// instances at render time, so the same asset works no matter which pipeline was active when it was imported.
using System.Collections.Generic;
using UnityEngine;

namespace ShotStudio
{
    public static class Materials
    {
        static Shader _lit;
        static readonly Dictionary<(Material, Texture), Material> Cache = new Dictionary<(Material, Texture), Material>();
        public static Shader Lit => _lit ? _lit : (_lit = Shader.Find("Universal Render Pipeline/Lit"));

        public static void Reset() => Cache.Clear();

        public static void ConvertAll(GameObject go, Texture2D skin = null, float smoothness = -1)
        {
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                var mats = r.sharedMaterials;
                for (int i = 0; i < mats.Length; i++) mats[i] = Convert(mats[i], skin, smoothness);
                r.sharedMaterials = mats;
            }
        }

        public static Material Convert(Material src, Texture skin = null, float smoothness = -1)
        {
            if (src == null) return Make(Color.gray, skin, 0.2f);
            if (Cache.TryGetValue((src, skin), out var hit)) return hit;
            Texture tex = skin;
            Color col = Color.white;
            foreach (var p in new[] { "_BaseMap", "_MainTex", "baseColorTexture", "_BaseColorMap" })
                if (!tex && src.HasProperty(p) && src.GetTexture(p)) { tex = src.GetTexture(p); break; }
            foreach (var p in new[] { "_BaseColor", "_Color", "baseColorFactor" })
                if (src.HasProperty(p)) { col = src.GetColor(p); break; }
            if (skin) col = Color.white;
            float sm = smoothness;
            if (sm < 0)
            {
                sm = 0.25f;
                if (src.HasProperty("_Glossiness")) sm = Mathf.Min(src.GetFloat("_Glossiness"), 0.6f);
                else if (src.HasProperty("_Smoothness")) sm = Mathf.Min(src.GetFloat("_Smoothness"), 0.6f);
                else if (src.HasProperty("roughnessFactor")) sm = Mathf.Clamp(1 - src.GetFloat("roughnessFactor"), 0.05f, 0.6f);
            }
            var m = Make(col, tex, sm);
            m.name = src.name + "_urp";
            Texture nrm = null;
            foreach (var p in new[] { "_BumpMap", "normalTexture" })
                if (src.HasProperty(p) && src.GetTexture(p)) { nrm = src.GetTexture(p); break; }
            if (nrm) { m.SetTexture("_BumpMap", nrm); m.EnableKeyword("_NORMALMAP"); }
            // Emissive parts (screens, lamps) keep their glow, which bloom picks up.
            foreach (var p in new[] { "_EmissionColor", "emissiveFactor" })
                if (src.HasProperty(p))
                {
                    var e = src.GetColor(p);
                    if (e.maxColorComponent > 0.01f) { m.SetColor("_EmissionColor", e); m.EnableKeyword("_EMISSION"); }
                    break;
                }
            Cache[(src, skin)] = m;
            return m;
        }

        public static Material Make(Color col, Texture tex = null, float smoothness = 0.25f, float metallic = 0f)
        {
            var m = new Material(Lit);
            m.SetColor("_BaseColor", col);
            if (tex) m.SetTexture("_BaseMap", tex);
            m.SetFloat("_Smoothness", smoothness);
            m.SetFloat("_Metallic", metallic);
            m.SetFloat("_EnvironmentReflections", 1);
            m.SetFloat("_SpecularHighlights", 1);
            return m;
        }

        public static Material Emissive(Color col, float intensity)
        {
            var m = Make(col, null, 0.5f);
            m.SetColor("_EmissionColor", col * intensity);
            m.EnableKeyword("_EMISSION");
            return m;
        }

        /// Tileable value-noise albedo for large ground planes (asphalt, grass, floorboards), deterministic per seed.
        public static Texture2D Noise(Color a, Color b, int size = 256, float scale = 8, int seed = 1, float streaks = 0)
        {
            var t = new Texture2D(size, size, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Repeat, filterMode = FilterMode.Trilinear, anisoLevel = 8 };
            var px = new Color[size * size];
            var rnd = new System.Random(seed);
            float ox = (float)rnd.NextDouble() * 100, oy = (float)rnd.NextDouble() * 100;
            for (int y = 0; y < size; y++)
                for (int x = 0; x < size; x++)
                {
                    float u = x / (float)size, v = y / (float)size;
                    float n = 0, amp = 0.5f, f = scale;
                    for (int o = 0; o < 4; o++)
                    {
                        n += amp * TileNoise(u * f + ox, v * f + oy, f);
                        f *= 2; amp *= 0.5f;
                    }
                    if (streaks > 0) n = Mathf.Lerp(n, TileNoise(u * 2 + ox, v * scale * 6 + oy, 2), streaks);
                    px[y * size + x] = Color.Lerp(a, b, Mathf.Clamp01(n));
                }
            t.SetPixels(px);
            t.Apply(true);
            return t;
        }

        static float TileNoise(float x, float y, float period)
        {
            // Perlin noise made tileable by blending four shifted copies.
            float p = period;
            float fx = Mathf.Repeat(x, p) / p, fy = Mathf.Repeat(y, p) / p;
            float a = Mathf.PerlinNoise(x, y), b = Mathf.PerlinNoise(x - p, y), c = Mathf.PerlinNoise(x, y - p), d = Mathf.PerlinNoise(x - p, y - p);
            return Mathf.Lerp(Mathf.Lerp(a, b, fx), Mathf.Lerp(c, d, fx), fy);
        }
    }
}
