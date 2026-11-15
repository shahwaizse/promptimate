// Project setup from code (ProjectSettings are not in git): URP asset, character import as Humanoid, URP materials,
// a studio look, and script-stepped physics.
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace SystemLab
{
    public class LabCharacterImport : AssetPostprocessor
    {
        public override uint GetVersion() => 1;

        void OnPreprocessModel()
        {
            if (!assetPath.StartsWith("Assets/Characters/")) return;
            var mi = (ModelImporter)assetImporter;
            mi.animationType = ModelImporterAnimationType.Human;
            mi.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            mi.importAnimation = false;
            mi.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            mi.materialLocation = ModelImporterMaterialLocation.InPrefab;
            mi.materialSearch = ModelImporterMaterialSearch.Local;
            mi.materialName = ModelImporterMaterialName.BasedOnTextureName;
        }
    }

    public static class LabSetup
    {
        const string Dir = "Assets/SystemLab/Generated";

        public static void Ensure()
        {
            if (!AssetDatabase.IsValidFolder(Dir)) AssetDatabase.CreateFolder("Assets/SystemLab", "Generated");
            var path = Dir + "/LabURP.asset";
            var asset = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(path);
            if (asset == null)
            {
                var rd = ScriptableObject.CreateInstance<UniversalRendererData>();
                AssetDatabase.CreateAsset(rd, Dir + "/LabURP_Renderer.asset");
                var ssao = ScriptableObject.CreateInstance<ScreenSpaceAmbientOcclusion>();
                ssao.name = "SSAO";
                AssetDatabase.AddObjectToAsset(ssao, rd);
                rd.rendererFeatures.Add(ssao);
                var so0 = new SerializedObject(ssao);
                var st = so0.FindProperty("m_Settings");
                if (st != null)
                {
                    void F(string n, float v) { var p = st.FindPropertyRelative(n); if (p != null) p.floatValue = v; }
                    F("Intensity", 1.2f); F("Radius", 0.3f); F("DirectLightingStrength", 0.3f);
                    var src = st.FindPropertyRelative("Source"); if (src != null) src.intValue = 1;
                    so0.ApplyModifiedPropertiesWithoutUndo();
                }
                asset = UniversalRenderPipelineAsset.Create(rd);
                AssetDatabase.CreateAsset(asset, path);
                asset.shadowDistance = 40f; asset.shadowCascadeCount = 4;
                asset.mainLightShadowmapResolution = 4096; asset.supportsHDR = true; asset.msaaSampleCount = 4;
                asset.shadowDepthBias = 0.6f; asset.shadowNormalBias = 0.5f;
                var so = new SerializedObject(asset);
                void B(string n, bool v) { var p = so.FindProperty(n); if (p != null) p.boolValue = v; }
                void I(string n, int v) { var p = so.FindProperty(n); if (p != null) p.intValue = v; }
                B("m_SoftShadowsSupported", true); I("m_SoftShadowQuality", 3); B("m_MainLightShadowsSupported", true);
                B("m_RequireDepthTexture", true);
                so.ApplyModifiedPropertiesWithoutUndo();
                EditorUtility.SetDirty(asset); EditorUtility.SetDirty(rd);
                AssetDatabase.SaveAssets();
            }
            GraphicsSettings.defaultRenderPipeline = asset;
            for (int i = 0; i < QualitySettings.names.Length; i++)
            {
                QualitySettings.SetQualityLevel(i, false);
                QualitySettings.renderPipeline = asset;
            }
            QualitySettings.SetQualityLevel(QualitySettings.names.Length - 1, true);
            ExtractTextures();
            Physics.simulationMode = SimulationMode.Script;
            Physics.gravity = new Vector3(0, -9.81f, 0);
            Physics.defaultSolverIterations = 16;
            Physics.defaultSolverVelocityIterations = 4;
            Physics.bounceThreshold = 1.5f;
            Physics.defaultContactOffset = 0.008f;
            Physics.sleepThreshold = 0.002f;
            Physics.defaultMaxAngularSpeed = 40f;
            Physics.IgnoreLayerCollision(ActiveRagdoll.Layer, ActiveRagdoll.Layer + 1, true);
        }

        static void ExtractTextures()
        {
            bool changed = false;
            foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { "Assets/Characters" }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var dir = Path.Combine(Path.GetDirectoryName(path), Path.GetFileNameWithoutExtension(path) + "_Textures").Replace('\\', '/');
                if (AssetDatabase.IsValidFolder(dir)) continue;
                Directory.CreateDirectory(dir);
                if (((ModelImporter)AssetImporter.GetAtPath(path)).ExtractTextures(dir)) changed = true;
            }
            if (changed) AssetDatabase.Refresh();
        }

        static Shader _lit;
        public static Shader Lit => _lit ? _lit : (_lit = Shader.Find("Universal Render Pipeline/Lit"));

        public static Material Mat(Color c, Texture tex = null, float smooth = 0.25f)
        {
            var m = new Material(Lit);
            m.SetColor("_BaseColor", c);
            if (tex) m.SetTexture("_BaseMap", tex);
            m.SetFloat("_Smoothness", smooth);
            return m;
        }

        /// Imported (built-in Standard) materials -> URP Lit, keeping albedo, colour and normal map.
        public static void ConvertMaterials(GameObject go, Texture skin = null)
        {
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                var mats = r.sharedMaterials;
                for (int i = 0; i < mats.Length; i++)
                {
                    var src = mats[i];
                    Texture tex = skin; Color col = Color.white;
                    if (src != null)
                    {
                        if (!tex && src.HasProperty("_MainTex")) tex = src.GetTexture("_MainTex");
                        if (!skin && src.HasProperty("_Color")) col = src.GetColor("_Color");
                    }
                    var m = Mat(col, tex, 0.2f);
                    if (src != null && src.HasProperty("_BumpMap") && src.GetTexture("_BumpMap"))
                    { m.SetTexture("_BumpMap", src.GetTexture("_BumpMap")); m.EnableKeyword("_NORMALMAP"); }
                    mats[i] = m;
                }
                r.sharedMaterials = mats;
                r.shadowCastingMode = ShadowCastingMode.On; r.receiveShadows = true;
            }
        }

        /// Soft studio daylight: warm key with soft shadows, cool fill, gradient ambient, light fog, ACES + bloom.
        public static void Look(float keyYaw = 35f)
        {
            Light Dir(string n, Color c, float i, float pitch, float yaw, LightShadows sh)
            {
                var l = new GameObject(n).AddComponent<Light>();
                l.type = LightType.Directional; l.color = c; l.intensity = i; l.shadows = sh; l.shadowStrength = 0.85f;
                l.shadowBias = 0.04f; l.shadowNormalBias = 0.35f;
                l.transform.rotation = Quaternion.Euler(pitch, yaw, 0);
                return l;
            }
            var key = Dir("Key", new Color(1f, 0.93f, 0.82f), 1.5f, 48, keyYaw, LightShadows.Soft);
            Dir("Fill", new Color(0.65f, 0.75f, 1f), 0.35f, 20, keyYaw + 140, LightShadows.None);
            Dir("Rim", new Color(1f, 0.95f, 0.9f), 0.6f, 25, keyYaw + 200, LightShadows.None);
            RenderSettings.sun = key;
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.55f, 0.62f, 0.75f);
            RenderSettings.ambientEquatorColor = new Color(0.45f, 0.45f, 0.47f);
            RenderSettings.ambientGroundColor = new Color(0.22f, 0.2f, 0.19f);
            RenderSettings.skybox = null;
            RenderSettings.fog = true; RenderSettings.fogMode = FogMode.ExponentialSquared;
            RenderSettings.fogColor = new Color(0.62f, 0.66f, 0.72f); RenderSettings.fogDensity = 0.045f;
            var vol = new GameObject("Post").AddComponent<Volume>();
            vol.isGlobal = true;
            var p = ScriptableObject.CreateInstance<VolumeProfile>();
            p.Add<Tonemapping>(true).mode.Override(TonemappingMode.ACES);
            var ca = p.Add<ColorAdjustments>(true); ca.postExposure.Override(-0.1f); ca.contrast.Override(8f); ca.saturation.Override(5f);
            var bl = p.Add<Bloom>(true); bl.intensity.Override(0.25f); bl.threshold.Override(1.1f);
            var vg = p.Add<Vignette>(true); vg.intensity.Override(0.22f); vg.smoothness.Override(0.45f);
            vol.sharedProfile = p;
        }

        /// Tileable two-tone grid texture for floors (reads scale and motion well on camera).
        public static Texture2D Grid(Color a, Color line, int size = 512, int cells = 4)
        {
            var t = new Texture2D(size, size, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Repeat, anisoLevel = 8, filterMode = FilterMode.Trilinear };
            var px = new Color[size * size];
            int cell = size / cells;
            var rnd = new System.Random(3);
            for (int y = 0; y < size; y++)
                for (int x = 0; x < size; x++)
                {
                    bool l = x % cell < 2 || y % cell < 2;
                    float n = (float)rnd.NextDouble() * 0.025f;
                    px[y * size + x] = (l ? line : a) * (1 - n);
                }
            t.SetPixels(px); t.Apply(true);
            return t;
        }
    }
}
