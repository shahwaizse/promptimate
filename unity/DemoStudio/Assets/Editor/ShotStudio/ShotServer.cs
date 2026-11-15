// Keeps one batchmode editor warm and renders shots from a job folder, so a short with many shots doesn't pay the
// editor start-up (30-60 s) per shot.
//   Unity.exe -batchmode -projectPath unity/DemoStudio -executeMethod ShotStudio.ShotServer.Run -queue <dir> [-idle 900]
// Protocol (files in <dir>): <id>.job.json (ShotSpec) -> renamed to <id>.running -> <id>.done.json {"ok":..,"error":..}.
// heartbeat.json is rewritten every second while the server is alive; it exits after `idle` seconds without jobs,
// or when stop.flag appears.
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace ShotStudio
{
    [InitializeOnLoad]
    public static class ShotServer
    {
        // A script change makes the editor reload its domain (statics reset, update callbacks dropped); re-attach then.
        static ShotServer()
        {
            var a = System.Environment.GetCommandLineArgs();
            if (System.Array.IndexOf(a, "-queue") >= 0 && a.Contains("ShotStudio.ShotServer.Run") && SessionState.GetBool("ShotStudio.ServerStarted", false))
                EditorApplication.delayCall += () => Attach(false);
        }

        static string queue;
        static double lastJob, lastBeat;
        static float idle = 900;
        static bool busy;

        public static void Run() => Attach(true);

        static void Attach(bool first)
        {
            var a = System.Environment.GetCommandLineArgs();
            int i = System.Array.IndexOf(a, "-queue");
            if (i < 0) { Debug.LogError("SHOT_ERROR missing -queue <dir>"); EditorApplication.Exit(2); return; }
            queue = a[i + 1];
            int k = System.Array.IndexOf(a, "-idle");
            if (k >= 0) float.TryParse(a[k + 1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out idle);
            Directory.CreateDirectory(queue);
            if (first) foreach (var f in Directory.GetFiles(queue, "*.running")) File.Delete(f); // stale from a crash
            if (File.Exists(Path.Combine(queue, "stop.flag"))) File.Delete(Path.Combine(queue, "stop.flag"));
            // Warm everything up front: pipeline, shaders and the first imports.
            try { Pipeline.Ensure(); Shader.Find("Universal Render Pipeline/Lit"); }
            catch (System.Exception e) { Debug.LogError("SHOT_ERROR warmup " + e); }
            lastJob = EditorApplication.timeSinceStartup;
            Beat("ready");
            EditorApplication.update -= Tick;
            EditorApplication.update += Tick;
            SessionState.SetBool("ShotStudio.ServerStarted", true);
            Debug.Log("SHOT_SERVER ready queue=" + queue);
        }

        static void Beat(string state)
        {
            lastBeat = EditorApplication.timeSinceStartup;
            File.WriteAllText(Path.Combine(queue, "heartbeat.json"),
                $"{{\"pid\":{System.Diagnostics.Process.GetCurrentProcess().Id},\"state\":\"{state}\",\"utc\":\"{System.DateTime.UtcNow:o}\",\"unity\":\"{Application.unityVersion}\"}}");
        }

        static void Tick()
        {
            if (busy) return;
            double now = EditorApplication.timeSinceStartup;
            if (now - lastBeat > 1) Beat("idle");
            if (File.Exists(Path.Combine(queue, "stop.flag")) || now - lastJob > idle)
            {
                Beat("stopped");
                EditorApplication.update -= Tick;
                EditorApplication.Exit(0);
                return;
            }
            var job = Directory.GetFiles(queue, "*.job.json").OrderBy(File.GetCreationTimeUtc).FirstOrDefault();
            if (job == null) return;
            busy = true;
            string id = Path.GetFileName(job).Replace(".job.json", "");
            string running = Path.Combine(queue, id + ".running");
            string done = Path.Combine(queue, id + ".done.json");
            try
            {
                File.Move(job, running);
                Beat("rendering " + id);
                var spec = JsonUtility.FromJson<ShotSpec>(File.ReadAllText(running));
                AssetDatabase.Refresh(); // new .kimodo clips dropped in by the Python side
                if (EditorApplication.isCompiling)
                {
                    // Renderer scripts changed: requeue and render after the domain reload, with the new code.
                    File.Move(running, job);
                    Beat("compiling");
                    return;
                }
                ShotRenderer.Render(spec);
                File.WriteAllText(done, "{\"ok\":true}");
            }
            catch (System.Exception e)
            {
                Debug.LogError("SHOT_ERROR " + id + " " + e);
                File.WriteAllText(done, "{\"ok\":false,\"error\":" + Json(e.GetType().Name + ": " + e.Message + "\n" + e.StackTrace) + "}");
            }
            finally
            {
                if (File.Exists(running)) File.Delete(running);
                lastJob = EditorApplication.timeSinceStartup;
                busy = false;
                Beat("idle");
            }
        }

        static string Json(string s) => "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "").Replace("\t", " ") + "\"";
    }
}
