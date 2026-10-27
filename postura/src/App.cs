using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

namespace Postura
{
    /// <summary>
    /// The resident part: tray icon, reminder clock, notifications and the break timer. The UI window (Edge in app
    /// mode) and its local server only exist while the window is open, so the tray process stays tiny.
    /// </summary>
    static class App
    {
        public static readonly Reminder Reminder = new Reminder();
        static NotifyIcon tray;
        static Control marshal;
        static Server server;
        static Process window;
        static BreakHud hud;
        static string webDir;
        static string balloonAction;
        static string lastTip = "";
        static System.Windows.Forms.Timer tick, housekeeping;

        public static void OnUi(Action a)
        {
            var m = marshal;
            if (m == null || m.IsDisposed) return;
            try { m.BeginInvoke(a); } catch { }
        }

        /// <summary>Run on the tray's UI thread and wait for the result (for API calls that report back).</summary>
        public static T OnUiWait<T>(Func<T> f)
        {
            var m = marshal;
            if (m == null || m.IsDisposed) return default(T);
            return (T)m.Invoke(f);
        }

        static bool keepServer;   // --serve (development): local server stays up without a window

        public static void Run(bool openWindow, string devWeb, bool serve = false, string startAction = null)
        {
            webDir = devWeb;
            keepServer = serve;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            marshal = new Control();
            marshal.CreateControl();
            var h = marshal.Handle;   // force the handle so BeginInvoke works before any window exists

            Store.Load();
            Toast.Init();
            Reminder.EyeDue += () => EyeDue(false);
            Reminder.MoveDue += MoveDue;

            tray = new NotifyIcon { Icon = TrayIcon(), Text = "Postura", Visible = true };
            tray.ContextMenuStrip = BuildMenu();
            tray.MouseClick += (s, e) => { if (e.Button == MouseButtons.Left) OpenWindow(null); };
            tray.BalloonTipClicked += (s, e) => { if (balloonAction != null) ToastAction(balloonAction); };

            tick = new System.Windows.Forms.Timer { Interval = 1000 };
            tick.Tick += (s, e) => { Reminder.Tick(); UpdateTip(); Store.Save(); };
            tick.Start();
            housekeeping = new System.Windows.Forms.Timer { Interval = 5000 };
            housekeeping.Tick += (s, e) => { StopServerIfIdle(); Ai.Housekeeping(); };
            housekeeping.Start();

            // a second launch (Start menu, desktop) asks this instance to show its window
            var openEvt = new EventWaitHandle(false, EventResetMode.AutoReset, Program.OpenEventName);
            var quitEvt = new EventWaitHandle(false, EventResetMode.AutoReset, Program.QuitEventName);
            var actionEvts = Program.Actions.Select(a => new EventWaitHandle(false, EventResetMode.AutoReset, Program.ActionEventName(a))).ToArray();
            var waiter = new Thread(() =>
            {
                // notification buttons arrive as postura: links, which a new process turns into these events
                var hs = new WaitHandle[] { openEvt, quitEvt }.Concat(actionEvts).ToArray();
                while (true)
                {
                    int i = WaitHandle.WaitAny(hs);
                    if (i == 0) OnUi(() => OpenWindow(null));
                    else if (i == 1) { OnUi(Quit); return; }
                    else { string a = Program.Actions[i - 2]; OnUi(() => ToastAction(a)); }
                }
            }) { IsBackground = true };
            waiter.Start();

            if (startAction != null) OnUi(() => ToastAction(startAction));
            if (keepServer) EnsureServer();
            else if (openWindow) OpenWindow(null);
            else Native.Trim();
            Application.Run();
            tray.Visible = false;
            Store.Save(true);
        }

        public static void Quit()
        {
            Store.Save(true);
            if (hud != null) hud.Close();
            if (server != null) server.Stop();
            Ai.Stop();
            tray.Visible = false;
            Application.Exit();
        }

        static Icon TrayIcon()
        {
            using (var s = typeof(App).Assembly.GetManifestResourceStream("tray.ico"))
                return s == null ? SystemIcons.Application : new Icon(s, SystemInformation.SmallIconSize);
        }

