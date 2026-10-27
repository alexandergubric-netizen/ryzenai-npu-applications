using System;
using System.Collections.Generic;
using System.IO;

namespace Tatami
{
    /// <summary>
    /// Squarified treemap (Bruls et al.) with van Wijk cushion coefficients. Output: int32 record count, the
    /// 40-byte records the browser rasterises per pixel, then a trailer (int32 n, n × {int32 record, float64
    /// bytes}) giving the size of each "many small items" block. Record:
    ///   float x, y, w, h | int32 node | uint16 ext | uint8 kind | uint8 depth | float s1x, s2x, s1y, s2y
    /// kind: 0 file, 1 folder frame (children follow), 2 collapsed folder / "small items" rest, 3 folder with header.
    /// Frames are only for hit-testing, outlines and labels; leaves (0, 2) cover every painted pixel.
    /// Colour keys follow the trailer: int32 mode (0 by type, 1 by age, 2 by growth), then for age float32[n] days
    /// since modified (size-weighted mean for folders and "small items"), for growth float32[n] relative change
    /// (-1…1, 2 = new since the previous scan, NaN = nothing to compare) and float32[n] change in bytes.
    /// </summary>
    sealed class Treemap
    {
        public const byte K_FILE = 0, K_FRAME = 1, K_REST = 2, K_HEADER = 3;
        public const int C_TYPE = 0, C_AGE = 1, C_GROWTH = 2;
        const double H0 = 0.40, F = 0.78;     // cushion ridge height and per-level falloff

        readonly Tree t;
        readonly bool bySize;
        readonly double header, minArea;
        readonly int headerLevels;
        readonly BinaryWriter w;
        public int Records;
        readonly List<KeyValuePair<int, double>> restSizes = new List<KeyValuePair<int, double>>();

        // colour keys
        int mode;
        double[] wsum, msum;               // age: per node, bytes and bytes × mtime of the files below
        long nowFt;
        ulong[] hashes; Baseline baseline;  // growth
        readonly List<float> keyA = new List<float>(), keyB = new List<float>();

        Treemap(Tree tree, bool bySize, double headerPx, int headerLevels, double minArea, BinaryWriter writer)
        {
            t = tree; this.bySize = bySize; header = headerPx; this.headerLevels = headerLevels; this.minArea = minArea; w = writer;
        }

        public static byte[] Build(Tree tree, int root, int width, int height, double dpr, bool bySize, int colorMode = C_TYPE, Baseline baseline = null)
        {
            var ms = new MemoryStream(1 << 20);
            var bw = new BinaryWriter(ms);
            bw.Write(0);                          // record count, patched below
            var tm = new Treemap(tree, bySize, Math.Round(17 * dpr), 3, Math.Max(1.5, dpr * dpr * 1.5), bw);
            if (colorMode == C_GROWTH && baseline == null) colorMode = C_TYPE;
            tm.mode = colorMode;
            lock (tree.Lock)
            {
                if (colorMode == C_AGE) tm.PrepareAge();
                if (colorMode == C_GROWTH) { tm.hashes = tree.PathHashes(); tm.baseline = baseline; }
                var s = new double[4];
                tm.Node(root, 0, 0, width, height, 0, s, H0);
            }
            // trailer: bytes held by each "many small items" block (record index, size)
            bw.Write(tm.restSizes.Count);
            foreach (var kv in tm.restSizes) { bw.Write(kv.Key); bw.Write(kv.Value); }
            bw.Write(tm.mode);
            if (tm.mode != C_TYPE) foreach (float f in tm.keyA) bw.Write(f);
            if (tm.mode == C_GROWTH) foreach (float f in tm.keyB) bw.Write(f);
            bw.Flush();
            var data = ms.ToArray();
            BitConverter.GetBytes(tm.Records).CopyTo(data, 0);
            return data;
        }

        long Val(int i)
        {
            if ((t.Flags[i] & Tree.F_DIR) != 0) return bySize ? t.Size[i] : t.Alloc[i];
            return t.Counted(i, bySize);
        }

