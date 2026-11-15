// Optional helper for Humanoid characters playing Promptimate clips (or any clips). Runs after the Animator
// (LateUpdate) and fixes what retargeting onto other body shapes can't know about:
//   - Seat: when sitting or squatting, a character with a fuller body than the source sinks into the floor (Unity
//     places the body by centre of mass; it doesn't know the mesh). The hips are raised just enough to keep the seat
//     (measured from this character's own mesh) on the floor, and the feet are put back where they were with leg IK.
//   - Soles: a foot whose sole would go below the floor is lifted onto it with leg IK (feet sink when Foot IK is off).
// The floor is this GameObject's height (where the character stands), plus floorOffset.
// Measured on Mixamo/Kenney characters sitting on the floor: seat 6-21 cm into the floor -> on the floor.
using UnityEngine;

namespace Promptimate
{
    static class GroundingExt
    {
        /// GetComponentsInChildren includes the parent itself first: drop it.
        public static Transform[] Skip1(this Transform[] a) { var o = new Transform[Mathf.Max(0, a.Length - 1)]; System.Array.Copy(a, 1, o, 0, o.Length); return o; }
    }

    [AddComponentMenu("Promptimate/Promptimate Grounding")]
    [RequireComponent(typeof(Animator))]
    [DefaultExecutionOrder(1000)]
    public class PromptimateGrounding : MonoBehaviour
    {
        [Tooltip("Raise the hips when the seat would go through the floor (sitting / squatting), feet stay put.")]
        public bool keepSeatAboveFloor = true;
        [Tooltip("Lift feet whose soles would go below the floor.")]
        public bool keepFeetAboveFloor = true;
        [Tooltip("Lift hands whose fingertips would go below the floor (leaning on the floor while sitting down).")]
        public bool keepHandsAboveFloor = true;
        [Tooltip("Floor height relative to this GameObject (m).")]
        public float floorOffset = 0f;
        [Header("Calibration (measured from the bind pose when added / at startup)")]
        [Tooltip("Points on the seat surface (buttocks and upper thighs), sampled from this character's skinned mesh, in the " +
                 "local space of the bone they move with (seatBones: 0 = hips, 1 = left upper leg, 2 = right upper leg).")]
        public Vector3[] seatPoints;
        [HideInInspector] public int[] seatBones;
        [Tooltip("Ankle (foot bone) height above the sole in the bind pose, local units.")]
        public float ankleHeight = -1f;
        [Tooltip("Bind-pose heights above the sole of every joint under each foot (toes, toe ends), local units, in hierarchy order.")]
        public float[] leftFootJointHeights, rightFootJointHeights;
        [Tooltip("Direction each knee points (character forward in the bind pose) and each elbow points (backward), in the " +
                 "local space of the thigh / upper arm: the bend direction for leg and arm IK.")]
        public Vector3 leftKneePole, rightKneePole, leftElbowPole, rightElbowPole;

        Animator anim;
        Transform hips, lUp, lLo, lFoot, lToe, rUp, rLo, rFoot, rToe, lArm, lFore, lHand, rArm, rFore, rHand;
        Transform[] lFingers, rFingers, lFootJoints, rFootJoints;

        void Reset() { Calibrate(); }
        void Awake()
        {
            Init();
            if (seatPoints == null || seatPoints.Length == 0 || ankleHeight < 0 || leftFootJointHeights == null || leftKneePole == Vector3.zero ||
                leftFootJointHeights.Length != lFootJoints.Length || rightFootJointHeights.Length != rFootJoints.Length) Calibrate();
        }

        bool Init()
        {
            anim = GetComponent<Animator>();
            if (anim == null || !anim.isHuman) return false;
            Transform B(HumanBodyBones b) => anim.GetBoneTransform(b);
            hips = B(HumanBodyBones.Hips);
            lUp = B(HumanBodyBones.LeftUpperLeg); lLo = B(HumanBodyBones.LeftLowerLeg); lFoot = B(HumanBodyBones.LeftFoot); lToe = B(HumanBodyBones.LeftToes);
            rUp = B(HumanBodyBones.RightUpperLeg); rLo = B(HumanBodyBones.RightLowerLeg); rFoot = B(HumanBodyBones.RightFoot); rToe = B(HumanBodyBones.RightToes);
            lArm = B(HumanBodyBones.LeftUpperArm); lFore = B(HumanBodyBones.LeftLowerArm); lHand = B(HumanBodyBones.LeftHand);
            rArm = B(HumanBodyBones.RightUpperArm); rFore = B(HumanBodyBones.RightLowerArm); rHand = B(HumanBodyBones.RightHand);
            lFingers = lHand ? lHand.GetComponentsInChildren<Transform>() : new Transform[0];
            lFootJoints = lFoot ? lFoot.GetComponentsInChildren<Transform>().Skip1() : new Transform[0];
            rFootJoints = rFoot ? rFoot.GetComponentsInChildren<Transform>().Skip1() : new Transform[0];
            rFingers = rHand ? rHand.GetComponentsInChildren<Transform>() : new Transform[0];
            return hips && lUp && lLo && lFoot && rUp && rLo && rFoot;
        }

