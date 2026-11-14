// Any model dropped under Assets/Characters is imported as a Humanoid (Mixamo, Kenney, ... all auto-map).
// Mixamo "FBX for Unity" files embed their textures; we extract them next to the model so materials pick them up.
using System.IO;
using UnityEditor;

public class HumanoidModelPostprocessor : AssetPostprocessor
{
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

    /// Extracts embedded textures of every character model once (batch-safe; call before using characters).
    public static void EnsureTextures()
    {
        bool changed = false;
        foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { "Assets/Characters" }))
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            var dir = Path.Combine(Path.GetDirectoryName(path), Path.GetFileNameWithoutExtension(path) + "_Textures").Replace(Path.DirectorySeparatorChar, '/');
            if (AssetDatabase.IsValidFolder(dir)) continue;
            Directory.CreateDirectory(dir);
            var mi = (ModelImporter)AssetImporter.GetAtPath(path);
            if (mi.ExtractTextures(dir)) changed = true;
            UnityEngine.Debug.Log($"extracted textures for {path} -> {dir}");
        }
        if (!changed) return;
        AssetDatabase.Refresh();
        foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { "Assets/Characters" }))
            AssetDatabase.ImportAsset(AssetDatabase.GUIDToAssetPath(guid), ImportAssetOptions.ForceUpdate);
    }
}
