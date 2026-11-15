// Small procedural props that the CC0 libraries don't have (ashtray, rugs, papers, paintings, crates, signs).
using UnityEngine;
using UnityEngine.Rendering;

namespace WorldLab
{
    public static class Procedural
    {
        public static GameObject Make(ItemSpec it, Transform parent)
        {
            var root = new GameObject(it.id);
            root.transform.SetParent(parent, false);
            var size = it.size != null && it.size.Length >= 3 ? WorldBuilder.V(it.size) : new Vector3(0.3f, 0.3f, 0.3f);
            var col = WorldBuilder.C(it.color, new Color(0.5f, 0.5f, 0.5f));
            switch (it.proc)
            {
                case "ashtray":
                {
                    var glass = ShotStudio.Materials.Make(new Color(0.18f, 0.2f, 0.22f), null, 0.85f, 0.2f);
                    Prim(PrimitiveType.Cylinder, root, new Vector3(0, size.y / 2, 0), new Vector3(size.x, size.y / 2, size.z), glass);
                    Prim(PrimitiveType.Cylinder, root, new Vector3(0, size.y + 0.0005f, 0), new Vector3(size.x * 0.75f, 0.001f, size.z * 0.75f), ShotStudio.Materials.Make(new Color(0.08f, 0.075f, 0.07f), null, 0.1f));
                    // a resting cigarette with a glowing tip
                    var cig = Prim(PrimitiveType.Cylinder, root, new Vector3(size.x * 0.3f, size.y + 0.006f, 0), new Vector3(0.008f, 0.04f, 0.008f), ShotStudio.Materials.Make(new Color(0.92f, 0.9f, 0.85f), null, 0.2f));
                    cig.transform.localRotation = Quaternion.Euler(0, 0, 80);
                    Prim(PrimitiveType.Sphere, root, new Vector3(size.x * 0.3f + 0.04f, size.y + 0.012f, 0), Vector3.one * 0.009f, ShotStudio.Materials.Emissive(new Color(1f, 0.35f, 0.08f), 8f));
                    break;
                }
                case "deskphone":
                {
                    // 1970s rotary desk phone: sloped body, dial, handset on its cradle (front = +Z)
                    var body = ShotStudio.Materials.Make(col == new Color(0.5f, 0.5f, 0.5f) ? new Color(0.06f, 0.055f, 0.05f) : col, null, 0.75f);
                    WorldBuilder.Box("PhoneBase", new Vector3(0, 0.03f, 0), new Vector3(size.x * 0.9f, 0.06f, size.z), Quaternion.identity, body, 1, root.transform);
                    WorldBuilder.Box("PhoneTop", new Vector3(0, 0.07f, -0.01f), new Vector3(size.x * 0.75f, 0.05f, size.z * 0.7f), Quaternion.Euler(-12, 0, 0), body, 1, root.transform);
                    var dial = Prim(PrimitiveType.Cylinder, root, new Vector3(0, 0.085f, 0.055f), new Vector3(0.085f, 0.004f, 0.085f), ShotStudio.Materials.Make(new Color(0.85f, 0.83f, 0.78f), null, 0.6f));
                    dial.transform.localRotation = Quaternion.Euler(-30, 0, 0);
                    var hs = Prim(PrimitiveType.Capsule, root, new Vector3(0, 0.115f, -0.02f), new Vector3(0.045f, 0.105f, 0.045f), body);
                    hs.transform.localRotation = Quaternion.Euler(0, 0, 90);
                    foreach (int sx in new[] { -1, 1 })
                        Prim(PrimitiveType.Sphere, root, new Vector3(sx * 0.085f, 0.112f, -0.02f), new Vector3(0.05f, 0.04f, 0.06f), body);
                    break;
                }
                case "rug":
                {
                    var m = WorldBuilder.Mat(it.mat, col, 0.05f);
                    if (it.color != null) { m = new Material(m); m.SetColor("_BaseColor", col); }
                    WorldBuilder.Box("Rug", new Vector3(0, 0.006f, 0), new Vector3(size.x, 0.012f, size.z), Quaternion.identity, m, 0.9f, root.transform);
                    var border = ShotStudio.Materials.Make(col * 0.45f, null, 0.05f);
                    float bw = Mathf.Min(size.x, size.z) * 0.06f;
                    foreach (var (c, s) in new[] { (new Vector3(0, 0.0065f, size.z / 2 - bw / 2), new Vector3(size.x, 0.013f, bw)), (new Vector3(0, 0.0065f, -size.z / 2 + bw / 2), new Vector3(size.x, 0.013f, bw)),
                                                   (new Vector3(size.x / 2 - bw / 2, 0.0065f, 0), new Vector3(bw, 0.013f, size.z)), (new Vector3(-size.x / 2 + bw / 2, 0.0065f, 0), new Vector3(bw, 0.013f, size.z)) })
                        WorldBuilder.Box("RugBorder", c, s, Quaternion.identity, border, 1, root.transform, false);
                    break;
                }
                case "paper":
                    WorldBuilder.Box("Paper", new Vector3(0, size.y / 2, 0), size, Quaternion.identity, ShotStudio.Materials.Make(new Color(0.9f, 0.88f, 0.8f), null, 0.1f), 1, root.transform, false);
                    break;
                case "painting":
                {
                    var frame = ShotStudio.Materials.Make(new Color(0.2f, 0.14f, 0.08f), null, 0.4f);
                    WorldBuilder.Box("Frame", new Vector3(0, 0, 0), size, Quaternion.identity, frame, 1, root.transform);
                    var art = ShotStudio.Materials.Make(Color.white, Painting(it.id.GetHashCode(), col), 0.15f);
                    var q = GameObject.CreatePrimitive(PrimitiveType.Quad);
                    Object.DestroyImmediate(q.GetComponent<Collider>());
                    q.transform.SetParent(root.transform, false);
                    q.transform.localPosition = new Vector3(0, 0, size.z / 2 + 0.001f);
                    q.transform.localRotation = Quaternion.Euler(0, 180, 0);
                    q.transform.localScale = new Vector3(size.x * 0.86f, size.y * 0.86f, 1);
                    q.GetComponent<Renderer>().sharedMaterial = art;
                    break;
                }
                case "sign":
                {
                    WorldBuilder.Box("SignBack", Vector3.zero, size, Quaternion.identity, ShotStudio.Materials.Make(new Color(0.08f, 0.08f, 0.09f), null, 0.4f), 1, root.transform);
                    var face = it.emissive > 0 ? ShotStudio.Materials.Emissive(col, it.emissive) : ShotStudio.Materials.Make(col, null, 0.4f);
                    WorldBuilder.Box("SignFace", new Vector3(0, 0, size.z / 2 + 0.002f), new Vector3(size.x * 0.92f, size.y * 0.7f, 0.004f), Quaternion.identity, face, 1, root.transform, false);
                    break;
                }
                case "cylinder":
                    Prim(PrimitiveType.Cylinder, root, new Vector3(0, size.y / 2, 0), new Vector3(size.x, size.y / 2, size.z), string.IsNullOrEmpty(it.mat) ? ShotStudio.Materials.Make(col, null, 0.3f) : WorldBuilder.Mat(it.mat, col));
                    break;
                default: // box / crate
                    WorldBuilder.Box("Box", new Vector3(0, size.y / 2, 0), size, Quaternion.identity, string.IsNullOrEmpty(it.mat) ? ShotStudio.Materials.Make(col, null, 0.3f) : WorldBuilder.Mat(it.mat, col), 1, root.transform);
                    break;
            }
            return root;
        }

