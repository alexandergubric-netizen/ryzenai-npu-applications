using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("Postura")]
[assembly: AssemblyProduct(Postura.Edition.DisplayName)]
[assembly: AssemblyDescription("Postura - healthy posture and 20-20-20 eye breaks")]
[assembly: AssemblyCompany("Alexander Gubric")]
[assembly: AssemblyCopyright("© 2026 Alexander Gubric · MIT License")]
[assembly: AssemblyVersion("1.0.4.0")]
[assembly: AssemblyFileVersion("1.0.3.0")]
[assembly: AssemblyInformationalVersion("1.0.4")]

namespace Postura
{
    static class Program
    {
        public const string Version = "1.0.4";
        public const int DefaultPort = 52697;
        public const int SetupPort = 52710;
        public static string OpenEventName { get { return @"Local\Postura-Open-" + InstanceKey; } }
        public static string QuitEventName { get { return @"Local\Postura-Quit-" + InstanceKey; } }
        /// <summary>Things a notification button may ask for (anything else in a postura: link just opens the window).</summary>
        public static readonly string[] Actions = { "open", "eye-start", "eye-snooze", "move-open", "move-done" };
        public static string ActionEventName(string action) { return @"Local\Postura-Act-" + action + "-" + InstanceKey; }

        /// <summary>One instance per user; a test copy with its own POSTURA_HOME counts as a separate instance.</summary>
        static string InstanceKey
        {
            get
            {
                string home = Environment.GetEnvironmentVariable("POSTURA_HOME");
                return Environment.UserName + (string.IsNullOrEmpty(home) ? "" : "-" + home.ToLowerInvariant().GetHashCode().ToString("x"));
            }
        }

        public static void Log(string msg)
        {
            try { File.AppendAllText(Path.Combine(Store.DataDir, "error.log"), DateTime.Now.ToString("s") + " " + msg + Environment.NewLine); } catch { }
        }

        [STAThread]
        static int Main(string[] args)
        {
            try
            {
                if (args.Contains("--uninstall")) return Setup.Uninstall(args.Contains("--quiet"));
                if (args.Contains("--install"))
                {
                    // silent install for IT: --ai adds the assistant only if the hardware check passes;
                    // --ai-no-engine uses an AI engine that is already there (no download, no admin prompt).
                    // Exit codes: 0 = installed, 2 = installed but the assistant could not be set up, 1 = not installed.
                    AiInstall.NoEngineInstall = args.Contains("--ai-no-engine");
                    bool ai = args.Contains("--ai") || AiInstall.NoEngineInstall;
                    AiInstall.Start(!args.Contains("--no-desktop"), true, !args.Contains("--no-autostart"), ai, ArgS(args, "--model"));
                    do Thread.Sleep(500); while (AiInstall.Running);
                    if (AiInstall.Error != "") { Log("silent install failed: " + AiInstall.Error); return 1; }
                    if (!args.Contains("--no-launch"))   // start the tray app (an already running one just stays)
                        try { Process.Start(new ProcessStartInfo(Setup.InstalledExe, "--tray") { UseShellExecute = false, WorkingDirectory = Setup.InstallDir }); } catch { }
                    if (ai && AiInstall.AiError != "") { Log("silent install: assistant not set up: " + AiInstall.AiError); return 2; }
                    return 0;
                }
                if (args.Contains("--quit")) { Signal(QuitEventName); return 0; }
#if DEV
                if (args.Contains("--break-test"))
                {
                    // shows only the break timer (for screenshots and tests)
                    Store.Load();
                    Application.EnableVisualStyles();
                    var h = new BreakHud(Math.Max(3, Arg(args, "--seconds", 20)), args.Contains("--prompt"));
                    h.FormClosed += (s, e) => Application.ExitThread();
                    string png = ArgS(args, "--png");
                    if (png != null)
                    {
                        // render a frame to a file after a moment (and, with --done, the finished state too)
                        var shot = new System.Windows.Forms.Timer { Interval = Arg(args, "--at", 1500) };
                        shot.Tick += (s, e) =>
                        {
                            shot.Stop();
                            using (var bmp = new System.Drawing.Bitmap(h.Width, h.Height))
                            {
                                h.DrawToBitmap(bmp, new System.Drawing.Rectangle(0, 0, h.Width, h.Height));
                                bmp.Save(png);
                            }
                            h.Close();
                        };
                        shot.Start();
                    }
                    Application.Run(h);
                    return 0;
                }
#endif
                string exeName = Path.GetFileNameWithoutExtension(Process.GetCurrentProcess().MainModule.FileName);
                if (args.Contains("--setup") || exeName.IndexOf("setup", StringComparison.OrdinalIgnoreCase) >= 0) return RunSetup(args);

                // a click on a notification arrives as "postura:eye-start" (protocol activation)
                string action = null;
                var link = args.FirstOrDefault(a => a.StartsWith(Toast.Scheme + ":", StringComparison.OrdinalIgnoreCase));
                if (link != null)
                {
                    action = link.Substring(Toast.Scheme.Length + 1).Trim('/', ' ').ToLowerInvariant();
                    if (!Actions.Contains(action)) action = "open";
                }
                bool tray = args.Contains("--tray") || (action != null && action != "open" && action != "move-open");
                bool created;
                using (var mutex = new Mutex(true, @"Local\Postura-App-" + InstanceKey, out created))
                {
                    if (!created)
                    {
                        if (action != null) Signal(ActionEventName(action));   // the running tray app does it
                        else if (!tray) Signal(OpenEventName);                // already running: show its window
                        return 0;
                    }
                    App.Run(!tray, WebDir(args), Dev && args.Contains("--serve"), action);
                    GC.KeepAlive(mutex);
                }
                return 0;
            }
            catch (Exception e)
            {
                Log(e.ToString());
                return 1;
            }
        }

