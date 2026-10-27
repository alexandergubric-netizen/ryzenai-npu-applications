using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;

namespace Tatami
{
    /// <summary>
    /// Snapshot history: every finished scan is stored compressed in %LOCALAPPDATA%\Tatami\history so the next
    /// scan of the same drive/folder can show what grew. Keeps the newest few per scanned path.
    /// </summary>
    static class History
    {
        const int Keep = 4;
        static string Dir { get { var d = Path.Combine(Program.DataDir, "history"); Directory.CreateDirectory(d); return d; } }

        public static string Key(string root)
        {
            uint h = 2166136261;
            foreach (char c in root.ToLowerInvariant()) { h ^= c; h *= 16777619; }
            var safe = new StringBuilder();
            foreach (char c in root) safe.Append(char.IsLetterOrDigit(c) ? c : '_');
            string s = safe.ToString().Trim('_');
            if (s.Length > 40) s = s.Substring(s.Length - 40);
            return s + "-" + h.ToString("x8");
        }

        public static void Add(Tree t)
        {
            string key = Key(t.RootPath);
            string file = Path.Combine(Dir, key + "_" + t.ScannedAt.ToString("yyyyMMdd-HHmmss") + ".tatami.gz");
            string tmp = file + ".tmp";
            using (var fs = new FileStream(tmp, FileMode.Create))
            using (var gz = new GZipStream(fs, CompressionLevel.Fastest))
                t.Save(gz);     // no lock: only deletes/rescans change a finished tree, and a stale snapshot is harmless
            File.Move(tmp, file);
            foreach (var old in List(t.RootPath).Skip(Keep)) try { File.Delete(old); } catch { }
            // nothing older than MaxAgeDays stays, whatever was scanned
            foreach (var f in Directory.GetFiles(Dir, "*.tatami.gz"))
                try { if (File.GetLastWriteTime(f) < DateTime.Now.AddDays(-MaxAgeDays)) File.Delete(f); } catch { }
        }

        public const int MaxAgeDays = 90;

        /// <summary>Delete every saved snapshot (Settings → Clear scan history). Returns how many went.</summary>
        public static int Clear()
        {
            int n = 0;
            string d = Path.Combine(Program.DataDirNoCreate, "history");
            if (!Directory.Exists(d)) return 0;
            foreach (var f in Directory.GetFiles(d)) try { File.Delete(f); n++; } catch { }
            return n;
        }

        /// <summary>Snapshots of this path, newest first.</summary>
        public static List<string> List(string root)
        {
            string key = Key(root);
            return Directory.GetFiles(Dir, key + "_*.tatami.gz").OrderByDescending(f => f, StringComparer.Ordinal).ToList();
        }

        public static Tree Load(string file)
        {
            using (var fs = new FileStream(file, FileMode.Open, FileAccess.Read))
            using (var gz = new GZipStream(fs, CompressionMode.Decompress))
            using (var bs = new BufferedStream(gz, 1 << 20))
                return Tree.Load(bs);
        }

        /// <summary>Folder sizes of the newest snapshot older than `before` (null if none).</summary>
        public static Baseline Previous(string root, DateTime before)
        {
            foreach (var f in List(root))
            {
                Tree old;
                try { old = Load(f); } catch { continue; }
                if (old.ScannedAt >= before) continue;     // that's this scan (or a newer one)
                var b = new Baseline { When = old.ScannedAt };
                for (int i = 0; i < old.Count; i++)
                    if ((old.Flags[i] & Tree.F_DIR) != 0 && (old.Flags[i] & Tree.F_DELETED) == 0)
                        b.Dirs[old.Path(i)] = new[] { old.Alloc[i], old.Size[i] };
                // every live file and folder by path hash (treemap "growth" colours)
                var hashes = old.PathHashes();
                var dead = new bool[old.Count];
                var idx = new List<int>(old.Count);
                for (int i = 0; i < old.Count; i++)
                {
                    dead[i] = (old.Flags[i] & Tree.F_DELETED) != 0 || (i > 0 && dead[old.Parent[i]]);
                    if (!dead[i]) idx.Add(i);
                }
                var keys = new ulong[idx.Count]; var ids = idx.ToArray();
                for (int k = 0; k < ids.Length; k++) keys[k] = hashes[ids[k]];
                Array.Sort(keys, ids);
                b.Keys = keys; b.Alloc = new long[ids.Length]; b.Size = new long[ids.Length];
                for (int k = 0; k < ids.Length; k++)
                {
                    int i = ids[k];
                    bool dir = (old.Flags[i] & Tree.F_DIR) != 0;
                    b.Alloc[k] = dir ? old.Alloc[i] : old.Counted(i, false);
                    b.Size[k] = dir ? old.Size[i] : old.Counted(i, true);
                }
                return b;
            }
            return null;
        }
    }