        static GameObject Prim(PrimitiveType t, GameObject parent, Vector3 pos, Vector3 scale, Material m)
        {
            var g = GameObject.CreatePrimitive(t);
            Object.DestroyImmediate(g.GetComponent<Collider>());
            g.transform.SetParent(parent.transform, false);
            g.transform.localPosition = pos; g.transform.localScale = scale;
            var r = g.GetComponent<Renderer>(); r.sharedMaterial = m; r.shadowCastingMode = ShadowCastingMode.On;
            return g;
        }

        /// An abstract painting: layered soft colour fields from a palette around `baseCol` (deterministic per seed).
        static Texture2D Painting(int seed, Color baseCol)
        {
            const int W = 256, H = 192;
            var rnd = new System.Random(seed);
            var t = new Texture2D(W, H, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Clamp };
            Color.RGBToHSV(baseCol, out var h0, out var s0, out var v0);
            var pal = new Color[4];
            for (int i = 0; i < 4; i++) pal[i] = Color.HSVToRGB(Mathf.Repeat(h0 + (float)(rnd.NextDouble() - 0.5) * 0.35f, 1), Mathf.Clamp01(0.25f + (float)rnd.NextDouble() * 0.5f), Mathf.Clamp01(0.3f + (float)rnd.NextDouble() * 0.6f));
            float ox = (float)rnd.NextDouble() * 50, oy = (float)rnd.NextDouble() * 50, horizon = 0.3f + (float)rnd.NextDouble() * 0.4f;
            var px = new Color[W * H];
            for (int y = 0; y < H; y++)
                for (int x = 0; x < W; x++)
                {
                    float u = x / (float)W, v = y / (float)H;
                    float n = Mathf.PerlinNoise(ox + u * 3, oy + v * 3), n2 = Mathf.PerlinNoise(ox * 2 + u * 9, oy + v * 9);
                    var c = v > horizon + (n - 0.5f) * 0.15f ? Color.Lerp(pal[0], pal[1], v) : Color.Lerp(pal[2], pal[3], n);
                    c = Color.Lerp(c, c * (0.8f + n2 * 0.4f), 0.6f);
                    px[y * W + x] = c;
                }
            t.SetPixels(px); t.Apply(true);
            return t;
        }
    }
}
