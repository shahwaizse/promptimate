// Headless validation entry point:
//   Unity.exe -batchmode -nographics -projectPath <proj> -executeMethod Promptimate.Editor.BatchValidate.Run -quit
// Re-imports every .kimodo under Assets, prints one "TTA_REPORT <json>" line per clip, exits 1 if any fail.
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Promptimate.Editor
{
    public static class BatchValidate
    {
        public static void Run()
        {
            AssetDatabase.Refresh();
            var paths = AssetDatabase.GetAllAssetPaths().Where(p => p.StartsWith("Assets/") && p.EndsWith(".kimodo")).ToArray();
            int failed = 0;
            foreach (var p in paths)
            {
                var reportPath = Path.Combine(KimodoValidator.ReportDir, Path.GetFileNameWithoutExtension(p) + ".json");
                if (File.Exists(reportPath)) File.Delete(reportPath);
                AssetDatabase.ImportAsset(p, ImportAssetOptions.ForceUpdate | ImportAssetOptions.ForceSynchronousImport);
                if (!File.Exists(reportPath))
                {
                    failed++;
                    Debug.Log("TTA_REPORT {\"asset\":\"" + p + "\",\"passed\":false,\"failures\":[\"import produced no report\"]}");
                    continue;
                }
                var json = File.ReadAllText(reportPath);
                if (!JsonUtility.FromJson<KimodoReport>(json).passed) failed++;
                Debug.Log("TTA_REPORT " + json.Replace("\n", "").Replace("\r", ""));
            }
            int selfTestErrors = System.Environment.GetCommandLineArgs().Contains("-ttaSelfTest") && paths.Length > 0
                ? SelfTest(PickSelfTestClip(paths)) : 0;
            Debug.Log($"TTA_SUMMARY clips={paths.Length} failed={failed} selftest_errors={selfTestErrors}");
            EditorApplication.Exit(failed > 0 || selfTestErrors > 0 ? 1 : 0);
        }

        /// The negative controls need the FK reference (refPos) and a clip that is not meant to move backward,
        /// otherwise unconverted quaternions / a flipped root are undetectable. Prefer such a clip.
        static string PickSelfTestClip(string[] paths)
        {
            foreach (var p in paths)
            {
                var d = JsonUtility.FromJson<KimodoFile>(File.ReadAllText(p));
                if (d.refPos != null && d.refPos.Length > 0 && !(d.prompt ?? "").ToLowerInvariant().Contains("backward"))
                    return p;
            }
            return paths[0];
        }

        /// Negative controls: deliberately broken conversions must FAIL validation, the correct one must PASS.
        static int SelfTest(string assetPath)
        {
            Debug.Log("TTA_SELFTEST_CLIP " + assetPath);
            var data = JsonUtility.FromJson<KimodoFile>(File.ReadAllText(assetPath));
            int errors = 0;
            foreach (KimodoImporter.ConversionVariant v in System.Enum.GetValues(typeof(KimodoImporter.ConversionVariant)))
            {
                KimodoImporter.Variant = v;
                try
                {
                    var clip = KimodoImporter.Bake(data, "selftest_" + v, false, out var avatar, out var err);
                    bool passed = clip != null && KimodoValidator.Validate(data, clip, avatar).passed;
                    string why = clip == null ? err : string.Join("; ", KimodoValidator.Validate(data, clip, avatar).failures);
                    bool expectPass = v == KimodoImporter.ConversionVariant.Correct;
                    bool ok = passed == expectPass;
                    if (!ok) errors++;
                    Debug.Log($"TTA_SELFTEST variant={v} expected={(expectPass ? "pass" : "fail")} got={(passed ? "pass" : "fail")} {(ok ? "OK" : "WRONG")} :: {why}");
                    if (clip != null) Object.DestroyImmediate(clip);
                    if (avatar != null) Object.DestroyImmediate(avatar);
                }
                finally { KimodoImporter.Variant = KimodoImporter.ConversionVariant.Correct; }
            }
            return errors;
        }
    }
}