        /// Measures the seat surface and sole heights. Call with the character in its bind pose (as in the prefab, before it
        /// is animated); Reset() does it when the component is added in the editor.
        [ContextMenu("Calibrate From Bind Pose")]
        public void Calibrate()
        {
            if (!Init()) return;
            float s = Mathf.Max(1e-6f, transform.lossyScale.y), floor = transform.position.y;
            ankleHeight = Mathf.Max(0f, (Mathf.Min(lFoot.position.y, rFoot.position.y) - floor) / s);
            float H(Transform t) => Mathf.Max(0f, (t.position.y - floor) / s);
            leftKneePole = lUp.InverseTransformDirection(transform.forward); rightKneePole = rUp.InverseTransformDirection(transform.forward);
            if (lArm) leftElbowPole = lArm.InverseTransformDirection(-transform.forward);
            if (rArm) rightElbowPole = rArm.InverseTransformDirection(-transform.forward);
            leftFootJointHeights = System.Array.ConvertAll(lFootJoints, H);
            rightFootJointHeights = System.Array.ConvertAll(rFootJoints, H);
            // Seat: vertices skinned mainly to the hips or the upper half of a thigh (in a player the mesh needs Read/Write;
            // calibrating in the editor, which happens when the component is added, works with any mesh and is saved). Kept in bone space, so the seat follows the pelvis tilt when sitting.
            var pts = new System.Collections.Generic.List<Vector3>(); var who = new System.Collections.Generic.List<int>();
            var seatT = new[] { hips, lUp, rUp };
            foreach (var smr in GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                var mesh = smr.sharedMesh;
                if (mesh == null || (!mesh.isReadable && !Application.isEditor)) continue; // players need Read/Write; the editor reads any mesh
                var bones = smr.bones; var bind = mesh.bindposes; var w = mesh.boneWeights; var v = mesh.vertices;
                if (w.Length != v.Length) continue;
                for (int k = 0; k < 3; k++)
                {
                    int bi = System.Array.IndexOf(bones, seatT[k]);
                    if (bi < 0) continue;
                    var m = bones[bi].localToWorldMatrix * bind[bi];
                    Vector3 knee = k == 1 ? lLo.position : k == 2 ? rLo.position : Vector3.zero;
                    var cand = new System.Collections.Generic.List<Vector3>();
                    for (int i = 0; i < v.Length; i++)
                    {
                        if (w[i].boneIndex0 != bi || w[i].weight0 < 0.5f) continue;
                        var p = m.MultiplyPoint3x4(v[i]);
                        if (k > 0 && Vector3.Distance(p, seatT[k].position) > Vector3.Distance(p, knee)) continue; // upper half of the thigh
                        cand.Add(p);
                    }
                    int stride = Mathf.Max(1, cand.Count / 160);
                    for (int i = 0; i < cand.Count; i += stride) { pts.Add(seatT[k].InverseTransformPoint(cand[i])); who.Add(k); }
                }
            }
            if (pts.Count == 0) // no readable mesh: one point under the hips, a quarter of a thigh length down
            {
                pts.Add(hips.InverseTransformPoint(hips.position + Vector3.down * 0.25f * Vector3.Distance(lUp.position, lLo.position)));
                who.Add(0);
            }
            seatPoints = pts.ToArray(); seatBones = who.ToArray();
        }

        void LateUpdate() => Solve();

