using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.Windows.Forms;

namespace Postura
{
    /// <summary>
    /// The 20-second break timer: a small floating card above the clock that never takes keyboard focus.
    /// A tiny "window view" (sky, sun, hills, a far tree) drifts slowly while the ring counts down.
    /// Drawn with GDI+ so it costs nothing when closed and ~1% CPU while open.
    /// </summary>
    sealed class BreakHud : Form
    {
        const int W = 432, H = 132;
        const double PromptTimeout = 120;      // an unanswered reminder card leaves after 2 minutes
        readonly int seconds;
        readonly DateTime shown = DateTime.Now;
        DateTime start = DateTime.Now;
        DateTime doneAt = DateTime.MinValue;
        bool prompting;                        // reminder mode: asks first, the countdown starts on click or when you look away
        readonly Timer anim = new Timer { Interval = 33 };
        float scale = 1f;
        bool dark, hoverClose;
        string hoverLink;
        readonly Font fTitle = MakeFont(17, FontStyle.Bold, true), fSub = MakeFont(12.5f, FontStyle.Regular, false),
                      fHint = MakeFont(12f, FontStyle.Bold, false), fNum = MakeFont(22, FontStyle.Bold, true);
        public event Action Completed, Skipped, Snoozed;

        // clickable texts of the prompt (logical units, scaled when hit-testing)
        static readonly RectangleF StartLink = new RectangleF(134, 92, 86, 22), SnoozeLink = new RectangleF(226, 92, 100, 22);
        Rectangle Px(RectangleF r) { return new Rectangle((int)(r.X * scale), (int)(r.Y * scale), (int)(r.Width * scale), (int)(r.Height * scale)); }

        // palette
        Color bg, text, sub, track, ring, sky1, sky2, sun, hillFar, hillNear, tree;

        public BreakHud(int seconds, bool prompt = false)
        {
            this.seconds = seconds;
            prompting = prompt;
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.Manual;
            TopMost = true;
            DoubleBuffered = true;
            AutoScaleMode = AutoScaleMode.None;
            Text = "Rest your eyes";
            Opacity = 0;
            dark = Native.DarkMode();
            Palette();
            anim.Tick += (s, e) => Step();
            MouseMove += (s, e) =>
            {
                bool h = CloseRect().Contains(e.Location);
                string link = !prompting ? null : Px(StartLink).Contains(e.Location) ? "start" : Px(SnoozeLink).Contains(e.Location) ? "snooze" : null;
                if (h != hoverClose || link != hoverLink) { hoverClose = h; hoverLink = link; Invalidate(); }
                Cursor = h || prompting ? Cursors.Hand : Cursors.Default;
            };
            MouseClick += (s, e) =>
            {
                bool finished = doneAt != DateTime.MinValue;
                if (CloseRect().Contains(e.Location) || finished)
                {
                    Close();
                    if (!finished && Skipped != null) Skipped();
                }
                else if (prompting && Px(SnoozeLink).Contains(e.Location))
                {
                    Close();
                    if (Snoozed != null) Snoozed();
                }
                else if (prompting) StartCountdown();   // anywhere else on the card starts the break
            };
        }

        void Palette()
        {
            bg = dark ? Color.FromArgb(36, 36, 38) : Color.White;
            text = dark ? Color.FromArgb(245, 245, 247) : Color.FromArgb(29, 29, 31);
            sub = dark ? Color.FromArgb(160, 160, 166) : Color.FromArgb(110, 110, 115);
            track = dark ? Color.FromArgb(62, 62, 66) : Color.FromArgb(232, 232, 237);
            ring = dark ? Color.FromArgb(100, 160, 255) : Color.FromArgb(47, 111, 219);
            sky1 = Color.FromArgb(191, 222, 255); sky2 = Color.FromArgb(234, 244, 255);
            sun = Color.FromArgb(244, 166, 58);
            hillFar = Color.FromArgb(134, 209, 159); hillNear = Color.FromArgb(59, 178, 115); tree = Color.FromArgb(31, 122, 76);
        }