    sealed class Baseline
    {
        public DateTime When;
        public readonly Dictionary<string, long[]> Dirs = new Dictionary<string, long[]>(StringComparer.OrdinalIgnoreCase);
        public ulong[] Keys;            // sorted path hashes (Tree.PathHashes) of every live node
        public long[] Alloc, Size;      // their sizes then, parallel to Keys

        /// <summary>Size of a node in the previous scan by path hash; -1 if it didn't exist then.</summary>
        public long Find(ulong key, bool bySize)
        {
            if (Keys == null) return -1;
            int k = Array.BinarySearch(Keys, key);
            return k < 0 ? -1 : bySize ? Size[k] : Alloc[k];
        }
    }

    /// <summary>Cleanup suggestions and "what changed" for the Insights tab.</summary>
    static class Insights
    {
        sealed class Card
        {
            public string Icon, Title, Text;
            public long? Size;
            public List<int> Items = new List<int>();
            public List<long> Deltas;              // signed change per item (changes card)
            public List<long> Values;              // shown per item instead of its size (duplicates: space wasted)
            public List<string> Actions = new List<string>();   // pre-rendered JSON objects
        }

        public static Json Build(Session s, Tree t, int scope)
        {
            var cards = new List<Card>();
            bool bySize = t.BySize;
            Func<int, long> val = i => bySize ? t.Size[i] : t.Alloc[i];
            string user = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string win = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
            long now = DateTime.UtcNow.ToFileTimeUtc();
            long year = TimeSpan.FromDays(365).Ticks;

            lock (t.Lock)
            {
                // ---- what changed since the previous scan
                var b = s.Baseline;
                if (b != null && scope == 0)
                {
                    var c = Changes(t, b, val, bySize);
                    if (c != null) cards.Add(c);
                }

                // ---- Recycle Bin
                var rb = new ShQueryRbInfo { cbSize = System.Runtime.InteropServices.Marshal.SizeOf(typeof(ShQueryRbInfo)) };
                if (Native.SHQueryRecycleBinW(t.Volume, ref rb) == 0 && rb.i64Size > 1 << 20)
                    cards.Add(new Card
                    {
                        Icon = "", Title = "Recycle Bin", Size = rb.i64Size,
                        Text = rb.i64NumItems + " deleted items on " + t.Volume.TrimEnd('\\') + " still take up space until you empty the Recycle Bin.",
                        Actions = { A("Open Recycle Bin", "open", "\"what\":\"recycle\"") }
                    });

                // ---- temporary files
                var temps = new List<int>();
                foreach (var p in new[] { Path.GetTempPath(), Path.Combine(win, "Temp"), Path.Combine(local, "CrashDumps"), Path.Combine(win, "Minidump") })
                {
                    int id = Server.Resolve(t, p.TrimEnd('\\'));
                    if (id > 0 && Under(t, id, scope) && val(id) > 0) temps.Add(id);
                }
                if (temps.Sum(val) > 50L << 20)
                    cards.Add(new Card
                    {
                        Icon = "", Title = "Temporary files", Size = temps.Sum(val), Items = temps,
                        Text = "Leftovers from installers, apps and crashes. Windows' Storage Sense can clear the ones not in use.",
                        Actions = { A("Open Storage Sense", "open", "\"what\":\"storage\""), A("Show folder", "zoom", "\"id\":" + temps.OrderByDescending(val).First()) }
                    });

                // ---- Windows Update cache
                int wu = Server.Resolve(t, Path.Combine(win, @"SoftwareDistribution\Download"));
                if (wu > 0 && Under(t, wu, scope) && val(wu) > 200L << 20)
                    cards.Add(new Card
                    {
                        Icon = "", Title = "Windows Update downloads", Size = val(wu), Items = { wu },
                        Text = "Update files Windows already installed. Disk Cleanup → \"Clean up system files\" removes them safely.",
                        Actions = { A("Open Disk Cleanup", "open", "\"what\":\"cleanmgr\"") }
                    });

                // ---- Downloads
                int dl = Server.Resolve(t, Path.Combine(user, "Downloads"));
                if (dl > 0 && Under(t, dl, scope) && val(dl) > 500L << 20)
                {
                    long old = 0; var big = new List<int>();
                    Walk(t, dl, f => { if (t.Mtime[f] < now - year / 2) old += t.Counted(f, bySize); });
                    foreach (int k in t.Children(dl).Take(6)) big.Add(k);
                    cards.Add(new Card
                    {
                        Icon = "", Title = "Downloads", Size = val(dl), Items = big,
                        Text = Fmt.Bytes(old) + " of it hasn't changed in over 6 months — old installers and archives are usually safe to delete.",
                        Actions = { A("Show files older than 6 months", "files", "\"root\":" + dl + ",\"filter\":{\"olderDays\":182}"), A("Zoom in", "zoom", "\"id\":" + dl) }
                    });
                }

                // ---- big old files
                var bigOld = new List<int>(); long bigOldSum = 0;
                Walk(t, scope, f =>
                {
                    if (t.Counted(f, bySize) >= 500L << 20 && t.Mtime[f] > 0 && t.Mtime[f] < now - year && !IsSystem(t, f, win))
                    { bigOld.Add(f); bigOldSum += t.Counted(f, bySize); }
                });
                if (bigOld.Count > 0)
                    cards.Add(new Card
                    {
                        Icon = "", Title = "Big files you haven't touched in a year", Size = bigOldSum,
                        Items = bigOld.OrderByDescending(val).Take(6).ToList(),
                        Text = bigOld.Count + " files over 500 MB, unchanged for more than a year (Windows files left out).",
                        Actions = { A("List them", "files", "\"filter\":{\"min\":524288000,\"olderDays\":365}") }
                    });

                // ---- duplicate files (the search runs on demand: it reads file contents)
                var dup = s.Dupes;
                if (dup == null || dup.State == "cancelled" || dup.State == "error")
                    cards.Add(new Card
                    {
                        Icon = "\uE8C8", Title = "Duplicate files",
                        Text = "Find files stored more than once (1 MB and bigger). Tatami compares their contents, not just names" +
                               (dup != null && dup.State == "error" ? " — the last search failed: " + dup.Error : ".") ,
                        Actions = { A("Find duplicates", "dupes", "\"start\":true") }
                    });
                else if (dup.State == "hashing")
                    cards.Add(new Card
                    {
                        Icon = "\uE8C8", Title = "Duplicate files",
                        Text = "Searching… " + dup.Phase.ToLowerInvariant() + ".",
                        Actions = { A("Show progress", "dupes", "") }
                    });
                else
                {
                    long wasted; int groups; List<int> top; List<long> topW;
                    dup.Totals(t, out wasted, out groups, out top, out topW);
                    string where = dup.Scope == 0 ? "" : " in " + dup.ScopePath;
                    cards.Add(new Card
                    {
                        Icon = "\uE8C8", Title = "Duplicate files", Size = groups > 0 ? wasted : (long?)null, Items = top, Values = topW,
                        Text = groups > 0
                            ? groups + (groups == 1 ? " set" : " sets") + " of identical files" + where + ". Keeping one copy of each would free this much:"
                            : "No identical files of " + Fmt.Bytes(dup.MinSize) + " or more" + where + ".",
                        Actions = { A(groups > 0 ? "Review duplicates" : "Show search", "dupes", ""), A("Search again", "dupes", "\"start\":true") }
                    });
                }

                // ---- disk images & virtual disks
                long imgSum = 0; var imgs = new List<int>();
                Walk(t, scope, f =>
                {
                    int e = t.Ext[f];
                    if (e < t.Exts.Count && t.Exts.Category(e) == ExtTable.C_DISK && t.Counted(f, bySize) > 100L << 20 && !IsSystem(t, f, win))
                    { imgs.Add(f); imgSum += t.Counted(f, bySize); }
                });
                if (imgSum > 1L << 30)
                    cards.Add(new Card
                    {
                        Icon = "", Title = "Disk images & virtual machines", Size = imgSum,
                        Items = imgs.OrderByDescending(val).Take(6).ToList(),
                        Text = "ISO files, WSL/Hyper-V/VirtualBox disks and similar. Big, and easy to forget once a VM or install is done.",
                        Actions = { A("List them", "files", "\"filter\":{\"cat\":" + ExtTable.C_DISK + ",\"min\":104857600}") }
                    });

                // ---- developer & app caches
                var caches = new List<int>(); long cacheSum = 0;
                var cacheNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase) {
                    "node_modules", "Cache", "Code Cache", "GPUCache", "ShaderCache", "cache2", "DawnCache", "GrShaderCache",
                    "DXCache", "NVIDIA Corporation\\NV_Cache", "pip", "npm-cache", ".gradle", "__pycache__", "Service Worker" };
                WalkDirs(t, scope, d =>
                {
                    string n = t.Name(d);
                    if (!cacheNames.Contains(n)) return true;
                    if (val(d) >= 20L << 20) { caches.Add(d); cacheSum += val(d); }
                    return false;    // don't look inside a cache we already counted
                });
                if (cacheSum > 500L << 20)
                    cards.Add(new Card
                    {
                        Icon = "", Title = "Caches", Size = cacheSum, Items = caches.OrderByDescending(val).Take(6).ToList(),
                        Text = caches.Count + " cache folders (browsers, apps, node_modules, shader caches). Apps rebuild them when needed, but close the app first.",
                        Actions = { A("List them", "files", "\"filter\":{\"dirs\":true,\"q\":\"node_modules;Cache;Code Cache;GPUCache;ShaderCache;cache2;DawnCache;GrShaderCache;DXCache;npm-cache;.gradle\",\"min\":20971520}") }
                    });

                // ---- page file & hibernation
                if (scope == 0 && t.RootPath.Length <= 3)
                {
                    var sys = new List<int>();
                    foreach (var n in new[] { "pagefile.sys", "hiberfil.sys", "swapfile.sys" })
                    {
                        int id = Server.Resolve(t, t.RootPath + n);
                        if (id > 0) sys.Add(id);
                    }
                    long sysSum = sys.Sum(i => t.Alloc[i]);
                    if (sysSum > 1L << 30)
                        cards.Add(new Card
                        {
                            Icon = "", Title = "Page file & hibernation", Size = sysSum, Items = sys,
                            Text = "Windows manages these. Turning hibernation off (powercfg /h off) frees hiberfil.sys; the page file size is set in Advanced system settings.",
                            Actions = { A("Advanced system settings", "open", "\"what\":\"sysprops\"") }
                        });
                }

                // ---- invisible / protected space
                if (scope == 0 && t.RootPath.Length <= 3)
                {
                    long used = t.DriveTotal - t.DriveFree, un = used - t.Alloc[0];
                    if (un > 2L << 30)
                        cards.Add(new Card
                        {
                            Icon = "", Title = "System & protected space", Size = un,
                            Text = "Used space this scan couldn't open: restore points, shadow copies and folders only administrators can read. " +
                                   (Native.IsUserAnAdmin() ? "" : "Turn on \"Include protected folders\" and rescan to see inside."),
                            Actions = { A("System Protection settings", "open", "\"what\":\"protection\"") }
                        });
                }

                // ---- online-only files
                long cloud = 0; int cloudN = 0;
                Walk(t, scope, f => { if ((t.Flags[f] & Tree.F_CLOUD) != 0 && (t.Flags[f] & Tree.F_HARDLINK) == 0) { cloud += t.Size[f]; cloudN++; } });
                if (cloud > 100L << 20)
                    cards.Add(new Card
                    {
                        Icon = "", Title = "Online-only files", Size = cloud,
                        Text = cloudN + " files live in the cloud (OneDrive, phone link…) and take no space here. Switch to \"Size\" to see them in the map; \"On disk\" leaves them out.",
                    });
            }

