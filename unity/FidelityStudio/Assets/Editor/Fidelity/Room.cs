// The set: an old living room with a big west-facing window (here +Z), a door to a lit hallway, a chess table by the
// window and period furniture. Shell and trim are built in code; furniture, props and surfaces come from Poly Haven
// (CC0). Blocking positions come from demo/fidelity/layout.json, shared with the motion generation.
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

namespace Fidelity
{
    [System.Serializable] public class Range2 { public float[] x = { -3.2f, 3.2f }; public float[] z = { -2.8f, 2.8f }; public float height = 2.8f; }
    [System.Serializable] public class WinSpec { public float[] x = { -1.5f, 1.5f }; public float sill = 0.72f; public float top = 2.42f; }
    [System.Serializable] public class DoorSpec { public float[] x = { -1.92f, -1f }; public float height = 2.12f; }
    [System.Serializable] public class Layout
    {
        public Range2 room = new Range2(); public WinSpec window = new WinSpec(); public DoorSpec door = new DoorSpec();
        public float seat_height = 0.46f;
        public float[] table = { 0.45f, 1.75f }, chair_a = { -0.42f, 1.75f }, chair_b = { 1.32f, 1.75f };
        public float chair_a_yaw = 90, chair_b_yaw = -90;
    }

    public class FurnitureInfo
    {
        public string id; public GameObject go; public float seatTop; public Vector3 seatCenter; public Bounds bounds;
    }

    public class RoomInfo
    {
        public Dictionary<string, FurnitureInfo> furniture = new Dictionary<string, FurnitureInfo>();
        public List<Light> practicals = new List<Light>();
        public GameObject chess;
        public Layout layout;
        public Vector3 windowCenter;
    }

    public static class Room
    {
        // Measured model fronts: the yaw that turns each model's front (seat side) toward +Z.
        static readonly Dictionary<string, float> Front = new Dictionary<string, float>
        {
            { "dining_chair_02", 0 }, { "ArmChair_01", 0 }, { "Sofa_01", 0 }, { "vintage_cabinet_01", 0 },
            { "vintage_grandfather_clock_01", 0 }, { "hanging_picture_frame_01", 0 }, { "hanging_picture_frame_02", 0 }, { "ornate_mirror_01", 0 },
        };

        public static Layout LoadLayout()
        {
            var f = Path.Combine(Lib.Root, "demo", "fidelity", "layout.json");
            return File.Exists(f) ? JsonUtility.FromJson<Layout>(File.ReadAllText(f)) : new Layout();
        }

        static Material wall, ceiling, trim, floor, wood, rug, curtain, brass, hallWall;

