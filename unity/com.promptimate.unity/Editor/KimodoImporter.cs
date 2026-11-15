// Imports a .kimodo motion file (written by the Promptimate MCP server) as a Humanoid AnimationClip.
// Approach: build a temporary SOMA-30 rig in its rest (T-)pose, build a Humanoid Avatar for it, drive the rig
// frame by frame with Kimodo's local rotations and sample muscle values with HumanPoseHandler.
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.AssetImporters;
using UnityEngine;

namespace Promptimate.Editor
{
    [System.Serializable]
    public class KimodoFile
    {
        public int version;
        public float fps;
        public string prompt;
        public int frames;
        public int joints;
        public string[] names;
        public int[] parents;
        public float[] offsets; // joints*3, Kimodo space
        public float[] root;    // frames*3, hips position, Kimodo space
        public float[] rot;     // frames*joints*4, local xyzw, Kimodo space
        public float[] refPos;  // optional frames*joints*3 global joint positions (Python FK), Kimodo space
        // Optional hints from the MCP server (missing = false). The importer's "From File" options follow them.
        public bool loop;       // motion is meant to loop (cycle)
        public bool inPlace;    // strip travel: the character should stay on the spot (locomotion driven by code)

        internal KimodoFile Clone()
        {
            var c = (KimodoFile)MemberwiseClone();
            c.root = (float[])root?.Clone();
            c.refPos = (float[])refPos?.Clone();
            return c;
        }
    }

    public enum KimodoLoopMode
    {
        [InspectorName("From File (default: off)")] FromFile,
        On,
        Off,
    }

    public enum KimodoRootMotion
    {
        [InspectorName("From File (default: root motion)")] FromFile,
        [InspectorName("Root Motion (moves with Apply Root Motion)")] RootMotion,
        [InspectorName("In Place (travel removed)")] InPlace,
    }

    public enum KimodoHandPose
    {
        [InspectorName("Relaxed (natural slight curl)")] Relaxed,
        [InspectorName("Open (flat hand)")] Open,
        Fist,
        [InspectorName("None (no finger curves)")] None,
    }

    /// Resolved import options (importer settings combined with the file's hints).
    internal struct BakeOptions
    {
        public bool loop, loopPose, inPlace, bakeRootRotation, bakeRootHeight, ikGoals;
        public float cycleOffset;
        public KimodoHandPose hands;

        /// Neutral options: what the core conversion checks run against (no loop, full root motion, no hand curves).
        public static BakeOptions Neutral => new BakeOptions { bakeRootHeight = true, hands = KimodoHandPose.None, ikGoals = true };
    }

    [ScriptedImporter(4, "kimodo")]
    public class KimodoImporter : ScriptedImporter
    {
        [Header("Loop")]
        [Tooltip("Loop Time. From File follows the \"loop\" flag the MCP server writes; off when the file has none.")]
        public KimodoLoopMode loop = KimodoLoopMode.FromFile;
        [Tooltip("Loop Pose: Unity blends the end of the clip into its start so the loop has no pop.")]
        public bool loopPose = true;
        [Tooltip("Cycle Offset (fraction of the clip) for looping clips.")]
        [Range(-1f, 1f)] public float cycleOffset = 0f;

        [Header("Root Motion")]
        [Tooltip("Root Motion: forward travel and turning are root motion; with Animator > Apply Root Motion the character moves.\n" +
                 "In Place: travel is removed from the motion (body sway is kept) and baked into the pose; the character stays on the spot.\n" +
                 "From File follows the \"inPlace\" flag the MCP server writes.")]
        public KimodoRootMotion rootMotion = KimodoRootMotion.FromFile;
        [Tooltip("Root Motion mode only: keep turning in the pose instead of rotating the GameObject (Root Transform Rotation > Bake Into Pose). In Place always bakes rotation.")]
        public bool bakeRootRotation = false;
        [Tooltip("Keep vertical motion (crouch, bob, jumps) in the pose instead of moving the GameObject up and down (Root Transform Position Y > Bake Into Pose). Recommended.")]
        public bool bakeRootHeight = true;

