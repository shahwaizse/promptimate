// Humanoid IK goal curves (LeftFootT/Q, RightFootT/Q, LeftHandT/Q, RightHandT/Q), the way Unity's FBX importer
// writes them. Without them, anything that applies Foot IK (Timeline's "Apply Foot IK" and AnimationClipPlayable
// default to on, Animator states with "Foot IK") pulls the feet to the hips.
//
// The goal convention is not documented, so it is not hand-derived: Unity itself is asked. An animation job reads
// the goal computed from the FK pose (AnimationHumanStream.GetGoal*FromPose) and the body transform, and a one-frame
// calibration clip measures the per-goal frame K and sole offset o of the goal curves:
//     world goal rotation W = Body * Q * K        world goal position P = Body.pos + Body * T * s + Body * Q * o
// which inverts exactly (validator: stream goal from curves == goal from pose, to < 1 mm).
using Unity.Collections;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

namespace Promptimate.Editor
{
    internal struct GoalProbeJob : IAnimationJob
    {
        // Layout: bodyPos 0..2, bodyRot 3..6, humanScale 7, then per goal g at 8 + g*14:
        //   goal from curves: pos 0..2, rot 3..6; goal from pose: pos 7..9, rot 10..13
        public NativeArray<float> o;
        public const int Size = 8 + 4 * 14;

        public void ProcessRootMotion(AnimationStream stream) { }

        public void ProcessAnimation(AnimationStream stream)
        {
            var h = stream.AsHuman();
            var a = o;
            int i = 0;
            void P(Vector3 v) { a[i++] = v.x; a[i++] = v.y; a[i++] = v.z; }
            void Q(Quaternion q) { a[i++] = q.x; a[i++] = q.y; a[i++] = q.z; a[i++] = q.w; }
            P(h.bodyPosition); Q(h.bodyRotation); a[i++] = h.humanScale;
            for (int g = 0; g < 4; g++)
            {
                var goal = (AvatarIKGoal)g;
                P(h.GetGoalPosition(goal)); Q(h.GetGoalRotation(goal));
                P(h.GetGoalPositionFromPose(goal)); Q(h.GetGoalRotationFromPose(goal));
            }
        }
    }

    internal static class IKGoals
    {
        // AvatarIKGoal order: LeftFoot, RightFoot, LeftHand, RightHand.
        internal static readonly string[] Names = { "LeftFoot", "RightFoot", "LeftHand", "RightHand" };
        static readonly string[] Axes = { "T.x", "T.y", "T.z", "Q.x", "Q.y", "Q.z", "Q.w" };

        internal static Vector3 V(NativeArray<float> a, int i) => new Vector3(a[i], a[i + 1], a[i + 2]);
        internal static Quaternion R(NativeArray<float> a, int i) => new Quaternion(a[i], a[i + 1], a[i + 2], a[i + 3]);

        /// Evaluates clip on (rig, avatar) at each frame time with an attached GoalProbeJob; IK not applied.
        internal static void Probe(GameObject rig, Avatar avatar, AnimationClip clip, int frames, float fps,
                                   System.Action<int, NativeArray<float>> perFrame)
        {
            var an = rig.GetComponent<Animator>(); if (an == null) an = rig.AddComponent<Animator>();
            an.avatar = avatar; an.applyRootMotion = false; an.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            var graph = PlayableGraph.Create("PromptimateGoalProbe");
            var data = new NativeArray<float>(GoalProbeJob.Size, Allocator.Persistent);
            try
            {
                graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
                var job = AnimationScriptPlayable.Create(graph, new GoalProbeJob { o = data }, 1);
                var cp = AnimationClipPlayable.Create(graph, clip);
                cp.SetApplyFootIK(false);
                job.ConnectInput(0, cp, 0, 1f);
                AnimationPlayableOutput.Create(graph, "out", an).SetSourcePlayable(job);
                graph.Play();
                for (int f = 0; f < frames; f++)
                {
                    cp.SetTime(f / (double)fps);
                    graph.Evaluate(0);
                    perFrame(f, data);
                }
            }
            finally
            {
                data.Dispose();
                graph.Destroy();
            }
        }

        /// Adds IK goal curves for all four goals to a humanoid clip, computed from its own FK pose.
        internal static void AddGoalCurves(AnimationClip clip, GameObject rig, Avatar avatar, int frames, float fps)
        {
            // Calibration: body at identity, every goal T = 0, Q = identity -> K and o per goal.
            var cal = new AnimationClip();
            void C(string p, float v) => cal.SetCurve("", typeof(Animator), p, AnimationCurve.Constant(0, 1, v));
            C("RootT.x", 0); C("RootT.y", 1); C("RootT.z", 0);
            C("RootQ.x", 0); C("RootQ.y", 0); C("RootQ.z", 0); C("RootQ.w", 1);
            foreach (var n in Names) { C(n + "T.x", 0); C(n + "T.y", 0); C(n + "T.z", 0); C(n + "Q.x", 0); C(n + "Q.y", 0); C(n + "Q.z", 0); C(n + "Q.w", 1); }
            var K = new Quaternion[4]; var off = new Vector3[4];
            Probe(rig, avatar, cal, 1, fps, (f, a) =>
            {
                for (int g = 0; g < 4; g++) { int b = 8 + g * 14; K[g] = R(a, b + 3); off[g] = V(a, b) - V(a, 0); }
            });
            Object.DestroyImmediate(cal);

            var curves = new AnimationCurve[4 * 7];
            for (int k = 0; k < curves.Length; k++) curves[k] = new AnimationCurve();
            var prev = new Quaternion[4];
            Probe(rig, avatar, clip, frames, fps, (f, a) =>
            {
                var bp = V(a, 0); var bq = R(a, 3); float s = a[7];
                var inv = Quaternion.Inverse(bq);
                for (int g = 0; g < 4; g++)
                {
                    int b = 8 + g * 14;
                    var q = inv * R(a, b + 10) * Quaternion.Inverse(K[g]);
                    if (f > 0 && Quaternion.Dot(prev[g], q) < 0) q = new Quaternion(-q.x, -q.y, -q.z, -q.w); // sign continuity
                    prev[g] = q;
                    var t = inv * (V(a, b + 7) - bp) / s - q * (off[g] / s);
                    float time = f / fps;
                    float[] vals = { t.x, t.y, t.z, q.x, q.y, q.z, q.w };
                    for (int k = 0; k < 7; k++) curves[g * 7 + k].AddKey(time, vals[k]);
                }
            });
            for (int g = 0; g < 4; g++)
                for (int k = 0; k < 7; k++)
                    clip.SetCurve("", typeof(Animator), Names[g] + Axes[k], curves[g * 7 + k]);
        }
    }
}
