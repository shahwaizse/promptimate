// Loads a character (FBX imported as Humanoid, or a glTF/GLB through glTFast), gives it a Humanoid avatar if it has
// none (GLB), normalises its height and converts its materials to URP Lit.
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace ShotStudio
{
    public static class Cast
    {
        public static GameObject Spawn(ActorSpec a)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(a.model);
            if (prefab == null) throw new System.Exception("missing model " + a.model + " (run unity/DemoStudio/fetch_render_assets.py)");
            var go = (GameObject)Object.Instantiate(prefab);
            go.name = string.IsNullOrEmpty(a.id) ? prefab.name : a.id;
            go.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            foreach (var legacy in go.GetComponentsInChildren<Animation>(true)) Object.DestroyImmediate(legacy); // glTF clips
            var anim = go.GetComponent<Animator>() ?? go.AddComponent<Animator>();
            if (anim.avatar == null || !anim.avatar.isHuman)
            {
                anim.avatar = BuildAvatar(go);
                anim.Rebind();
            }
            anim.applyRootMotion = false;
            anim.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            Normalise(go, anim, a.height);
            if (a.build > 0 && Mathf.Abs(a.build - 1) > 1e-3f)
            {
                var ls = go.transform.localScale;
                go.transform.localScale = new Vector3(ls.x * a.build, ls.y, ls.z * a.build);
            }
            Materials.ConvertAll(go, string.IsNullOrEmpty(a.skin) ? null : AssetDatabase.LoadAssetAtPath<Texture2D>(a.skin));
            foreach (var r in go.GetComponentsInChildren<Renderer>())
            {
                r.shadowCastingMode = ShadowCastingMode.On;
                r.receiveShadows = true;
            }
            // Manual rendering skips Unity's per-frame skinning update: force fresh skinning on every render.
            foreach (var smr in go.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                smr.updateWhenOffscreen = true;
                smr.forceMatrixRecalculationPerRender = true;
            }
            return go;
        }

        /// Scales the character so its standing height (feet to top of head) is `height` metres.
        static void Normalise(GameObject go, Animator anim, float height)
        {
            var head = anim.GetBoneTransform(HumanBodyBones.Head);
            var lf = anim.GetBoneTransform(HumanBodyBones.LeftFoot);
            float top = MeshTop(go);
            float rest = 0;
            if (top > 0 && lf) rest = top - Mathf.Min(MeshBottom(go), lf.position.y);
            else if (head && lf) rest = (head.position.y - lf.position.y) * 1.13f;
            Debug.Log($"SHOT_CAST {go.name} top={top} bottom={MeshBottom(go)} head={(head ? head.position.y : -1)} lfoot={(lf ? lf.position.y : -1)} rest={rest} scale0={go.transform.localScale.x} lossy={go.transform.lossyScale.x}");
            if (rest > 0.01f) go.transform.localScale *= height / rest;
        }

        static float MeshTop(GameObject go)
        {
            float top = float.MinValue;
            foreach (var smr in go.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                var m = new Mesh();
                smr.BakeMesh(m, true);
                var mtx = smr.transform.localToWorldMatrix; // BakeMesh(useScale) output is in the renderer's local space
                foreach (var v in m.vertices) top = Mathf.Max(top, mtx.MultiplyPoint3x4(v).y);
                Object.DestroyImmediate(m);
            }
            return top == float.MinValue ? -1 : top;
        }

        static float MeshBottom(GameObject go)
        {
            float bot = float.MaxValue;
            foreach (var smr in go.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                var m = new Mesh();
                smr.BakeMesh(m, true);
                var mtx = smr.transform.localToWorldMatrix; // BakeMesh(useScale) output is in the renderer's local space
                foreach (var v in m.vertices) bot = Mathf.Min(bot, mtx.MultiplyPoint3x4(v).y);
                Object.DestroyImmediate(m);
            }
            return bot == float.MaxValue ? 0 : bot;
        }

        // ---- Humanoid avatar for rigs that come without one (glTF) ---------------------------------------------------

        // Name patterns per human bone, tried in order (Quaternius, Blender/Rigify-like, Mixamo-like).
        static readonly (string human, string[] names)[] Map =
        {
            ("Hips", new[] { "Hips", "pelvis", "mixamorig:Hips" }),
            ("Spine", new[] { "Abdomen", "Spine", "spine", "spine_01" }),
            ("Chest", new[] { "Torso", "Spine1", "Chest", "spine_02" }),
            ("UpperChest", new[] { "Chest", "Spine2", "spine_03" }),
            ("Neck", new[] { "Neck", "neck", "neck_01" }),
            ("Head", new[] { "Head", "head" }),
            ("LeftShoulder", new[] { "Shoulder.L", "LeftShoulder", "clavicle_l" }),
            ("LeftUpperArm", new[] { "UpperArm.L", "LeftArm", "upperarm_l" }),
            ("LeftLowerArm", new[] { "LowerArm.L", "LeftForeArm", "lowerarm_l" }),
            ("LeftHand", new[] { "Wrist.L", "Palm.L", "Hand.L", "Fist.L", "LeftHand", "hand_l" }),
            ("RightShoulder", new[] { "Shoulder.R", "RightShoulder", "clavicle_r" }),
            ("RightUpperArm", new[] { "UpperArm.R", "RightArm", "upperarm_r" }),
            ("RightLowerArm", new[] { "LowerArm.R", "RightForeArm", "lowerarm_r" }),
            ("RightHand", new[] { "Wrist.R", "Palm.R", "Hand.R", "Fist.R", "RightHand", "hand_r" }),
            ("LeftUpperLeg", new[] { "UpperLeg.L", "LeftUpLeg", "thigh_l" }),
            ("LeftLowerLeg", new[] { "LowerLeg.L", "LeftLeg", "calf_l" }),
            ("LeftFoot", new[] { "Foot.L", "LeftFoot", "foot_l" }),
            ("LeftToes", new[] { "Toes.L", "LeftToeBase", "ball_l" }),
            ("RightUpperLeg", new[] { "UpperLeg.R", "RightUpLeg", "thigh_r" }),
            ("RightLowerLeg", new[] { "LowerLeg.R", "RightLeg", "calf_r" }),
            ("RightFoot", new[] { "Foot.R", "RightFoot", "foot_r" }),
            ("RightToes", new[] { "Toes.R", "RightToeBase", "ball_r" }),
        };
        static readonly string[] Fingers = { "Thumb", "Index", "Middle", "Ring", "Little" };
        static readonly string[] Phal = { "Proximal", "Intermediate", "Distal" };

        static Avatar BuildAvatar(GameObject go)
        {
            var all = go.GetComponentsInChildren<Transform>(true);
            Transform Find(params string[] names)
            {
                foreach (var n in names)
                {
                    var t = all.FirstOrDefault(x => x.name == n);
                    if (t) return t;
                }
                return null;
            }
            RestoreBindPose(go);
            var bones = new Dictionary<string, Transform>();
            foreach (var (hname, names) in Map)
            {
                var t = Find(names);
                if (t && !bones.ContainsValue(t)) bones[hname] = t;
            }
            // Chest/UpperChest: only when the chain really has them between spine and neck.
            if (bones.TryGetValue("UpperChest", out var uc) && bones.TryGetValue("Neck", out var nk) && !nk.IsChildOf(uc)) bones.Remove("UpperChest");
            foreach (var side in new[] { "L", "R" })
            {
                string sideName = side == "L" ? "Left" : "Right";
                foreach (var f in Fingers)
                {
                    string src = f == "Little" ? "Pinky" : f;
                    for (int k = 0; k < 3; k++)
                    {
                        var t = Find($"{src}{k + 1}.{side}");
                        if (t) bones[$"{sideName} {f} {Phal[k]}"] = t;
                    }
                }
            }
            foreach (var need in new[] { "Hips", "Spine", "Head", "LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm", "RightLowerArm", "RightHand", "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperLeg", "RightLowerLeg", "RightFoot" })
                if (!bones.ContainsKey(need)) throw new System.Exception($"{go.name}: no bone for {need}; can't build a Humanoid avatar");

            // IK-style rigs (Quaternius): legs hang off a 'Body' bone next to the hips and the feet off the rig root.
            // Humanoid needs hips > upper leg > lower leg > foot. Re-parenting keeps world transforms; skinning uses the
            // bone transforms directly, so the mesh is unaffected.
            void Reparent(string child, string parent)
            {
                var c = bones[child]; var p = bones[parent];
                if (!c.IsChildOf(p)) c.SetParent(p, true);
            }
            Reparent("LeftUpperLeg", "Hips"); Reparent("RightUpperLeg", "Hips");
            Reparent("LeftFoot", "LeftLowerLeg"); Reparent("RightFoot", "RightLowerLeg");
            Reparent("Spine", "Hips");

            var human = new List<HumanBone>();
            var hb = HumanTrait.BoneName;
            foreach (var kv in bones)
            {
                string unityName = hb.FirstOrDefault(n => n.Replace(" ", "") == kv.Key.Replace(" ", ""));
                if (unityName == null) continue;
                human.Add(new HumanBone { humanName = unityName, boneName = kv.Value.name, limit = new HumanLimit { useDefaultValues = true } });
            }
            var skel = go.GetComponentsInChildren<Transform>(true).Select(t => new SkeletonBone
            { name = t.name, position = t.localPosition, rotation = t.localRotation, scale = t.localScale }).ToArray();
            var desc = new HumanDescription
            {
                human = human.ToArray(), skeleton = skel,
                upperArmTwist = 0.5f, lowerArmTwist = 0.5f, upperLegTwist = 0.5f, lowerLegTwist = 0.5f,
                armStretch = 0.05f, legStretch = 0.05f, feetSpacing = 0, hasTranslationDoF = false,
            };
            var av = AvatarBuilder.BuildHumanAvatar(go, desc);
            if (!av.isValid || !av.isHuman) throw new System.Exception($"{go.name}: AvatarBuilder failed");
            av.name = go.name + "_Avatar";
            return av;
        }

        /// Puts every skinned bone back into the mesh's bind pose (glTF files often store an arms-down pose in the
        /// nodes while the mesh is bound in a T-pose; Humanoid retargeting expects the T-pose).
        static void RestoreBindPose(GameObject go)
        {
            var world = new Dictionary<Transform, Matrix4x4>();
            foreach (var smr in go.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                var bp = smr.sharedMesh ? smr.sharedMesh.bindposes : null;
                if (bp == null || bp.Length != smr.bones.Length) continue;
                var meshToWorld = smr.transform.localToWorldMatrix;
                for (int i = 0; i < bp.Length; i++)
                    if (smr.bones[i] && !world.ContainsKey(smr.bones[i])) world[smr.bones[i]] = meshToWorld * bp[i].inverse;
            }
            // Parents first, so children are placed after their parent moved.
            foreach (var t in go.GetComponentsInChildren<Transform>(true))
            {
                if (!world.TryGetValue(t, out var m)) continue;
                t.position = m.GetColumn(3);
                t.rotation = m.rotation;
            }
        }
    }
}
