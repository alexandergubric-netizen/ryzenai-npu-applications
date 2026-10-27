using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;

namespace Postura
{
    /// <summary>
    /// Who may talk to the local server: only the window this user opened (same idea as websec.py in the Python apps).
    ///  * A per-user discovery file (DataDir\instance.json) holds the port and a random secret; only this Windows user
    ///    can read it. A second launch asks the running server for a launch key with that secret.
    ///  * The window opens at /?k=one-time-key; the server swaps the key for an HttpOnly, SameSite=Strict cookie and
    ///    redirects to "/", so no page ever contains a secret.
    ///  * Every request needs the right Host, no cross-site Sec-Fetch-Site and the cookie; API calls also the app header.
    ///  * Every response forbids framing (clickjacking) and MIME sniffing.
    /// </summary>
    sealed class WebGate
    {
        readonly string app, header, file;
        public int Port;
        public readonly string Secret = NewKey(32);
        readonly string session = NewKey(32);
        readonly string cookie;
        readonly Dictionary<string, DateTime> launch = new Dictionary<string, DateTime>();
        readonly Dictionary<string, string> launchArgs = new Dictionary<string, string>();
        public const long MaxBody = 4 * 1024 * 1024;

        public WebGate(string app, string header, string dataDir)
        {
            this.app = app; this.header = header;
            cookie = app.ToLowerInvariant() + "_s";
            file = Path.Combine(dataDir, "instance.json");
        }

        static string NewKey(int bytes)
        {
            var b = new byte[bytes];
            using (var r = RandomNumberGenerator.Create()) r.GetBytes(b);
            return Convert.ToBase64String(b).TrimEnd('=').Replace('+', '-').Replace('/', '_');
        }

        /// <summary>The preferred port if it is free, else any free one.</summary>
        public static int PickPort(int preferred)
        {
            try { var l = new TcpListener(IPAddress.Loopback, preferred); l.Start(); l.Stop(); return preferred; }
            catch (SocketException) { }
            var any = new TcpListener(IPAddress.Loopback, 0); any.Start();
            int p = ((IPEndPoint)any.LocalEndpoint).Port; any.Stop();
            return p;
        }

