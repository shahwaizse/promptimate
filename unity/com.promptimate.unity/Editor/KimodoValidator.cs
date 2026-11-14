// Automated sanity checks for an imported Kimodo clip, so orientation/retarget bugs are caught without a human.
//   Rig A = source motion converted to Unity space (ground truth).
//   Rig B = the baked Humanoid clip replayed through Unity's Animator on the SOMA avatar (round-trip accuracy).
//   Rig C = a synthetic humanoid with different proportions and scrambled bone axes (like Mixamo/VRM rigs),
//           driven by the same clip (cross-rig retarget sanity).
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;

namespace Promptimate.Editor
{
    [System.Serializable]
    public class RigChecks
    {
        public float facingErrMaxDeg;   // body yaw difference vs source
        public float toesForwardRatio;  // measurable frames where both feet point along body forward
        public float handednessRatio;   // frames where left shoulder is on the character's left
        public float groundedRatio;     // frames where the lowest foot is within 10 cm of the floor
        public float minFootHeightM;
    }

    [System.Serializable]
    public class KimodoReport
    {
        public string asset;
        public string prompt;
        public bool passed;
        public List<string> failures = new List<string>();
        public bool humanMotion;
        public int framesChecked;
        public float travelM;           // source hips XZ displacement first->last
        public float facingVsTravelDeg; // angle between mean body forward and travel (-1 if static)
        public float initialFacingDeg;  // body forward at frame 0 vs Unity +Z (character forward convention)
        public float refPosErrMaxM = -1; // rig A vs independent Python FK positions (mirrored X); -1 if absent
        public string refPosErrMaxJoint;
        public RigChecks source = new RigChecks();
        public float poseErrMeanM;      // B vs A, hips-relative joint position error (m)
        public float poseErrMaxM;
        public string poseErrMaxJoint;
        public float rootDriftMaxM;     // B hips vs A hips, world
        public RigChecks somaClip = new RigChecks();
        public float boneDirErrMeanDeg; // C vs A, mean angle between corresponding bone directions
        public float boneDirErrMaxDeg;
        public string boneDirErrMaxBone;
        public RigChecks otherRig = new RigChecks();
    }

    public static class KimodoValidator
    {
        // Gross-error thresholds. Real bugs (mirroring, 180° facing, broken retarget) blow way past these;
        // legitimate motion (jumps, toe-off, crouches) should stay inside.
        const float PoseErrMeanLimit = 0.05f, PoseErrMaxLimit = 0.20f, FacingLimitDeg = 25f;
        const float ToesRatioLimit = 0.6f, HandednessLimit = 0.9f, GroundedLimit = 0.3f, MinFootLow = -0.08f;
        const float BoneDirMeanLimitDeg = 20f, RefPosLimit = 0.01f;

        static readonly string[] Compared =
        {
            "Spine1", "Spine2", "Chest", "Neck1", "Head",
            "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "RightShoulder", "RightArm", "RightForeArm", "RightHand",
            "LeftLeg", "LeftShin", "LeftFoot", "LeftToeBase", "RightLeg", "RightShin", "RightFoot", "RightToeBase",
        };

        // Bones (child joint names) whose direction parent->child is compared across rigs.
        static readonly string[] DirBones =
        {
            "LeftForeArm", "LeftHand", "RightForeArm", "RightHand",
            "LeftShin", "LeftFoot", "LeftToeBase", "RightShin", "RightFoot", "RightToeBase", "Head",
        };

        class Acc
        {
            public int n, toesN, toesOk, handOk, grounded;
            public float facingMax, minFoot = float.MaxValue;
            public RigChecks Done() => new RigChecks
            {
                facingErrMaxDeg = facingMax, toesForwardRatio = toesN > 0 ? (float)toesOk / toesN : 1f,
                handednessRatio = (float)handOk / n, groundedRatio = (float)grounded / n, minFootHeightM = minFoot,
            };
        }