        /// <summary>Extension of the largest file inside a folder (its colour when drawn collapsed).</summary>
        int Dominant(int i)
        {
            for (int guard = 0; guard < 512 && (t.Flags[i] & Tree.F_DIR) != 0; guard++)
            {
                int best = -1;
                foreach (int c in t.Children(i)) { best = c; break; }
                if (best < 0) return -1;
                i = best;
            }
            return (t.Flags[i] & Tree.F_DIR) != 0 ? -1 : t.Ext[i];
        }

        void Emit(double x, double y, double ww, double hh, int id, int ext, byte kind, int depth, double[] s)
        {
            w.Write((float)x); w.Write((float)y); w.Write((float)ww); w.Write((float)hh);
            w.Write(id);
            w.Write((ushort)(ext < 0 ? 65535 : Math.Min(ext, 65534)));
            w.Write(kind); w.Write((byte)Math.Min(depth, 255));
            w.Write((float)s[0]); w.Write((float)s[1]); w.Write((float)s[2]); w.Write((float)s[3]);
            Records++;
        }

        // ---------------------------------------------------------------- colour keys (one per record, after Emit)

        void KeyNone() { if (mode != C_TYPE) { keyA.Add(float.NaN); keyB.Add(float.NaN); } }
        void KeyNode(int id) { if (mode != C_TYPE) KeyOf(null, id, 0); }
        void KeyRest(List<int> kids, int from) { if (mode != C_TYPE) KeyOf(kids, -1, from); }

        void PrepareAge()
        {
            int n = t.Count;
            wsum = new double[n]; msum = new double[n];
            nowFt = DateTime.UtcNow.ToFileTimeUtc();
            for (int i = n - 1; i >= 0; i--)
            {
                byte f = t.Flags[i];
                if ((f & Tree.F_DIR) == 0)
                {
                    long v = t.Counted(i, bySize);
                    if (v > 0 && t.Mtime[i] > 0) { wsum[i] = v; msum[i] = (double)v * t.Mtime[i]; }
                }
                if (i > 0 && (f & Tree.F_DELETED) == 0) { int p = t.Parent[i]; wsum[p] += wsum[i]; msum[p] += msum[i]; }
            }
        }

        /// <summary>Key of node id (kids == null) or of kids[from..], the items in a "small items" block.</summary>
        void KeyOf(List<int> kids, int id, int from)
        {
            int a = kids == null ? 0 : from, b = kids == null ? 1 : kids.Count;
            if (mode == C_AGE)
            {
                double ws = 0, ms = 0;
                for (int k = a; k < b; k++) { int c = kids == null ? id : kids[k]; ws += wsum[c]; ms += msum[c]; }
                keyA.Add(ws > 0 ? (float)((nowFt - ms / ws) / 864e9) : float.NaN);
                return;
            }
            long cur = 0, old = 0; bool any = false;
            for (int k = a; k < b; k++)
            {
                int c = kids == null ? id : kids[k];
                cur += Val(c);
                long o = baseline.Find(hashes[c], bySize);
                if (o >= 0) { old += o; any = true; }
            }
            if (!any) { keyA.Add(cur > 0 ? 2f : float.NaN); keyB.Add(cur); return; }
            long d = cur - old, m = Math.Max(cur, old);
            keyA.Add(m > 0 ? (float)((double)d / m) : 0f);
            keyB.Add(d);
        }

        static void Ridge(double[] s, double x, double y, double ww, double hh, double h)
        {
            double x2 = x + ww, y2 = y + hh;
            s[0] += 4 * h * (x2 + x) / ww; s[1] -= 4 * h / ww;
            s[2] += 4 * h * (y2 + y) / hh; s[3] -= 4 * h / hh;
        }