            var j = new Json().Arr();
            foreach (var c in cards)
            {
                j.Obj().P("icon", c.Icon).P("title", c.Title).P("text", c.Text);
                if (c.Size.HasValue) j.P("size", c.Size.Value);
                if (c.Deltas != null) j.P("signed", true);
                j.Key("items").Arr();
                for (int k = 0; k < c.Items.Count; k++)
                {
                    int i = c.Items[k];
                    j.Obj().P("id", i).P("n", t.Name(i)).P("path", t.Path(i)).P("s", c.Deltas != null ? c.Deltas[k] : c.Values != null ? c.Values[k] : val(i));
                    if (c.Deltas != null) j.P("delta", true);
                    j.EndObj();
                }
                j.EndArr().Key("actions").Arr();
                foreach (var a in c.Actions) j.Raw(a);
                j.EndArr().EndObj();
            }
            return j.EndArr();
        }

        static string A(string label, string kind, string extra)
        {
            return "{\"label\":" + Json.Ser(label) + ",\"kind\":\"" + kind + "\"" + (extra.Length > 0 ? "," + extra : "") + "}";
        }

        static bool Under(Tree t, int i, int scope) { return t.IsUnder(i, scope); }

        static bool IsSystem(Tree t, int f, string win)
        {
            string p = t.Path(f);
            return p.StartsWith(win + "\\", StringComparison.OrdinalIgnoreCase) || ExtTable.IsSystemName(t.Name(f).ToLowerInvariant());
        }