        public static KimodoReport Validate(KimodoFile data, AnimationClip clip, Avatar somaAvatar)
        {
            var r = new KimodoReport { prompt = data.prompt, humanMotion = clip.humanMotion };
            var rigA = KimodoImporter.BuildRig(data, out var a);
            var rigB = KimodoImporter.BuildRig(data, out var b);
            var rigC = BuildSyntheticRig(data, out var c);
            Avatar avatarC = null;
            try
            {
                var animB = rigB.AddComponent<Animator>();
                animB.avatar = somaAvatar; animB.applyRootMotion = false;
                avatarC = KimodoImporter.BuildAvatar(rigC, c);
                if (!avatarC.isValid || !avatarC.isHuman) r.failures.Add("could not build synthetic test avatar");
                var animC = rigC.AddComponent<Animator>();
                animC.avatar = avatarC; animC.applyRootMotion = false;

                int Idx(string nm) => System.Array.IndexOf(data.names, nm);
                int hips = Idx("Hips");
                var cmp = Compared.Select(Idx).Where(i => i >= 0).ToArray();
                var dirs = DirBones.Select(Idx).Where(i => i >= 0).ToArray();

                var accA = new Acc(); var accB = new Acc(); var accC = new Acc();
                int F = data.frames, step = Mathf.Max(1, F / 40);
                double errSum = 0, dirSum = 0; int errN = 0, dirN = 0;
                Vector3 fwdSum = Vector3.zero;
                bool hasRef = data.refPos != null && data.refPos.Length == F * data.joints * 3;
                if (hasRef) r.refPosErrMaxM = 0;

                for (int f = 0; f < F; f += step)
                {
                    KimodoImporter.ApplySourceFrame(data, a, f);
                    clip.SampleAnimation(rigB, f / data.fps);
                    clip.SampleAnimation(rigC, f / data.fps);
                    r.framesChecked++;

                    if (hasRef)
                        for (int j = 0; j < data.joints; j++)
                        {
                            int o = (f * data.joints + j) * 3;
                            // Position handedness change is unambiguous (mirror X), unlike rotation conversion.
                            var refP = new Vector3(-data.refPos[o], data.refPos[o + 1], data.refPos[o + 2]);
                            float e = Vector3.Distance(a[j].position, refP);
                            if (e > r.refPosErrMaxM) { r.refPosErrMaxM = e; r.refPosErrMaxJoint = data.names[j]; }
                        }
                    var fwdA = Semantics(data, a, accA, Vector3.zero);
                    if (f == 0) r.initialFacingDeg = Vector3.Angle(fwdA, Vector3.forward);
                    fwdSum += fwdA;
                    Semantics(data, b, accB, fwdA);
                    Semantics(data, c, accC, fwdA);

                    foreach (var j in cmp)
                    {
                        float e = Vector3.Distance(a[j].position - a[hips].position, b[j].position - b[hips].position);
                        errSum += e; errN++;
                        if (e > r.poseErrMaxM) { r.poseErrMaxM = e; r.poseErrMaxJoint = data.names[j]; }
                    }
                    r.rootDriftMaxM = Mathf.Max(r.rootDriftMaxM, Vector3.Distance(a[hips].position, b[hips].position));

                    foreach (var j in dirs)
                    {
                        int p = data.parents[j];
                        float ang = Vector3.Angle(a[j].position - a[p].position, c[j].position - c[p].position);
                        dirSum += ang; dirN++;
                        if (ang > r.boneDirErrMaxDeg) { r.boneDirErrMaxDeg = ang; r.boneDirErrMaxBone = data.names[j]; }
                    }
                }

                r.source = accA.Done(); r.somaClip = accB.Done(); r.otherRig = accC.Done();
                r.poseErrMeanM = errN > 0 ? (float)(errSum / errN) : float.NaN;
                r.boneDirErrMeanDeg = dirN > 0 ? (float)(dirSum / dirN) : float.NaN;

                KimodoImporter.ApplySourceFrame(data, a, 0);
                var p0 = Flat(a[hips].position);
                KimodoImporter.ApplySourceFrame(data, a, F - 1);
                var travel = Flat(a[hips].position) - p0;
                r.travelM = travel.magnitude;
                r.facingVsTravelDeg = r.travelM > 0.5f ? Vector3.Angle(fwdSum, travel) : -1f;

                if (!r.humanMotion) r.failures.Add("clip is not humanoid");
                if (r.refPosErrMaxM > RefPosLimit) r.failures.Add($"source rig differs from reference FK by {r.refPosErrMaxM:F3} m at {r.refPosErrMaxJoint} (conversion bug?)");
                if (r.initialFacingDeg > 45f) r.failures.Add($"clip starts facing {r.initialFacingDeg:F0} deg away from +Z (Unity forward)");
                bool backwardPrompt = (data.prompt ?? "").ToLowerInvariant().Contains("backward");
                if (r.facingVsTravelDeg > 120f && !backwardPrompt)
                    r.failures.Add($"moves opposite to where it faces ({r.facingVsTravelDeg:F0} deg) but prompt doesn't say backward");
                if (r.poseErrMeanM > PoseErrMeanLimit) r.failures.Add($"SOMA round-trip pose error mean {r.poseErrMeanM:F3} m");
                if (r.poseErrMaxM > PoseErrMaxLimit) r.failures.Add($"SOMA round-trip pose error max {r.poseErrMaxM:F3} m at {r.poseErrMaxJoint}");
                if (r.boneDirErrMeanDeg > BoneDirMeanLimitDeg) r.failures.Add($"other-rig bone directions off by {r.boneDirErrMeanDeg:F0} deg on average");
                if (r.source.minFootHeightM < MinFootLow) r.failures.Add($"source feet below ground ({r.source.minFootHeightM:F3} m)");
                if (r.source.groundedRatio < GroundedLimit) r.failures.Add($"source feet near ground in only {r.source.groundedRatio:P0} of frames");
                CheckRig("source", r.source, r.failures, false);
                CheckRig("SOMA clip", r.somaClip, r.failures, true);
                CheckRig("other rig", r.otherRig, r.failures, true);
                r.passed = r.failures.Count == 0;
            }
            finally
            {
                Object.DestroyImmediate(rigA);
                Object.DestroyImmediate(rigB);
                Object.DestroyImmediate(rigC);
                if (avatarC != null) Object.DestroyImmediate(avatarC);
            }
            return r;
        }