        public void Publish()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(file));
            string tmp = file + ".tmp";
            File.WriteAllText(tmp, Store.ToJson(new Dictionary<string, object> { { "app", app }, { "port", Port }, { "secret", Secret },
                { "pid", Process.GetCurrentProcess().Id } }));
            if (File.Exists(file)) File.Delete(file);
            File.Move(tmp, file);
        }

        public void Withdraw()
        {
            try
            {
                var d = Store.Parse(File.ReadAllText(file));
                if (Convert.ToInt32(d["pid"]) == Process.GetCurrentProcess().Id) File.Delete(file);
            }
            catch { }
        }

        public string NewLaunchKey(string arg = null)
        {
            string k = NewKey(24);
            lock (launch)
            {
                var now = DateTime.UtcNow;
                foreach (var old in new List<string>(launch.Keys)) if (launch[old] < now) { launch.Remove(old); launchArgs.Remove(old); }
                launch[k] = now.AddMinutes(2);
                if (arg != null) launchArgs[k] = arg;
            }
            return k;
        }

        public string LaunchUrl(string arg = null) { return "http://127.0.0.1:" + Port + "/?k=" + NewLaunchKey(arg); }

        /// <summary>A launch key's argument (e.g. the folder to scan), handed out once to the page that used the key.</summary>
        string pendingArg;
        public string TakePendingArg() { lock (launch) { var a = pendingArg; pendingArg = null; return a; } }

        public static void AddHeaders(HttpListenerResponse res)
        {
            res.AddHeader("X-Frame-Options", "DENY");
            res.AddHeader("Content-Security-Policy", "frame-ancestors 'none'");
            res.AddHeader("X-Content-Type-Options", "nosniff");
            res.AddHeader("Referrer-Policy", "no-referrer");
            res.AddHeader("Cross-Origin-Resource-Policy", "same-origin");
        }

        bool HostOk(HttpListenerRequest req)
        {
            string host = req.Headers["Host"] ?? "";
            return host == "127.0.0.1:" + Port || host == "localhost:" + Port;
        }

        static bool SiteOk(HttpListenerRequest req)
        {
            string s = (req.Headers["Sec-Fetch-Site"] ?? "").ToLowerInvariant();
            return s == "" || s == "same-origin" || s == "none";
        }

        bool HasSession(HttpListenerRequest req)
        {
            var c = req.Cookies[cookie];
            return c != null && FixedEquals(c.Value, session);
        }

        static bool FixedEquals(string a, string b)
        {
            if (a == null || b == null || a.Length != b.Length) return false;
            int d = 0;
            for (int i = 0; i < a.Length; i++) d |= a[i] ^ b[i];
            return d == 0;
        }

        /// <summary>Decides a request. Returns true when the caller may serve it; otherwise the response is done.</summary>
        public bool Allow(HttpListenerRequest req, HttpListenerResponse res)
        {
            AddHeaders(res);
            if (!HostOk(req)) { Deny(res, false); return false; }
            string path = req.Url.AbsolutePath;
            if (path == "/api/launch") { Launch(req, res); return false; }
            if (!SiteOk(req)) { Deny(res, path.StartsWith("/api/")); return false; }
            string key = req.QueryString["k"];
            if (!string.IsNullOrEmpty(key) && !path.StartsWith("/api/"))
            {
                bool ok; string arg;
                lock (launch)
                {
                    DateTime exp;
                    ok = launch.TryGetValue(key, out exp) && exp > DateTime.UtcNow;
                    launchArgs.TryGetValue(key, out arg);
                    launch.Remove(key); launchArgs.Remove(key);
                    if (ok) pendingArg = arg;
                }
                if (ok)
                {
                    res.AddHeader("Set-Cookie", cookie + "=" + session + "; HttpOnly; SameSite=Strict; Path=/");
                    res.AddHeader("Cache-Control", "no-store");
                    res.StatusCode = 303;
                    res.RedirectLocation = path;
                    res.ContentLength64 = 0;
                    res.OutputStream.Close();
                    return false;
                }
                if (!HasSession(req)) { Deny(res, false); return false; }
                return true;
            }
            if (!HasSession(req)) { Deny(res, path.StartsWith("/api/")); return false; }
            if (path.StartsWith("/api/"))
            {
                if (string.IsNullOrEmpty(req.Headers[header]) || req.ContentLength64 > MaxBody) { Deny(res, true); return false; }
            }
            return true;
        }

        void Launch(HttpListenerRequest req, HttpListenerResponse res)
        {
            if (req.HttpMethod != "POST" || !FixedEquals(req.Headers[header + "-Secret"] ?? "", Secret) || req.ContentLength64 > 64 * 1024)
            { Deny(res, true); return; }
            string arg = null;
            try
            {
                using (var r = new StreamReader(req.InputStream, Encoding.UTF8))
                {
                    object a; var d = Store.Parse(r.ReadToEnd());
                    arg = d.TryGetValue("arg", out a) ? a as string : null;
                }
            }
            catch { }
            var body = Encoding.UTF8.GetBytes(Store.ToJson(new Dictionary<string, object> { { "app", app }, { "port", Port }, { "key", NewLaunchKey(arg) } }));
            res.StatusCode = 200; res.ContentType = "application/json"; res.AddHeader("Cache-Control", "no-store");
            res.ContentLength64 = body.Length; res.OutputStream.Write(body, 0, body.Length); res.OutputStream.Close();
        }

        static readonly byte[] Blocked = Encoding.UTF8.GetBytes("<!doctype html><meta charset=utf-8><title>Closed</title>" +
            "<body style='font:15px system-ui;margin:3em;color:#444'>This window has expired. Please open the app again from its shortcut.</body>");

        static void Deny(HttpListenerResponse res, bool json)
        {
            byte[] body = json ? Encoding.UTF8.GetBytes("{\"error\":\"forbidden\"}") : Blocked;
            res.StatusCode = 403;
            res.ContentType = json ? "application/json" : "text/html; charset=utf-8";
            res.AddHeader("Cache-Control", "no-store");
            res.KeepAlive = false;
            res.ContentLength64 = body.Length;
            try { res.OutputStream.Write(body, 0, body.Length); res.OutputStream.Close(); } catch { }
        }
    }
}