        public static RoomInfo Build(Layout L)
        {
            var info = new RoomInfo { layout = L };
            var root = new GameObject("Room").transform;
            wall = Lib.Surface("plastered_wall_04", 1f, new Color(0.93f, 0.86f, 0.74f), 0.6f, 0.6f);
            hallWall = Lib.Surface("plastered_wall_04", 1f, new Color(0.80f, 0.70f, 0.58f), 0.6f, 0.6f);
            ceiling = Lib.Surface("plastered_wall_04", 1f, new Color(0.95f, 0.93f, 0.88f), 0.4f, 0.3f);
            floor = Lib.Surface("rectangular_parquet", 1f, new Color(0.92f, 0.86f, 0.8f), 1f, 1f);
            wood = Lib.Surface("dark_wood", 1f, new Color(0.75f, 0.62f, 0.5f), 1f, 1f);
            rug = Lib.Surface("floral_jacquard", 1f, new Color(1.0f, 0.82f, 0.7f), 0.4f, 1.2f);
            trim = Lib.Lit(new Color(0.86f, 0.83f, 0.76f), 0.55f);
            curtain = Lib.Lit(new Color(0.80f, 0.72f, 0.60f), 0.2f);
            curtain.SetFloat("_DoubleSidedEnable", 1); HDMaterial.ValidateMaterial(curtain);
            brass = Lib.Lit(new Color(0.78f, 0.6f, 0.34f), 0.75f, 1f);

            float x0 = L.room.x[0], x1 = L.room.x[1], z0 = L.room.z[0], z1 = L.room.z[1], H = L.room.height, T = 0.22f;
            float wx0 = L.window.x[0], wx1 = L.window.x[1], ws = L.window.sill, wt = L.window.top;
            float dx0 = L.door.x[0], dx1 = L.door.x[1], dh = L.door.height;

            // Shell.
            Lib.Box("Floor", new Vector3((x0 + x1) / 2, -0.05f, (z0 + z1) / 2), new Vector3(x1 - x0, 0.1f, z1 - z0), floor, root, 1.6f);
            Lib.Box("Ceiling", new Vector3((x0 + x1) / 2, H + 0.05f, (z0 + z1) / 2), new Vector3(x1 - x0 + 2 * T, 0.1f, z1 - z0 + 2 * T), ceiling, root, 2f);
            float zc = z1 + T / 2;
            WallBox("N_left", x0 - T, wx0, 0, H, zc, T, root);
            WallBox("N_right", wx1, x1 + T, 0, H, zc, T, root);
            WallBox("N_below", wx0, wx1, 0, ws, zc, T, root);
            WallBox("N_above", wx0, wx1, wt, H, zc, T, root);
            float zs = z0 - T / 2;
            WallBox("S_left", x0 - T, dx0, 0, H, zs, T, root);
            WallBox("S_right", dx1, x1 + T, 0, H, zs, T, root);
            WallBox("S_above", dx0, dx1, dh, H, zs, T, root);
            Lib.Box("W", new Vector3(x0 - T / 2, H / 2, (z0 + z1) / 2), new Vector3(T, H, z1 - z0), wall, root, 2f);
            Lib.Box("E", new Vector3(x1 + T / 2, H / 2, (z0 + z1) / 2), new Vector3(T, H, z1 - z0), wall, root, 2f);

            // Skirting and cornice.
            float sk = 0.11f, st = 0.018f;
            Lib.Box("Skirt_W", new Vector3(x0 + st / 2, sk / 2, (z0 + z1) / 2), new Vector3(st, sk, z1 - z0), trim, root);
            Lib.Box("Skirt_E", new Vector3(x1 - st / 2, sk / 2, (z0 + z1) / 2), new Vector3(st, sk, z1 - z0), trim, root);
            Lib.Box("Skirt_N1", new Vector3((x0 + wx0) / 2, sk / 2, z1 - st / 2), new Vector3(wx0 - x0, sk, st), trim, root);
            Lib.Box("Skirt_N2", new Vector3((wx1 + x1) / 2, sk / 2, z1 - st / 2), new Vector3(x1 - wx1, sk, st), trim, root);
            Lib.Box("Skirt_N3", new Vector3((wx0 + wx1) / 2, sk / 2, z1 - st / 2), new Vector3(wx1 - wx0, sk, st), trim, root);
            Lib.Box("Skirt_S1", new Vector3((x0 + dx0) / 2, sk / 2, z0 + st / 2), new Vector3(dx0 - x0, sk, st), trim, root);
            Lib.Box("Skirt_S2", new Vector3((dx1 + x1) / 2, sk / 2, z0 + st / 2), new Vector3(x1 - dx1, sk, st), trim, root);
            float cs = 0.07f;
            Lib.Box("Cornice_W", new Vector3(x0 + cs / 2, H - cs / 2, (z0 + z1) / 2), new Vector3(cs, cs, z1 - z0), trim, root);
            Lib.Box("Cornice_E", new Vector3(x1 - cs / 2, H - cs / 2, (z0 + z1) / 2), new Vector3(cs, cs, z1 - z0), trim, root);
            Lib.Box("Cornice_N", new Vector3((x0 + x1) / 2, H - cs / 2, z1 - cs / 2), new Vector3(x1 - x0, cs, cs), trim, root);
            Lib.Box("Cornice_S", new Vector3((x0 + x1) / 2, H - cs / 2, z0 + cs / 2), new Vector3(x1 - x0, cs, cs), trim, root);

            // Window: frame, mullion, transom, glazing bars, interior sill, curtains on a brass rod.
            float fz = z1 + T * 0.55f, fw = 0.07f, fd = 0.07f;
            Lib.Box("Win_L", new Vector3(wx0 + fw / 2, (ws + wt) / 2, fz), new Vector3(fw, wt - ws, fd), trim, root);
            Lib.Box("Win_R", new Vector3(wx1 - fw / 2, (ws + wt) / 2, fz), new Vector3(fw, wt - ws, fd), trim, root);
            Lib.Box("Win_T", new Vector3((wx0 + wx1) / 2, wt - fw / 2, fz), new Vector3(wx1 - wx0, fw, fd), trim, root);
            Lib.Box("Win_B", new Vector3((wx0 + wx1) / 2, ws + fw / 2, fz), new Vector3(wx1 - wx0, fw, fd), trim, root);
            Lib.Box("Win_M", new Vector3((wx0 + wx1) / 2, (ws + wt) / 2, fz), new Vector3(0.06f, wt - ws, fd), trim, root);
            float tr = ws + (wt - ws) * 0.74f;
            Lib.Box("Win_Tr", new Vector3((wx0 + wx1) / 2, tr, fz), new Vector3(wx1 - wx0, 0.06f, fd), trim, root);
            float bar = 0.022f;
            Lib.Box("Bar_1", new Vector3((wx0 + wx1) / 2, ws + (tr - ws) * 0.5f, fz), new Vector3(wx1 - wx0, bar, 0.03f), trim, root);
            for (int i = 1; i <= 2; i++)
            {
                float u = i / 3f;
                Lib.Box("BarV_L" + i, new Vector3(Mathf.Lerp(wx0, (wx0 + wx1) / 2, u), (ws + tr) / 2, fz), new Vector3(bar, tr - ws, 0.03f), trim, root);
                Lib.Box("BarV_R" + i, new Vector3(Mathf.Lerp((wx0 + wx1) / 2, wx1, u), (ws + tr) / 2, fz), new Vector3(bar, tr - ws, 0.03f), trim, root);
            }
            Lib.Box("Sill", new Vector3((wx0 + wx1) / 2, ws - 0.02f, z1 - 0.03f), new Vector3(wx1 - wx0 + 0.2f, 0.04f, 0.2f), wood, root, 0.8f);
            Curtain("Curtain_L", wx0 - 0.62f, wx0 + 0.08f, z1 - 0.09f, H - 0.16f, root, 0);
            Curtain("Curtain_R", wx1 - 0.08f, wx1 + 0.62f, z1 - 0.09f, H - 0.16f, root, 1);
            var rod = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            Object.DestroyImmediate(rod.GetComponent<Collider>());
            rod.name = "Rod"; rod.transform.SetParent(root);
            rod.transform.position = new Vector3((wx0 + wx1) / 2, H - 0.13f, z1 - 0.09f);
            rod.transform.rotation = Quaternion.Euler(0, 0, 90); rod.transform.localScale = new Vector3(0.025f, (wx1 - wx0) / 2 + 0.8f, 0.025f);
            rod.GetComponent<Renderer>().sharedMaterial = brass;
            info.windowCenter = new Vector3((wx0 + wx1) / 2, (ws + wt) / 2, z1);

            // Door casing and an open door leaf against the wall; a warm hallway beyond.
            float cw = 0.08f;
            Lib.Box("Case_L", new Vector3(dx0 - cw / 2, dh / 2, z0 + 0.01f), new Vector3(cw, dh + cw, 0.03f), trim, root);
            Lib.Box("Case_R", new Vector3(dx1 + cw / 2, dh / 2, z0 + 0.01f), new Vector3(cw, dh + cw, 0.03f), trim, root);
            Lib.Box("Case_T", new Vector3((dx0 + dx1) / 2, dh + cw / 2, z0 + 0.01f), new Vector3(dx1 - dx0 + 2 * cw, cw, 0.03f), trim, root);
            Lib.Box("DoorLeaf", new Vector3(dx0 + 0.02f, dh / 2 - 0.005f, z0 - T - (dx1 - dx0) / 2 + 0.02f), new Vector3(0.04f, dh - 0.02f, dx1 - dx0 - 0.04f), wood, root, 0.9f);
            float hz0 = z0 - T - 2.4f, hx0 = dx0 - 0.8f, hx1 = dx1 + 1.1f;
            Lib.Box("H_Floor", new Vector3((hx0 + hx1) / 2, -0.05f, (hz0 + z0 - T) / 2), new Vector3(hx1 - hx0, 0.1f, z0 - T - hz0 + 0.02f), floor, root, 1.6f);
            Lib.Box("H_Ceil", new Vector3((hx0 + hx1) / 2, H + 0.05f, (hz0 + z0 - T) / 2), new Vector3(hx1 - hx0, 0.1f, z0 - T - hz0), ceiling, root, 2f);
            Lib.Box("H_W", new Vector3(hx0 - 0.1f, H / 2, (hz0 + z0 - T) / 2), new Vector3(0.2f, H, z0 - T - hz0), hallWall, root, 2f);
            Lib.Box("H_E", new Vector3(hx1 + 0.1f, H / 2, (hz0 + z0 - T) / 2), new Vector3(0.2f, H, z0 - T - hz0), hallWall, root, 2f);
            Lib.Box("H_S", new Vector3((hx0 + hx1) / 2, H / 2, hz0 - 0.1f), new Vector3(hx1 - hx0 + 0.4f, H, 0.2f), hallWall, root, 2f);
            info.practicals.Add(Lib.Point(new Vector3((dx0 + dx1) / 2, H - 0.35f, hz0 + 0.9f), 900, 2700, 7, 0.08f));
            var shade = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            Object.DestroyImmediate(shade.GetComponent<Collider>());
            shade.name = "HallBulb"; shade.transform.SetParent(root);
            shade.transform.position = new Vector3((dx0 + dx1) / 2, H - 0.35f, hz0 + 0.9f); shade.transform.localScale = Vector3.one * 0.16f;
            var sr = shade.GetComponent<Renderer>(); sr.sharedMaterial = Lib.Emissive(new Color(1f, 0.72f, 0.45f), 30f); sr.shadowCastingMode = ShadowCastingMode.Off;

            // Rug.
            Lib.Box("Rug", new Vector3(0.05f, 0.006f, 0.15f), new Vector3(2.9f, 0.012f, 2.0f), rug, root, 0.9f);

            // Chess table and chairs.
            var tbl = Lib.Model("round_wooden_table_01", new Vector3(L.table[0], 0, L.table[1]), 0, root);
            Fit(tbl, height: 0.75f);
            var tb = Lib.WorldBounds(tbl);
            float shrink = 0.82f / Mathf.Max(tb.size.x, tb.size.z); // a smaller table: the board must be within reach
            tbl.transform.localScale = Vector3.Scale(tbl.transform.localScale, new Vector3(shrink, 1, shrink));
            tb = Lib.WorldBounds(tbl);
            info.chess = Lib.Model("chess_set", new Vector3(L.table[0], tb.max.y, L.table[1]), 90, root, 0.72f);
            AddChair(info, "chair_a", L.chair_a, L.chair_a_yaw, L.seat_height, root);
            AddChair(info, "chair_b", L.chair_b, L.chair_b_yaw, L.seat_height, root);

            // Furniture along the walls.
            Place("ArmChair_01", new Vector3(x0 + 0.75f, 0, z1 - 0.8f), 140, root);
            var side = Place("side_table_01", new Vector3(x0 + 0.35f, 0, z1 - 0.25f), 90, root);
            var sb = Lib.WorldBounds(side);
            var lamp = Lib.Model("vintage_oil_lamp", new Vector3(x0 + 0.33f, sb.max.y, z1 - 0.22f), 0, root);
            var lb = Lib.WorldBounds(lamp);
            info.practicals.Add(Lib.Point(new Vector3(lb.center.x, lb.min.y + lb.size.y * 0.55f, lb.center.z), 120, 2300, 4, 0.03f));
            Lib.Model("standing_picture_frame_01", new Vector3(x0 + 0.42f, sb.max.y, z1 - 0.38f), 120, root);
            Place("Sofa_01", new Vector3(x0 + 0.38f, 0, -0.55f), 90, root);
            Place("potted_plant_02", new Vector3(x0 + 0.42f, 0, -1.85f), 30, root);
            Place("hanging_picture_frame_01", new Vector3(x0 + 0.005f, 1.62f, -0.15f), 90, root);
            Place("hanging_picture_frame_02", new Vector3(x0 + 0.005f, 1.55f, -1.0f), 90, root);
            var cab = Place("vintage_cabinet_01", new Vector3(x1 - 0.36f, 0, -0.35f), -90, root);
            Place("vintage_grandfather_clock_01", new Vector3(x1 - 0.25f, 0, 1.75f), -90, root);
            Place("potted_plant_01", new Vector3(wx1 + 0.85f, 0, z1 - 0.4f), 200, root);
            Place("ornate_mirror_01", new Vector3(0.4f, 1.6f, z0 + 0.005f), 0, root);
            // Small things on the cabinet counter and the window sill (dropped onto the surface below).
            PlaceOn("book_encyclopedia_set_01", x1 - 0.35f, -0.95f, -90, 1.3f, root);
            PlaceOn("mantel_clock_01", x1 - 0.32f, -0.2f, -90, 1.3f, root);
            PlaceOn("tea_set_01", x1 - 0.38f, 0.35f, -90, 1.3f, root, 0.7f);
            PlaceOn("ceramic_vase_01", wx1 - 0.35f, z1 - 0.02f, 0, 1.2f, root, 0.8f);
            PlaceOn("brass_vase_01", wx0 + 0.3f, z1 - 0.02f, 0, 1.2f, root, 0.5f);
            Physics.SyncTransforms();
            return info;
        }

