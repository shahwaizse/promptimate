// Shared helpers for FidelityStudio: HDRP materials, lights, volumes, cameras, asset loading, frame capture.
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

namespace Fidelity
{
    public static class Lib
    {
        public const string TP = "Assets/ThirdParty/";
        public const string PHM = TP + "PolyHaven/Models/";
        public const string PHT = TP + "PolyHaven/Textures/";
        public static readonly string Root = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", ".."));

        // ---------------------------------------------------------------- materials
        static readonly Dictionary<string, Material> cache = new Dictionary<string, Material>();
        public static void ResetCache() => cache.Clear();

        public static Material Lit(Color c, float smooth = 0.4f, float metal = 0f)
        {
            string key = $"lit_{c}_{smooth}_{metal}";
            if (cache.TryGetValue(key, out var m) && m) return m;
            m = new Material(Shader.Find("HDRP/Lit")) { name = key };
            m.SetColor("_BaseColor", c);
            m.SetFloat("_Smoothness", smooth);
            m.SetFloat("_Metallic", metal);
            HDMaterial.ValidateMaterial(m);
            return cache[key] = m;
        }

        /// PBR material from a Poly Haven texture set (diffuse, GL normal, HDRP mask map made by fetch_assets.py).
        public static Material Surface(string id, float tiling = 1f, Color? tint = null, float smoothScale = 1f, float normalScale = 1f)
        {
            string key = $"surf_{id}_{tiling}_{tint}_{smoothScale}_{normalScale}";
            if (cache.TryGetValue(key, out var m) && m) return m;
            string dir = PHT + id + "/";
            Texture2D T(string part) => Directory.GetFiles(dir, "*" + part + "*").Where(f => !f.EndsWith(".meta")).Select(f => AssetDatabase.LoadAssetAtPath<Texture2D>(f.Replace('\\', '/'))).FirstOrDefault(t => t);
            m = new Material(Shader.Find("HDRP/Lit")) { name = key };
            var diff = T("_diff_"); var nor = T("_nor_gl_"); var mask = T("_mask_");
            if (diff) m.SetTexture("_BaseColorMap", diff);
            m.SetColor("_BaseColor", tint ?? Color.white);
            if (nor) { m.SetTexture("_NormalMap", nor); m.SetFloat("_NormalScale", normalScale); }
            if (mask)
            {
                m.SetTexture("_MaskMap", mask);
                m.SetFloat("_SmoothnessRemapMin", 0); m.SetFloat("_SmoothnessRemapMax", smoothScale);
                m.SetFloat("_AORemapMin", 0); m.SetFloat("_AORemapMax", 1);
                m.SetFloat("_MetallicRemapMin", 0); m.SetFloat("_MetallicRemapMax", 1);
            }
            m.SetTextureScale("_BaseColorMap", Vector2.one * tiling);
            HDMaterial.ValidateMaterial(m);
            return cache[key] = m;
        }

        public static Material Emissive(Color c, float nits)
        {
            string key = $"emis_{c}_{nits}";
            if (cache.TryGetValue(key, out var m) && m) return m;
            m = new Material(Shader.Find("HDRP/Unlit")) { name = key };
            m.SetColor("_UnlitColor", c * nits);
            HDMaterial.ValidateMaterial(m);
            return cache[key] = m;
        }

        // ---------------------------------------------------------------- geometry
        public static GameObject Box(string name, Vector3 center, Vector3 size, Material m, Transform parent = null, float uvScale = 0)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            go.name = name;
            Object.DestroyImmediate(go.GetComponent<Collider>());
            go.transform.SetParent(parent, false);
            go.transform.localPosition = center; go.transform.localScale = size;
            go.GetComponent<MeshRenderer>().sharedMaterial = m;
            if (uvScale > 0) WorldUV(go, uvScale);
            go.AddComponent<BoxCollider>();
            return go;
        }

