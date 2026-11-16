using System;

namespace Postura
{
    /// <summary>
    /// The 20-20-20 clock and the move clock (a plain "time to move" reminder, or a sit-stand rhythm).
    /// Only screen time counts: input within the last 5 minutes, or watching (a video or a call keeps the screen on
    /// although nobody touches the keyboard). Five minutes really away from the PC (or sleep / lock) is a natural
    /// break and restarts both clocks. Ticked once a second on the tray's UI thread.
    /// </summary>
    sealed class Reminder
    {
        const double AwaySeconds = 300;
        const double PendingWindow = 240;       // after an eye reminder, an idle stretch this soon counts as the break taken
        const double MovePendingWindow = 600;   // after a move reminder, a minute away from the PC this soon counts as moved

        double eyeActive, moveActive, activeUnsaved;
        DateTime lastTick = DateTime.Now;
        DateTime pendingAt = DateTime.MinValue, movePendingAt = DateTime.MinValue;
        public DateTime PausedUntil = DateTime.MinValue;
        public bool BreakOpen;              // the eye-break timer window is showing

        public event Action EyeDue;
        /// <summary>"move" (plain reminder), "stand" or "sit" (sit-stand rhythm).</summary>
        public event Action<string> MoveDue;

        public bool Paused { get { return DateTime.Now < PausedUntil; } }
        public int EyeIntervalSec { get { return Store.Int("eyeInterval") * 60; } }
        public bool SitStand { get { return Store.Bool("sitStand"); } }
        /// <summary>Sit-stand rhythm: true while the standing part runs.</summary>
        public bool Standing { get; private set; }
        public int MoveIntervalSec { get { return (SitStand ? Store.Int(Standing ? "standMinutes" : "sitMinutes") : Store.Int("moveInterval")) * 60; } }
        public int SnoozeSec { get { return Store.Int("snoozeMinutes") * 60; } }
        public int NextEye { get { return (int)Math.Max(0, Math.Ceiling(EyeIntervalSec - eyeActive)); } }
        public int NextMove { get { return (int)Math.Max(0, Math.Ceiling(MoveIntervalSec - moveActive)); } }
        public bool Away { get; private set; }
        /// <summary>Nobody touches the keyboard, but a video or a call is running: still screen time.</summary>
        public bool Watching { get; private set; }
        /// <summary>An app is using the microphone.</summary>
        public bool InCall { get; private set; }
        /// <summary>Reminders wait until the call is over.</summary>
        public bool Holding { get { return InCall && Store.Bool("quietCalls"); } }

        public void Tick()
        {
            var now = DateTime.Now;
            double gap = (now - lastTick).TotalSeconds;
            lastTick = now;
            if (gap < 0 || gap > 90) { Restart(); return; }   // sleep, hibernate or clock change

            double idle = Native.IdleSeconds();
            InCall = Native.InCall();
            Watching = idle >= 30 && Store.Bool("watchCounts") && (InCall || Native.DisplayRequired());
            Away = idle >= AwaySeconds && !Watching;

            if (pendingAt != DateTime.MinValue && !BreakOpen)   // the open card counts its own break
            {
                // idle long enough, and the quiet stretch began around or after the reminder (not someone already reading
                // or watching a film: hands off the keyboard says nothing about the eyes then)
                if (!Watching && idle >= Store.Int("eyeSeconds") && now.AddSeconds(-idle) >= pendingAt.AddSeconds(-30))
                {
                    Store.Count("eyeTaken");     // looked away on their own after the reminder
                    pendingAt = DateTime.MinValue;
                }
                else if ((now - pendingAt).TotalSeconds > PendingWindow) pendingAt = DateTime.MinValue;
            }
            if (movePendingAt != DateTime.MinValue)
            {
                // a minute away from the keyboard right after "time to move" = they got up
                if (!Watching && idle >= 60 && now.AddSeconds(-idle) >= movePendingAt.AddSeconds(-30)) MoveDone();
                else if ((now - movePendingAt).TotalSeconds > MovePendingWindow) movePendingAt = DateTime.MinValue;
            }

            if (Away)
            {
                if (Store.Bool("idleReset")) { eyeActive = 0; moveActive = 0; Standing = false; }
                return;
            }
            activeUnsaved += gap;
            if (activeUnsaved >= 60) { Store.Count("activeSec", (int)activeUnsaved); activeUnsaved = 0; }
            if (Paused || BreakOpen) return;

            eyeActive += gap;
            moveActive += gap;
            bool hold = (Store.Bool("skipBusy") && Native.Busy()) || Holding;

            if (Store.Bool("eyeEnabled") && eyeActive >= EyeIntervalSec)
            {
                if (hold) eyeActive = EyeIntervalSec - 60;   // try again in a minute
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
                if (hold) moveActive = MoveIntervalSec - 120;
                else
                {
                    moveActive = 0;
                    string kind = "move";
                    if (SitStand) { Standing = !Standing; kind = Standing ? "stand" : "sit"; }
                    if (kind != "sit") { Store.Count("moveReminded"); movePendingAt = kind == "move" ? now : DateTime.MinValue; }
                    if (MoveDue != null) MoveDue(kind);
                }
            }
            if (!Store.Bool("eyeEnabled")) eyeActive = 0;
            if (!Store.Bool("moveEnabled")) { moveActive = 0; Standing = false; }
        }

        public void Restart() { eyeActive = 0; moveActive = 0; Standing = false; }
        public void RestartEye() { eyeActive = 0; }
        public void RestartMove() { moveActive = 0; Standing = false; movePendingAt = DateTime.MinValue; }

        /// <summary>A completed 20-second break (break window or the in-app break).</summary>
        public void EyeBreakDone()
        {
            Store.Count("eyeTaken");
            pendingAt = DateTime.MinValue;
            eyeActive = 0;
        }

        public void Snooze() { Snooze(SnoozeSec); }
        public void Snooze(int seconds) { eyeActive = Math.Max(0, EyeIntervalSec - seconds); pendingAt = DateTime.MinValue; }

        /// <summary>"Done" / "I'm standing" on a move reminder, or a minute away from the PC after it.</summary>
        public void MoveDone()
        {
            Store.Count("moveTaken");
            movePendingAt = DateTime.MinValue;
            if (!SitStand) moveActive = 0;
        }

        /// <summary>Not now: ask again after the snooze time. In the sit-stand rhythm the sitting part simply goes on.</summary>
        public void MoveSnooze()
        {
            if (SitStand && Standing) Standing = false;
            moveActive = Math.Max(0, MoveIntervalSec - SnoozeSec);
            movePendingAt = DateTime.MinValue;
        }

        /// <summary>A guided stretch was finished in the window: it answers a waiting move reminder and restarts the move clock.</summary>
        public void StretchDone()
        {
            Store.Count("stretches");
            if (movePendingAt != DateTime.MinValue) MoveDone();
            else if (!SitStand) moveActive = 0;
        }

        public void Pause(int minutes)
        {
            if (minutes == 0) PausedUntil = DateTime.MinValue;
            else if (minutes < 0) PausedUntil = DateTime.Today.AddDays(1).AddHours(5);   // "until tomorrow"
            else PausedUntil = DateTime.Now.AddMinutes(minutes);
            Store.PausedUntil = PausedUntil;   // kept across a restart
            if (minutes == 0) Restart();
        }
    }
}