        [Header("Hands")]
        [Tooltip("The model generates no finger motion. Relaxed adds a natural resting hand (slight curl, thumb in) as finger muscle curves. None writes no finger curves so another layer can drive the fingers.")]
        public KimodoHandPose handPose = KimodoHandPose.Relaxed;

        [Header("IK")]
        [Tooltip("Write foot and hand IK goal curves, like Unity's FBX importer does. Needed wherever Foot IK is applied: Timeline " +
                 "(Apply Foot IK is on by default), AnimationClipPlayable, Animator states with Foot IK. Without them the feet are pulled to the hips. " +
                 "With them, Foot IK keeps the feet on the generated foot path on characters with other proportions.")]
        public bool ikGoalCurves = true;

        // SOMA joint -> Unity HumanBodyBones name. Unlisted SOMA joints (Neck2, hand end sites) are unmapped.
        static readonly Dictionary<string, string> HumanMap = new Dictionary<string, string>
        {
            {"Hips", "Hips"}, {"Spine1", "Spine"}, {"Spine2", "Chest"}, {"Chest", "UpperChest"},
            {"Neck1", "Neck"}, {"Head", "Head"}, {"Jaw", "Jaw"},
            {"LeftEye", "LeftEye"}, {"RightEye", "RightEye"},
            {"LeftShoulder", "LeftShoulder"}, {"LeftArm", "LeftUpperArm"}, {"LeftForeArm", "LeftLowerArm"}, {"LeftHand", "LeftHand"},
            {"RightShoulder", "RightShoulder"}, {"RightArm", "RightUpperArm"}, {"RightForeArm", "RightLowerArm"}, {"RightHand", "RightHand"},
            {"LeftLeg", "LeftUpperLeg"}, {"LeftShin", "LeftLowerLeg"}, {"LeftFoot", "LeftFoot"}, {"LeftToeBase", "LeftToes"},
            {"RightLeg", "RightUpperLeg"}, {"RightShin", "RightLowerLeg"}, {"RightFoot", "RightFoot"}, {"RightToeBase", "RightToes"},
        };

        // Kimodo is right-handed Y-up (character faces +Z); Unity is left-handed Y-up. Mirror X.
        internal static Vector3 ToUnity(float x, float y, float z) =>
            Variant == ConversionVariant.NoMirror ? new Vector3(x, y, z) : new Vector3(-x, y, z);
        internal static Quaternion ToUnity(float x, float y, float z, float w) =>
            Variant == ConversionVariant.NoMirror || Variant == ConversionVariant.RawQuaternion
                ? new Quaternion(x, y, z, w) : new Quaternion(x, -y, -z, w);

        /// Deliberately broken conversions, used only by the validator self-test (negative controls).
        internal enum ConversionVariant { Correct, NoMirror, RawQuaternion, Yaw180, RootZFlipped }
        internal static ConversionVariant Variant = ConversionVariant.Correct;

        internal BakeOptions Resolve(KimodoFile data) => new BakeOptions
        {
            loop = loop == KimodoLoopMode.On || (loop == KimodoLoopMode.FromFile && data.loop),
            loopPose = loopPose,
            cycleOffset = cycleOffset,
            inPlace = rootMotion == KimodoRootMotion.InPlace || (rootMotion == KimodoRootMotion.FromFile && data.inPlace),
            bakeRootRotation = bakeRootRotation,
            bakeRootHeight = bakeRootHeight,
            hands = handPose,
            ikGoals = ikGoalCurves,
        };

        internal static GameObject BuildRig(KimodoFile data, out Transform[] bones)
        {
            var rigRoot = new GameObject("KimodoRig");
            bones = new Transform[data.joints];
            for (int j = 0; j < data.joints; j++)
            {
                var t = new GameObject(data.names[j]).transform;
                t.SetParent(data.parents[j] < 0 ? rigRoot.transform : bones[data.parents[j]], false);
                t.localPosition = ToUnity(data.offsets[j * 3], data.offsets[j * 3 + 1], data.offsets[j * 3 + 2]);
                t.localRotation = Quaternion.identity;
                bones[j] = t;
            }
            return rigRoot;
        }