        /// Replaces a scaled cube's UVs with world-size UVs (uvScale metres per texture repeat), so tiling textures keep
        /// their real-world size on walls of any size.
        public static void WorldUV(GameObject go, float metresPerTile)
        {
            var mf = go.GetComponent<MeshFilter>();
            var mesh = Object.Instantiate(mf.sharedMesh);
            var s = go.transform.lossyScale;
            var v = mesh.vertices; var n = mesh.normals; var uv = new Vector2[v.Length];
            for (int i = 0; i < v.Length; i++)
            {
                var p = Vector3.Scale(v[i], s);
                var a = new Vector3(Mathf.Abs(n[i].x), Mathf.Abs(n[i].y), Mathf.Abs(n[i].z));
                uv[i] = a.x > 0.5f ? new Vector2(p.z, p.y) : a.y > 0.5f ? new Vector2(p.x, p.z) : new Vector2(p.x, p.y);
                uv[i] /= metresPerTile;
            }
            mesh.uv = uv;
            mesh.RecalculateTangents();
            mf.sharedMesh = mesh;
        }

        /// Instantiates a Poly Haven glTF model (imported by glTFast) at a position/yaw, optionally scaled to a target
        /// size along its largest horizontal axis or its height.
        public static GameObject Model(string id, Vector3 pos, float yaw, Transform parent = null, float scale = 1f)
        {
            var dir = PHM + id + "/";
            var file = Directory.GetFiles(dir, "*.gltf").FirstOrDefault();
            if (file == null) throw new System.Exception("missing model " + id);
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(file.Replace('\\', '/'));
            if (prefab == null) throw new System.Exception("model not imported " + file);
            var go = (GameObject)Object.Instantiate(prefab);
            go.name = id;
            go.transform.SetParent(parent, false);
            go.transform.localPosition = pos; go.transform.localRotation = Quaternion.Euler(0, yaw, 0);
            go.transform.localScale = Vector3.one * scale;
            GltfMaterials(go, file.Replace(System.IO.Path.DirectorySeparatorChar, '/'));
            foreach (var r in go.GetComponentsInChildren<Renderer>()) { r.shadowCastingMode = ShadowCastingMode.On; r.rayTracingMode = UnityEngine.Experimental.Rendering.RayTracingMode.Static; }
            return go;
        }

        // glTFast's HDRP shader graphs don't render here (and aren't path traced), so every glTF material is rebuilt
        // as HDRP/Lit from the glTF JSON: base colour, normal, and the HDRP mask map fetch_assets.py makes from ARM.
        [System.Serializable] class GTexRef { public int index = -1; public float scale = 1; }
        [System.Serializable] class GPbr { public float[] baseColorFactor; public GTexRef baseColorTexture = new GTexRef(); public GTexRef metallicRoughnessTexture = new GTexRef(); public float metallicFactor = 1, roughnessFactor = 1; }
        [System.Serializable] class GMat { public string name; public GPbr pbrMetallicRoughness = new GPbr(); public GTexRef normalTexture = new GTexRef(); public string alphaMode; public float alphaCutoff = 0.5f; public bool doubleSided; }
        [System.Serializable] class GTex { public int source = -1; }
        [System.Serializable] class GImg { public string uri; }
        [System.Serializable] class GDoc { public GMat[] materials = new GMat[0]; public GTex[] textures = new GTex[0]; public GImg[] images = new GImg[0]; }
        static readonly Dictionary<string, GDoc> docs = new Dictionary<string, GDoc>();

