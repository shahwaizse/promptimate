// Debug probe: hand height relative to head over time, for one clip on several characters.
//   -executeMethod Probe.Run -clip <Assets/...kimodo>
using System.Linq;
using UnityEditor;
using UnityEngine;

public static class Probe
{
    public static void Run()
    {
        var args = System.Environment.GetCommandLineArgs();
        string clipPath = args[System.Array.IndexOf(args, "-clip") + 1];
        AssetDatabase.Refresh();
        AssetDatabase.ImportAsset(clipPath, ImportAssetOptions.ForceUpdate);
        var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
        Debug.Log($"PROBE clip={clipPath} loaded={(clip != null)} length={clip?.length} human={clip?.humanMotion}");
        var b = AnimationUtility.GetCurveBindings(clip);
        foreach (var n in new[] { "Right Arm Down-Up", "Right Shoulder Down-Up", "Right Forearm Stretch", "Left Arm Down-Up" })
        {
            var bind = b.FirstOrDefault(x => x.propertyName == n);
            var c = AnimationUtility.GetEditorCurve(clip, bind);
            Debug.Log($"PROBE curve '{n}' found={(c != null)} " + (c == null ? "" : string.Join(" ", Enumerable.Range(0, 7).Select(i => c.Evaluate(i * clip.length / 6f).ToString("F2")))));
        }
        foreach (var m in new[] { "Assets/Characters/Mixamo/Ch24_nonPBR.fbx", "Assets/Characters/Mixamo/Erika Archer.fbx", "Assets/Characters/Kenney/characterMedium.fbx" })
        {
            var go = (GameObject)Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(m));
            var anim = go.GetComponent<Animator>();
            var hand = anim.GetBoneTransform(HumanBodyBones.RightHand); var head = anim.GetBoneTransform(HumanBodyBones.Head);
            var s = "";
            for (int i = 0; i <= 6; i++) { clip.SampleAnimation(go, i * clip.length / 6f); s += $" t{i * clip.length / 6f:F1}:{hand.position.y - head.position.y:F2}"; }
            Debug.Log($"PROBE {m.Split('/').Last()} handY-headY:{s}");
            Object.DestroyImmediate(go);
        }
        EditorApplication.Exit(0);
    }
}
