// Automated sanity checks for an imported Kimodo clip, so orientation/retarget bugs are caught without a human.
//   Rig A = source motion converted to Unity space (ground truth).
//   Rig B = the baked Humanoid clip replayed through Unity's Animator on the SOMA avatar (round-trip accuracy).
//   Rig C = a synthetic humanoid with different proportions, scrambled bone axes and finger bones (like Mixamo/VRM
//           rigs), driven by the same clip (cross-rig retarget sanity, hand pose).
// The conversion checks (A/B/C) run on a copy of the clip with neutral settings. The clip as imported (loop, root
// motion, hands, IK goals) is then played through a PlayableGraph, the way an Animator/Timeline plays it.
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

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
        public float maxFootLowestM;    // highest "lowest foot" over the clip (feet flying up shows here)
    }

    [System.Serializable]
    public class ClipOptionsInfo
    {
        public bool loop, loopPose, inPlace, bakeRootRotation, bakeRootHeight, ikGoals;
        public string hands;
    }

    [System.Serializable]
    public class KimodoReport
    {
        public string asset;
        public string prompt;
        public bool passed;
        public List<string> failures = new List<string>();
        public ClipOptionsInfo options = new ClipOptionsInfo();
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
        public float handRollErrMeanDeg = -1; // C vs A, palm roll (thumb side around the hand axis); -1 if no end sites
        public float handRollErrMaxDeg = -1;
        public RigChecks otherRig = new RigChecks();
        // Clip as imported, played through a PlayableGraph with Apply Root Motion on (SOMA avatar).
        public float rootMotionTravelM;     // GameObject XZ displacement over the clip
        public float rootMotionHipsErrMaxM; // world hips vs source hips
        public float inPlaceHipsWanderM;    // max hips XZ distance from the start (in-place clips)
        public RigChecks runtime = new RigChecks();
        // IK goal curves
        public float goalCurveErrMaxM = -1;     // goal decoded from the curves vs goal from the FK pose (stream)
        public float goalCurveErrMaxDeg = -1;
        public float footIKErrMaxM = -1;        // SOMA avatar: feet with Foot IK on vs off
        public float otherRigFootIKDiffMaxM = -1; // rig C: feet with Foot IK on vs off (info: proportion correction)
        public RigChecks otherRigFootIK = new RigChecks();
        // Hands
        public int fingerCurves;
        public float fingerCurlDeg = -1;  // rig C, mean total curl of the four fingers at t=0
        // Loop
        public float loopSeamM = -1;      // pose difference end vs start of the looping clip (hips-relative)
        public float sourceSeamM = -1;    // same, raw source frames (how loopable the generated motion is)
    }

    public static class KimodoValidator
    {
        // Gross-error thresholds. Real bugs (mirroring, 180° facing, broken retarget) blow way past these;
        // legitimate motion (jumps, toe-off, crouches) should stay inside.
        const float PoseErrMeanLimit = 0.05f, PoseErrMaxLimit = 0.20f, FacingLimitDeg = 25f;
        const float ToesRatioLimit = 0.6f, HandednessLimit = 0.9f, GroundedLimit = 0.3f, MinFootLow = -0.08f;
        const float ToePlantedM = 0.10f;  // toe joint below this height = foot on the ground (toes check)
        const float BoneDirMeanLimitDeg = 20f, RefPosLimit = 0.01f, HandRollMeanLimitDeg = 25f;
        const float GoalCurveLimitM = 0.002f, GoalCurveLimitDeg = 1f, FootIKLimitM = 0.03f;
        const float InPlaceTravelLimit = 0.05f, InPlaceWanderLimit = 0.5f, LoopSeamLimit = 0.03f;

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

        static readonly string[] FeetJoints = { "LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase" };

        class Acc
        {
            public int n, toesN, toesOk, handOk, grounded;
            public float facingMax, minFoot = float.MaxValue, maxLowest = float.MinValue;
            public RigChecks Done() => new RigChecks
            {
                facingErrMaxDeg = facingMax, toesForwardRatio = toesN > 0 ? (float)toesOk / toesN : 1f,
                handednessRatio = n > 0 ? (float)handOk / n : 0f, groundedRatio = n > 0 ? (float)grounded / n : 0f,
                minFootHeightM = minFoot, maxFootLowestM = maxLowest,
            };
        }

        internal static KimodoReport Validate(KimodoFile data, AnimationClip clip, Avatar somaAvatar, BakeOptions opts)
        {
            var r = new KimodoReport { prompt = data.prompt, humanMotion = clip.humanMotion };
            r.options = new ClipOptionsInfo
            {
                loop = opts.loop, loopPose = opts.loopPose, inPlace = opts.inPlace, bakeRootRotation = opts.bakeRootRotation,
                bakeRootHeight = opts.bakeRootHeight, ikGoals = opts.ikGoals, hands = opts.hands.ToString(),
            };
            // Conversion checks run on a neutral copy, so loop blending / baking can't mask or fake errors.
            var core = Object.Instantiate(clip);
            var cs = AnimationUtility.GetAnimationClipSettings(core);
            cs.loopTime = cs.loopBlend = cs.loopBlendOrientation = cs.loopBlendPositionXZ = cs.loopBlendPositionY = false;
            cs.keepOriginalOrientation = cs.keepOriginalPositionXZ = cs.keepOriginalPositionY = cs.heightFromFeet = false;
            cs.cycleOffset = 0;
            AnimationUtility.SetAnimationClipSettings(core, cs);

            var rigA = KimodoImporter.BuildRig(data, out var a);
            var rigB = KimodoImporter.BuildRig(data, out var b);
            var rigC = BuildSyntheticRig(data, out var c, out var fingers, out var fingerRest);
            Avatar avatarC = null;
            try
            {
                var animB = rigB.AddComponent<Animator>();
                animB.avatar = somaAvatar; animB.applyRootMotion = false;
                avatarC = KimodoImporter.BuildAvatar(rigC, c);
                bool cOk = avatarC.isValid && avatarC.isHuman;
                if (!cOk) r.failures.Add("could not build synthetic test avatar");
                var animC = rigC.AddComponent<Animator>();
                animC.avatar = avatarC; animC.applyRootMotion = false;

                int Idx(string nm) => System.Array.IndexOf(data.names, nm);
                int hips = Idx("Hips");
                var cmp = Compared.Select(Idx).Where(i => i >= 0).ToArray();
                var dirs = DirBones.Select(Idx).Where(i => i >= 0).ToArray();
                // Palm roll: thumb end-site around the hand->middle end-site axis (both carried by the hand bone).
                var palms = new[] { ("LeftHand", "LeftHandThumbEnd", "LeftHandMiddleEnd"), ("RightHand", "RightHandThumbEnd", "RightHandMiddleEnd") }
                    .Select(p => (Idx(p.Item1), Idx(p.Item2), Idx(p.Item3))).Where(p => p.Item1 >= 0 && p.Item2 >= 0 && p.Item3 >= 0).ToArray();

                var accA = new Acc(); var accB = new Acc(); var accC = new Acc();
                int F = data.frames, step = Mathf.Max(1, F / 40);
                double errSum = 0, dirSum = 0, rollSum = 0; int errN = 0, dirN = 0, rollN = 0;
                Vector3 fwdSum = Vector3.zero;
                bool hasRef = data.refPos != null && data.refPos.Length == F * data.joints * 3;
                if (hasRef) r.refPosErrMaxM = 0;

                for (int f = 0; f < F; f += step)
                {
                    KimodoImporter.ApplySourceFrame(data, a, f);
                    core.SampleAnimation(rigB, f / data.fps);
                    core.SampleAnimation(rigC, f / data.fps);
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

                    foreach (var (h, th, mid) in palms)
                    {
                        Vector3 Roll(Transform[] t) => Vector3.ProjectOnPlane(t[th].position - t[h].position, t[mid].position - t[h].position);
                        float ang = Vector3.Angle(Roll(a), Roll(c));
                        rollSum += ang; rollN++;
                        r.handRollErrMaxDeg = Mathf.Max(r.handRollErrMaxDeg, ang);
                    }
                }

                r.source = accA.Done(); r.somaClip = accB.Done(); r.otherRig = accC.Done();
                r.poseErrMeanM = errN > 0 ? (float)(errSum / errN) : float.NaN;
                r.boneDirErrMeanDeg = dirN > 0 ? (float)(dirSum / dirN) : float.NaN;
                if (rollN > 0) r.handRollErrMeanDeg = (float)(rollSum / rollN);

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
                if (r.handRollErrMeanDeg > HandRollMeanLimitDeg) r.failures.Add($"other-rig palm roll off by {r.handRollErrMeanDeg:F0} deg on average (twist retarget)");
                if (r.source.minFootHeightM < MinFootLow) r.failures.Add($"source feet below ground ({r.source.minFootHeightM:F3} m)");
                if (r.source.groundedRatio < GroundedLimit) r.failures.Add($"source feet near ground in only {r.source.groundedRatio:P0} of frames");
                CheckRig("source", r.source, r.failures, false);
                CheckRig("SOMA clip", r.somaClip, r.failures, true);
                CheckRig("other rig", r.otherRig, r.failures, true);

                CheckSettings(clip, opts, r.failures);
                CheckHands(clip, opts, r, cOk ? rigC : null, c, fingers, fingerRest, data);
                CheckRuntime(data, clip, somaAvatar, opts, r, fwdSum);
                CheckIK(data, clip, somaAvatar, cOk ? avatarC : null, opts, r);
                if (opts.loop) CheckLoop(data, clip, somaAvatar, opts, r);

                r.passed = r.failures.Count == 0;
            }
            finally
            {
                Object.DestroyImmediate(rigA);
                Object.DestroyImmediate(rigB);
                Object.DestroyImmediate(rigC);
                Object.DestroyImmediate(core);
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

        static void CheckGrounded(string label, RigChecks k, List<string> failures)
        {
            if (k.minFootHeightM < MinFootLow) failures.Add($"{label}: feet below ground ({k.minFootHeightM:F3} m)");
            if (k.groundedRatio < GroundedLimit) failures.Add($"{label}: feet near ground in only {k.groundedRatio:P0} of frames");
        }

        // ---- Clip settings ------------------------------------------------------------------------------------

        static void CheckSettings(AnimationClip clip, BakeOptions o, List<string> failures)
        {
            var s = AnimationUtility.GetAnimationClipSettings(clip);
            var want = KimodoImporter.ClipSettings(clip, o);
            if (s.loopTime != want.loopTime || s.loopBlend != want.loopBlend || s.loopBlendOrientation != want.loopBlendOrientation ||
                s.loopBlendPositionXZ != want.loopBlendPositionXZ || s.loopBlendPositionY != want.loopBlendPositionY ||
                s.keepOriginalOrientation != want.keepOriginalOrientation || s.keepOriginalPositionY != want.keepOriginalPositionY ||
                s.keepOriginalPositionXZ != want.keepOriginalPositionXZ)
                failures.Add("clip settings (loop / root motion) were not applied");
        }

        // ---- Hands --------------------------------------------------------------------------------------------

        static void CheckHands(AnimationClip clip, BakeOptions o, KimodoReport r, GameObject rigC, Transform[] c,
                               Dictionary<string, Transform> fingers, Dictionary<string, Vector3> fingerRest, KimodoFile data)
        {
            var expected = KimodoImporter.HandPoseMuscles(o.hands);
            var bindings = AnimationUtility.GetCurveBindings(clip).Where(bd => bd.type == typeof(Animator)).ToArray();
            int bad = 0;
            foreach (var m in HumanTrait.MuscleName.Where(KimodoImporter.IsFingerMuscle))
            {
                var prop = KimodoImporter.MusclePropertyName(m);
                var bd = bindings.FirstOrDefault(x => x.propertyName == prop);
                if (bd.propertyName == null) continue;
                r.fingerCurves++;
                var curve = AnimationUtility.GetEditorCurve(clip, bd);
                if (expected == null || !expected.TryGetValue(m, out var v) || Mathf.Abs(curve.Evaluate(0) - v) > 1e-4f) bad++;
            }
            int want = expected?.Count ?? 0;
            if (r.fingerCurves != want || bad > 0)
                r.failures.Add($"hand pose {o.hands}: {r.fingerCurves} finger curves (expected {want}), {bad} with wrong values");

            if (rigC == null || o.hands == KimodoHandPose.None) return;
            // Functional check on a rig with finger bones: total curl (MCP+PIP+DIP) of the four fingers.
            clip.SampleAnimation(rigC, 0f);
            double sum = 0; int n = 0;
            foreach (var side in new[] { "Left", "Right" })
            {
                var hand = c[System.Array.IndexOf(data.names, side + "Hand")];
                foreach (var f in new[] { "Index", "Middle", "Ring", "Little" })
                {
                    var p = Enumerable.Range(1, 4).Select(i => fingers[$"{side}Hand{f}{i}"]).ToArray();
                    var restDir = hand.TransformDirection(fingerRest[$"{side}Hand{f}1"]);
                    var s1 = p[1].position - p[0].position; var s2 = p[2].position - p[1].position; var s3 = p[3].position - p[2].position;
                    sum += Vector3.Angle(restDir, s1) + Vector3.Angle(s1, s2) + Vector3.Angle(s2, s3); n++;
                }
            }
            r.fingerCurlDeg = (float)(sum / n);
            bool ok = o.hands == KimodoHandPose.Open ? r.fingerCurlDeg < 20f
                    : o.hands == KimodoHandPose.Fist ? r.fingerCurlDeg > 180f
                    : r.fingerCurlDeg > 35f && r.fingerCurlDeg < 150f;
            if (!ok) r.failures.Add($"hand pose {o.hands}: fingers curled {r.fingerCurlDeg:F0} deg on the test rig");
        }

        // ---- Runtime playback (root motion, in place, grounding) -------------------------------------------------

        static PlayableGraph Play(GameObject rig, Avatar avatar, AnimationClip clip, bool rootMotion, bool footIK, out AnimationClipPlayable cp)
        {
            var an = rig.GetComponent<Animator>(); if (an == null) an = rig.AddComponent<Animator>();
            an.avatar = avatar; an.applyRootMotion = rootMotion;
            an.cullingMode = AnimatorCullingMode.AlwaysAnimate; // batch mode has no visible renderers
            var g = PlayableGraph.Create("PromptimateValidate");
            g.SetTimeUpdateMode(DirectorUpdateMode.Manual);
            cp = AnimationClipPlayable.Create(g, clip);
            cp.SetApplyFootIK(footIK);
            AnimationPlayableOutput.Create(g, "out", an).SetSourcePlayable(cp);
            g.Play();
            return g;
        }

        static void CheckRuntime(KimodoFile data, AnimationClip clip, Avatar soma, BakeOptions o, KimodoReport r, Vector3 fwdSum)
        {
            var rigS = KimodoImporter.BuildRig(data, out var a);
            var rigR = KimodoImporter.BuildRig(data, out var b);
            var g = Play(rigR, soma, clip, true, false, out _);
            try
            {
                int hips = System.Array.IndexOf(data.names, "Hips");
                var acc = new Acc();
                float dt = 1f / data.fps;
                Vector3 hips0 = Vector3.zero;
                for (int f = 0; f < data.frames; f++)
                {
                    g.Evaluate(f == 0 ? 0 : dt);
                    KimodoImporter.ApplySourceFrame(data, a, f);
                    var fwdA = BodyForward(a[System.Array.IndexOf(data.names, "LeftLeg")].position, a[System.Array.IndexOf(data.names, "RightLeg")].position);
                    Semantics(data, b, acc, fwdA);
                    if (f == 0) hips0 = b[hips].position;
                    r.rootMotionHipsErrMaxM = Mathf.Max(r.rootMotionHipsErrMaxM, Vector3.Distance(a[hips].position, b[hips].position));
                    r.inPlaceHipsWanderM = Mathf.Max(r.inPlaceHipsWanderM, Flat(b[hips].position - hips0).magnitude);
                }
                r.rootMotionTravelM = Flat(rigR.transform.position).magnitude;
                r.runtime = acc.Done();
                CheckRig("playback", r.runtime, r.failures, true);
                CheckGrounded("playback", r.runtime, r.failures);
                if (o.inPlace)
                {
                    if (r.rootMotionTravelM > InPlaceTravelLimit) r.failures.Add($"in-place clip moves the GameObject {r.rootMotionTravelM:F2} m with Apply Root Motion");
                    if (r.inPlaceHipsWanderM > InPlaceWanderLimit) r.failures.Add($"in-place clip drifts: hips wander {r.inPlaceHipsWanderM:F2} m from the start");
                }
                else if (!o.bakeRootRotation)
                {
                    // Root motion + pose must reproduce the source path in the world.
                    float tol = 0.1f + 0.03f * r.travelM;
                    if (Mathf.Abs(r.rootMotionTravelM - r.travelM) > tol)
                        r.failures.Add($"Apply Root Motion travels {r.rootMotionTravelM:F2} m, source travels {r.travelM:F2} m");
                    if (r.rootMotionHipsErrMaxM > tol)
                        r.failures.Add($"Apply Root Motion: hips leave the source path by {r.rootMotionHipsErrMaxM:F2} m");
                }
            }
            finally
            {
                g.Destroy();
                Object.DestroyImmediate(rigS);
                Object.DestroyImmediate(rigR);
            }
        }

        // ---- IK goals -----------------------------------------------------------------------------------------

        static void CheckIK(KimodoFile data, AnimationClip clip, Avatar soma, Avatar avatarC, BakeOptions o, KimodoReport r)
        {
            if (!o.ikGoals) return;
            int F = data.frames;
            // 1) Goals decoded from the curves must equal the goals of the FK pose (exact inverse of Unity's convention).
            var rig = KimodoImporter.BuildRig(data, out _);
            float pe = 0, re = 0;
            try
            {
                IKGoals.Probe(rig, soma, clip, F, data.fps, (f, a) =>
                {
                    for (int g = 0; g < 4; g++)
                    {
                        int b = 8 + g * 14;
                        pe = Mathf.Max(pe, Vector3.Distance(IKGoals.V(a, b), IKGoals.V(a, b + 7)));
                        re = Mathf.Max(re, Quaternion.Angle(IKGoals.R(a, b + 3), IKGoals.R(a, b + 10)));
                    }
                });
            }
            finally { Object.DestroyImmediate(rig); }
            r.goalCurveErrMaxM = pe; r.goalCurveErrMaxDeg = re;
            if (pe > GoalCurveLimitM || re > GoalCurveLimitDeg)
                r.failures.Add($"IK goal curves don't match the pose ({pe:F3} m, {re:F1} deg)");

            // 2) Foot IK on vs off: same avatar -> feet must not move; other rig -> feet must stay grounded.
            r.footIKErrMaxM = FootIKDiff(data, () =>
            {
                var x = KimodoImporter.BuildRig(data, out _);
                var y = KimodoImporter.BuildRig(data, out var u);
                return (x, y, u);
            }, soma, clip, null);
            if (r.footIKErrMaxM > FootIKLimitM)
                r.failures.Add($"Foot IK moves the feet by {r.footIKErrMaxM:F2} m on the source avatar (missing/wrong IK goal curves)");
            if (avatarC != null)
            {
                var acc = new Acc();
                r.otherRigFootIKDiffMaxM = FootIKDiff(data, () =>
                {
                    var x = BuildSyntheticRig(data, out _, out _, out _);
                    var y = BuildSyntheticRig(data, out var u, out _, out _);
                    return (x, y, u);
                }, avatarC, clip, acc);
                r.otherRigFootIK = acc.Done();
                CheckGrounded("other rig with Foot IK", r.otherRigFootIK, r.failures);
            }
        }

        /// Plays the clip on two copies of a rig (Foot IK off / on, no root motion); returns max feet distance.
        /// accOn collects semantics of the IK-on rig.
        static float FootIKDiff(KimodoFile data, System.Func<(GameObject off, GameObject on, Transform[] onBones)> make,
                                Avatar avatar, AnimationClip clip, Acc accOn)
        {
            var (rigOff, rigOn, onBones) = make();
            // Transform arrays: re-resolve by name for the IK-off rig.
            var offBones = data.names.Select(n => FindDeep(rigOff.transform, n)).ToArray();
            var g0 = Play(rigOff, avatar, clip, false, false, out _);
            var g1 = Play(rigOn, avatar, clip, false, true, out _);
            float max = 0, dt = 1f / data.fps;
            try
            {
                var feet = FeetJoints.Select(n => System.Array.IndexOf(data.names, n)).ToArray();
                for (int f = 0; f < data.frames; f++)
                {
                    g0.Evaluate(f == 0 ? 0 : dt); g1.Evaluate(f == 0 ? 0 : dt);
                    foreach (var j in feet) max = Mathf.Max(max, Vector3.Distance(offBones[j].position, onBones[j].position));
                    if (accOn != null) Semantics(data, onBones, accOn, Vector3.zero);
                }
            }
            finally
            {
                g0.Destroy(); g1.Destroy();
                Object.DestroyImmediate(rigOff); Object.DestroyImmediate(rigOn);
            }
            return max;
        }

        static Transform FindDeep(Transform t, string name)
        {
            if (t.name == name) return t;
            foreach (Transform ch in t) { var x = FindDeep(ch, name); if (x != null) return x; }
            return null;
        }

        // ---- Loop ---------------------------------------------------------------------------------------------

        static void CheckLoop(KimodoFile data, AnimationClip clip, Avatar soma, BakeOptions o, KimodoReport r)
        {
            int hips = System.Array.IndexOf(data.names, "Hips");
            var cmp = Compared.Select(n => System.Array.IndexOf(data.names, n)).Where(i => i >= 0).ToArray();
            float Seam(Transform[] t, System.Action<bool> pose)
            {
                pose(false); var start = cmp.Select(j => t[j].position - t[hips].position).ToArray();
                pose(true); var end = cmp.Select(j => t[j].position - t[hips].position).ToArray();
                return start.Zip(end, (x, y) => Vector3.Distance(x, y)).Max();
            }
            var rigS = KimodoImporter.BuildRig(data, out var a);
            var rigR = KimodoImporter.BuildRig(data, out var b);
            var g = Play(rigR, soma, clip, false, false, out var cp);
            try
            {
                r.sourceSeamM = Seam(a, end => KimodoImporter.ApplySourceFrame(data, a, end ? data.frames - 1 : 0));
                r.loopSeamM = Seam(b, end => { cp.SetTime(end ? clip.length - 1e-4 : 0); g.Evaluate(0); });
            }
            finally
            {
                g.Destroy();
                Object.DestroyImmediate(rigS); Object.DestroyImmediate(rigR);
            }
            if (o.loopPose && r.loopSeamM > LoopSeamLimit)
                r.failures.Add($"looping clip pops at the loop point ({r.loopSeamM:F3} m) despite Loop Pose");
        }

        // ---- Semantics ----------------------------------------------------------------------------------------

        /// Accumulates per-frame semantic checks for a posed rig; returns its body forward.
        static Vector3 Semantics(KimodoFile d, Transform[] t, Acc acc, Vector3 refForward)
        {
            int Idx(string nm) => System.Array.IndexOf(d.names, nm);
            Transform lLeg = t[Idx("LeftLeg")], rLeg = t[Idx("RightLeg")], lArm = t[Idx("LeftArm")], rArm = t[Idx("RightArm")];
            Transform lFoot = t[Idx("LeftFoot")], rFoot = t[Idx("RightFoot")], lToe = t[Idx("LeftToeBase")], rToe = t[Idx("RightToeBase")];
            acc.n++;
            var fwd = BodyForward(lLeg.position, rLeg.position);
            if (refForward != Vector3.zero) acc.facingMax = Mathf.Max(acc.facingMax, Vector3.Angle(fwd, refForward));

            // Planted feet should point the way the body faces. Only judge a foot while its toe is near the floor: a
            // kicked-up trailing foot (jogging, running) legitimately points backwards. Skip feet pointing mostly
            // down (toe-off, jumps).
            Vector3 lt = Flat(lToe.position - lFoot.position), rt = Flat(rToe.position - rFoot.position);
            foreach (var (v, toe) in new[] { (lt, lToe), (rt, rToe) })
            {
                if (v.magnitude <= 0.03f || toe.position.y > ToePlantedM) continue;
                acc.toesN++;
                if (Vector3.Dot(v, fwd) > 0) acc.toesOk++;
            }
            // Left shoulder must be on the character's left; in Unity (left-handed) left = Cross(forward, up).
            if (Vector3.Dot(lArm.position - rArm.position, Vector3.Cross(fwd, Vector3.up)) > 0) acc.handOk++;

            float lowest = Mathf.Min(Mathf.Min(lFoot.position.y, rFoot.position.y), Mathf.Min(lToe.position.y, rToe.position.y));
            acc.minFoot = Mathf.Min(acc.minFoot, lowest);
            acc.maxLowest = Mathf.Max(acc.maxLowest, lowest);
            if (lowest < 0.10f) acc.grounded++;
            return fwd;
        }

        // Unity (left-handed, facing +Z): character's left is -X. Cross(up, left) = Cross((0,1,0), (-1,0,0)) = (0,0,1).
        static Vector3 BodyForward(Vector3 leftHip, Vector3 rightHip) =>
            Vector3.Cross(Vector3.up, Flat(leftHip - rightHip)).normalized;

        static Vector3 Flat(Vector3 v) => new Vector3(v.x, 0, v.z);

        /// Same joint names and rest pose shape as SOMA, but with different segment lengths and random bone axes,
        /// the way third-party rigs differ, plus 5 three-segment fingers per hand (straight in the T-pose, like
        /// Mixamo). Rest world positions are a T-pose; local rotations are non-identity.
        /// fingerRest: finger base bone name -> rest finger direction in hand space (for curl measurement).
        static GameObject BuildSyntheticRig(KimodoFile d, out Transform[] bones, out Dictionary<string, Transform> fingers,
                                            out Dictionary<string, Vector3> fingerRest)
        {
            int J = d.joints;
            var rng = new System.Random(1234);
            var world = new Vector3[J];
            var worldRot = new Quaternion[J];
            Quaternion RandRot() => Quaternion.Euler((float)rng.NextDouble() * 360f, (float)rng.NextDouble() * 360f, (float)rng.NextDouble() * 360f);
            for (int j = 0; j < J; j++)
            {
                string nm = d.names[j];
                float s = nm.Contains("Leg") || nm.Contains("Shin") || nm.Contains("Foot") || nm.Contains("Toe") ? 0.9f
                        : nm.Contains("Arm") || nm.Contains("Hand") ? 1.1f
                        : nm.StartsWith("Spine") || nm == "Chest" || nm.StartsWith("Neck") ? 1.08f : 1f;
                var off = KimodoImporter.ToUnity(d.offsets[j * 3], d.offsets[j * 3 + 1], d.offsets[j * 3 + 2]);
                if (d.parents[j] < 0) off.y *= 0.9f; // hips height follows the shorter legs
                world[j] = (d.parents[j] < 0 ? Vector3.zero : world[d.parents[j]]) + off * s;
                worldRot[j] = RandRot();
            }
            var root = new GameObject("KimodoRig");
            bones = new Transform[J];
            for (int j = 0; j < J; j++)
            {
                var t = new GameObject(d.names[j]).transform;
                int p = d.parents[j];
                t.SetParent(p < 0 ? root.transform : bones[p], false);
                t.position = world[j];
                t.rotation = worldRot[j];
                bones[j] = t;
            }

            fingers = new Dictionary<string, Transform>();
            fingerRest = new Dictionary<string, Vector3>();
            foreach (var side in new[] { "Left", "Right" })
            {
                int hi = System.Array.IndexOf(d.names, side + "Hand"), fi = System.Array.IndexOf(d.names, side + "ForeArm");
                if (hi < 0 || fi < 0) continue;
                var hand = bones[hi];
                var dir = (world[hi] - world[fi]).normalized; // along the arm (T-pose)
                var fwd = Vector3.forward;                    // thumb side (character faces +Z, palms down)
                var defs = new (string name, Vector3 baseOff, Vector3 fdir, float[] len)[]
                {
                    ("Thumb", dir * 0.025f + fwd * 0.025f + Vector3.down * 0.01f, (dir + fwd * 0.8f).normalized, new[] { 0.035f, 0.030f, 0.025f }),
                    ("Index", dir * 0.095f + fwd * 0.030f, dir, new[] { 0.045f, 0.028f, 0.022f }),
                    ("Middle", dir * 0.100f + fwd * 0.010f, dir, new[] { 0.048f, 0.030f, 0.023f }),
                    ("Ring", dir * 0.095f - fwd * 0.010f, dir, new[] { 0.045f, 0.028f, 0.022f }),
                    ("Little", dir * 0.085f - fwd * 0.028f, dir, new[] { 0.036f, 0.022f, 0.020f }),
                };
                foreach (var (name, baseOff, fdir, len) in defs)
                {
                    Transform parent = hand;
                    var pos = world[hi] + baseOff;
                    for (int i = 0; i < 4; i++) // 1..3 = phalanges (mapped), 4 = tip (unmapped)
                    {
                        var t = new GameObject($"{side}Hand{name}{i + 1}").transform;
                        t.SetParent(parent, false);
                        t.position = pos;
                        t.rotation = RandRot();
                        fingers[t.name] = t;
                        if (i == 0) fingerRest[t.name] = hand.InverseTransformDirection(fdir);
                        if (i < 3) pos += fdir * len[i];
                        parent = t;
                    }
                }
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
