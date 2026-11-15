// Camera language computed from the actors' actual poses over the shot: wide, medium, close_up, over_shoulder, follow,
// push_in, orbit, low_angle, top_down, two_shot (+ explicit). The core is a framing solver: for a viewing direction,
// find the camera position that puts a set of body points inside a target rectangle of the frame, for any aspect.
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace ShotStudio
{
    /// Body samples of one actor over the shot (world space), taken every `dt` seconds.
    public class Track
    {
        public string id; public float height = 1.75f;
        public List<Vector3> hips = new List<Vector3>(), head = new List<Vector3>(), chest = new List<Vector3>(),
            lsh = new List<Vector3>(), rsh = new List<Vector3>(), lhand = new List<Vector3>(), rhand = new List<Vector3>(),
            lfoot = new List<Vector3>(), rfoot = new List<Vector3>();
        public float S => height / 1.75f;
        public Vector3 HeadTop(int i) => head[i] + Vector3.up * 0.15f * S;
        public Vector3 Facing(int i)
        {
            var r = rsh[i] - lsh[i]; r.y = 0;
            var f = Vector3.Cross(r, Vector3.up); // Unity is left-handed: right x up = forward
            return f.sqrMagnitude > 1e-6f ? f.normalized : Vector3.forward;
        }
        public Vector3 MeanFacing()
        {
            var f = Vector3.zero; for (int i = 0; i < hips.Count; i++) f += Facing(i);
            return f.sqrMagnitude > 1e-6f ? f.normalized : Vector3.forward;
        }
        public Vector3 Ground(int i) => new Vector3(hips[i].x, 0, hips[i].z);
        public float Travel() { float m = 0; for (int i = 1; i < hips.Count; i++) m = Mathf.Max(m, Vector3.Distance(Ground(0), Ground(i))); return m; }

        /// Points that must be in frame for a framing size: full | knees | waist | chest | face.
        public IEnumerable<Vector3> Region(int i, string size)
        {
            var up = Vector3.up; var w = (rsh[i] - lsh[i]).normalized * 0.12f * S;
            yield return HeadTop(i);
            yield return head[i] + w * 1.4f; yield return head[i] - w * 1.4f;
            if (size == "face") { yield return Vector3.Lerp(head[i], chest[i], 0.7f); yield break; }
            yield return lsh[i] - w; yield return rsh[i] + w;
            if (size == "chest") { yield return Vector3.Lerp(chest[i], hips[i], 0.45f); yield break; }
            // Hands only count from knees-up: in medium and closer framings a gesture may break the frame edge.
            if (size == "waist") { yield return hips[i] - up * 0.12f * S; yield break; }
            yield return lhand[i]; yield return rhand[i];
            if (size == "knees") { yield return Vector3.Lerp(hips[i], (lfoot[i] + rfoot[i]) / 2, 0.55f); yield break; }
            yield return lfoot[i] - up * 0.1f * S; yield return rfoot[i] - up * 0.1f * S;
            yield return lfoot[i] + w; yield return rfoot[i] - w;
        }
    }

    public class CamTrack
    {
        public float dt; public List<Vector3> pos = new List<Vector3>(), look = new List<Vector3>(); public List<float> fov = new List<float>();
        public string preset; public float yaw; public float focus;
        public bool overhead;
        public (Vector3 pos, Quaternion rot, float fov) At(float t)
        {
            float f = Mathf.Clamp(t / dt, 0, pos.Count - 1);
            int a = Mathf.FloorToInt(f), b = Mathf.Min(a + 1, pos.Count - 1); float u = f - a;
            var p = Vector3.Lerp(pos[a], pos[b], u); var l = Vector3.Lerp(look[a], look[b], u);
            var fwd = l - p;
            var rot = Quaternion.LookRotation(fwd.sqrMagnitude > 1e-8f ? fwd : Vector3.forward, Mathf.Abs(Vector3.Dot(fwd.normalized, Vector3.up)) > 0.99f ? Vector3.forward : Vector3.up);
            return (p, rot, Mathf.Lerp(fov[a], fov[b], u));
        }
    }

    public static class CameraRig
    {
        public static readonly string[] Presets = { "wide", "medium", "close_up", "over_shoulder", "follow", "push_in", "orbit", "low_angle", "top_down", "two_shot", "explicit" };

        struct Rect { public float u0, u1, v0, v1; public Rect(float a, float b, float c, float d) { u0 = a; u1 = b; v0 = c; v1 = d; } }

        /// Vertical fov from a lens defined on the frame's short side (so a "50 degree" wide works for 9:16 and 16:9).
        static float VFov(float shortFov, float aspect)
        {
            if (aspect >= 1) return shortFov;
            float h = Mathf.Tan(shortFov * 0.5f * Mathf.Deg2Rad);
            return 2 * Mathf.Atan(h / aspect) * Mathf.Rad2Deg;
        }

        /// Framing solver. Camera looks along (yaw, pitch); returns the camera position putting every point inside rect
        /// (normalised device coords, -1..1) with the subject centred in the rect's free space.
        static Vector3 Solve(List<Vector3> pts, float yaw, float pitch, float vfov, float aspect, Rect r, float distScale, out float dist)
        {
            var rot = Quaternion.Euler(pitch, yaw, 0);
            Vector3 fwd = rot * Vector3.forward, right = rot * Vector3.right, up = rot * Vector3.up;
            var c = Vector3.zero; foreach (var p in pts) c += p; c /= pts.Count;
            float tv = Mathf.Tan(vfov * 0.5f * Mathf.Deg2Rad), th = tv * aspect;
            var P = pts.Select(p => new Vector3(Vector3.Dot(p - c, right), Vector3.Dot(p - c, up), Vector3.Dot(p - c, fwd))).ToList();
            // Feasible lateral offset interval for distance D along one axis.
            (float lo, float hi) Interval(float D, bool horiz)
            {
                float lo = float.MinValue, hi = float.MaxValue;
                float t = horiz ? th : tv, n0 = horiz ? r.u0 : r.v0, n1 = horiz ? r.u1 : r.v1;
                foreach (var q in P)
                {
                    float x = horiz ? q.x : q.y, z = q.z + D;
                    lo = Mathf.Max(lo, x - n1 * t * z);
                    hi = Mathf.Min(hi, x - n0 * t * z);
                }
                return (lo, hi);
            }
            bool Ok(float D)
            {
                foreach (var q in P) if (q.z + D < 0.3f) return false;
                var a = Interval(D, true); var b = Interval(D, false);
                return a.lo <= a.hi && b.lo <= b.hi;
            }
            float dLo = 0.3f, dHi = 1;
            while (!Ok(dHi) && dHi < 500) dHi *= 1.6f;
            for (int k = 0; k < 40; k++) { float m = (dLo + dHi) / 2; if (Ok(m)) dHi = m; else dLo = m; }
            float D = dHi * Mathf.Max(0.3f, distScale);
            if (!Ok(D)) D = dHi;
            var ia = Interval(D, true); var ib = Interval(D, false);
            float aOff = (ia.lo + ia.hi) / 2, bOff = (ib.lo + ib.hi) / 2;
            dist = D;
            return c + right * aOff + up * bOff - fwd * D;
        }

        /// Like Solve, but searches the pitch that puts the camera at `height` metres.
        static Vector3 SolveAtHeight(List<Vector3> pts, float yaw, float height, float vfov, float aspect, Rect r, float distScale, out float pitch, out float dist)
        {
            float best = float.MaxValue; pitch = 0; dist = 1; var bestPos = Vector3.zero;
            for (float p = -40; p <= 75; p += 1f)
            {
                var pos = Solve(pts, yaw, p, vfov, aspect, r, distScale, out var d);
                float e = Mathf.Abs(pos.y - height);
                if (e < best) { best = e; pitch = p; bestPos = pos; dist = d; }
            }
            return bestPos;
        }

        /// Smallest ground distance from other actors to the sight line from the subject toward a camera 6 m out
        /// along `toCamDir` (only actors between subject and camera count).
        static float Clearance(Track S, List<Track> tracks, Vector3 toCamDir)
        {
            float m = 99;
            toCamDir.y = 0; toCamDir.Normalize();
            for (int i = 0; i < S.hips.Count; i += 3)
            {
                var a = S.Ground(i);
                foreach (var o in tracks)
                {
                    if (o == S) continue;
                    var p = o.Ground(Mathf.Min(i, o.hips.Count - 1)) - a;
                    float along = Vector3.Dot(p, toCamDir); // distance toward the camera
                    if (along < 0.2f || along > 6f) continue;
                    m = Mathf.Min(m, (p - toCamDir * along).magnitude);
                }
            }
            return m;
        }

        static float YawOf(Vector3 dir) => Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg;
        static Vector3 Dir(float yaw) => new Vector3(Mathf.Sin(yaw * Mathf.Deg2Rad), 0, Mathf.Cos(yaw * Mathf.Deg2Rad));

        public static CamTrack Build(CamSpec c, List<Track> tracks, float dt, float aspect, float seconds)
        {
            int n = tracks.Count > 0 ? tracks[0].hips.Count : 1;
            var ct = new CamTrack { dt = dt, preset = c.preset };
            string preset = string.IsNullOrEmpty(c.preset) ? "medium" : c.preset;
            if (preset == "explicit" || tracks.Count == 0) return Explicit(c, tracks, ct, n, dt, aspect);
            var S = tracks.FirstOrDefault(t => t.id == c.subject) ?? tracks[0];
            var T = tracks.FirstOrDefault(t => t.id == c.target && t != S) ?? (preset == "over_shoulder" || preset == "two_shot" ? tracks.FirstOrDefault(t => t != S) : null);
            bool vertical = aspect < 1;
            var all = Enumerable.Range(0, n);

            // Viewing direction. Two actors: perpendicular to the line of action, on the side that keeps the first actor
            // (by cast order) screen-left, so cuts between presets respect the 180-degree rule. One actor: 3/4 front.
            Vector3 viewDir;
            Vector3 sideN = Vector3.zero;
            var A = tracks[0]; var B = tracks.Count > 1 ? tracks[1] : null;
            if (B != null && (T != null || preset == "wide" || preset == "top_down"))
            {
                var ab = B.Ground(0) - A.Ground(0); if (ab.sqrMagnitude < 1e-4f) ab = Vector3.right; ab.Normalize();
                // Camera looks along d with right = cross(up, d); A screen-left means ab . right > 0.
                // Default side: the audience side (camera at -Z looking toward +Z), so staging directions (left = -X)
                // read the same on screen; for a line running toward the audience, keep A screen-left instead.
                var d = Vector3.Cross(ab, Vector3.up).normalized;
                if (Mathf.Abs(d.z) > 0.25f) { if (d.z < 0) d = -d; }
                else if (Vector3.Dot(ab, Vector3.Cross(Vector3.up, d)) < 0) d = -d;
                if (c.side == "right" || c.side == "reverse") d = -d;
                sideN = -d; // from the line toward the camera
                viewDir = d;
            }
            else
            {
                var f = S.MeanFacing();
                // 3/4 front; with other actors around, take the side (and angle) whose line of sight is clearest.
                float[] offs = c.side == "right" ? new[] { -28f, -50f, -12f } : c.side == "left" ? new[] { 28f, 50f, 12f } : new[] { 28f, -28f, 50f, -50f, 12f, -12f };
                float best = float.MinValue, off = offs[0];
                foreach (var o in offs)
                {
                    float clear = Clearance(S, tracks, -(Quaternion.Euler(0, 180 + o, 0) * f)); // the camera sits opposite its view direction
                    float score = Mathf.Min(clear, 0.9f) - Mathf.Abs(o) * 0.002f; // past 0.9 m any side is fine: prefer the classic angle
                    if (score > best + 1e-4f) { best = score; off = o; }
                }
                if (preset == "low_angle") off *= 0.7f;
                viewDir = Quaternion.Euler(0, 180 + off, 0) * f;
            }
            float yaw = YawOf(viewDir) + c.yawOffset;
            float dist = 1;

            List<Vector3> Pts(Track t, string size, IEnumerable<int> frames) => frames.SelectMany(i => t.Region(i, size)).ToList();
            List<Vector3> Both(string size, IEnumerable<int> frames) => tracks.Where(t => t == S || t == T).SelectMany(t => Pts(t, size, frames)).ToList();
            bool moving = S.Travel() > 1.0f;
            float fovDef(float shortFov) => c.fov > 0 ? c.fov : VFov(shortFov, aspect);

            // Frames are safe areas: 9:16 keeps the lower ~28% for captions and platform UI.
            Rect full = vertical ? new Rect(-0.86f, 0.86f, -0.42f, 0.86f) : new Rect(-0.82f, 0.82f, -0.86f, 0.86f);
            // Medium and closer: the subject may sit behind the captions from the chest down; the face stays above them.
            Rect tight = vertical ? new Rect(-0.78f, 0.78f, -1.0f, 0.84f) : new Rect(-0.5f, 0.5f, -1.0f, 0.84f);

            void Static(List<Vector3> pts, float pitch, float vf, Rect r, float h = -1)
            {
                Vector3 p; float pt = pitch;
                if (h >= 0) p = SolveAtHeight(pts, yaw, h, vf, aspect, r, c.distance, out pt, out dist);
                else p = Solve(pts, yaw, pitch, vf, aspect, r, c.distance, out dist);
                var look = p + Quaternion.Euler(pt, yaw, 0) * Vector3.forward * dist;
                for (int i = 0; i < n; i++) { ct.pos.Add(p); ct.look.Add(look); ct.fov.Add(vf); }
            }
            void Tracking(string size, float pitch, float vf, Rect r, float h = -1, IEnumerable<Track> who = null)
            {
                who = who ?? new[] { S };
                for (int i = 0; i < n; i++)
                {
                    var pts = who.SelectMany(t => t.Region(i, size)).ToList();
                    Vector3 p; float pt = pitch;
                    if (h >= 0) p = SolveAtHeight(pts, yaw, h, vf, aspect, r, c.distance, out pt, out dist);
                    else p = Solve(pts, yaw, pitch, vf, aspect, r, c.distance, out dist);
                    ct.pos.Add(p); ct.look.Add(p + Quaternion.Euler(pt, yaw, 0) * Vector3.forward * dist); ct.fov.Add(vf);
                }
                Smooth(ct.pos, 0.8f / dt * Mathf.Max(0.2f, c.amount)); Smooth(ct.look, 0.5f / dt * Mathf.Max(0.2f, c.amount));
            }

            switch (preset)
            {
                case "wide":
                {
                    var pts = tracks.SelectMany(t => Pts(t, "full", all)).ToList();
                    var r = vertical ? new Rect(-0.8f, 0.8f, -0.36f, 0.72f) : new Rect(-0.62f, 0.62f, -0.7f, 0.62f);
                    Static(pts, 8, fovDef(vertical ? 58 : 42), r);
                    break;
                }
                case "medium":
                    if (moving) Tracking("waist", 4, fovDef(vertical ? 40 : 30), tight);
                    else Static(Pts(S, "waist", all), 4, fovDef(vertical ? 40 : 30), tight);
                    break;
                case "close_up":
                {
                    var r = vertical ? new Rect(-0.8f, 0.8f, -1.0f, 0.86f) : new Rect(-0.4f, 0.4f, -1.0f, 0.86f);
                    if (moving) Tracking("chest", 2, fovDef(vertical ? 30 : 22), r);
                    else Static(Pts(S, "chest", all), 2, fovDef(vertical ? 30 : 22), r);
                    break;
                }
                case "two_shot":
                {
                    if (T == null) goto case "medium";
                    // 9:16 is narrow: swing the camera ~30 degrees off the perpendicular so the two overlap in depth.
                    if (vertical) yaw += c.side == "right" ? 30 : -30;
                    var r = vertical ? new Rect(-0.88f, 0.88f, -0.36f, 0.86f) : new Rect(-0.7f, 0.7f, -0.9f, 0.84f);
                    if (moving || T.Travel() > 1.0f) Tracking("waist", 5, fovDef(vertical ? 46 : 32), r, -1, new[] { S, T });
                    else Static(Both("waist", all), 5, fovDef(vertical ? 46 : 32), r);
                    break;
                }
                case "low_angle":
                {
                    float h = c.height >= 0 ? c.height : 0.35f * S.S;
                    if (moving) Tracking("full", -12, fovDef(vertical ? 56 : 44), full, h);
                    else Static(Pts(S, "full", all), -12, fovDef(vertical ? 56 : 44), full, h);
                    break;
                }
                case "top_down":
                {
                    var pts = tracks.SelectMany(t => Pts(t, "full", all)).ToList();
                    float vf = fovDef(vertical ? 50 : 40);
                    var r = new Rect(-0.82f, 0.82f, -0.82f, 0.82f);
                    var p = Solve(pts, yaw, 82, vf, aspect, r, c.distance, out dist);
                    var look = p + Quaternion.Euler(82, yaw, 0) * Vector3.forward * dist;
                    for (int i = 0; i < n; i++) { ct.pos.Add(p); ct.look.Add(look); ct.fov.Add(vf); }
                    ct.overhead = true;
                    break;
                }
                case "over_shoulder":
                {
                    if (T == null) goto case "close_up";
                    // Behind the subject's shoulder on the camera side of the line, looking at the target's face.
                    float vf = fovDef(vertical ? 36 : 26);
                    for (int i = 0; i < n; i++)
                    {
                        var st = T.Ground(i) - S.Ground(i); st.y = 0; var d = st.sqrMagnitude > 1e-4f ? st.normalized : S.Facing(i);
                        var nside = sideN.sqrMagnitude > 0 ? sideN : Vector3.Cross(Vector3.up, d);
                        if (c.side == "right" && sideN.sqrMagnitude == 0) nside = -nside;
                        var shoulder = Vector3.Dot(S.lsh[i] - S.rsh[i], nside) > 0 ? S.lsh[i] : S.rsh[i];
                        var p = shoulder - d * (0.85f * S.S * c.distance) + nside * 0.32f * S.S + Vector3.up * 0.12f * S.S;
                        var look = Vector3.Lerp(T.head[i], T.chest[i], 0.45f);
                        ct.pos.Add(p); ct.look.Add(look);
                        // Lens: the target's chest-up fills about 60% of the frame height.
                        float dd = Vector3.Distance(p, look);
                        float need = (T.HeadTop(i).y - T.chest[i].y + 0.35f * T.S) / 0.6f;
                        ct.fov.Add(c.fov > 0 ? c.fov : Mathf.Clamp(2 * Mathf.Atan(need / 2 / dd) * Mathf.Rad2Deg, 14, vf * 1.6f));
                    }
                    Smooth(ct.pos, 0.6f / dt); Smooth(ct.look, 0.4f / dt); Smooth(ct.fov, 0.6f / dt);
                    dist = Vector3.Distance(ct.pos[0], ct.look[0]);
                    break;
                }
                case "follow":
                {
                    // Tracks the subject from 3/4 front of its direction of travel (or of its facing if it barely moves),
                    // with lag; framing full body to knees.
                    var travel = S.Ground(n - 1) - S.Ground(0);
                    var f = travel.magnitude > 0.5f ? travel.normalized : S.MeanFacing();
                    yaw = YawOf(Quaternion.Euler(0, 180 + (c.side == "right" ? -40 : 40), 0) * f) + c.yawOffset;
                    var r = vertical ? new Rect(-0.84f, 0.84f, -0.4f, 0.86f) : new Rect(-0.6f, 0.6f, -0.86f, 0.84f);
                    Tracking("knees", 6, fovDef(vertical ? 46 : 34), r);
                    break;
                }
                case "push_in":
                {
                    float vf = fovDef(vertical ? 38 : 28);
                    var p0 = Solve(Pts(S, "full", all), yaw, 5, vf, aspect, full, c.distance, out var d0);
                    var rEnd = vertical ? new Rect(-0.8f, 0.8f, -1.0f, 0.86f) : new Rect(-0.4f, 0.4f, -1.0f, 0.86f);
                    var p1 = Solve(Pts(S, "chest", all), yaw, 2, vf, aspect, rEnd, c.distance, out var d1);
                    var l0 = p0 + Quaternion.Euler(5, yaw, 0) * Vector3.forward * d0;
                    var l1 = p1 + Quaternion.Euler(2, yaw, 0) * Vector3.forward * d1;
                    float amt = Mathf.Clamp01(c.amount);
                    for (int i = 0; i < n; i++)
                    {
                        float u = n > 1 ? i / (float)(n - 1) : 0; u = u * u * (3 - 2 * u) * amt;
                        ct.pos.Add(Vector3.Lerp(p0, p1, u)); ct.look.Add(Vector3.Lerp(l0, l1, u)); ct.fov.Add(vf);
                    }
                    dist = Mathf.Lerp(d0, d1, amt);
                    break;
                }
                case "orbit":
                {
                    var who = T != null ? Both("full", all) : Pts(S, "knees", all);
                    float vf = fovDef(vertical ? 44 : 34);
                    float total = (c.orbitDeg != 0 ? c.orbitDeg : 50f) * c.amount * (c.side == "right" ? -1 : 1);
                    for (int i = 0; i < n; i++)
                    {
                        float u = n > 1 ? i / (float)(n - 1) : 0;
                        float y = yaw - total / 2 + total * u;
                        var p = Solve(who, y, 6, vf, aspect, full, c.distance, out var d);
                        ct.pos.Add(p); ct.look.Add(p + Quaternion.Euler(6, y, 0) * Vector3.forward * d); ct.fov.Add(vf);
                        dist = d;
                    }
                    Smooth(ct.pos, 0.3f / dt); Smooth(ct.look, 0.3f / dt);
                    break;
                }
                default:
                    throw new System.Exception($"unknown camera preset {preset}; one of {string.Join(", ", Presets)}");
            }
            if (c.height >= 0 && preset != "low_angle" && preset != "over_shoulder")
            {
                // Explicit height on other presets: raise/lower the camera and keep looking at the same point.
                for (int i = 0; i < ct.pos.Count; i++) { var p = ct.pos[i]; p.y = c.height; ct.pos[i] = p; }
            }
            if (c.handheld > 0) Handheld(ct, c.handheld);
            ct.yaw = yaw;
            ct.focus = Vector3.Distance(ct.pos[ct.pos.Count / 2], Vector3.Lerp(S.head[n / 2], S.chest[n / 2], 0.5f));
            return ct;
        }

        static CamTrack Explicit(CamSpec c, List<Track> tracks, CamTrack ct, int n, float dt, float aspect)
        {
            Vector3 V(float[] a, Vector3 d) => a == null || a.Length < 3 ? d : new Vector3(a[0], a[1], a[2]);
            var p0 = V(c.pos, new Vector3(0, 1.6f, -5)); var l0 = V(c.lookAt, new Vector3(0, 1, 0));
            var p1 = V(c.endPos, p0); var l1 = V(c.endLookAt, l0);
            var F = tracks.FirstOrDefault(t => t.id == c.follow);
            float vf = c.fov > 0 ? c.fov : VFov(40, aspect);
            for (int i = 0; i < n; i++)
            {
                float u = n > 1 ? i / (float)(n - 1) : 0; float s = u * u * (3 - 2 * u);
                var look = Vector3.Lerp(l0, l1, s); var pos = Vector3.Lerp(p0, p1, s);
                if (F != null) { var h = F.hips[i]; var delta = new Vector3(h.x, look.y, h.z) - l0; look = l0 + delta; pos += delta; }
                if (c.orbitDeg != 0) pos = look + Quaternion.Euler(0, c.orbitDeg * u, 0) * (pos - look);
                ct.pos.Add(pos); ct.look.Add(look); ct.fov.Add(vf);
            }
            ct.yaw = YawOf(l0 - p0); ct.focus = Vector3.Distance(p0, l0);
            if (c.handheld > 0) Handheld(ct, c.handheld);
            return ct;
        }

        static void Handheld(CamTrack ct, float amount)
        {
            for (int i = 0; i < ct.look.Count; i++)
            {
                float t = i * ct.dt;
                var off = new Vector3(Mathf.Sin(t * 1.3f) + 0.5f * Mathf.Sin(t * 3.1f + 1), 0.7f * Mathf.Sin(t * 1.7f + 2) + 0.3f * Mathf.Sin(t * 4.3f), 0) * 0.025f * amount;
                ct.look[i] += off;
                ct.pos[i] += off * 0.3f;
            }
        }

        static void Smooth<T>(List<T> v, float sigmaSamples)
        {
            if (v.Count < 3 || sigmaSamples < 0.5f) return;
            int r = Mathf.CeilToInt(sigmaSamples * 2.5f);
            var w = Enumerable.Range(-r, 2 * r + 1).Select(k => Mathf.Exp(-k * k / (2 * sigmaSamples * sigmaSamples))).ToArray();
            var src = v.ToList();
            for (int i = 0; i < v.Count; i++)
            {
                double ws = 0; Vector3 acc = Vector3.zero; float accf = 0;
                for (int k = -r; k <= r; k++)
                {
                    int j = Mathf.Clamp(i + k, 0, v.Count - 1);
                    float ww = w[k + r]; ws += ww;
                    if (src[j] is Vector3 p) acc += p * ww; else if (src[j] is float f) accf += f * ww;
                }
                if (typeof(T) == typeof(Vector3)) v[i] = (T)(object)(acc / (float)ws); else v[i] = (T)(object)(accf / (float)ws);
            }
        }
    }
}
