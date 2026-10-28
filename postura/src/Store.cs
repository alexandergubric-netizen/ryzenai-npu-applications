using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Web.Script.Serialization;

namespace Postura
{
    /// <summary>
    /// Settings, UI state and daily stats in one small JSON file: %LOCALAPPDATA%\Postura\postura.json.
    /// Everything is guarded by one lock; the file is rewritten (atomically) at most every few seconds.
    /// </summary>
    static class Store
    {
        public static readonly object Lock = new object();
        static readonly JavaScriptSerializer Ser = new JavaScriptSerializer();
        static Dictionary<string, object> settings, ui, days;
        static bool dirty;
        static DateTime lastSave = DateTime.MinValue;

        static readonly Dictionary<string, object> Defaults = new Dictionary<string, object> {
            { "eyeEnabled", true }, { "eyeInterval", 20 }, { "eyeSeconds", 20 },
            { "idleReset", true }, { "skipBusy", true }, { "sound", false }, { "autoTimer", false }, { "remindStyle", "both" },
            { "moveEnabled", false }, { "moveInterval", 45 },
            { "autostart", true }, { "theme", "system" }, { "motion", "full" },
            // set by the installer after its hardware check; "" = this PC runs Postura without the assistant
            { "aiEngine", "" }, { "aiModel", "" }, { "aiEnabled", false }, { "aiPmode", "performance" }
        };

        public static string DataDir
        {
            get
            {
                string d = Environment.GetEnvironmentVariable("POSTURA_HOME");
                if (string.IsNullOrEmpty(d)) d = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Postura");
                Directory.CreateDirectory(d);
                return d;
            }
        }

        static string FilePath { get { return Path.Combine(DataDir, "postura.json"); } }

        public static void Load()
        {
            lock (Lock)
            {
                settings = new Dictionary<string, object>(Defaults);
                ui = new Dictionary<string, object>();
                days = new Dictionary<string, object>();
                try
                {
                    if (!File.Exists(FilePath)) return;
                    var root = Ser.Deserialize<Dictionary<string, object>>(File.ReadAllText(FilePath, Encoding.UTF8));
                    var s = Dict(root, "settings");
                    foreach (var kv in s) if (Defaults.ContainsKey(kv.Key) && Valid(kv.Key, kv.Value)) settings[kv.Key] = kv.Value;
                    // 1.0.2 and older: "start the floating timer straight away" becomes the card style
                    if (!s.ContainsKey("remindStyle") && Bool("autoTimer")) settings["remindStyle"] = "card";
                    ui = Dict(root, "ui");
                    days = Dict(root, "days");
                }
                catch (Exception e) { Program.Log("load settings: " + e.Message); }
            }
        }

        static Dictionary<string, object> Dict(Dictionary<string, object> d, string k)
        {
            object v;
            return d != null && d.TryGetValue(k, out v) && v is Dictionary<string, object> ? (Dictionary<string, object>)v : new Dictionary<string, object>();
        }

        static bool Valid(string key, object v)
        {
            object def = Defaults[key];
            if (def is bool) return v is bool;
            if (def is int)
            {
                if (!(v is int)) return false;
                int i = (int)v;
                switch (key)
                {
                    case "eyeInterval": return i >= 5 && i <= 120;
                    case "eyeSeconds": return i >= 10 && i <= 120;
                    case "moveInterval": return i >= 15 && i <= 180;
                }
                return true;
            }
            if (key == "theme") return v is string && new[] { "system", "light", "dark" }.Contains((string)v);
            if (key == "motion") return v is string && new[] { "full", "reduced" }.Contains((string)v);
            if (key == "remindStyle") return v is string && new[] { "notify", "card", "both" }.Contains((string)v);
            if (key == "aiEngine") return v is string && new[] { "", "flm", "foundry" }.Contains((string)v);
            if (key == "aiPmode") return v is string && FlmShare.Pmodes.Contains((string)v);
            return v is string;
        }

