// Ported from unity/DemoStudio/Assets/Editor/ShotStudio/Seating.cs (same algorithm; FurnitureInfo lives in Room.cs).
// Sitting on furniture. The generated motion already sits at about the right height (generate_motion's `seat`
// option constrains the hips height and position during the seated span); at render time the seat contact is made
// exact for this character's proportions: the lowest seat point of the body (buttocks / thigh undersides, sampled from
// the skinned mesh by PromptimateGrounding.Calibrate) is eased onto the measured seat top, and the legs are re-solved
// so the feet stay where they were. Errors before and after the correction are reported, so a motion that doesn't
// actually sit where the chair is still shows up in validation instead of being hidden.
using System.Collections.Generic;
using UnityEngine;

namespace Fidelity
{
    public class SeatState
    {
        public SeatSpec spec; public FurnitureInfo seat;
        public List<float> gapBefore = new List<float>(), gapAfter = new List<float>(), xzErr = new List<float>();
        public List<Vector3> lfoot = new List<Vector3>(), rfoot = new List<Vector3>();
    }


    public static class Seating
    {
        /// Applies the seat contact for shot time t; returns true when the actor is (partly) seated.
        public static bool Apply(SeatState st, Animator anim, Promptimate.PromptimateGrounding g, float t, bool measure)
        {
            var s = st.spec;
            float w;
            if (t < s.start - s.blend || t > s.end + s.blend) return false;
            if (t < s.start) w = Smooth((t - (s.start - s.blend)) / s.blend);
            else if (t > s.end) w = Smooth(1 - (t - s.end) / s.blend);
            else w = 1;
            var hips = anim.GetBoneTransform(HumanBodyBones.Hips);
            var lUp = anim.GetBoneTransform(HumanBodyBones.LeftUpperLeg); var lLo = anim.GetBoneTransform(HumanBodyBones.LeftLowerLeg); var lFoot = anim.GetBoneTransform(HumanBodyBones.LeftFoot);
            var rUp = anim.GetBoneTransform(HumanBodyBones.RightUpperLeg); var rLo = anim.GetBoneTransform(HumanBodyBones.RightLowerLeg); var rFoot = anim.GetBoneTransform(HumanBodyBones.RightFoot);
            float low = Low(g, hips, lUp, rUp);
            float gap = low - st.seat.seatTop;
            var hxz = new Vector2(hips.position.x, hips.position.z);
            // Nearest point on the seat line (benches and sofas seat several people side by side).
            var c3 = st.seat.seatCenter; var right = st.seat.go.transform.right; right.y = 0; right.Normalize();
            float half = Mathf.Max(0, Mathf.Max(st.seat.bounds.extents.x, st.seat.bounds.extents.z) - 0.22f);
            var onLine = c3 + right * Mathf.Clamp(Vector3.Dot(hips.position - c3, right), -half, half);
            var sxz = new Vector2(onLine.x, onLine.z);
            bool fully = t >= s.start && t <= s.end;
            if (measure && fully) { st.gapBefore.Add(gap); st.xzErr.Add(Vector2.Distance(hxz, sxz)); }
            float dy = Mathf.Clamp(-gap, -s.maxCorrection, s.maxCorrection) * w;
            if (Mathf.Abs(dy) > 1e-5f)
            {
                Vector3 lp = lFoot.position, rp = rFoot.position; Quaternion lq = lFoot.rotation, rq = rFoot.rotation;
                hips.position += Vector3.up * dy;
                TwoBone(lUp, lLo, lFoot, lp); lFoot.rotation = lq;
                TwoBone(rUp, rLo, rFoot, rp); rFoot.rotation = rq;
            }
            if (measure && fully)
            {
                st.gapAfter.Add(Low(g, hips, lUp, rUp) - st.seat.seatTop);
                st.lfoot.Add(lFoot.position); st.rfoot.Add(rFoot.position);
            }
            return true;
        }