        static void CheckRig(string label, RigChecks k, List<string> failures, bool facing)
        {
            if (facing && k.facingErrMaxDeg > FacingLimitDeg) failures.Add($"{label}: facing differs from source by {k.facingErrMaxDeg:F0} deg");
            if (k.toesForwardRatio < ToesRatioLimit) failures.Add($"{label}: feet point along body forward in only {k.toesForwardRatio:P0} of frames");
            if (k.handednessRatio < HandednessLimit) failures.Add($"{label}: left/right correct in only {k.handednessRatio:P0} of frames (mirrored?)");
        }

        /// Accumulates per-frame semantic checks for a posed rig; returns its body forward.
        static Vector3 Semantics(KimodoFile d, Transform[] t, Acc acc, Vector3 refForward)
        {
            int Idx(string nm) => System.Array.IndexOf(d.names, nm);
            Transform lLeg = t[Idx("LeftLeg")], rLeg = t[Idx("RightLeg")], lArm = t[Idx("LeftArm")], rArm = t[Idx("RightArm")];
            Transform lFoot = t[Idx("LeftFoot")], rFoot = t[Idx("RightFoot")], lToe = t[Idx("LeftToeBase")], rToe = t[Idx("RightToeBase")];
            acc.n++;
            var fwd = BodyForward(lLeg.position, rLeg.position);
            if (refForward != Vector3.zero) acc.facingMax = Mathf.Max(acc.facingMax, Vector3.Angle(fwd, refForward));

            // Feet should point the way the body faces. Skip frames where a foot points mostly down (toe-off, jumps).
            Vector3 lt = Flat(lToe.position - lFoot.position), rt = Flat(rToe.position - rFoot.position);
            if (lt.magnitude > 0.03f && rt.magnitude > 0.03f)
            {
                acc.toesN++;
                if (Vector3.Dot(lt, fwd) > 0 && Vector3.Dot(rt, fwd) > 0) acc.toesOk++;
            }
            // Left shoulder must be on the character's left; in Unity (left-handed) left = Cross(forward, up).
            if (Vector3.Dot(lArm.position - rArm.position, Vector3.Cross(fwd, Vector3.up)) > 0) acc.handOk++;

            float lowest = Mathf.Min(Mathf.Min(lFoot.position.y, rFoot.position.y), Mathf.Min(lToe.position.y, rToe.position.y));
            acc.minFoot = Mathf.Min(acc.minFoot, lowest);
            if (lowest < 0.10f) acc.grounded++;
            return fwd;
        }