        static void WallBox(string name, float xa, float xb, float ya, float yb, float zc, float t, Transform root)
        {
            if (xb - xa < 1e-3f || yb - ya < 1e-3f) return;
            Lib.Box(name, new Vector3((xa + xb) / 2, (ya + yb) / 2, zc), new Vector3(xb - xa, yb - ya, t), wall, root, 2f);
        }

        /// Pleated curtain: a vertical strip whose depth follows a sine (folds), gathered a little more at the top.
        static void Curtain(string name, float xa, float xb, float z, float top, Transform root, int seed)
        {
            int nx = 80, ny = 24;
            var v = new List<Vector3>(); var uv = new List<Vector2>(); var tri = new List<int>();
            float folds = (xb - xa) / 0.11f;
            for (int j = 0; j <= ny; j++)
                for (int i = 0; i <= nx; i++)
                {
                    float u = i / (float)nx, h = j / (float)ny;
                    float x = Mathf.Lerp(xa, xb, u);
                    float amp = 0.035f * (0.8f + 0.4f * h);
                    float d = Mathf.Sin(u * folds * Mathf.PI * 2 + seed * 1.7f) * amp + Mathf.Sin(u * folds * 0.7f * Mathf.PI + seed) * 0.01f;
                    v.Add(new Vector3(x, Mathf.Lerp(0.01f, top, h), z + d)); uv.Add(new Vector2(u * (xb - xa), h * top));
                }
            for (int j = 0; j < ny; j++)
                for (int i = 0; i < nx; i++)
                {
                    int a = j * (nx + 1) + i, b = a + 1, c = a + nx + 1, d = c + 1;
                    tri.AddRange(new[] { a, c, b, b, c, d });
                }
            var mesh = new Mesh { name = name };
            mesh.SetVertices(v); mesh.SetUVs(0, uv); mesh.SetTriangles(tri, 0);
            mesh.RecalculateNormals(); mesh.RecalculateTangents(); mesh.RecalculateBounds();
            var go = new GameObject(name); go.transform.SetParent(root);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>(); r.sharedMaterial = curtain;
            r.rayTracingMode = UnityEngine.Experimental.Rendering.RayTracingMode.Static; r.shadowCastingMode = ShadowCastingMode.TwoSided;
            Debug.Log($"FID_CURTAIN {name} verts={mesh.vertexCount} bounds={mesh.bounds}");
        }

