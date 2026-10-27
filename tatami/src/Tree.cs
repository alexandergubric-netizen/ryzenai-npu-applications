using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading.Tasks;

namespace Tatami
{
    /// <summary>
    /// The scanned file system as struct-of-arrays. Node 0 is the root. A directory's children occupy one
    /// contiguous index range [First, First+NChild) and always have higher indices than their parent, so a single
    /// reverse pass aggregates sizes. Order[] holds each range sorted by the current metric (largest first).
    /// </summary>
    sealed class Tree
    {
        public const byte F_DIR = 1, F_DENIED = 2, F_HARDLINK = 4, F_LINK = 8, F_DELETED = 16, F_CLOUD = 32, F_FREE = 64;

        public int Count;
        public int[] Parent, First, NChild, Files, Dirs, Ext, NameOff, Order;
        public long[] Size, Alloc, Mtime;
        public uint[] Attr;
        public byte[] Flags;
        public ushort[] NameLen;
        public char[] Names;
        public int NamesLen;
        public long[] FileIds;          // only during scan (hardlink de-dup), null afterwards

        public string RootPath;          // e.g. "C:\" or "D:\Photos"
        public string Volume;            // e.g. "C:\"
        public ExtTable Exts = new ExtTable();
        public long DriveTotal, DriveFree, ClusterSize = 4096;
        public DateTime ScannedAt;
        public double ScanSeconds;
        public string Method = "Directory scan";
        public bool BySize = false;      // sort/treemap metric: logical size (true) or size on disk (false, default:
                                         // online-only cloud files take no space, so they shouldn't fill the map)
        public readonly object Lock = new object();
        public volatile bool Busy;       // a folder is being rescanned into this tree right now

        public Tree(int capacity)
        {
            Grow(Math.Max(capacity, 1024));
            Names = new char[capacity * 16];
        }

        void Grow(int cap)
        {
            Array.Resize(ref Parent, cap); Array.Resize(ref First, cap); Array.Resize(ref NChild, cap);
            Array.Resize(ref Files, cap); Array.Resize(ref Dirs, cap); Array.Resize(ref Ext, cap);
            Array.Resize(ref NameOff, cap); Array.Resize(ref Size, cap); Array.Resize(ref Alloc, cap);
            Array.Resize(ref Mtime, cap); Array.Resize(ref Attr, cap); Array.Resize(ref Flags, cap);
            Array.Resize(ref NameLen, cap); Array.Resize(ref FileIds, cap);
        }

        /// <summary>Reserve n consecutive nodes; caller must hold Lock.</summary>
        public int Reserve(int n, int nameChars)
        {
            if (Count + n > Parent.Length) Grow(Math.Max(Parent.Length * 2, Count + n + 1024));
            if (NamesLen + nameChars > Names.Length) Array.Resize(ref Names, Math.Max(Names.Length * 2, NamesLen + nameChars + 4096));
            int s = Count; Count += n; return s;
        }

        public int AddName(char[] src, int off, int len)
        {
            int o = NamesLen;
            Array.Copy(src, off, Names, o, len);
            NamesLen += len;
            return o;
        }

        public int AddName(string s)
        {
            int o = NamesLen;
            if (NamesLen + s.Length > Names.Length) Array.Resize(ref Names, Math.Max(Names.Length * 2, NamesLen + s.Length + 4096));
            s.CopyTo(0, Names, o, s.Length);
            NamesLen += s.Length;
            return o;
        }

        public string Name(int i) { return new string(Names, NameOff[i], NameLen[i]); }
        public bool IsDir(int i) { return (Flags[i] & F_DIR) != 0; }

        public string Path(int i)
        {
            if (i == 0) return RootPath;
            var parts = new List<int>();
            for (int p = i; p > 0; p = Parent[p]) parts.Add(p);
            var sb = new StringBuilder(RootPath.TrimEnd('\\'));
            for (int k = parts.Count - 1; k >= 0; k--) { sb.Append('\\'); sb.Append(Names, NameOff[parts[k]], NameLen[parts[k]]); }
            return sb.ToString();
        }

        public int Depth(int i) { int d = 0; while (i > 0) { i = Parent[i]; d++; } return d; }

        public long Metric(int i) { return BySize ? Size[i] : Alloc[i]; }

