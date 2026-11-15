// Warm headless validator: one batch-mode Unity stays alive and serves validation requests from a folder queue,
// so a check costs ~1 s instead of a full editor launch.
//   Unity.exe -batchmode -nographics -projectPath <proj> -executeMethod Promptimate.Editor.ValidationServer.Start
//             -ttaServer [-ttaParentPid <pid>] [-ttaIdleSeconds <s>] [-ttaFingerprint <str>]
// (no -quit). Protocol, all files under <proj>/Temp/ttaq/ (mcp_server/unity_validate.py is the client):
//   status.json         written by the server: {"pid","state","fingerprint","since"}; state = ready | stopped
//   <id>.req.json       written by the client (atomic rename): {"id","cmd":"validate|ping|stop","selfTest"}
//   <id>.resp.json      written by the server (atomic rename): {"id","status","exitCode","lines":[...]}
//                       status = ok | compile_failed | error | stopping | pong
// "validate" runs BatchValidate.RunCore on whatever .kimodo files are under Assets (the client syncs Assets/Clips),
// so warm and one-shot runs execute exactly the same code. A script change recompiles and reloads the domain:
// [InitializeOnLoad] re-arms the server after every reload whenever -ttaServer is on the command line, and an
// unfinished request is simply picked up again. The server exits after the idle timeout, when the parent process
// is gone, or on a "stop" request.
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace Promptimate.Editor
{
    [InitializeOnLoad]
    public static class ValidationServer
    {
        [Serializable]
        class Request { public string id; public string cmd; public bool selfTest; }

        static bool armed;
        static string dir;
        static int parentPid;
        static double idleSeconds = 900;
        static string fingerprint = "";
        static double lastPoll, lastActivity, lastParentCheck;
        static bool busy;

        static ValidationServer()
        {
            if (Environment.GetCommandLineArgs().Contains("-ttaServer")) Arm();
        }

        /// -executeMethod entry point. Returns immediately; the editor keeps running because there is no -quit.
        public static void Start() => Arm();

        static string Arg(string name)
        {
            var a = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(a, name);
            return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
        }

        static void Arm()
        {
            if (armed) return;
            armed = true;
            dir = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Temp", "ttaq"));
            Directory.CreateDirectory(dir);
            int.TryParse(Arg("-ttaParentPid") ?? "0", out parentPid);
            if (double.TryParse(Arg("-ttaIdleSeconds") ?? "", System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out var idle)) idleSeconds = idle;
            fingerprint = Arg("-ttaFingerprint") ?? "";
            lastActivity = EditorApplication.timeSinceStartup;
            EditorApplication.update -= Tick;
            EditorApplication.update += Tick;
            WriteStatus("ready");
            UnityEngine.Debug.Log($"TTA_SERVER armed dir={dir} parent={parentPid} idle={idleSeconds}s");
        }

        static void WriteStatus(string state)
        {
            var json = "{\"pid\":" + Process.GetCurrentProcess().Id + ",\"state\":\"" + state + "\",\"fingerprint\":"
                       + Quote(fingerprint) + ",\"since\":" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "}";
            WriteAtomic(Path.Combine(dir, "status.json"), json);
        }

        static void Shutdown(string why)
        {
            UnityEngine.Debug.Log("TTA_SERVER exiting: " + why);
            EditorApplication.update -= Tick;
            try { WriteStatus("stopped"); } catch { }
            EditorApplication.Exit(0);
        }

        static void Tick()
        {
            if (busy) return;
            double now = EditorApplication.timeSinceStartup;
            if (now - lastPoll < 0.02) return;
            lastPoll = now;

            if (parentPid > 0 && now - lastParentCheck > 2)
            {
                lastParentCheck = now;
                if (!ProcessAlive(parentPid)) { Shutdown($"parent {parentPid} is gone"); return; }
            }
            if (idleSeconds > 0 && now - lastActivity > idleSeconds) { Shutdown($"idle for {idleSeconds}s"); return; }
            // Mid-compile or with a domain reload pending: leave requests in place, the reloaded domain serves them.
            if (EditorApplication.isCompiling || EditorApplication.isUpdating) return;

            string[] reqs;
            try { reqs = Directory.GetFiles(dir, "*.req.json"); }
            catch (DirectoryNotFoundException) { Directory.CreateDirectory(dir); WriteStatus("ready"); return; }
            if (reqs.Length == 0) return;
            Array.Sort(reqs, StringComparer.Ordinal);
            busy = true;
            try { Serve(reqs[0]); }
            finally { busy = false; lastActivity = EditorApplication.timeSinceStartup; }
        }

        static void Serve(string reqPath)
        {
            Request req;
            try { req = JsonUtility.FromJson<Request>(File.ReadAllText(reqPath)); }
            catch (Exception e)
            {
                UnityEngine.Debug.LogWarning("TTA_SERVER bad request " + reqPath + ": " + e.Message);
                TryDelete(reqPath);
                return;
            }
            string id = string.IsNullOrEmpty(req.id) ? Path.GetFileName(reqPath).Replace(".req.json", "") : req.id;
            string respPath = Path.Combine(dir, id + ".resp.json");
            switch (req.cmd)
            {
                case "ping":
                    Respond(reqPath, respPath, id, "pong", 0, null);
                    return;
                case "stop":
                    Respond(reqPath, respPath, id, "stopping", 0, null);
                    Shutdown("stop requested");
                    return;
            }

            var sw = Stopwatch.StartNew();
            // Pick up script edits first. If that starts a compile the domain reloads after this frame; keep the
            // request so the re-armed server answers it with the new code.
            AssetDatabase.Refresh();
            if (EditorApplication.isCompiling)
            {
                UnityEngine.Debug.Log("TTA_SERVER scripts changed; deferring " + id + " until after the domain reload");
                return;
            }
            if (EditorUtility.scriptCompilationFailed)
            {
                Respond(reqPath, respPath, id, "compile_failed", -1, null);
                return;
            }
            var lines = new System.Collections.Generic.List<string>();
            int code;
            try { code = BatchValidate.RunCore(req.selfTest, lines.Add); }
            catch (Exception e)
            {
                lines.Add("TTA_SERVER_ERROR " + e);
                Respond(reqPath, respPath, id, "error", -1, lines);
                return;
            }
            foreach (var l in lines) UnityEngine.Debug.Log(l);
            UnityEngine.Debug.Log($"TTA_SERVER served {id} in {sw.ElapsedMilliseconds} ms (exit {code})");
            Respond(reqPath, respPath, id, "ok", code, lines);
        }

        static void Respond(string reqPath, string respPath, string id, string status, int code,
                            System.Collections.Generic.List<string> lines)
        {
            var sb = new StringBuilder();
            sb.Append("{\"id\":").Append(Quote(id)).Append(",\"status\":\"").Append(status)
              .Append("\",\"exitCode\":").Append(code).Append(",\"lines\":[");
            if (lines != null)
                for (int i = 0; i < lines.Count; i++) { if (i > 0) sb.Append(','); sb.Append(Quote(lines[i])); }
            sb.Append("]}");
            WriteAtomic(respPath, sb.ToString());
            TryDelete(reqPath);
        }

        static string Quote(string s)
        {
            var sb = new StringBuilder("\"");
            foreach (char c in s ?? "")
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else sb.Append(c);
                        break;
                }
            }
            return sb.Append('"').ToString();
        }

        static void WriteAtomic(string path, string text)
        {
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, text, new UTF8Encoding(false));
            if (File.Exists(path)) File.Delete(path);
            File.Move(tmp, path);
        }

        static void TryDelete(string path) { try { File.Delete(path); } catch { } }

        static bool ProcessAlive(int pid)
        {
            try { using (var p = Process.GetProcessById(pid)) return !p.HasExited; }
            catch { return false; }
        }
    }
}