        static void GltfMaterials(GameObject go, string gltfPath)
        {
            if (!docs.TryGetValue(gltfPath, out var doc)) docs[gltfPath] = doc = JsonUtility.FromJson<GDoc>(File.ReadAllText(gltfPath));
            string dir = Path.GetDirectoryName(gltfPath).Replace(Path.DirectorySeparatorChar, '/') + "/";
            Texture2D Img(GTexRef r, string swapFrom = null, string swapTo = null)
            {
                if (r == null || r.index < 0 || r.index >= doc.textures.Length) return null;
                int src = doc.textures[r.index].source;
                if (src < 0 || src >= doc.images.Length) return null;
                var uri = System.Uri.UnescapeDataString(doc.images[src].uri);
                if (swapFrom != null) uri = Path.ChangeExtension(uri.Replace(swapFrom, swapTo), ".png");
                return AssetDatabase.LoadAssetAtPath<Texture2D>(dir + uri);
            }
            foreach (var r in go.GetComponentsInChildren<Renderer>())
            {
                var mats = r.sharedMaterials;
                for (int i = 0; i < mats.Length; i++)
                {
                    var name = mats[i] ? mats[i].name.Replace(" (Instance)", "") : "";
                    var gm = doc.materials.FirstOrDefault(x => x.name == name) ?? (doc.materials.Length == 1 ? doc.materials[0] : null);
                    if (gm == null) { Debug.LogWarning($"FID_MAT no glTF material '{name}' in {gltfPath}"); continue; }
                    string key = gltfPath + "|" + gm.name;
                    if (!cache.TryGetValue(key, out var m) || !m)
                    {
                        m = new Material(Shader.Find("HDRP/Lit")) { name = "ph_" + gm.name };
                        var pbr = gm.pbrMetallicRoughness ?? new GPbr();
                        var bc = pbr.baseColorFactor != null && pbr.baseColorFactor.Length >= 3 ? new Color(pbr.baseColorFactor[0], pbr.baseColorFactor[1], pbr.baseColorFactor[2], pbr.baseColorFactor.Length > 3 ? pbr.baseColorFactor[3] : 1) : Color.white;
                        m.SetColor("_BaseColor", bc);
                        var bt = Img(pbr.baseColorTexture); if (bt) m.SetTexture("_BaseColorMap", bt);
                        var nt = Img(gm.normalTexture); if (nt) { m.SetTexture("_NormalMap", nt); m.SetFloat("_NormalScale", gm.normalTexture.scale); }
                        var mk = Img(pbr.metallicRoughnessTexture, "_arm_", "_mask_");
                        if (mk)
                        {
                            m.SetTexture("_MaskMap", mk);
                            m.SetFloat("_MetallicRemapMin", 0); m.SetFloat("_MetallicRemapMax", pbr.metallicFactor);
                            m.SetFloat("_SmoothnessRemapMin", 1 - Mathf.Min(1, pbr.roughnessFactor)); m.SetFloat("_SmoothnessRemapMax", 1);
                            m.SetFloat("_AORemapMin", 0); m.SetFloat("_AORemapMax", 1);
                        }
                        else { m.SetFloat("_Metallic", pbr.metallicFactor); m.SetFloat("_Smoothness", 1 - pbr.roughnessFactor); }
                        if (gm.alphaMode == "MASK" || gm.alphaMode == "BLEND") { m.SetFloat("_AlphaCutoffEnable", 1); m.SetFloat("_AlphaCutoff", gm.alphaMode == "MASK" ? gm.alphaCutoff : 0.5f); }
                        if (gm.doubleSided || gm.alphaMode != null) m.SetFloat("_DoubleSidedEnable", 1);
                        if (gm.name.ToLowerInvariant().Contains("glass"))
                        {   // thin picture glass: transparent with a faint reflection
                            m.SetFloat("_SurfaceType", 1); m.SetFloat("_BlendMode", 0);
                            m.SetColor("_BaseColor", new Color(1, 1, 1, 0.06f)); m.SetTexture("_BaseColorMap", null);
                            m.SetTexture("_MaskMap", null); m.SetFloat("_Smoothness", 0.95f); m.SetFloat("_Metallic", 0);
                        }
                        HDMaterial.ValidateMaterial(m);
                        cache[key] = m;
                    }
                    mats[i] = m;
                }
                r.sharedMaterials = mats;
            }
        }

        public static Bounds WorldBounds(GameObject go)
        {
            var rs = go.GetComponentsInChildren<Renderer>();
            if (rs.Length == 0) return new Bounds(go.transform.position, Vector3.zero);
            var b = rs[0].bounds; foreach (var r in rs) b.Encapsulate(r.bounds); return b;
        }

        // ---------------------------------------------------------------- lights
        public static Light Sun(Vector3 dirTowardScene, float lux, float kelvin, float angularDiameter = 0.53f)
        {
            var go = new GameObject("Sun");
            var l = go.AddComponent<Light>();
            var hd = go.GetComponent<HDAdditionalLightData>() ?? go.AddComponent<HDAdditionalLightData>();
            l.type = LightType.Directional;
            l.lightUnit = LightUnit.Lux;
            l.intensity = lux;
            l.useColorTemperature = true; l.colorTemperature = kelvin; l.color = Color.white;
            l.shadows = LightShadows.Soft;
            hd.angularDiameter = angularDiameter;
            hd.SetShadowResolution(4096);
            go.transform.rotation = Quaternion.LookRotation(dirTowardScene.normalized);
            return l;
        }

