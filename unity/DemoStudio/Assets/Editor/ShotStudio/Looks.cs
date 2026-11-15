// Lighting / mood presets: key light, ambient, sky, fog and a URP post stack (ACES tonemapping, bloom, colour grade,
// vignette). Practical lights (street lamps, room lamps) come from the stage and are switched on by the look.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace ShotStudio
{
    public class Look
    {
        public string name;
        public Color keyColor = Color.white; public float keyIntensity = 1.6f, keyPitch = 45, keyYawOffset = -50; // yaw relative to the camera
        public float shadowStrength = 0.85f;
        public Color fillColor = new Color(0.6f, 0.7f, 1f); public float fillIntensity = 0.0f; // second directional, no shadows
        public Color rimColor = new Color(0.8f, 0.85f, 1f); public float rimIntensity = 0.5f;
        public Color ambSky = new Color(0.5f, 0.58f, 0.75f), ambEquator = new Color(0.38f, 0.38f, 0.4f), ambGround = new Color(0.2f, 0.18f, 0.16f);
        public float ambientScale = 1f;
        public Color skyTop = new Color(0.22f, 0.42f, 0.78f), skyHorizon = new Color(0.72f, 0.82f, 0.92f), skyGlow = new Color(1f, 0.95f, 0.85f);
        public float glow = 0.35f;     // sun glow strength around the key direction
        public bool sky = true; public Color skyTint = new Color(0.5f, 0.55f, 0.65f); public float skyExposure = 1.15f, atmosphere = 1f; public Color background = new Color(0.1f, 0.11f, 0.14f);
        public bool fog = true; public Color fogColor = new Color(0.66f, 0.73f, 0.82f); public float fogDensity = 0.012f;
        public float exposure = 0f, contrast = 8f, saturation = 5f, temperature = 0f, tint = 0f;
        public float bloom = 0.35f, bloomThreshold = 1.0f, vignette = 0.22f;
        public Color shadowsTint = Color.white, highlightsTint = Color.white;
        public bool practicals;         // switch on stage lamps
        public Color practicalColor = new Color(1f, 0.78f, 0.5f); public float practicalIntensity = 4f, practicalRange = 9f;
        public float dof = 0;           // >0: gentle background blur (Bokeh), focus on the subject
        public float sceneKey = 0;      // >0: a practical (street lamp / sign) right by the actors, so faces read at night
    }

    public static class Looks
    {
        public static readonly Dictionary<string, Look> All = new Dictionary<string, Look>
        {
            ["day"] = new Look { name = "day", keyColor = new Color(1f, 0.95f, 0.88f), keyIntensity = 1.55f, keyPitch = 48,
                ambSky = new Color(0.52f, 0.62f, 0.8f), ambEquator = new Color(0.45f, 0.47f, 0.5f), ambGround = new Color(0.25f, 0.23f, 0.2f),
                skyTint = new Color(0.45f, 0.55f, 0.7f), atmosphere = 0.9f, fogColor = new Color(0.68f, 0.76f, 0.86f), fogDensity = 0.008f,
                skyTop = new Color(0.2f, 0.42f, 0.8f), skyHorizon = new Color(0.7f, 0.8f, 0.92f), glow = 0.25f,
                saturation = 0, contrast = 10, bloom = 0.25f },
            ["golden_hour"] = new Look { name = "golden_hour", keyColor = new Color(1f, 0.62f, 0.32f), keyIntensity = 2.6f, keyPitch = 11, keyYawOffset = -110,
                rimColor = new Color(1f, 0.7f, 0.45f), rimIntensity = 0.3f, fillColor = new Color(0.45f, 0.55f, 0.9f), fillIntensity = 0.25f,
                ambSky = new Color(0.55f, 0.5f, 0.6f), ambEquator = new Color(0.6f, 0.45f, 0.35f), ambGround = new Color(0.25f, 0.17f, 0.12f), ambientScale = 0.9f,
                skyTint = new Color(0.75f, 0.5f, 0.35f), skyExposure = 1.3f, atmosphere = 2.6f, fogColor = new Color(0.95f, 0.7f, 0.5f), fogDensity = 0.014f,
                skyTop = new Color(0.27f, 0.32f, 0.55f), skyHorizon = new Color(1f, 0.62f, 0.4f), skyGlow = new Color(1f, 0.7f, 0.35f), glow = 0.9f,
                temperature = 18, saturation = 12, contrast = 14, bloom = 0.7f, bloomThreshold = 0.9f, vignette = 0.28f,
                highlightsTint = new Color(1f, 0.92f, 0.82f), dof = 1 },
            ["night_street"] = new Look { name = "night_street", keyColor = new Color(0.55f, 0.66f, 1f), keyIntensity = 0.55f, keyPitch = 40, keyYawOffset = 140, shadowStrength = 0.6f,
                rimColor = new Color(0.45f, 0.6f, 1f), rimIntensity = 0.6f,
                ambSky = new Color(0.12f, 0.15f, 0.26f), ambEquator = new Color(0.09f, 0.09f, 0.14f), ambGround = new Color(0.04f, 0.04f, 0.05f),
                sky = true, skyTop = new Color(0.01f, 0.015f, 0.04f), skyHorizon = new Color(0.07f, 0.08f, 0.16f), skyGlow = new Color(0.4f, 0.45f, 0.7f), glow = 0.15f,
                background = new Color(0.02f, 0.03f, 0.06f), fogColor = new Color(0.05f, 0.06f, 0.11f), fogDensity = 0.03f, sceneKey = 14f,
                exposure = 0.6f, contrast = 18, saturation = 6, temperature = -12, bloom = 1.4f, bloomThreshold = 0.8f, vignette = 0.35f,
                shadowsTint = new Color(0.85f, 0.9f, 1f), practicals = true, practicalIntensity = 7f, practicalRange = 11f, dof = 1 },
            ["interior_warm"] = new Look { name = "interior_warm", keyColor = new Color(1f, 0.86f, 0.68f), keyIntensity = 1.2f, keyPitch = 35, keyYawOffset = -65,
                fillColor = new Color(1f, 0.8f, 0.6f), fillIntensity = 0.2f, rimColor = new Color(1f, 0.8f, 0.6f), rimIntensity = 0.45f,
                ambSky = new Color(0.4f, 0.34f, 0.3f), ambEquator = new Color(0.36f, 0.29f, 0.23f), ambGround = new Color(0.2f, 0.15f, 0.11f),
                sky = false, background = new Color(0.14f, 0.11f, 0.09f), fog = false,
                temperature = 14, saturation = 6, contrast = 10, bloom = 0.6f, vignette = 0.3f, practicals = true, practicalIntensity = 3.5f, practicalRange = 7f, dof = 1 },
            ["studio"] = new Look { name = "studio", keyColor = Color.white, keyIntensity = 2.0f, keyPitch = 38, keyYawOffset = -45,
                fillColor = new Color(0.85f, 0.9f, 1f), fillIntensity = 0.45f, rimColor = Color.white, rimIntensity = 1.1f,
                ambSky = new Color(0.45f, 0.46f, 0.5f), ambEquator = new Color(0.4f, 0.4f, 0.42f), ambGround = new Color(0.25f, 0.25f, 0.26f),
                sky = false, background = new Color(0.16f, 0.17f, 0.2f), fogColor = new Color(0.16f, 0.17f, 0.2f), fogDensity = 0.03f,
                contrast = 6, saturation = 0, bloom = 0.15f, vignette = 0.25f },
        };

        public static Look Get(string name)
        {
            if (string.IsNullOrEmpty(name)) name = "day";
            if (!All.TryGetValue(name, out var l)) throw new System.Exception($"unknown lighting preset {name}; one of {string.Join(", ", All.Keys)}");
            return l;
        }

        public class Rig { public Light key, fill, rim; public Volume volume; public Look look; }

        /// Creates lights, sky, fog and the post volume. Key light yaw is relative to the camera's viewing yaw unless
        /// a fixed keyYaw is given (keeps lighting consistent across the shots of one scene).
        public static Rig Apply(Look l, LightSpec spec, float cameraYaw)
        {
            var rig = new Rig { look = l };
            float yaw = float.IsNaN(spec.keyYaw) ? cameraYaw + l.keyYawOffset : spec.keyYaw;
            rig.key = Dir("Key", l.keyColor, l.keyIntensity, l.keyPitch, yaw, LightShadows.Soft, l.shadowStrength);
            if (l.fillIntensity > 0) rig.fill = Dir("Fill", l.fillColor, l.fillIntensity, 20, yaw + 120, LightShadows.None, 0);
            if (l.rimIntensity > 0) rig.rim = Dir("Rim", l.rimColor, l.rimIntensity, 25, cameraYaw + 180 + 35, LightShadows.None, 0);
            RenderSettings.sun = rig.key;

            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = l.ambSky * l.ambientScale;
            RenderSettings.ambientEquatorColor = l.ambEquator * l.ambientScale;
            RenderSettings.ambientGroundColor = l.ambGround * l.ambientScale;
            RenderSettings.reflectionIntensity = l.sky ? 0.6f : 0.3f;
            RenderSettings.defaultReflectionMode = DefaultReflectionMode.Skybox;
            if (l.sky)
            {
                // Gradient sky with a glow toward the key light: full control over the mood (the procedural sky turns
                // green at low sun angles).
                var sky = new Material(Shader.Find("Skybox/Panoramic"));
                sky.SetTexture("_MainTex", SkyTexture(l, yaw));
                sky.SetFloat("_Mapping", 1); // latitude-longitude
                sky.SetFloat("_Exposure", 1f);
                RenderSettings.skybox = sky;
            }
            else RenderSettings.skybox = null;
            RenderSettings.fog = l.fog;
            RenderSettings.fogMode = FogMode.ExponentialSquared;
            RenderSettings.fogColor = l.fogColor;
            RenderSettings.fogDensity = l.fogDensity;
            DynamicGI.UpdateEnvironment();

            var vgo = new GameObject("Post");
            var vol = vgo.AddComponent<Volume>();
            vol.isGlobal = true;
            var p = ScriptableObject.CreateInstance<VolumeProfile>();
            var tm = p.Add<Tonemapping>(true); tm.mode.Override(TonemappingMode.ACES);
            var ca = p.Add<ColorAdjustments>(true);
            ca.postExposure.Override(l.exposure + spec.exposure);
            ca.contrast.Override(l.contrast); ca.saturation.Override(l.saturation);
            var wb = p.Add<WhiteBalance>(true); wb.temperature.Override(l.temperature); wb.tint.Override(l.tint);
            var bl = p.Add<Bloom>(true); bl.intensity.Override(l.bloom); bl.threshold.Override(l.bloomThreshold); bl.scatter.Override(0.7f); bl.highQualityFiltering.Override(true);
            var vg = p.Add<Vignette>(true); vg.intensity.Override(l.vignette); vg.smoothness.Override(0.45f);
            var smh = p.Add<ShadowsMidtonesHighlights>(true);
            smh.shadows.Override(new Vector4(l.shadowsTint.r, l.shadowsTint.g, l.shadowsTint.b, 0));
            smh.highlights.Override(new Vector4(l.highlightsTint.r, l.highlightsTint.g, l.highlightsTint.b, 0));
            var fg = p.Add<FilmGrain>(true); fg.type.Override(FilmGrainLookup.Thin1); fg.intensity.Override(0.12f); fg.response.Override(0.8f);
            vol.sharedProfile = p;
            rig.volume = vol;
            return rig;
        }

        /// Depth of field focused at `distance` metres (Bokeh, gentle). Called once the camera knows its subject.
        public static void Focus(Rig rig, float distance, float fovDeg)
        {
            if (rig.look.dof <= 0) return;
            var p = rig.volume.sharedProfile;
            if (!p.TryGet<DepthOfField>(out var d)) d = p.Add<DepthOfField>(true);
            d.mode.Override(DepthOfFieldMode.Bokeh);
            d.focusDistance.Override(Mathf.Max(0.5f, distance));
            // Longer lenses (small fov) get a shallower depth of field, like real glass.
            d.focalLength.Override(Mathf.Clamp(24f / Mathf.Tan(fovDeg * 0.5f * Mathf.Deg2Rad) * 0.6f, 35f, 120f));
            d.aperture.Override(Mathf.Lerp(8f, 2.8f, Mathf.Clamp01(rig.look.dof)));
        }

        static Texture2D SkyTexture(Look l, float sunYaw)
        {
            const int W = 512, H = 256;
            var t = new Texture2D(W, H, TextureFormat.RGBAHalf, false) { wrapModeU = TextureWrapMode.Repeat, wrapModeV = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear };
            var px = new Color[W * H];
            // Direction toward the sun: the key light shines along its forward vector, so the sun sits opposite.
            var toSun = -(Quaternion.Euler(Mathf.Max(2f, l.keyPitch * 0.6f), sunYaw, 0) * Vector3.forward);
            for (int y = 0; y < H; y++)
            {
                float lat = (y / (float)(H - 1) - 0.5f) * Mathf.PI;
                for (int x = 0; x < W; x++)
                {
                    float lon = (x / (float)W) * 2 * Mathf.PI - Mathf.PI;
                    var d = new Vector3(Mathf.Sin(lon) * Mathf.Cos(lat), Mathf.Sin(lat), -Mathf.Cos(lon) * Mathf.Cos(lat));
                    float up = Mathf.Clamp01(d.y);
                    Color c = d.y >= 0 ? Color.Lerp(l.skyHorizon, l.skyTop, Mathf.Pow(up, 0.55f)) : Color.Lerp(l.skyHorizon, l.fogColor * 0.6f, Mathf.Clamp01(-d.y * 4));
                    float g = Mathf.Max(0, Vector3.Dot(d, toSun));
                    c += l.skyGlow * (l.glow * Mathf.Pow(g, 6) + l.glow * 2.5f * Mathf.Pow(g, 200));
                    px[y * W + x] = c;
                }
            }
            t.SetPixels(px); t.Apply(false);
            return t;
        }

        static Light Dir(string name, Color c, float intensity, float pitch, float yaw, LightShadows sh, float strength)
        {
            var l = new GameObject(name).AddComponent<Light>();
            l.type = LightType.Directional; l.color = c; l.intensity = intensity; l.shadows = sh; l.shadowStrength = strength;
            l.shadowBias = 0.05f; l.shadowNormalBias = 0.4f;
            l.transform.rotation = Quaternion.Euler(pitch, yaw, 0);
            return l;
        }

        public static Light Point(Vector3 pos, Color c, float intensity, float range, bool shadows)
        {
            var l = new GameObject("Practical").AddComponent<Light>();
            l.type = LightType.Point; l.color = c; l.intensity = intensity; l.range = range;
            l.shadows = shadows ? LightShadows.Soft : LightShadows.None; l.shadowStrength = 0.8f;
            l.transform.position = pos;
            return l;
        }
    }
}
