using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Threading;

[assembly: AssemblyTitle("Tatami")]
[assembly: AssemblyProduct("Tatami")]
[assembly: AssemblyDescription("See what fills your disk")]
[assembly: AssemblyCompany("Alexander Gubric")]
[assembly: AssemblyCopyright("© 2026 Alexander Gubric · MIT License")]
[assembly: AssemblyVersion("0.10.1.0")]
[assembly: AssemblyFileVersion("0.10.1.0")]
[assembly: AssemblyInformationalVersion("0.10.1")]

namespace Tatami
{
    static class Program
    {
        public const string Version = "0.10.1";
        public const int DefaultPort = 52695;
        public static bool NoHistory;    // CLI/test runs and the elevated helper don't write scan history

        public static string DataDirNoCreate
        {
            get
            {
                string d = Environment.GetEnvironmentVariable("TATAMI_HOME");
                return string.IsNullOrEmpty(d) ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Tatami") : d;
            }
        }

        public static string DataDir
        {
            get
            {
                string d = Environment.GetEnvironmentVariable("TATAMI_HOME");
                if (string.IsNullOrEmpty(d)) d = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Tatami");
                Directory.CreateDirectory(d);
                return d;
            }
        }

        public static void Log(string msg)
        {
            try { File.AppendAllText(Path.Combine(DataDir, "error.log"), DateTime.Now.ToString("s") + " " + msg + Environment.NewLine); } catch { }
        }