        // Unity (left-handed, facing +Z): character's left is -X. Cross(up, left) = Cross((0,1,0), (-1,0,0)) = (0,0,1).
        static Vector3 BodyForward(Vector3 leftHip, Vector3 rightHip) =>
            Vector3.Cross(Vector3.up, Flat(leftHip - rightHip)).normalized;

        static Vector3 Flat(Vector3 v) => new Vector3(v.x, 0, v.z);

        /// Same joint names and rest pose shape as SOMA, but with different segment lengths and random bone axes,
        /// the way third-party rigs differ. Rest world positions are a T-pose; local rotations are non-identity.
        static GameObject BuildSyntheticRig(KimodoFile d, out Transform[] bones)
        {
            int J = d.joints;
            var rng = new System.Random(1234);
            var world = new Vector3[J];
            var worldRot = new Quaternion[J];
            for (int j = 0; j < J; j++)
            {
                string nm = d.names[j];
                float s = nm.Contains("Leg") || nm.Contains("Shin") || nm.Contains("Foot") || nm.Contains("Toe") ? 0.9f
                        : nm.Contains("Arm") || nm.Contains("Hand") ? 1.1f
                        : nm.StartsWith("Spine") || nm == "Chest" || nm.StartsWith("Neck") ? 1.08f : 1f;
                var off = KimodoImporter.ToUnity(d.offsets[j * 3], d.offsets[j * 3 + 1], d.offsets[j * 3 + 2]);
                if (d.parents[j] < 0) off.y *= 0.9f; // hips height follows the shorter legs
                world[j] = (d.parents[j] < 0 ? Vector3.zero : world[d.parents[j]]) + off * s;
                worldRot[j] = Quaternion.Euler((float)rng.NextDouble() * 360f, (float)rng.NextDouble() * 360f, (float)rng.NextDouble() * 360f);
            }
            var root = new GameObject("KimodoRig");
            bones = new Transform[J];
            for (int j = 0; j < J; j++)
            {
                var t = new GameObject(d.names[j]).transform;
                int p = d.parents[j];
                t.SetParent(p < 0 ? root.transform : bones[p], false);
                Quaternion parentRot = p < 0 ? Quaternion.identity : worldRot[p];
                Vector3 parentPos = p < 0 ? Vector3.zero : world[p];
                t.localPosition = Quaternion.Inverse(parentRot) * (world[j] - parentPos);
                t.localRotation = Quaternion.Inverse(parentRot) * worldRot[j];
                bones[j] = t;
            }
            return root;
        }

        public static string ReportDir => Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Library", "Promptimate", "Reports"));

        public static void WriteReport(KimodoReport r)
        {
            Directory.CreateDirectory(ReportDir);
            File.WriteAllText(Path.Combine(ReportDir, Path.GetFileNameWithoutExtension(r.asset) + ".json"), JsonUtility.ToJson(r, true));
        }
    }
}