        /// <summary>Size a file adds to its folders (0 for the second+ name of a hardlinked file).</summary>
        public long Counted(int i, bool bySize)
        {
            if ((Flags[i] & (F_HARDLINK | F_DELETED)) != 0) return 0;
            return bySize ? Size[i] : Alloc[i];
        }

        /// <summary>Mark extra names of hardlinked files so they are counted once (like Explorer's "size on disk").</summary>
        public void DedupHardlinks()
        {
            if (FileIds == null) return;
            var ids = new List<long>();
            var idx = new List<int>();
            for (int i = 1; i < Count; i++)
                if ((Flags[i] & F_DIR) == 0 && FileIds[i] != 0) { ids.Add(FileIds[i]); idx.Add(i); }
            var a = ids.ToArray(); var b = idx.ToArray();
            Array.Sort(a, b);
            // Count each file once, at its shallowest name (ties: alphabetically first path), so the result doesn't
            // depend on the order threads found the names. E.g. System32\x.dll wins over WinSxS\...\x.dll.
            for (int k = 1; k < a.Length; k++)
                if (a[k] == a[k - 1])
                {
                    int p = b[k - 1], q = b[k];
                    int dp = Depth(p), dq = Depth(q);
                    bool keepP = dp != dq ? dp < dq : string.CompareOrdinal(Path(p), Path(q)) <= 0;
                    Flags[keepP ? q : p] |= F_HARDLINK;
                    b[k] = keepP ? p : q;
                }
            FileIds = null;
        }

        /// <summary>Recompute folder totals from the files. Children always have higher indices than parents.</summary>
        public void Aggregate()
        {
            for (int i = 0; i < Count; i++)
                if ((Flags[i] & F_DIR) != 0) { Size[i] = 0; Alloc[i] = 0; Files[i] = 0; Dirs[i] = 0; }
            for (int i = Count - 1; i > 0; i--)
            {
                if ((Flags[i] & F_DELETED) != 0) continue;
                int p = Parent[i];
                if ((Flags[i] & F_DIR) != 0)
                {
                    Size[p] += Size[i]; Alloc[p] += Alloc[i]; Files[p] += Files[i]; Dirs[p] += Dirs[i] + 1;
                }
                else
                {
                    if ((Flags[i] & F_HARDLINK) == 0) { Size[p] += Size[i]; Alloc[p] += Alloc[i]; }
                    Files[p]++;
                }
            }
        }

        /// <summary>Sort every folder's children by the current metric, largest first.</summary>
        public void SortAll()
        {
            if (Order == null || Order.Length < Parent.Length) Order = new int[Parent.Length];
            for (int i = 0; i < Count; i++) Order[i] = i;
            var keys = new long[Count];
            bool bs = BySize;
            for (int i = 0; i < Count; i++) keys[i] = -Counted(i, bs);
            var dirs = new List<int>();
            for (int i = 0; i < Count; i++) if ((Flags[i] & F_DIR) != 0 && NChild[i] > 1) dirs.Add(i);
            Parallel.ForEach(dirs, d => Array.Sort(keys, Order, First[d], NChild[d]));
        }

        /// <summary>Children of a folder in the current order, skipping deleted ones.</summary>
        public IEnumerable<int> Children(int d)
        {
            int s = First[d], n = NChild[d];
            for (int k = 0; k < n; k++)
            {
                int c = Order[s + k];
                if ((Flags[c] & F_DELETED) == 0) yield return c;
            }
        }

        /// <summary>True while neither the node nor any folder above it was deleted or dropped.</summary>
        public bool IsLive(int i)
        {
            if (i < 0 || i >= Count) return false;
            for (int p = i; ; p = Parent[p])
            {
                if ((Flags[p] & F_DELETED) != 0) return false;
                if (p == 0) return true;
            }
        }

        /// <summary>Remove a node from the totals (after it was deleted from disk).</summary>
        public void Remove(int i)
        {
            if (i <= 0 || !IsLive(i)) return;
            bool dir = (Flags[i] & F_DIR) != 0;
            long s = dir ? Size[i] : Counted(i, true), a = dir ? Alloc[i] : Counted(i, false);
            int f = dir ? Files[i] : 1, dd = dir ? Dirs[i] + 1 : 0;
            Flags[i] |= F_DELETED;
            for (int p = Parent[i]; ; p = Parent[p])
            {
                Size[p] -= s; Alloc[p] -= a; Files[p] -= f; Dirs[p] -= dd;
                if (p == 0) break;
            }
        }

