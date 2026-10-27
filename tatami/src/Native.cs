using System;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace Tatami
{
    [StructLayout(LayoutKind.Sequential)]
    struct IoStatusBlock { public IntPtr Status; public IntPtr Information; }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct ShFileOpStruct
    {
        public IntPtr hwnd; public uint wFunc;
        [MarshalAs(UnmanagedType.LPWStr)] public string pFrom;
        [MarshalAs(UnmanagedType.LPWStr)] public string pTo;
        public ushort fFlags; public int fAnyOperationsAborted; public IntPtr hNameMappings;
        [MarshalAs(UnmanagedType.LPWStr)] public string lpszProgressTitle;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct ShellExecuteInfo
    {
        public int cbSize; public uint fMask; public IntPtr hwnd;
        [MarshalAs(UnmanagedType.LPWStr)] public string lpVerb;
        [MarshalAs(UnmanagedType.LPWStr)] public string lpFile;
        [MarshalAs(UnmanagedType.LPWStr)] public string lpParameters;
        [MarshalAs(UnmanagedType.LPWStr)] public string lpDirectory;
        public int nShow; public IntPtr hInstApp; public IntPtr lpIDList;
        [MarshalAs(UnmanagedType.LPWStr)] public string lpClass;
        public IntPtr hkeyClass; public uint dwHotKey; public IntPtr hIcon; public IntPtr hProcess;
    }

    static unsafe class Native
    {
        public const uint FILE_LIST_DIRECTORY = 0x1, SYNCHRONIZE = 0x100000, GENERIC_READ = 0x80000000;
        public const uint SHARE_ALL = 7, OPEN_EXISTING = 3, FLAG_BACKUP_SEMANTICS = 0x02000000;
        public const int FileIdFullDirectoryInformation = 38;
        public const uint STATUS_NO_MORE_FILES = 0x80000006;

        public const uint ATTR_READONLY = 0x1, ATTR_HIDDEN = 0x2, ATTR_SYSTEM = 0x4, ATTR_DIRECTORY = 0x10,
            ATTR_ARCHIVE = 0x20, ATTR_SPARSE = 0x200, ATTR_REPARSE = 0x400, ATTR_COMPRESSED = 0x800,
            ATTR_OFFLINE = 0x1000, ATTR_ENCRYPTED = 0x4000, ATTR_PINNED = 0x80000, ATTR_UNPINNED = 0x100000,
            ATTR_RECALL_ON_OPEN = 0x40000, ATTR_RECALL_ON_DATA = 0x400000;

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr sa, uint disp, uint flags, IntPtr tmpl);

        [DllImport("ntdll.dll")]
        public static extern uint NtQueryDirectoryFile(SafeFileHandle h, IntPtr ev, IntPtr apc, IntPtr apcCtx,
            out IoStatusBlock iosb, byte* buf, uint len, int infoClass, byte returnSingle, IntPtr fileName, byte restart);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern bool GetDiskFreeSpaceExW(string dir, out ulong freeToCaller, out ulong total, out ulong totalFree);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern bool GetVolumeInformationW(string root, StringBuilder label, int labelLen, out uint serial,
            out uint maxComp, out uint fsFlags, StringBuilder fs, int fsLen);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        public static extern uint GetDriveTypeW(string root);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern bool GetDiskFreeSpaceW(string root, out uint sectorsPerCluster, out uint bytesPerSector,
            out uint freeClusters, out uint totalClusters);

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        public static extern int SHFileOperationW(ref ShFileOpStruct op);

        [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern bool ShellExecuteExW(ref ShellExecuteInfo info);

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        public static extern int SHQueryRecycleBinW(string root, ref ShQueryRbInfo info);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern uint GetFileAttributesW(string name);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern bool RemoveDirectoryW(string name);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern bool DeleteFileW(string name);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern bool GetVolumeNameForVolumeMountPointW(string mountPoint, StringBuilder volumeName, int len);

        [DllImport("kernel32.dll")]
        public static extern bool AttachConsole(int pid);

        [DllImport("user32.dll")]
        public static extern bool SetForegroundWindow(IntPtr hwnd);

        [DllImport("user32.dll")]
        public static extern bool ShowWindow(IntPtr hwnd, int cmd);

        [DllImport("user32.dll")]
        public static extern bool IsIconic(IntPtr hwnd);

        [DllImport("shell32.dll")]
        public static extern bool IsUserAnAdmin();

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern uint WaitForSingleObject(IntPtr h, uint ms);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool GetExitCodeProcess(IntPtr h, out uint code);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool CloseHandle(IntPtr h);

        [DllImport("advapi32.dll", SetLastError = true)]
        static extern bool OpenProcessToken(IntPtr process, uint access, out IntPtr token);

        [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        static extern bool LookupPrivilegeValueW(string system, string name, out long luid);

        [DllImport("advapi32.dll", SetLastError = true)]
        static extern bool AdjustTokenPrivileges(IntPtr token, bool disableAll, ref TokenPrivileges state, int len, IntPtr prev, IntPtr retLen);

        [DllImport("kernel32.dll")]
        static extern IntPtr GetCurrentProcess();

        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        struct TokenPrivileges { public int Count; public long Luid; public int Attributes; }

        /// <summary>Enable a privilege the (elevated) token holds, e.g. SeBackupPrivilege to read every folder.</summary>
        public static bool EnablePrivilege(string name)
        {
            IntPtr tok;
            if (!OpenProcessToken(GetCurrentProcess(), 0x20 | 0x8, out tok)) return false;   // ADJUST_PRIVILEGES | QUERY
            try
            {
                long luid;
                if (!LookupPrivilegeValueW(null, name, out luid)) return false;
                var tp = new TokenPrivileges { Count = 1, Luid = luid, Attributes = 2 };     // SE_PRIVILEGE_ENABLED
                return AdjustTokenPrivileges(tok, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero) && Marshal.GetLastWin32Error() == 0;
            }
            finally { CloseHandle(tok); }
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    struct ShQueryRbInfo { public int cbSize; public long i64Size; public long i64NumItems; }
}