        /// Builds a Humanoid avatar for a rig whose bones carry SOMA joint names, using its current pose as rest.
        /// The rest pose is SOMA's T-pose (arms level along X, legs straight), which is what Unity's muscle space
        /// expects, so no T-pose correction is needed. Twist/stretch/feet values are Unity's ModelImporter defaults:
        /// Mixamo and most FBX humanoids are imported with exactly these, so muscle values transfer 1:1.
        /// Translation DoF stays off: SOMA bone lengths are constant, there is no translation to carry.
        internal static Avatar BuildAvatar(GameObject rigRoot, Transform[] bones)
        {
            // Every transform under the root (the SOMA bones, plus finger bones on the validator's test rig).
            var all = rigRoot.GetComponentsInChildren<Transform>(true);
            var human = new List<HumanBone>();
            foreach (var b in all)
                if (HumanMap.TryGetValue(b.name, out var hb) || ExtraHumanMap.TryGetValue(b.name, out hb))
                    human.Add(new HumanBone { boneName = b.name, humanName = HumanTrait.BoneName[(int)System.Enum.Parse(typeof(HumanBodyBones), hb)], limit = new HumanLimit { useDefaultValues = true } });
            var skeleton = new List<SkeletonBone> { new SkeletonBone { name = rigRoot.name, position = Vector3.zero, rotation = Quaternion.identity, scale = Vector3.one } };
            foreach (var b in all)
                if (b != rigRoot.transform) skeleton.Add(new SkeletonBone { name = b.name, position = b.localPosition, rotation = b.localRotation, scale = Vector3.one });
            var desc = new HumanDescription
            {
                human = human.ToArray(), skeleton = skeleton.ToArray(),
                upperArmTwist = 0.5f, lowerArmTwist = 0.5f, upperLegTwist = 0.5f, lowerLegTwist = 0.5f,
                armStretch = 0.05f, legStretch = 0.05f, feetSpacing = 0f, hasTranslationDoF = false,
            };
            return AvatarBuilder.BuildHumanAvatar(rigRoot, desc);
        }

        /// Optional extra mappings (finger bones), used only by the validator's synthetic test rig.
        internal static readonly Dictionary<string, string> ExtraHumanMap = BuildFingerMap();

        static Dictionary<string, string> BuildFingerMap()
        {
            var m = new Dictionary<string, string>();
            string[] unityFinger = { "Thumb", "Index", "Middle", "Little", "Ring" };
            string[] unityPhalanx = { "Proximal", "Intermediate", "Distal" };
            foreach (var side in new[] { "Left", "Right" })
                foreach (var f in unityFinger)
                    for (int i = 0; i < 3; i++)
                        m[$"{side}Hand{f}{i + 1}"] = $"{side}{f}{unityPhalanx[i]}";
            return m;
        }

        /// Poses a rig with the source (Kimodo) frame f, converted to Unity space.
        internal static void ApplySourceFrame(KimodoFile data, Transform[] bones, int f)
        {
            int J = data.joints;
            var rootPos = ToUnity(data.root[f * 3], data.root[f * 3 + 1], data.root[f * 3 + 2]);
            if (Variant == ConversionVariant.Yaw180) rootPos = new Vector3(-rootPos.x, rootPos.y, -rootPos.z);
            if (Variant == ConversionVariant.RootZFlipped) rootPos.z = -rootPos.z;
            bones[0].localPosition = rootPos;
            for (int j = 0; j < J; j++)
            {
                int o = (f * J + j) * 4;
                bones[j].localRotation = ToUnity(data.rot[o], data.rot[o + 1], data.rot[o + 2], data.rot[o + 3]);
            }
            if (Variant == ConversionVariant.Yaw180) bones[0].localRotation = Quaternion.Euler(0, 180, 0) * bones[0].localRotation;
        }

