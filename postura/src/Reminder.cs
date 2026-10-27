using System;

namespace Postura
{
    /// <summary>
    /// The 20-20-20 clock (and the optional move clock). Only screen time counts: input within the last 5 minutes.
    /// Five minutes away from the PC (or sleep / lock) is a natural break and restarts both clocks.
    /// Ticked once a second on the tray's UI thread.
    /// </summary>
    sealed class Reminder
    {
        const double AwaySeconds = 300;
        const double PendingWindow = 240;   // after a reminder, an idle stretch this soon counts as the break taken

        double eyeActive, moveActive, activeUnsaved;
        DateTime lastTick = DateTime.Now;
        DateTime pendingAt = DateTime.MinValue;
        public DateTime PausedUntil = DateTime.MinValue;
        public bool BreakOpen;              // the break timer window is showing

        public event Action EyeDue, MoveDue;

        public bool Paused { get { return DateTime.Now < PausedUntil; } }
        public int EyeIntervalSec { get { return Store.Int("eyeInterval") * 60; } }
        public int MoveIntervalSec { get { return Store.Int("moveInterval") * 60; } }
        public int NextEye { get { return (int)Math.Max(0, Math.Ceiling(EyeIntervalSec - eyeActive)); } }
        public int NextMove { get { return (int)Math.Max(0, Math.Ceiling(MoveIntervalSec - moveActive)); } }
        public bool Away { get; private set; }

        public void Tick()
        {
            var now = DateTime.Now;
            double gap = (now - lastTick).TotalSeconds;
            lastTick = now;
            if (gap < 0 || gap > 90) { Restart(); return; }   // sleep, hibernate or clock change

            double idle = Native.IdleSeconds();
            Away = idle >= AwaySeconds;

            if (pendingAt != DateTime.MinValue && !BreakOpen)   // the open card counts its own break
            {
                // idle long enough, and the quiet stretch began around or after the reminder (not someone already reading)
                if (idle >= Store.Int("eyeSeconds") && now.AddSeconds(-idle) >= pendingAt.AddSeconds(-30))
                {
                    Store.Count("eyeTaken");     // looked away on their own after the reminder
                    pendingAt = DateTime.MinValue;
                }
                else if ((now - pendingAt).TotalSeconds > PendingWindow) pendingAt = DateTime.MinValue;
            }

            if (Away)
            {
                if (Store.Bool("idleReset")) { eyeActive = 0; moveActive = 0; }
                return;
            }
            activeUnsaved += gap;
            if (activeUnsaved >= 60) { Store.Count("activeSec", (int)activeUnsaved); activeUnsaved = 0; }
            if (Paused || BreakOpen) return;

            eyeActive += gap;
            moveActive += gap;

            if (Store.Bool("eyeEnabled") && eyeActive >= EyeIntervalSec)
            {
                if (Store.Bool("skipBusy") && Native.Busy()) eyeActive = EyeIntervalSec - 60;   // try again in a minute
                else
                {
                    eyeActive = 0;
                    pendingAt = now;
                    Store.Count("eyeReminded");
                    if (EyeDue != null) EyeDue();
                }
            }
            if (Store.Bool("moveEnabled") && moveActive >= MoveIntervalSec)
            {
                if (Store.Bool("skipBusy") && Native.Busy()) moveActive = MoveIntervalSec - 120;
                else
                {
                    moveActive = 0;
                    Store.Count("moveReminded");
                    if (MoveDue != null) MoveDue();
                }
            }
            if (!Store.Bool("eyeEnabled")) eyeActive = 0;
            if (!Store.Bool("moveEnabled")) moveActive = 0;
        }

        public void Restart() { eyeActive = 0; moveActive = 0; }

        /// <summary>A completed 20-second break (break window or the in-app break).</summary>
        public void EyeBreakDone()
        {
            Store.Count("eyeTaken");
            pendingAt = DateTime.MinValue;
            eyeActive = 0;
        }

        public void Snooze(int seconds) { eyeActive = Math.Max(0, EyeIntervalSec - seconds); pendingAt = DateTime.MinValue; }

        public void Pause(int minutes)
        {
            if (minutes == 0) PausedUntil = DateTime.MinValue;
            else if (minutes < 0) PausedUntil = DateTime.Today.AddDays(1).AddHours(5);   // "until tomorrow"
            else PausedUntil = DateTime.Now.AddMinutes(minutes);
            if (minutes == 0) Restart();
        }
    }
}
