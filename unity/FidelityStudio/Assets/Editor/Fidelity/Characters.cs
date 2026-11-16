// Microsoft Rocketbox avatars (MIT) as HDRP characters: Humanoid rig, HDRP Lit materials rebuilt from the avatar's
// colour/normal/specular textures, subsurface-scattering skin, alpha-clipped hair and lashes, blinks via blendshapes.
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

namespace Fidelity
{
    public static class Characters
    {
        const string RB = Lib.TP + "Rocketbox/";

        public static GameObject Spawn(string id, Vector3 pos, float yaw, float height)
        {
            var dir = RB + id + "/";
            var fbx = Directory.GetFiles(dir + "Export", "*.fbx").First().Replace('\\', '/');
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(fbx) ?? throw new System.Exception("missing " + fbx);
            var go = (GameObject)Object.Instantiate(prefab);
            go.name = id;
            var anim = go.GetComponent<Animator>() ?? go.AddComponent<Animator>();
            if (anim.avatar == null) anim.avatar = AssetDatabase.LoadAllAssetsAtPath(fbx).OfType<Avatar>().FirstOrDefault();
            anim.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            go.transform.SetPositionAndRotation(pos, Quaternion.Euler(0, yaw, 0));
            // Scale to the wanted standing height (bind pose head top).
            var head = anim.GetBoneTransform(HumanBodyBones.Head);
            var b = Lib.WorldBounds(go);
            float h = b.max.y - pos.y;
            if (h > 0.5f) go.transform.localScale *= height / h;
            Materials(go, dir + "Textures/");
            foreach (var smr in go.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                smr.updateWhenOffscreen = true;
                smr.forceMatrixRecalculationPerRender = true; // bone edits after the animation pass (IK, seat) must be skinned
                smr.rayTracingMode = UnityEngine.Experimental.Rendering.RayTracingMode.DynamicGeometry;
                smr.shadowCastingMode = ShadowCastingMode.On;
                smr.skinnedMotionVectors = true;
                smr.quality = SkinQuality.Bone4;
            }
            return go;
        }

        static Texture2D Tex(string dir, string part)
        {
            var f = Directory.GetFiles(dir).FirstOrDefault(x => !x.EndsWith(".meta") && Path.GetFileName(x).ToLowerInvariant().Contains(part));
            return f == null ? null : AssetDatabase.LoadAssetAtPath<Texture2D>(f.Replace('\\', '/'));
        }

        static DiffusionProfileSettings _skin;
        static DiffusionProfileSettings Skin()
        {
            if (_skin) return _skin;
            // HDRP ships a Skin diffusion profile; it must also be listed in the global settings to be used.
            var guid = AssetDatabase.FindAssets("SkinDiffusionProfile t:DiffusionProfileSettings").FirstOrDefault() ?? AssetDatabase.FindAssets("Skin t:DiffusionProfileSettings").FirstOrDefault();
            _skin = guid != null ? AssetDatabase.LoadAssetAtPath<DiffusionProfileSettings>(AssetDatabase.GUIDToAssetPath(guid)) : null;
            return _skin;
        }

        static readonly Dictionary<string, Material> made = new Dictionary<string, Material>();

        static void Materials(GameObject go, string texDir)
        {
            foreach (var r in go.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                var mats = r.sharedMaterials;
                for (int i = 0; i < mats.Length; i++)
                {
                    string n = (mats[i] ? mats[i].name : "").ToLowerInvariant();
                    string key = texDir + "|" + n;
                    if (made.TryGetValue(key, out var mm) && mm) { mats[i] = mm; continue; }
                    Material m;
                    if (n.Contains("opacity") || n.Contains("hair") || n.Contains("lash"))
                    {
                        m = new Material(Shader.Find("HDRP/Lit")) { name = "rb_" + n };
                        var t = Tex(texDir, "opacity_color");
                        if (t) m.SetTexture("_BaseColorMap", t);
                        m.SetFloat("_AlphaCutoffEnable", 1); m.SetFloat("_AlphaCutoff", 0.45f);
                        m.SetFloat("_DoubleSidedEnable", 1);
                        m.SetFloat("_Smoothness", 0.45f);
                    }
                    else
                    {
                        bool head = n.Contains("head");
                        string part = head ? "head" : "body";
                        m = new Material(Shader.Find("HDRP/Lit")) { name = "rb_" + n };
                        var c = Tex(texDir, part + "_color"); var nn = Tex(texDir, part + "_normal.");
                        if (nn == null) nn = Tex(texDir, part + "_normal");
                        if (c) m.SetTexture("_BaseColorMap", c);
                        if (nn) { m.SetTexture("_NormalMap", nn); m.SetFloat("_NormalScale", 1f); }
                        m.SetFloat("_Smoothness", head ? 0.36f : 0.28f);
                        if (head && Skin() != null && System.Environment.GetEnvironmentVariable("FID_SSS") == "1")
                        {
                            m = Persist(m, texDir, n);
                            m.SetFloat("_MaterialID", 0); // subsurface scattering
                            HDMaterial.SetDiffusionProfile(m, Skin());
                            m.SetFloat("_SubsurfaceMask", 1f);
                        }
                    }
                    HDMaterial.ValidateMaterial(m);
                    made[key] = m; mats[i] = m;
                }
                r.sharedMaterials = mats;
            }
        }

        /// Materials that carry a diffusion profile must be assets (HDRP stores the profile reference as a sub-asset).
        static Material Persist(Material m, string texDir, string n)
        {
            const string dir = "Assets/Fidelity/Generated/Materials";
            if (!AssetDatabase.IsValidFolder("Assets/Fidelity/Generated/Materials")) AssetDatabase.CreateFolder("Assets/Fidelity/Generated", "Materials");
            var path = $"{dir}/{Path.GetFileName(texDir.TrimEnd('/'))}_{Path.GetFileName(Path.GetDirectoryName(texDir.TrimEnd('/')))}_{n}.mat".Replace(" ", "_");
            var old = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (old != null) AssetDatabase.DeleteAsset(path);
            AssetDatabase.CreateAsset(m, path);
            return m;
        }

        /// Blink weights for a time t (deterministic per seed): ~every 3-5 s, 150 ms closing+opening.
        public static float Blink(float t, int seed)
        {
            var rng = new System.Random(seed);
            float at = 0.6f + (float)rng.NextDouble() * 1.5f;
            while (at < t + 1)
            {
                float d = t - at;
                if (d >= 0 && d < 0.16f) return Mathf.Sin(d / 0.16f * Mathf.PI);
                at += 2.8f + (float)rng.NextDouble() * 2.6f;
            }
            return 0;
        }

        public static void ApplyBlink(GameObject go, float w)
        {
            foreach (var smr in go.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                var m = smr.sharedMesh; if (m == null) continue;
                for (int i = 0; i < m.blendShapeCount; i++)
                {
                    var n = m.GetBlendShapeName(i).ToLowerInvariant();
                    if (n.Contains("blink") || n.Contains("eyeclose") || n.Contains("eyes_closed") || n.Contains("eyesclosed")) smr.SetBlendShapeWeight(i, w * 100);
                }
            }
        }
    }
}
