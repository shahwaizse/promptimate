// What users see on real characters: plays Promptimate clips on every humanoid in Assets/Characters through a
// PlayableGraph (Apply Root Motion on, like an Animator), with Foot IK off and on, and measures on the TARGET
// character's skinned mesh and bones:
//   skate   horizontal speed of a foot bone while the source foot is planted (cm/s)
//   float   sole height (lowest skinned foot vertex) above the floor while the source foot is planted (cm)
//   pen     deepest any skinned vertex goes below the floor (cm)
//   hand    hands inside the torso / head (cm, capsule/sphere fitted to the character's own mesh)
//   hyper   knee / elbow bent past straight the wrong way (deg; hinge axis calibrated from the avatar's muscles)
//   pops    frames whose hand/foot/head acceleration is far above the source's at that frame
// All lengths are normalised to a 1.75 m character. Source numbers (SOMA, from refPos) are printed alongside.
//   Unity.exe -batchmode -nographics -projectPath DemoStudio -executeMethod RetargetCheck.Run [-clips a,b] [-variant name] -quit
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

public static class RetargetCheck
{
    [System.Serializable] class Kim { public float fps; public int frames, joints; public string[] names; public float[] refPos; public string prompt; }

    [System.Serializable] public class Row
    {
        public string character, clip, variant; public bool footIK;
        public float heightM;                    // native standing height (before normalising)
        public float skateCms, skateP95Cms, srcSkateCms; // feet planted in the source
        public float floatCm, floatP95Cm;        // sole height while planted (target)
        public float penCm;                      // deepest vertex below floor (target), positive = below
        public string penBone; public int penFrame; // which bone's vertex, when
        public float srcPenCm;                   // source lowest joint below its own rest sole height (info)
        public float handTorsoCm, handHeadCm;    // max penetration depth
        public float handTorsoFrames, handHeadFrames; // fraction of frames with > 2 cm
        public float kneeHyperDeg, elbowHyperDeg;
        public int pops; public float popMaxRatio;
        public int contactFrames;
    }
    [System.Serializable] class Report { public List<Row> rows = new List<Row>(); }

    const float NormHeight = 1.75f;
    internal static bool Grounding;
    static string Arg(string n) { var a = System.Environment.GetCommandLineArgs(); int i = System.Array.IndexOf(a, n); return i >= 0 && i + 1 < a.Length ? a[i + 1] : null; }

    public static void Run()
    {
        int code = 0;
        try { RunCore(); }
        catch (System.Exception e) { Debug.LogError("TTA_RT_ERROR " + e); code = 1; }
        EditorApplication.Exit(code);
    }

