using System;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace Postura
{
    static class Native
    {
        [StructLayout(LayoutKind.Sequential)]
        struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }

        [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
        [DllImport("kernel32.dll")] static extern uint GetTickCount();
        [DllImport("shell32.dll")] static extern int SHQueryUserNotificationState(out int state);
        [DllImport("shell32.dll", CharSet = CharSet.Unicode)] public static extern int SetCurrentProcessExplicitAppUserModelID(string id);
        [DllImport("dwmapi.dll")] public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
        [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr hwnd);
        [DllImport("kernel32.dll")] static extern bool SetProcessWorkingSetSize(IntPtr proc, IntPtr min, IntPtr max);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int MessageBoxW(IntPtr hwnd, string text, string caption, uint type);

        /// <summary>Seconds since the last keyboard or mouse input in this session.</summary>
        public static double IdleSeconds()
        {
            var li = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf(typeof(LASTINPUTINFO)) };
            if (!GetLastInputInfo(ref li)) return 0;
            return unchecked(GetTickCount() - li.dwTime) / 1000.0;
        }

        /// <summary>True while a full-screen app, game or presentation is running (Windows' own "busy" signal).</summary>
        public static bool Busy()
        {
            int s;
            if (SHQueryUserNotificationState(out s) != 0) return false;
            return s == 2 || s == 3 || s == 4;   // QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE
        }

        /// <summary>Raw QUERY_USER_NOTIFICATION_STATE (5 = accepts notifications, 6 = quiet time / Do not disturb).</summary>
        public static int NotificationState()
        {
            int s;
            return SHQueryUserNotificationState(out s) == 0 ? s : 5;
        }

        [DllImport("powrprof.dll")] static extern uint CallNtPowerInformation(int level, IntPtr inBuf, uint inLen, out uint outBuf, uint outLen);

        /// <summary>True while some app keeps the screen on (a video player, a call, a presentation): Windows' own
        /// "display required" flag, the same one that stops the screen saver.</summary>
        public static bool DisplayRequired()
        {
            try { uint s; return CallNtPowerInformation(16, IntPtr.Zero, 0, out s, 4) == 0 && (s & 2) != 0; }   // SystemExecutionState, ES_DISPLAY_REQUIRED
            catch { return false; }
        }

        static DateTime callChecked = DateTime.MinValue;
        static bool inCall;

        /// <summary>True while an app uses the microphone (a call or a recording). Windows keeps this per user for its
        /// own privacy indicator: LastUsedTimeStop is 0 while the microphone is in use. Asked at most every 5 s.</summary>
        public static bool InCall()
        {
            if ((DateTime.Now - callChecked).TotalSeconds < 5) return inCall;
            callChecked = DateTime.Now;
            bool on = false;
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"))
                {
                    on = MicUsed(k);
                    if (!on && k != null) using (var n = k.OpenSubKey("NonPackaged")) on = MicUsed(n);
                }
            }
            catch { }
            inCall = on;
            return on;
        }

        static bool MicUsed(RegistryKey parent)
        {
            if (parent == null) return false;
            foreach (var name in parent.GetSubKeyNames())
                using (var k = parent.OpenSubKey(name))
                {
                    if (k == null) continue;
                    object start = k.GetValue("LastUsedTimeStart"), stop = k.GetValue("LastUsedTimeStop");
                    if (start is long && stop is long && (long)start != 0 && (long)stop == 0) return true;
                }
            return false;
        }

        public static bool DarkMode()
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"))
                {
                    object v = k == null ? null : k.GetValue("AppsUseLightTheme");
                    return v is int && (int)v == 0;
                }
            }
            catch { return false; }
        }

        /// <summary>Win 11 rounded corners for a borderless window (ignored on older Windows).</summary>
        public static void RoundCorners(IntPtr hwnd)
        {
            int round = 2;   // DWMWCP_ROUND
            try { DwmSetWindowAttribute(hwnd, 33, ref round, 4); } catch { }
        }

        /// <summary>Give memory back to Windows after the UI closes; the tray process idles at a few MB.</summary>
        public static void Trim()
        {
            GC.Collect();
            GC.WaitForPendingFinalizers();
            try { SetProcessWorkingSetSize(System.Diagnostics.Process.GetCurrentProcess().Handle, (IntPtr)(-1), (IntPtr)(-1)); } catch { }
        }
    }
}
