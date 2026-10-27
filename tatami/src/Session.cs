using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

namespace Tatami
{
    /// <summary>
    /// One scan: builds a Tree for a drive or folder and finishes it (hardlinks, totals, order).
    /// Admin scans run in an elevated copy of Tatami.exe (`--elevated-scan`) that writes progress to a text file
    /// and the finished tree to a .tatami snapshot, so this window never runs elevated.
    /// </summary>
    sealed class Session
    {
        public Tree Tree;
        public Scanner Scanner;
        public volatile string State = "idle";   // idle | elevating | scanning | finishing | done | cancelled | error
        public string Error;
        public string Path;
        public bool Admin;
        public volatile Baseline Baseline;      // folder sizes from the previous scan of the same path (Insights)
        public volatile bool BaselineLoading;
        public volatile Dupes Dupes;            // duplicate search of this scan (null until started)

        // progress of an elevated helper (read from its progress file)
        long xFiles, xDirs, xBytes, xDenied; double xSeconds; string xCurrent = "";
        string cancelFile;

        public long Files { get { var s = Scanner; return s != null ? s.FilesSeen : xFiles; } }
        public long Dirs { get { var s = Scanner; return s != null ? s.DirsSeen : xDirs; } }
        public long Bytes { get { var s = Scanner; return s != null ? s.BytesSeen : xBytes; } }
        public long Denied { get { var s = Scanner; return s != null ? s.Denied : xDenied; } }
        public double Seconds { get { var s = Scanner; return s != null ? s.Clock.Elapsed.TotalSeconds : xSeconds; } }
        public string Current { get { var s = Scanner; return s != null ? s.Current : xCurrent; } }

        public static string NormalizePath(string path)
        {
            path = path.Trim().Trim('"');
            if (path.Length == 2 && path[1] == ':') path += "\\";
            path = System.IO.Path.GetFullPath(path);
            if (path.Length > 3) path = path.TrimEnd('\\');
            return path;
        }

        public void Start(string path, bool background, bool admin = false)
        {
            Path = NormalizePath(path);
            Admin = admin && !Native.IsUserAnAdmin();
            State = Admin ? "elevating" : "scanning";
            ThreadStart run = Admin ? (ThreadStart)RunElevated : Run;
            if (background) { var th = new Thread(run); th.IsBackground = true; th.Start(); }
            else run();
        }

        /// <summary>Load the previous snapshot (for "what changed") and store this scan, in the background.</summary>
        void AfterDone(Tree t)
        {
            if (Program.NoHistory) return;
            BaselineLoading = true;
            var th = new Thread(() =>
            {
                try { Baseline = History.Previous(t.RootPath, t.ScannedAt); } catch (Exception e) { Program.Log("history read: " + e); }
                BaselineLoading = false;
                try { History.Add(t); } catch (Exception e) { Program.Log("history save: " + e); }
            });
            th.IsBackground = true;
            th.Priority = ThreadPriority.BelowNormal;
            th.Start();
        }

        public static Session FromTree(Tree t, string file)
        {
            t.Method = "Saved scan · " + System.IO.Path.GetFileName(file);
            return new Session { Tree = t, Path = t.RootPath, State = "done" };
        }

        public static Tree NewTree(string path)
        {
            var tree = new Tree(1 << 18);
            tree.RootPath = path;
            tree.Volume = System.IO.Path.GetPathRoot(path);
            FillVolume(tree);
            lock (tree.Lock)
            {
                tree.Reserve(1, 0);
                tree.NameOff[0] = tree.AddName(path);
                tree.NameLen[0] = (ushort)Math.Min(path.Length, 65535);
                tree.Flags[0] = Tree.F_DIR;
                tree.Parent[0] = 0;
                try { tree.Mtime[0] = Directory.GetLastWriteTimeUtc(path).ToFileTimeUtc(); } catch { }
            }
            return tree;
        }

        static int Threads { get { return Math.Max(4, Math.Min(32, Environment.ProcessorCount * 2)); } }

        void Run()
        {
            try
            {
                var clock = Stopwatch.StartNew();
                var tree = NewTree(Path);
                if (Native.IsUserAnAdmin() && Native.EnablePrivilege("SeBackupPrivilege")) tree.Method = "Administrator scan";
                Tree = tree;
                Scanner = new Scanner(tree);
                Scanner.Run(0, Path, Threads);
                if (Scanner.Cancel) { State = "cancelled"; return; }
                State = "finishing";
                Finish(tree);
                tree.ScanSeconds = clock.Elapsed.TotalSeconds;
                tree.ScannedAt = DateTime.Now;
                State = "done";
                AfterDone(tree);
            }
            catch (Exception e)
            {
                Error = e.Message;
                State = "error";
            }
        }

        public static void Finish(Tree tree)
        {
            tree.DedupHardlinks();
            tree.Aggregate();
            tree.SortAll();
        }

        /// <summary>Scan one folder of a finished tree again (after the user changed things on disk).</summary>
        public static double Rescan(Tree t, int node)
        {
            string path;
            lock (t.Lock)
            {
                if (t.Busy) throw new InvalidOperationException("Tatami is already rescanning a folder.");
                t.Busy = true;     // the API answers "busy" instead of reading a tree that is being rebuilt
                path = t.Path(node);
                t.DropChildren(node);
            }
            try
            {
                var sc = new Scanner(t);
                sc.Run(node, path, Threads);
                lock (t.Lock) Finish(t);
                return sc.Clock.Elapsed.TotalSeconds;
            }
            finally { lock (t.Lock) t.Busy = false; }
        }