        /// In-place source: subtracts the hips' ground-plane travel (1 s moving average, linear-extrapolated at the
        /// ends so a straight walk is removed exactly) from the root and, consistently, from refPos. Sway, bob and
        /// turning stay. Coordinates stay in Kimodo space (X/Z are ground axes in both spaces).
        internal static KimodoFile MakeInPlace(KimodoFile src)
        {
            var d = src.Clone();
            int F = d.frames, J = d.joints;
            int half = Mathf.Max(1, Mathf.RoundToInt(d.fps * 0.5f));
            foreach (int axis in new[] { 0, 2 })
            {
                float P(int f)
                {
                    // Odd reflection keeps linear trends at the boundaries.
                    if (f < 0) return 2 * src.root[axis] - src.root[(-f) * 3 + axis];
                    if (f >= F) return 2 * src.root[(F - 1) * 3 + axis] - src.root[(2 * (F - 1) - f) * 3 + axis];
                    return src.root[f * 3 + axis];
                }
                for (int f = 0; f < F; f++)
                {
                    double s = 0;
                    for (int k = -half; k <= half; k++) s += P(Mathf.Clamp(f + k, -(F - 1), 2 * (F - 1)));
                    float trend = (float)(s / (2 * half + 1));
                    d.root[f * 3 + axis] -= trend;
                    if (d.refPos != null && d.refPos.Length == F * J * 3)
                        for (int j = 0; j < J; j++) d.refPos[(f * J + j) * 3 + axis] -= trend;
                }
            }
            return d;
        }

        public override void OnImportAsset(AssetImportContext ctx)
        {
            var data = JsonUtility.FromJson<KimodoFile>(File.ReadAllText(ctx.assetPath));
            int J = data.joints, F = data.frames;
            if (data.rot == null || data.root == null || F < 2 || data.rot.Length != F * J * 4 || data.root.Length != F * 3)
            {
                ctx.LogImportError("Malformed .kimodo file");
                return;
            }

            var opts = Resolve(data);
            if (opts.inPlace) data = MakeInPlace(data);
            var name = Path.GetFileNameWithoutExtension(ctx.assetPath);
            var clip = Bake(data, name, opts, out var avatar, out var error);
            if (clip == null)
            {
                ctx.LogImportError(error);
                return;
            }
            ctx.AddObjectToAsset("clip", clip);
            ctx.AddObjectToAsset("avatar", avatar);
            ctx.SetMainObject(clip);

            // Self-check: replay the baked clip through Unity's humanoid system and compare with the source.
            var report = KimodoValidator.Validate(data, clip, avatar, opts);
            report.asset = ctx.assetPath;
            KimodoValidator.WriteReport(report);
            if (!report.passed)
                ctx.LogImportWarning($"Promptimate validation FAILED for {ctx.assetPath}: {string.Join("; ", report.failures)}");
        }

