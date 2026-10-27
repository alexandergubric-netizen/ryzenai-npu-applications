using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace Postura
{
    /// <summary>
    /// The assistant's local model. Both engines speak the OpenAI chat API on 127.0.0.1:
    ///   flm      FastFlowLM, port 52625 (shared with other apps; started by us only if nobody else runs it)
    ///   foundry  Microsoft Foundry Local, fixed port 39839, with an idle timeout so it frees its memory
    /// Nothing starts until the assistant is opened; a FastFlowLM server we started stops after 10 idle minutes.
    /// </summary>
    static class Ai
    {
        const int FlmPort = 52625, FoundryPort = 39839;
        public static string State = "off", Detail = "";     // off | starting | ready | error
        static string baseUrl, modelId;
        static Process ownProc;
        static int generation;        // bumped by Reset so a start that was already under way can't mark the old model ready
        static DateTime lastUse = DateTime.MinValue;
        static readonly object startLock = new object(), genLock = new object();
        static readonly JavaScriptSerializer Ser = new JavaScriptSerializer();

        public static string Engine { get { return Store.Str("aiEngine"); } }
        public static bool Enabled { get { return Engine != "" && Store.Bool("aiEnabled"); } }

        static bool Ping(string url)
        {
            try
            {
                var r = (HttpWebRequest)WebRequest.Create(url + "/models");
                r.Timeout = 2000; r.Proxy = null;
                using (var resp = r.GetResponse()) return true;
            }
            catch { return false; }
        }

        /// <summary>Start (or find) the engine in the background and warm the model up.</summary>
        public static void Ensure()
        {
            if (!Enabled) { State = "off"; return; }
            lastUse = DateTime.Now;
            lock (startLock)
            {
                if (State == "starting" || (State == "ready" && Ping(baseUrl))) return;
                State = "starting";
                Detail = Engine == "flm" ? "Waking the NPU…" : "Starting Foundry Local…";
            }
            int g = generation;
            new Thread(() =>
            {
                try
                {
                    if (Engine == "flm") StartFlm(); else StartFoundry();
                    Detail = "Loading the model…";
                    Generate(new[] { new { role = "user", content = "hi" } }, 1, s => { });
                    if (g == generation) { State = "ready"; Detail = ""; }
                }
                catch (Exception e)
                {
                    if (g != generation) return;
                    State = "error";
                    Detail = e.Message;
                    Program.Log("ai start: " + e.Message);
                }
            }) { IsBackground = true }.Start();
        }

        static void StartFlm()
        {
            string model = Store.Str("aiModel");
            if (model == "") model = Hardware.FlmModel;
            baseUrl = "http://127.0.0.1:" + FlmPort + "/v1";
            modelId = model;
            if (Ping(baseUrl)) return;   // another app's FastFlowLM server: it swaps models per request
            string exe = Hardware.FlmExe();
            if (exe == null) throw new Exception("FastFlowLM is not installed any more. Run Postura setup again.");
            ownProc = Process.Start(new ProcessStartInfo(exe, "serve " + model + " --port " + FlmPort)
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = false });
            for (int i = 0; i < 360; i++)
            {
                if (Ping(baseUrl)) return;
                if (ownProc.HasExited) throw new Exception("FastFlowLM did not start (is the NPU driver up to date?)");
                Thread.Sleep(500);
            }
            throw new Exception("FastFlowLM did not start in time.");
        }

        static void StartFoundry()
        {
            string exe = Hardware.FoundryExe();
            if (exe == null) throw new Exception("Foundry Local is not installed any more. Run Postura setup again.");
            string alias = Store.Str("aiModel");
            if (alias == "") alias = Hardware.FoundryModel;
            baseUrl = FindFoundry(exe);
            if (baseUrl == null)
            {
                Hardware.Run(exe, "server start --port " + FoundryPort + " --idle-timeout 15", 120000);
                baseUrl = FindFoundry(exe) ?? "http://127.0.0.1:" + FoundryPort + "/v1";
            }
            Hardware.Run(exe, "model load " + alias, 300000);
            // the loaded variant's id (e.g. …-openvino-npu) is what the chat API expects
            modelId = alias;
            try
            {
                using (var c = new WebClient { Proxy = null })
                {
                    var m = Regex.Matches(c.DownloadString(baseUrl + "/models"), "\"id\"\\s*:\\s*\"([^\"]+)\"");
                    foreach (Match x in m)
                        if (x.Groups[1].Value.IndexOf(alias, StringComparison.OrdinalIgnoreCase) >= 0) { modelId = x.Groups[1].Value; break; }
                }
            }
            catch { }
        }

        static string FindFoundry(string exe)
        {
            var m = Regex.Match(Hardware.Run(exe, "server status", 30000), @"https?://(127\.0\.0\.1|localhost):(\d+)");
            if (!m.Success) return null;
            string url = "http://127.0.0.1:" + m.Groups[2].Value + "/v1";
            return Ping(url) ? url : null;
        }

        /// <summary>Called every few seconds by the tray: stop a FastFlowLM server we started once it is idle.</summary>
        public static void Housekeeping()
        {
            if (ownProc == null || (DateTime.Now - lastUse).TotalMinutes < 10) return;
            try { if (!ownProc.HasExited) ownProc.Kill(); } catch { }
            ownProc = null;
            State = "off";
        }

        public static void Stop()
        {
            try { if (ownProc != null && !ownProc.HasExited) ownProc.Kill(); } catch { }
            ownProc = null;
        }

        /// <summary>After a model change: the next question starts the engine with the new model.</summary>
        public static void Reset()
        {
            lock (startLock)
            {
                generation++;
                Stop();
                State = "off"; Detail = "";
                modelId = null;
            }
        }

        /// <summary>
        /// Stream an answer; onText gets the visible text piece by piece (any &lt;think&gt; reasoning removed).
        /// One request at a time.
        /// </summary>
        public static void Generate(object messages, int maxTokens, Action<string> onText)
        {
            lastUse = DateTime.Now;
            lock (genLock)
            {
                var body = Ser.Serialize(new { model = modelId, messages = messages, stream = true, max_tokens = maxTokens, temperature = 0.3, top_p = 0.9 });
                var req = (HttpWebRequest)WebRequest.Create(baseUrl + "/chat/completions");
                req.Method = "POST"; req.ContentType = "application/json"; req.Proxy = null;
                req.Timeout = 300000; req.ReadWriteTimeout = 300000;
                var bytes = Encoding.UTF8.GetBytes(body);
                using (var s = req.GetRequestStream()) s.Write(bytes, 0, bytes.Length);
                using (var resp = req.GetResponse())
                using (var r = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                {
                    var filter = new ThinkFilter(onText);
                    string line;
                    while ((line = r.ReadLine()) != null)
                    {
                        line = line.Trim();
                        if (!line.StartsWith("data:") || line.EndsWith("[DONE]")) continue;
                        string piece = null;
                        try
                        {
                            var j = Ser.DeserializeObject(line.Substring(5)) as System.Collections.Generic.Dictionary<string, object>;
                            var choices = j["choices"] as object[];
                            var delta = (choices[0] as System.Collections.Generic.Dictionary<string, object>)["delta"] as System.Collections.Generic.Dictionary<string, object>;
                            object c;
                            if (delta.TryGetValue("content", out c) && c is string && ((string)c).Length > 0) piece = (string)c;
                            else if (Engine == "flm" && delta.TryGetValue("reasoning_content", out c) && c is string) piece = (string)c;  // FLM quirk
                        }
                        catch { }
                        if (!string.IsNullOrEmpty(piece)) filter.Push(piece);
                    }
                    filter.End();
                }
            }
            lastUse = DateTime.Now;
        }

        /// <summary>Drops &lt;think&gt;…&lt;/think&gt; blocks from a stream (keeps an unclosed one if it held the whole answer).</summary>
        sealed class ThinkFilter
        {
            readonly Action<string> emit;
            string pending = "", hidden = "";
            bool inThink, started;
            public ThinkFilter(Action<string> emit) { this.emit = emit; }

            public void Push(string piece)
            {
                pending += piece;
                while (true)
                {
                    if (inThink)
                    {
                        int end = pending.IndexOf("</think>");
                        if (end < 0) { if (pending.Length > 10) { hidden += pending.Substring(0, pending.Length - 10); pending = pending.Substring(pending.Length - 10); } return; }
                        hidden = ""; pending = pending.Substring(end + 8); inThink = false; continue;
                    }
                    int start = pending.IndexOf("<think>");
                    string outp;
                    if (start >= 0) { outp = pending.Substring(0, start); pending = pending.Substring(start + 7); inThink = true; }
                    else
                    {
                        int lt = pending.LastIndexOf('<');
                        if (lt >= 0 && lt >= pending.Length - 8 && !pending.TrimEnd().EndsWith(">")) { outp = pending.Substring(0, lt); pending = pending.Substring(lt); }
                        else { outp = pending; pending = ""; }
                    }
                    Out(outp);
                    if (!inThink) return;
                }
            }

            void Out(string s)
            {
                if (!started) { s = s.TrimStart(); started = s.Length > 0; }
                if (s.Length > 0) emit(s);
            }

            public void End()
            {
                if (!inThink) Out(pending);
                else if (!started && (hidden + pending).Trim().Length > 0) Out((hidden + pending).Trim());
            }
        }
    }
}
