using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using Microsoft.Win32;

namespace Postura
{
    /// <summary>
    /// Per-user install / uninstall, no administrator rights. The installer is this same exe named
    /// "Postura-Setup.exe": it shows web/setup.html and copies itself to
    /// %LOCALAPPDATA%\Programs\Postura\Postura.exe. POSTURA_SETUP_TEST=&lt;dir&gt; installs into that folder and
    /// skips shortcuts and registry (dry run for tests).
    /// </summary>
    static class Setup
    {
        public const string Publisher = "Alexander Gubric";
        const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\Postura";
        const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";

        public static string TestDir { get { var d = Environment.GetEnvironmentVariable("POSTURA_SETUP_TEST"); return string.IsNullOrEmpty(d) ? null : d; } }

        public static string InstallDir
        {
            get { return TestDir ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\Postura"); }
        }

        public static string InstalledExe { get { return Path.Combine(InstallDir, "Postura.exe"); } }
        static string StartMenuLink { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Postura.lnk"); } }
        static string DesktopLink { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Postura.lnk"); } }

        static string Self { get { return Process.GetCurrentProcess().MainModule.FileName; } }

        public static bool IsInstalledCopy
        {
            get { return string.Equals(Path.GetFullPath(Self), Path.GetFullPath(InstalledExe), StringComparison.OrdinalIgnoreCase); }
        }

        public static string InstalledVersion()
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(UninstallKey))
                    if (k != null) return k.GetValue("DisplayVersion") as string;
            }
            catch { }
            return File.Exists(InstalledExe) ? FileVersionInfo.GetVersionInfo(InstalledExe).ProductVersion : null;
        }