        /// Bakes source motion into a Humanoid clip (muscles + RootT/RootQ) via a SOMA rig and HumanPoseHandler.
        internal static AnimationClip Bake(KimodoFile data, string name, BakeOptions opts, out Avatar avatar, out string error)
        {
            int F = data.frames;
            var rigRoot = BuildRig(data, out var bones);
            avatar = null; error = null;
            try
            {
                avatar = BuildAvatar(rigRoot, bones);
                avatar.name = name + "_SomaAvatar";
                if (!avatar.isValid || !avatar.isHuman)
                {
                    error = "Failed to build humanoid avatar for SOMA rig";
                    return null;
                }

                var handler = new HumanPoseHandler(avatar, rigRoot.transform);
                var pose = new HumanPose();
                int muscleCount = HumanTrait.MuscleCount;
                var muscleCurves = new AnimationCurve[muscleCount];
                for (int m = 0; m < muscleCount; m++) muscleCurves[m] = new AnimationCurve();
                var rootT = new[] { new AnimationCurve(), new AnimationCurve(), new AnimationCurve() };
                var rootQ = new[] { new AnimationCurve(), new AnimationCurve(), new AnimationCurve(), new AnimationCurve() };
                float dt = 1f / data.fps;
                Quaternion prev = Quaternion.identity;

                for (int f = 0; f < F; f++)
                {
                    ApplySourceFrame(data, bones, f);
                    handler.GetHumanPose(ref pose);
                    float t = f * dt;
                    for (int m = 0; m < muscleCount; m++) muscleCurves[m].AddKey(t, pose.muscles[m]);
                    rootT[0].AddKey(t, pose.bodyPosition.x); rootT[1].AddKey(t, pose.bodyPosition.y); rootT[2].AddKey(t, pose.bodyPosition.z);
                    var q = pose.bodyRotation;
                    if (f > 0 && Quaternion.Dot(prev, q) < 0) q = new Quaternion(-q.x, -q.y, -q.z, -q.w); // sign continuity
                    prev = q;
                    rootQ[0].AddKey(t, q.x); rootQ[1].AddKey(t, q.y); rootQ[2].AddKey(t, q.z); rootQ[3].AddKey(t, q.w);
                }
                handler.Dispose();

                var clip = new AnimationClip { name = name, frameRate = data.fps };
                var anim = typeof(Animator);
                string[] tq = { "x", "y", "z" }, qq = { "x", "y", "z", "w" };
                for (int i = 0; i < 3; i++) clip.SetCurve("", anim, "RootT." + tq[i], rootT[i]);
                for (int i = 0; i < 4; i++) clip.SetCurve("", anim, "RootQ." + qq[i], rootQ[i]);
                var hand = HandPoseMuscles(opts.hands);
                float end = (F - 1) * dt;
                for (int m = 0; m < muscleCount; m++)
                {
                    var mName = HumanTrait.MuscleName[m];
                    if (IsFingerMuscle(mName))
                    {
                        // The model has no finger data: write a constant hand pose (or nothing for None).
                        if (hand == null) continue;
                        hand.TryGetValue(mName, out var v);
                        clip.SetCurve("", anim, MusclePropertyName(mName), AnimationCurve.Constant(0, end, v));
                    }
                    else clip.SetCurve("", anim, MusclePropertyName(mName), muscleCurves[m]);
                }

                // Settings first: the goals are taken from the pose as Unity actually plays it (Loop Pose blends the
                // muscles towards the loop point but not goal curves, so goals baked from the raw pose would disagree).
                AnimationUtility.SetAnimationClipSettings(clip, ClipSettings(clip, opts));
                if (opts.ikGoals)
                {
                    var probeRig = BuildRig(data, out _);
                    try { IKGoals.AddGoalCurves(clip, probeRig, avatar, F, data.fps); }
                    finally { Object.DestroyImmediate(probeRig); }
                    AnimationUtility.SetAnimationClipSettings(clip, ClipSettings(clip, opts)); // SetCurve can reset stop time
                }
                return clip;
            }
            finally
            {
                Object.DestroyImmediate(rigRoot);
            }
        }

        internal static AnimationClipSettings ClipSettings(AnimationClip clip, BakeOptions o)
        {
            var s = AnimationUtility.GetAnimationClipSettings(clip);
            s.loopTime = o.loop;
            s.loopBlend = o.loop && o.loopPose;
            s.cycleOffset = o.cycleOffset;
            s.mirror = false;
            // "Based Upon: Original" everywhere. The clip has no separate root track, so Unity derives the root from the
            // body, but with "Body Orientation" it also rotates the root so the clip's average body direction lines up
            // with its velocity: generated walks that crab slightly (a few degrees) then leave their path (measured 1 m
            // over 14 m). With Original, Apply Root Motion reproduces the generated world path exactly and the GameObject
            // still turns with the character.
            s.loopBlendOrientation = o.inPlace || o.bakeRootRotation;
            s.keepOriginalOrientation = true;
            s.orientationOffsetY = 0f;
            s.loopBlendPositionXZ = o.inPlace;
            s.keepOriginalPositionXZ = true;
            // Height baked into the pose relative to the original floor (y = 0, where the source stands): feet stay
            // exactly as generated and the GameObject never bobs. Not baked: the GameObject follows the body up and down.
            s.loopBlendPositionY = o.bakeRootHeight;
            s.keepOriginalPositionY = true;
            s.heightFromFeet = false;
            s.level = 0f;
            return s;
        }

