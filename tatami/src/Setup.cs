using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using Microsoft.Win32;

namespace Tatami
{
    /// <summary>
    /// Per-user install / uninstall. The installer is this same exe named "Tatami-Setup.exe": it shows web/setup.html
    /// and copies itself to %LOCALAPPDATA%\Programs\Tatami\Tatami.exe. TATAMI_SETUP_TEST=&lt;dir&gt; installs into that
    /// folder and skips shortcuts and registry (dry run for tests).
    /// </summary>
    static class Setup
    {
        public const string Publisher = "Alexander Gubric";
        const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tatami";

        public static string TestDir { get { var d = Environment.GetEnvironmentVariable("TATAMI_SETUP_TEST"); return string.IsNullOrEmpty(d) ? null : d; } }

        public static string InstallDir
        {
            get
            {
                return TestDir ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\Tatami");
            }
        }

        public static string InstalledExe { get { return Path.Combine(InstallDir, "Tatami.exe"); } }

        static string StartMenuLink { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Tatami.lnk"); } }
        static string DesktopLink { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Tatami.lnk"); } }

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

        public static Json Info()
        {
            return new Json().Obj().P("version", Program.Version).P("dir", InstallDir).P("installed", InstalledVersion())
                .P("edge", Program.EdgePath() != null).P("test", TestDir != null)
                .P("desktopExists", File.Exists(DesktopLink)).EndObj();
        }

        /// <summary>Copy this exe into place and register it. Returns the installed exe path.</summary>
        public static string Install(bool desktop, bool startMenu, bool context)
        {
            string self = Process.GetCurrentProcess().MainModule.FileName;
            string dir = InstallDir, exe = InstalledExe;
            Directory.CreateDirectory(dir);
            CloseRunning(exe);
            if (!string.Equals(Path.GetFullPath(self), Path.GetFullPath(exe), StringComparison.OrdinalIgnoreCase))
            {
                string tmp = exe + ".new";
                File.Copy(self, tmp, true);
                if (File.Exists(exe)) File.Delete(exe);
                File.Move(tmp, exe);
            }
            if (TestDir != null)
            {
                File.WriteAllText(Path.Combine(dir, "setup-test.txt"), "desktop=" + desktop + " startMenu=" + startMenu + " context=" + context);
                return exe;
            }
            if (startMenu) Shortcut(StartMenuLink, exe); else TryDelete(StartMenuLink);
            if (desktop) Shortcut(DesktopLink, exe); else TryDelete(DesktopLink);
            SetContextMenu(exe, context);
            using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\App Paths\Tatami.exe"))
            {
                k.SetValue("", exe);
                k.SetValue("Path", dir);
            }
            using (var k = Registry.CurrentUser.CreateSubKey(UninstallKey))
            {
                k.SetValue("DisplayName", "Tatami");
                k.SetValue("DisplayVersion", Program.Version);
                k.SetValue("Publisher", Publisher);
                k.SetValue("DisplayIcon", exe + ",0");
                k.SetValue("InstallLocation", dir);
                k.SetValue("UninstallString", "\"" + exe + "\" --uninstall");
                k.SetValue("QuietUninstallString", "\"" + exe + "\" --uninstall --quiet");
                k.SetValue("Comments", "See what fills your disk");
                k.SetValue("EstimatedSize", (int)Math.Max(1, new FileInfo(exe).Length / 1024), RegistryValueKind.DWord);
                k.SetValue("NoModify", 1, RegistryValueKind.DWord);
                k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                k.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd"));
            }
            return exe;
        }

        /// <summary>"Analyse with Tatami" on folders, drives and folder backgrounds (Show more options on Win 11).</summary>
        static void SetContextMenu(string exe, bool on)
        {
            foreach (var cls in new[] { @"Directory\shell\Tatami", @"Drive\shell\Tatami", @"Directory\Background\shell\Tatami" })
            {
                string key = @"Software\Classes\" + cls;
                if (!on) { try { Registry.CurrentUser.DeleteSubKeyTree(key, false); } catch { } continue; }
                using (var k = Registry.CurrentUser.CreateSubKey(key))
                {
                    k.SetValue("", "Analyse with Tatami");
                    k.SetValue("Icon", "\"" + exe + "\",0");
                }
                using (var k = Registry.CurrentUser.CreateSubKey(key + @"\command"))
                    k.SetValue("", "\"" + exe + "\" \"%V\"");
            }
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
                sc.Description = "Tatami - see what fills your disk";
                sc.Save();
                Marshal.FinalReleaseComObject(sc);
            }
            finally { Marshal.FinalReleaseComObject(shell); }
        }

        static void TryDelete(string f) { try { if (File.Exists(f)) File.Delete(f); } catch { } }

        /// <summary>Stop a running installed copy so its exe can be replaced or removed.</summary>
        static void CloseRunning(string exe)
        {
            int me = Process.GetCurrentProcess().Id;
            foreach (var p in Process.GetProcessesByName("Tatami"))
            {
                try
                {
                    if (p.Id == me) continue;
                    if (string.Equals(p.MainModule.FileName, exe, StringComparison.OrdinalIgnoreCase)) { p.Kill(); p.WaitForExit(3000); }
                }
                catch { }
            }
        }

        public static void Launch()
        {
            var psi = new ProcessStartInfo(InstalledExe) { UseShellExecute = false, WorkingDirectory = InstallDir };
            Process.Start(psi);
        }

        // ---------------------------------------------------------------- uninstall

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        static extern int MessageBoxW(IntPtr hwnd, string text, string caption, uint type);

        public static int Uninstall(bool quiet)
        {
            const uint YESNO = 0x4, ICONQ = 0x20, ICONI = 0x40, TOPMOST = 0x40000;
            if (!quiet && MessageBoxW(IntPtr.Zero, "Remove Tatami from this PC?", "Uninstall Tatami", YESNO | ICONQ | TOPMOST) != 6) return 1;
            bool data = !quiet && Directory.Exists(Program.DataDirNoCreate) &&
                        MessageBoxW(IntPtr.Zero, "Also delete Tatami's saved scan history and settings?", "Uninstall Tatami", YESNO | ICONQ | TOPMOST) == 6;
            string exe = InstalledExe, dir = InstallDir;
            CloseRunning(exe);
            TryDelete(StartMenuLink);
            TryDelete(DesktopLink);
            SetContextMenu(exe, false);
            try { Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\App Paths\Tatami.exe", false); } catch { }
            try { Registry.CurrentUser.DeleteSubKeyTree(UninstallKey, false); } catch { }
            if (data) try { Directory.Delete(Program.DataDirNoCreate, true); } catch { }
            // this exe is running from the folder: remove it a moment after we exit
            string self = Process.GetCurrentProcess().MainModule.FileName;
            if (self.StartsWith(dir, StringComparison.OrdinalIgnoreCase))
            {
                var psi = new ProcessStartInfo("cmd.exe", "/c ping 127.0.0.1 -n 3 >nul & rmdir /s /q \"" + dir + "\"")
                { CreateNoWindow = true, UseShellExecute = false, WorkingDirectory = Path.GetTempPath() };
                Process.Start(psi);
            }
            else try { Directory.Delete(dir, true); } catch { }
            if (!quiet) MessageBoxW(IntPtr.Zero, "Tatami was removed.", "Uninstall Tatami", ICONI | TOPMOST);
            return 0;
        }
    }
}
