using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

namespace Tatami
{
    /// <summary>
    /// Parallel directory scanner. Each folder is read with NtQueryDirectoryFile(FileIdFullDirectoryInformation),
    /// which returns name, size, size on disk, dates, attributes, reparse tag and file id for ~500 entries per call
    /// without opening any file. Works without admin rights on any file system.
    /// </summary>
    sealed unsafe class Scanner
    {
        struct Job { public int Node; public string Path; }

        struct Entry
        {
            public int NameOff, NameLen, Ext;
            public long Size, Alloc, Mtime, FileId;
            public uint Attr;
            public byte Flags;
        }

        readonly Tree t;
        readonly Stack<Job> work = new Stack<Job>();
        int active;
        public volatile bool Cancel;
        public long FilesSeen, DirsSeen, BytesSeen, Denied;
        public volatile string Current = "";
        public readonly Stopwatch Clock = new Stopwatch();
        public readonly List<string> Slow = new List<string>();   // folders that took > 1 s (diagnostics)

        public Scanner(Tree tree) { t = tree; }

        /// <summary>Scan the folder already present as node `node` (path = full path) into the tree.</summary>
        public void Run(int node, string path, int threads)
        {
            Clock.Start();
            work.Push(new Job { Node = node, Path = path });
            var ts = new Thread[threads];
            for (int i = 0; i < threads; i++)
            {
                ts[i] = new Thread(Worker, 256 * 1024);
                ts[i].IsBackground = true;
                ts[i].Start();
            }
            foreach (var th in ts) th.Join();
            Clock.Stop();
        }

        void Worker()
        {
            const int BUF = 128 * 1024;
            IntPtr mem = Marshal.AllocHGlobal(BUF);
            var entries = new List<Entry>(256);
            var names = new char[8192];
            try
            {
                while (true)
                {
                    Job job;
                    lock (work)
                    {
                        while (work.Count == 0)
                        {
                            if (active == 0) { Monitor.PulseAll(work); return; }
                            Monitor.Wait(work);
                        }
                        job = work.Pop();
                        active++;
                    }
                    long t0 = Clock.ElapsedMilliseconds;
                    try
                    {
                        if (!Cancel) ScanDir(job, (byte*)mem, BUF, entries, ref names);
                    }
                    catch (Exception) { /* a single unreadable folder must never stop the scan */ }
                    long dt = Clock.ElapsedMilliseconds - t0;
                    if (dt > 1000) lock (Slow) Slow.Add(dt + " ms  " + job.Path);
                    lock (work)
                    {
                        active--;
                        if (active == 0 && work.Count == 0) Monitor.PulseAll(work);
                    }
                }
            }
            finally { Marshal.FreeHGlobal(mem); }
        }