        /// <summary>Mark everything below a folder deleted and empty it (before scanning it again).</summary>
        public void DropChildren(int d)
        {
            var stack = new Stack<int>();
            stack.Push(d);
            while (stack.Count > 0)
            {
                int x = stack.Pop();
                int s = First[x], n = NChild[x];
                for (int k = 0; k < n; k++)
                {
                    int c = s + k;
                    if ((Flags[c] & F_DIR) != 0 && (Flags[c] & F_DELETED) == 0) stack.Push(c);
                    Flags[c] |= F_DELETED;
                }
            }
            First[d] = 0; NChild[d] = 0;
            Flags[d] = (byte)(Flags[d] & ~F_DENIED);
            if (FileIds == null) FileIds = new long[Parent.Length];
        }

        // ---------------------------------------------------------------- snapshot file (.tatami)
        const string Magic = "TATAMI-SCAN-1";

        public void Save(string file)
        {
            using (var fs = new FileStream(file, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 20)) Save(fs);
        }

        public void Save(Stream stream)
        {
            using (var w = new BinaryWriter(stream, Encoding.UTF8, true))
            {
                w.Write(Magic); w.Write(Count); w.Write(NamesLen);
                w.Write(RootPath); w.Write(Volume ?? ""); w.Write(DriveTotal); w.Write(DriveFree); w.Write(ClusterSize);
                w.Write(ScanSeconds); w.Write(Method ?? ""); w.Write(ScannedAt.ToBinary()); w.Write(BySize);
                var en = Exts.NameArray(); var ec = Exts.CategoryArray();
                w.Write(en.Length);
                for (int i = 0; i < en.Length; i++) { w.Write(en[i]); w.Write(ec[i]); }
                WriteArr(w, Parent, Count); WriteArr(w, First, Count); WriteArr(w, NChild, Count); WriteArr(w, Files, Count);
                WriteArr(w, Dirs, Count); WriteArr(w, Ext, Count); WriteArr(w, NameOff, Count);
                WriteArr(w, Size, Count); WriteArr(w, Alloc, Count); WriteArr(w, Mtime, Count);
                WriteArr(w, Attr, Count); WriteArr(w, Flags, Count); WriteArr(w, NameLen, Count); WriteArr(w, Names, NamesLen);
            }
        }

        public static Tree Load(string file)
        {
            using (var fs = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 20)) return Load(fs);
        }

        public static Tree Load(Stream stream)
        {
            using (var r = new BinaryReader(stream, Encoding.UTF8, true))
            {
                if (r.ReadString() != Magic) throw new InvalidDataException("Not a Tatami scan file.");
                int count = r.ReadInt32(), namesLen = r.ReadInt32();
                if (count < 1 || count > 100000000 || namesLen < 0 || namesLen > (1 << 30))
                    throw new InvalidDataException("The scan file is damaged.");
                var t = new Tree(Math.Max(count, 1024));
                t.Count = count; t.NamesLen = namesLen;
                t.RootPath = r.ReadString(); t.Volume = r.ReadString(); t.DriveTotal = r.ReadInt64(); t.DriveFree = r.ReadInt64();
                t.ClusterSize = r.ReadInt64(); t.ScanSeconds = r.ReadDouble(); t.Method = r.ReadString();
                t.ScannedAt = DateTime.FromBinary(r.ReadInt64()); t.BySize = r.ReadBoolean();
                int ne = r.ReadInt32();
                for (int i = 0; i < ne; i++) { string n = r.ReadString(); int c = r.ReadInt32(); if (i > 0) t.Exts.Restore(n, c); }
                ReadArr(r, t.Parent, count); ReadArr(r, t.First, count); ReadArr(r, t.NChild, count); ReadArr(r, t.Files, count);
                ReadArr(r, t.Dirs, count); ReadArr(r, t.Ext, count); ReadArr(r, t.NameOff, count);
                ReadArr(r, t.Size, count); ReadArr(r, t.Alloc, count); ReadArr(r, t.Mtime, count);
                ReadArr(r, t.Attr, count); ReadArr(r, t.Flags, count); ReadArr(r, t.NameLen, count);
                if (t.Names.Length < namesLen) t.Names = new char[namesLen];
                ReadArr(r, t.Names, namesLen);
                t.FileIds = null;
                t.Validate();
                return t;
            }
        }

