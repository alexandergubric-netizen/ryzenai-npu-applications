using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Threading;

namespace Tatami
{
    /// <summary>Things the user does to scanned items: open, show in Explorer, properties, delete.</summary>
    static class Actions
    {
        public static void Handle(Server srv, Tree t, string name, Dictionary<string, object> b, HttpListenerResponse res)
        {
            var ids = Json.Ls(b, "ids");
            if (ids.Count == 0 && b.ContainsKey("id")) ids.Add(Json.L(b, "id"));
            var paths = new List<string>();
            var nodes = new List<int>();
            lock (t.Lock)
                foreach (long l in ids)
                {
                    int id = (int)l;
                    if (!t.IsLive(id)) continue;
                    nodes.Add(id); paths.Add(t.Path(id));
                }
            if (paths.Count == 0) { Reply(res, 404, new Json().Obj().P("error", "Item no longer exists").EndObj()); return; }

            switch (name)
            {
                case "open":
                    Shell(paths[0], null);
                    Reply(res, 200, new Json().Obj().P("ok", true).EndObj());
                    return;
                case "reveal":
                    Process.Start("explorer.exe", "/select,\"" + paths[0] + "\"");
                    Reply(res, 200, new Json().Obj().P("ok", true).EndObj());
                    return;
                case "props":
                    Shell(paths[0], "properties");
                    Reply(res, 200, new Json().Obj().P("ok", true).EndObj());
                    return;
                case "delete":
                    Delete(srv, t, nodes, paths, Json.B(b, "permanent"), res);
                    return;
            }
            Reply(res, 404, new Json().Obj().P("error", "Unknown action").EndObj());
        }

        static void Reply(HttpListenerResponse res, int code, Json j)
        {
            var data = System.Text.Encoding.UTF8.GetBytes(j.ToString());
            res.StatusCode = code; res.ContentType = "application/json; charset=utf-8";
            res.ContentLength64 = data.Length; res.OutputStream.Write(data, 0, data.Length); res.OutputStream.Close();
        }

        /// <summary>ShellExecuteEx on an STA thread that stays alive while a Properties sheet is open.</summary>
        static void Shell(string path, string verb)
        {
            var th = new Thread(() =>
            {
                var info = new ShellExecuteInfo();
                info.cbSize = System.Runtime.InteropServices.Marshal.SizeOf(typeof(ShellExecuteInfo));
                info.lpFile = path; info.lpVerb = verb; info.nShow = 1;
                info.fMask = verb == "properties" ? 0x0000000Cu : 0u;     // SEE_MASK_INVOKEIDLIST
                if (verb == null) info.lpDirectory = Path.GetDirectoryName(path);
                Native.ShellExecuteExW(ref info);
                if (verb == "properties") Thread.Sleep(TimeSpan.FromMinutes(30));   // the sheet lives on this thread's apartment
            });
            th.SetApartmentState(ApartmentState.STA);
            th.IsBackground = true;
            th.Start();
        }

