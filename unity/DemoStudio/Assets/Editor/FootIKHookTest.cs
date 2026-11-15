// Test for Promptimate's Animator Foot IK hook:  -executeMethod FootIKHookTest.Run
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

public static class FootIKHookTest
{
    public static void Run()
    {
        int fails = 0;
        void Check(bool ok, string what) { Debug.Log($"FOOTIK_TEST {(ok ? "OK  " : "FAIL")} {what}"); if (!ok) fails++; }
        try
        {
            AssetDatabase.Refresh();
            const string path = "Assets/Clips/FootIKHookTest.controller";
            AssetDatabase.DeleteAsset(path);
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>("Assets/Clips/Retarget/rt_walk.kimodo");
            var other = new AnimationClip { name = "plain" };
            AssetDatabase.CreateAsset(other, "Assets/Clips/FootIKHookTest_plain.anim");
            var c = AnimatorController.CreateAnimatorControllerAtPath(path);
            var sm = c.layers[0].stateMachine;
            var s1 = sm.AddState("walk"); s1.motion = clip;
            var s2 = sm.AddState("plain"); s2.motion = other;
            EditorUtility.SetDirty(c); AssetDatabase.SaveAssets();
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
            c = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
            AnimatorState S(string n) => c.layers[0].stateMachine.states.First(x => x.state.name == n).state;
            Check(S("walk").iKOnFeet, "Promptimate state gets Foot IK after save");
            Check(!S("plain").iKOnFeet, "non-Promptimate state untouched");

            S("walk").iKOnFeet = false; EditorUtility.SetDirty(c); AssetDatabase.SaveAssets();
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
            c = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
            Check(!S("walk").iKOnFeet, "user unticking Foot IK sticks");

            var s3 = c.layers[0].stateMachine.AddState("walk2"); s3.motion = clip;
            EditorUtility.SetDirty(c); AssetDatabase.SaveAssets();
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
            c = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
            Check(S("walk2").iKOnFeet, "second Promptimate state gets Foot IK");
            Check(!S("walk").iKOnFeet, "first state still as the user left it");

            Selection.activeObject = null;
            EditorApplication.ExecuteMenuItem("Tools/Promptimate/Enable Foot IK On Promptimate States");
            Check(S("walk").iKOnFeet, "menu command forces Foot IK on all Promptimate states");
            AssetDatabase.DeleteAsset(path); AssetDatabase.DeleteAsset("Assets/Clips/FootIKHookTest_plain.anim");
        }
        catch (System.Exception e) { Debug.LogError("FOOTIK_TEST ERROR " + e); fails++; }
        Debug.Log($"FOOTIK_TEST_SUMMARY fails={fails}");
        EditorApplication.Exit(fails > 0 ? 1 : 0);
    }
}