    static void RunCore()
    {
        AssetDatabase.Refresh();
        var models = AssetDatabase.FindAssets("t:Model", new[] { "Assets/Characters" }).Select(AssetDatabase.GUIDToAssetPath).ToArray();
        var dir = Arg("-dir") ?? "Assets/Clips/Retarget";
        var clips = AssetDatabase.FindAssets("", new[] { dir }).Select(AssetDatabase.GUIDToAssetPath).Where(p => p.EndsWith(".kimodo")).Distinct().ToArray();
        var only = Arg("-clips");
        if (only != null) clips = clips.Where(c => only.Split(',').Any(o => Path.GetFileNameWithoutExtension(c) == o)).ToArray();
        string variant = Arg("-variant") ?? "current";
        Grounding = variant.Contains("grounding");
        var report = new Report();
        foreach (var m in models)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(m);
            foreach (var c in clips)
                foreach (bool ik in new[] { false, true })
                {
                    var row = Measure(prefab, c, ik);
                    row.variant = variant;
                    report.rows.Add(row);
                    Debug.Log("TTA_RT " + JsonUtility.ToJson(row));
                }
        }
        var outPath = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "demo", $"retarget_report_{variant}.json"));
        File.WriteAllText(outPath, JsonUtility.ToJson(report, true));
        Debug.Log($"TTA_RT_SUMMARY characters={models.Length} clips={clips.Length} rows={report.rows.Count} out={outPath}");
    }

    // ---- character model ---------------------------------------------------------------------------------------

    internal class Character
    {
        public GameObject go; public Animator anim; public float scale, nativeHeight;
        public Promptimate.PromptimateGrounding grounding; // variant "grounding": optional runtime helper
        public List<(Skin skin, int[] left, int[] right)> meshes = new List<(Skin, int[], int[])>();
        public float torsoR, headR; public Vector3 headCenterLocal; // in head bone space
        public Vector3 kneeAxisL, kneeAxisR, elbowAxisL, elbowAxisR;  // hinge axes in upper-limb local space
        public Transform B(HumanBodyBones b) => anim.GetBoneTransform(b);
    }

    internal static Character Load(GameObject prefab)
    {
        var ch = new Character { go = (GameObject)Object.Instantiate(prefab) };
        ch.anim = ch.go.GetComponent<Animator>();
        var head = ch.B(HumanBodyBones.Head); var lf = ch.B(HumanBodyBones.LeftFoot);
        // Bind pose: lowest vertex = floor reference, highest = top of head. Vertices are skinned by hand (bone
        // matrices x bind poses): BakeMesh gets the scale wrong on rigs with scaled bones (Kenney).
        var skins = ch.go.GetComponentsInChildren<SkinnedMeshRenderer>().Where(r => r.sharedMesh != null).Select(r => new Skin(r)).ToList();
        float lo = float.MaxValue, hi = float.MinValue;
        foreach (var sk in skins) foreach (var v in sk.World()) { lo = Mathf.Min(lo, v.y); hi = Mathf.Max(hi, v.y); }
        ch.nativeHeight = hi - lo;
        ch.scale = NormHeight / ch.nativeHeight;
        ch.go.transform.localScale *= ch.scale;
        ch.go.transform.position = Vector3.zero;
        // Sit the bind pose on the floor (characters whose origin isn't at the soles).
        float lo2 = skins.SelectMany(sk => sk.World()).Min(v => v.y);
        ch.go.transform.position = new Vector3(0, -lo2, 0);

        if (Grounding)
        {
            ch.grounding = ch.go.AddComponent<Promptimate.PromptimateGrounding>();
            ch.grounding.Calibrate(); // bind pose, final scale
            Debug.Log($"TTA_RT_GROUNDING {prefab.name} seatPoints={ch.grounding.seatPoints.Length} ankle={ch.grounding.ankleHeight:F3} footJoints={ch.grounding.leftFootJointHeights.Length}");
        }
        var footSet = new[] { HumanBodyBones.LeftFoot, HumanBodyBones.LeftToes, HumanBodyBones.RightFoot, HumanBodyBones.RightToes };
        var lFoot = ch.B(HumanBodyBones.LeftFoot); var rFoot = ch.B(HumanBodyBones.RightFoot);
        var torsoBones = new[] { HumanBodyBones.Spine, HumanBodyBones.Chest, HumanBodyBones.UpperChest }.Select(ch.B).Where(t => t).ToHashSet();
        var torsoD = new List<float>(); var headPts = new List<Vector3>();
        Vector3 hipsP = ch.B(HumanBodyBones.Hips).position, neckP = (ch.B(HumanBodyBones.Neck) ?? head).position;
        foreach (var sk in skins)
        {
            var vs = sk.World();
            var left = new List<int>(); var right = new List<int>();
            for (int i = 0; i < sk.w.Length; i++)
            {
                var b = sk.bones[sk.w[i].boneIndex0];
                if (b == null) continue;
                if (b == lFoot || b.IsChildOf(lFoot)) left.Add(i);
                else if (b == rFoot || b.IsChildOf(rFoot)) right.Add(i);
                else if (torsoBones.Contains(b)) torsoD.Add(SegDist(vs[i], hipsP, neckP));
                else if (b == head) headPts.Add(vs[i]);
            }
            ch.meshes.Add((sk, left.ToArray(), right.ToArray()));
        }
        torsoD.Sort();
        ch.torsoR = torsoD.Count > 0 ? torsoD[(int)(torsoD.Count * 0.25f)] : 0.12f;
        if (headPts.Count > 0)
        {
            var c = headPts.Aggregate(Vector3.zero, (a, b) => a + b) / headPts.Count;
            var d = headPts.Select(p => (p - c).magnitude).OrderBy(x => x).ToList();
            ch.headR = d[(int)(d.Count * 0.25f)];
            ch.headCenterLocal = head.InverseTransformPoint(c);
        }
        else { ch.headR = 0.09f; ch.headCenterLocal = head.InverseTransformPoint(head.position + Vector3.up * 0.09f); }

        // Hinge axes: bend each knee/elbow with its stretch muscle and read the bend plane in the upper bone's space.
        var hph = new HumanPoseHandler(ch.anim.avatar, ch.go.transform);
        var pose = new HumanPose(); hph.GetHumanPose(ref pose);
        var saved = pose.muscles.ToArray(); var savedPos = pose.bodyPosition; var savedRot = pose.bodyRotation;
        Vector3 Axis(string muscle, HumanBodyBones up, HumanBodyBones mid, HumanBodyBones end)
        {
            int mi = System.Array.IndexOf(HumanTrait.MuscleName, muscle);
            Vector3 best = Vector3.zero; float bestAng = -1;
            foreach (float v in new[] { -1f, 1f })
            {
                hph.GetHumanPose(ref pose);
                for (int k = 0; k < pose.muscles.Length; k++) pose.muscles[k] = 0;
                pose.muscles[mi] = v;
                hph.SetHumanPose(ref pose);
                Vector3 a = ch.B(mid).position - ch.B(up).position, b = ch.B(end).position - ch.B(mid).position;
                float ang = Vector3.Angle(a, b);
                if (ang > bestAng) { bestAng = ang; best = ch.B(up).InverseTransformDirection(Vector3.Cross(a, b).normalized); }
            }
            return best;
        }
        ch.kneeAxisL = Axis("Left Lower Leg Stretch", HumanBodyBones.LeftUpperLeg, HumanBodyBones.LeftLowerLeg, HumanBodyBones.LeftFoot);
        ch.kneeAxisR = Axis("Right Lower Leg Stretch", HumanBodyBones.RightUpperLeg, HumanBodyBones.RightLowerLeg, HumanBodyBones.RightFoot);
        ch.elbowAxisL = Axis("Left Forearm Stretch", HumanBodyBones.LeftUpperArm, HumanBodyBones.LeftLowerArm, HumanBodyBones.LeftHand);
        ch.elbowAxisR = Axis("Right Forearm Stretch", HumanBodyBones.RightUpperArm, HumanBodyBones.RightLowerArm, HumanBodyBones.RightHand);
        pose.muscles = saved; pose.bodyPosition = savedPos; pose.bodyRotation = savedRot;
        hph.SetHumanPose(ref pose);
        hph.Dispose();
        return ch;
    }

    /// Linear blend skinning done by hand, so the world vertex positions are right whatever the rig's scales.
    internal class Skin
    {
        public SkinnedMeshRenderer smr; public Vector3[] v; public BoneWeight[] w; public Matrix4x4[] bind; public Transform[] bones;
        Matrix4x4[] m;
        public Skin(SkinnedMeshRenderer r)
        {
            smr = r; v = r.sharedMesh.vertices; w = r.sharedMesh.boneWeights; bind = r.sharedMesh.bindposes; bones = r.bones;
            m = new Matrix4x4[bones.Length];
        }
        void Update() { for (int b = 0; b < bones.Length; b++) m[b] = bones[b] ? bones[b].localToWorldMatrix * bind[b] : smr.transform.localToWorldMatrix; }
        Vector3 P(int i)
        {
            var bw = w[i]; var x = v[i];
            if (w.Length == 0) return smr.transform.localToWorldMatrix.MultiplyPoint3x4(x);
            return m[bw.boneIndex0].MultiplyPoint3x4(x) * bw.weight0 + m[bw.boneIndex1].MultiplyPoint3x4(x) * bw.weight1
                 + m[bw.boneIndex2].MultiplyPoint3x4(x) * bw.weight2 + m[bw.boneIndex3].MultiplyPoint3x4(x) * bw.weight3;
        }
        public Vector3[] World() { Update(); var o = new Vector3[v.Length]; for (int i = 0; i < v.Length; i++) o[i] = P(i); return o; }
        /// Lowest y over a vertex subset (null = every 2nd vertex); call Refresh() first.
        public void Refresh() => Update();
        public float Lowest(int[] idx)
        {
            float lo = float.MaxValue;
            if (idx == null) { for (int i = 0; i < v.Length; i += 2) lo = Mathf.Min(lo, P(i).y); }
            else foreach (var i in idx) lo = Mathf.Min(lo, P(i).y);
            return lo;
        }
        public (float y, int i) LowestWithIndex()
        {
            float lo = float.MaxValue; int bi = -1;
            for (int i = 0; i < v.Length; i++) { float y = P(i).y; if (y < lo) { lo = y; bi = i; } }
            return (lo, bi);
        }
    }

    static float SegDist(Vector3 p, Vector3 a, Vector3 b)
    {
        var ab = b - a; float t = Mathf.Clamp01(Vector3.Dot(p - a, ab) / Mathf.Max(1e-8f, ab.sqrMagnitude));
        return (p - (a + ab * t)).magnitude;
    }

    /// Lowest left-foot vertex, right-foot vertex and whole-mesh vertex (world y).
    internal static (float l, float r, float all) Soles(Character ch)
    {
        float l = float.MaxValue, r = float.MaxValue, all = float.MaxValue;
        foreach (var (sk, left, right) in ch.meshes)
        {
            sk.Refresh();
            all = Mathf.Min(all, sk.Lowest(null));
            if (left.Length > 0) l = Mathf.Min(l, sk.Lowest(left));
            if (right.Length > 0) r = Mathf.Min(r, sk.Lowest(right));
        }
        return (l, r, all);
    }

    internal static float Hyper(Character ch, Vector3 axisLocal, HumanBodyBones up, HumanBodyBones mid, HumanBodyBones end)
    {
        Vector3 a = ch.B(mid).position - ch.B(up).position, b = ch.B(end).position - ch.B(mid).position;
        if (Vector3.Angle(a, b) > 90f) return 0f; // deeply flexed: SignedAngle wraps near 180 (a full fold), not hyperextension
        var axis = ch.B(up).TransformDirection(axisLocal);
        float s = Vector3.SignedAngle(a, Vector3.ProjectOnPlane(b, axis), axis);
        return Mathf.Max(0, -s);
    }

    // ---- measurement -------------------------------------------------------------------------------------------

    static Row Measure(GameObject prefab, string clipPath, bool footIK)
    {
        var row = new Row { character = prefab.name, clip = Path.GetFileNameWithoutExtension(clipPath), footIK = footIK };
        var ch = Load(prefab);
        var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
        var src = JsonUtility.FromJson<Kim>(File.ReadAllText(clipPath));
        int J = src.joints, F = src.frames; float fps = src.fps, dt = 1f / fps;
        Vector3 Ref(int f, string n) { int j = System.Array.IndexOf(src.names, n), o = (f * J + j) * 3; return new Vector3(-src.refPos[o], src.refPos[o + 1], src.refPos[o + 2]); }
        row.heightM = ch.nativeHeight;
        float srcH = Enumerable.Range(0, 1).Select(_ => Ref(0, "Head").y).First() * 1.1f; // SOMA standing height ~ head joint * 1.1
        float srcK = NormHeight / Mathf.Max(1f, srcH);

        // Source contacts per foot joint: near its own lowest height and slow.
        string[] srcJ = { "LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase" };
        var tgtB = new[] { HumanBodyBones.LeftFoot, HumanBodyBones.LeftToes, HumanBodyBones.RightFoot, HumanBodyBones.RightToes };
        var contact = new bool[4, F];
        var srcSpeedSum = 0.0; int srcSpeedN = 0;
        for (int k = 0; k < 4; k++)
        {
            float minY = Enumerable.Range(0, F).Min(f => Ref(f, srcJ[k]).y);
            for (int f = 0; f < F; f++)
            {
                int a = Mathf.Max(0, f - 1), b = Mathf.Min(F - 1, f + 1);
                float v = Flat(Ref(b, srcJ[k]) - Ref(a, srcJ[k])).magnitude / ((b - a) * dt);
                contact[k, f] = Ref(f, srcJ[k]).y < minY + 0.03f && v < 0.25f;
                if (contact[k, f]) { srcSpeedSum += v; srcSpeedN++; }
            }
        }
        row.srcSkateCms = srcSpeedN > 0 ? (float)(srcSpeedSum / srcSpeedN) * 100 * srcK : 0;

        var an = ch.anim; an.applyRootMotion = true; an.cullingMode = AnimatorCullingMode.AlwaysAnimate;
        var g = PlayableGraph.Create("RetargetCheck");
        g.SetTimeUpdateMode(DirectorUpdateMode.Manual);
        var cp = AnimationClipPlayable.Create(g, clip);
        cp.SetApplyFootIK(footIK);
        AnimationPlayableOutput.Create(g, "out", an).SetSourcePlayable(cp);
        g.Play();
        var watch = new[] { HumanBodyBones.LeftHand, HumanBodyBones.RightHand, HumanBodyBones.LeftFoot, HumanBodyBones.RightFoot, HumanBodyBones.Head };
        string[] watchSrc = { "LeftHand", "RightHand", "LeftFoot", "RightFoot", "Head" };
        var tPos = new Vector3[F, 4]; var wPos = new Vector3[F, watch.Length];
        var skate = new List<float>(); var floatH = new List<float>();
        float pen = 0; int torsoN = 0, headN = 0;
        try
        {
            for (int f = 0; f < F; f++)
            {
                g.Evaluate(f == 0 ? 0 : dt);
                if (ch.grounding) ch.grounding.Solve(); // LateUpdate doesn't run here
                for (int k = 0; k < 4; k++) tPos[f, k] = ch.B(tgtB[k]) ? ch.B(tgtB[k]).position : ch.B(tgtB[k & 2]).position;
                for (int w = 0; w < watch.Length; w++) wPos[f, w] = ch.B(watch[w]).position;
                var (sl, sr, all) = Soles(ch);
                if (-all > pen)
                {
                    pen = -all; row.penFrame = f; float lo = float.MaxValue;
                    foreach (var (sk, _, _) in ch.meshes) { var (y, i) = sk.LowestWithIndex(); if (y < lo) { lo = y; row.penBone = sk.bones[sk.w[i].boneIndex0]?.name; } }
                }
                bool lc = contact[0, f] || contact[1, f], rc = contact[2, f] || contact[3, f];
                if (lc) floatH.Add(sl); if (rc) floatH.Add(sr);

                // Hands vs torso capsule and head sphere.
                Vector3 hips = ch.B(HumanBodyBones.Hips).position, neck = (ch.B(HumanBodyBones.Neck) ?? ch.B(HumanBodyBones.Head)).position;
                var headC = ch.B(HumanBodyBones.Head).TransformPoint(ch.headCenterLocal);
                float tMax = 0, hMax = 0;
                foreach (var (hb, mb) in new[] { (HumanBodyBones.LeftHand, HumanBodyBones.LeftMiddleProximal), (HumanBodyBones.RightHand, HumanBodyBones.RightMiddleProximal) })
                {
                    var h = ch.B(hb).position;
                    var tip = ch.B(mb) ? ch.B(mb).position : h + (h - ch.B(hb == HumanBodyBones.LeftHand ? HumanBodyBones.LeftLowerArm : HumanBodyBones.RightLowerArm).position).normalized * 0.08f / ch.scale;
                    var palm = (h + tip) * 0.5f;
                    foreach (var p in new[] { h, palm })
                    {
                        tMax = Mathf.Max(tMax, ch.torsoR - SegDist(p, hips, neck));
                        hMax = Mathf.Max(hMax, ch.headR - (p - headC).magnitude);
                    }
                }
                row.handTorsoCm = Mathf.Max(row.handTorsoCm, tMax * 100);
                row.handHeadCm = Mathf.Max(row.handHeadCm, hMax * 100);
                if (tMax > 0.02f) torsoN++; if (hMax > 0.02f) headN++;

                row.kneeHyperDeg = Mathf.Max(row.kneeHyperDeg, Hyper(ch, ch.kneeAxisL, HumanBodyBones.LeftUpperLeg, HumanBodyBones.LeftLowerLeg, HumanBodyBones.LeftFoot),
                                                               Hyper(ch, ch.kneeAxisR, HumanBodyBones.RightUpperLeg, HumanBodyBones.RightLowerLeg, HumanBodyBones.RightFoot));
                row.elbowHyperDeg = Mathf.Max(row.elbowHyperDeg, Hyper(ch, ch.elbowAxisL, HumanBodyBones.LeftUpperArm, HumanBodyBones.LeftLowerArm, HumanBodyBones.LeftHand),
                                                                 Hyper(ch, ch.elbowAxisR, HumanBodyBones.RightUpperArm, HumanBodyBones.RightLowerArm, HumanBodyBones.RightHand));
            }
        }
        finally { g.Destroy(); }

        for (int k = 0; k < 4; k++)
            for (int f = 1; f < F - 1; f++)
                if (contact[k, f]) { skate.Add(Flat(tPos[f + 1, k] - tPos[f - 1, k]).magnitude / (2 * dt) * 100); row.contactFrames++; }
        skate.Sort(); floatH.Sort();
        row.skateCms = skate.Count > 0 ? skate.Average() : 0;
        row.skateP95Cms = skate.Count > 0 ? skate[(int)(skate.Count * 0.95f)] : 0;
        row.floatCm = floatH.Count > 0 ? floatH.Average() * 100 : 0;
        row.floatP95Cm = floatH.Count > 0 ? floatH[(int)(floatH.Count * 0.95f)] * 100 : 0;
        row.penCm = pen * 100;
        row.handTorsoFrames = (float)torsoN / F; row.handHeadFrames = (float)headN / F;

        // Pops: target end-effector acceleration vs source at the same frame (both normalised to 1.75 m).
        for (int f = 1; f < F - 1; f++)
        {
            for (int w = 0; w < watch.Length; w++)
            {
                float at = (wPos[f + 1, w] - 2 * wPos[f, w] + wPos[f - 1, w]).magnitude * fps * fps;
                float asrc = (Ref(f + 1, watchSrc[w]) - 2 * Ref(f, watchSrc[w]) + Ref(f - 1, watchSrc[w])).magnitude * fps * fps * srcK;
                float ratio = at / Mathf.Max(asrc, 5f);
                row.popMaxRatio = Mathf.Max(row.popMaxRatio, ratio);
                if (at > 30f && ratio > 3f) { row.pops++; break; }
            }
        }
        // Source floor: lowest foot joint vs its own minimum is 0 by construction; report source min toe height.
        row.srcPenCm = -Enumerable.Range(0, F).Min(f => Mathf.Min(Ref(f, "LeftToeBase").y, Ref(f, "RightToeBase").y)) * 100 * srcK;
        Object.DestroyImmediate(ch.go);
        return row;
    }

    static Vector3 Flat(Vector3 v) => new Vector3(v.x, 0, v.z);
}