        /// <summary>Paths Tatami refuses to delete whatever the user clicks.</summary>
        public static string Protected(string path)
        {
            string p = path.TrimEnd('\\');
            if (p.Length <= 2) return "a whole drive";
            string win = Environment.GetFolderPath(Environment.SpecialFolder.Windows).TrimEnd('\\');
            string[] keep = {
                win, Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                Path.Combine(Path.GetPathRoot(win), "Users"),
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                Environment.GetFolderPath(Environment.SpecialFolder.Desktop),
            };
            foreach (var k in keep)
                if (!string.IsNullOrEmpty(k) && string.Equals(p, k.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
                    return "a Windows system folder";
            if (p.StartsWith(win + "\\", StringComparison.OrdinalIgnoreCase)) return "inside the Windows folder";
            // whole subtrees Windows and installed programs depend on (uninstall programs from Settings instead)
            string[] trees = {
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Microsoft"),
            };
            foreach (var k in trees)
                if (!string.IsNullOrEmpty(k) && p.StartsWith(k.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase))
                    return "part of an installed program or of Windows (uninstall it from Settings → Apps instead)";
            string users = Path.Combine(Path.GetPathRoot(win), "Users");
            if (string.Equals(Path.GetDirectoryName(p).TrimEnd('\\'), users, StringComparison.OrdinalIgnoreCase))
                return "a user's whole profile folder";
            string name = Path.GetFileName(p).ToLowerInvariant();
            if (Path.GetDirectoryName(p).TrimEnd('\\').Length <= 2 &&
                (name == "pagefile.sys" || name == "hiberfil.sys" || name == "swapfile.sys"))
                return "a file Windows manages itself (change it in System settings instead)";
            return null;
        }

        static void Delete(Server srv, Tree t, List<int> nodes, List<string> paths, bool permanent, HttpListenerResponse res)
        {
            var done = new List<int>();
            var errors = new List<string>();
            var dupes = srv.Session != null ? srv.Session.Dupes : null;
            var deleting = new HashSet<int>(nodes);
            for (int k = 0; k < paths.Count; k++)
            {
                string path = paths[k], name = Path.GetFileName(path);
                string why = nodes[k] == 0 ? "the folder you scanned (delete it in File Explorer if you really mean to)" : Protected(path);
                if (why != null) { errors.Add(name + ": not deleted - it is " + why + "."); continue; }
                long size; lock (t.Lock) size = t.Size[nodes[k]];
                try
                {
                    uint attr = Native.GetFileAttributesW(Long(path));
                    if (attr == 0xFFFFFFFF) throw new IOException("it is no longer on the disk.");
                    bool isDir = (attr & 0x10) != 0, isLink = (attr & 0x400) != 0;   // DIRECTORY, REPARSE_POINT
                    // a duplicate is deleted only if it still matches a copy that stays (re-read now, SHA-256)
                    var g = dupes != null && !isDir ? dupes.GroupOf(nodes[k]) : null;
                    if (g != null) CheckStillDuplicate(t, g, nodes[k], deleting, path);
                    if (permanent)
                    {
                        if (isLink)
                        {
                            // a junction or symbolic link: remove only the link, never what it points to
                            if (isDir) { if (!Native.RemoveDirectoryW(Long(path))) throw new IOException("Windows couldn't remove the link (error " + System.Runtime.InteropServices.Marshal.GetLastWin32Error() + ")."); }
                            else { if (!Native.DeleteFileW(Long(path))) throw new IOException("Windows couldn't remove the link (error " + System.Runtime.InteropServices.Marshal.GetLastWin32Error() + ")."); }
                        }
                        else if (isDir) DeleteTree(path);
                        else { File.SetAttributes(path, FileAttributes.Normal); File.Delete(path); }
                    }
                    else
                    {
                        string bin = RecycleProblem(path, isLink ? 0 : size);
                        if (bin != null) throw new IOException(bin + " Nothing was deleted. Use \"Delete permanently\" if you really want it gone.");
                        var op = new ShFileOpStruct();
                        op.wFunc = 3;                               // FO_DELETE
                        op.pFrom = path + "\0\0";
                        // ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI | WANTNUKEWARNING: if Windows would still
                        // destroy it instead of recycling, it asks first rather than deleting silently
                        op.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400 | 0x4000;
                        int rc = Native.SHFileOperationW(ref op);
                        if (op.fAnyOperationsAborted != 0) throw new IOException("not deleted (you said no to deleting it permanently).");
                        if (rc != 0) throw new IOException("Windows couldn't move it to the Recycle Bin (code " + rc + "). It may be open in another program.");
                    }
                }
                catch (Exception e)
                {
                    errors.Add(name + ": " + e.Message);
                }
                // honest result: only what is really gone leaves the tree (long paths checked with \\?\)
                bool gone = Native.GetFileAttributesW(Long(path)) == 0xFFFFFFFF;
                if (gone) { lock (t.Lock) t.Remove(nodes[k]); done.Add(nodes[k]); }
            }
            var j = new Json().Obj().Key("deleted").Arr();
            foreach (int d in done) j.Val(d);
            j.EndArr().Key("errors").Arr();
            foreach (var e in errors) j.Val(e);
            Reply(res, 200, j.EndArr().EndObj());
        }

        static string Long(string path)
        {
            if (path.StartsWith(@"\\?\")) return path;
            return path.StartsWith(@"\\") ? @"\\?\UNC\" + path.Substring(2) : @"\\?\" + path;
        }

        static void CheckStillDuplicate(Tree t, Dupes.Group g, int id, HashSet<int> deleting, string path)
        {
            string partner = null;
            lock (t.Lock)
                foreach (int o in g.Ids)
                    if (o != id && !deleting.Contains(o) && t.IsLive(o)) { partner = t.Path(o); break; }
            if (partner == null) return;   // every copy goes: the UI warned about that
            var a = new FileInfo(path); var b = new FileInfo(partner);
            string ha = a.Exists && b.Exists && a.Length == b.Length ? Dupes.HashNow(path) : null;
            if (ha == null || ha != Dupes.HashNow(partner))
                throw new IOException("not deleted - it is no longer an exact copy of " + partner + " (it changed after the duplicate search).");
        }

        /// <summary>Why the Recycle Bin can't take this item (so Windows would delete it for good), or null.</summary>
        public static string RecycleProblem(string path, long size)
        {
            if (path.Length >= 260) return "It is too deep in folders for the Recycle Bin.";
            string root = Path.GetPathRoot(path);
            uint type = Native.GetDriveTypeW(root);
            if (type != 3) return "The Recycle Bin doesn't cover " + (type == 4 ? "network folders" : type == 2 ? "removable drives" : "this drive") + ".";
            var vol = new System.Text.StringBuilder(64);
            if (!Native.GetVolumeNameForVolumeMountPointW(root, vol, 64)) return null;   // subst/odd mounts: Windows asks (nuke warning)
            string guid = vol.ToString();
            int a = guid.IndexOf('{'), b = guid.IndexOf('}');
            if (a < 0 || b < a) return null;
            try
            {
                using (var k = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume\" + guid.Substring(a, b - a + 1)))
                {
                    if (k == null) return null;
                    object nuke = k.GetValue("NukeOnDelete"), max = k.GetValue("MaxCapacity");
                    if (nuke is int && (int)nuke != 0) return "The Recycle Bin is turned off for drive " + root.TrimEnd('\\') + ".";
                    if (max is int && size > (long)(int)max * 1024 * 1024)
                        return "It is bigger than the Recycle Bin of drive " + root.TrimEnd('\\') + " (" + Fmt.Bytes((long)(int)max * 1024 * 1024) + ").";
                }
            }
            catch { }
            return null;
        }

        static void DeleteTree(string dir)
        {
            foreach (var f in Directory.EnumerateFiles(dir, "*", SearchOption.TopDirectoryOnly))
            {
                try { File.SetAttributes(f, FileAttributes.Normal); } catch { }
                File.Delete(f);
            }
            foreach (var d in Directory.EnumerateDirectories(dir))
            {
                var attr = File.GetAttributes(d);
                if ((attr & FileAttributes.ReparsePoint) != 0) Directory.Delete(d);   // unlink junctions, never follow
                else DeleteTree(d);
            }
            Directory.Delete(dir);
        }
    }
}
