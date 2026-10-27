using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Reflection;
using System.Text;
using System.Threading;

namespace Postura
{
    /// <summary>
    /// Local HTTP server for the UI window (127.0.0.1 only). Started when the window opens and stopped a little
    /// after it closes. Every /api call must carry the per-run token header; the Host header is checked too,
    /// so other web pages can't talk to it. Nothing here ever reaches the internet.
    /// </summary>
    sealed class Server
    {
        readonly HttpListener http = new HttpListener();
        public readonly int Port;
        public readonly WebGate Gate;    // the window's session cookie; see WebGate.cs
        readonly string webDir;          // dev: serve UI from disk
        public bool SetupMode;           // installer wizard: serves setup.html and only the setup API
        public DateTime LastSeen = DateTime.Now;
        public string PendingPage;       // a page the tray asked an already open window to show

        public Server(WebGate gate, string webDir)
        {
            Gate = gate;
            Port = gate.Port;
            this.webDir = webDir;
            http.Prefixes.Add("http://127.0.0.1:" + Port + "/");
        }

        public void Start()
        {
            http.Start();
            var th = new Thread(Loop) { IsBackground = true, Name = "http" };
            th.Start();
        }

        public void Stop() { try { http.Stop(); http.Close(); } catch { } }

        void Loop()
        {
            while (http.IsListening)
            {
                HttpListenerContext ctx;
                try { ctx = http.GetContext(); } catch { return; }
                ThreadPool.QueueUserWorkItem(_ => Handle(ctx));
            }
        }

        void Handle(HttpListenerContext ctx)
        {
            var req = ctx.Request;
            var res = ctx.Response;
            try
            {
                if (!Gate.Allow(req, res)) return;   // host, cross-site, session cookie, body size
                string path = req.Url.AbsolutePath;
                if (path.StartsWith("/api/"))
                {
                    LastSeen = DateTime.Now;
                    Api(path.Substring(5), req, res);
                }
                else Static(path, res);
            }
            catch (Exception e)
            {
                try { Json(res, 500, new Dictionary<string, object> { { "error", e.Message } }); } catch { }
            }
        }

        // ---------------------------------------------------------------- static files

        static readonly Dictionary<string, string> Mime = new Dictionary<string, string> {
            { ".html", "text/html; charset=utf-8" }, { ".js", "text/javascript; charset=utf-8" },
            { ".css", "text/css; charset=utf-8" }, { ".svg", "image/svg+xml" }, { ".png", "image/png" },
            { ".ico", "image/x-icon" }, { ".json", "application/json" }, { ".woff2", "font/woff2" }
        };

        public static byte[] Resource(string name)
        {
            using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("web/" + name))
            {
                if (s == null) return null;
                var ms = new MemoryStream(); s.CopyTo(ms); return ms.ToArray();
            }
        }