        protected override bool ShowWithoutActivation { get { return true; } }

        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ExStyle |= 0x08 | 0x80 | 0x08000000;   // TOPMOST, TOOLWINDOW, NOACTIVATE
                cp.ClassStyle |= 0x20000;                  // CS_DROPSHADOW
                return cp;
            }
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            try { scale = Native.GetDpiForWindow(Handle) / 96f; } catch { scale = 1f; }
            if (scale < 1) scale = 1;
            Native.RoundCorners(Handle);
            var wa = Screen.PrimaryScreen.WorkingArea;
            int w = (int)(W * scale), h = (int)(H * scale), m = (int)(16 * scale);
            Bounds = new Rectangle(wa.Right - w - m, wa.Bottom - h - m, w, h);
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            anim.Start();
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            anim.Stop();
            anim.Dispose();
            fTitle.Dispose(); fSub.Dispose(); fHint.Dispose(); fNum.Dispose();
            base.OnFormClosed(e);
        }

        double Elapsed { get { return prompting ? 0 : (DateTime.Now - start).TotalSeconds; } }

        void StartCountdown()
        {
            if (!prompting) return;
            prompting = false;
            start = DateTime.Now;
            Cursor = Cursors.Default;
            Invalidate();
        }

        void Step()
        {
            double shownFor = (DateTime.Now - shown).TotalSeconds;
            if (Opacity < 1 && doneAt == DateTime.MinValue) Opacity = Math.Min(1, shownFor / 0.25);
            if (prompting)
            {
                // stopped typing to look away? then the break has started: a 3 s pause after the card appeared,
                // or no input at all for the first 6 s of the card
                double idle = Native.IdleSeconds();
                bool pausedAfterCard = idle >= 3 && idle < shownFor;
                if (pausedAfterCard || (shownFor >= 6 && idle >= shownFor)) StartCountdown();
                else if (shownFor > PromptTimeout) { Close(); if (Skipped != null) Skipped(); return; }
                Invalidate();
                return;
            }
            double t = Elapsed;
            if (doneAt == DateTime.MinValue)
            {
                if (t >= seconds)
                {
                    doneAt = DateTime.Now;
                    if (Completed != null) Completed();
                }
            }
            else
            {
                double d = (DateTime.Now - doneAt).TotalSeconds;
                if (d > 2.6) Opacity = Math.Max(0, 1 - (d - 2.6) / 0.35);
                if (d > 3.0) { Close(); return; }
            }
            Invalidate();
        }

        Rectangle CloseRect() { int s = (int)(26 * scale); return new Rectangle(Width - s - (int)(6 * scale), (int)(6 * scale), s, s); }

        static GraphicsPath Round(RectangleF r, float rad)
        {
            var p = new GraphicsPath();
            float d = rad * 2;
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }

        static Font MakeFont(float px, FontStyle st, bool display)
        {
            foreach (var name in display ? new[] { "Segoe UI Variable Display", "Segoe UI" } : new[] { "Segoe UI Variable Text", "Segoe UI" })
            {
                try
                {
                    var f = new Font(name, px, st, GraphicsUnit.Pixel);
                    if (f.Name == name) return f;
                    f.Dispose();
                }
                catch { }
            }
            return new Font("Segoe UI", px, st, GraphicsUnit.Pixel);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            g.Clear(bg);
            g.ScaleTransform(scale, scale);
            double t = Elapsed;
            bool done = doneAt != DateTime.MinValue;

            DrawView(g, new RectangleF(16, 16, 100, 100), (float)(DateTime.Now - shown).TotalSeconds);

            // texts
            using (var bText = new SolidBrush(text))
            using (var bSub = new SolidBrush(sub))
            {
                float x = 134, w = 200;
                var sf = new StringFormat { Trimming = StringTrimming.EllipsisWord };
                if (prompting)
                {
                    g.DrawString("Time to rest your eyes", fTitle, bText, x, 22);
                    g.DrawString("Look 6 m (20 ft) away for " + seconds + " s.", fSub, bSub, x, 49);
                    g.DrawString("It starts when you look away.", fSub, bSub, x, 67);
                    using (var bLink = new SolidBrush(ring))
                    using (var fLink = new Font(fHint, hoverLink == "start" ? FontStyle.Bold | FontStyle.Underline : FontStyle.Bold))
                    using (var fLink2 = new Font(fHint, hoverLink == "snooze" ? FontStyle.Bold | FontStyle.Underline : FontStyle.Bold))
                    {
                        g.DrawString("Start timer", fLink, bLink, StartLink.X, StartLink.Y + 2);
                        g.DrawString("Snooze 5 min", fLink2, bSub, SnoozeLink.X, SnoozeLink.Y + 2);
                    }
                }
                else if (!done)
                {
                    g.DrawString("Rest your eyes", fTitle, bText, x, 24);
                    g.DrawString("Look at something about 6 metres (20 ft) away", fSub, bSub, new RectangleF(x, 50, w, 36), sf);
                    // a gentle "blink" cue that breathes in and out every 5 s
                    int a = (int)(110 + 145 * (0.5 + 0.5 * Math.Sin(t * Math.PI * 2 / 5)));
                    using (var bHint = new SolidBrush(Color.FromArgb(a, ring)))
                        g.DrawString("Blink slowly and relax", fHint, bHint, x, 92);
                }
                else
                {
                    g.DrawString("Eyes rested", fTitle, bText, x, 30);
                    g.DrawString("Nice. Next reminder in " + Store.Int("eyeInterval") + " minutes of screen time.", fSub, bSub, new RectangleF(x, 56, w, 40), sf);
                }
            }

            // countdown ring
            float cx = W - 58, cy = H / 2f + 4, r = 30;
            var rr = new RectangleF(cx - r, cy - r, r * 2, r * 2);
            using (var pTrack = new Pen(track, 6f))
                g.DrawEllipse(pTrack, rr);
            float frac = done ? 1f : prompting ? 0f : (float)Math.Min(1, t / seconds);
            using (var pRing = new Pen(ring, 6f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
                if (frac > 0.002f) g.DrawArc(pRing, rr, -90, 360 * frac);
            if (prompting)
            {
                // a play button inside the ring
                using (var b = new SolidBrush(ring))
                    g.FillPolygon(b, new[] { new PointF(cx - 7, cy - 11), new PointF(cx - 7, cy + 11), new PointF(cx + 11, cy) });
            }
            else if (!done)
            {
                int left = (int)Math.Ceiling(seconds - t);
                using (var b = new SolidBrush(text))
                {
                    var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
                    g.DrawString(Math.Max(0, left).ToString(), fNum, b, new RectangleF(cx - r, cy - r - 1, r * 2, r * 2), sf);
                }
            }
            else
            {
                // tick drawn in as a stroke
                double d = Math.Min(1, (DateTime.Now - doneAt).TotalSeconds / 0.35);
                var pts = new[] { new PointF(cx - 12, cy + 1), new PointF(cx - 3, cy + 10), new PointF(cx + 13, cy - 9) };
                using (var p = new Pen(ring, 5f) { StartCap = LineCap.Round, EndCap = LineCap.Round, LineJoin = LineJoin.Round })
                {
                    float l1 = 12.7f, l2 = 24.8f, len = (float)(d * (l1 + l2));
                    if (len <= l1) g.DrawLine(p, pts[0], Lerp(pts[0], pts[1], len / l1));
                    else { g.DrawLine(p, pts[0], pts[1]); g.DrawLine(p, pts[1], Lerp(pts[1], pts[2], (len - l1) / l2)); }
                }
            }

            // close button
            var cr = CloseRect();
            float s = 1 / scale;
            var c = new RectangleF(cr.X * s, cr.Y * s, cr.Width * s, cr.Height * s);
            if (hoverClose) using (var b = new SolidBrush(track)) g.FillEllipse(b, c);
            using (var p = new Pen(sub, 1.6f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
            {
                float m = 9;
                g.DrawLine(p, c.X + m, c.Y + m, c.Right - m, c.Bottom - m);
                g.DrawLine(p, c.Right - m, c.Y + m, c.X + m, c.Bottom - m);
            }
        }

        static PointF Lerp(PointF a, PointF b, float k) { return new PointF(a.X + (b.X - a.X) * k, a.Y + (b.Y - a.Y) * k); }

        /// <summary>The far view to look at: sky, sun, two slowly drifting hill layers and a tree on the horizon.</summary>
        void DrawView(Graphics g, RectangleF r, float t)
        {
            using (var clip = Round(r, 18))
            {
                var state = g.Save();
                g.SetClip(clip);
                using (var sky = new LinearGradientBrush(r, sky1, sky2, 90f)) g.FillRectangle(sky, r);
                float sunY = r.Y + 30 + (float)Math.Sin(t * 0.4) * 2;
                using (var b = new SolidBrush(Color.FromArgb(70, sun))) g.FillEllipse(b, r.X + 58, sunY - 6, 32, 32);
                using (var b = new SolidBrush(sun)) g.FillEllipse(b, r.X + 64, sunY, 20, 20);
                Hills(g, r, hillFar, r.Y + 64, 9, 0.9f, t * 3.0f);
                // the far tree, which is what the eyes should rest on
                float tx = r.X + 30 + (float)Math.Sin(t * 0.25) * 3, ty = r.Y + 60;
                using (var b = new SolidBrush(tree))
                {
                    g.FillRectangle(b, tx - 1.2f, ty, 2.4f, 10);
                    g.FillEllipse(b, tx - 7, ty - 12, 14, 16);
                }
                Hills(g, r, hillNear, r.Y + 80, 7, 1.4f, t * 6.0f);
                g.Restore(state);
            }
        }

        static void Hills(Graphics g, RectangleF r, Color c, float baseY, float amp, float freq, float shift)
        {
            var pts = new System.Collections.Generic.List<PointF>();
            for (float x = 0; x <= r.Width; x += 4)
                pts.Add(new PointF(r.X + x, baseY - amp * (float)(Math.Sin((x + shift) / r.Width * Math.PI * 2 * freq) * 0.6 + Math.Sin((x + shift * 0.6) / r.Width * Math.PI * 2 * freq * 2.3) * 0.4)));
            pts.Add(new PointF(r.Right, r.Bottom));
            pts.Add(new PointF(r.X, r.Bottom));
            using (var b = new SolidBrush(c)) g.FillPolygon(b, pts.ToArray());
        }
    }
}
