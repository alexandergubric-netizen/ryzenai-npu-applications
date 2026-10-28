using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;

namespace Postura
{
    /// <summary>
    /// The FastFlowLM server shared with Washi, Morph, Sensei and Kaizen 5S (same file and rules as their flmshare.py).
    /// One `flm serve` on 127.0.0.1:52625 serves whichever app is open; a request naming another model makes FastFlowLM
    /// swap models in place, so a model change never needs a restart. Every app starts it the same way (the model's
    /// full 32k context, the user's power mode), and the last app that uses it stops it, so one app closing never
    /// pulls the AI away from another. Bookkeeping: %TEMP%\ryzenai-apps-flm.json
    ///   {"server": pid of the flm.exe an app started, "port": 52625, "pmode": "...", "users": {"Postura": pid, ...}}
    /// </summary>
    static class FlmShare
    {
        public const int CtxLen = 32768;
        public static readonly string[] Pmodes = { "powersaver", "balanced", "performance", "turbo" };
        const string App = "Postura";
        static readonly string FilePath = Path.Combine(Path.GetTempPath(), "ryzenai-apps-flm.json");
        static readonly string[] AppImages = { "python.exe", "pythonw.exe", "postura.exe" };
        static readonly object fileLock = new object();
        static readonly JavaScriptSerializer Ser = new JavaScriptSerializer();

        [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr OpenProcess(int access, bool inherit, int pid);
        [DllImport("kernel32.dll", SetLastError = true)] static extern bool CloseHandle(IntPtr h);
        [DllImport("kernel32.dll", SetLastError = true)] static extern bool GetExitCodeProcess(IntPtr h, out int code);
        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        static extern bool QueryFullProcessImageName(IntPtr h, int flags, StringBuilder buf, ref int size);

        /// <summary>File name (lower case) of a running process, or null when it is gone.</summary>
        static string Image(object pidObj)
        {
            int pid;
            try { pid = Convert.ToInt32(pidObj); } catch { return null; }
            if (pid <= 0) return null;
            IntPtr h = OpenProcess(0x1000, false, pid);   // PROCESS_QUERY_LIMITED_INFORMATION
            if (h == IntPtr.Zero) return null;
            try
            {
                int code;
                if (!GetExitCodeProcess(h, out code) || code != 259) return null;   // STILL_ACTIVE
                var buf = new StringBuilder(1024);
                int n = buf.Capacity;
                if (!QueryFullProcessImageName(h, 0, buf, ref n)) return null;
                return Path.GetFileName(buf.ToString()).ToLowerInvariant();
            }
            finally { CloseHandle(h); }
        }

        static Dictionary<string, object> Read()
        {
            try { return Ser.DeserializeObject(File.ReadAllText(FilePath)) as Dictionary<string, object> ?? new Dictionary<string, object>(); }
            catch { return new Dictionary<string, object>(); }
        }

        static void Write(Dictionary<string, object> d)
        {
            string tmp = FilePath + "." + Process.GetCurrentProcess().Id + ".tmp";
            try
            {
                File.WriteAllText(tmp, Ser.Serialize(d));
                if (File.Exists(FilePath)) File.Replace(tmp, FilePath, null); else File.Move(tmp, FilePath);
            }
            catch { try { File.Delete(tmp); } catch { } }
        }

        static Dictionary<string, object> LiveUsers(Dictionary<string, object> d, string skip)
        {
            var live = new Dictionary<string, object>();
            object u;
            var users = d.TryGetValue("users", out u) ? u as Dictionary<string, object> : null;
            if (users != null)
                foreach (var kv in users)
                    if (kv.Key != skip && Array.IndexOf(AppImages, Image(kv.Value)) >= 0) live[kv.Key] = kv.Value;
            return live;
        }

        public static string Pmode(string p) { return Array.IndexOf(Pmodes, p) >= 0 ? p : "performance"; }

        /// <summary>Start the shared server with the full context and the chosen power mode, and record it.</summary>
        public static Process Start(string exe, string model, int port, string pmode)
        {
            var proc = Process.Start(new ProcessStartInfo(exe, "serve " + model + " --port " + port + " --pmode " + Pmode(pmode) + " --ctx-len " + CtxLen)
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = false });
            lock (fileLock)
            {
                var d = Read();
                var users = LiveUsers(d, null);
                users[App] = Process.GetCurrentProcess().Id;
                d["server"] = proc.Id; d["port"] = port; d["pmode"] = Pmode(pmode); d["users"] = users;
                Write(d);
            }
            return proc;
        }

        /// <summary>Postura uses the server (started by itself or by another app).</summary>
        public static void Join()
        {
            lock (fileLock)
            {
                var d = Read();
                var users = LiveUsers(d, null);
                users[App] = Process.GetCurrentProcess().Id;
                d["users"] = users;
                Write(d);
            }
        }

        public static bool OthersUsing() { return LiveUsers(Read(), App).Count > 0; }

        /// <summary>The power mode the recorded server runs in, or null if no app started the running one.</summary>
        public static string ServerPmode()
        {
            var d = Read();
            object pid, p;
            if (!d.TryGetValue("server", out pid) || Image(pid) != "flm.exe") return null;
            return d.TryGetValue("pmode", out p) ? p as string : null;
        }

        /// <summary>Stop the server an app started (never a FastFlowLM someone started by hand).</summary>
        public static bool StopServer()
        {
            int pid;
            lock (fileLock)
            {
                var d = Read();
                object o;
                if (!d.TryGetValue("server", out o) || Image(o) != "flm.exe") return false;
                pid = Convert.ToInt32(o);
                try { Process.GetProcessById(pid).Kill(); } catch { return false; }
                d.Remove("server");
                Write(d);
            }
            for (int i = 0; i < 40 && Image(pid) != null; i++) System.Threading.Thread.Sleep(250);
            return true;
        }

        /// <summary>Postura no longer needs the server; the last app to leave stops it.</summary>
        public static bool Leave()
        {
            Dictionary<string, object> users;
            lock (fileLock)
            {
                var d = Read();
                users = LiveUsers(d, App);
                d["users"] = users;
                Write(d);
            }
            return users.Count == 0 && StopServer();
        }
    }
}