        // ---- Hands ----------------------------------------------------------------------------------------------

        internal static bool IsFingerMuscle(string muscle)
        {
            foreach (var f in Fingers)
                if (muscle.StartsWith("Left " + f + " ") || muscle.StartsWith("Right " + f + " ")) return true;
            return false;
        }

        static readonly string[] Fingers = { "Thumb", "Index", "Middle", "Ring", "Little" };

        // Per finger: 1 Stretched, Spread, 2 Stretched, 3 Stretched, in Unity muscle units (default limits, which Mixamo
        // and most FBX humanoids use). Measured on a Mixamo avatar: muscle 0 is NOT a flat hand, it is a ~33/37/36 deg
        // curl per joint; flat T-pose fingers are about 0.67 / 0.81 / 0.81. Per-joint flex ~= 33 - 50*v (joint 1),
        // 37 - 45*v (joints 2, 3). Thumb: lower 1 Stretched = closer to the index, lower Spread = in front of the palm.
        //                                          Thumb                           Index                          Middle                         Ring                           Little
        static readonly float[,] RelaxedPose = { { -0.80f, -0.30f, 0.10f, 0.00f }, { 0.22f, -0.35f, 0.04f, 0.47f }, { 0.12f, -0.60f, -0.07f, 0.40f }, { 0.04f, -0.55f, -0.16f, 0.36f }, { -0.04f, -0.25f, -0.24f, 0.31f } };
        static readonly float[,] OpenPose =    { { -0.50f, 0.20f, 0.60f, 0.60f }, { 0.67f, -0.45f, 0.81f, 0.81f }, { 0.67f, -0.61f, 0.81f, 0.81f }, { 0.67f, -0.61f, 0.81f, 0.81f }, { 0.67f, -0.46f, 0.81f, 0.81f } };
        static readonly float[,] FistPose =    { { -1.00f, -0.80f, -0.40f, -0.60f }, { -1.00f, -0.40f, -1.00f, -0.50f }, { -1.00f, -0.60f, -1.00f, -0.50f }, { -1.00f, -0.60f, -1.00f, -0.50f }, { -1.00f, -0.40f, -1.00f, -0.50f } };

        /// Finger muscle name -> value for a hand pose; null for None (write no finger curves).
        internal static Dictionary<string, float> HandPoseMuscles(KimodoHandPose pose)
        {
            if (pose == KimodoHandPose.None) return null;
            var table = pose == KimodoHandPose.Relaxed ? RelaxedPose : pose == KimodoHandPose.Fist ? FistPose : OpenPose;
            var m = new Dictionary<string, float>();
            string[] part = { "1 Stretched", "Spread", "2 Stretched", "3 Stretched" };
            foreach (var side in new[] { "Left", "Right" })
                for (int f = 0; f < 5; f++)
                    for (int p = 0; p < 4; p++)
                        m[$"{side} {Fingers[f]} {part[p]}"] = table[f, p];
            return m;
        }

        // HumanTrait finger muscle names ("Left Thumb 1 Stretched") differ from Animator property names
        // ("LeftHand.Thumb.1 Stretched"). Body muscle names are identical.
        internal static string MusclePropertyName(string muscle)
        {
            foreach (var side in new[] { "Left", "Right" })
                foreach (var finger in Fingers)
                {
                    string prefix = side + " " + finger + " ";
                    if (muscle.StartsWith(prefix))
                    {
                        var rest = muscle.Substring(prefix.Length); // e.g. "1 Stretched" or "Spread"
                        if (rest.Length > 1 && char.IsDigit(rest[0]))
                            return side + "Hand." + finger + "." + rest[0] + " " + rest.Substring(2);
                        return side + "Hand." + finger + "." + rest;
                    }
                }
            return muscle;
        }
    }
}