        public static bool Bool(string k) { lock (Lock) return settings[k] is bool && (bool)settings[k]; }
        public static int Int(string k) { lock (Lock) return settings[k] is int ? (int)settings[k] : (int)Defaults[k]; }
        public static string Str(string k) { lock (Lock) return settings[k] as string ?? ""; }

        /// <summary>Merge validated keys; returns the keys that changed.</summary>
        public static List<string> SetSettings(Dictionary<string, object> patch)
        {
            var changed = new List<string>();
            lock (Lock)
            {
                foreach (var kv in patch)
                {
                    if (!Defaults.ContainsKey(kv.Key)) continue;
                    object v = kv.Value;
                    if (v is decimal || v is double) v = Convert.ToInt32(v);
                    if (!Valid(kv.Key, v)) continue;
                    if (!Equals(settings[kv.Key], v)) { settings[kv.Key] = v; changed.Add(kv.Key); }
                }
                if (changed.Count > 0) dirty = true;
            }
            return changed;
        }

        /// <summary>UI-owned state (self-check answers, body height, light room …). Values are kept as sent.</summary>
        public static void SetUi(Dictionary<string, object> patch)
        {
            lock (Lock)
            {
                foreach (var kv in patch)
                {
                    if (kv.Key.Length > 40) continue;
                    if (kv.Value == null) ui.Remove(kv.Key); else ui[kv.Key] = kv.Value;
                }
                if (Ser.Serialize(ui).Length > 64 * 1024) throw new InvalidOperationException("UI state too large");
                dirty = true;
            }
        }

        static string Today { get { return DateTime.Now.ToString("yyyy-MM-dd"); } }

        /// <summary>Add to today's counters: eyeTaken, eyeReminded, moveReminded, activeSec.</summary>
        public static void Count(string key, int n = 1)
        {
            lock (Lock)
            {
                var d = Dict(days, Today);
                object v;
                d[key] = (d.TryGetValue(key, out v) && v is int ? (int)v : 0) + n;
                days[Today] = d;
                if (days.Count > 40)
                    foreach (var old in days.Keys.OrderBy(x => x).Take(days.Count - 40).ToList()) days.Remove(old);
                dirty = true;
            }
        }

        public static Dictionary<string, object> Snapshot()
        {
            lock (Lock)
            {
                var recent = new Dictionary<string, object>();
                for (int i = 6; i >= 0; i--)
                {
                    string k = DateTime.Now.AddDays(-i).ToString("yyyy-MM-dd");
                    recent[k] = Dict(days, k);
                }
                return new Dictionary<string, object> {
                    { "settings", new Dictionary<string, object>(settings) },
                    { "ui", new Dictionary<string, object>(ui) },
                    { "today", Dict(days, Today) },
                    { "week", recent }
                };
            }
        }

        public static string ToJson(object o) { return Ser.Serialize(o); }
        public static Dictionary<string, object> Parse(string s)
        {
            return string.IsNullOrWhiteSpace(s) ? new Dictionary<string, object>() : Ser.Deserialize<Dictionary<string, object>>(s);
        }

        /// <summary>Write if something changed (called every second by the reminder loop, and on exit with force).</summary>
        public static void Save(bool force = false)
        {
            string json;
            lock (Lock)
            {
                if (!dirty || (!force && (DateTime.Now - lastSave).TotalSeconds < 5)) return;
                json = Ser.Serialize(new Dictionary<string, object> { { "settings", settings }, { "ui", ui }, { "days", days } });
                dirty = false;
                lastSave = DateTime.Now;
            }
            try
            {
                string tmp = FilePath + ".tmp";
                File.WriteAllText(tmp, json, new UTF8Encoding(false));
                if (File.Exists(FilePath)) File.Replace(tmp, FilePath, null); else File.Move(tmp, FilePath);
            }
            catch (Exception e) { Program.Log("save: " + e.Message); }
        }
    }
}