        static GameObject Place(string id, Vector3 pos, float yaw, Transform root, float scale = 1f)
        {
            Front.TryGetValue(id, out var f);
            var go = Lib.Model(id, pos, yaw + f, root, scale);
            Colliders(go);
            return go;
        }

        static void PlaceOn(string id, float x, float z, float yaw, float from, Transform root, float scale = 1f)
        {
            Physics.SyncTransforms();
            float y = 0;
            if (Physics.Raycast(new Vector3(x, from, z), Vector3.down, out var hit, from + 0.5f)) y = hit.point.y;
            var go = Lib.Model(id, new Vector3(x, y, z), yaw, root, scale);
            Colliders(go);
        }

        public static void Colliders(GameObject go)
        {
            foreach (var mf in go.GetComponentsInChildren<MeshFilter>())
                if (mf.sharedMesh && !mf.GetComponent<Collider>()) mf.gameObject.AddComponent<MeshCollider>().sharedMesh = mf.sharedMesh;
        }

        static void Fit(GameObject go, float height)
        {
            var b = Lib.WorldBounds(go);
            if (b.size.y > 1e-3f) go.transform.localScale *= height / b.size.y;
            Colliders(go);
        }

        static void AddChair(RoomInfo info, string id, float[] at, float yaw, float seatH, Transform root)
        {
            var go = Place("dining_chair_02", new Vector3(at[0], 0, at[1]), yaw, root);
            go.name = id;
            Physics.SyncTransforms();
            var b = Lib.WorldBounds(go);
            float top = seatH;
            var c = new Vector3(at[0], 0, at[1]);
            if (Physics.Raycast(new Vector3(c.x, 0.8f, c.z), Vector3.down, out var hit, 1f)) top = hit.point.y;
            info.furniture[id] = new FurnitureInfo { id = id, go = go, seatTop = top, seatCenter = new Vector3(c.x, top, c.z), bounds = b };
            Debug.Log($"FID_CHAIR {id} seatTop={top:F3} bounds={b.size}");
        }
    }
}