        static string InstalledEdition()
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(UninstallKey))
                    if (k != null) return k.GetValue("DisplayName") as string;
            }
            catch { }
            return null;
        }

        public static Dictionary<string, object> Info()
        {
            return new Dictionary<string, object> {
                { "version", Program.Version }, { "dir", InstallDir }, { "installed", InstalledVersion() },
                { "installedName", InstalledEdition() }, { "displayName", Edition.DisplayName },
                { "edition", Edition.Id }, { "assistant", Edition.Assistant }, { "org", Edition.Org },
                { "edge", Program.EdgePath() != null }, { "test", TestDir != null }, { "ai", Hardware.Check() }
            };
        }

        /// <summary>
        /// Copy this exe into place and register it. Returns the installed exe path. aiEngine "" switches the
        /// assistant off (it is turned on by SaveAi once the engine is ready); null leaves the setting alone.
        /// </summary>
        public static string Install(bool desktop, bool startMenu, bool autostart, string aiEngine = null, string aiModel = null)
        {
            string dir = InstallDir, exe = InstalledExe;
            Directory.CreateDirectory(dir);
            CloseRunning();
            if (!IsInstalledCopy)
            {
                string tmp = exe + ".new";
                File.Copy(Self, tmp, true);
                if (File.Exists(exe)) File.Delete(exe);
                File.Move(tmp, exe);
            }
            if (aiEngine != null) SaveAi(aiEngine, aiModel ?? "");
            if (TestDir != null)
            {
                File.WriteAllText(Path.Combine(dir, "setup-test.txt"), "desktop=" + desktop + " startMenu=" + startMenu + " autostart=" + autostart);
                return exe;
            }
            if (startMenu) Shortcut(StartMenuLink, exe); else TryDelete(StartMenuLink);
            if (desktop) Shortcut(DesktopLink, exe); else TryDelete(DesktopLink);
            SetAutostart(autostart, exe);
            // remember the choice so the app's own Settings switch shows the same
            try
            {
                Store.Load();
                Store.SetSettings(new Dictionary<string, object> { { "autostart", autostart } });
                Store.Save(true);
            }
            catch { }
            using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\App Paths\Postura.exe"))
            {
                k.SetValue("", exe);
                k.SetValue("Path", dir);
            }
            using (var k = Registry.CurrentUser.CreateSubKey(UninstallKey))
            {
                k.SetValue("DisplayName", Edition.DisplayName);
                k.SetValue("DisplayVersion", Program.Version);
                k.SetValue("Publisher", Publisher);
                k.SetValue("DisplayIcon", exe + ",0");
                k.SetValue("InstallLocation", dir);
                k.SetValue("UninstallString", "\"" + exe + "\" --uninstall");
                k.SetValue("QuietUninstallString", "\"" + exe + "\" --uninstall --quiet");
                k.SetValue("Comments", "Healthy posture and 20-20-20 eye breaks");
                k.SetValue("URLInfoAbout", "");
                k.SetValue("EstimatedSize", (int)Math.Max(1, new FileInfo(exe).Length / 1024), RegistryValueKind.DWord);
                k.SetValue("NoModify", 1, RegistryValueKind.DWord);
                k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                k.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd"));
            }
            return exe;
        }

        /// <summary>Which engine the assistant uses ("" = no assistant). Written to the app's settings file.</summary>
        public static void SaveAi(string engine, string model)
        {
            try
            {
                Store.Load();
                Store.SetSettings(new Dictionary<string, object> { { "aiEngine", engine }, { "aiModel", model }, { "aiEnabled", engine != "" } });
                Store.Save(true);
            }
            catch (Exception e) { Program.Log("save ai: " + e.Message); }
        }

        public static bool AutostartEnabled()
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(RunKey))
                    return k != null && k.GetValue("Postura") != null;
            }
            catch { return false; }
        }

        /// <summary>Start in the tray at sign-in (only for the installed copy, so a dev build never registers).</summary>
        public static void SetAutostart(bool on, string exe = null)
        {
            exe = exe ?? (IsInstalledCopy ? InstalledExe : null);
            try
            {
                using (var k = Registry.CurrentUser.CreateSubKey(RunKey))
                {
                    if (on && exe != null) k.SetValue("Postura", "\"" + exe + "\" --tray");
                    else if (!on) k.DeleteValue("Postura", false);
                }
            }
            catch (Exception e) { Program.Log("autostart: " + e.Message); }
        }

        static void Shortcut(string link, string exe)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(link));
            var t = Type.GetTypeFromProgID("WScript.Shell");
            dynamic shell = Activator.CreateInstance(t);
            try
            {
                dynamic sc = shell.CreateShortcut(link);
                sc.TargetPath = exe;
                sc.WorkingDirectory = Path.GetDirectoryName(exe);
                sc.IconLocation = exe + ",0";
                sc.Description = "Postura - healthy posture and 20-20-20 eye breaks";
                sc.Save();
                Marshal.FinalReleaseComObject(sc);
            }
            finally { Marshal.FinalReleaseComObject(shell); }
        }

        static void TryDelete(string f) { try { if (File.Exists(f)) File.Delete(f); } catch { } }

        /// <summary>Ask a running copy to quit (it saves its stats), then make sure it's gone.</summary>
        static void CloseRunning()
        {
            try { using (var ev = EventWaitHandle.OpenExisting(Program.QuitEventName)) ev.Set(); } catch { }
            int me = Process.GetCurrentProcess().Id;
            foreach (var p in Process.GetProcessesByName("Postura"))
            {
                try
                {
                    if (p.Id == me) continue;
                    if (string.Equals(p.MainModule.FileName, InstalledExe, StringComparison.OrdinalIgnoreCase))
                    {
                        if (!p.WaitForExit(3000)) { p.Kill(); p.WaitForExit(3000); }
                    }
                }
                catch { }
            }
        }

        public static void Launch()
        {
            Process.Start(new ProcessStartInfo(InstalledExe) { UseShellExecute = false, WorkingDirectory = InstallDir });
        }

        // ---------------------------------------------------------------- uninstall

        public static int Uninstall(bool quiet)
        {
            const uint YESNO = 0x4, ICONQ = 0x20, ICONI = 0x40, TOPMOST = 0x40000;
            if (!quiet && Native.MessageBoxW(IntPtr.Zero, "Remove Postura from this PC?", "Uninstall Postura", YESNO | ICONQ | TOPMOST) != 6) return 1;
            string data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Postura");
            bool wipe = !quiet && Directory.Exists(data) &&
                        Native.MessageBoxW(IntPtr.Zero, "Also delete your Postura settings and break history?", "Uninstall Postura", YESNO | ICONQ | TOPMOST) == 6;
            string dir = InstallDir;
            CloseRunning();
            TryDelete(StartMenuLink);
            TryDelete(DesktopLink);
            SetAutostart(false);
            Toast.Unregister();
            try { Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\App Paths\Postura.exe", false); } catch { }
            try { Registry.CurrentUser.DeleteSubKeyTree(UninstallKey, false); } catch { }
            if (wipe) try { Directory.Delete(data, true); } catch { }
            // this exe is running from the folder: remove it a moment after we exit
            if (Self.StartsWith(dir, StringComparison.OrdinalIgnoreCase))
            {
                var psi = new ProcessStartInfo("cmd.exe", "/c ping 127.0.0.1 -n 3 >nul & rmdir /s /q \"" + dir + "\"")
                { CreateNoWindow = true, UseShellExecute = false, WorkingDirectory = Path.GetTempPath() };
                Process.Start(psi);
            }
            else try { Directory.Delete(dir, true); } catch { }
            if (!quiet) Native.MessageBoxW(IntPtr.Zero, "Postura was removed.", "Uninstall Postura", ICONI | TOPMOST);
            return 0;
        }
    }
}
