using System;
using System.Runtime.InteropServices;
using System.Threading;

namespace Tatami
{
    /// <summary>The modern Windows folder picker / save dialog (IFileDialog), shown on its own STA thread.</summary>
    static class Dialogs
    {
        [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")] class FileOpenDialogRCW { }
        [ComImport, Guid("C0B4E2F3-BA21-4773-8DBA-335EC946EB8B")] class FileSaveDialogRCW { }

        [ComImport, Guid("42f85136-db7e-439c-85f1-e4075d135fc8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IFileDialog
        {
            [PreserveSig] int Show(IntPtr parent);
            void SetFileTypes(uint cFileTypes, [MarshalAs(UnmanagedType.LPArray)] ComDlgFilterSpec[] rgFilterSpec);
            void SetFileTypeIndex(uint iFileType);
            void GetFileTypeIndex(out uint piFileType);
            void Advise(IntPtr pfde, out uint pdwCookie);
            void Unadvise(uint dwCookie);
            void SetOptions(uint fos);
            void GetOptions(out uint pfos);
            void SetDefaultFolder(IShellItem psi);
            void SetFolder(IShellItem psi);
            void GetFolder(out IShellItem ppsi);
            void GetCurrentSelection(out IShellItem ppsi);
            void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string pszName);
            void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string pszName);
            void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string pszTitle);
            void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string pszText);
            void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string pszLabel);
            void GetResult(out IShellItem ppsi);
            void AddPlace(IShellItem psi, int fdap);
            void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string pszDefaultExtension);
            void Close(int hr);
            void SetClientGuid(ref Guid guid);
            void ClearClientData();
            void SetFilter(IntPtr pFilter);
        }

        [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IShellItem
        {
            void BindToHandler(IntPtr pbc, ref Guid bhid, ref Guid riid, out IntPtr ppv);
            void GetParent(out IShellItem ppsi);
            void GetDisplayName(uint sigdnName, [MarshalAs(UnmanagedType.LPWStr)] out string ppszName);
            void GetAttributes(uint sfgaoMask, out uint psfgaoAttribs);
            void Compare(IShellItem psi, uint hint, out int piOrder);
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct ComDlgFilterSpec
        {
            [MarshalAs(UnmanagedType.LPWStr)] public string pszName;
            [MarshalAs(UnmanagedType.LPWStr)] public string pszSpec;
        }

        [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
        static extern void SHCreateItemFromParsingName(string path, IntPtr pbc, ref Guid riid, out IShellItem item);

        [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();

        const uint FOS_PICKFOLDERS = 0x20, FOS_FORCEFILESYSTEM = 0x40, FOS_OVERWRITEPROMPT = 0x2, FOS_PATHMUSTEXIST = 0x800;
        const uint SIGDN_FILESYSPATH = 0x80058000;

        static string RunSta(Func<string> f)
        {
            string result = null;
            var th = new Thread(() => { try { result = f(); } catch { result = null; } });
            th.SetApartmentState(ApartmentState.STA);
            th.Start();
            th.Join();
            return result;
        }

        static void StartIn(IFileDialog d, string folder)
        {
            if (string.IsNullOrEmpty(folder)) return;
            try
            {
                var iid = typeof(IShellItem).GUID;
                IShellItem item;
                SHCreateItemFromParsingName(folder, IntPtr.Zero, ref iid, out item);
                d.SetFolder(item);
            }
            catch { }
        }

        public static string PickFolder(string title, string start)
        {
            return RunSta(() =>
            {
                var d = (IFileDialog)new FileOpenDialogRCW();
                d.SetOptions(FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST);
                d.SetTitle(title);
                StartIn(d, start);
                if (d.Show(GetForegroundWindow()) != 0) return null;
                IShellItem item; d.GetResult(out item);
                string path; item.GetDisplayName(SIGDN_FILESYSPATH, out path);
                return path;
            });
        }

        public static string OpenFile(string title, string filterName, string ext, string start)
        {
            return RunSta(() =>
            {
                var d = (IFileDialog)new FileOpenDialogRCW();
                d.SetOptions(FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST | 0x1000);   // FOS_FILEMUSTEXIST
                d.SetTitle(title);
                d.SetFileTypes(1, new[] { new ComDlgFilterSpec { pszName = filterName, pszSpec = "*." + ext } });
                StartIn(d, start);
                if (d.Show(GetForegroundWindow()) != 0) return null;
                IShellItem item; d.GetResult(out item);
                string path; item.GetDisplayName(SIGDN_FILESYSPATH, out path);
                return path;
            });
        }

        public static string SaveFile(string title, string fileName, string filterName, string ext, string start)
        {
            return RunSta(() =>
            {
                var d = (IFileDialog)new FileSaveDialogRCW();
                d.SetOptions(FOS_FORCEFILESYSTEM | FOS_OVERWRITEPROMPT | FOS_PATHMUSTEXIST);
                d.SetTitle(title);
                d.SetFileTypes(1, new[] { new ComDlgFilterSpec { pszName = filterName, pszSpec = "*." + ext } });
                d.SetDefaultExtension(ext);
                d.SetFileName(fileName);
                StartIn(d, start);
                if (d.Show(GetForegroundWindow()) != 0) return null;
                IShellItem item; d.GetResult(out item);
                string path; item.GetDisplayName(SIGDN_FILESYSPATH, out path);
                return path;
            });
        }
    }
}
