// Keeps one batchmode editor warm and runs jobs from a folder: world jobs (WorldJob: build + stills + camera move,
// or a measure pass) and character shots (ShotStudio ShotSpec whose stage is "world:<resolved world json>").
//   Unity.exe -batchmode -projectPath unity/WorldLab -executeMethod WorldLab.WorldServer.Run -queue <dir> [-idle 600]
// Protocol (same as ShotStudio.ShotServer): <id>.job.json -> <id>.running -> <id>.done.json {"ok":..,"error":..};
// heartbeat.json every second; exits after `idle` seconds without jobs or when stop.flag appears.
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace WorldLab
{
    [InitializeOnLoad]
    public static class WorldServer
    {
        static WorldServer()
        {
            var a = System.Environment.GetCommandLineArgs();
            if (System.Array.IndexOf(a, "-queue") >= 0 && a.Contains("WorldLab.WorldServer.Run") && SessionState.GetBool("WorldLab.ServerStarted", false))
                EditorApplication.delayCall += () => Attach(false);
        }

        static string queue;
        static double lastJob, lastBeat;
        static float idle = 600;
        static bool busy;

        public static void Run() => Attach(true);

        static void Attach(bool first)
        {
            var a = System.Environment.GetCommandLineArgs();
            int i = System.Array.IndexOf(a, "-queue");
            if (i < 0) { Debug.LogError("WORLD_ERROR missing -queue <dir>"); EditorApplication.Exit(2); return; }
            queue = a[i + 1];
            int k = System.Array.IndexOf(a, "-idle");
            if (k >= 0) float.TryParse(a[k + 1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out idle);
            Directory.CreateDirectory(queue);
            if (first) foreach (var f in Directory.GetFiles(queue, "*.running")) File.Delete(f);
            if (File.Exists(Path.Combine(queue, "stop.flag"))) File.Delete(Path.Combine(queue, "stop.flag"));
            try { ShotStudio.Pipeline.Ensure(); Shader.Find("Universal Render Pipeline/Lit"); }
            catch (System.Exception e) { Debug.LogError("WORLD_ERROR warmup " + e); }
            lastJob = EditorApplication.timeSinceStartup;
            Beat("ready");
            EditorApplication.update -= Tick;
            EditorApplication.update += Tick;
            SessionState.SetBool("WorldLab.ServerStarted", true);
            Debug.Log("WORLD_SERVER ready queue=" + queue);
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
                Beat("working " + id);
                string json = File.ReadAllText(running);
                AssetDatabase.Refresh();
                if (EditorApplication.isCompiling) { File.Move(running, job); Beat("compiling"); return; }
                var kind = JsonUtility.FromJson<KindProbe>(json).kind;
                if (kind == "world" || kind == "measure") WorldRenderer.Dispatch(json);
                else ShotStudio.ShotRenderer.Render(JsonUtility.FromJson<ShotStudio.ShotSpec>(json));
                File.WriteAllText(done, "{\"ok\":true}");
            }
            catch (System.Exception e)
            {
                Debug.LogError("WORLD_ERROR " + id + " " + e);
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

        [System.Serializable] class KindProbe { public string kind; }

        static string Json(string s) => "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "").Replace("\t", " ") + "\"";
    }
}
