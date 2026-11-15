// Builds a resolved world (WorldJob) in the open scene: PBR materials with world-space UVs, the room shell (floor,
// walls split around windows/doors, ceiling, trim, blinds, curtains, doors), structural features, and every model,
// snapped by its real mesh bounds onto the floor, against its wall, onto the top of its parent (ray cast) or under
// the ceiling. Everything placed is measured and reported so Python can verify the layout that actually rendered.
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace WorldLab
{
    public class Placed
    {
        public ItemSpec spec; public GameObject go; public Bounds bounds; public string status = "ok"; public float dropY = float.NaN;
        public Quaternion rot; public Vector3 bottom;
    }

    public class BuiltWorld
    {
        public Transform root;
        public readonly Dictionary<string, Placed> items = new Dictionary<string, Placed>();
        public readonly List<(Renderer r, Vector3 p, Vector3 n)> walls = new List<(Renderer, Vector3, Vector3)>();
        public readonly List<Renderer> ceiling = new List<Renderer>();
        public readonly List<Material> glass = new List<Material>();
        public Bounds roomBounds;
    }

    public static class WorldBuilder
    {
        static readonly CultureInfo IC = CultureInfo.InvariantCulture;
        static readonly Dictionary<string, Material> mats = new Dictionary<string, Material>();
        static readonly Dictionary<string, MatSpec> matSpecs = new Dictionary<string, MatSpec>();
        static float kenneyScale = -1;
        static System.Random rnd;

        public static Vector3 V(float[] a, float dflt = 0) => a == null ? new Vector3(dflt, dflt, dflt) : a.Length >= 3 ? new Vector3(a[0], a[1], a[2]) : a.Length == 2 ? new Vector3(a[0], 0, a[1]) : Vector3.zero;
        public static Color C(float[] a, Color dflt) => a == null || a.Length < 3 ? dflt : new Color(a[0], a[1], a[2], a.Length > 3 ? a[3] : 1);

        public static BuiltWorld Build(WorldJob job)
        {
            rnd = new System.Random(job.seed * 31 + 7);
            mats.Clear(); matSpecs.Clear();
            var w = new BuiltWorld { root = new GameObject("Stage_world").transform };
            foreach (var m in job.materials ?? new MatSpec[0]) matSpecs[m.id] = m;
            var r = job.room;
            w.roomBounds = new Bounds(new Vector3(0, r.h / 2, 0), new Vector3(r.w, r.h, r.d));
            Shell(job, w);
            foreach (var f in r.features ?? new FeatureSpec[0]) Feature(f, w);
            foreach (var it in job.items ?? new ItemSpec[0])
            {
                try { w.items[it.id] = Place(it, w, job); }
                catch (System.Exception e) { Debug.LogWarning($"WORLD_ITEM_FAIL {it.id} {e.Message}"); w.items[it.id] = new Placed { spec = it, status = "error: " + e.Message }; }
            }
            return w;
        }

        // ---- materials ------------------------------------------------------------------------------------------

        public static Material Mat(string id, Color fallback, float smooth = 0.3f)
        {
            string key = (id ?? "") + "|" + ColorUtility.ToHtmlStringRGB(fallback);
            if (mats.TryGetValue(key, out var hit)) return hit;
            Material m;
            if (!string.IsNullOrEmpty(id) && matSpecs.TryGetValue(id, out var s))
            {
                m = ShotStudio.Materials.Make(C(s.tint, Color.white), Tex(s.albedo), s.smooth, s.metallic);
                var n = Tex(s.normal);
                if (n) { m.SetTexture("_BumpMap", n); m.SetFloat("_BumpScale", s.normalScale); m.EnableKeyword("_NORMALMAP"); }
                m.name = id;
            }
            else { m = ShotStudio.Materials.Make(fallback, null, smooth); m.name = "flat_" + key; }
            mats[key] = m;
            return m;
        }

        static Texture2D Tex(string path) => string.IsNullOrEmpty(path) ? null : AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        static float Tile(string id) => !string.IsNullOrEmpty(id) && matSpecs.TryGetValue(id, out var s) && s.tile > 0.01f ? s.tile : 2f;

        // ---- meshes with world-space UVs --------------------------------------------------------------------------

        /// A box whose faces get planar world-space UVs (u, v = world coords / tile), so textures keep their real-world
        /// size on walls, floors and columns of any size.
        public static GameObject Box(string name, Vector3 center, Vector3 size, Quaternion rot, Material m, float tile, Transform parent, bool shadows = true)
        {
            var mesh = new Mesh { name = name };
            var v = new List<Vector3>(); var nn = new List<Vector3>(); var uv = new List<Vector2>(); var tri = new List<int>();
            Vector3 h = size * 0.5f;
            Vector3[] normals = { Vector3.right, Vector3.left, Vector3.up, Vector3.down, Vector3.forward, Vector3.back };
            foreach (var n in normals)
            {
                Vector3 a = Mathf.Abs(n.y) > 0.5f ? Vector3.right : Vector3.up;
                Vector3 t1 = Vector3.Cross(n, a).normalized, t2 = Vector3.Cross(n, t1).normalized;
                int b = v.Count;
                for (int k = 0; k < 4; k++)
                {
                    float s1 = (k == 1 || k == 2) ? 1 : -1, s2 = k >= 2 ? 1 : -1;
                    var lp = Vector3.Scale(n + t1 * s1 + t2 * s2, h);
                    v.Add(lp); nn.Add(n);
                    var wp = center + rot * lp; var wn = rot * n;
                    Vector2 q = Mathf.Abs(wn.x) > 0.5f ? new Vector2(wp.z, wp.y) : Mathf.Abs(wn.y) > 0.5f ? new Vector2(wp.x, wp.z) : new Vector2(wp.x, wp.y);
                    uv.Add(q / Mathf.Max(0.05f, tile));
                }
                // winding so the face points along n
                if (Vector3.Dot(Vector3.Cross(v[b + 1] - v[b], v[b + 2] - v[b]), n) > 0) tri.AddRange(new[] { b, b + 1, b + 2, b, b + 2, b + 3 });
                else tri.AddRange(new[] { b, b + 2, b + 1, b, b + 3, b + 2 });
            }
            mesh.SetVertices(v); mesh.SetNormals(nn); mesh.SetUVs(0, uv); mesh.SetTriangles(tri, 0);
            mesh.RecalculateBounds(); mesh.RecalculateTangents();
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.transform.SetPositionAndRotation(center, rot);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = m;
            mr.shadowCastingMode = shadows ? ShadowCastingMode.On : ShadowCastingMode.Off; mr.receiveShadows = true;
            return go;
        }

        // ---- room shell ---------------------------------------------------------------------------------------------

        static void Shell(WorldJob job, BuiltWorld w)
        {
            var r = job.room;
            var trim = ShotStudio.Materials.Make(C(r.trimColor, new Color(0.9f, 0.88f, 0.84f)), null, 0.35f);
            // Floor (walkable rect) and ceiling.
            var fr = r.floorRect != null && r.floorRect.Length == 4 ? r.floorRect : new[] { -r.w / 2, -r.d / 2, r.w / 2, r.d / 2 };
            var floorMat = Mat(r.floorMat, new Color(0.4f, 0.3f, 0.22f));
            if (r.floorTint != null) { floorMat = new Material(floorMat); floorMat.SetColor("_BaseColor", C(r.floorTint, Color.white)); }
            var floor = Box("Floor", new Vector3((fr[0] + fr[2]) / 2, -0.1f, (fr[1] + fr[3]) / 2), new Vector3(fr[2] - fr[0], 0.2f, fr[3] - fr[1]), Quaternion.identity, floorMat, Tile(r.floorMat), w.root);
            floor.AddComponent<MeshCollider>();
            if (r.ceiling)
            {
                var cm = Mat(r.ceilingMat, new Color(0.85f, 0.85f, 0.83f), 0.05f);
                if (r.ceilingTint != null) { cm = new Material(cm); cm.SetColor("_BaseColor", C(r.ceilingTint, Color.white)); }
                var c = Box("Ceiling", new Vector3(0, r.h + 0.1f, 0), new Vector3(r.w + 0.6f, 0.2f, r.d + 0.6f), Quaternion.identity, cm, Tile(r.ceilingMat), w.root);
                w.ceiling.Add(c.GetComponent<Renderer>());
            }
            foreach (var wall in job.walls ?? new WallSpec[0]) Wall(wall, w, trim, r);
        }

        static void Wall(WallSpec s, BuiltWorld w, Material trim, RoomSpec room)
        {
            Vector3 a = V(s.a), b = V(s.b), n = V(s.n).normalized;
            float L = Vector3.Distance(a, b);
            var t = (b - a) / Mathf.Max(1e-4f, L);
            const float T = 0.24f;
            var m = Mat(s.mat, new Color(0.8f, 0.78f, 0.74f), 0.1f);
            if (s.tint != null && s.tint.Length >= 3) { m = new Material(m); m.SetColor("_BaseColor", C(s.tint, Color.white)); }
            float tile = Tile(s.mat);
            var rot = Quaternion.LookRotation(n, Vector3.up); // local z = inward
            float y0 = s.baseY, y1 = s.height;
            var ops = (s.openings ?? new OpeningSpec[0]).OrderBy(o => o.u).ToList();
            void Seg(float u0, float u1, float ya, float yb, string nm)
            {
                if (u1 - u0 < 0.005f || yb - ya < 0.005f) return;
                float ext0 = u0 <= 0.001f ? T : 0, ext1 = u1 >= L - 0.001f ? T : 0; // close the corners
                float cu = (u0 - ext0 + u1 + ext1) / 2;
                var c = a + t * cu - n * (T / 2) + Vector3.up * ((ya + yb) / 2);
                var go = Box(nm, c, new Vector3(u1 + ext1 - u0 + ext0, yb - ya, T), rot, m, tile, w.root);
                w.walls.Add((go.GetComponent<Renderer>(), a + t * cu, n));
            }
            float cur = 0;
            foreach (var o in ops)
            {
                float u0 = Mathf.Clamp(o.u - o.width / 2, 0, L), u1 = Mathf.Clamp(o.u + o.width / 2, 0, L);
                Seg(cur, u0, y0, y1, s.name);
                float sill = o.type == "window" ? o.sill : 0;
                if (o.type == "tunnel") sill = y0;
                Seg(u0, u1, y0, sill, s.name + "_below");
                Seg(u0, u1, sill + o.height, y1, s.name + "_above");
                Opening(o, s, a, t, n, rot, w, trim, room);
                cur = u1;
            }
            Seg(cur, L, y0, y1, s.name);
            if (s.baseboard)
            {
                // Skirting along the wall, broken at doors.
                float bcur = 0;
                foreach (var o in ops.Where(o => o.type != "window"))
                {
                    float u0 = Mathf.Clamp(o.u - o.width / 2 - 0.06f, 0, L);
                    if (u0 - bcur > 0.05f) { var go = Box(s.name + "_skirt", a + t * ((bcur + u0) / 2) + n * 0.008f + Vector3.up * 0.05f, new Vector3(u0 - bcur, 0.1f, 0.016f), rot, trim, 1, w.root, false); w.walls.Add((go.GetComponent<Renderer>(), a + t * ((bcur + u0) / 2), n)); }
                    bcur = Mathf.Clamp(o.u + o.width / 2 + 0.06f, 0, L);
                }
                if (L - bcur > 0.05f) { var go = Box(s.name + "_skirt", a + t * ((bcur + L) / 2) + n * 0.008f + Vector3.up * 0.05f, new Vector3(L - bcur, 0.1f, 0.016f), rot, trim, 1, w.root, false); w.walls.Add((go.GetComponent<Renderer>(), a + t * ((bcur + L) / 2), n)); }
            }
        }

        static void Opening(OpeningSpec o, WallSpec s, Vector3 a, Vector3 t, Vector3 n, Quaternion rot, BuiltWorld w, Material trim, RoomSpec room)
        {
            var c = a + t * o.u; // on the inner wall surface, floor level
            var frameM = ShotStudio.Materials.Make(C(o.frameColor, new Color(0.85f, 0.83f, 0.78f)), null, 0.35f);
            const float T = 0.24f;
            if (o.type == "window")
            {
                float y0 = o.sill, y1 = o.sill + o.height, cy = (y0 + y1) / 2;
                var mid = c - n * (T * 0.5f);
                // Frame (jambs, head, sill) inset in the opening, a cross mullion, a sill board inside.
                Box("WinJambL", mid - t * (o.width / 2 - 0.03f) + Vector3.up * cy, new Vector3(0.06f, o.height, T), rot, frameM, 1, w.root);
                Box("WinJambR", mid + t * (o.width / 2 - 0.03f) + Vector3.up * cy, new Vector3(0.06f, o.height, T), rot, frameM, 1, w.root);
                Box("WinHead", mid + Vector3.up * (y1 - 0.03f), new Vector3(o.width, 0.06f, T), rot, frameM, 1, w.root);
                Box("WinSillIn", c + n * 0.04f + Vector3.up * (y0 - 0.02f), new Vector3(o.width + 0.12f, 0.04f, 0.12f), rot, frameM, 1, w.root);
                Box("WinMullionV", mid + Vector3.up * cy, new Vector3(0.045f, o.height, 0.06f), rot, frameM, 1, w.root);
                Box("WinMullionH", mid + Vector3.up * (y0 + o.height * 0.62f), new Vector3(o.width, 0.045f, 0.06f), rot, frameM, 1, w.root);
                if (o.glass)
                {
                    var gm = Glass(o.rainy);
                    w.glass.Add(gm);
                    var g = Box("Glass", mid + Vector3.up * cy, new Vector3(o.width - 0.06f, o.height - 0.06f, 0.01f), rot, gm, 1, w.root, false);
                    g.GetComponent<Renderer>().receiveShadows = false;
                }
                if (o.blinds)
                {
                    // Real slats inside the opening: sunlight and street light through them paint true stripes.
                    var bm = ShotStudio.Materials.Make(new Color(0.78f, 0.74f, 0.66f), null, 0.3f);
                    float span = o.height * Mathf.Clamp01(o.blindsOpen <= 0 ? 1 : o.blindsOpen);
                    int count = Mathf.Max(3, Mathf.RoundToInt(span / 0.055f));
                    for (int i = 0; i < count; i++)
                    {
                        float y = y1 - 0.05f - i * (span - 0.06f) / Mathf.Max(1, count - 1);
                        var slatRot = rot * Quaternion.Euler(o.blindsTilt, 0, 0);
                        Box("BlindSlat", c - n * 0.035f + Vector3.up * y, new Vector3(o.width - 0.1f, 0.003f, 0.05f), slatRot, bm, 1, w.root);
                    }
                    Box("BlindRail", c - n * 0.035f + Vector3.up * (y1 - 0.02f), new Vector3(o.width - 0.08f, 0.04f, 0.06f), rot, bm, 1, w.root);
                }
                if (o.curtains)
                {
                    var cm = Mat(o.curtainMat, new Color(0.5f, 0.2f, 0.18f), 0.05f);
                    float top = Mathf.Min(room.h - 0.05f, y1 + 0.25f);
                    foreach (int side in new[] { -1, 1 })
                        Curtain(c + n * 0.09f + t * side * (o.width / 2 + 0.12f), t, n, 0.5f, top, Mathf.Max(0.02f, y0 - 0.15f), cm, w.root);
                    Box("CurtainRod", c + n * 0.1f + Vector3.up * (top + 0.02f), new Vector3(o.width + 0.9f, 0.025f, 0.025f), rot, ShotStudio.Materials.Make(new Color(0.15f, 0.13f, 0.1f), null, 0.6f, 0.8f), 1, w.root);
                }
            }
            else if (o.type == "door")
            {
                float hgt = o.height;
                Box("DoorJambL", c - t * (o.width / 2 + 0.035f) + n * 0.01f + Vector3.up * (hgt / 2), new Vector3(0.07f, hgt + 0.07f, T + 0.04f), rot, trim, 1, w.root);
                Box("DoorJambR", c + t * (o.width / 2 + 0.035f) + n * 0.01f + Vector3.up * (hgt / 2), new Vector3(0.07f, hgt + 0.07f, T + 0.04f), rot, trim, 1, w.root);
                Box("DoorHead", c + n * 0.01f + Vector3.up * (hgt + 0.035f), new Vector3(o.width + 0.14f, 0.07f, T + 0.04f), rot, trim, 1, w.root);
                var dm = string.IsNullOrEmpty(o.doorMat) ? ShotStudio.Materials.Make(C(o.doorColor, new Color(0.35f, 0.24f, 0.16f)), ShotStudio.Materials.Noise(new Color(0.85f, 0.85f, 0.85f), Color.white, 128, 3, 5, 0.9f), 0.35f) : Mat(o.doorMat, Color.white);
                // Leaf hinged on the left jamb, swinging into the room by doorOpen degrees.
                var hinge = c - t * (o.width / 2) - n * 0.03f;
                var leafRot = Quaternion.AngleAxis(-o.doorOpen, Vector3.up) * rot;
                var leafT = Quaternion.AngleAxis(-o.doorOpen, Vector3.up) * t;
                var leaf = Box("DoorLeaf", hinge + leafT * (o.width / 2 - 0.005f) + Vector3.up * (hgt / 2 - 0.005f), new Vector3(o.width - 0.01f, hgt - 0.01f, 0.045f), leafRot, dm, 1, w.root);
                var knobM = ShotStudio.Materials.Make(new Color(0.75f, 0.6f, 0.35f), null, 0.8f, 1f);
                var knobN = Quaternion.AngleAxis(-o.doorOpen, Vector3.up) * n;
                Box("DoorKnob", hinge + leafT * (o.width - 0.08f) + Vector3.up * 1.0f + knobN * 0.045f, new Vector3(0.05f, 0.05f, 0.05f), leafRot, knobM, 1, w.root);
                // A short dim corridor behind the door, so an open door doesn't show the sky.
                Corridor(c, t, n, o.width, hgt, s, w);
            }
            else if (o.type == "arch")
                Corridor(c, t, n, o.width, o.height, s, w); // a passage, dimly lit by the room
            else if (o.type == "tunnel")
            {
                var black = ShotStudio.Materials.Make(new Color(0.01f, 0.01f, 0.012f), null, 0.1f);
                float yb = o.type == "tunnel" ? s.baseY : 0;
                Box("TunnelVoid", c - n * 4f + Vector3.up * (yb + o.height / 2), new Vector3(o.width + 0.4f, o.height + 0.4f, 7.5f), rot, black, 1, w.root, true);
            }
        }

        static void Corridor(Vector3 c, Vector3 t, Vector3 n, float width, float hgt, WallSpec s, BuiltWorld w)
        {
            var m = Mat(s.mat, new Color(0.6f, 0.58f, 0.55f), 0.1f);
            var dim = new Material(m); dim.SetColor("_BaseColor", new Color(0.45f, 0.45f, 0.45f));
            var rot = Quaternion.LookRotation(n, Vector3.up);
            float D = 1.8f, W = width + 1.6f;
            var back = c - n * (0.24f + D);
            Box("CorrBack", back - n * 0.1f + Vector3.up * 1.4f, new Vector3(W, 2.8f, 0.2f), rot, dim, Tile(s.mat), w.root);
            Box("CorrL", c - n * (0.24f + D / 2) - t * (W / 2 + 0.1f) + Vector3.up * 1.4f, new Vector3(0.2f, 2.8f, D + 0.2f), rot, dim, Tile(s.mat), w.root);
            Box("CorrR", c - n * (0.24f + D / 2) + t * (W / 2 + 0.1f) + Vector3.up * 1.4f, new Vector3(0.2f, 2.8f, D + 0.2f), rot, dim, Tile(s.mat), w.root);
            Box("CorrCeil", c - n * (0.24f + D / 2) + Vector3.up * 2.9f, new Vector3(W + 0.4f, 0.2f, D + 0.4f), rot, dim, 2, w.root);
            Box("CorrFloor", c - n * (0.24f + D / 2) + Vector3.up * -0.1f, new Vector3(W + 0.4f, 0.2f, D + 0.4f), rot, ShotStudio.Materials.Make(new Color(0.2f, 0.18f, 0.16f), null, 0.3f), 2, w.root);
        }

        static Material Glass(bool rainy)
        {
            var m = ShotStudio.Materials.Make(new Color(0.75f, 0.82f, 0.88f, rainy ? 0.22f : 0.08f), null, 0.96f);
            m.SetFloat("_Surface", 1); m.SetFloat("_Blend", 0);
            m.SetOverrideTag("RenderType", "Transparent");
            m.SetInt("_SrcBlend", (int)BlendMode.SrcAlpha); m.SetInt("_DstBlend", (int)BlendMode.OneMinusSrcAlpha); m.SetInt("_ZWrite", 0);
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            if (rainy)
            {
                m.SetTexture("_BumpMap", WorldEffects.RainNormal(256, 11)); m.SetFloat("_BumpScale", 1.0f); m.EnableKeyword("_NORMALMAP");
                m.SetTextureScale("_BumpMap", new Vector2(1.6f, 1.6f));
            }
            return m;
        }

        /// A pleated curtain panel (double-sided strip with a sine fold), hanging from `top` to `bottom`.
        static void Curtain(Vector3 center, Vector3 t, Vector3 n, float width, float top, float bottom, Material m, Transform parent)
        {
            var mesh = new Mesh { name = "Curtain" };
            int N = 28; var v = new List<Vector3>(); var uv = new List<Vector2>(); var tri = new List<int>();
            for (int i = 0; i <= N; i++)
            {
                float u = i / (float)N, x = (u - 0.5f) * width, z = Mathf.Sin(u * Mathf.PI * 7) * 0.035f;
                v.Add(t * x + n * z + Vector3.up * top); v.Add(t * x + n * z + Vector3.up * bottom);
                uv.Add(new Vector2(u * width / 0.6f, top / 0.6f)); uv.Add(new Vector2(u * width / 0.6f, bottom / 0.6f));
            }
            for (int i = 0; i < N; i++) { int k = i * 2; tri.AddRange(new[] { k, k + 1, k + 2, k + 1, k + 3, k + 2, k, k + 2, k + 1, k + 1, k + 2, k + 3 }); }
            mesh.SetVertices(v); mesh.SetUVs(0, uv); mesh.SetTriangles(tri, 0); mesh.RecalculateNormals(); mesh.RecalculateBounds(); mesh.RecalculateTangents();
            var go = new GameObject("Curtain"); go.transform.SetParent(parent, false); go.transform.position = new Vector3(center.x, 0, center.z);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mm = new Material(m); mm.SetFloat("_Cull", 0);
            var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = mm; mr.shadowCastingMode = ShadowCastingMode.TwoSided;
        }

        static void Feature(FeatureSpec f, BuiltWorld w)
        {
            var col = C(f.color, new Color(0.5f, 0.5f, 0.5f));
            Material m = string.IsNullOrEmpty(f.mat) ? (f.emissive > 0 ? ShotStudio.Materials.Emissive(col, f.emissive) : ShotStudio.Materials.Make(col, null, f.type == "rail" ? 0.7f : 0.3f, f.type == "rail" ? 0.9f : 0)) : Mat(f.mat, col);
            if (!string.IsNullOrEmpty(f.mat) && f.color != null) { m = new Material(m); m.SetColor("_BaseColor", col); }
            var go = Box(f.type + "_feature", V(f.pos), V(f.size, 0.4f), Quaternion.Euler(0, f.yaw, 0), m, Tile(f.mat), w.root, f.emissive <= 0);
            if (f.type == "trench" || f.type == "box" || f.type == "strip" || f.type == "platform") go.AddComponent<MeshCollider>();
        }

        // ---- models ------------------------------------------------------------------------------------------------

        static float KenneyScale()
        {
            if (kenneyScale > 0) return kenneyScale;
            var p = AssetDatabase.LoadAssetAtPath<GameObject>("Assets/ThirdParty/Kenney/Furniture/doorway.fbx");
            if (p == null) return kenneyScale = 1;
            var b = Bounds(Object.Instantiate(p), true);
            return kenneyScale = b.size.y > 1e-4f ? 2.25f / b.size.y : 1;
        }

        public static Bounds Bounds(GameObject go, bool destroy = false)
        {
            var rs = go.GetComponentsInChildren<Renderer>().Where(r => r.enabled && !(r is ParticleSystemRenderer)).ToArray();
            var b = rs.Length > 0 ? rs[0].bounds : new Bounds(go.transform.position, Vector3.zero);
            foreach (var r in rs) b.Encapsulate(r.bounds);
            if (destroy) Object.DestroyImmediate(go);
            return b;
        }

        /// Instantiates a library model at the origin with its size rule (Poly Haven is metric; Kenney is scaled by
        /// its kit reference; anything else is fitted to fitHeight) and its front correction.
        public static GameObject Spawn(ItemSpec it, Transform parent)
        {
            GameObject go;
            if (!string.IsNullOrEmpty(it.proc)) go = Procedural.Make(it, parent);
            else
            {
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(it.path);
                if (prefab == null) throw new System.Exception("missing model " + it.path + " (run unity/WorldLab/fetch_world_assets.py)");
                go = (GameObject)Object.Instantiate(prefab, parent);
                go.name = it.id;
                float k = it.scale <= 0 ? 1 : it.scale;
                if (it.src == "kenney") k *= KenneyScale();
                go.transform.localScale = prefab.transform.localScale * k;
                go.transform.rotation = Quaternion.Euler(0, it.yaw + it.front, 0);
                if (it.fitHeight > 0)
                {
                    var b0 = Bounds(go);
                    if (b0.size.y > 1e-4f) go.transform.localScale *= it.fitHeight / b0.size.y;
                }
                ShotStudio.Materials.ConvertAll(go);
                if (it.tint != null && it.tint.Length >= 3)
                    foreach (var r in go.GetComponentsInChildren<Renderer>())
                    {
                        var ms = r.sharedMaterials.Select(x => { var c = new Material(x); c.SetColor("_BaseColor", x.GetColor("_BaseColor") * C(it.tint, Color.white)); return c; }).ToArray();
                        r.sharedMaterials = ms;
                    }
            }
            go.transform.rotation = Quaternion.Euler(0, it.yaw + it.front, 0);
            foreach (var r in go.GetComponentsInChildren<Renderer>())
            {
                r.shadowCastingMode = it.shadows ? ShadowCastingMode.On : ShadowCastingMode.Off; r.receiveShadows = true;
            }
            return go;
        }

        static Placed Place(ItemSpec it, BuiltWorld w, WorldJob job)
        {
            var go = Spawn(it, w.root);
            var p = new Placed { spec = it, go = go, rot = Quaternion.Euler(0, it.yaw, 0) };
            var target = V(it.pos);
            var b = Bounds(go);
            Vector3 Shift(Bounds bb, Vector3 want) => want - bb.center;
            switch (it.anchor)
            {
                case "wall":
                {
                    var n = V(it.wallN).normalized;
                    float y = it.mountY >= 0 ? it.mountY : target.y;
                    go.transform.position += Shift(b, new Vector3(target.x, y, target.z));
                    b = Bounds(go);
                    // Push along the wall normal until the back of the bounds touches the wall surface.
                    float back = float.MaxValue;
                    foreach (var corner in Corners(b)) back = Mathf.Min(back, Vector3.Dot(new Vector3(corner.x, 0, corner.z), n));
                    go.transform.position += n * (it.wallD + 0.004f - back);
                    if (it.mountY < 0 && target.y <= 0.001f) { b = Bounds(go); go.transform.position += Vector3.up * (0 - b.min.y); } // floor-standing against a wall
                    break;
                }
                case "ceiling":
                    go.transform.position += new Vector3(target.x - b.center.x, job.room.h - 0.002f - b.max.y, target.z - b.center.z);
                    break;
                case "surface":
                case "seat":
                {
                    go.transform.position += new Vector3(target.x - b.center.x, target.y - b.min.y, target.z - b.center.z);
                    if (!string.IsNullOrEmpty(it.on) && w.items.TryGetValue(it.on, out var parent) && parent.go != null)
                    {
                        b = Bounds(go);
                        float top = Drop(parent.go, b, it.anchor == "seat");
                        if (!float.IsNaN(top)) { go.transform.position += Vector3.up * (top - b.min.y + 0.001f); p.dropY = top; }
                        else p.status = "drop_miss";
                    }
                    break;
                }
                case "free":
                    go.transform.position += target - new Vector3(b.center.x, b.min.y, b.center.z);
                    break;
                default: // floor
                    go.transform.position += new Vector3(target.x - b.center.x, target.y - b.min.y, target.z - b.center.z);
                    break;
            }
            if (it.lie) go.transform.RotateAround(Bounds(go).center, Vector3.up, (float)(rnd.NextDouble() * 24 - 12));
            p.bounds = Bounds(go);
            p.bottom = new Vector3(p.bounds.center.x, p.bounds.min.y, p.bounds.center.z);
            return p;
        }

        /// Highest point of the parent's mesh under the middle of the footprint b (ray cast against temporary mesh colliders).
        static float Drop(GameObject parent, Bounds b, bool seat)
        {
            var cols = new List<Collider>();
            foreach (var mf in parent.GetComponentsInChildren<MeshFilter>())
                if (mf.sharedMesh && !mf.GetComponent<Collider>()) { var mc = mf.gameObject.AddComponent<MeshCollider>(); mc.sharedMesh = mf.sharedMesh; cols.Add(mc); }
            Physics.SyncTransforms();
            var pb = Bounds(parent);
            var hits = new List<float>();
            for (int i = -1; i <= 1; i++)
                for (int j = -1; j <= 1; j++)
                {
                    var o = new Vector3(b.center.x + i * b.extents.x * 0.5f, pb.max.y + 0.5f, b.center.z + j * b.extents.z * 0.5f);
                    foreach (var h in Physics.RaycastAll(o, Vector3.down, pb.size.y + 1f))
                        if (h.collider.transform.IsChildOf(parent.transform)) { hits.Add(h.point.y); break; }
                }
            foreach (var c in cols) Object.DestroyImmediate(c);
            if (hits.Count == 0) return float.NaN;
            hits.Sort();
            // Seats: the median (cushions are lumpy); surfaces: the centre-ish maximum, ignoring a raised back edge.
            return seat ? hits[hits.Count / 2] : hits[Mathf.Min(hits.Count - 1, hits.Count * 2 / 3)];
        }

        public static IEnumerable<Vector3> Corners(Bounds b)
        {
            for (int i = 0; i < 8; i++)
                yield return new Vector3((i & 1) == 0 ? b.min.x : b.max.x, (i & 2) == 0 ? b.min.y : b.max.y, (i & 4) == 0 ? b.min.z : b.max.z);
        }

        /// Walls between the camera and the room become shadow-only (a film-set cutaway that keeps the room light-tight).
        public static void Cull(BuiltWorld w, Vector3 cam)
        {
            foreach (var (r, p, n) in w.walls)
                r.shadowCastingMode = Vector3.Dot(cam - p, n) > 0.05f ? ShadowCastingMode.On : ShadowCastingMode.ShadowsOnly;
            foreach (var r in w.ceiling) r.shadowCastingMode = cam.y < w.roomBounds.max.y - 0.02f ? ShadowCastingMode.On : ShadowCastingMode.ShadowsOnly;
        }

        public static string Report(BuiltWorld w)
        {
            string F(float v) => float.IsNaN(v) || float.IsInfinity(v) ? "null" : v.ToString("0.###", IC);
            string Vv(Vector3 v) => $"[{F(v.x)},{F(v.y)},{F(v.z)}]";
            var sb = new StringBuilder("[");
            bool first = true;
            foreach (var kv in w.items)
            {
                var p = kv.Value;
                sb.Append(first ? "" : ","); first = false;
                if (p.go == null) { sb.Append($"{{\"id\":\"{kv.Key}\",\"status\":\"{p.status.Replace("\"", "'")}\"}}"); continue; }
                sb.Append($"{{\"id\":\"{kv.Key}\",\"asset\":\"{p.spec.asset}\",\"status\":\"{p.status}\",\"min\":{Vv(p.bounds.min)},\"max\":{Vv(p.bounds.max)},\"yaw\":{F(p.spec.yaw)},\"anchor\":\"{p.spec.anchor}\",\"dropY\":{F(p.dropY)}}}");
            }
            return sb.Append("]").ToString();
        }
    }
}
