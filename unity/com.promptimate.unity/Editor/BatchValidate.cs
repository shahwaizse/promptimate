// Headless validation entry point:
//   Unity.exe -batchmode -nographics -projectPath <proj> -executeMethod Promptimate.Editor.BatchValidate.Run -quit
// Re-imports every .kimodo under Assets, prints one "TTA_REPORT <json>" line per clip, exits 1 if any fail.
using System.Collections.Generic;
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
            int code = RunCore(System.Environment.GetCommandLineArgs().Contains("-ttaSelfTest"), line => Debug.Log(line));
            EditorApplication.Exit(code);
        }

        /// Shared by the one-shot entry point (Run) and the warm ValidationServer: refreshes the AssetDatabase,
        /// force-reimports every .kimodo under Assets, emits the TTA_* lines in order and returns the exit code.
        public static int RunCore(bool selfTest, System.Action<string> emit)
        {
            System.Action<string> prev = Emit;
            Emit = emit;
            try
            {
                AssetDatabase.Refresh();
                var paths = AssetDatabase.GetAllAssetPaths().Where(p => p.StartsWith("Assets/") && p.EndsWith(".kimodo")).OrderBy(p => p, System.StringComparer.Ordinal).ToArray();
                int failed = 0;
                foreach (var p in paths)
                {
                    var reportPath = Path.Combine(KimodoValidator.ReportDir, Path.GetFileNameWithoutExtension(p) + ".json");
                    if (File.Exists(reportPath)) File.Delete(reportPath);
                    AssetDatabase.ImportAsset(p, ImportAssetOptions.ForceUpdate | ImportAssetOptions.ForceSynchronousImport);
                    if (!File.Exists(reportPath))
                    {
                        failed++;
                        Emit("TTA_REPORT {\"asset\":\"" + p + "\",\"passed\":false,\"failures\":[\"import produced no report\"]}");
                        continue;
                    }
                    var json = File.ReadAllText(reportPath);
                    if (!JsonUtility.FromJson<KimodoReport>(json).passed) failed++;
                    Emit("TTA_REPORT " + json.Replace("\n", "").Replace("\r", ""));
                }
                int selfTestErrors = selfTest && paths.Length > 0
                    ? SelfTest(PickSelfTestClip(paths)) + OptionSelfTest(PickTravelClip(paths)) : 0;
                Emit($"TTA_SUMMARY clips={paths.Length} failed={failed} selftest_errors={selfTestErrors}");
                return failed > 0 || selfTestErrors > 0 ? 1 : 0;
            }
            finally { Emit = prev; }
        }

        static System.Action<string> Emit = line => Debug.Log(line);

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
            Emit("TTA_SELFTEST_CLIP " + assetPath);
            var data = JsonUtility.FromJson<KimodoFile>(File.ReadAllText(assetPath));
            int errors = 0;
            foreach (KimodoImporter.ConversionVariant v in System.Enum.GetValues(typeof(KimodoImporter.ConversionVariant)))
            {
                KimodoImporter.Variant = v;
                try
                {
                    var opts = BakeOptions.Neutral;
                    var clip = KimodoImporter.Bake(data, "selftest_" + v, opts, out var avatar, out var err);
                    var rep = clip != null ? KimodoValidator.Validate(data, clip, avatar, opts) : null;
                    bool passed = rep != null && rep.passed;
                    string why = rep == null ? err : string.Join("; ", rep.failures);
                    bool expectPass = v == KimodoImporter.ConversionVariant.Correct;
                    bool ok = passed == expectPass;
                    if (!ok) errors++;
                    Emit($"TTA_SELFTEST variant={v} expected={(expectPass ? "pass" : "fail")} got={(passed ? "pass" : "fail")} {(ok ? "OK" : "WRONG")} :: {why}");
                    if (clip != null) Object.DestroyImmediate(clip);
                    if (avatar != null) Object.DestroyImmediate(avatar);
                }
                finally { KimodoImporter.Variant = KimodoImporter.ConversionVariant.Correct; }
            }
            return errors;
        }

        /// The clip that travels furthest (the in-place negative control needs real travel).
        static string PickTravelClip(string[] paths)
        {
            string best = paths[0]; float bestD = -1;
            foreach (var p in paths)
            {
                var d = JsonUtility.FromJson<KimodoFile>(File.ReadAllText(p));
                if (d.root == null || d.frames < 2) continue;
                int e = (d.frames - 1) * 3;
                float dist = new Vector2(d.root[e] - d.root[0], d.root[e + 2] - d.root[2]).magnitude;
                if (dist > bestD) { bestD = dist; best = p; }
            }
            return best;
        }

        /// Import options: valid combinations must PASS; clips that don't deliver what the options promise
        /// (travel not removed, no IK goals, no hand pose) must FAIL.
        static int OptionSelfTest(string assetPath)
        {
            Emit("TTA_SELFTEST_OPTIONS_CLIP " + assetPath);
            var src = JsonUtility.FromJson<KimodoFile>(File.ReadAllText(assetPath));
            int e = (src.frames - 1) * 3;
            float travel = new Vector2(src.root[e] - src.root[0], src.root[e + 2] - src.root[2]).magnitude;
            var neutral = BakeOptions.Neutral;
            BakeOptions With(System.Action<BakeOptions[]> f) { var o = new[] { neutral }; f(o); return o[0]; }
            var cases = new List<(string name, BakeOptions bake, BakeOptions expect, bool strip, bool expectPass)>
            {
                ("opt:LoopInPlaceRelaxed", With(o => { o[0].loop = o[0].loopPose = o[0].inPlace = true; o[0].hands = KimodoHandPose.Relaxed; }), default, true, true),
                ("opt:LoopPose", With(o => { o[0].loop = o[0].loopPose = true; }), default, false, true),
                ("opt:InPlace", With(o => o[0].inPlace = true), default, true, true),
                ("opt:RootMotionFist", With(o => o[0].hands = KimodoHandPose.Fist), default, false, true),
                ("opt:RootMotionOpenBakeRotationLoop", With(o => { o[0].hands = KimodoHandPose.Open; o[0].bakeRootRotation = true; o[0].loop = true; o[0].bakeRootHeight = false; }), default, false, true),
                ("neg:NoIKGoalCurves", With(o => o[0].ikGoals = false), neutral, false, false),
                ("neg:HandPoseMissing", neutral, With(o => o[0].hands = KimodoHandPose.Relaxed), false, false),
            };
            if (travel > 1f)
                cases.Add(("neg:InPlaceTravelNotRemoved", With(o => o[0].inPlace = true), default, false, false));
            else
                Emit($"TTA_SELFTEST_SKIP neg:InPlaceTravelNotRemoved (clip travels only {travel:F2} m)");

            int errors = 0;
            foreach (var (name, bake, expectArg, strip, expectPass) in cases)
            {
                var expect = expectArg.Equals(default(BakeOptions)) ? bake : expectArg;
                var data = strip ? KimodoImporter.MakeInPlace(src) : src;
                var clip = KimodoImporter.Bake(data, "selftest_" + name, bake, out var avatar, out var err);
                var rep = clip != null ? KimodoValidator.Validate(data, clip, avatar, expect) : null;
                bool passed = rep != null && rep.passed;
                string why = rep == null ? err : string.Join("; ", rep.failures);
                bool ok = passed == expectPass;
                if (!ok) errors++;
                Emit($"TTA_SELFTEST variant={name} expected={(expectPass ? "pass" : "fail")} got={(passed ? "pass" : "fail")} {(ok ? "OK" : "WRONG")} :: {why}");
                if (rep != null) Emit("TTA_SELFTEST_REPORT " + JsonUtility.ToJson(rep));
                if (clip != null) Object.DestroyImmediate(clip);
                if (avatar != null) Object.DestroyImmediate(avatar);
            }
            return errors;
        }
    }
}
