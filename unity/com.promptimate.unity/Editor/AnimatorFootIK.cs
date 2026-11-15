// Animator states are created with "Foot IK" off. For a generated clip on a character with other proportions that
// means the feet follow the leg angles instead of the generated foot path: on real Mixamo/Kenney characters planted
// feet slide 3-7x more than in the source and, when sitting on the floor, the feet sink 12-18 cm into it (measured,
// unity/DemoStudio RetargetCheck). With Foot IK on, the clip's IK goal curves keep them where they were generated.
// So whenever a Promptimate clip is put into an Animator state, Foot IK is switched on for that state, once: the
// choice is remembered per state (in the controller's importer userData), so unticking it afterwards sticks.
// Menu: Tools > Promptimate > Enable Foot IK On Promptimate States (all controllers, ignores the memory).
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace Promptimate.Editor
{
    internal class AnimatorFootIK : AssetPostprocessor
    {
        internal static bool Enabled = true; // tests can switch it off

        static void OnPostprocessAllAssets(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
        {
            if (!Enabled) return;
            foreach (var p in imported.Where(p => p.EndsWith(".controller")))
            {
                var c = AssetDatabase.LoadAssetAtPath<AnimatorController>(p);
                if (c != null) Apply(c, p, false);
            }
        }

        [InitializeOnLoadMethod]
        static void Hook()
        {
            // The postprocessor only runs when the controller is saved. Also catch states made in the Animator window:
            // a new state is selected right after it is created, and before Play mode every controller in memory is checked.
            Selection.selectionChanged += () =>
            {
                if (!Enabled) return;
                var o = Selection.activeObject;
                if (o is AnimatorState || o is AnimatorStateMachine || o is AnimatorController) ApplyLoaded(AssetDatabase.GetAssetPath(o));
            };
            EditorApplication.playModeStateChanged += s =>
            {
                if (!Enabled || s != PlayModeStateChange.ExitingEditMode) return;
                foreach (var c in Resources.FindObjectsOfTypeAll<AnimatorController>()) ApplyLoaded(AssetDatabase.GetAssetPath(c));
            };
        }

        static void ApplyLoaded(string path)
        {
            if (string.IsNullOrEmpty(path) || !path.EndsWith(".controller")) return;
            var c = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
            if (c != null) Apply(c, path, false);
        }

        [MenuItem("Tools/Promptimate/Enable Foot IK On Promptimate States")]
        static void EnableAll()
        {
            int n = 0;
            foreach (var g in AssetDatabase.FindAssets("t:AnimatorController"))
            {
                var p = AssetDatabase.GUIDToAssetPath(g);
                var c = AssetDatabase.LoadAssetAtPath<AnimatorController>(p);
                if (c != null) n += Apply(c, p, true);
            }
            Debug.Log($"Promptimate: Foot IK enabled on {n} Animator state(s) that play Promptimate clips.");
        }

        internal static bool IsPromptimate(Motion m)
        {
            if (m == null) return false;
            if (m is BlendTree bt) return bt.children.Any(ch => IsPromptimate(ch.motion));
            return AssetDatabase.GetAssetPath(m).EndsWith(".kimodo");
        }

        /// Turns Foot IK on for states playing Promptimate clips that haven't been handled yet. Returns how many changed.
        internal static int Apply(AnimatorController c, string path, bool force)
        {
            var imp = AssetImporter.GetAtPath(path);
            const string Tag = "promptimateFootIK:";
            var seen = new HashSet<string>();
            string ud = imp != null ? imp.userData ?? "" : "";
            int tagAt = ud.IndexOf(Tag);
            if (tagAt >= 0)
                foreach (var k in ud.Substring(tagAt + Tag.Length).Split('\n')[0].Split('|')) if (k.Length > 0) seen.Add(k);
            int changed = 0; bool newKeys = false;
            for (int l = 0; l < c.layers.Length; l++)
                foreach (var (st, sp) in States(c.layers[l].stateMachine, c.layers[l].name))
                {
                    if (!IsPromptimate(st.motion)) continue;
                    string key = (sp + "/" + st.name + "@" + AssetDatabase.AssetPathToGUID(AssetDatabase.GetAssetPath(st.motion))).Replace("|", "_").Replace("\n", "_");
                    if (!force && seen.Contains(key)) continue;
                    if (seen.Add(key)) newKeys = true;
                    if (!st.iKOnFeet)
                    {
                        Undo.RecordObject(st, "Enable Foot IK");
                        st.iKOnFeet = true;
                        EditorUtility.SetDirty(st);
                        changed++;
                        Debug.Log($"Promptimate: enabled Foot IK on Animator state '{st.name}' in {path} (keeps the generated foot " +
                                  "path on characters with other proportions; untick it to turn it off).");
                    }
                }
            if (newKeys && imp != null)
            {
                string rest = ud;
                if (tagAt >= 0)
                {
                    int end = ud.IndexOf('\n', tagAt);
                    rest = ud.Remove(tagAt, (end >= 0 ? end + 1 : ud.Length) - tagAt);
                }
                imp.userData = rest + Tag + string.Join("|", seen) + "\n";
                EditorUtility.SetDirty(imp); // userData is written to the .meta with the next save
            }
            if (changed > 0) EditorUtility.SetDirty(c);
            return changed;
        }

        static IEnumerable<(AnimatorState, string)> States(AnimatorStateMachine sm, string path)
        {
            foreach (var cs in sm.states) yield return (cs.state, path);
            foreach (var sub in sm.stateMachines)
                foreach (var x in States(sub.stateMachine, path + "/" + sub.stateMachine.name)) yield return x;
        }
    }
}