        // ---------------------------------------------------------------- reminders

        /// <summary>
        /// An eye-break reminder. Style "notify" = Windows notification, "card" = Postura's floating card, "both".
        /// The card is Postura's own window, so it also appears when Windows holds notifications back (Do not disturb,
        /// full screen, notifications switched off): then it is used even in "notify" mode. Returns what was shown.
        /// </summary>
        public static string EyeDue(bool test)
        {
            string style = Store.Str("remindStyle");
            bool toast = style != "card" && Toast.ShowEye(Store.Int("eyeSeconds"));
            bool card = style != "notify" || !toast || Toast.Quiet();
            if (card) StartEyeBreak(true);
            return toast && card ? "both" : toast ? "notification" : "card";
        }

        public static void MoveDue()
        {
            if (!Toast.ShowMove(Store.Int("moveInterval")) || Toast.Quiet())
                Balloon("Time to move", "Stand up, stretch, or switch your desk to standing. Click for stretches.", "move-open");
        }

        static void Balloon(string title, string body, string action)
        {
            balloonAction = action;
            tray.ShowBalloonTip(10000, title, body, ToolTipIcon.None);
        }

        static void ToastAction(string a)
        {
            switch (a)
            {
                case "eye-start": StartEyeBreak(); break;
                case "eye-snooze": Reminder.Snooze(300); break;
                case "move-open": OpenWindow("move"); break;
                case "move-done": break;
                default: OpenWindow(null); break;
            }
        }

        /// <summary>prompt: the reminder card (asks first); otherwise the countdown starts at once.</summary>
        public static void StartEyeBreak() { StartEyeBreak(false); }

        public static void StartEyeBreak(bool prompt)
        {
            if (hud != null && !hud.IsDisposed) return;
            Reminder.BreakOpen = true;
            hud = new BreakHud(Store.Int("eyeSeconds"), prompt);
            hud.Completed += () => Reminder.EyeBreakDone();
            hud.Snoozed += () => Reminder.Snooze(300);
            hud.FormClosed += (s, e) => { Reminder.BreakOpen = false; hud = null; };
            hud.Show();
        }

        public static void Pause(int minutes) { Reminder.Pause(minutes); UpdateTip(); }

        public static void SettingsChanged(List<string> changed)
        {
            if (changed.Contains("autostart")) Setup.SetAutostart(Store.Bool("autostart"));
            if (changed.Contains("eyeInterval") || changed.Contains("eyeEnabled")) Reminder.Restart();
            if (changed.Contains("aiEnabled") && !Store.Bool("aiEnabled")) { Ai.Stop(); Ai.State = "off"; }   // free the NPU now
        }

        static string Clock(int secs)
        {
            if (secs < 60) return "less than a minute";
            int m = (secs + 59) / 60;
            return m + " min";
        }

        static string Status()
        {
            if (Reminder.Paused)
                return Reminder.PausedUntil.Date > DateTime.Today ? "Reminders paused until tomorrow" : "Reminders paused until " + Reminder.PausedUntil.ToString("HH:mm");
            if (!Store.Bool("eyeEnabled")) return "Eye reminders are off";
            if (Reminder.Away) return "Away: the clock restarts when you're back";
            return "Next eye break in " + Clock(Reminder.NextEye);
        }

        static void UpdateTip()
        {
            string tip = "Postura · " + Status();
            if (tip.Length > 63) tip = tip.Substring(0, 63);
            if (tip != lastTip) { tray.Text = tip; lastTip = tip; }
        }

        // ---------------------------------------------------------------- tray menu