        static void Walk(Tree t, int root, Action<int> file)
        {
            var st = new Stack<int>(); st.Push(root);
            while (st.Count > 0)
            {
                int d = st.Pop(); int s = t.First[d], n = t.NChild[d];
                for (int k = 0; k < n; k++)
                {
                    int c = s + k; byte f = t.Flags[c];
                    if ((f & Tree.F_DELETED) != 0) continue;
                    if ((f & Tree.F_DIR) != 0) st.Push(c); else file(c);
                }
            }
        }

        /// <summary>Visit folders; return false from the callback to skip a folder's contents.</summary>
        static void WalkDirs(Tree t, int root, Func<int, bool> dir)
        {
            var st = new Stack<int>(); st.Push(root);
            while (st.Count > 0)
            {
                int d = st.Pop(); int s = t.First[d], n = t.NChild[d];
                for (int k = 0; k < n; k++)
                {
                    int c = s + k; byte f = t.Flags[c];
                    if ((f & (Tree.F_DELETED | Tree.F_DIR)) != Tree.F_DIR) continue;
                    if (dir(c)) st.Push(c);
                }
            }
        }

        /// <summary>Folders that grew or shrank the most since the baseline, at the level that explains the change.</summary>
        static Card Changes(Tree t, Baseline b, Func<int, long> val, bool bySize)
        {
            int k = bySize ? 1 : 0;
            var delta = new Dictionary<int, long>();
            var paths = new Dictionary<int, string>();
            // compute paths top-down so each is one string concat
            paths[0] = t.RootPath.TrimEnd('\\');
            var order = new List<int> { 0 };
            for (int q = 0; q < order.Count; q++)
            {
                int d = order[q];
                foreach (int c in t.Children(d))
                    if (t.IsDir(c)) { paths[c] = paths[d] + "\\" + t.Name(c); order.Add(c); }
            }
            foreach (int d in order)
            {
                long[] old;
                string key = d == 0 ? t.RootPath : paths[d];
                long before = b.Dirs.TryGetValue(key, out old) ? old[k] : 0;
                delta[d] = val(d) - before;
            }
            long total = delta[0];
            long threshold = Math.Max(100L << 20, Math.Abs(t.Alloc[0]) / 1000);
            var picks = new List<int>();
            foreach (int d in order)
            {
                if (d == 0) continue;
                long dd = delta[d];
                if (Math.Abs(dd) < threshold) continue;
                // skip a folder if one child explains most of its change (report the child instead)
                bool explained = false;
                foreach (int c in t.Children(d))
                {
                    long cd;
                    if (t.IsDir(c) && delta.TryGetValue(c, out cd) && Math.Sign(cd) == Math.Sign(dd) && Math.Abs(cd) >= Math.Abs(dd) * 0.7) { explained = true; break; }
                }
                if (!explained) picks.Add(d);
            }
            picks = picks.OrderByDescending(d => Math.Abs(delta[d])).Take(8).ToList();
            var days = (DateTime.Now - b.When).TotalDays;
            string when = days < 1 ? "earlier today" : days < 2 ? "yesterday" : ((int)days) + " days ago";
            return new Card
            {
                Icon = "", Title = "Changes since " + b.When.ToString("d MMM yyyy, HH:mm"), Size = total, Items = picks,
                Deltas = picks.Select(d => delta[d]).ToList(),
                Text = (total >= 0 ? "Grew by " : "Shrank by ") + Fmt.Bytes(Math.Abs(total)) + " since the scan " + when + "." +
                       (picks.Count == 0 ? " No single folder changed by more than " + Fmt.Bytes(threshold) + "." : " These folders changed the most:"),
            };
        }
    }
}