        // Developer switches (--web: UI from disk, --serve: server without a window, --break-test) exist only in
        // builds made with build.ps1 -Dev; release installers ignore them.
#if DEV
        const bool Dev = true;
#else
        const bool Dev = false;
#endif

        static string WebDir(string[] args)
        {
            string web = Dev ? ArgS(args, "--web") : null;
            return web != null ? Path.GetFullPath(web) : null;
        }

        static void Signal(string name)
        {
            try { using (var ev = EventWaitHandle.OpenExisting(name)) ev.Set(); } catch { }
        }

        static string ArgS(string[] args, string name)
        {
            int i = Array.IndexOf(args, name);
            return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
        }

        static int Arg(string[] args, string name, int def)
        {
            int v; return int.TryParse(ArgS(args, name), out v) ? v : def;
        }

        /// <summary>The installer wizard: the same server with setup.html, its own port and window profile.</summary>
        static int RunSetup(string[] args)
        {
            Server srv = null;
            for (int port = SetupPort; port < SetupPort + 10 && srv == null; port++)
            {
                try
                {
                    var gate = new WebGate("PosturaSetup", "X-Postura", Path.GetTempPath()) { Port = port };
                    var s = new Server(gate, WebDir(args)) { SetupMode = true }; s.Start(); srv = s;
                }
                catch { }
            }
            if (srv == null) { Native.MessageBoxW(IntPtr.Zero, "Setup couldn't start (no free local port).", "Postura setup", 0x10); return 1; }
            if (args.Contains("--no-window"))
            {
                // tests: port and secret (this user's %TEMP%) to ask for a launch key
                File.WriteAllText(Path.Combine(Path.GetTempPath(), "postura-setup-port.txt"), srv.Port + " " + srv.Gate.Secret);
                Thread.Sleep(Timeout.Infinite); return 0;
            }
            string profile = Path.Combine(Path.GetTempPath(), "PosturaSetupWindow");
            var win = OpenWindow(srv.Gate.LaunchUrl(), profile, "--window-size=800,780");
            if (win != null) { try { win.WaitForExit(); } catch { } }
            // P5: closing the window must not kill a model download that is still running
            while ((DateTime.Now - srv.LastSeen).TotalSeconds < 6 || AiInstall.Running) Thread.Sleep(500);
            srv.Stop();
            try { Directory.Delete(profile, true); } catch { }
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

        /// <summary>
        /// Edge (part of every Windows 11) in app mode with its own small profile. Background networking, sync,
        /// component updates and translation are switched off: the window only ever talks to 127.0.0.1.
        /// </summary>
        public static Process OpenWindow(string url, string profile, string size)
        {
            string edge = EdgePath();
            if (edge == null) { Process.Start(url); return null; }
            var psi = new ProcessStartInfo(edge,
                "--app=\"" + url + "\" --user-data-dir=\"" + profile + "\" " + size + " --no-first-run " +
                "--no-default-browser-check --disable-extensions --disable-sync --disable-background-networking " +
                "--disable-component-update --disable-domain-reliability --disable-client-side-phishing-detection " +
                "--no-pings --metrics-recording-only --disable-breakpad --renderer-process-limit=1 " +
                // software rendering: this UI is light, and it saves ~90 MB (no GPU process memory)
                "--disable-gpu --disable-gpu-compositing " +
                "--disable-features=Translate,msEdgeSidebarV2,msUndersideButton,EdgeCollections,msEdgeCollections,msShoppingExp,msEdgeShopping," +
                "AutofillServerCommunication,OptimizationHints,MediaRouter,msEntityExtraction,SpareRendererForSitePerProcess,msWebAssistant,msEdgeCopilot");
            psi.UseShellExecute = false;
            return Process.Start(psi);
        }
    }
}
