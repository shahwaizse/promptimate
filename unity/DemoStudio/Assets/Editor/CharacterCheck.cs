// "Works on any Mixamo character": plays every clip in Assets/Clips on every character in Assets/Characters and
// checks facing, travel direction, left/right and foot contact against the source motion (refPos in the .kimodo).
//   Unity.exe -batchmode -nographics -projectPath DemoStudio -executeMethod CharacterCheck.Run -quit
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

public static class CharacterCheck
{
    [System.Serializable] class Kim { public float fps; public int frames, joints; public string[] names; public float[] refPos; public string prompt; }
    [System.Serializable] public class Row
    {
        public string character, clip; public bool avatarHuman, passed; public List<string> failures = new List<string>();
        public float facingErrMaxDeg, travelErrDeg, toesForwardRatio, handednessRatio, groundedRatio;
    }
    [System.Serializable] class Report { public List<Row> rows = new List<Row>(); }

    static Vector3 Flat(Vector3 v) => new Vector3(v.x, 0, v.z);
    static Vector3 Fwd(Vector3 leftHip, Vector3 rightHip) => Vector3.Cross(Vector3.up, Flat(leftHip - rightHip)).normalized;

    public static void Run()
    {
        AssetDatabase.Refresh();
        HumanoidModelPostprocessor.EnsureTextures();
        var models = AssetDatabase.FindAssets("t:Model", new[] { "Assets/Characters" }).Select(AssetDatabase.GUIDToAssetPath).ToArray();
        var clips = AssetDatabase.FindAssets("", new[] { "Assets/Clips" }).Select(AssetDatabase.GUIDToAssetPath).Where(p => p.EndsWith(".kimodo")).ToArray();
        var only = System.Environment.GetCommandLineArgs().SkipWhile(a => a != "-clips").Skip(1).FirstOrDefault();
        if (only != null) clips = clips.Where(c => only.Split(',').Any(o => Path.GetFileNameWithoutExtension(c) == o)).ToArray();
        var report = new Report();
        foreach (var m in models)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(m);
            foreach (var c in clips)
            {
                var row = Check(prefab, m, c);
                report.rows.Add(row);
                Debug.Log("TTA_CHAR " + JsonUtility.ToJson(row));
            }
        }
        var outPath = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "demo", "character_report.json"));
        File.WriteAllText(outPath, JsonUtility.ToJson(report, true));
        int failed = report.rows.Count(r => !r.passed);
        Debug.Log($"TTA_CHAR_SUMMARY characters={models.Length} clips={clips.Length} runs={report.rows.Count} failed={failed}");
        EditorApplication.Exit(failed > 0 ? 1 : 0);
    }

    static Row Check(GameObject prefab, string modelPath, string clipPath)
    {
        var row = new Row { character = Path.GetFileNameWithoutExtension(modelPath), clip = Path.GetFileNameWithoutExtension(clipPath) };
        var go = (GameObject)Object.Instantiate(prefab);
        try
        {
            var anim = go.GetComponent<Animator>();
            row.avatarHuman = anim && anim.avatar && anim.avatar.isHuman;
            if (!row.avatarHuman) { row.failures.Add("model did not import as a valid Humanoid avatar"); return row; }
            anim.applyRootMotion = false;
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
            var src = JsonUtility.FromJson<Kim>(File.ReadAllText(clipPath));
            if (src.refPos == null || src.refPos.Length != src.frames * src.joints * 3) { row.failures.Add("clip has no refPos (re-export it)"); return row; }
            int J = src.joints, iL = System.Array.IndexOf(src.names, "LeftLeg"), iR = System.Array.IndexOf(src.names, "RightLeg"), iH = 0;
            Vector3 Ref(int f, int j) { int o = (f * J + j) * 3; return new Vector3(-src.refPos[o], src.refPos[o + 1], src.refPos[o + 2]); }

            Transform B(HumanBodyBones b) => anim.GetBoneTransform(b);
            Transform lUL = B(HumanBodyBones.LeftUpperLeg), rUL = B(HumanBodyBones.RightUpperLeg), lUA = B(HumanBodyBones.LeftUpperArm), rUA = B(HumanBodyBones.RightUpperArm);
            Transform lF = B(HumanBodyBones.LeftFoot), rF = B(HumanBodyBones.RightFoot), lT = B(HumanBodyBones.LeftToes), rT = B(HumanBodyBones.RightToes), hips = B(HumanBodyBones.Hips), head = B(HumanBodyBones.Head);
            clip.SampleAnimation(go, 0);
            float height = Mathf.Max(0.01f, head.position.y - Mathf.Min(lF.position.y, rF.position.y));
            int n = 0, toesN = 0, toesOk = 0, hand = 0, grounded = 0, step = Mathf.Max(1, src.frames / 30);
            Vector3 hips0 = Vector3.zero;
            for (int f = 0; f < src.frames; f += step)
            {
                clip.SampleAnimation(go, f / src.fps);
                if (f == 0) hips0 = hips.position;
                n++;
                var fwd = Fwd(lUL.position, rUL.position);
                row.facingErrMaxDeg = Mathf.Max(row.facingErrMaxDeg, Vector3.Angle(fwd, Fwd(Ref(f, iL), Ref(f, iR))));
                if (lT && rT)
                {
                    Vector3 a = Flat(lT.position - lF.position), b = Flat(rT.position - rF.position);
                    if (a.magnitude > 0.015f * height && b.magnitude > 0.015f * height) { toesN++; if (Vector3.Dot(a, fwd) > 0 && Vector3.Dot(b, fwd) > 0) toesOk++; }
                }
                if (Vector3.Dot(lUA.position - rUA.position, Vector3.Cross(fwd, Vector3.up)) > 0) hand++;
                float low = Mathf.Min(lF.position.y, rF.position.y);
                if (lT && rT) low = Mathf.Min(low, Mathf.Min(lT.position.y, rT.position.y));
                if (low - go.transform.position.y < 0.10f * height) grounded++;
            }
            row.toesForwardRatio = toesN > 0 ? (float)toesOk / toesN : 1;
            row.handednessRatio = (float)hand / n;
            row.groundedRatio = (float)grounded / n;
            int last = (src.frames - 1) / step * step;
            clip.SampleAnimation(go, last / src.fps);
            Vector3 travel = Flat(hips.position - hips0), srcTravel = Flat(Ref(last, iH) - Ref(0, iH));
            row.travelErrDeg = srcTravel.magnitude > 0.5f ? Vector3.Angle(travel, srcTravel) : 0;

            if (row.facingErrMaxDeg > 25) row.failures.Add($"facing differs from source by {row.facingErrMaxDeg:F0} deg");
            if (row.travelErrDeg > 25) row.failures.Add($"travels {row.travelErrDeg:F0} deg off the source direction");
            if (row.toesForwardRatio < 0.6f) row.failures.Add($"feet point forward in only {row.toesForwardRatio:P0} of frames");
            if (row.handednessRatio < 0.9f) row.failures.Add($"left/right correct in only {row.handednessRatio:P0} of frames");
            if (row.groundedRatio < 0.3f) row.failures.Add($"feet near ground in only {row.groundedRatio:P0} of frames");
            row.passed = row.failures.Count == 0;
            return row;
        }
        finally { Object.DestroyImmediate(go); }
    }
}
