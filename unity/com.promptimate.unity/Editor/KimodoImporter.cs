// Research MVP: imports a .kimodo motion file (written by the kimodo MCP server) as a Humanoid AnimationClip.
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
    }

    [ScriptedImporter(3, "kimodo")]
    public class KimodoImporter : ScriptedImporter
    {
        [Tooltip("Loop the clip (sets loopTime).")]
        public bool loop = false;

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
        internal static Avatar BuildAvatar(GameObject rigRoot, Transform[] bones)
        {
            var human = new List<HumanBone>();
            foreach (var b in bones)
                if (HumanMap.TryGetValue(b.name, out var hb))
                    human.Add(new HumanBone { boneName = b.name, humanName = HumanTrait.BoneName[(int)System.Enum.Parse(typeof(HumanBodyBones), hb)], limit = new HumanLimit { useDefaultValues = true } });
            var skeleton = new List<SkeletonBone> { new SkeletonBone { name = rigRoot.name, position = Vector3.zero, rotation = Quaternion.identity, scale = Vector3.one } };
            foreach (var b in bones)
                skeleton.Add(new SkeletonBone { name = b.name, position = b.localPosition, rotation = b.localRotation, scale = Vector3.one });
            var desc = new HumanDescription
            {
                human = human.ToArray(), skeleton = skeleton.ToArray(),
                upperArmTwist = 0.5f, lowerArmTwist = 0.5f, upperLegTwist = 0.5f, lowerLegTwist = 0.5f,
                armStretch = 0.05f, legStretch = 0.05f, feetSpacing = 0f, hasTranslationDoF = false,
            };
            return AvatarBuilder.BuildHumanAvatar(rigRoot, desc);
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

        public override void OnImportAsset(AssetImportContext ctx)
        {
            var data = JsonUtility.FromJson<KimodoFile>(File.ReadAllText(ctx.assetPath));
            int J = data.joints, F = data.frames;
            if (data.rot == null || data.rot.Length != F * J * 4 || data.root.Length != F * 3)
            {
                ctx.LogImportError("Malformed .kimodo file");
                return;
            }

            var name = Path.GetFileNameWithoutExtension(ctx.assetPath);
            var clip = Bake(data, name, loop, out var avatar, out var error);
            if (clip == null)
            {
                ctx.LogImportError(error);
                return;
            }
            ctx.AddObjectToAsset("clip", clip);
            ctx.AddObjectToAsset("avatar", avatar);
            ctx.SetMainObject(clip);

            // Self-check: replay the baked clip through Unity's humanoid system and compare with the source.
            var report = KimodoValidator.Validate(data, clip, avatar);
            report.asset = ctx.assetPath;
            KimodoValidator.WriteReport(report);
            if (!report.passed)
                ctx.LogImportWarning($"Promptimate validation FAILED for {ctx.assetPath}: {string.Join("; ", report.failures)}");
        }

        /// Bakes source motion into a Humanoid clip (muscles + RootT/RootQ) via a SOMA rig and HumanPoseHandler.
        internal static AnimationClip Bake(KimodoFile data, string name, bool loop, out Avatar avatar, out string error)
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
                for (int m = 0; m < muscleCount; m++)
                    clip.SetCurve("", anim, MusclePropertyName(HumanTrait.MuscleName[m]), muscleCurves[m]);

                var settings = AnimationUtility.GetAnimationClipSettings(clip);
                settings.loopTime = loop;
                AnimationUtility.SetAnimationClipSettings(clip, settings);
                return clip;
            }
            finally
            {
                Object.DestroyImmediate(rigRoot);
            }
        }

        // HumanTrait finger muscle names ("Left Thumb 1 Stretched") differ from Animator property names
        // ("LeftHand.Thumb.1 Stretched"). Body muscle names are identical.
        static string MusclePropertyName(string muscle)
        {
            foreach (var side in new[] { "Left", "Right" })
                foreach (var finger in new[] { "Thumb", "Index", "Middle", "Ring", "Little" })
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
