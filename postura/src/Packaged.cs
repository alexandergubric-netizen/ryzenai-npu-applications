using System;
using System.Runtime.CompilerServices;
using Windows.ApplicationModel;
using Windows.ApplicationModel.Activation;
using Windows.Foundation;

namespace Postura
{
    /// <summary>
    /// What only exists in the MSIX build: the sign-in task ("Start with Windows") and how the app was started.
    /// WinRT calls sit in NoInlining methods and run only when the app really has a package identity.
    /// </summary>
    static class PackagedApp
    {
        public const string TaskId = "PosturaTray";

        /// <summary>Enabled, Disabled, DisabledByUser (switched off in Settings → Apps → Startup), DisabledByPolicy,
        /// EnabledByPolicy, "none" (not packaged) or "error".</summary>
        static string cached = "";
        static DateTime cachedAt = DateTime.MinValue;

        public static string StartupState()
        {
            if (!Program.Packaged) return "none";
            // the page asks every second; Windows only needs to be asked now and then
            if (cached != "" && (DateTime.Now - cachedAt).TotalSeconds < 5) return cached;
            try { cached = StateCore(); }
            catch (Exception e) { Program.Log("startup state: " + e.Message); cached = "error"; }
            cachedAt = DateTime.Now;
            return cached;
        }

        public static string SetStartup(bool on)
        {
            if (!Program.Packaged) return "none";
            try { cached = SetCore(on); }
            catch (Exception e) { Program.Log("startup set: " + e.Message); cached = "error"; }
            cachedAt = DateTime.Now;
            return cached;
        }

        public static bool IsEnabled(string state) { return state == "Enabled" || state == "EnabledByPolicy"; }

        /// <summary>Started by Windows at sign-in (the StartupTask), as opposed to a click on the tile or shortcut.</summary>
        public static bool StartedAtSignIn()
        {
            if (!Program.Packaged) return false;
            try { return SignInCore(); }
            catch (Exception e) { Program.Log("activation kind: " + e.Message); return false; }
        }

        /// <summary>Wait for a WinRT operation (the AsTask helpers don't bind to these winmd types with csc 4).</summary>
        static T Wait<T>(IAsyncOperation<T> op)
        {
            var done = new System.Threading.ManualResetEvent(false);
            op.Completed = (o, status) => done.Set();
            if (!done.WaitOne(15000)) throw new TimeoutException("Windows did not answer");
            if (op.Status != AsyncStatus.Completed) throw new InvalidOperationException("Windows refused: " + op.Status);
            return op.GetResults();
        }

        [MethodImpl(MethodImplOptions.NoInlining)]
        static string StateCore()
        {
            return Wait(StartupTask.GetAsync(TaskId)).State.ToString();
        }

        [MethodImpl(MethodImplOptions.NoInlining)]
        static string SetCore(bool on)
        {
            var t = Wait(StartupTask.GetAsync(TaskId));
            if (on) return Wait(t.RequestEnableAsync()).ToString();
            t.Disable();
            return t.State.ToString();
        }

        [MethodImpl(MethodImplOptions.NoInlining)]
        static bool SignInCore()
        {
            var a = AppInstance.GetActivatedEventArgs();
            return a != null && a.Kind == ActivationKind.StartupTask;
        }
    }
}
