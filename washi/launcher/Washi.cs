// Washi.exe - the native front door of Washi, so Windows can list it in "Open with" and Default apps.
// It starts Washi's Python app with the files it was given and exits. Built by make_launcher.py with the C# compiler
// that ships with Windows (.NET Framework 4).
//
// Where it looks:
//   installed:    <here>\runtime\pythonw.exe  <here>\app\app.py
//   from source:  <here>\app.py  with pythonw.exe from pythonw.txt (next to this exe), the Python registry keys
//                 or PATH
//
// Copyright (c) 2026 Alexander Gubric. MIT License.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32;

[assembly: AssemblyTitle("Washi")]
[assembly: AssemblyDescription("Washi - PDF editor with a local AI assistant")]
[assembly: AssemblyProduct("Washi")]
[assembly: AssemblyCompany("Alexander Gubric")]
[assembly: AssemblyCopyright("Copyright (c) 2026 Alexander Gubric. MIT License.")]
[assembly: AssemblyVersion("1.0.3.0")]
[assembly: AssemblyFileVersion("1.0.3.0")]

static class Launcher
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);

    [DllImport("user32.dll")]
    static extern bool AllowSetForegroundWindow(int processId);

    [STAThread]
    static int Main(string[] args)
    {
        string here = AppDomain.CurrentDomain.BaseDirectory;
        string pythonw = null, app = null;
        if (File.Exists(Path.Combine(here, @"runtime\pythonw.exe")) && File.Exists(Path.Combine(here, @"app\app.py")))
        {
            pythonw = Path.Combine(here, @"runtime\pythonw.exe");
            app = Path.Combine(here, @"app\app.py");
        }
        else if (File.Exists(Path.Combine(here, "app.py")))
        {
            app = Path.Combine(here, "app.py");
            pythonw = FindPythonw(here);
        }
        if (app == null)
        {
            MessageBoxW(IntPtr.Zero, "Washi's files are missing next to Washi.exe. Please reinstall Washi.", "Washi", 0x10);
            return 2;
        }
        if (pythonw == null)
        {
            MessageBoxW(IntPtr.Zero, "Washi needs Python 3.12 (pythonw.exe) to run from its source folder. Install Python, " +
                        "or install Washi with Washi-Setup.exe, which brings its own.", "Washi", 0x10);
            return 3;
        }
        var cmd = new StringBuilder(Quote(app));
        foreach (string a in args)
            cmd.Append(' ').Append(Quote(Path.GetFullPath(a.Trim('"'))));
        var psi = new ProcessStartInfo(pythonw, cmd.ToString());
        psi.UseShellExecute = false;
        psi.WorkingDirectory = Path.GetDirectoryName(app);
        try
        {
            AllowSetForegroundWindow(-1);   // let Washi bring its window to the front
            Process.Start(psi);
            return 0;
        }
        catch (Exception e)
        {
            MessageBoxW(IntPtr.Zero, "Washi could not start: " + e.Message, "Washi", 0x10);
            return 4;
        }
    }

    // Windows command-line quoting (CommandLineToArgvW rules)
    static string Quote(string s)
    {
        var sb = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in s)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { sb.Append('\\', slashes * 2 + 1); sb.Append('"'); slashes = 0; continue; }
            sb.Append('\\', slashes); slashes = 0; sb.Append(c);
        }
        sb.Append('\\', slashes * 2);
        return sb.Append('"').ToString();
    }

    static string FindPythonw(string here)
    {
        // 1. an explicit choice written by make_launcher.py
        string pin = Path.Combine(here, "pythonw.txt");
        if (File.Exists(pin))
        {
            string p = File.ReadAllText(pin).Trim();
            if (File.Exists(p)) return p;
        }
        // 2. Python's own registry entries, newest 3.x first
        var found = new List<KeyValuePair<Version, string>>();
        foreach (RegistryKey hive in new[] { Registry.CurrentUser, Registry.LocalMachine })
        {
            using (RegistryKey core = hive.OpenSubKey(@"Software\Python\PythonCore"))
            {
                if (core == null) continue;
                foreach (string tag in core.GetSubKeyNames())
                {
                    using (RegistryKey ip = core.OpenSubKey(tag + @"\InstallPath"))
                    {
                        if (ip == null) continue;
                        string w = ip.GetValue("WindowedExecutablePath") as string;
                        if (string.IsNullOrEmpty(w))
                        {
                            string root = ip.GetValue("") as string;
                            if (!string.IsNullOrEmpty(root)) w = Path.Combine(root, "pythonw.exe");
                        }
                        Version v;
                        if (!string.IsNullOrEmpty(w) && File.Exists(w) && Version.TryParse(tag.Split('-')[0], out v) && v.Major == 3)
                            found.Add(new KeyValuePair<Version, string>(v, w));
                    }
                }
            }
        }
        found.Sort((a, b) => b.Key.CompareTo(a.Key));
        if (found.Count > 0) return found[0].Value;
        // 3. PATH
        foreach (string dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
        {
            try
            {
                string w = Path.Combine(dir.Trim(), "pythonw.exe");
                if (dir.Trim().Length > 0 && File.Exists(w) && !w.ToLower().Contains("windowsapps")) return w;
            }
            catch (ArgumentException) { }
        }
        return null;
    }
}
