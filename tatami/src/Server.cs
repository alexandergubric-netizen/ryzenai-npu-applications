using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

namespace Tatami
{
    /// <summary>Local HTTP API + static files for the UI. Every /api call must carry the per-run token header.</summary>
    sealed class Server
    {
        readonly HttpListener http = new HttpListener();
        public readonly int Port;
        public readonly WebGate Gate;     // the window's session cookie; see WebGate.cs
        readonly string webDir;           // dev: serve UI from disk
        public Session Session;
        public bool SetupMode;            // installer wizard: serves setup.html and only the setup API
        public DateTime LastSeen = DateTime.Now;
        readonly object scanLock = new object();

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
            var th = new Thread(Loop); th.IsBackground = true; th.Start();
        }

        public void Stop() { try { http.Stop(); } catch { } }

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
                try { SendJson(res, 500, new Json().Obj().P("error", e.Message).EndObj().ToString()); } catch { }
            }
        }

        // ---------------------------------------------------------------- static files

        static readonly Dictionary<string, string> Mime = new Dictionary<string, string> {
            { ".html", "text/html; charset=utf-8" }, { ".js", "text/javascript; charset=utf-8" },
            { ".css", "text/css; charset=utf-8" }, { ".svg", "image/svg+xml" }, { ".png", "image/png" },
            { ".ico", "image/x-icon" }, { ".json", "application/json" }, { ".woff2", "font/woff2" }
        };

        void Static(string path, HttpListenerResponse res)
        {
            if (path == "/") path = SetupMode ? "/setup.html" : "/index.html";
            string name = path.TrimStart('/');
            if (name.Contains("..") || name.Contains("/") || name.Contains("\\")) { Send(res, 404, "text/plain", "Not found"); return; }
            byte[] data = null;
            if (webDir != null)
            {
                string f = System.IO.Path.Combine(webDir, name);
                if (File.Exists(f)) data = File.ReadAllBytes(f);
            }
            else
            {
                using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("web/" + name))
                    if (s != null) { var ms = new MemoryStream(); s.CopyTo(ms); data = ms.ToArray(); }
            }
            if (data == null) { Send(res, 404, "text/plain", "Not found"); return; }
            string ext = System.IO.Path.GetExtension(name).ToLowerInvariant();
            if (ext == ".html")
                data = Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(data).Replace("{{TOKEN}}", "1").Replace("{{VERSION}}", Program.Version));
            string mime;
            res.AddHeader("Cache-Control", "no-store");
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

        static void SendJson(HttpListenerResponse res, int code, string json) { Send(res, code, "application/json; charset=utf-8", json); }
        static void Ok(HttpListenerResponse res, Json j) { SendJson(res, 200, j.ToString()); }
        static void Fail(HttpListenerResponse res, int code, string msg) { SendJson(res, code, new Json().Obj().P("error", msg).EndObj().ToString()); }

        static string Q(HttpListenerRequest req, string k, string def = null) { return req.QueryString[k] ?? def; }
        static int QI(HttpListenerRequest req, string k, int def)
        {
            int v; return int.TryParse(req.QueryString[k], NumberStyles.Integer, CultureInfo.InvariantCulture, out v) ? v : def;
        }
        static double QD(HttpListenerRequest req, string k, double def)
        {
            double v; return double.TryParse(req.QueryString[k], NumberStyles.Float, CultureInfo.InvariantCulture, out v) ? v : def;
        }

        static Dictionary<string, object> Body(HttpListenerRequest req)
        {
            using (var r = new StreamReader(req.InputStream, Encoding.UTF8)) return Json.Parse(r.ReadToEnd());
        }

        public static long JsTime(long filetime)
        {
            return filetime <= 0 ? 0 : (filetime - 116444736000000000L) / 10000;
        }

        Tree DoneTree()
        {
            var s = Session;
            return s != null && s.State == "done" ? s.Tree : null;
        }

        static bool Valid(Tree t, int id) { lock (t.Lock) return t.IsLive(id); }

        /// <summary>Opens an object with the node fields; the caller adds more and closes it.</summary>
        static void NodeJson(Json j, Tree t, int c)
        {
            j.Obj().P("id", c).P("n", t.Name(c)).P("f", (long)t.Flags[c]).P("s", t.Size[c]).P("a", t.Alloc[c])
             .P("m", JsTime(t.Mtime[c])).P("at", (long)t.Attr[c]);
            if ((t.Flags[c] & Tree.F_DIR) != 0) j.P("fi", t.Files[c]).P("di", t.Dirs[c]).P("c", t.NChild[c] > 0);
            else j.P("e", t.Ext[c]);
        }

        // ---------------------------------------------------------------- API

        void Api(string name, HttpListenerRequest req, HttpListenerResponse res)
        {
            if (SetupMode)
            {
                switch (name)
                {
                    case "hello": Ok(res, new Json().Obj().P("app", "tatami-setup").P("version", Program.Version).EndObj()); return;
                    case "ping": Ok(res, new Json().Obj().P("ok", true).EndObj()); return;
                    case "setup-info": Ok(res, Setup.Info()); return;
                    case "setup-install":
                        {
                            var b = Body(req);
                            try
                            {
                                string exe = Setup.Install(Json.B(b, "desktop", true), Json.B(b, "startMenu", true), Json.B(b, "context", true));
                                Ok(res, new Json().Obj().P("ok", true).P("exe", exe).EndObj());
                            }
                            catch (Exception e) { Fail(res, 500, "Install failed: " + e.Message); }
                            return;
                        }
                    case "setup-launch": Setup.Launch(); Ok(res, new Json().Obj().P("ok", true).EndObj()); return;
                }
                Fail(res, 404, "Not available in setup"); return;
            }
            switch (name)
            {
                case "hello": Ok(res, new Json().Obj().P("app", "tatami").P("version", Program.Version).EndObj()); return;
                case "ping": Ok(res, new Json().Obj().P("ok", true).EndObj()); return;
                case "startup": Ok(res, new Json().Obj().P("scan", Gate.TakePendingArg()).EndObj()); return;
                case "history-clear": Ok(res, new Json().Obj().P("deleted", History.Clear()).EndObj()); return;
                case "drives": Ok(res, Drives()); return;
                case "scan": StartScan(Body(req), res); return;
                case "cancel": { var s = Session; if (s != null) s.Cancel(); Ok(res, new Json().Obj().P("ok", true).EndObj()); return; }
                case "status": Ok(res, Status()); return;
                case "exts": Ok(res, ExtTable()); return;
                case "system": Ok(res, SystemInfo()); return;
                case "load":
                    {
                        string f = Json.S(Body(req), "path", null) ?? Dialogs.OpenFile("Open a saved scan", "Tatami scan", "tatami",
                            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));
                        if (f == null) { Ok(res, new Json().Obj().P("cancelled", true).EndObj()); return; }
                        Tree lt;
                        try { lt = Tree.Load(f); lt.SortAll(); }
                        catch (Exception e) { Fail(res, 400, "Couldn't open that scan: " + e.Message); return; }
                        lock (scanLock)
                        {
                            var old = Session; if (old != null) old.Cancel();
                            Session = Session.FromTree(lt, f);
                        }
                        Ok(res, new Json().Obj().P("ok", true).EndObj()); return;
                    }
                case "open-special":
                    {
                        string what = Json.S(Body(req), "what", "");
                        string cmd = null, arg = null;
                        switch (what)
                        {
                            case "recycle": cmd = "explorer.exe"; arg = "shell:RecycleBinFolder"; break;
                            case "storage": cmd = "ms-settings:storagesense"; break;
                            case "cleanmgr": cmd = "cleanmgr.exe"; break;
                            case "sysprops": cmd = "SystemPropertiesAdvanced.exe"; break;
                            case "protection": cmd = "SystemPropertiesProtection.exe"; break;
                        }
                        if (cmd == null) { Fail(res, 400, "Unknown target"); return; }
                        try { System.Diagnostics.Process.Start(cmd, arg ?? ""); }
                        catch (Exception e) { Fail(res, 500, "Windows couldn't open it: " + e.Message); return; }
                        Ok(res, new Json().Obj().P("ok", true).EndObj()); return;
                    }
                case "pick-folder":
                    {
                        string p = Dialogs.PickFolder("Choose a folder to scan", Environment.GetFolderPath(Environment.SpecialFolder.UserProfile));
                        Ok(res, new Json().Obj().P("path", p).EndObj()); return;
                    }
            }
            var t = DoneTree();
            if (t == null) { Fail(res, 409, "No scan loaded"); return; }
            if (t.Busy) { Fail(res, 409, "Tatami is rescanning a folder. Try again in a moment."); return; }
            switch (name)
            {
                case "summary": Ok(res, Summary(t)); return;
                case "children": Children(t, req, res); return;
                case "node": NodeInfo(t, QI(req, "id", 0), res); return;
                case "find": FindPath(t, Q(req, "path", ""), res); return;
                case "treemap": TreemapBin(t, req, res); return;
                case "types": Types(t, QI(req, "id", 0), res); return;
                case "files": Files(t, req, res); return;
                case "metric": SetMetric(t, Body(req), res); return;
                case "names":
                    {
                        var j = new Json().Arr();
                        lock (t.Lock)
                            foreach (long l in Json.Ls(Body(req), "ids"))
                            {
                                int i = (int)l;
                                if (i < 0 || i >= t.Count) continue;
                                j.Obj().P("id", i).P("n", i == 0 ? t.RootPath : t.Name(i)).P("s", t.Size[i]).P("a", t.Alloc[i]).EndObj();
                            }
                        Ok(res, j.EndArr()); return;
                    }
                case "open": case "reveal": case "props": case "delete":
                    Actions.Handle(this, t, name, Body(req), res); return;
                case "export": Export(t, req, res); return;
                case "dupes":
                    {
                        var d = Session.Dupes;
                        if (d == null) { Ok(res, new Json().Obj().P("state", "idle").EndObj()); return; }
                        Ok(res, d.ToJson(Math.Max(1, Math.Min(20000, QI(req, "limit", 2000))))); return;
                    }
                case "dupes-start":
                    {
                        var b = Body(req);
                        int id = (int)Json.L(b, "id", 0);
                        if (!Valid(t, id) || !t.IsDir(id)) { Fail(res, 404, "Folder no longer exists"); return; }
                        var s = Session;
                        lock (scanLock)
                        {
                            var old = s.Dupes; if (old != null) old.Cancel = true;
                            s.Dupes = Dupes.Start(t, id, Json.L(b, "min", 1L << 20));
                        }
                        Ok(res, new Json().Obj().P("ok", true).EndObj()); return;
                    }
                case "dupes-cancel":
                    {
                        var d = Session.Dupes; if (d != null) d.Cancel = true;
                        Ok(res, new Json().Obj().P("ok", true).EndObj()); return;
                    }
                case "insights":
                    {
                        int id = QI(req, "id", 0);
                        if (!Valid(t, id)) { Fail(res, 404, "Item no longer exists"); return; }
                        Ok(res, Insights.Build(Session, t, id)); return;
                    }
                case "rescan":
                    {
                        int id = (int)Json.L(Body(req), "id", -1);
                        if (!Valid(t, id) || !t.IsDir(id)) { Fail(res, 404, "Folder no longer exists"); return; }
                        string p = t.Path(id);
                        if (!Directory.Exists(p)) { lock (t.Lock) t.Remove(id); Fail(res, 404, "The folder is gone from the disk."); return; }
                        double secs = Session.Rescan(t, id);
                        Ok(res, new Json().Obj().P("ok", true).P("seconds", secs).EndObj()); return;
                    }
                case "save":
                    {
                        string target = Dialogs.SaveFile("Save scan", "Tatami scan " + DateTime.Now.ToString("yyyy-MM-dd HHmm") + ".tatami",
                            "Tatami scan", "tatami", Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));
                        if (target == null) { Ok(res, new Json().Obj().P("cancelled", true).EndObj()); return; }
                        lock (t.Lock) t.Save(target);
                        Ok(res, new Json().Obj().P("path", target).EndObj()); return;
                    }
            }
            Fail(res, 404, "Unknown API " + name);
        }

        Json Drives()
        {
            var j = new Json().Arr();
            foreach (var d in DriveInfo.GetDrives())
            {
                string root = d.Name;
                uint type = Native.GetDriveTypeW(root);
                if (type == 5 || type == 1) continue;      // CD-ROM, no root dir
                var label = new StringBuilder(261); var fs = new StringBuilder(261);
                uint serial, maxc, flags;
                bool ok = Native.GetVolumeInformationW(root, label, 261, out serial, out maxc, out flags, fs, 261);
                ulong free, total, tfree;
                if (!ok || !Native.GetDiskFreeSpaceExW(root, out free, out total, out tfree)) continue;
                j.Obj().P("root", root).P("label", label.ToString()).P("fs", fs.ToString())
                 .P("type", type == 2 ? "removable" : type == 4 ? "network" : type == 6 ? "ram" : "fixed")
                 .P("total", (long)total).P("free", (long)tfree).EndObj();
            }
            return j.EndArr();
        }

        void StartScan(Dictionary<string, object> b, HttpListenerResponse res)
        {
            string path = Json.S(b, "path", "");
            string norm;
            try { norm = Session.NormalizePath(path); }
            catch (Exception) { Fail(res, 400, "That isn't a valid folder path."); return; }
            if (!Directory.Exists(norm)) { Fail(res, 400, "Folder not found: " + norm); return; }
            lock (scanLock)
            {
                var old = Session;
                if (old != null && (old.State == "scanning" || old.State == "finishing" || old.State == "elevating")) old.Cancel();
                if (old != null && old.Dupes != null) old.Dupes.Cancel = true;
                var s = new Session();
                s.Start(norm, true, Json.B(b, "admin"));
                Session = s;
            }
            Ok(res, new Json().Obj().P("ok", true).P("path", norm).EndObj());
        }

        Json Status()
        {
            var s = Session;
            var j = new Json().Obj();
            if (s == null) return j.P("state", "idle").EndObj();
            j.P("state", s.State).P("path", s.Path).P("error", s.Error).P("admin", s.Admin);
            j.P("files", s.Files).P("dirs", s.Dirs).P("bytes", s.Bytes).P("denied", s.Denied)
             .P("seconds", s.Seconds).P("current", s.Current);
            if (s.Tree != null) j.P("driveUsed", s.Tree.DriveTotal - s.Tree.DriveFree);
            else if (s.DriveUsed > 0) j.P("driveUsed", s.DriveUsed);
            return j.EndObj();
        }

        static Json SystemInfo()
        {
            var j = new Json().Obj();
            try
            {
                using (var k = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\DWM"))
                {
                    object v = k == null ? null : k.GetValue("AccentColor");
                    if (v is int)
                    {
                        uint abgr = unchecked((uint)(int)v);
                        j.P("accent", string.Format("#{0:x2}{1:x2}{2:x2}", abgr & 0xff, (abgr >> 8) & 0xff, (abgr >> 16) & 0xff));
                    }
                }
                using (var k = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"))
                {
                    object v = k == null ? null : k.GetValue("AppsUseLightTheme");
                    if (v is int) j.P("light", (int)v != 0);
                }
            }
            catch { }
            j.P("admin", Native.IsUserAnAdmin()).P("version", Program.Version)
             .P("user", Environment.GetFolderPath(Environment.SpecialFolder.UserProfile));
            return j.EndObj();
        }

        Json ExtTable()
        {
            var j = new Json().Obj().Key("categories").Arr();
            foreach (var c in Tatami.ExtTable.Categories) j.Val(c);
            j.EndArr();
            var t = Session != null ? Session.Tree : null;
            j.Key("names").Arr();
            if (t != null) foreach (var n in t.Exts.NameArray()) j.Val(n);
            j.EndArr().Key("cats").Arr();
            if (t != null) foreach (var c in t.Exts.CategoryArray()) j.Val(c);
            return j.EndArr().EndObj();
        }

        Json Summary(Tree t)
        {
            long used = t.DriveTotal - t.DriveFree;
            bool wholeDrive = t.RootPath.Length <= 3;
            return new Json().Obj().P("path", t.RootPath).P("volume", t.Volume).P("total", t.DriveTotal).P("free", t.DriveFree)
                .P("used", used).P("size", t.Size[0]).P("alloc", t.Alloc[0]).P("files", t.Files[0]).P("dirs", t.Dirs[0])
                .P("seconds", t.ScanSeconds).P("method", t.Method).P("bySize", t.BySize).P("wholeDrive", wholeDrive)
                .P("unaccounted", wholeDrive ? Math.Max(0, used - t.Alloc[0]) : 0)
                .P("denied", Session.Denied)
                .P("scannedAt", t.ScannedAt.ToString("yyyy-MM-dd HH:mm")).P("cluster", t.ClusterSize)
                .P("admin", Native.IsUserAnAdmin())
                .P("baseline", Session.Baseline != null ? Session.Baseline.When.ToString("d MMM yyyy, HH:mm") : null)
                .P("baselineLoading", Session.BaselineLoading).EndObj();
        }

        void Children(Tree t, HttpListenerRequest req, HttpListenerResponse res)
        {
            int id = QI(req, "id", 0);
            int limit = QI(req, "limit", 5000);
            string sort = Q(req, "sort", "size");
            bool asc = Q(req, "dir", "desc") == "asc";
            if (!Valid(t, id)) { Fail(res, 404, "Item no longer exists"); return; }
            var j = new Json().Obj().P("id", id).Key("items").Arr();
            lock (t.Lock)
            {
                var kids = t.Children(id).ToList();
                if (sort != "size" || asc) Sort(t, kids, sort, asc);
                int n = 0;
                foreach (int c in kids) { if (n++ >= limit) break; NodeJson(j, t, c); j.EndObj(); }
                j.EndArr().P("total", kids.Count);
            }
            Ok(res, j.EndObj());
        }

        static void Sort(Tree t, List<int> ids, string sort, bool asc)
        {
            Comparison<int> cmp;
            switch (sort)
            {
                case "name": cmp = (a, b) => string.Compare(t.Name(a), t.Name(b), StringComparison.CurrentCultureIgnoreCase); break;
                case "alloc": cmp = (a, b) => t.Alloc[a].CompareTo(t.Alloc[b]); break;
                case "files": cmp = (a, b) => t.Files[a].CompareTo(t.Files[b]); break;
                case "dirs": cmp = (a, b) => t.Dirs[a].CompareTo(t.Dirs[b]); break;
                case "modified": cmp = (a, b) => t.Mtime[a].CompareTo(t.Mtime[b]); break;
                case "type": cmp = (a, b) => string.Compare(t.Exts.Name(t.IsDir(a) ? 0 : t.Ext[a]), t.Exts.Name(t.IsDir(b) ? 0 : t.Ext[b]), StringComparison.Ordinal); break;
                default: cmp = (a, b) => t.Size[a].CompareTo(t.Size[b]); break;
            }
            if (asc) ids.Sort(cmp); else ids.Sort((a, b) => cmp(b, a));
        }

        void NodeInfo(Tree t, int id, HttpListenerResponse res)
        {
            if (!Valid(t, id)) { Fail(res, 404, "Item no longer exists"); return; }
            var j = new Json().Obj().Key("node");
            lock (t.Lock)
            {
                NodeJson(j, t, id);
                j.P("path", t.Path(id)).P("parent", id == 0 ? -1 : t.Parent[id]);
                j.Key("chain").Arr();
                var chain = new List<int>();
                for (int p = id; ; p = t.Parent[p]) { chain.Add(p); if (p == 0) break; }
                chain.Reverse();
                foreach (int c in chain) j.Obj().P("id", c).P("n", c == 0 ? t.RootPath : t.Name(c)).EndObj();
                j.EndArr();
                long parentSize = id == 0 ? t.Metric(0) : t.Metric(t.Parent[id]);
                j.P("pctParent", parentSize > 0 ? (double)t.Metric(id) / parentSize : 0);
                j.P("pctRoot", t.Metric(0) > 0 ? (double)t.Metric(id) / t.Metric(0) : 0);
                j.EndObj();
            }
            Ok(res, j.EndObj());
        }

        void FindPath(Tree t, string path, HttpListenerResponse res)
        {
            int id = Resolve(t, path);
            Ok(res, new Json().Obj().P("id", id).EndObj());
        }

        public static int Resolve(Tree t, string path)
        {
            path = path.Trim().TrimEnd('\\');
            string root = t.RootPath.TrimEnd('\\');
            if (string.Equals(path, root, StringComparison.OrdinalIgnoreCase)) return 0;
            if (!path.StartsWith(root + "\\", StringComparison.OrdinalIgnoreCase)) return -1;
            int cur = 0;
            lock (t.Lock)
                foreach (var part in path.Substring(root.Length + 1).Split('\\'))
                {
                    int found = -1;
                    foreach (int c in t.Children(cur))
                        if (string.Equals(t.Name(c), part, StringComparison.OrdinalIgnoreCase)) { found = c; break; }
                    if (found < 0) return -1;
                    cur = found;
                }
            return cur;
        }

        void TreemapBin(Tree t, HttpListenerRequest req, HttpListenerResponse res)
        {
            int id = QI(req, "id", 0);
            int w = Math.Max(1, Math.Min(8192, QI(req, "w", 800))), h = Math.Max(1, Math.Min(8192, QI(req, "h", 600)));
            if (!Valid(t, id)) { Fail(res, 404, "Item no longer exists"); return; }
            string color = Q(req, "color", "type");
            int mode = color == "age" ? Treemap.C_AGE : color == "growth" ? Treemap.C_GROWTH : Treemap.C_TYPE;
            var data = Treemap.Build(t, id, w, h, QD(req, "dpr", 1), t.BySize, mode, Session.Baseline);
            res.AddHeader("Cache-Control", "no-store");
            Send(res, 200, "application/octet-stream", data);
        }

        void SetMetric(Tree t, Dictionary<string, object> b, HttpListenerResponse res)
        {
            bool bySize = Json.B(b, "bySize", true);
            lock (t.Lock)
            {
                if (t.BySize != bySize) { t.BySize = bySize; t.SortAll(); }
            }
            Ok(res, new Json().Obj().P("ok", true).EndObj());
        }

        /// <summary>Size per extension inside a folder (the WizTree "file types" panel).</summary>
        void Types(Tree t, int id, HttpListenerResponse res)
        {
            if (!Valid(t, id)) { Fail(res, 404, "Item no longer exists"); return; }
            int ne = t.Exts.Count;
            var size = new long[ne]; var alloc = new long[ne]; var count = new int[ne];
            lock (t.Lock)
            {
                Walk(t, id, (c) =>
                {
                    int e = t.Ext[c]; if (e >= ne) return;
                    count[e]++;
                    if ((t.Flags[c] & Tree.F_HARDLINK) == 0) { size[e] += t.Size[c]; alloc[e] += t.Alloc[c]; }
                });
            }
            var order = Enumerable.Range(0, ne).Where(e => count[e] > 0)
                .OrderByDescending(e => t.BySize ? size[e] : alloc[e]).ToList();
            var j = new Json().Arr();
            var cats = t.Exts.CategoryArray(); var names = t.Exts.NameArray();
            foreach (int e in order)
                j.Obj().P("e", e).P("n", names[e]).P("cat", cats[e]).P("s", size[e]).P("a", alloc[e]).P("c", count[e]).EndObj();
            Ok(res, j.EndArr());
        }

        /// <summary>Visit every live file below a folder.</summary>
        static void Walk(Tree t, int root, Action<int> file)
        {
            var stack = new Stack<int>();
            stack.Push(root);
            while (stack.Count > 0)
            {
                int d = stack.Pop();
                int s = t.First[d], n = t.NChild[d];
                for (int k = 0; k < n; k++)
                {
                    int c = s + k;
                    byte f = t.Flags[c];
                    if ((f & Tree.F_DELETED) != 0) continue;
                    if ((f & Tree.F_DIR) != 0) stack.Push(c); else file(c);
                }
            }
        }

        /// <summary>Flat file list (WizTree "File View"): largest files, optionally filtered.</summary>
        void Files(Tree t, HttpListenerRequest req, HttpListenerResponse res)
        {
            int id = QI(req, "id", 0);
            int limit = Math.Max(1, Math.Min(100000, QI(req, "limit", 1000)));
            string q = (Q(req, "q", "") ?? "").Trim();
            int ext = QI(req, "ext", -1), cat = QI(req, "cat", -1);
            long min = (long)QD(req, "min", 0);
            long olderThan = (long)QD(req, "older", 0);   // JS ms timestamp: only files modified before
            bool dirs = Q(req, "dirs", "0") == "1";
            string sort = Q(req, "sort", "size");
            bool asc = Q(req, "dir", "desc") == "asc";
            if (!Valid(t, id)) { Fail(res, 404, "Item no longer exists"); return; }

            Func<string, string, bool> match = null;
            bool matchPath = q.Contains("\\");
            if (q.Length > 0)
            {
                var terms = q.Split(new[] { ';', '|' }, StringSplitOptions.RemoveEmptyEntries).Select(s => s.Trim()).Where(s => s.Length > 0).ToList();
                var tests = new List<Func<string, bool>>();
                foreach (var term in terms)
                {
                    if (term.IndexOfAny(new[] { '*', '?' }) >= 0)
                    {
                        var rx = new Regex("^" + Regex.Escape(term).Replace("\\*", ".*").Replace("\\?", ".") + "$",
                            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
                        tests.Add(s => rx.IsMatch(s));
                    }
                    else { string tt = term; tests.Add(s => s.IndexOf(tt, StringComparison.OrdinalIgnoreCase) >= 0); }
                }
                match = (name, path) => { foreach (var f in tests) if (f(matchPath ? path : name)) return true; return false; };
            }
            int[] cats = t.Exts.CategoryArray();
            long olderFt = olderThan > 0 ? olderThan * 10000 + 116444736000000000L : 0;
            var hits = new List<int>();
            lock (t.Lock)
            {
                Action<int> test = c =>
                {
                    if (t.Size[c] < min && t.Alloc[c] < min) return;
                    if (ext >= 0 && t.Ext[c] != ext) return;
                    if (cat >= 0 && (t.Ext[c] >= cats.Length || cats[t.Ext[c]] != cat)) return;
                    if (olderFt > 0 && t.Mtime[c] >= olderFt) return;
                    if (match != null && !match(t.Name(c), matchPath ? t.Path(c) : null)) return;
                    hits.Add(c);
                };
                if (dirs) WalkAll(t, id, test, true); else Walk(t, id, test);
                if (sort == "size" && !asc)
                {
                    var keys = hits.Select(c => -(t.BySize ? t.Size[c] : t.Alloc[c])).ToArray();
                    var arr = hits.ToArray(); Array.Sort(keys, arr); hits = arr.ToList();
                }
                else Sort(t, hits, sort, asc);
                var j = new Json().Obj().P("total", hits.Count);
                // total without double counting: hard links once; a folder only if no folder above it matched too
                long sum = 0;
                var hitSet = dirs ? new HashSet<int>(hits) : null;
                foreach (int c in hits)
                {
                    bool count;
                    if (dirs)
                    {
                        count = true;
                        for (int p = t.Parent[c]; p != id && p > 0; p = t.Parent[p]) if (hitSet.Contains(p)) { count = false; break; }
                    }
                    else count = (t.Flags[c] & Tree.F_HARDLINK) == 0;
                    if (count) sum += t.BySize ? t.Size[c] : t.Alloc[c];
                }
                j.P("sum", sum).Key("items").Arr();
                foreach (int c in hits.Take(limit))
                {
                    NodeJson(j, t, c);
                    j.P("path", t.Path(c)).EndObj();
                }
                Ok(res, j.EndArr().EndObj());
            }
        }

        static void WalkAll(Tree t, int root, Action<int> visit, bool dirsOnly)
        {
            var stack = new Stack<int>();
            stack.Push(root);
            while (stack.Count > 0)
            {
                int d = stack.Pop();
                int s = t.First[d], n = t.NChild[d];
                for (int k = 0; k < n; k++)
                {
                    int c = s + k;
                    byte f = t.Flags[c];
                    if ((f & Tree.F_DELETED) != 0) continue;
                    if ((f & Tree.F_DIR) != 0) { stack.Push(c); visit(c); }
                    else if (!dirsOnly) visit(c);
                }
            }
        }

        void Export(Tree t, HttpListenerRequest req, HttpListenerResponse res)
        {
            int id = QI(req, "id", 0);
            string target = Q(req, "to", "");
            bool filesOnly = Q(req, "files", "0") == "1";
            if (!Valid(t, id)) { Fail(res, 404, "Item no longer exists"); return; }
            if (string.IsNullOrEmpty(target))
            {
                string nm = id == 0 ? t.RootPath.Replace(":", "").Replace("\\", " ").Trim() : t.Name(id);
                target = Dialogs.SaveFile("Export to CSV", "Tatami - " + nm + ".csv", "CSV spreadsheet", "csv",
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));
                if (target == null) { Ok(res, new Json().Obj().P("cancelled", true).EndObj()); return; }
            }
            int rows = 0;
            lock (t.Lock)
                using (var w = new StreamWriter(target, false, new UTF8Encoding(true)))
                {
                    w.WriteLine("Path,Type,Size,Size on disk,Files,Folders,Modified,Attributes");
                    var stack = new Stack<KeyValuePair<int, string>>();
                    stack.Push(new KeyValuePair<int, string>(id, t.Path(id)));
                    while (stack.Count > 0)
                    {
                        var kv = stack.Pop();
                        int d = kv.Key;
                        bool dir = t.IsDir(d);
                        if (!(filesOnly && dir))
                        {
                            w.WriteLine("\"{0}\",{1},{2},{3},{4},{5},{6},{7}", kv.Value.Replace("\"", "\"\""), dir ? "Folder" : "File",
                                t.Size[d], t.Alloc[d], dir ? t.Files[d] : 0, dir ? t.Dirs[d] : 0,
                                t.Mtime[d] > 0 ? DateTime.FromFileTimeUtc(t.Mtime[d]).ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture) : "",
                                Attrs(t.Attr[d]));
                            rows++;
                        }
                        if (!dir) continue;
                        var kids = t.Children(d).ToList();
                        for (int k = kids.Count - 1; k >= 0; k--)
                            stack.Push(new KeyValuePair<int, string>(kids[k], kv.Value.TrimEnd('\\') + "\\" + t.Name(kids[k])));
                    }
                }
            Ok(res, new Json().Obj().P("ok", true).P("rows", rows).P("path", target).EndObj());
        }

        public static string Attrs(uint a)
        {
            var sb = new StringBuilder();
            if ((a & Native.ATTR_READONLY) != 0) sb.Append('R');
            if ((a & Native.ATTR_HIDDEN) != 0) sb.Append('H');
            if ((a & Native.ATTR_SYSTEM) != 0) sb.Append('S');
            if ((a & Native.ATTR_ARCHIVE) != 0) sb.Append('A');
            if ((a & Native.ATTR_COMPRESSED) != 0) sb.Append('C');
            if ((a & Native.ATTR_ENCRYPTED) != 0) sb.Append('E');
            if ((a & Native.ATTR_SPARSE) != 0) sb.Append('P');
            if ((a & Native.ATTR_REPARSE) != 0) sb.Append('L');
            if ((a & Native.ATTR_OFFLINE) != 0 || (a & Native.ATTR_RECALL_ON_DATA) != 0) sb.Append('O');
            return sb.ToString();
        }
    }
}
