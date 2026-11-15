// Import settings for the downloaded world library: GL normal maps as normal maps, HDRIs as clamped lat-long
// textures (no seam from mips/wrap), roughness as linear data.
using UnityEditor;
using UnityEngine;

public class WorldAssetPostprocessor : AssetPostprocessor
{
    public override uint GetVersion() => 3;

    void OnPreprocessTexture()
    {
        if (!assetPath.StartsWith("Assets/WorldAssets/")) return;
        var ti = (TextureImporter)assetImporter;
        string p = assetPath.ToLowerInvariant();
        if (p.Contains("_nor_gl") || p.Contains("normalgl") || p.EndsWith("_nor.jpg"))
        {
            ti.textureType = TextureImporterType.NormalMap;
            ti.sRGBTexture = false;
        }
        else if (p.Contains("_rough") || p.Contains("_arm") || p.Contains("_ao"))
            ti.sRGBTexture = false;
        if (p.EndsWith(".hdr") || p.EndsWith(".exr"))
        {
            ti.textureShape = TextureImporterShape.Texture2D;
            ti.mipmapEnabled = false;
            ti.wrapModeU = TextureWrapMode.Repeat; ti.wrapModeV = TextureWrapMode.Clamp;
            ti.maxTextureSize = 4096;
            ti.textureCompression = TextureImporterCompression.CompressedHQ;
        }
        else ti.maxTextureSize = 2048;
    }
}
