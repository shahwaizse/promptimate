// Stage presets built from CC0 kits (Kenney City/Furniture/Nature) plus procedural ground. The actors' area (their
// positions over the whole shot) is kept free of props. Kit units differ, so each kit is scaled against a reference
// piece measured at load time.
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace ShotStudio
{
    public class StageInfo
    {
        public string name;
        public List<Vector3> lamps = new List<Vector3>();       // practical light positions (lamp heads)
        public List<(Renderer r, Vector3 p, Vector3 n)> walls = new List<(Renderer, Vector3, Vector3)>(); // n points into the room
        public List<Renderer> ceiling = new List<Renderer>();
        public Bounds area;                                     // playable area (used by validation and wide shots)
    }

    public static class Stages
    {
        public static readonly string[] Names = { "studio", "street", "interior", "park", "void" };
        const string Kit = "Assets/ThirdParty/Kenney/";
        static System.Random rnd;
        static List<Vector3> clear;
        static Transform root;
        static readonly Dictionary<string, float> KitScale = new Dictionary<string, float>();

        public static StageInfo Build(string name, int seed, List<Vector3> keepClear)
        {
            rnd = new System.Random(seed * 7919 + 17);
            tinted.Clear();
            clear = keepClear ?? new List<Vector3>();
            root = new GameObject("Stage_" + name).transform;
            var s = new StageInfo { name = name, area = new Bounds(Vector3.zero, new Vector3(12, 3, 12)) };
            switch (name)
            {
                case "studio": Studio(s); break;
                case "void": Void(s); break;
                case "street": Street(s); break;
                case "interior": Interior(s); break;
                case "park": Park(s); break;
                default: throw new System.Exception($"unknown stage {name}; one of {string.Join(", ", Names)}");
            }
            return s;
        }

        /// Hides walls between the camera and the set (cutaway) and the ceiling for overhead shots.
        public static void CullForCamera(StageInfo s, Vector3 camPos, bool overhead)
        {
            foreach (var (r, p, n) in s.walls)
                r.enabled = Vector3.Dot(camPos - p, n) > 0.15f;
            foreach (var r in s.ceiling) r.enabled = !overhead && camPos.y < 2.6f;
        }

        // ---- helpers ------------------------------------------------------------------------------------------------

        static float R(float a, float b) => a + (float)rnd.NextDouble() * (b - a);
        static bool IsClear(Vector3 p, float radius)
        {
            foreach (var c in clear)
                if (new Vector2(c.x - p.x, c.z - p.z).sqrMagnitude < radius * radius) return false;
            return true;
        }

        static GameObject Load(string rel) => AssetDatabase.LoadAssetAtPath<GameObject>(Kit + rel + ".fbx");

        static Bounds RawBounds(GameObject prefab)
        {
            var go = (GameObject)Object.Instantiate(prefab);
            go.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            var rs = go.GetComponentsInChildren<Renderer>();
            var b = rs.Length > 0 ? rs[0].bounds : new Bounds();
            foreach (var r in rs) b.Encapsulate(r.bounds);
            Object.DestroyImmediate(go);
            return b;
        }

        /// Scale for a kit so that `reference` measures `size` metres along `axis` (0 x, 1 y, 2 z; 3 = max horizontal).
        static float Scale(string kit, string reference, int axis, float size)
        {
            if (KitScale.TryGetValue(kit, out var s)) return s;
            var p = Load(kit + "/" + reference);
            if (p == null) throw new System.Exception($"missing {Kit}{kit}/{reference}.fbx (run unity/DemoStudio/fetch_render_assets.py)");
            var b = RawBounds(p);
            float m = axis == 3 ? Mathf.Max(b.size.x, b.size.z) : b.size[axis];
            s = m > 1e-4f ? size / m : 1;
            KitScale[kit] = s;
            return s;
        }

        /// Places a kit model with its lowest point on y = 0 (+ lift). Returns null when the spot isn't clear.
        static GameObject Prop(string kit, string model, Vector3 pos, float yaw, float scale, float clearRadius = 1.2f, float lift = 0)
        {
            if (clearRadius > 0 && !IsClear(pos, clearRadius)) return null;
            var prefab = Load(kit + "/" + model);
            if (prefab == null) { Debug.LogWarning("ShotStudio: missing prop " + kit + "/" + model); return null; }
            var go = (GameObject)Object.Instantiate(prefab, root);
            go.name = model;
            go.transform.localScale = prefab.transform.localScale * scale;
            go.transform.SetPositionAndRotation(pos, Quaternion.Euler(0, yaw, 0));
            var rs = go.GetComponentsInChildren<Renderer>();
            if (rs.Length > 0)
            {
                var b = rs[0].bounds; foreach (var r in rs) b.Encapsulate(r.bounds);
                go.transform.position += Vector3.up * (pos.y - b.min.y + lift);
            }
            Materials.ConvertAll(go);
            if (kit == "Nature" || kit == "CitySuburban") Foliage(go);
            foreach (var r in rs) { r.shadowCastingMode = ShadowCastingMode.On; r.receiveShadows = true; }
            return go;
        }

        /// Kenney's foliage greens lean teal; pull them toward natural yellow-greens (shared converted materials, once).
        static readonly HashSet<Material> tinted = new HashSet<Material>();
        static void Foliage(GameObject go)
        {
            foreach (var r in go.GetComponentsInChildren<Renderer>())
                foreach (var m in r.sharedMaterials)
                {
                    if (m == null || !tinted.Add(m) || !m.HasProperty("_BaseColor")) continue;
                    var c = m.GetColor("_BaseColor");
                    Color.RGBToHSV(c, out var h, out var sat, out var v);
                    if (h > 0.36f && h < 0.56f && sat > 0.2f) // teal / cyan-green
                        m.SetColor("_BaseColor", Color.HSVToRGB(Mathf.Lerp(h, 0.27f, 0.75f), sat * 0.8f, v * 0.8f));
                }
        }

        static GameObject Ground(float size, Material m, float tile, float y = 0)
        {
            var g = GameObject.CreatePrimitive(PrimitiveType.Plane);
            g.name = "Ground"; g.transform.SetParent(root);
            g.transform.position = new Vector3(0, y, 0);
            g.transform.localScale = Vector3.one * (size / 10f);
            m.mainTextureScale = Vector2.one * (size / tile);
            m.SetTextureScale("_BaseMap", Vector2.one * (size / tile));
            g.GetComponent<Renderer>().sharedMaterial = m;
            Object.DestroyImmediate(g.GetComponent<Collider>());
            return g;
        }

        static GameObject Box(string name, Vector3 center, Vector3 size, Material m, bool shadows = true)
        {
            var g = GameObject.CreatePrimitive(PrimitiveType.Cube);
            g.name = name; g.transform.SetParent(root);
            g.transform.position = center; g.transform.localScale = size;
            var r = g.GetComponent<Renderer>(); r.sharedMaterial = m;
            r.shadowCastingMode = shadows ? ShadowCastingMode.On : ShadowCastingMode.Off;
            Object.DestroyImmediate(g.GetComponent<Collider>());
            return g;
        }

        // ---- stages -------------------------------------------------------------------------------------------------

        static void Studio(StageInfo s)
        {
            // Seamless cyclorama: floor fades into the background colour through fog; a soft floor tone under the actors.
            var m = Materials.Make(new Color(0.2f, 0.205f, 0.22f), Materials.Noise(new Color(0.92f, 0.92f, 0.92f), Color.white, 128, 4, 3), 0.25f);
            Ground(200, m, 8);
        }

        static void Void(StageInfo s)
        {
            var t = new Texture2D(64, 64, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Repeat, filterMode = FilterMode.Trilinear, anisoLevel = 8 };
            for (int y = 0; y < 64; y++) for (int x = 0; x < 64; x++) { float v = x < 1 || y < 1 ? 1f : 0.82f; t.SetPixel(x, y, new Color(v, v, v)); }
            t.Apply();
            Ground(120, Materials.Make(new Color(0.35f, 0.38f, 0.45f), t, 0.15f), 1);
        }

        static void Street(StageInfo s)
        {
            // Sidewalk plaza around the origin, a road along X beyond it, shopfronts on both sides.
            float bs = Scale("CityCommercial", "building-a", 3, 9.5f);
            float rs = Scale("CityRoads", "road-straight", 3, 7f);
            float ss = Scale("CitySuburban", "tree-large", 1, 5.5f);
            var concrete = Materials.Make(Color.white, Materials.Noise(new Color(0.30f, 0.30f, 0.31f), new Color(0.40f, 0.39f, 0.38f), 256, 10, 5), 0.12f);
            Ground(160, concrete, 3);
            var asphalt = Materials.Make(Color.white, Materials.Noise(new Color(0.12f, 0.12f, 0.13f), new Color(0.2f, 0.2f, 0.21f), 256, 24, 9), 0.3f);
            var road = Box("Road", new Vector3(0, -0.0f, 10.5f), new Vector3(160, 0.02f, 8f), asphalt);
            asphalt.SetTextureScale("_BaseMap", new Vector2(40, 2));
            var curb = Materials.Make(new Color(0.5f, 0.5f, 0.49f), null, 0.1f);
            Box("CurbA", new Vector3(0, 0.06f, 6.45f), new Vector3(160, 0.14f, 0.18f), curb);
            Box("CurbB", new Vector3(0, 0.06f, 14.55f), new Vector3(160, 0.14f, 0.18f), curb);
            var paint = Materials.Make(new Color(0.95f, 0.85f, 0.4f), null, 0.2f);
            for (float x = -78; x < 78; x += 4.5f) Box("Lane", new Vector3(x, 0.012f, 10.5f), new Vector3(2.2f, 0.01f, 0.15f), paint, false);
            var crossing = Materials.Make(new Color(0.92f, 0.92f, 0.9f), null, 0.2f);
            for (int i = 0; i < 9; i++) Box("Crossing", new Vector3(-9f, 0.012f, 7.1f + i * 0.85f), new Vector3(3.2f, 0.01f, 0.45f), crossing, false);
            road.GetComponent<Renderer>().shadowCastingMode = ShadowCastingMode.Off;

            string[] fronts = { "building-a", "building-b", "building-c", "building-d", "building-e", "building-f", "building-g", "building-h", "building-skyscraper-a", "building-skyscraper-b" };
            // Across the road (facing -Z) and behind the plaza (facing +Z).
            float x0 = -44;
            for (float x = x0; x < 44;)
            {
                var b = Prop("CityCommercial", fronts[rnd.Next(fronts.Length)], new Vector3(x, 0, 21f), 180, bs, 0);
                x += b ? Width(b) + 0.4f : 10;
            }
            for (float x = x0; x < 44;)
            {
                var b = Prop("CityCommercial", fronts[rnd.Next(fronts.Length)], new Vector3(x, 0, -16f), 0, bs, 0);
                x += b ? Width(b) + 0.4f : 10;
            }
            // Street furniture along the curb: lamps, trees, a traffic light, planters, awnings.
            for (float x = -40; x <= 40; x += 10)
            {
                var lamp = Prop("CityRoads", "light-curved", new Vector3(x, 0, 5.9f), 0, rs, 1.0f);
                if (lamp) s.lamps.Add(new Vector3(x, 5.6f, 6.9f));
                Prop("CitySuburban", rnd.NextDouble() < 0.5 ? "tree-large" : "tree-small", new Vector3(x + 5, 0, 5.2f), R(0, 360), ss, 1.3f);
            }
            Prop("CityRoads", "traffic-light", new Vector3(-11.5f, 0, 6.2f), 0, rs, 1.0f);
            for (int i = 0; i < 6; i++) Prop("CitySuburban", "planter", new Vector3(R(-16, 16), 0, R(-12, -9)), R(0, 360), ss, 1.5f);
            Prop("CityRoads", "dumpster", new Vector3(14, 0, -11.5f), 0, rs, 1.5f);
            for (int i = 0; i < 4; i++)
            {
                float x = -20 + i * 13;
                s.lamps.Add(new Vector3(x, 3.2f, -12.8f)); // shop window glow on the near side
            }
            s.area = new Bounds(new Vector3(0, 1.5f, -2f), new Vector3(30, 3, 16));
        }

        static float Width(GameObject go)
        {
            var rs = go.GetComponentsInChildren<Renderer>();
            var b = rs[0].bounds; foreach (var r in rs) b.Encapsulate(r.bounds);
            return b.size.x;
        }

        static void Interior(StageInfo s)
        {
            // A warm living room / loft, 11 x 11 m, walls with windows, furniture along the walls, the centre left free.
            float fs = Scale("Furniture", "doorway", 1, 2.25f);
            float W = 5.5f, D = 5.5f, H = 2.9f;
            var floorTex = Materials.Noise(new Color(0.42f, 0.27f, 0.16f), new Color(0.6f, 0.4f, 0.24f), 256, 6, 11, 0.85f);
            var floor = Materials.Make(Color.white, floorTex, 0.42f);
            var g = Ground(2 * W + 0.2f, floor, 1.6f);
            var plaster = Materials.Make(new Color(0.86f, 0.8f, 0.72f), Materials.Noise(new Color(0.94f, 0.94f, 0.94f), Color.white, 128, 12, 4), 0.08f);
            var accent = Materials.Make(new Color(0.32f, 0.42f, 0.4f), null, 0.1f);
            var trim = Materials.Make(new Color(0.95f, 0.93f, 0.9f), null, 0.3f);
            var glass = Materials.Emissive(new Color(0.85f, 0.92f, 1f), 1.6f);
            void Wall(string n, Vector3 c, Vector3 size, Vector3 inward, Material m)
            {
                var w = Box(n, c, size, m, false);
                s.walls.Add((w.GetComponent<Renderer>(), c, inward));
            }
            Wall("WallBack", new Vector3(0, H / 2, D), new Vector3(2 * W, H, 0.2f), Vector3.back, plaster);
            Wall("WallFront", new Vector3(0, H / 2, -D), new Vector3(2 * W, H, 0.2f), Vector3.forward, plaster);
            Wall("WallLeft", new Vector3(-W, H / 2, 0), new Vector3(0.2f, H, 2 * D), Vector3.right, accent);
            Wall("WallRight", new Vector3(W, H / 2, 0), new Vector3(0.2f, H, 2 * D), Vector3.left, plaster);
            // Windows on the back and right walls (bright panes + frames), they read as daylight outside.
            foreach (var x in new[] { -3f, 0f, 3f })
            {
                var pane = Box("Window", new Vector3(x, 1.6f, D - 0.11f), new Vector3(1.6f, 1.5f, 0.02f), glass, false);
                s.walls.Add((pane.GetComponent<Renderer>(), new Vector3(x, 1.6f, D), Vector3.back));
                foreach (var dx in new[] { -0.82f, 0f, 0.82f })
                {
                    var f = Box("Frame", new Vector3(x + dx, 1.6f, D - 0.13f), new Vector3(0.06f, 1.56f, 0.04f), trim, false);
                    s.walls.Add((f.GetComponent<Renderer>(), new Vector3(x, 1.6f, D), Vector3.back));
                }
            }
            var ceil = Box("Ceiling", new Vector3(0, H + 0.05f, 0), new Vector3(2 * W, 0.1f, 2 * D), trim, false);
            s.ceiling.Add(ceil.GetComponent<Renderer>());
            // Skirting boards.
            foreach (var (c, sz, n) in new[] { (new Vector3(0, 0.06f, D - 0.12f), new Vector3(2 * W, 0.12f, 0.04f), Vector3.back), (new Vector3(-W + 0.12f, 0.06f, 0), new Vector3(0.04f, 0.12f, 2 * D), Vector3.right), (new Vector3(W - 0.12f, 0.06f, 0), new Vector3(0.04f, 0.12f, 2 * D), Vector3.left), (new Vector3(0, 0.06f, -D + 0.12f), new Vector3(2 * W, 0.12f, 0.04f), Vector3.forward) })
            {
                var b = Box("Skirting", c, sz, trim, false);
                s.walls.Add((b.GetComponent<Renderer>(), c, n));
            }

            // Lounge corner (back-left), kitchen bar (right), bookcases (left wall), plants and lamps.
            Prop("Furniture", "rugRectangle", new Vector3(-2.6f, 0, 2.6f), 0, fs * 1.5f, 0.6f);
            Prop("Furniture", "loungeSofaLong", new Vector3(-2.6f, 0, 4.5f), 180, fs, 1.0f);
            Prop("Furniture", "tableCoffee", new Vector3(-2.6f, 0, 3.0f), 0, fs, 0.9f);
            Prop("Furniture", "loungeChair", new Vector3(-4.3f, 0, 2.4f), 100, fs, 0.9f);
            Prop("Furniture", "pillowBlue", new Vector3(-2.9f, 0.45f, 4.6f), 10, fs, 0);
            var l1 = Prop("Furniture", "lampRoundFloor", new Vector3(-4.6f, 0, 4.6f), 0, fs, 0.6f);
            if (l1) s.lamps.Add(new Vector3(-4.6f, 1.6f, 4.6f));
            Prop("Furniture", "bookcaseOpen", new Vector3(-W + 0.35f, 0, -1.5f), 90, fs, 0.8f);
            Prop("Furniture", "bookcaseClosedWide", new Vector3(-W + 0.35f, 0, -3.4f), 90, fs, 0.8f);
            Prop("Furniture", "pottedPlant", new Vector3(-4.8f, 0, -4.8f), 0, fs * 1.3f, 0.6f);
            Prop("Furniture", "pottedPlant", new Vector3(4.8f, 0, 4.8f), 30, fs * 1.3f, 0.6f);
            Prop("Furniture", "kitchenBar", new Vector3(3.6f, 0, -0.6f), 90, fs, 1.0f);
            Prop("Furniture", "kitchenBar", new Vector3(3.6f, 0, -1.7f), 90, fs, 1.0f);
            Prop("Furniture", "stoolBar", new Vector3(2.7f, 0, -0.5f), 0, fs, 0.6f);
            Prop("Furniture", "stoolBar", new Vector3(2.7f, 0, -1.6f), 0, fs, 0.6f);
            Prop("Furniture", "kitchenCabinet", new Vector3(W - 0.35f, 0, -3.6f), -90, fs, 0.8f);
            Prop("Furniture", "kitchenFridgeLarge", new Vector3(W - 0.45f, 0, -4.8f), -90, fs, 0.8f);
            Prop("Furniture", "cabinetTelevision", new Vector3(2.4f, 0, D - 0.4f), 180, fs, 0.8f);
            Prop("Furniture", "televisionModern", new Vector3(2.4f, 0.5f, D - 0.4f), 180, fs, 0);
            Prop("Furniture", "tableRound", new Vector3(2.6f, 0, 2.4f), 0, fs, 1.0f);
            Prop("Furniture", "chair", new Vector3(2.0f, 0, 2.4f), 90, fs, 0.6f);
            Prop("Furniture", "chair", new Vector3(3.2f, 0, 2.4f), -90, fs, 0.6f);
            var l2 = Prop("Furniture", "lampSquareTable", new Vector3(2.6f, 0.75f, 2.4f), 0, fs, 0);
            if (l2) s.lamps.Add(new Vector3(2.6f, 1.3f, 2.4f));
            s.lamps.Add(new Vector3(0, H - 0.3f, 0));          // ceiling pendant
            s.lamps.Add(new Vector3(-2.5f, H - 0.3f, -3f));
            s.area = new Bounds(new Vector3(0, 1.4f, 0), new Vector3(2 * W - 1, 2.8f, 2 * D - 1));
        }

        static void Park(StageInfo s)
        {
            float ns = Scale("Nature", "tree_oak", 1, 7.5f);
            var grassTex = Materials.Noise(new Color(0.12f, 0.22f, 0.07f), new Color(0.24f, 0.34f, 0.12f), 256, 14, 21);
            Ground(220, Materials.Make(Color.white, grassTex, 0.08f), 5);
            // A gravel path crossing the clearing, with a bench and a lamp beside it.
            var gravel = Materials.Make(Color.white, Materials.Noise(new Color(0.38f, 0.34f, 0.28f), new Color(0.5f, 0.46f, 0.38f), 256, 30, 23), 0.1f);
            var path = Box("Path", new Vector3(0, 0.005f, 0), new Vector3(2.4f, 0.01f, 90f), gravel, false);
            gravel.SetTextureScale("_BaseMap", new Vector2(1, 36));
            path.transform.rotation = Quaternion.Euler(0, 62, 0);
            float fs = Scale("Furniture", "doorway", 1, 2.25f);
            Prop("Furniture", "bench", new Vector3(-3.2f, 0, 3.6f), 152, fs * 1.2f, 1.2f);
            var lamp = Prop("CityRoads", "light-square", new Vector3(3.8f, 0, -3.8f), 0, Scale("CityRoads", "road-straight", 3, 7f) * 0.8f, 1.0f);
            if (lamp) s.lamps.Add(new Vector3(3.8f, 4.0f, -3.8f));
            string[] trees = { "tree_oak", "tree_default", "tree_detailed", "tree_fat", "tree_tall", "tree_oak_dark", "tree_default_dark" };
            for (int i = 0; i < 70; i++)
            {
                float a = R(0, 360) * Mathf.Deg2Rad, r = R(8.5f, 38f);
                var p = new Vector3(Mathf.Cos(a) * r, 0, Mathf.Sin(a) * r);
                if (Mathf.Abs(Vector3.Dot(p, new Vector3(Mathf.Cos(-62 * Mathf.Deg2Rad), 0, Mathf.Sin(-62 * Mathf.Deg2Rad)))) < 2.5f) continue; // keep the path open
                Prop("Nature", trees[rnd.Next(trees.Length)], p, R(0, 360), ns * R(0.8f, 1.25f), 2.5f);
            }
            string[] small = { "plant_bush", "plant_bushLarge", "plant_bushDetailed", "rock_smallA", "rock_smallC", "rock_largeA", "stump_round", "log", "flower_redA", "flower_yellowB", "flower_purpleA", "grass_large", "grass", "grass_leafs" };
            for (int i = 0; i < 160; i++)
            {
                float a = R(0, 360) * Mathf.Deg2Rad, r = R(3.5f, 26f);
                var p = new Vector3(Mathf.Cos(a) * r, 0, Mathf.Sin(a) * r);
                string m = small[rnd.Next(small.Length)];
                float sc = m.StartsWith("grass") || m.StartsWith("flower") ? ns * 1.4f : ns;
                Prop("Nature", m, p, R(0, 360), sc * R(0.8f, 1.3f), 1.4f);
            }
            s.area = new Bounds(new Vector3(0, 1.5f, 0), new Vector3(16, 3, 16));
        }
    }
}