        /// Applies the corrections to the current pose. Called from LateUpdate; call it yourself after evaluating a
        /// PlayableGraph manually.
        public void Solve()
        {
            if (hips == null && !Init()) return;
            float s = transform.lossyScale.y, floor = transform.position.y + floorOffset;
            Vector3 lp = lFoot.position, rp = rFoot.position;
            Quaternion lq = lFoot.rotation, rq = rFoot.rotation;
            bool moved = false;
            if (keepSeatAboveFloor && seatPoints != null && seatBones != null && seatBones.Length == seatPoints.Length)
            {
                float low = float.MaxValue;
                for (int i = 0; i < seatPoints.Length; i++)
                    low = Mathf.Min(low, (seatBones[i] == 0 ? hips : seatBones[i] == 1 ? lUp : rUp).TransformPoint(seatPoints[i]).y);
                float lift = floor - low;
                if (lift > 0) { hips.position += Vector3.up * lift; moved = true; }
            }
            if (keepFeetAboveFloor && ankleHeight >= 0)
            {
                lp.y += SoleLift(lp, lFootJoints, leftFootJointHeights, floor, s);
                rp.y += SoleLift(rp, rFootJoints, rightFootJointHeights, floor, s);
                moved |= lp != lFoot.position || rp != rFoot.position;
            }
            if (moved)
            {
                TwoBone(lUp, lLo, lFoot, lp, lUp.TransformDirection(leftKneePole)); lFoot.rotation = lq;
                TwoBone(rUp, rLo, rFoot, rp, rUp.TransformDirection(rightKneePole)); rFoot.rotation = rq;
            }
            if (keepHandsAboveFloor)
            {
                HandLift(lArm, lFore, lHand, lFingers, floor, leftElbowPole);
                HandLift(rArm, rFore, rHand, rFingers, floor, rightElbowPole);
            }
        }

        /// Lifts a hand whose lowest finger joint is under the floor onto it (arm IK, hand orientation kept).
        static void HandLift(Transform arm, Transform fore, Transform hand, Transform[] fingers, float floor, Vector3 poleLocal)
        {
            if (!arm || !fore || !hand) return;
            float low = hand.position.y;
            foreach (var t in fingers) low = Mathf.Min(low, t.position.y);
            float lift = floor + 0.01f - low; // finger joints sit ~1 cm inside the skin
            if (lift <= 0) return;
            var q = hand.rotation;
            TwoBone(arm, fore, hand, hand.position + Vector3.up * lift, arm.TransformDirection(poleLocal));
            hand.rotation = q;
        }

        float SoleLift(Vector3 ankle, Transform[] joints, float[] heights, float floor, float s)
        {
            float lift = floor + ankleHeight * s - ankle.y;
            if (heights != null && heights.Length == joints.Length)
                for (int i = 0; i < joints.Length; i++) lift = Mathf.Max(lift, floor + heights[i] * s - joints[i].position.y);
            return Mathf.Max(0f, lift);
        }

        /// Two-bone IK: rotates upper and lower so that end reaches target. The joint bends towards its current
        /// direction when the limb is clearly bent that way, else towards `pole` (the anatomical bend direction, carried
        /// by the upper bone), so a nearly straight limb never flips backwards.
        static void TwoBone(Transform upper, Transform lower, Transform end, Vector3 target, Vector3 pole)
        {
            Vector3 a = upper.position, b = lower.position, c = end.position;
            float la = (b - a).magnitude, lb = (c - b).magnitude;
            if (la < 1e-5f || lb < 1e-5f) return;
            Vector3 toT = target - a;
            float d = Mathf.Clamp(toT.magnitude, Mathf.Abs(la - lb) + 1e-4f, la + lb - 1e-4f);
            Vector3 dir = toT.sqrMagnitude > 1e-10f ? toT.normalized : (c - a).normalized;
            Vector3 bend = b - (a + Vector3.Project(b - a, c - a));                 // current joint offset from the line
            // Bend the way the joint is bent now when that agrees with the anatomical pole; else along the pole.
            Vector3 hint = Vector3.Angle(b - a, c - b) > 10f && Vector3.Dot(bend, pole) > 0 ? bend : pole;
            Vector3 perp = Vector3.ProjectOnPlane(hint, dir);
            if (perp.sqrMagnitude < 1e-10f) return;
            perp.Normalize();
            float cosA = Mathf.Clamp((la * la + d * d - lb * lb) / (2 * la * d), -1f, 1f);
            Vector3 knee = a + dir * (la * cosA) + perp * (la * Mathf.Sqrt(1f - cosA * cosA));
            upper.rotation = Quaternion.FromToRotation(b - a, knee - a) * upper.rotation;
            lower.rotation = Quaternion.FromToRotation(end.position - lower.position, a + dir * d - lower.position) * lower.rotation;
        }
    }
}