        void ScanDir(Job job, byte* buf, int bufLen, List<Entry> entries, ref char[] names)
        {
            entries.Clear();
            int nameLen = 0;
            string lp = job.Path.StartsWith(@"\\?\") ? job.Path : (job.Path.StartsWith(@"\\") ? @"\\?\UNC\" + job.Path.Substring(2) : @"\\?\" + job.Path);
            using (var h = Native.CreateFileW(lp, Native.FILE_LIST_DIRECTORY | Native.SYNCHRONIZE, Native.SHARE_ALL,
                       IntPtr.Zero, Native.OPEN_EXISTING, Native.FLAG_BACKUP_SEMANTICS, IntPtr.Zero))
            {
                if (h.IsInvalid)
                {
                    Interlocked.Increment(ref Denied);
                    lock (t.Lock) t.Flags[job.Node] |= Tree.F_DENIED;
                    return;
                }
                Current = job.Path;
                bool first = true;
                while (!Cancel)
                {
                    IoStatusBlock iosb;
                    uint st = Native.NtQueryDirectoryFile(h, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, out iosb, buf, (uint)bufLen,
                        Native.FileIdFullDirectoryInformation, 0, IntPtr.Zero, (byte)(first ? 1 : 0));
                    first = false;
                    if (st == Native.STATUS_NO_MORE_FILES) break;
                    if (st != 0)
                    {
                        if (entries.Count == 0) { Interlocked.Increment(ref Denied); lock (t.Lock) t.Flags[job.Node] |= Tree.F_DENIED; }
                        break;
                    }
                    byte* p = buf;
                    while (true)
                    {
                        uint next = *(uint*)p;
                        int fnLen = (int)(*(uint*)(p + 60)) / 2;
                        char* fn = (char*)(p + 80);
                        if (!(fnLen == 1 && fn[0] == '.') && !(fnLen == 2 && fn[0] == '.' && fn[1] == '.'))
                        {
                            if (nameLen + fnLen > names.Length) Array.Resize(ref names, names.Length * 2 + fnLen);
                            for (int k = 0; k < fnLen; k++) names[nameLen + k] = fn[k];
                            var e = new Entry();
                            e.NameOff = nameLen; e.NameLen = fnLen; nameLen += fnLen;
                            e.Mtime = *(long*)(p + 24);
                            e.Attr = *(uint*)(p + 56);
                            e.FileId = *(long*)(p + 72);
                            if ((e.Attr & Native.ATTR_DIRECTORY) != 0)
                            {
                                e.Flags = Tree.F_DIR;
                                // Junctions and symlinks are name surrogates: don't follow (they point at data
                                // counted elsewhere). Cloud-file folders (OneDrive) are reparse points too, but not
                                // surrogates, so they are scanned.
                                if ((e.Attr & Native.ATTR_REPARSE) != 0)
                                {
                                    uint tag = *(uint*)(p + 64);
                                    if ((tag & 0x20000000) != 0) e.Flags |= Tree.F_LINK;
                                }
                            }
                            else
                            {
                                e.Size = *(long*)(p + 40);
                                e.Alloc = *(long*)(p + 48);
                                if ((e.Attr & Native.ATTR_REPARSE) != 0 && (*(uint*)(p + 64) & 0x20000000) != 0) e.Flags |= Tree.F_LINK;
                                if ((e.Attr & (Native.ATTR_RECALL_ON_DATA | Native.ATTR_OFFLINE)) != 0) e.Flags |= Tree.F_CLOUD;
                                e.Ext = t.Exts.Of(names, e.NameOff, e.NameLen);
                            }
                            entries.Add(e);
                        }
                        if (next == 0) break;
                        p += next;
                    }
                }
            }
            int n = entries.Count;
            if (n == 0) return;

            int start;
            long bytes = 0; int files = 0, dirs = 0;
            lock (t.Lock)
            {
                start = t.Reserve(n, nameLen);
                int nameBase = t.AddName(names, 0, nameLen);
                for (int k = 0; k < n; k++)
                {
                    var e = entries[k];
                    int i = start + k;
                    t.Parent[i] = job.Node; t.First[i] = 0; t.NChild[i] = 0;
                    t.NameOff[i] = nameBase + e.NameOff; t.NameLen[i] = (ushort)e.NameLen;
                    t.Size[i] = e.Size; t.Alloc[i] = e.Alloc; t.Mtime[i] = e.Mtime; t.Attr[i] = e.Attr;
                    t.Flags[i] = e.Flags; t.Ext[i] = e.Ext; t.FileIds[i] = e.FileId;
                    t.Files[i] = 0; t.Dirs[i] = 0;
                    if ((e.Flags & Tree.F_DIR) != 0) dirs++; else { files++; bytes += e.Size; }
                }
                t.First[job.Node] = start; t.NChild[job.Node] = n;
            }
            Interlocked.Add(ref FilesSeen, files);
            Interlocked.Add(ref DirsSeen, dirs);
            Interlocked.Add(ref BytesSeen, bytes);

            if (dirs == 0) return;
            string bp = job.Path.EndsWith("\\") ? job.Path : job.Path + "\\";
            lock (work)
            {
                for (int k = n - 1; k >= 0; k--)
                {
                    var e = entries[k];
                    if ((e.Flags & Tree.F_DIR) != 0 && (e.Flags & Tree.F_LINK) == 0)
                        work.Push(new Job { Node = start + k, Path = bp + new string(names, e.NameOff, e.NameLen) });
                }
                Monitor.PulseAll(work);
            }
        }
    }
}
