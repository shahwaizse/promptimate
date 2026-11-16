// Import settings for the fetched third-party assets: normal maps, linear mask/specular maps, Rocketbox avatars as
// Humanoid rigs with their own materials left to Characters.cs.
using UnityEditor;
using UnityEngine;

namespace Fidelity
{
    public class ImportRules : AssetPostprocessor
    {
        void OnPreprocessTexture()
        {
            if (!assetPath.StartsWith("Assets/ThirdParty/")) return;
            var t = (TextureImporter)assetImporter;
            string n = System.IO.Path.GetFileNameWithoutExtension(assetPath).ToLowerInvariant();
            if (assetPath.Contains("/HDRI/")) return; // Lib.HDRI sets cube import
            t.maxTextureSize = assetPath.Contains("/Rocketbox/") ? 2048 : 4096;
            if (n.Contains("_nor_gl") || n.EndsWith("_normal") || n.Contains("_normal_"))
            {
                t.textureType = TextureImporterType.NormalMap;
            }
            else if (n.Contains("_mask_") || n.Contains("_arm_") || n.Contains("_rough") || n.EndsWith("_specular") || n.Contains("_ao_"))
            {
                t.textureType = TextureImporterType.Default;
                t.sRGBTexture = false;
            }
            if (n.Contains("opacity")) t.alphaSource = TextureImporterAlphaSource.FromInput;
            t.textureCompression = TextureImporterCompression.CompressedHQ;
            t.anisoLevel = 8;
        }

        void OnPreprocessModel()
        {
            if (!assetPath.Contains("/Rocketbox/")) return;
            var m = (ModelImporter)assetImporter;
            m.animationType = ModelImporterAnimationType.Human;
            m.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            m.importAnimation = false;
            m.importBlendShapes = true;
            m.importBlendShapeNormals = ModelImporterNormals.Calculate;
            m.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            m.isReadable = true;
            m.optimizeGameObjects = false;
        }
    }
}