        void Static(string path, HttpListenerResponse res)
        {
            if (path == "/") path = SetupMode ? "/setup.html" : "/index.html";
            string name = path.TrimStart('/');
            if (name.Contains("..") || name.Contains("/") || name.Contains("\\")) { Send(res, 404, "text/plain", "Not found"); return; }
            byte[] data = null;
            if (webDir != null)
            {
                string f = Path.Combine(webDir, name);
                if (File.Exists(f)) data = File.ReadAllBytes(f);
                if (data == null && name == "icon.png") data = Resource(name);   // per-edition icon lives in the build
            }
            else data = Resource(name);
            if (data == null) { Send(res, 404, "text/plain", "Not found"); return; }
            string ext = Path.GetExtension(name).ToLowerInvariant();
            if (ext == ".html")
                data = Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(data)
                    .Replace("{{TOKEN}}", "1").Replace("{{VERSION}}", Program.Version)
                    .Replace("{{EDITION}}", Edition.Id).Replace("{{ASSISTANT}}", Edition.Assistant));
            string mime;
            res.AddHeader("Cache-Control", "no-store");
            // the UI may only load its own files: no remote scripts, fonts, images or connections
            res.Headers.Set("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'");
            Send(res, 200, Mime.TryGetValue(ext, out mime) ? mime : "application/octet-stream", data);
        }

        // ---------------------------------------------------------------- helpers

        static void Send(HttpListenerResponse res, int code, string type, string body) { Send(res, code, type, Encoding.UTF8.GetBytes(body)); }

        static void Send(HttpListenerResponse res, int code, string type, byte[] body)
        {
            res.StatusCode = code;
            res.ContentType = type;
            res.ContentLength64 = body.Length;
            res.OutputStream.Write(body, 0, body.Length);
            res.OutputStream.Close();
        }

        static void Json(HttpListenerResponse res, int code, object o) { Send(res, code, "application/json; charset=utf-8", Store.ToJson(o)); }
        static void Ok(HttpListenerResponse res) { Json(res, 200, new Dictionary<string, object> { { "ok", true } }); }

        static Dictionary<string, object> Body(HttpListenerRequest req)
        {
            using (var r = new StreamReader(req.InputStream, Encoding.UTF8)) return Store.Parse(r.ReadToEnd());
        }

        static int IntArg(Dictionary<string, object> b, string k, int def)
        {
            object v;
            if (!b.TryGetValue(k, out v) || v == null) return def;
            try { return Convert.ToInt32(v); } catch { return def; }
        }

        // ---------------------------------------------------------------- API

        void Api(string name, HttpListenerRequest req, HttpListenerResponse res)
        {
            if (SetupMode)
            {
                switch (name)
                {
                    case "ping": Ok(res); return;
                    case "setup-info": Json(res, 200, Setup.Info()); return;
                    case "setup-install":
                        {
                            var b = Body(req);
                            object mdl;
                            AiInstall.Start(Flag(b, "desktop"), Flag(b, "startMenu"), Flag(b, "autostart"), Flag(b, "ai"),
                                b.TryGetValue("model", out mdl) ? mdl as string : null);
                            Ok(res);
                            return;
                        }
                    case "setup-progress": Json(res, 200, AiInstall.Progress()); return;
                    case "setup-launch": Setup.Launch(); Ok(res); return;
                }
                Json(res, 404, new Dictionary<string, object> { { "error", "Not available in setup" } });
                return;
            }

            switch (name)
            {
                case "ping": Ok(res); return;
                case "state": Json(res, 200, App.State()); return;
                case "settings":
                    {
                        var patch = Body(req);
                        // the engine is chosen by the installer's hardware check only; the page may just switch it on/off
                        patch.Remove("aiEngine"); patch.Remove("aiModel");
                        if (Ai.Engine == "") patch.Remove("aiEnabled");
                        var changed = Store.SetSettings(patch);
                        App.OnUi(() => App.SettingsChanged(changed));
                        Json(res, 200, App.State());
                        return;
                    }
                case "ui": Store.SetUi(Body(req)); Ok(res); return;
                case "eye-now": App.OnUi(App.StartEyeBreak); Ok(res); return;
                case "eye-done": App.OnUi(() => App.Reminder.EyeBreakDone()); Ok(res); return;
                case "snooze": App.OnUi(() => App.Reminder.Snooze(IntArg(Body(req), "seconds", 300))); Ok(res); return;
                case "pause": { int m = IntArg(Body(req), "minutes", 60); App.OnUi(() => App.Pause(m)); Ok(res); return; }
                case "test-notify":
                    {
                        // run it now and report what actually happened, so the page can explain it
                        string shown = App.OnUiWait(() => App.EyeDue(true));
                        Json(res, 200, new Dictionary<string, object> { { "shown", shown }, { "status", Toast.Status() } });
                        return;
                    }
                case "notify-status": Json(res, 200, Toast.Status()); return;
                case "notify-settings": Toast.OpenWindowsSettings(); Ok(res); return;
                case "test-move": App.OnUi(App.MoveDue); Ok(res); return;
                case "ai-warm": Ai.Ensure(); Json(res, 200, App.AiState()); return;
                case "ai-models":
                    Json(res, 200, new Dictionary<string, object> {
                        { "current", Store.Str("aiModel") }, { "recommended", Hardware.Recommended(Ai.Engine) },
                        { "models", Hardware.Models(Ai.Engine).ToArray() } });
                    return;
                case "ai-model":
                    {
                        // poka-yoke: only a chat model the engine really has installed
                        object v;
                        string model = Body(req).TryGetValue("model", out v) ? v as string : null;
                        if (Ai.Engine == "" || model == null || !Hardware.Models(Ai.Engine).Contains(model))
                        { Json(res, 400, new Dictionary<string, object> { { "error", "That model isn't installed for this AI engine" } }); return; }
                        Store.SetSettings(new Dictionary<string, object> { { "aiModel", model } });
                        Ai.Reset();
                        Json(res, 200, App.AiState());
                        return;
                    }
                case "ai-chat": AiChat(req, res); return;
            }
            Json(res, 404, new Dictionary<string, object> { { "error", "Unknown call " + name } });
        }

        /// <summary>Streams the model's answer as plain UTF-8 text (chunked) to the page.</summary>
        static void AiChat(HttpListenerRequest req, HttpListenerResponse res)
        {
            if (!Ai.Enabled) { Json(res, 403, new Dictionary<string, object> { { "error", "The AI assistant is not enabled on this PC" } }); return; }
            if (Ai.State != "ready") { Ai.Ensure(); Json(res, 503, App.AiState()); return; }
            var b = Body(req);
            object m;
            var list = new List<Dictionary<string, string>>();
            if (b.TryGetValue("messages", out m) && m is System.Collections.IList)   // JavaScriptSerializer gives ArrayList
                foreach (var o in (System.Collections.IList)m)
                {
                    var d = o as Dictionary<string, object>;
                    if (d == null) continue;
                    string role = d.ContainsKey("role") ? d["role"] as string : null, content = d.ContainsKey("content") ? d["content"] as string : null;
                    if ((role != "system" && role != "user" && role != "assistant") || content == null) continue;
                    list.Add(new Dictionary<string, string> { { "role", role }, { "content", content.Length > 12000 ? content.Substring(0, 12000) : content } });
                }
            if (list.Count == 0 || list.Count > 16) { Json(res, 400, new Dictionary<string, object> { { "error", "Bad messages" } }); return; }
            // Qwen3 / Qwen3.5 hybrid models reason at length by default: ask for a direct answer (instruct "-it"/2507 builds don't think)
            if (System.Text.RegularExpressions.Regex.IsMatch(Store.Str("aiModel"), @"qwen3(?!.*(2507|instruct|-it\b|vl))", System.Text.RegularExpressions.RegexOptions.IgnoreCase))
                for (int i = list.Count - 1; i >= 0; i--)
                    if (list[i]["role"] == "user") { list[i]["content"] = "/no_think " + list[i]["content"]; break; }
            res.StatusCode = 200;
            res.ContentType = "text/plain; charset=utf-8";
            res.SendChunked = true;
            var output = res.OutputStream;
            try
            {
                Ai.Generate(list, 260, piece =>
                {
                    var bytes = Encoding.UTF8.GetBytes(piece);
                    output.Write(bytes, 0, bytes.Length);
                    output.Flush();
                });
                // always under an AI answer, whatever the model wrote
                var note = Encoding.UTF8.GetBytes("\n\n*General guidance, not medical advice.*");
                output.Write(note, 0, note.Length);
            }
            catch (Exception e)
            {
                Program.Log("ai chat: " + e.Message);
                Ai.State = "error"; Ai.Detail = e.Message;
                var bytes = Encoding.UTF8.GetBytes("\u0000ERROR " + e.Message);
                try { output.Write(bytes, 0, bytes.Length); } catch { }
            }
            try { output.Close(); } catch { }
        }

        static bool Flag(Dictionary<string, object> b, string k)
        {
            object v; return b.TryGetValue(k, out v) && v is bool && (bool)v;
        }
    }
}