        static ContextMenuStrip BuildMenu()
        {
            var m = new ContextMenuStrip { ShowImageMargin = false, Renderer = new MenuRenderer(), Padding = new Padding(4) };
            m.Font = new Font("Segoe UI", 9.5f);
            var status = new ToolStripMenuItem("") { Enabled = false };
            var open = new ToolStripMenuItem("Open Postura", null, (s, e) => OpenWindow(null)) { Font = new Font("Segoe UI", 9.5f, FontStyle.Bold) };
            var now = new ToolStripMenuItem("Rest my eyes now (20 s)", null, (s, e) => StartEyeBreak());
            var pause = new ToolStripMenuItem("Pause reminders");
            pause.DropDown = new ContextMenuStrip { ShowImageMargin = false, Renderer = new MenuRenderer(), Padding = new Padding(4), Font = m.Font };
            pause.DropDownItems.Add("30 minutes", null, (s, e) => Pause(30));
            pause.DropDownItems.Add("1 hour", null, (s, e) => Pause(60));
            pause.DropDownItems.Add("2 hours", null, (s, e) => Pause(120));
            pause.DropDownItems.Add("Until tomorrow", null, (s, e) => Pause(-1));
            var resume = new ToolStripMenuItem("Resume reminders", null, (s, e) => Pause(0));
            var quit = new ToolStripMenuItem("Quit Postura", null, (s, e) => Quit());
            m.Items.AddRange(new ToolStripItem[] { status, new ToolStripSeparator(), open, now, pause, resume, new ToolStripSeparator(), quit });
            m.Opening += (s, e) =>
            {
                status.Text = Status();
                now.Text = "Rest my eyes now (" + Store.Int("eyeSeconds") + " s)";
                resume.Visible = Reminder.Paused;
                pause.Visible = !Reminder.Paused;
            };
            return m;
        }

        /// <summary>Flat, rounded menu in the system light/dark colours.</summary>
        sealed class MenuRenderer : ToolStripRenderer
        {
            readonly bool dark = Native.DarkMode();
            Color Bg { get { return dark ? Color.FromArgb(44, 44, 46) : Color.FromArgb(250, 250, 252); } }
            Color Fg { get { return dark ? Color.FromArgb(240, 240, 242) : Color.FromArgb(29, 29, 31); } }
            Color Muted { get { return dark ? Color.FromArgb(150, 150, 156) : Color.FromArgb(120, 120, 126); } }
            Color Hi
            {
                get { return dark ? Color.FromArgb(40, 70, 120) : Color.FromArgb(222, 234, 252); }
            }

