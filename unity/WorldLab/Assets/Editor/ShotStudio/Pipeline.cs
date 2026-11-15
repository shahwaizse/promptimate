// URP setup for the shot renderer, created from code so a fresh clone needs no hand-made settings assets
// (DemoStudio's ProjectSettings are not in git). Assets live in Assets/ShotStudio/Generated (gitignored).
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace ShotStudio
{
    public static class Pipeline
    {
        const string Dir = "Assets/ShotStudio/Generated";
        const string AssetPath = Dir + "/ShotURP.asset";
        const string RendererPath = Dir + "/ShotURP_Renderer.asset";
        const int Version = 5; // WorldLab: softer SSAO (rooms are full of contact edges) // bump to rebuild the asset when settings below change

        public static UniversalRenderPipelineAsset Ensure()
        {
            var asset = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(AssetPath);
            if (asset == null || EditorPrefs.GetInt("ShotStudio.PipelineVersion." + Application.dataPath, 0) != Version)
            {
                if (!AssetDatabase.IsValidFolder("Assets/ShotStudio")) AssetDatabase.CreateFolder("Assets", "ShotStudio");
                if (!AssetDatabase.IsValidFolder(Dir)) AssetDatabase.CreateFolder("Assets/ShotStudio", "Generated");
                AssetDatabase.DeleteAsset(AssetPath);
                AssetDatabase.DeleteAsset(RendererPath);
                var rd = ScriptableObject.CreateInstance<UniversalRendererData>();
                AssetDatabase.CreateAsset(rd, RendererPath);
                // Screen-space ambient occlusion as a renderer feature (contact shadows under feet, in folds, at walls).
                var ssao = ScriptableObject.CreateInstance<ScreenSpaceAmbientOcclusion>();
                ssao.name = "SSAO";
                AssetDatabase.AddObjectToAsset(ssao, rd);
                rd.rendererFeatures.Add(ssao);
                SetSsao(ssao);
                rd.SetDirty();
                asset = UniversalRenderPipelineAsset.Create(rd);
                AssetDatabase.CreateAsset(asset, AssetPath);
                Configure(asset);
                EditorUtility.SetDirty(asset);
                EditorUtility.SetDirty(rd);
                AssetDatabase.SaveAssets();
                EditorPrefs.SetInt("ShotStudio.PipelineVersion." + Application.dataPath, Version);
            }
            Use(asset);
            return asset;
        }

        /// Activates URP (also for every quality level, which otherwise overrides the default).
        public static void Use(RenderPipelineAsset asset)
        {
            GraphicsSettings.defaultRenderPipeline = asset;
            for (int i = 0; i < QualitySettings.names.Length; i++)
            {
                QualitySettings.SetQualityLevel(i, false);
                QualitySettings.renderPipeline = asset;
            }
            QualitySettings.SetQualityLevel(QualitySettings.names.Length - 1, true);
        }

        static void Configure(UniversalRenderPipelineAsset a)
        {
            a.shadowDistance = 45f;
            a.shadowCascadeCount = 4;
            a.cascade4Split = new Vector3(0.06f, 0.18f, 0.45f);
            a.mainLightShadowmapResolution = 4096;
            a.additionalLightsShadowmapResolution = 2048;
            a.supportsHDR = true;
            a.msaaSampleCount = 4;
            a.renderScale = 1f;
            a.shadowDepthBias = 0.6f;
            a.shadowNormalBias = 0.5f;
            a.maxAdditionalLightsCount = 8;
            a.colorGradingMode = ColorGradingMode.HighDynamicRange;
            a.colorGradingLutSize = 32;
            // Fields without public setters in URP 17: soft shadow quality, additional-light shadows, per-pixel lights.
            var so = new SerializedObject(a);
            void Set(string prop, System.Action<SerializedProperty> f) { var p = so.FindProperty(prop); if (p != null) f(p); else Debug.LogWarning("ShotStudio: URP asset has no " + prop); }
            Set("m_SoftShadowsSupported", p => p.boolValue = true);
            Set("m_SoftShadowQuality", p => p.intValue = 3); // High
            Set("m_AdditionalLightsRenderingMode", p => p.intValue = 1); // per pixel
            Set("m_AdditionalLightShadowsSupported", p => p.boolValue = true);
            Set("m_MainLightShadowsSupported", p => p.boolValue = true);
            Set("m_RequireDepthTexture", p => p.boolValue = true);
            Set("m_RequireOpaqueTexture", p => p.boolValue = false);
            so.ApplyModifiedPropertiesWithoutUndo();
        }

        static void SetSsao(ScreenSpaceAmbientOcclusion ssao)
        {
            // URP keeps the settings in a private field; set the strength through serialization.
            var so = new SerializedObject(ssao);
            var s = so.FindProperty("m_Settings");
            if (s == null) return;
            void F(string n, float v) { var p = s.FindPropertyRelative(n); if (p != null) p.floatValue = v; }
            void I(string n, int v) { var p = s.FindPropertyRelative(n); if (p != null) p.intValue = v; }
            void B(string n, bool v) { var p = s.FindPropertyRelative(n); if (p != null) p.boolValue = v; }
            F("Intensity", 0.75f); F("Radius", 0.22f); F("DirectLightingStrength", 0.2f); F("Falloff", 40f);
            B("Downsample", false); I("Samples", 0); I("BlurQuality", 0);
            B("AfterOpaque", false);
            I("Source", 1); // depth-normals
            so.ApplyModifiedPropertiesWithoutUndo();
        }
    }
}