        public static Light Point(Vector3 pos, float lumen, float kelvin, float range = 8f, float radius = 0.05f, bool shadows = true)
        {
            var go = new GameObject("Point");
            var l = go.AddComponent<Light>();
            var hd = go.GetComponent<HDAdditionalLightData>() ?? go.AddComponent<HDAdditionalLightData>();
            l.type = LightType.Point; l.lightUnit = LightUnit.Lumen; l.intensity = lumen; l.range = range;
            l.useColorTemperature = true; l.colorTemperature = kelvin; l.color = Color.white;
            l.shadows = shadows ? LightShadows.Soft : LightShadows.None;
            hd.shapeRadius = radius;
            go.transform.position = pos;
            return l;
        }

        /// Rectangular area light (soft window fill / bounce cards). Faces along its +Z.
        public static Light Area(Vector3 pos, Quaternion rot, Vector2 size, float lumen, float kelvin, Color? tint = null)
        {
            var go = new GameObject("Area");
            var l = go.AddComponent<Light>();
            var hd = go.GetComponent<HDAdditionalLightData>() ?? go.AddComponent<HDAdditionalLightData>();
            l.type = LightType.Rectangle; l.lightUnit = LightUnit.Lumen; l.intensity = lumen;
            l.useColorTemperature = true; l.colorTemperature = kelvin; l.color = tint ?? Color.white;
            l.areaSize = size; hd.shapeWidth = size.x; hd.shapeHeight = size.y;
            l.shadows = LightShadows.Soft;
            l.range = 12;
            go.transform.SetPositionAndRotation(pos, rot);
            return l;
        }

        // ---------------------------------------------------------------- environment
        public static Cubemap HDRI(string file)
        {
            var path = TP + "PolyHaven/HDRI/" + file;
            var imp = AssetImporter.GetAtPath(path) as TextureImporter;
            if (imp != null && imp.textureShape != TextureImporterShape.TextureCube)
            {
                imp.textureShape = TextureImporterShape.TextureCube;
                imp.generateCubemap = TextureImporterGenerateCubemap.AutoCubemap;
                imp.maxTextureSize = 4096;
                imp.textureCompression = TextureImporterCompression.CompressedHQ;
                imp.mipmapEnabled = true;
                imp.SaveAndReimport();
            }
            return AssetDatabase.LoadAssetAtPath<Cubemap>(path);
        }

        public static T Add<T>(VolumeProfile p) where T : VolumeComponent
        {
            var c = p.Add<T>(true);
            return c;
        }

        // ---------------------------------------------------------------- capture
        public static RenderTexture Target(int w, int h)
        {
            var rt = new RenderTexture(w, h, 24, RenderTextureFormat.ARGBHalf) { name = "fid_rt" };
            rt.Create();
            return rt;
        }

        /// Reads the camera target (already tonemapped by HDRP; ARGBHalf holds display-referred values) into 8-bit sRGB.
        public static byte[] Read(RenderTexture rt, Texture2D tex)
        {
            var tmp = RenderTexture.GetTemporary(rt.width, rt.height, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            Graphics.Blit(rt, tmp);
            var prev = RenderTexture.active; RenderTexture.active = tmp;
            tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
            RenderTexture.active = prev; RenderTexture.ReleaseTemporary(tmp);
            return tex.GetRawTextureData<byte>().ToArray();
        }

        public static void SavePng(RenderTexture rt, string file)
        {
            var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
            var raw = Read(rt, tex);
            Directory.CreateDirectory(Path.GetDirectoryName(file));
            File.WriteAllBytes(file, ImageConversion.EncodeArrayToPNG(raw, UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8B8_SRGB, (uint)rt.width, (uint)rt.height));
            Object.DestroyImmediate(tex);
        }

        public static string Arg(string name, string def = null)
        {
            var a = System.Environment.GetCommandLineArgs();
            int i = System.Array.IndexOf(a, name);
            return i >= 0 && i + 1 < a.Length ? a[i + 1] : def;
        }
    }
}