        [STAThread]
        static int Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "--bench") Native.AttachConsole(-1);
            if (args.Length > 0 && (args[0] == "--bench" || args[0] == "--roundtrip" || args[0] == "--elevated-scan")) NoHistory = true;
            try
            {
                if (args.Length >= 2 && args[0] == "--bench") return Bench(args[1]);
                if (args.Length >= 2 && args[0] == "--history-test")
                {
                    NoHistory = true;
                    var hs = new Session(); hs.Start(args[1], false);
                    History.Add(hs.Tree);
                    var b = History.Previous(hs.Tree.RootPath, DateTime.Now.AddMinutes(5));
                    Console.WriteLine("snapshots: " + History.List(hs.Tree.RootPath).Count + ", baseline dirs: " + (b == null ? -1 : b.Dirs.Count));
                    return 0;
                }
                if (args.Length >= 3 && args[0] == "--roundtrip") return RoundTrip(args[1], args[2]);
                if (args.Length >= 4 && args[0] == "--recycle-check")   // test: would the Recycle Bin take it? (writes the answer to a file)
                {
                    File.WriteAllText(args[3], Actions.RecycleProblem(args[1], long.Parse(args[2])) ?? "OK");
                    return 0;
                }
                if (args.Length >= 2 && args[0] == "--elevated-scan")
                    return Session.ElevatedMain(args[1], Arg(args, "--out"), Arg(args, "--progress"), Arg(args, "--cancel"));
                if (args.Contains("--uninstall")) return Setup.Uninstall(args.Contains("--quiet"));
                if (args.Contains("--install"))
                {
                    // silent per-user install with every option (for scripts): Start menu, desktop, Explorer menu
                    string exe = Setup.Install(!args.Contains("--no-desktop"), true, !args.Contains("--no-context"));
                    Console.WriteLine("Installed " + exe);
                    return 0;
                }
                string exeName = Path.GetFileNameWithoutExtension(Process.GetCurrentProcess().MainModule.FileName);
                if (args.Contains("--setup") || exeName.IndexOf("setup", StringComparison.OrdinalIgnoreCase) >= 0) return RunSetup(args);
                return Run(args);
            }
            catch (Exception e)
            {
                try { File.AppendAllText(Path.Combine(DataDir, "error.log"), DateTime.Now + " " + e + Environment.NewLine); } catch { }
                Console.Error.WriteLine(e);
                return 1;
            }
        }

        static string Arg(string[] args, string name)
        {
            int i = Array.IndexOf(args, name);
            return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
        }

        static int Run(string[] args)
        {
            int port = DefaultPort;
            int p;
            if (int.TryParse(Environment.GetEnvironmentVariable("TATAMI_PORT"), out p)) port = p;
            string web = Arg(args, "--web");
            bool noWindow = args.Contains("--no-window");
            string scan = args.FirstOrDefault(a => !a.StartsWith("--") && a != web && (Directory.Exists(a) || (a.Length == 2 && a[1] == ':')));

            // this user's Tatami is already running: it hands out a one-time launch key (and takes the folder to scan)
            string running = WebGate.FindRunning("Tatami", "X-Tatami", DataDirNoCreate, scan);
            if (running != null) { OpenWindow(running); return 0; }

            var gate = new WebGate("Tatami", "X-Tatami", DataDir) { Port = WebGate.PickPort(port) };
            var srv = new Server(gate, web != null ? Path.GetFullPath(web) : null);
            srv.Start();
            gate.Publish();
            try
            {
                if (noWindow)
                {
                    Thread.Sleep(Timeout.Infinite);
                    return 0;
                }
                var win = OpenWindow(gate.LaunchUrl(scan));
                if (win != null) { try { win.WaitForExit(); } catch { } }
                // Edge may hand the window to an already running Edge process; wait until the page stops pinging.
                while ((DateTime.Now - srv.LastSeen).TotalSeconds < 15) Thread.Sleep(1000);
                srv.Stop();
                return 0;
            }
            finally { gate.Withdraw(); }
        }

        /// <summary>The installer wizard: same server, setup.html as the page, its own port and window profile.</summary>
        static int RunSetup(string[] args)
        {
            int port = DefaultPort + 1;
            int p;
            if (int.TryParse(Environment.GetEnvironmentVariable("TATAMI_SETUP_PORT"), out p)) port = p;
            string web = Arg(args, "--web");
            var gate = new WebGate("TatamiSetup", "X-Tatami", Path.GetTempPath()) { Port = WebGate.PickPort(port) };
            var srv = new Server(gate, web != null ? Path.GetFullPath(web) : null) { SetupMode = true };
            srv.Start();
            if (args.Contains("--no-window"))
            {
                // tests: port and secret (this user's %TEMP%, like the discovery file) to get a launch key
                File.WriteAllText(Path.Combine(Path.GetTempPath(), "tatami-setup-port.txt"), gate.Port + " " + gate.Secret);
                Thread.Sleep(Timeout.Infinite); return 0;
            }
            var win = OpenWindow(gate.LaunchUrl(), Path.Combine(Path.GetTempPath(), "TatamiSetupWindow"), "--window-size=760,600");
            if (win != null) { try { win.WaitForExit(); } catch { } }
            while ((DateTime.Now - srv.LastSeen).TotalSeconds < 6) Thread.Sleep(500);
            srv.Stop();
            try { Directory.Delete(Path.Combine(Path.GetTempPath(), "TatamiSetupWindow"), true); } catch { }
            return 0;
        }

        public static string EdgePath()
        {
            foreach (var hive in new[] { Microsoft.Win32.Registry.CurrentUser, Microsoft.Win32.Registry.LocalMachine })
            {
                try
                {
                    using (var k = hive.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"))
                    {
                        var v = k == null ? null : k.GetValue("") as string;
                        if (!string.IsNullOrEmpty(v) && File.Exists(v)) return v;
                    }
                }
                catch { }
            }
            foreach (var pf in new[] { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles) })
            {
                string e = Path.Combine(pf, @"Microsoft\Edge\Application\msedge.exe");
                if (File.Exists(e)) return e;
            }
            return null;
        }

        static Process OpenWindow(string url, string profile = null, string size = "--window-size=1400,900")
        {
            string edge = EdgePath();
            if (edge == null) { Process.Start(url); return null; }
            profile = profile ?? Path.Combine(DataDir, "window");
            var psi = new ProcessStartInfo(edge,
                "--app=\"" + url + "\" --user-data-dir=\"" + profile + "\" " + size + " --no-first-run " +
                "--no-default-browser-check --disable-features=Translate --disable-extensions");
            psi.UseShellExecute = false;
            return Process.Start(psi);
        }

        /// <summary>Test: run the elevated-helper code path without elevation, load its snapshot, compare.</summary>
        static int RoundTrip(string path, string dir)
        {
            Directory.CreateDirectory(dir);
            string snap = Path.Combine(dir, "rt.tatami"), prog = Path.Combine(dir, "rt.txt");
            int rc = Session.ElevatedMain(path, snap, prog, null);
            if (rc != 0) { Console.WriteLine("helper exit " + rc); return 1; }
            var a = new Session(); a.Start(path, false);
            var b = Tree.Load(snap); b.SortAll();
            var t = a.Tree;
            bool ok = b.Count == t.Count && b.Size[0] == t.Size[0] && b.Alloc[0] == t.Alloc[0] && b.Files[0] == t.Files[0] &&
                      b.Exts.Count == t.Exts.Count &&
                      string.Join("|", b.Children(0).Select(c => b.Name(c) + b.Size[c])) == string.Join("|", t.Children(0).Select(c => t.Name(c) + t.Size[c]));
            Console.WriteLine("snapshot {0} ({1}), progress: {2}", ok ? "OK" : "MISMATCH", Fmt.Bytes(new FileInfo(snap).Length), File.ReadAllText(prog));
            Console.WriteLine("live {0} nodes {1}; loaded {2} nodes {3}; last path {4}", t.Count, Fmt.Bytes(t.Size[0]), b.Count, Fmt.Bytes(b.Size[0]), b.Path(b.Count - 1));
            return ok ? 0 : 1;
        }

        static int Bench(string path)
        {
            var s = new Session();
            var gc0 = GC.GetTotalMemory(false);
            s.Start(path, true);
            while (s.State == "scanning" || s.State == "finishing") Thread.Sleep(100);
            if (s.State != "done") { Console.WriteLine("State: " + s.State + " " + s.Error); return 2; }
            var t = s.Tree;
            Console.WriteLine("Scanned {0} in {1:F2} s ({2})", t.RootPath, t.ScanSeconds, t.Method);
            Console.WriteLine("Nodes {0:N0}  files {1:N0}  folders {2:N0}  denied {3:N0}  exts {4:N0}",
                t.Count, t.Files[0], t.Dirs[0], s.Scanner.Denied, t.Exts.Count);
            Console.WriteLine("Size {0}  on disk {1}  drive used {2}", Fmt.Bytes(t.Size[0]), Fmt.Bytes(t.Alloc[0]),
                Fmt.Bytes(t.DriveTotal - t.DriveFree));
            int hl = 0; for (int i = 0; i < t.Count; i++) if ((t.Flags[i] & Tree.F_HARDLINK) != 0) hl++;
            Console.WriteLine("Hardlink duplicates {0:N0}   managed memory {1}", hl, Fmt.Bytes(GC.GetTotalMemory(true) - gc0));
            foreach (var sl in s.Scanner.Slow) Console.WriteLine("  slow: " + sl);
            foreach (int c in t.Children(0).Take(12))
                Console.WriteLine("  {0,12}  {1,12}  {2}", Fmt.Bytes(t.Size[c]), Fmt.Bytes(t.Alloc[c]), t.Name(c));
            var sw = Stopwatch.StartNew();
            var tm = Treemap.Build(t, 0, 1920, 1080, 1.5, true);
            Console.WriteLine("Treemap 1920x1080: {0:N0} records, {1}, {2} ms", tm.Length / 40, Fmt.Bytes(tm.Length), sw.ElapsedMilliseconds);
            return 0;
        }
    }

    static class Fmt
    {
        public static string Bytes(long b)
        {
            string[] u = { "B", "KB", "MB", "GB", "TB", "PB" };
            double v = b; int k = 0;
            while (Math.Abs(v) >= 1024 && k < u.Length - 1) { v /= 1024; k++; }
            return k == 0 ? b + " B" : v.ToString(v >= 100 ? "F0" : "F1") + " " + u[k];
        }
    }
}
