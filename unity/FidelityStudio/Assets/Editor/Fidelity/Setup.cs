// HDRP project setup for FidelityStudio, from code (ProjectSettings and pipeline assets are generated, not committed).
//   Unity.exe -batchmode -force-d3d12 -projectPath unity/FidelityStudio -executeMethod Fidelity.Setup.Run -quit
// Sets linear colour, DX12 (needed for DXR / the path tracer) and creates the HDRP asset with ray tracing on.
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

namespace Fidelity
{
    public static class Setup
    {
        const string Dir = "Assets/Fidelity/Generated";
        const string AssetPath = Dir + "/FidelityHDRP.asset";
        const int Version = 4;

        public static void Run()
        {
            Project();
            var a = Ensure();
            Debug.Log($"FID_SETUP ok device={SystemInfo.graphicsDeviceType} rt={SystemInfo.supportsRayTracing} gpu={SystemInfo.graphicsDeviceName} asset={a != null}");
        }

        public static void Project()
        {
            if (PlayerSettings.colorSpace != ColorSpace.Linear) PlayerSettings.colorSpace = ColorSpace.Linear;
            PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.StandaloneWindows64, false);
            PlayerSettings.SetGraphicsAPIs(BuildTarget.StandaloneWindows64, new[] { UnityEngine.Rendering.GraphicsDeviceType.Direct3D12 });
            GraphicsSettings.lightsUseLinearIntensity = true;
            GraphicsSettings.lightsUseColorTemperature = true;
        }

        public static HDRenderPipelineAsset Ensure()
        {
            var asset = AssetDatabase.LoadAssetAtPath<HDRenderPipelineAsset>(AssetPath);
            if (asset == null || EditorPrefs.GetInt("Fidelity.PipelineVersion." + Application.dataPath, 0) != Version)
            {
                if (!AssetDatabase.IsValidFolder("Assets/Fidelity")) AssetDatabase.CreateFolder("Assets", "Fidelity");
                if (!AssetDatabase.IsValidFolder(Dir)) AssetDatabase.CreateFolder("Assets/Fidelity", "Generated");
                if (asset == null)
                {
                    asset = ScriptableObject.CreateInstance<HDRenderPipelineAsset>();
                    AssetDatabase.CreateAsset(asset, AssetPath);
                }
                var s = asset.currentPlatformRenderPipelineSettings;
                s.supportRayTracing = true;
                s.supportedRayTracingMode = RenderPipelineSettings.SupportedRayTracingMode.Both;
                s.supportVolumetrics = true;
                s.supportSSR = true; s.supportSSAO = true; s.supportSSGI = true; s.supportSubsurfaceScattering = true;
                s.supportMotionVectors = true;
                s.supportDistortion = true; s.supportTransparentBackface = true;
                s.colorBufferFormat = RenderPipelineSettings.ColorBufferFormat.R16G16B16A16;
                s.supportedLitShaderMode = RenderPipelineSettings.SupportedLitShaderMode.Both;
                s.lodBias = new FloatScalableSetting(new[] { 2f, 2f, 2f }, ScalableSettingSchemaId.With3Levels);
                var sh = s.hdShadowInitParams;
                sh.maxShadowRequests = 128;
                sh.directionalShadowsDepthBits = DepthBits.Depth32;
                sh.punctualShadowFilteringQuality = HDShadowFilteringQuality.High; sh.directionalShadowFilteringQuality = HDShadowFilteringQuality.High;
                sh.cachedAreaLightShadowAtlas = 2048;
                sh.punctualLightShadowAtlas.shadowAtlasResolution = 8192;
                sh.areaLightShadowAtlas.shadowAtlasResolution = 4096;
                s.hdShadowInitParams = sh;
                var ll = s.lightLoopSettings;
                ll.maxDirectionalLightsOnScreen = 4; ll.maxPunctualLightsOnScreen = 64; ll.maxAreaLightsOnScreen = 16;
                s.lightLoopSettings = ll;
                asset.currentPlatformRenderPipelineSettings = s;
                EditorUtility.SetDirty(asset);
                AssetDatabase.SaveAssets();
                EditorPrefs.SetInt("Fidelity.PipelineVersion." + Application.dataPath, Version);
            }
            GraphicsSettings.defaultRenderPipeline = asset;
            for (int i = 0; i < QualitySettings.names.Length; i++)
            {
                QualitySettings.SetQualityLevel(i, false);
                QualitySettings.renderPipeline = asset;
            }
            QualitySettings.SetQualityLevel(QualitySettings.names.Length - 1, true);
            return asset;
        }
    }
}