        /// <summary>A loaded scan is only data from a file: check every link and name before anything walks or acts on it
        /// (a crafted file could otherwise loop forever, read out of range, or smuggle "..\" into a path).</summary>
        void Validate()
        {
            Func<string, Exception> bad = why => new InvalidDataException("The scan file is damaged (" + why + ").");
            if (string.IsNullOrEmpty(RootPath) || !System.IO.Path.IsPathRooted(RootPath) || RootPath.IndexOfAny(System.IO.Path.GetInvalidPathChars()) >= 0)
                throw bad("root folder");
            foreach (var part in RootPath.Split('\\'))
                if (part == ".." || part == ".") throw bad("root folder");
            int nExt = Exts.Count;
            for (int i = 0; i < Count; i++)
            {
                if (i > 0 && (Parent[i] < 0 || Parent[i] >= i)) throw bad("parent link");
                if (NameOff[i] < 0 || NameLen[i] > NamesLen || NameOff[i] > NamesLen - NameLen[i]) throw bad("name");
                if (Ext[i] < 0 || Ext[i] >= Math.Max(1, nExt)) throw bad("file type");
                if (i > 0)
                {
                    if (NameLen[i] == 0) throw bad("empty name");
                    for (int k = 0; k < NameLen[i]; k++)
                    {
                        char c = Names[NameOff[i] + k];
                        if (c == '\\' || c == '/' || c == ':' || c < 32) throw bad("name");
                    }
                    if (NameLen[i] <= 2 && Names[NameOff[i]] == '.' && (NameLen[i] == 1 || Names[NameOff[i] + 1] == '.')) throw bad("name");
                }
                if ((Flags[i] & F_DIR) != 0)
                {
                    if (NChild[i] < 0 || First[i] < 0 || (NChild[i] > 0 && (First[i] <= i || First[i] > Count - NChild[i])))
                        throw bad("folder contents");
                }
                else if (NChild[i] != 0) throw bad("file with contents");
            }
            for (int i = 0; i < Count; i++)
                if ((Flags[i] & F_DIR) != 0)
                    for (int k = 0; k < NChild[i]; k++)
                        if (Parent[First[i] + k] != i) throw bad("folder contents");
        }

        static void WriteArr(BinaryWriter w, Array a, int n)
        {
            int size = Buffer.ByteLength(a) / Math.Max(1, a.Length);
            var buf = new byte[1 << 20];
            int per = buf.Length / size, done = 0;
            while (done < n)
            {
                int k = Math.Min(per, n - done);
                Buffer.BlockCopy(a, done * size, buf, 0, k * size);
                w.Write(buf, 0, k * size);
                done += k;
            }
        }

        static void ReadArr(BinaryReader r, Array a, int n)
        {
            int size = Buffer.ByteLength(a) / Math.Max(1, a.Length);
            var buf = new byte[1 << 20];
            int per = buf.Length / size, done = 0;
            while (done < n)
            {
                int k = Math.Min(per, n - done), want = k * size, got = 0;
                while (got < want) { int g = r.Read(buf, got, want - got); if (g <= 0) throw new EndOfStreamException(); got += g; }
                Buffer.BlockCopy(buf, 0, a, done * size, want);
                done += k;
            }
        }

        public bool IsUnder(int i, int ancestor)
        {
            for (int p = i; ; p = Parent[p]) { if (p == ancestor) return true; if (p == 0) return false; }
        }

        // ---------------------------------------------------------------- path hashes (growth colours)
        ulong[] pathHashes;

        /// <summary>
        /// 64-bit FNV-1a of every node's lower-cased full path, so two scans of the same folder can be matched
        /// node by node without keeping a million path strings. Cached; recomputed after a rescan added nodes.
        /// </summary>
        public ulong[] PathHashes()
        {
            if (pathHashes != null && pathHashes.Length == Count) return pathHashes;
            const ulong P = 1099511628211UL;
            var h = new ulong[Count];
            ulong r = 14695981039346656037UL;
            foreach (char c in RootPath.TrimEnd('\\')) r = (r ^ char.ToLowerInvariant(c)) * P;
            h[0] = r;
            for (int i = 1; i < Count; i++)
            {
                ulong x = (h[Parent[i]] ^ '\\') * P;
                int o = NameOff[i], n = NameLen[i];
                for (int k = 0; k < n; k++) x = (x ^ char.ToLowerInvariant(Names[o + k])) * P;
                h[i] = x;
            }
            return pathHashes = h;
        }
    }
}