        static float Low(Promptimate.PromptimateGrounding g, Transform hips, Transform lUp, Transform rUp)
        {
            if (g == null || g.seatPoints == null || g.seatBones == null || g.seatPoints.Length == 0 || g.seatBones.Length != g.seatPoints.Length)
                return hips.position.y - 0.1f * hips.lossyScale.y;
            // Buttock points (on the hips bone) carry the weight; thigh points hang over the seat's front edge when
            // the knees are lower than the hips, so they only count when the rig has no buttock points.
            float low = float.MaxValue, lowAll = float.MaxValue;
            for (int i = 0; i < g.seatPoints.Length; i++)
            {
                float y = (g.seatBones[i] == 0 ? hips : g.seatBones[i] == 1 ? lUp : rUp).TransformPoint(g.seatPoints[i]).y;
                lowAll = Mathf.Min(lowAll, y);
                if (g.seatBones[i] == 0) low = Mathf.Min(low, y);
            }
            return low < float.MaxValue ? low : lowAll;
        }

        static float Smooth(float x) { x = Mathf.Clamp01(x); return x * x * (3 - 2 * x); }

        public static void TwoBoneArm(Transform upper, Transform lower, Transform end, Vector3 target) => TwoBone(upper, lower, end, target);

        /// Two-bone IK that keeps the current bend plane (seated knees are clearly bent).
        static void TwoBone(Transform upper, Transform lower, Transform end, Vector3 target)
        {
            Vector3 a = upper.position, b = lower.position, c = end.position;
            float la = (b - a).magnitude, lb = (c - b).magnitude;
            if (la < 1e-5f || lb < 1e-5f) return;
            var toT = target - a;
            float d = Mathf.Clamp(toT.magnitude, Mathf.Abs(la - lb) + 1e-4f, la + lb - 1e-4f);
            var dir = toT.normalized;
            var bend = b - (a + Vector3.Project(b - a, c - a));
            var perp = Vector3.ProjectOnPlane(bend.sqrMagnitude > 1e-8f ? bend : upper.forward, dir);
            if (perp.sqrMagnitude < 1e-10f) return;
            perp.Normalize();
            float cosA = Mathf.Clamp((la * la + d * d - lb * lb) / (2 * la * d), -1f, 1f);
            var knee = a + dir * (la * cosA) + perp * (la * Mathf.Sqrt(1f - cosA * cosA));
            upper.rotation = Quaternion.FromToRotation(b - a, knee - a) * upper.rotation;
            lower.rotation = Quaternion.FromToRotation(end.position - lower.position, a + dir * d - lower.position) * lower.rotation;
        }

        public static string Report(SeatState st)
        {
            string F(float v) => v.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture);
            float Med(List<float> l) { if (l.Count == 0) return 0; var c = new List<float>(l); c.Sort(); return c[c.Count / 2]; }
            float MaxAbs(List<float> l) { float m = 0; foreach (var v in l) m = Mathf.Max(m, Mathf.Abs(v)); return m; }
            float Drift(List<Vector3> l) { float m = 0; foreach (var v in l) m = Mathf.Max(m, Vector2.Distance(new Vector2(v.x, v.z), new Vector2(l[0].x, l[0].z))); return l.Count > 0 ? m : 0; }
            float FootY(List<Vector3> l) { if (l.Count == 0) return 0; float m = float.MaxValue; foreach (var v in l) m = Mathf.Min(m, v.y); return m; }
            return $"{{\"furniture\":\"{st.spec.furniture}\",\"seatTopM\":{F(st.seat.seatTop)},\"samples\":{st.gapBefore.Count}," +
                   $"\"gapBeforeMedianCm\":{F(Med(st.gapBefore) * 100)},\"gapBeforeMaxAbsCm\":{F(MaxAbs(st.gapBefore) * 100)}," +
                   $"\"gapAfterMedianCm\":{F(Med(st.gapAfter) * 100)},\"gapAfterMaxAbsCm\":{F(MaxAbs(st.gapAfter) * 100)}," +
                   $"\"hipsToSeatXZMedianCm\":{F(Med(st.xzErr) * 100)},\"hipsToSeatXZMaxCm\":{F(MaxAbs(st.xzErr) * 100)}," +
                   $"\"leftFootDriftCm\":{F(Drift(st.lfoot) * 100)},\"rightFootDriftCm\":{F(Drift(st.rfoot) * 100)}," +
                   $"\"footMinYCm\":{F(Mathf.Min(FootY(st.lfoot), FootY(st.rfoot)) * 100)}}}";
        }
    }
}
