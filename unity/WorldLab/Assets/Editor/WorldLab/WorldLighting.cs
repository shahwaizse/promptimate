// Lights, sky and post from the physically derived values Python computed (Kelvin colours already white-balanced,
// intensities already exposure-normalised: 1.0 = a white surface at middle exposure). Unity just instantiates them.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace WorldLab
{
    public class LightRig { public List<Light> lights = new List<Light>(); public Volume volume; public Material sky; public float skyExposure = 1; public ReflectionProbe probe; }

    public static class WorldLighting
    {
        public static LightRig Apply(WorldJob job, BuiltWorld w, EffectsRig fx)
        {
            var rig = new LightRig();
            var env = job.env ?? new EnvSpec();
            // Sky: the HDRI is the view out of the windows and the reflection source; the room's ambient comes from
            // Python (window openness x sky + practical bounce), not from the sky, since walls block most of it.
            if (!string.IsNullOrEmpty(env.hdri))
            {
                var tex = UnityEditor.AssetDatabase.LoadAssetAtPath<Texture>(env.hdri);
                if (tex == null) Debug.LogWarning("WORLD missing hdri " + env.hdri);
                var sky = new Material(Shader.Find("Skybox/Panoramic"));
                sky.SetTexture("_MainTex", tex); sky.SetFloat("_Mapping", 1); sky.SetFloat("_ImageType", 0);
                sky.SetFloat("_Exposure", env.hdriExposure); sky.SetFloat("_Rotation", env.hdriRotation);
                RenderSettings.skybox = sky; rig.sky = sky; rig.skyExposure = env.hdriExposure;
            }
            else RenderSettings.skybox = null;
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = WorldBuilder.C(env.ambientSky, Color.gray);
            RenderSettings.ambientEquatorColor = WorldBuilder.C(env.ambientEquator, Color.gray);
            RenderSettings.ambientGroundColor = WorldBuilder.C(env.ambientGround, Color.gray);
            RenderSettings.defaultReflectionMode = DefaultReflectionMode.Skybox;
            RenderSettings.reflectionIntensity = env.reflection;
            RenderSettings.fog = env.fogDensity > 0;
            RenderSettings.fogMode = FogMode.ExponentialSquared;
            RenderSettings.fogDensity = env.fogDensity;
            RenderSettings.fogColor = WorldBuilder.C(env.fogColor, Color.gray);
            DynamicGI.UpdateEnvironment();

            int i = 0;
            foreach (var s in job.lights ?? new LightItem[0])
            {
                var l = new GameObject("L_" + (string.IsNullOrEmpty(s.id) ? (i++).ToString() : s.id)).AddComponent<Light>();
                l.type = s.type == "directional" ? LightType.Directional : s.type == "spot" ? LightType.Spot : LightType.Point;
                l.color = WorldBuilder.C(s.color, Color.white);
                l.intensity = s.intensity;
                l.range = s.range;
                l.shadows = s.shadows ? LightShadows.Soft : LightShadows.None;
                l.shadowStrength = 1; l.shadowBias = 0.02f; l.shadowNormalBias = 0.3f;
                if (l.type == LightType.Directional) l.shadowNormalBias = 0.5f;
                l.renderMode = LightRenderMode.ForcePixel;
                var pos = WorldBuilder.V(s.pos);
                var dir = WorldBuilder.V(s.dir); if (dir.sqrMagnitude < 1e-6f) dir = Vector3.down;
                if (!string.IsNullOrEmpty(s.attach) && w.items.TryGetValue(s.attach, out var it) && it.go)
                {
                    var rot = Quaternion.Euler(0, it.spec.yaw, 0);
                    pos = it.bottom + rot * pos;
                    dir = rot * dir;
                }
                l.transform.position = pos;
                l.transform.rotation = Quaternion.LookRotation(dir.normalized, Mathf.Abs(dir.normalized.y) > 0.95f ? Vector3.forward : Vector3.up);
                if (l.type == LightType.Spot) { l.spotAngle = s.angle; l.innerSpotAngle = Mathf.Min(s.inner, s.angle - 1); }
                if (s.glow == "bulb" || s.glow == "flame")
                {
                    var g = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                    g.name = "Glow_" + s.id; Object.DestroyImmediate(g.GetComponent<Collider>());
                    g.transform.position = pos; g.transform.localScale = s.glow == "flame" ? new Vector3(s.glowSize * 0.6f, s.glowSize * 1.6f, s.glowSize * 0.6f) : Vector3.one * s.glowSize;
                    var r = g.GetComponent<Renderer>(); r.sharedMaterial = ShotStudio.Materials.Emissive(l.color, s.glowIntensity); r.shadowCastingMode = ShadowCastingMode.Off;
                }
                if (s.flicker > 0) fx.flicker.Add((l, s.intensity, s.flicker, i * 17 + 3));
                if (s.role == "sun" || s.role == "moon") RenderSettings.sun = l;
                rig.lights.Add(l);
            }
            fx.sky = rig.sky; fx.skyBase = rig.skyExposure;

            // Box-projected reflection probe for the room (glossy floors, glass, metal pick up the actual room).
            var pgo = new GameObject("RoomProbe");
            var probe = pgo.AddComponent<ReflectionProbe>();
            probe.mode = ReflectionProbeMode.Realtime; probe.refreshMode = ReflectionProbeRefreshMode.ViaScripting;
            probe.timeSlicingMode = ReflectionProbeTimeSlicingMode.NoTimeSlicing;
            probe.boxProjection = true; probe.size = w.roomBounds.size + Vector3.one * 0.1f; probe.resolution = 256; probe.hdr = true;
            pgo.transform.position = w.roomBounds.center;
            probe.intensity = 1;
            rig.probe = probe;

            rig.volume = Post(job.post ?? new PostSpec());
            return rig;
        }

        static Volume Post(PostSpec s)
        {
            var vgo = new GameObject("Post");
            var vol = vgo.AddComponent<Volume>(); vol.isGlobal = true;
            var p = ScriptableObject.CreateInstance<VolumeProfile>();
            var tm = p.Add<Tonemapping>(true); tm.mode.Override(TonemappingMode.ACES);
            var ca = p.Add<ColorAdjustments>(true);
            ca.postExposure.Override(s.exposure); ca.contrast.Override(s.contrast); ca.saturation.Override(s.saturation);
            var wb = p.Add<WhiteBalance>(true); wb.temperature.Override(s.temperature); wb.tint.Override(s.tint);
            var bl = p.Add<Bloom>(true); bl.intensity.Override(s.bloom); bl.threshold.Override(s.bloomThreshold); bl.scatter.Override(0.72f); bl.highQualityFiltering.Override(true);
            var vg = p.Add<Vignette>(true); vg.intensity.Override(s.vignette); vg.smoothness.Override(0.45f);
            var smh = p.Add<ShadowsMidtonesHighlights>(true);
            smh.shadows.Override(Vec4(s.shadowsTint)); smh.highlights.Override(Vec4(s.highlightsTint));
            var fg = p.Add<FilmGrain>(true); fg.type.Override(FilmGrainLookup.Thin1); fg.intensity.Override(s.grain); fg.response.Override(0.8f);
            vol.sharedProfile = p;
            return vol;
        }

        static Vector4 Vec4(float[] a) => a == null || a.Length < 3 ? new Vector4(1, 1, 1, 0) : new Vector4(a[0], a[1], a[2], a.Length > 3 ? a[3] : 0);

        public static void Focus(LightRig rig, float distance, float fov, float strength)
        {
            if (strength <= 0) return;
            var p = rig.volume.sharedProfile;
            if (!p.TryGet<DepthOfField>(out var d)) d = p.Add<DepthOfField>(true);
            d.mode.Override(DepthOfFieldMode.Bokeh);
            d.focusDistance.Override(Mathf.Max(0.3f, distance));
            d.focalLength.Override(Mathf.Clamp(24f / Mathf.Tan(fov * 0.5f * Mathf.Deg2Rad) * 0.6f, 24f, 100f));
            d.aperture.Override(Mathf.Lerp(11f, 2.8f, Mathf.Clamp01(strength)));
        }
    }
}
