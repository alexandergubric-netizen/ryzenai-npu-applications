using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;

namespace Tatami
{
    /// <summary>
    /// Duplicate finder: files of the same size → same hash of the first 64 KB → same hash of the whole file.
    /// Runs on a background thread per session; the UI polls Status and can cancel. Hard links (already counted
    /// once), links and online-only placeholders (opening them would download them) are left out, and so is the
    /// Windows folder (Tatami refuses to delete there anyway).
    /// </summary>
    sealed class Dupes
    {
        const int Head = 64 * 1024;
        const int Threads = 4;

        sealed class Cand { public int Id; public string Path; public long Size; public string HeadHash, FullHash; }

        public sealed class Group { public long Size; public string Hash; public int[] Ids; }

        readonly Tree t;
        public readonly int Scope;
        public readonly string ScopePath;
        public readonly long MinSize;
        public volatile string State = "hashing";     // hashing | done | cancelled | error
        public volatile string Phase = "Comparing sizes";
        public volatile bool Cancel;
        public string Error;
        public long FilesTotal, FilesDone, BytesTotal, BytesDone, Unreadable, Candidates;
        public readonly Stopwatch Clock = Stopwatch.StartNew();
        public double Seconds;
        public DateTime FinishedAt;
        public List<Group> Groups = new List<Group>();

        Dupes(Tree tree, int scope, long min)
        {
            t = tree; Scope = scope; MinSize = min;
            lock (t.Lock) ScopePath = t.Path(scope);
        }

        public static Dupes Start(Tree tree, int scope, long min)
        {
            var d = new Dupes(tree, scope, Math.Max(1, min));
            var th = new Thread(d.Run); th.IsBackground = true; th.Priority = ThreadPriority.BelowNormal; th.Start();
            return d;
        }

        void Run()
        {
            try
            {
                // ---- 1. candidates: same size as at least one other file
                var all = new List<Cand>();
                string win = Environment.GetFolderPath(Environment.SpecialFolder.Windows).TrimEnd('\\');
                lock (t.Lock)
                {
                    int winId = Server.Resolve(t, win);
                    var st = new Stack<int>(); st.Push(Scope);
                    while (st.Count > 0)
                    {
                        int d = st.Pop(); int s = t.First[d], n = t.NChild[d];
                        for (int k = 0; k < n; k++)
                        {
                            int c = s + k; byte f = t.Flags[c];
                            if ((f & Tree.F_DELETED) != 0 || c == winId) continue;
                            if ((f & Tree.F_DIR) != 0) { if ((f & Tree.F_LINK) == 0) st.Push(c); continue; }
                            if ((f & (Tree.F_HARDLINK | Tree.F_CLOUD | Tree.F_LINK)) != 0) continue;
                            if ((t.Attr[c] & (Native.ATTR_OFFLINE | Native.ATTR_RECALL_ON_DATA | Native.ATTR_RECALL_ON_OPEN)) != 0) continue;
                            if (t.Size[c] < MinSize) continue;
                            all.Add(new Cand { Id = c, Size = t.Size[c] });
                        }
                    }
                }
                var sized = all.GroupBy(c => c.Size).Where(g => g.Count() > 1).SelectMany(g => g).ToList();
                Candidates = sized.Count;
                if (Cancel) { Finish("cancelled"); return; }
                lock (t.Lock) foreach (var c in sized) c.Path = t.Path(c.Id);

                // ---- 2. hash of the first 64 KB
                Phase = "Reading the start of each file";
                FilesTotal = sized.Count; FilesDone = 0;
                BytesTotal = sized.Sum(c => Math.Min(c.Size, Head)); BytesDone = 0;
                Hash(sized, true);
                if (Cancel) { Finish("cancelled"); return; }
                var heads = sized.Where(c => c.HeadHash != null).GroupBy(c => c.Size + ":" + c.HeadHash)
                                 .Where(g => g.Count() > 1).SelectMany(g => g).ToList();

                // ---- 3. hash of the whole file
                Phase = "Comparing whole files";
                FilesTotal = heads.Count; FilesDone = 0;
                BytesTotal = heads.Sum(c => c.Size); BytesDone = 0;
                Hash(heads, false);
                if (Cancel) { Finish("cancelled"); return; }

                var groups = new List<Group>();
                foreach (var g in heads.Where(c => c.FullHash != null).GroupBy(c => c.Size + ":" + c.FullHash))
                {
                    if (g.Count() < 2) continue;
                    var ids = g.Select(c => c.Id).ToList();
                    groups.Add(new Group { Size = g.First().Size, Hash = g.First().FullHash.Substring(0, 12), Ids = ids.ToArray() });
                }
                Groups = groups.OrderByDescending(g => g.Size * (g.Ids.Length - 1)).ToList();
                Finish("done");
            }
            catch (Exception e)
            {
                Error = e.Message;
                Program.Log("dupes: " + e);
                Finish("error");
            }
        }

        void Finish(string state)
        {
            Seconds = Clock.Elapsed.TotalSeconds;
            FinishedAt = DateTime.Now;
            State = state;
        }

        void Hash(List<Cand> list, bool head)
        {
            // big files first so the slowest ones don't end up alone at the end
            var order = head ? list : list.OrderByDescending(c => c.Size).ToList();
            var opts = new ParallelOptions { MaxDegreeOfParallelism = Threads };
            Parallel.ForEach(order, opts, () => new byte[1 << 20], (c, loop, buf) =>
            {
                if (Cancel) { loop.Stop(); return buf; }
                string h = HashFile(c, head ? Head : long.MaxValue, buf);
                if (h == null) Interlocked.Increment(ref Unreadable);
                if (head) c.HeadHash = h; else c.FullHash = h;
                // a file that fits in the first block is already fully hashed
                if (head && h != null && c.Size <= Head) c.FullHash = h;
                Interlocked.Increment(ref FilesDone);
                return buf;
            }, buf => { });
        }

