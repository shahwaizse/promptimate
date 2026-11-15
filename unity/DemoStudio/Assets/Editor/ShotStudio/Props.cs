// Props held in a hand (phone, cup, bag, sword, book, flashlight, umbrella, stick) and the matching finger pose.
//
// Grip frame (rig independent): at spawn, while the character is still in its bind pose (T- or A-pose: palms down,
// thumbs forward), the direction along the fingers (hand -> middle finger, else forearm -> hand) and the thumb side
// (the character's forward) are stored in the hand bone's local space. Every frame they give
//   F = along the fingers, A = toward the thumb, N = out of the palm,
// whatever the rig's bone axes are. Grip styles place the prop's main axis (+Y after modelRot) and front (+Z):
//   power: Y -> A (a handle across the fist: cup, sword, flashlight, umbrella), surface against the palm
//   flat:  Y -> F, Z -> N (phone, book lying against the palm)
//   hang:  Y -> world up, hanging from the fingers (bag, briefcase)
//   cane:  Y -> -A (a stick whose shaft leaves the fist on the little-finger side)
//   pinch: like flat but held at the fingertips
// Fingers: the finger bones are posed with the importer's hand-pose muscle tables (grip, point, ...) while the prop is
// held, blended in and out over 0.2 s, on rigs that have finger bones.
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace ShotStudio
{
    public class HeldProp
    {
        public PropSpec spec; public GameObject root; public Transform hand; public bool left;
        public Vector3 localF, localA; public float hs; public Transform head; public float twistDeg; public Vector3 extent; // prop size after scaling (m)
        public Renderer[] renderers; public Light torch; public Vector3[] samplePts; // prop-local sample points
        // measurements
        public float maxPen, sumPen; public int penSamples, penOver; public string penWhere = "";
        public List<Vector3> pivotInHand = new List<Vector3>();
        public bool visible;
        public Animator anim; public float actorHeight; public float handScale = 1; public Vector3 gripPos; public float push, maxPush, maxSwing;
    }

    public static class Props
    {
        // ---- hand frame --------------------------------------------------------------------------------------------

        public static (Vector3 F, Vector3 A, Vector3 N, Vector3 palm) Frame(HeldProp p, float along)
        {
            var q = p.hand.rotation;
            var F = (q * p.localF).normalized;
            var A = Vector3.ProjectOnPlane(q * p.localA, F).normalized;
            var N = p.left ? -Vector3.Cross(F, A) : Vector3.Cross(F, A);
            var palm = p.hand.position + F * (along * p.hs) + N * (0.012f * p.hs);
            return (F, A, N, palm);
        }

        /// Hand-frame axes in the hand bone's local space, measured in the bind pose (call before any animation).
        static void Calibrate(HeldProp p, PropSpec s, Animator anim, GameObject actor)
        {
            var hb = p.left ? HumanBodyBones.LeftHand : HumanBodyBones.RightHand;
            p.hand = anim.GetBoneTransform(hb);
            var mid = anim.GetBoneTransform(p.left ? HumanBodyBones.LeftMiddleProximal : HumanBodyBones.RightMiddleProximal);
            var fore = anim.GetBoneTransform(p.left ? HumanBodyBones.LeftLowerArm : HumanBodyBones.RightLowerArm);
            Vector3 f = mid ? mid.position - p.hand.position : p.hand.position - fore.position;
            if (f.sqrMagnitude < 1e-8f) f = p.left ? -actor.transform.right : actor.transform.right;
            f.Normalize();
            // Thumb side: from the thumb bone when the rig has one, else the body's forward (thumbs point forward in a
            // T/A bind pose). Forward from the shoulders, not the root transform: glTF roots don't always face +Z.
            var thumb = anim.GetBoneTransform(p.left ? HumanBodyBones.LeftThumbProximal : HumanBodyBones.RightThumbProximal);
            var ls = anim.GetBoneTransform(HumanBodyBones.LeftUpperArm); var rs = anim.GetBoneTransform(HumanBodyBones.RightUpperArm);
            var fwd = ls && rs ? Vector3.Cross(rs.position - ls.position, Vector3.up) : actor.transform.forward;
            var a = thumb ? Vector3.ProjectOnPlane(thumb.position - p.hand.position, f) : Vector3.zero;
            if (a.sqrMagnitude < 1e-8f || Vector3.Dot(a.normalized, fwd.normalized) < 0.2f) a = Vector3.ProjectOnPlane(fwd, f);
            a.Normalize();
            p.localF = Quaternion.Inverse(p.hand.rotation) * f;
            p.localA = Quaternion.Inverse(p.hand.rotation) * a;
        }

        // ---- spawn -------------------------------------------------------------------------------------------------

        public static HeldProp Attach(PropSpec s, GameObject actor, Animator anim, float actorHeight)
        {
            var p = new HeldProp { spec = s, left = (s.hand ?? "right").ToLower().StartsWith("l"), hs = actorHeight / 1.75f };
            Calibrate(p, s, anim, actor);
            p.head = anim.GetBoneTransform(HumanBodyBones.Head);
            p.anim = anim; p.actorHeight = actorHeight;
            GameObject model;
            if (s.model.StartsWith("procedural:"))
            {
                p.root = new GameObject("Prop_" + (string.IsNullOrEmpty(s.id) ? s.model.Substring(11) : s.id));
                model = Procedural(s.model.Substring(11));
                model.transform.SetParent(p.root.transform, false);
            }
            else
            {
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(s.model);
                if (prefab == null) throw new System.Exception("missing prop model " + s.model + " (run unity/DemoStudio/fetch_render_assets.py)");
                p.root = new GameObject("Prop_" + (string.IsNullOrEmpty(s.id) ? prefab.name : s.id));
                model = (GameObject)Object.Instantiate(prefab, p.root.transform);
            }
            foreach (var legacy in model.GetComponentsInChildren<Animation>(true)) Object.DestroyImmediate(legacy);
            foreach (var an in model.GetComponentsInChildren<Animator>(true)) Object.DestroyImmediate(an);
            model.transform.localPosition = Vector3.zero;
            model.transform.localRotation = Quaternion.Euler(V(s.modelRot));
            model.transform.localScale = Vector3.one;
            Materials.ConvertAll(model, null);
            if (s.tint != null && s.tint.Length >= 3)
                foreach (var r in model.GetComponentsInChildren<Renderer>())
                {
                    var mats = r.sharedMaterials.Select(m => { var c = new Material(m); c.SetColor("_BaseColor", c.GetColor("_BaseColor") * new Color(s.tint[0], s.tint[1], s.tint[2])); return c; }).ToArray();
                    r.sharedMaterials = mats;
                }
            p.renderers = model.GetComponentsInChildren<Renderer>();
            foreach (var r in p.renderers) { r.shadowCastingMode = ShadowCastingMode.On; r.receiveShadows = true; }
            // Normalise: longest side = size (scaled with the actor), grip point at the root's origin.
            var b = LocalBounds(p.root.transform, p.renderers);
            float longest = Mathf.Max(b.size.x, b.size.y, b.size.z);
            float k = longest > 1e-5f ? s.size * p.hs * HandScale(p, anim) / longest : 1;
            model.transform.localScale = Vector3.one * k;
            b = LocalBounds(p.root.transform, p.renderers);
            var grip = new Vector3(b.center.x, Mathf.Lerp(b.min.y, b.max.y, Mathf.Clamp01(s.gripAt)), b.center.z);
            model.transform.localPosition -= grip;
            p.extent = b.size;
            // Sample points for the penetration test (bounds corners, edge midpoints and mesh vertices).
            var pts = new List<Vector3>();
            foreach (var r in p.renderers)
            {
                var v = Verts(r); int step = Mathf.Max(1, v.Length / 160);
                for (int i = 0; i < v.Length; i += step) pts.Add(p.root.transform.InverseTransformPoint(r.transform.TransformPoint(v[i])));
            }
            p.samplePts = pts.ToArray();
            if (s.light == "torch")
            {
                var lg = new GameObject("Torch").AddComponent<Light>();
                lg.type = LightType.Spot; lg.color = new Color(1f, 0.93f, 0.8f); lg.intensity = 14; lg.range = 14; lg.spotAngle = 38; lg.innerSpotAngle = 14;
                lg.shadows = LightShadows.Soft; lg.shadowStrength = 0.8f;
                lg.transform.SetParent(p.root.transform, false);
                lg.transform.localPosition = new Vector3(0, b.max.y - grip.y + 0.01f, 0);
                lg.transform.localRotation = Quaternion.LookRotation(Vector3.up, Vector3.forward);
                p.torch = lg;
                var lens = GameObject.CreatePrimitive(PrimitiveType.Sphere); Object.DestroyImmediate(lens.GetComponent<Collider>());
                lens.name = "TorchLens"; lens.transform.SetParent(p.root.transform, false);
                lens.transform.localPosition = lg.transform.localPosition - Vector3.up * 0.008f; lens.transform.localScale = Vector3.one * Mathf.Min(b.size.x, b.size.z) * 0.8f;
                var lr = lens.GetComponent<Renderer>(); lr.sharedMaterial = Materials.Emissive(new Color(1f, 0.95f, 0.85f), 8f); lr.shadowCastingMode = ShadowCastingMode.Off;
            }
            if (s.light == "screen")
            {
                // A lit phone screen: emissive face on the front (+Z) plus a faint cool light on the holder's face.
                var scr = GameObject.CreatePrimitive(PrimitiveType.Cube); Object.DestroyImmediate(scr.GetComponent<Collider>());
                scr.name = "Screen"; scr.transform.SetParent(p.root.transform, false);
                float cy = (b.min.y + b.max.y) / 2 - grip.y;
                scr.transform.localPosition = new Vector3(b.center.x - grip.x, cy, b.max.z - grip.z + 0.0012f);
                scr.transform.localScale = new Vector3(b.size.x * 0.84f, b.size.y * 0.88f, 0.001f);
                var sr = scr.GetComponent<Renderer>(); sr.sharedMaterial = Materials.Emissive(new Color(0.62f, 0.78f, 1f), 2.2f); sr.shadowCastingMode = ShadowCastingMode.Off;
                var gl = new GameObject("ScreenLight").AddComponent<Light>();
                gl.type = LightType.Point; gl.color = new Color(0.6f, 0.75f, 1f); gl.intensity = 0.5f; gl.range = 0.7f; gl.shadows = LightShadows.None;
                gl.transform.SetParent(p.root.transform, false); gl.transform.localPosition = scr.transform.localPosition + Vector3.forward * 0.06f;
                p.torch = gl;
                p.renderers = p.renderers.Append(sr).ToArray();
            }
            SetVisible(p, false);
            return p;
        }

        /// Vertices of a renderer in its own space (bounds corners when the mesh isn't CPU-readable).
        static Vector3[] Verts(Renderer r)
        {
            Mesh m = r is SkinnedMeshRenderer smr ? smr.sharedMesh : r.GetComponent<MeshFilter>()?.sharedMesh;
            if (m != null && m.isReadable && m.vertexCount > 0) return m.vertices;
            var b = m != null ? m.bounds : r.localBounds;
            var o = new Vector3[8];
            for (int i = 0; i < 8; i++) o[i] = new Vector3((i & 1) == 0 ? b.min.x : b.max.x, (i & 2) == 0 ? b.min.y : b.max.y, (i & 4) == 0 ? b.min.z : b.max.z);
            return o;
        }

        /// Stylised rigs have oversized hands (Quaternius ~1.5x): a real-size phone vanishes in the fist. Props scale
        /// with the hand: wrist to middle-finger tip over a human hand's ~0.15 m (per 1.75 m), clamped to 1..1.6.
        public static float HandScale(HeldProp p, Animator anim)
        {
            var tip = anim.GetBoneTransform(p.left ? HumanBodyBones.LeftMiddleDistal : HumanBodyBones.RightMiddleDistal);
            if (!tip) return 1;
            float len = Vector3.Distance(p.hand.position, tip.position) + 0.02f * p.hs; // distal bone origin -> tip
            p.handScale = Mathf.Clamp(len / (0.15f * p.hs), 1f, 1.6f);
            return p.handScale;
        }

        static Bounds LocalBounds(Transform root, Renderer[] rs)
        {
            bool any = false; var b = new Bounds();
            foreach (var r in rs)
                foreach (var v in Verts(r))
                {
                    var l = root.InverseTransformPoint(r.transform.TransformPoint(v));
                    if (!any) { b = new Bounds(l, Vector3.zero); any = true; } else b.Encapsulate(l);
                }
            return b;
        }

        static void SetVisible(HeldProp p, bool on)
        {
            p.visible = on;
            foreach (var r in p.renderers) r.enabled = on;
            if (p.torch) p.torch.enabled = on;
            foreach (Transform c in p.root.transform) if (c.name == "TorchLens") c.gameObject.SetActive(on);
        }

        // ---- per frame -------------------------------------------------------------------------------------------------

        public static void Place(HeldProp p, float t)
        {
            bool on = t >= p.spec.start - 1e-4f && t <= p.spec.end + 1e-4f;
            if (on != p.visible) SetVisible(p, on);
            if (!on) return;
            var s = p.spec;
            string g = (s.grip ?? "power").ToLower();
            // Flat props (phone, book) are looked at or held to the ear: turn the hand about the finger axis so the
            // palm faces the head. Kimodo's wrist roll is loose, and a palm-down "looks at the phone" hand would hide
            // the prop under the fist. Eased in/out with the prop, at most 150 degrees.
            if ((g == "flat" || g == "pinch") && p.head)
            {
                var (F0, _, N0, palm0) = Frame(p, 0.065f);
                // At the ear (a call) the palm faces the head; lower down (looking at the screen) it faces mostly up.
                var dh = p.head.position - palm0;
                float ear = Mathf.Clamp01((0.38f * p.hs - dh.magnitude) / (0.16f * p.hs));
                var look = Vector3.up + 0.4f * dh.normalized;
                var toHead = Vector3.ProjectOnPlane(Vector3.Lerp(look.normalized, dh.normalized, ear), F0);
                if (toHead.sqrMagnitude > 1e-6f)
                {
                    float ang = Mathf.Clamp(Vector3.SignedAngle(N0, toHead, F0), -150, 150);
                    float w = Mathf.Clamp01(Mathf.Min(t - s.start, s.end - t) / 0.2f);
                    p.twistDeg = ang * w;
                    p.hand.rotation = Quaternion.AngleAxis(p.twistDeg, F0) * p.hand.rotation;
                }
            }
            float along = g == "flat" ? 0.065f : g == "pinch" ? 0.11f : g == "hang" ? 0.075f : 0.075f;
            var (F, A, N, palm) = Frame(p, along);
            Vector3 up, fwd, pos = palm;
            float radiusN = 0;
            switch (g)
            {
                case "flat": case "pinch": up = F; fwd = N; radiusN = p.extent.z * 0.5f + 0.018f * p.hs; break; // on the palm skin, not in the hand mesh
                case "hang":
                    up = Vector3.up; fwd = Vector3.ProjectOnPlane(N, Vector3.up);
                    if (fwd.sqrMagnitude < 1e-4f) fwd = Vector3.ProjectOnPlane(A, Vector3.up);
                    break;
                case "cup":
                {
                    // Drinks stay upright (nobody carries a coffee sideways) and tilt with the hand only at the mouth.
                    float mouth = p.head ? Mathf.Clamp01((0.3f * p.hs - Vector3.Distance(palm, p.head.position)) / (0.12f * p.hs)) : 0;
                    up = Vector3.Slerp(Vector3.up, A, mouth * 0.85f).normalized;
                    fwd = Vector3.ProjectOnPlane(N, up); radiusN = Mathf.Min(p.extent.x, p.extent.z) * 0.5f; break;
                }
                case "cane":
                {
                    // A walking stick hangs to the ground from the fist, tip a little ahead (towards the thumb).
                    var ah = Vector3.ProjectOnPlane(A, Vector3.up);
                    up = (Vector3.up - 0.3f * (ah.sqrMagnitude > 1e-6f ? ah.normalized : Vector3.zero)).normalized;
                    fwd = N; radiusN = Mathf.Min(p.extent.x, p.extent.z) * 0.5f; break;
                }
                default: up = A; fwd = N; radiusN = Mathf.Min(p.extent.x, p.extent.z) * 0.5f; break; // power
            }
            fwd = Vector3.ProjectOnPlane(fwd, up);
            if (fwd.sqrMagnitude < 1e-6f) fwd = Vector3.ProjectOnPlane(F, up);
            var rot = Quaternion.LookRotation(fwd.normalized, up.normalized);
            pos += N * radiusN;
            var off = V(s.offset) * p.hs;
            pos += A * off.x + N * off.y + F * off.z;
            var extra = Quaternion.Euler(V(s.rot));
            // extra rotation is expressed in the grip frame (A, N, F)
            var frame = Quaternion.LookRotation(F, N);
            rot = frame * extra * Quaternion.Inverse(frame) * rot;
            p.root.transform.SetPositionAndRotation(pos, rot);
            p.gripPos = pos;
            // Keep it out of the holder's body: push along the way out of the deepest capsule (a bag swings out, a cup
            // is held a little off the thigh). Capped, so a prop that really goes through still shows in validation.
            // First swing it about the grip (a cup tilted off the hip, a bag swinging out), then slide what's left.
            float cap = (g == "hang" ? 0.15f : 0.06f) * p.hs, swingCap = g == "hang" ? 50f : 40f, swung = 0;
            p.push = 0;
            for (int it = 0; it < 6; it++)
            {
                var (depth, dir, point) = Deepest(p);
                if (depth < 0.004f) break;
                var arm = point - pos;
                var axis = Vector3.Cross(arm, dir);
                if (swung < swingCap && arm.magnitude > 0.03f && axis.sqrMagnitude > 1e-8f)
                {
                    float ang = Mathf.Min((depth + 0.004f) / arm.magnitude * Mathf.Rad2Deg, swingCap - swung);
                    p.root.transform.RotateAround(pos, axis.normalized, ang);
                    swung += ang;
                    continue;
                }
                if (p.push >= cap) break;
                float step = Mathf.Min(depth + 0.004f, cap - p.push);
                p.root.transform.position += dir * step;
                p.push += step;
            }
            p.maxPush = Mathf.Max(p.maxPush, p.push);
            p.maxSwing = Mathf.Max(p.maxSwing, swung);
        }

        static (string name, Vector3 a, Vector3 b, float r)[] Shapes(HeldProp p)
        {
            var anim = p.anim; float hs = p.hs;
            Vector3 B(HumanBodyBones b) { var x = anim.GetBoneTransform(b); return x ? x.position : Vector3.zero; }
            var head = B(HumanBodyBones.Head) + Vector3.up * 0.07f * hs;
            var hips = B(HumanBodyBones.Hips);
            var neck = anim.GetBoneTransform(HumanBodyBones.Neck) ? B(HumanBodyBones.Neck) : B(HumanBodyBones.Head);
            return new (string, Vector3, Vector3, float)[]
            {
                ("head", head, head, 0.095f * hs),
                ("torso", Vector3.Lerp(hips, neck, 0.3f), Vector3.Lerp(hips, neck, 0.85f), 0.115f * hs), // hips region: the thighs cover it
                ("left thigh", B(HumanBodyBones.LeftUpperLeg), B(HumanBodyBones.LeftLowerLeg), 0.065f * hs),
                ("right thigh", B(HumanBodyBones.RightUpperLeg), B(HumanBodyBones.RightLowerLeg), 0.065f * hs),
            };
        }

        static (float depth, Vector3 dir, Vector3 point) Deepest(HeldProp p)
        {
            var shapes = Shapes(p);
            var M = p.root.transform.localToWorldMatrix;
            float worst = 0; Vector3 dir = Vector3.zero, at = Vector3.zero;
            foreach (var lp in p.samplePts)
            {
                var w = M.MultiplyPoint3x4(lp);
                foreach (var sh in shapes)
                {
                    var ab = sh.b - sh.a; float t = ab.sqrMagnitude > 1e-8f ? Mathf.Clamp01(Vector3.Dot(w - sh.a, ab) / ab.sqrMagnitude) : 0;
                    var c = sh.a + ab * t; var d = w - c; float pen = sh.r - d.magnitude - HandDepth(p, sh);
                    if (pen > worst) { worst = pen; at = w; dir = d.sqrMagnitude > 1e-10f ? d.normalized : Vector3.up; }
                }
            }
            return (worst, dir, at);
        }

        /// Prop sample points against the holder's body (head sphere, torso capsule, thighs; the holding arm and hand
        /// are excluded), and the prop pivot in the hand's local space (constant when the prop follows the hand).
        public static void Measure(HeldProp p, Animator anim, float actorHeight)
        {
            if (!p.visible) return;
            var shapes = Shapes(p);
            float worst = 0; string where = "";
            var M = p.root.transform.localToWorldMatrix;
            foreach (var lp in p.samplePts)
            {
                var w = M.MultiplyPoint3x4(lp);
                foreach (var sh in shapes)
                {
                    float pen = sh.r - DistSeg(w, sh.a, sh.b) - HandDepth(p, sh);
                    if (pen > worst) { worst = pen; where = sh.name; }
                }
            }
            if (worst > p.maxPen) p.penWhere = where;
            p.maxPen = Mathf.Max(p.maxPen, worst);
            p.sumPen += worst; p.penSamples++;
            if (worst > 0.03f) p.penOver++;
            p.pivotInHand.Add(p.hand.InverseTransformPoint(p.gripPos) * p.hand.lossyScale.x);
        }

        /// How deep the gripping hand itself is inside a body shape (a hand resting on the belly): the prop is only
        /// blamed for going deeper than that.
        static float HandDepth(HeldProp p, (string name, Vector3 a, Vector3 b, float r) sh)
            => Mathf.Max(0, sh.r - DistSeg(p.gripPos, sh.a, sh.b));

        static float DistSeg(Vector3 p, Vector3 a, Vector3 b)
        {
            var ab = b - a; float t = ab.sqrMagnitude > 1e-8f ? Mathf.Clamp01(Vector3.Dot(p - a, ab) / ab.sqrMagnitude) : 0;
            return Vector3.Distance(p, a + ab * t);
        }

        public static string Report(HeldProp p)
        {
            float drift = 0;
            if (p.pivotInHand.Count > 0)
            {
                var mean = Vector3.zero; foreach (var v in p.pivotInHand) mean += v; mean /= p.pivotInHand.Count;
                foreach (var v in p.pivotInHand) drift = Mathf.Max(drift, Vector3.Distance(v, mean));
            }
            string F(float v) => v.ToString("0.####", System.Globalization.CultureInfo.InvariantCulture);
            return $"{{\"id\":\"{p.spec.id}\",\"hand\":\"{(p.left ? "left" : "right")}\",\"grip\":\"{p.spec.grip}\",\"samples\":{p.penSamples}," +
                   $"\"maxPenetrationCm\":{F(p.maxPen * 100)},\"meanPenetrationCm\":{F(p.penSamples > 0 ? p.sumPen / p.penSamples * 100 : 0)}," +
                   $"\"overThreeCmShare\":{F(p.penSamples > 0 ? p.penOver / (float)p.penSamples : 0)},\"worstPart\":\"{p.penWhere}\"," +
                   $"\"handDriftCm\":{F(drift * 100)},\"maxPushCm\":{F(p.maxPush * 100)},\"maxSwingDeg\":{F(p.maxSwing)},\"handScale\":{F(p.handScale)},\"sizeM\":[{F(p.extent.x)},{F(p.extent.y)},{F(p.extent.z)}]}}";
        }

        // ---- procedural props (no CC0 model found that fits) ---------------------------------------------------------
        // Built along +Y (handle at the bottom), front +Z, in metres; Attach rescales to the catalogue size.

        static GameObject Procedural(string kind)
        {
            var root = new GameObject(kind);
            Material M(Color c, float sm = 0.35f, float met = 0) => Materials.Make(c, null, sm, met);
            GameObject Cyl(string n, Vector3 a, Vector3 b, float r, Material m)
            {
                var g = GameObject.CreatePrimitive(PrimitiveType.Cylinder); Object.DestroyImmediate(g.GetComponent<Collider>());
                g.name = n; g.transform.SetParent(root.transform, false);
                g.transform.localPosition = (a + b) / 2; g.transform.localRotation = Quaternion.FromToRotation(Vector3.up, b - a);
                g.transform.localScale = new Vector3(r * 2, (b - a).magnitude / 2, r * 2);
                g.GetComponent<Renderer>().sharedMaterial = m; return g;
            }
            switch (kind)
            {
                case "umbrella":
                {
                    var shaft = M(new Color(0.15f, 0.15f, 0.16f), 0.5f, 0.6f);
                    Cyl("Handle", new Vector3(0, 0, 0), new Vector3(0, 0.12f, 0), 0.016f, M(new Color(0.25f, 0.14f, 0.08f), 0.45f));
                    Cyl("Shaft", new Vector3(0, 0.1f, 0), new Vector3(0, 0.86f, 0), 0.007f, shaft);
                    // Canopy: 8 panels, slightly domed, double-sided.
                    var cm = M(new Color(0.07f, 0.09f, 0.16f), 0.55f);
                    var mesh = new Mesh { name = "Canopy" };
                    var v = new List<Vector3> { new Vector3(0, 0.9f, 0) }; var tri = new List<int>();
                    const int N = 8; float R = 0.52f;
                    for (int i = 0; i < N; i++)
                    {
                        float ang = i / (float)N * Mathf.PI * 2;
                        v.Add(new Vector3(Mathf.Cos(ang) * R * 0.62f, 0.83f, Mathf.Sin(ang) * R * 0.62f));
                        v.Add(new Vector3(Mathf.Cos(ang) * R, 0.66f, Mathf.Sin(ang) * R));
                    }
                    for (int i = 0; i < N; i++)
                    {
                        int a0 = 1 + 2 * i, a1 = 1 + 2 * ((i + 1) % N);
                        tri.AddRange(new[] { 0, a1, a0, 0, a0, a1 });
                        tri.AddRange(new[] { a0, a1, a0 + 1, a0 + 1, a1, a1 + 1, a0, a0 + 1, a1, a0 + 1, a1 + 1, a1 });
                    }
                    mesh.SetVertices(v); mesh.SetTriangles(tri, 0); mesh.RecalculateNormals(); mesh.RecalculateBounds();
                    var cg = new GameObject("Canopy"); cg.transform.SetParent(root.transform, false);
                    cg.AddComponent<MeshFilter>().sharedMesh = mesh; cg.AddComponent<MeshRenderer>().sharedMaterial = cm;
                    Cyl("Tip", new Vector3(0, 0.89f, 0), new Vector3(0, 0.95f, 0), 0.006f, shaft);
                    break;
                }
                case "cane":
                {
                    var wood = M(new Color(0.32f, 0.19f, 0.1f), 0.45f);
                    Cyl("Shaft", new Vector3(0, 0, 0), new Vector3(0, 0.86f, 0), 0.011f, wood);
                    // Crook: a short arc over the top.
                    var prev = new Vector3(0, 0.86f, 0);
                    for (int i = 1; i <= 6; i++)
                    {
                        float ang = i / 6f * Mathf.PI;
                        var pt = new Vector3(0, 0.86f + Mathf.Sin(ang) * 0.055f, 0.055f - Mathf.Cos(ang) * 0.055f);
                        Cyl("Crook", prev, pt, 0.011f, wood); prev = pt;
                    }
                    Cyl("Ferrule", new Vector3(0, -0.01f, 0), new Vector3(0, 0.03f, 0), 0.012f, M(new Color(0.1f, 0.1f, 0.1f), 0.3f));
                    break;
                }
                case "flashlight":
                {
                    var body = M(new Color(0.08f, 0.08f, 0.09f), 0.55f, 0.7f);
                    Cyl("Body", new Vector3(0, 0, 0), new Vector3(0, 0.15f, 0), 0.016f, body);
                    Cyl("Head", new Vector3(0, 0.15f, 0), new Vector3(0, 0.2f, 0), 0.024f, body);
                    Cyl("Ring", new Vector3(0, 0.198f, 0), new Vector3(0, 0.202f, 0), 0.025f, M(new Color(0.7f, 0.7f, 0.72f), 0.7f, 0.9f));
                    break;
                }
                default: throw new System.Exception("unknown procedural prop " + kind + " (umbrella, cane, flashlight)");
            }
            return root;
        }

        static Vector3 V(float[] a) => a == null || a.Length < 3 ? Vector3.zero : new Vector3(a[0], a[1], a[2]);

        // ---- fingers ---------------------------------------------------------------------------------------------------

        // Same muscle tables as the Promptimate importer (KimodoImporter.cs), per finger: 1 Stretched, Spread,
        // 2 Stretched, 3 Stretched. Thumb, Index, Middle, Ring, Little.
        static readonly Dictionary<string, float[,]> Poses = new Dictionary<string, float[,]>
        {
            ["grip"] = new float[,] { { -1.00f, -0.60f, -0.10f, -0.20f }, { -0.35f, -0.40f, -0.50f, -0.10f }, { -0.40f, -0.60f, -0.55f, -0.10f }, { -0.45f, -0.60f, -0.55f, -0.10f }, { -0.50f, -0.40f, -0.55f, -0.10f } },
            ["fist"] = new float[,] { { -1.00f, -0.80f, -0.40f, -0.60f }, { -1.00f, -0.40f, -1.00f, -0.50f }, { -1.00f, -0.60f, -1.00f, -0.50f }, { -1.00f, -0.60f, -1.00f, -0.50f }, { -1.00f, -0.40f, -1.00f, -0.50f } },
            ["point"] = new float[,] { { -1.00f, -0.70f, -0.30f, -0.50f }, { 0.67f, -0.20f, 0.81f, 0.81f }, { -1.00f, -0.60f, -1.00f, -0.50f }, { -1.00f, -0.60f, -1.00f, -0.50f }, { -1.00f, -0.40f, -1.00f, -0.50f } },
            ["flat"] = new float[,] { { -0.90f, 0.00f, 0.60f, 0.60f }, { 0.67f, -0.45f, 0.81f, 0.81f }, { 0.67f, -0.61f, 0.81f, 0.81f }, { 0.67f, -0.75f, 0.81f, 0.81f }, { 0.67f, -0.80f, 0.81f, 0.81f } },
            ["open"] = new float[,] { { -0.10f, 0.30f, 0.60f, 0.60f }, { 0.67f, 0.55f, 0.81f, 0.81f }, { 0.67f, 0.00f, 0.81f, 0.81f }, { 0.67f, 0.55f, 0.81f, 0.81f }, { 0.67f, 0.80f, 0.81f, 0.81f } },
            // phone / book: fingers fairly straight behind the object, thumb across the front
            ["hold_flat"] = new float[,] { { -0.70f, -0.20f, 0.20f, 0.20f }, { 0.10f, -0.40f, 0.30f, 0.40f }, { 0.05f, -0.60f, 0.30f, 0.40f }, { 0.00f, -0.60f, 0.25f, 0.35f }, { -0.05f, -0.40f, 0.25f, 0.35f } },
        };
        static readonly string[] FingerNames = { "Thumb", "Index", "Middle", "Ring", "Little" };
        static readonly string[] Parts = { "1 Stretched", "Spread", "2 Stretched", "3 Stretched" };

        public class FingerSet { public Transform[] bones; public Quaternion[] target; }

        /// Finger bone local rotations for a pose on one hand, computed once through HumanPoseHandler (bind pose body).
        public static FingerSet FingerTargets(Animator anim, bool left, string pose)
        {
            if (string.IsNullOrEmpty(pose) || pose == "none" || !Poses.TryGetValue(pose, out var table)) return null;
            var first = left ? HumanBodyBones.LeftThumbProximal : HumanBodyBones.RightThumbProximal;
            var bones = new List<Transform>();
            for (int i = 0; i < 15; i++) { var t = anim.GetBoneTransform(first + i); if (t) bones.Add(t); }
            if (bones.Count == 0) return null; // rig without finger bones
            var saved = bones.Select(b => b.localRotation).ToArray();
            var all = anim.GetComponentsInChildren<Transform>();
            var savedAll = all.Select(t => (t.localPosition, t.localRotation)).ToArray();
            var h = new HumanPoseHandler(anim.avatar, anim.transform);
            var hp = new HumanPose(); h.GetHumanPose(ref hp);
            string side = left ? "Left" : "Right";
            for (int m = 0; m < HumanTrait.MuscleCount; m++)
            {
                var name = HumanTrait.MuscleName[m];
                if (!name.StartsWith(side + " ")) continue;
                for (int f = 0; f < 5; f++)
                    for (int k = 0; k < 4; k++)
                        if (name == $"{side} {FingerNames[f]} {Parts[k]}") hp.muscles[m] = table[f, k];
            }
            h.SetHumanPose(ref hp);
            var fs = new FingerSet { bones = bones.ToArray(), target = bones.Select(b => b.localRotation).ToArray() };
            for (int i = 0; i < all.Length; i++) { all[i].localPosition = savedAll[i].localPosition; all[i].localRotation = savedAll[i].localRotation; }
            h.Dispose();
            return fs;
        }

        public static void ApplyFingers(FingerSet fs, float w)
        {
            if (fs == null || w <= 0) return;
            for (int i = 0; i < fs.bones.Length; i++)
                fs.bones[i].localRotation = Quaternion.Slerp(fs.bones[i].localRotation, fs.target[i], Mathf.Clamp01(w));
        }
    }
}
