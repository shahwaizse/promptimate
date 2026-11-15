// Renders several DemoRenderer shots in one editor session:  -executeMethod RenderShots.Run -shots a.json;b.json
using System.IO;
using UnityEditor;
using UnityEngine;

public static class RenderShots
{
    public static void Run()
    {
        var a = System.Environment.GetCommandLineArgs();
        int i = System.Array.IndexOf(a, "-shots"), code = 0;
        // -beforeClips a.kimodo;b.kimodo : re-import these with the pre-fix SOMA rest pose (toe joint on the floor), for
        // before/after renders of the sole calibration. Uses the importer's self-test switch via reflection.
        int bi = System.Array.IndexOf(a, "-beforeClips");
        if (bi >= 0)
        {
            var t = System.Type.GetType("Promptimate.Editor.KimodoImporter, Promptimate.Editor");
            var fld = t.GetField("SkipSoleShift", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
            fld.SetValue(null, true);
            try { foreach (var c in a[bi + 1].Split(';')) AssetDatabase.ImportAsset(c, ImportAssetOptions.ForceUpdate | ImportAssetOptions.ForceSynchronousImport); }
            finally { fld.SetValue(null, false); }
        }
        foreach (var p in a[i + 1].Split(';'))
        {
            try { DemoRenderer.Render(JsonUtility.FromJson<DemoRenderer.Shot>(File.ReadAllText(p))); }
            catch (System.Exception e) { Debug.LogError("DEMO_ERROR " + p + " " + e); code = 1; }
        }
        EditorApplication.Exit(code);
    }
}