        void Node(int i, double x, double y, double ww, double hh, int depth, double[] parentS, double h)
        {
            var s = (double[])parentS.Clone();
            if (ww <= 0 || hh <= 0) return;
            Ridge(s, x, y, ww, hh, h);
            bool dir = (t.Flags[i] & Tree.F_DIR) != 0;
            if (!dir) { Emit(x, y, ww, hh, i, t.Ext[i], K_FILE, depth, s); KeyNode(i); return; }

            if (ww < 3 || hh < 3 || t.NChild[i] == 0)
            {
                Emit(x, y, ww, hh, i, Dominant(i), K_REST, depth, s); KeyNode(i);
                return;
            }
            double cx = x, cy = y, cw = ww, ch = hh;
            bool withHeader = depth < headerLevels && ww >= header * 4 && hh >= header * 2.5;
            if (withHeader)
            {
                Emit(x, y, ww, hh, i, -1, K_HEADER, depth, s); KeyNone();
                double pad = Math.Max(1, Math.Round(header / 12));
                cx += pad; cw -= 2 * pad; cy += header; ch -= header + pad;
                s = (double[])parentS.Clone();          // children get a fresh cushion inside the header frame
                Ridge(s, cx, cy, cw, ch, h);
            }
            else { Emit(x, y, ww, hh, i, -1, K_FRAME, depth, s); KeyNone(); }

            var kids = new List<int>();
            var vals = new List<double>();
            double total = 0;
            foreach (int c in t.Children(i))
            {
                long v = Val(c);
                if (v <= 0) break;          // sorted largest first
                kids.Add(c); vals.Add(v); total += v;
            }
            if (kids.Count == 0 || cw <= 0 || ch <= 0) return;
            Squarify(i, kids, vals, total, cx, cy, cw, ch, depth + 1, s, h * F);
        }

        void Squarify(int parent, List<int> kids, List<double> vals, double total, double x, double y, double ww, double hh,
                      int depth, double[] s, double h)
        {
            double scale = ww * hh / total;
            int n = kids.Count, i = 0;
            double remaining = total;
            while (i < n)
            {
                if (vals[i] * scale < minArea)
                {
                    // everything from here on is tinier than a pixel or two: one "small items" block
                    var rs = (double[])s.Clone();
                    Ridge(rs, x, y, ww, hh, h);
                    int ext = (t.Flags[kids[i]] & Tree.F_DIR) != 0 ? Dominant(kids[i]) : t.Ext[kids[i]];
                    restSizes.Add(new KeyValuePair<int, double>(Records, remaining));
                    Emit(x, y, ww, hh, parent, ext, K_REST, depth, rs); KeyRest(kids, i);
                    return;
                }
                bool horiz = ww >= hh;              // lay the row along the short side
                double side = horiz ? hh : ww;
                double rowSum = 0, worst = double.MaxValue;
                int j = i;
                while (j < n)
                {
                    double sum = rowSum + vals[j];
                    double aSum = sum * scale, aMax = vals[i] * scale, aMin = vals[j] * scale;
                    double side2 = side * side;
                    double wr = Math.Max(side2 * aMax / (aSum * aSum), (aSum * aSum) / (side2 * aMin));
                    if (j > i && wr > worst) break;
                    worst = wr; rowSum = sum; j++;
                }
                double thick = rowSum * scale / side;
                if (horiz) thick = Math.Min(thick, ww); else thick = Math.Min(thick, hh);
                double pos = horiz ? y : x;
                for (int k = i; k < j; k++)
                {
                    double len = vals[k] / rowSum * side;
                    if (k == j - 1) len = (horiz ? y + hh : x + ww) - pos;   // absorb rounding
                    if (horiz) Node(kids[k], x, pos, thick, len, depth, s, h);
                    else Node(kids[k], pos, y, len, thick, depth, s, h);
                    pos += len;
                }
                if (horiz) { x += thick; ww -= thick; } else { y += thick; hh -= thick; }
                remaining -= rowSum;
                i = j;
                if (ww <= 0.01 || hh <= 0.01) return;
                scale = ww * hh / remaining;
            }
        }
    }
}