        /// <summary>Full SHA-256 of a file now (null if it can't be read): the check right before a duplicate is deleted.</summary>
        public static string HashNow(string path)
        {
            try
            {
                using (var sha = SHA256.Create())
                using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 1 << 20, FileOptions.SequentialScan))
                    return BitConverter.ToString(sha.ComputeHash(fs)).Replace("-", "");
            }
            catch (Exception) { return null; }
        }

        /// <summary>The group a file was found in, or null.</summary>
        public Group GroupOf(int id)
        {
            if (State != "done") return null;
            foreach (var g in Groups) if (Array.IndexOf(g.Ids, id) >= 0) return g;
            return null;
        }

        string HashFile(Cand c, long limit, byte[] buf)
        {
            long done = 0;
            try
            {
                using (var md5 = SHA256.Create())   // SHA-256: no practical way to make two different files match
                using (var fs = new FileStream(c.Path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 4096,
                                               limit == long.MaxValue ? FileOptions.SequentialScan : FileOptions.None))
                {
                    if (fs.Length != c.Size) return null;          // changed since the scan
                    long want = Math.Min(limit, c.Size);
                    while (done < want)
                    {
                        if (Cancel) return null;
                        int n = fs.Read(buf, 0, (int)Math.Min(buf.Length, want - done));
                        if (n <= 0) break;
                        md5.TransformBlock(buf, 0, n, null, 0);
                        done += n;
                        Interlocked.Add(ref BytesDone, n);
                    }
                    md5.TransformFinalBlock(buf, 0, 0);
                    return BitConverter.ToString(md5.Hash).Replace("-", "").ToLowerInvariant();
                }
            }
            catch (Exception) { return null; }
            finally
            {
                // keep the progress bar honest when a file stops early
                long left = Math.Min(limit, c.Size) - done;
                if (left > 0) Interlocked.Add(ref BytesDone, left);
            }
        }

        // ---------------------------------------------------------------- JSON for the UI

        /// <summary>Progress, plus the groups once done. Items deleted since are dropped; groups need 2 live copies.</summary>
        public Json ToJson(int limit)
        {
            var j = new Json().Obj().P("state", State).P("phase", Phase).P("scope", Scope).P("scopePath", ScopePath)
                .P("min", MinSize).P("filesTotal", Interlocked.Read(ref FilesTotal)).P("filesDone", Interlocked.Read(ref FilesDone))
                .P("bytesTotal", Interlocked.Read(ref BytesTotal)).P("bytesDone", Interlocked.Read(ref BytesDone))
                .P("unreadable", Interlocked.Read(ref Unreadable)).P("candidates", Candidates)
                .P("seconds", State == "hashing" ? Clock.Elapsed.TotalSeconds : Seconds).P("error", Error);
            if (State != "done") return j.EndObj();
            j.P("finishedAt", FinishedAt.ToString("HH:mm"));
            bool bySize = t.BySize;
            long wasted = 0, files = 0; int count = 0;
            var live = new List<KeyValuePair<Group, List<int>>>();
            lock (t.Lock)
            {
                foreach (var g in Groups)
                {
                    var ids = g.Ids.Where(i => t.IsLive(i)).ToList();
                    if (ids.Count < 2) continue;
                    long each = bySize ? t.Size[ids[0]] : t.Alloc[ids[0]];
                    wasted += each * (ids.Count - 1); files += ids.Count; count++;
                    // keep the oldest copy first (the one "Select extra copies" leaves alone), then the shortest path
                    ids = ids.OrderBy(i => t.Mtime[i]).ThenBy(i => t.Path(i).Length).ToList();
                    live.Add(new KeyValuePair<Group, List<int>>(g, ids));
                }
                j.P("groups", count).P("files", files).P("wasted", wasted).Key("items").Arr();
                foreach (var kv in live.OrderByDescending(kv => kv.Key.Size * (kv.Value.Count - 1)).Take(limit))
                {
                    var g = kv.Key;
                    j.Obj().P("size", g.Size).P("hash", g.Hash).P("wasted", (bySize ? g.Size : t.Alloc[kv.Value[0]]) * (kv.Value.Count - 1)).Key("files").Arr();
                    foreach (int i in kv.Value)
                        j.Obj().P("id", i).P("n", t.Name(i)).P("path", t.Path(i)).P("f", (long)t.Flags[i]).P("s", t.Size[i]).P("a", t.Alloc[i])
                         .P("m", Server.JsTime(t.Mtime[i])).P("e", t.Ext[i]).EndObj();
                    j.EndArr().EndObj();
                }
                j.EndArr();
            }
            return j.EndObj();
        }

        /// <summary>Totals of the finished search for the Insights card (null while running or when nothing found).</summary>
        public void Totals(Tree tree, out long wasted, out int groups, out List<int> top, out List<long> topWasted)
        {
            wasted = 0; groups = 0; top = new List<int>(); topWasted = new List<long>();
            bool bySize = tree.BySize;
            lock (tree.Lock)
                foreach (var g in Groups)
                {
                    var ids = g.Ids.Where(i => tree.IsLive(i)).ToList();
                    if (ids.Count < 2) continue;
                    long w = (bySize ? tree.Size[ids[0]] : tree.Alloc[ids[0]]) * (ids.Count - 1);
                    wasted += w; groups++;
                    if (top.Count < 6) { top.Add(ids.OrderBy(i => tree.Mtime[i]).First()); topWasted.Add(w); }
                }
        }
    }
}