            protected override void OnRenderToolStripBackground(ToolStripRenderEventArgs e) { e.Graphics.Clear(Bg); }
            protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e)
            {
                using (var p = new Pen(dark ? Color.FromArgb(70, 70, 74) : Color.FromArgb(220, 220, 226)))
                    e.Graphics.DrawRectangle(p, 0, 0, e.AffectedBounds.Width - 1, e.AffectedBounds.Height - 1);
            }
            protected override void OnRenderMenuItemBackground(ToolStripItemRenderEventArgs e)
            {
                if (!e.Item.Selected || !e.Item.Enabled) return;
                var g = e.Graphics;
                g.SmoothingMode = SmoothingMode.AntiAlias;
                var r = new Rectangle(2, 1, e.Item.Width - 4, e.Item.Height - 2);
                using (var path = new GraphicsPath())
                {
                    int d = 8;
                    path.AddArc(r.X, r.Y, d, d, 180, 90); path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
                    path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90); path.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
                    path.CloseFigure();
                    using (var b = new SolidBrush(Hi)) g.FillPath(b, path);
                }
            }
            protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
            {
                e.TextColor = e.Item.Enabled ? Fg : Muted;
                base.OnRenderItemText(e);
            }
            protected override void OnRenderSeparator(ToolStripSeparatorRenderEventArgs e)
            {
                int y = e.Item.Height / 2;
                using (var p = new Pen(dark ? Color.FromArgb(70, 70, 74) : Color.FromArgb(226, 226, 232)))
                    e.Graphics.DrawLine(p, 8, y, e.Item.Width - 8, y);
            }
            protected override void OnRenderArrow(ToolStripArrowRenderEventArgs e) { e.ArrowColor = Muted; base.OnRenderArrow(e); }
        }

        // ---------------------------------------------------------------- the window

        [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindow(string cls, string title);
        [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
        [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);
        [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);

        static void EnsureServer()
        {
            if (server != null) return;
            int basePort = Program.DefaultPort;
            int p;
            if (int.TryParse(Environment.GetEnvironmentVariable("POSTURA_PORT"), out p)) basePort = p;
            for (int port = basePort; port < basePort + 12; port++)
            {
                try
                {
                    var gate = new WebGate("Postura", "X-Postura", Store.DataDir) { Port = port };
                    var s = new Server(gate, webDir);
                    s.Start();
                    server = s;
                    gate.Publish();   // instance.json: port + secret, readable only by this user (tests ask it for a launch key)
                    return;
                }
                catch (Exception) { }   // port taken (another user on this PC): try the next one
            }
            throw new InvalidOperationException("No free local port for the window");
        }

        public static void OpenWindow(string page)
        {
            try
            {
                // already open? bring it forward
                var h = FindWindow("Chrome_WidgetWin_1", "Postura");
                if (h != IntPtr.Zero && server != null && (DateTime.Now - server.LastSeen).TotalSeconds < 6)
                {
                    if (IsIconic(h)) ShowWindow(h, 9);
                    SetForegroundWindow(h);
                    if (page != null) server.PendingPage = page;
                    return;
                }
                EnsureServer();
                server.LastSeen = DateTime.Now;
                string url = server.Gate.LaunchUrl() + (page != null ? "#" + page : "");   // one-time key -> session cookie
                window = Program.OpenWindow(url, Path.Combine(Store.DataDir, "window"), "--window-size=1180,800");
            }
            catch (Exception e)
            {
                Program.Log("open window: " + e);
                Native.MessageBoxW(IntPtr.Zero, "Postura couldn't open its window: " + e.Message, "Postura", 0x10);
            }
        }

        static void StopServerIfIdle()
        {
            if (server == null || keepServer) return;
            bool alive = false;
            try { alive = window != null && !window.HasExited; } catch { }
            if (alive || (DateTime.Now - server.LastSeen).TotalSeconds < 20) return;
            server.Stop();
            server.Gate.Withdraw();
            server = null;
            window = null;
            Native.Trim();
        }

        // ---------------------------------------------------------------- state for the UI

        public static Dictionary<string, object> AiState()
        {
            string e = Ai.Engine;
            return new Dictionary<string, object> {
                { "engine", e }, { "enabled", Ai.Enabled }, { "available", e != "" },
                { "engineName", e == "flm" ? "FastFlowLM · AMD Ryzen AI NPU" : e == "foundry" ? "Foundry Local · Intel NPU / graphics" : "" },
                { "model", Store.Str("aiModel") }, { "state", Ai.Enabled ? Ai.State : "off" }, { "detail", Ai.Detail }
            };
        }

        public static Dictionary<string, object> State()
        {
            var d = Store.Snapshot();
            d["app"] = "postura";
            d["version"] = Program.Version;
            d["edition"] = Edition.Id;
            d["assistant"] = Edition.Assistant;
            d["org"] = Edition.Org;
            d["nextEye"] = Reminder.NextEye;
            d["nextMove"] = Reminder.NextMove;
            d["eyeIntervalSec"] = Reminder.EyeIntervalSec;
            d["moveIntervalSec"] = Reminder.MoveIntervalSec;
            d["paused"] = Reminder.Paused;
            d["pausedUntil"] = Reminder.Paused ? Reminder.PausedUntil.ToString("yyyy-MM-ddTHH:mm:ss") : null;
            d["away"] = Reminder.Away;
            d["breakOpen"] = Reminder.BreakOpen;
            d["toast"] = Toast.Ready;
            d["ai"] = AiState();
            d["installed"] = Setup.IsInstalledCopy;
            d["autostartActual"] = Setup.AutostartEnabled();
            var s = server;
            if (s != null && s.PendingPage != null) { d["goto"] = s.PendingPage; s.PendingPage = null; }
            return d;
        }
    }
}
