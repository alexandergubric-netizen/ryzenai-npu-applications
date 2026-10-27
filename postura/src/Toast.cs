using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.CompilerServices;
using System.Security;
using Microsoft.Win32;
using Windows.Data.Xml.Dom;
using Windows.UI.Notifications;

namespace Postura
{
    /// <summary>
    /// Windows notifications (toasts) with buttons. Unpackaged apps need an AppUserModelID registered under
    /// HKCU\Software\Classes\AppUserModelId. Clicks use protocol activation ("postura:eye-start" …): Windows starts
    /// Postura.exe with that link, and the new process hands the action to the running tray app. This works even when
    /// the toast is clicked later from the notification centre, after Postura restarted.
    /// Every toast gets a new tag (a toast with the same tag only replaces the one on screen, without a new banner).
    /// </summary>
    static class Toast
    {
        public static bool Ready;
        public const string Scheme = "postura";
        static int counter;
        static string lastEyeTag, lastMoveTag;
        public static string LastResult = "", LastDetail = "";   // for the "Send a test reminder" feedback

        public static string LogoPath { get { return Path.Combine(Store.DataDir, "notify-logo.png"); } }

        public static void Init()
        {
            try
            {
                using (var s = typeof(Toast).Assembly.GetManifestResourceStream("web/icon.png"))
                using (var f = File.Create(LogoPath)) s.CopyTo(f);
                using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Classes\AppUserModelId\" + Edition.Aumid))
                {
                    k.SetValue("DisplayName", "Postura");
                    k.SetValue("IconUri", LogoPath);
                }
                RegisterProtocol();
                Native.SetCurrentProcessExplicitAppUserModelID(Edition.Aumid);
                Ready = true;
            }
            catch (Exception e) { Program.Log("toast init: " + e.Message); Ready = false; }
        }

        /// <summary>postura: links open this exe (per user, points at whichever copy is running).</summary>
        static void RegisterProtocol()
        {
            string exe = Process.GetCurrentProcess().MainModule.FileName;
            using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Classes\" + Scheme))
            {
                k.SetValue("", "URL:Postura");
                k.SetValue("URL Protocol", "");
            }
            using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Classes\" + Scheme + @"\DefaultIcon")) k.SetValue("", "\"" + exe + "\",0");
            using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Classes\" + Scheme + @"\shell\open\command")) k.SetValue("", "\"" + exe + "\" \"%1\"");
        }

        /// <summary>Windows' own switch for Postura's notifications (Settings → System → Notifications).</summary>
        [MethodImpl(MethodImplOptions.NoInlining)]
        public static string Setting()
        {
            // Windows throws "element not found" for an app that has never shown a notification: that means allowed
            try { return ToastNotificationManager.CreateToastNotifier(Edition.Aumid).Setting.ToString(); }
            catch { return "Enabled"; }
        }

        /// <summary>True while Windows reports it holds banners back: full screen (2, 7), presentation (4), busy (3) or
        /// the quiet hour after a first sign-in (6). Windows 11's Do not disturb is NOT reported here, which is why the
        /// default reminder style is "both" (notification + Postura's own card).</summary>
        public static bool Quiet()
        {
            int s = Native.NotificationState();
            return s == 2 || s == 3 || s == 4 || s == 6 || s == 7;
        }

        static string X(string s) { return SecurityElement.Escape(s); }

        static string Act(string label, string action)
        {
            return "<action content='" + X(label) + "' arguments='" + Scheme + ":" + action + "' activationType='protocol'/>";
        }

        public static bool ShowEye(int seconds)
        {
            string xml = Build("Time to rest your eyes", "Look at something about 6 metres (20 ft) away for " + seconds + " seconds.",
                Act("Start " + seconds + " s timer", "eye-start") + Act("Snooze 5 min", "eye-snooze"), "eye-start");
            return Show(xml, ref lastEyeTag, "eye");
        }

        public static bool ShowMove(int minutes)
        {
            string xml = Build("Time to move", "You've been at the screen for " + minutes + " minutes. Stand up, stretch, or switch your desk to standing.",
                Act("Show stretches", "move-open") + Act("Done", "move-done"), "move-open");
            return Show(xml, ref lastMoveTag, "move");
        }

        static string Build(string title, string body, string actions, string launch)
        {
            return "<toast launch='" + Scheme + ":" + launch + "' activationType='protocol' duration='long'><visual><binding template='ToastGeneric'>" +
                   "<text>" + X(title) + "</text><text>" + X(body) + "</text>" +
                   "<text placement='attribution'>" + X(Ai.Enabled ? Edition.Assistant + " · Postura" : "Postura") + "</text>" +
                   "<image placement='appLogoOverride' hint-crop='none' src='" + X(new Uri(LogoPath).AbsoluteUri) + "'/>" +
                   "</binding></visual>" +
                   "<actions>" + actions + "</actions>" +
                   (Store.Bool("sound") ? "<audio src='ms-winsoundevent:Notification.Reminder'/>" : "<audio silent='true'/>") +
                   "</toast>";
        }

        static bool Show(string xml, ref string lastTag, string kind)
        {
            if (!Ready) { LastResult = "unavailable"; LastDetail = "Windows notifications couldn't be set up"; return false; }
            try { return ShowCore(xml, ref lastTag, kind); }
            catch (Exception e) { Program.Log("toast: " + e.Message); LastResult = "error"; LastDetail = e.Message; return false; }
        }

        [MethodImpl(MethodImplOptions.NoInlining)]
        static bool ShowCore(string xml, ref string lastTag, string kind)
        {
            string setting = Setting();
            if (setting != "Enabled") { LastResult = "off"; LastDetail = setting; return false; }
            // the previous reminder of this kind leaves the notification centre, the new one pops up fresh
            if (lastTag != null) try { ToastNotificationManager.History.Remove(lastTag, "postura", Edition.Aumid); } catch { }
            string tag = kind + "-" + (++counter) + "-" + DateTime.Now.ToString("HHmmss");
            var doc = new XmlDocument();
            doc.LoadXml(xml);
            var t = new ToastNotification(doc) { Tag = tag, Group = "postura" };
            t.ExpirationTime = DateTimeOffset.Now.AddMinutes(kind == "eye" ? 10 : 30);
            t.Failed += (s, e) => { Program.Log("toast failed: " + e.ErrorCode); LastResult = "failed"; LastDetail = e.ErrorCode.Message; };
            ToastNotificationManager.CreateToastNotifier(Edition.Aumid).Show(t);
            lastTag = tag;
            LastResult = Quiet() ? "quiet" : "shown";
            LastDetail = "";
            return true;
        }

        public static Dictionary<string, object> Status()
        {
            string setting = Ready ? Setting() : "Unavailable";
            return new Dictionary<string, object> {
                { "setting", setting }, { "enabled", setting == "Enabled" }, { "quiet", Quiet() },
                { "last", LastResult }, { "lastDetail", LastDetail }
            };
        }

        public static void OpenWindowsSettings()
        {
            try { Process.Start(new ProcessStartInfo("ms-settings:notifications") { UseShellExecute = true }); } catch { }
        }

        public static void Unregister()
        {
            try { Registry.CurrentUser.DeleteSubKeyTree(@"Software\Classes\AppUserModelId\" + Edition.Aumid, false); } catch { }
            try { Registry.CurrentUser.DeleteSubKeyTree(@"Software\Classes\" + Scheme, false); } catch { }
        }
    }
}