        static void FillVolume(Tree t)
        {
            ulong free, total, totalFree;
            if (Native.GetDiskFreeSpaceExW(t.Volume, out free, out total, out totalFree))
            {
                t.DriveTotal = (long)total;
                t.DriveFree = (long)totalFree;
            }
            uint spc, bps, fc, tc;
            if (Native.GetDiskFreeSpaceW(t.Volume, out spc, out bps, out fc, out tc)) t.ClusterSize = (long)spc * bps;
        }

        public void Cancel()
        {
            var s = Scanner; if (s != null) s.Cancel = true;
            var d = Dupes; if (d != null) d.Cancel = true;
            var cf = cancelFile; if (cf != null) try { File.WriteAllText(cf, "cancel"); } catch { }
        }

        // ---------------------------------------------------------------- elevated helper (client side)

        void RunElevated()
        {
            string dir = System.IO.Path.Combine(Program.DataDir, "elevated");
            Directory.CreateDirectory(dir);
            string outFile = System.IO.Path.Combine(dir, "scan.tatami"), prog = System.IO.Path.Combine(dir, "progress.txt");
            cancelFile = System.IO.Path.Combine(dir, "cancel.txt");
            foreach (var f in new[] { outFile, prog, cancelFile }) try { File.Delete(f); } catch { }
            var info = new ShellExecuteInfo();
            info.cbSize = Marshal.SizeOf(typeof(ShellExecuteInfo));
            info.fMask = 0x40;    // SEE_MASK_NOCLOSEPROCESS
            info.lpVerb = "runas";
            info.lpFile = Process.GetCurrentProcess().MainModule.FileName;
            info.lpParameters = "--elevated-scan \"" + Path.TrimEnd('\\') + (Path.Length <= 3 ? "\\\\" : "") + "\" --out \"" + outFile + "\" --progress \"" + prog + "\" --cancel \"" + cancelFile + "\"";
            info.nShow = 0;
            if (!Native.ShellExecuteExW(ref info) || info.hProcess == IntPtr.Zero)
            {
                int err = Marshal.GetLastWin32Error();
                Error = err == 1223 ? "Administrator permission wasn't given, so nothing was scanned." : "Couldn't start the administrator scan (error " + err + ").";
                State = err == 1223 ? "cancelled" : "error";
                return;
            }
            State = "scanning";
            try
            {
                while (Native.WaitForSingleObject(info.hProcess, 150) == 0x102)   // WAIT_TIMEOUT
                    ReadProgress(prog);
                uint code;
                Native.GetExitCodeProcess(info.hProcess, out code);
                ReadProgress(prog);
                if (code == 3) { State = "cancelled"; return; }
                if (code != 0 || !File.Exists(outFile)) { Error = "The administrator scan stopped (code " + code + ")."; State = "error"; return; }
                State = "finishing";
                var t = Tree.Load(outFile);
                t.SortAll();
                Tree = t;
                State = "done";
                AfterDone(t);
                try { File.Delete(outFile); } catch { }
            }
            catch (Exception e) { Error = e.Message; State = "error"; }
            finally { Native.CloseHandle(info.hProcess); }
        }

        void ReadProgress(string file)
        {
            try
            {
                var p = File.ReadAllText(file).Split('\t');
                if (p.Length < 6) return;
                var ci = CultureInfo.InvariantCulture;
                xFiles = long.Parse(p[0], ci); xDirs = long.Parse(p[1], ci); xBytes = long.Parse(p[2], ci);
                xDenied = long.Parse(p[3], ci); xSeconds = double.Parse(p[4], ci); xCurrent = p[5];
                if (p.Length > 6 && p[6] == "finishing") State = "finishing";
                if (Tree == null && p.Length > 8) { DriveUsed = long.Parse(p[7], ci); }
            }
            catch { }
        }

        public long DriveUsed = -1;

        // ---------------------------------------------------------------- elevated helper (the elevated process)

        public static int ElevatedMain(string path, string outFile, string progFile, string cancel)
        {
            var s = new Session();
            s.Start(path, true);
            var ci = CultureInfo.InvariantCulture;
            while (s.State == "scanning" || s.State == "finishing")
            {
                Thread.Sleep(150);
                if (cancel != null && File.Exists(cancel)) s.Cancel();
                try
                {
                    long used = s.Tree != null ? s.Tree.DriveTotal - s.Tree.DriveFree : 0;
                    File.WriteAllText(progFile, string.Join("\t", s.Files.ToString(ci), s.Dirs.ToString(ci), s.Bytes.ToString(ci),
                        s.Denied.ToString(ci), s.Seconds.ToString("F2", ci), (s.Current ?? "").Replace('\t', ' '), s.State, used.ToString(ci), "x"));
                }
                catch { }
            }
            if (s.State == "cancelled") return 3;
            if (s.State != "done") return 2;
            s.Tree.ScannedAt = DateTime.Now;
            s.Tree.Save(outFile);
            return 0;
        }
    }
}
