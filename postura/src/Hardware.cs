using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace Postura
{
    /// <summary>
    /// Decides whether this PC can run the AI assistant, and with which engine. Poka-yoke: the installer and the app
    /// only offer AI when every requirement passes.
    ///   AMD Ryzen AI 300/400/Max (XDNA 2 NPU) → FastFlowLM on the NPU.
    ///   Intel Core Ultra with an NPU ("Intel AI Boost") → Microsoft Foundry Local (OpenVINO picks NPU or Intel
    ///   graphics) with a small model, because many of these NPUs (e.g. Core Ultra 5 225U) are modest.
    ///   Anything else → Postura without the assistant.
    /// POSTURA_FAKE_HW=amd|intel|none overrides the detection (tests).
    /// </summary>
    static class Hardware
    {
        public const string FlmModel = "qwen3-it:4b";
        public const double FlmModelGb = 2.6;
        // FastFlowLM's MSI is not code-signed, so the exact file is pinned (same pin as the Python apps' safety.py)
        public const string FlmVersion = "1.0.9";
        public const string FlmMsi = "https://github.com/ROCm/FastFlowLM/releases/download/v" + FlmVersion + "/flm-setup.msi";
        public const string FlmMsiSha256 = "a14fda91b55192391bd4422d6e3c2fa13fce09d3c8877a63df94997a306372e0";
        public const string FlmPage = "github.com/FastFlowLM/FastFlowLM";
        public static readonly Version FlmMinDriver = new Version(32, 0, 203, 311);
        public const string FoundryModel = "qwen2.5-1.5b";
        public const double FoundryModelGb = 1.6;
        public const string FoundryWinget = "Microsoft.FoundryLocal";
        const string NpuClass = @"SYSTEM\CurrentControlSet\Control\Class\{f01a9d53-3ff6-48d2-9f97-c8a7004be10c}";

        [StructLayout(LayoutKind.Sequential)]
        struct MEMORYSTATUSEX
        {
            public uint dwLength, dwMemoryLoad;
            public ulong ullTotalPhys, ullAvailPhys, ullTotalPageFile, ullAvailPageFile, ullTotalVirtual, ullAvailVirtual, ullAvailExtendedVirtual;
        }
        [DllImport("kernel32.dll")] static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX m);

        public static int RamGb()
        {
            var m = new MEMORYSTATUSEX { dwLength = (uint)Marshal.SizeOf(typeof(MEMORYSTATUSEX)) };
            return GlobalMemoryStatusEx(ref m) ? (int)Math.Round(m.ullTotalPhys / 1073741824.0) : 0;
        }

        static string Reg(RegistryKey hive, string path, string name)
        {
            try { using (var k = hive.OpenSubKey(path)) return k == null ? null : Convert.ToString(k.GetValue(name)); }
            catch { return null; }
        }

        public static string Cpu { get { return (Reg(Registry.LocalMachine, @"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString") ?? "").Trim(); } }

        public static int Build
        {
            get { int b; return int.TryParse(Reg(Registry.LocalMachine, @"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuild"), out b) ? b : 0; }
        }

        public class Npu { public string Name, Driver, Vendor; }

        public static List<Npu> Npus()
        {
            var list = new List<Npu>();
            try
            {
                using (var root = Registry.LocalMachine.OpenSubKey(NpuClass))
                {
                    if (root == null) return list;
                    foreach (var sub in root.GetSubKeyNames().Where(n => n.All(char.IsDigit)))
                    {
                        try
                        {
                            using (var k = root.OpenSubKey(sub))
                            {
                                string desc = k == null ? null : k.GetValue("DriverDesc") as string;
                                if (string.IsNullOrEmpty(desc) || !Regex.IsMatch(desc, "npu|ipu|neural|ai boost|compute accelerator", RegexOptions.IgnoreCase)) continue;
                                list.Add(new Npu { Name = desc, Driver = k.GetValue("DriverVersion") as string ?? "", Vendor = k.GetValue("ProviderName") as string ?? "" });
                            }
                        }
                        catch { }
                    }
                }
            }
            catch { }
            return list;
        }

        public static double FreeGb(string path)
        {
            try { return new DriveInfo(Path.GetPathRoot(path)).AvailableFreeSpace / 1073741824.0; } catch { return 0; }
        }

        static Version Ver(string s)
        {
            var m = Regex.Match(s ?? "", @"(\d+)\.(\d+)\.(\d+)\.(\d+)");
            return m.Success ? new Version(int.Parse(m.Groups[1].Value), int.Parse(m.Groups[2].Value), int.Parse(m.Groups[3].Value), int.Parse(m.Groups[4].Value)) : new Version(0, 0);
        }

        // ---------------------------------------------------------------- engines on disk

        public static string FlmExe()
        {
            foreach (var p in new[] { Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"flm\flm.exe"), Which("flm.exe") })
                if (!string.IsNullOrEmpty(p) && File.Exists(p)) return p;
            return null;
        }

        public static string FoundryExe()
        {
            string la = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            foreach (var p in new[] { Path.Combine(la, @"Microsoft\WindowsApps\foundry.exe"), Which("foundry.exe") })
                if (!string.IsNullOrEmpty(p) && File.Exists(p)) return p;
            return null;
        }

        public static string WingetExe()
        {
            string p = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Microsoft\WindowsApps\winget.exe");
            return File.Exists(p) ? p : Which("winget.exe");
        }

        /// <summary>Search PATH as it is now in the registry (an install earlier in this run may have changed it).</summary>
        public static string Which(string exe)
        {
            var dirs = new List<string>();
            foreach (var path in new[] {
                Environment.GetEnvironmentVariable("PATH"),
                Environment.GetEnvironmentVariable("PATH", EnvironmentVariableTarget.User),
                Environment.GetEnvironmentVariable("PATH", EnvironmentVariableTarget.Machine) })
                if (!string.IsNullOrEmpty(path)) dirs.AddRange(path.Split(';'));
            foreach (var d in dirs)
            {
                try
                {
                    string f = Path.Combine(Environment.ExpandEnvironmentVariables(d.Trim().Trim('"')), exe);
                    if (File.Exists(f)) return f;
                }
                catch { }
            }
            return null;
        }

        /// <summary>Run a console tool hidden and return its output (empty on failure or timeout).</summary>
        public static string Run(string exe, string args, int timeoutMs = 30000)
        {
            try
            {
                var psi = new ProcessStartInfo(exe, args)
                {
                    UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true,
                    StandardOutputEncoding = System.Text.Encoding.UTF8
                };
                using (var p = Process.Start(psi))
                {
                    var err = p.StandardError.ReadToEndAsync();
                    string o = p.StandardOutput.ReadToEnd();
                    if (!p.WaitForExit(timeoutMs)) { try { p.Kill(); } catch { } }
                    return o + err.Result;
                }
            }
            catch { return ""; }
        }

        // speech, embedding and image models can't chat: never offer them
        static readonly Regex NotChat = new Regex(@"embed|whisper|asr|tts|speech|transcri|rerank|clip|vision-only", RegexOptions.IgnoreCase);

        /// <summary>Chat models FastFlowLM has downloaded ("flm list --filter installed --quiet").</summary>
        public static List<string> FlmModels(string exe)
        {
            var list = new List<string>();
            if (exe == null) return list;
            foreach (Match m in Regex.Matches(Run(exe, "list --filter installed --quiet"), @"^\s*-\s+(\S+)", RegexOptions.Multiline))
                if (!NotChat.IsMatch(m.Groups[1].Value)) list.Add(m.Groups[1].Value);
            return list;
        }

        /// <summary>Chat models in Foundry Local's cache: the alias (first model-like word) of each row of "foundry cache list".</summary>
        public static List<string> FoundryModels(string exe)
        {
            var list = new List<string>();
            if (exe == null) return list;
            foreach (var line in Run(exe, "cache list", 60000).Split('\n'))
            {
                var m = Regex.Match(line, @"(?<![\w.:-])([a-z][a-z0-9]*(?:[.-][a-z0-9]+)+(?::\d+)?)(?![\w.:-])", RegexOptions.IgnoreCase);
                if (!m.Success || Regex.IsMatch(line, @"^\s*(alias|model|name|cache|models cached)\b", RegexOptions.IgnoreCase)) continue;
                string alias = m.Groups[1].Value;
                if (!NotChat.IsMatch(alias) && Regex.IsMatch(alias, @"\d") && !list.Contains(alias)) list.Add(alias);
            }
            return list;
        }

        public static bool FlmHasModel(string exe) { return FlmModels(exe).Contains(FlmModel); }

        public static bool FoundryHasModel(string exe)
        {
            return FoundryModels(exe).Any(m => m.StartsWith(FoundryModel, StringComparison.OrdinalIgnoreCase));
        }

        /// <summary>Installed chat models for an engine (the recommended one first when present).</summary>
        public static List<string> Models(string engine)
        {
            var list = engine == "flm" ? FlmModels(FlmExe()) : engine == "foundry" ? FoundryModels(FoundryExe()) : new List<string>();
            string rec = engine == "flm" ? FlmModel : FoundryModel;
            return list.OrderBy(m => m.StartsWith(rec, StringComparison.OrdinalIgnoreCase) ? 0 : 1).ToList();
        }

        public static string Recommended(string engine) { return engine == "flm" ? FlmModel : engine == "foundry" ? FoundryModel : ""; }

        // ---------------------------------------------------------------- the check

        /// <summary>
        /// Everything the installer shows: requirement rows (ok/bad/info), the engine, whether AI can be enabled,
        /// whether anything has to be downloaded. `deep` also asks the engine CLIs which models are present.
        /// </summary>
        public static Dictionary<string, object> Check(bool deep = true)
        {
            string fake = (Environment.GetEnvironmentVariable("POSTURA_FAKE_HW") ?? "").ToLowerInvariant();
            string cpu = Cpu;
            int build = Build, ram = RamGb();
            var npus = Npus();
            if (fake == "intel") { cpu = "Intel(R) Core(TM) Ultra 5 225U"; npus = new List<Npu> { new Npu { Name = "Intel(R) AI Boost", Driver = "32.0.100.4239", Vendor = "Intel Corporation" } }; }
            if (fake == "none") { cpu = "Intel(R) Core(TM) i5-1235U"; npus = new List<Npu>(); }
            bool x64 = Environment.Is64BitOperatingSystem && !Regex.IsMatch(Environment.GetEnvironmentVariable("PROCESSOR_ARCHITECTURE") ?? "", "ARM", RegexOptions.IgnoreCase);
            bool win11 = build >= 22000;
            bool xdna2 = Regex.IsMatch(cpu, @"Ryzen\s+AI\s+(Max\+?\s+)?(PRO\s+)?(\d\s+)?(HX\s+)?(PRO\s+)?[34]\d\d", RegexOptions.IgnoreCase) ||
                         Regex.IsMatch(cpu, @"Ryzen\s+AI\s+Max", RegexOptions.IgnoreCase);
            bool amdCpu = cpu.IndexOf("AMD", StringComparison.OrdinalIgnoreCase) >= 0;
            bool intelCpu = cpu.IndexOf("Intel", StringComparison.OrdinalIgnoreCase) >= 0;
            var amdNpu = npus.FirstOrDefault(n => amdCpu && (n.Vendor.IndexOf("AMD", StringComparison.OrdinalIgnoreCase) >= 0 || n.Name.IndexOf("Compute Accelerator", StringComparison.OrdinalIgnoreCase) >= 0));
            var intelNpu = npus.FirstOrDefault(n => intelCpu && (n.Vendor.IndexOf("Intel", StringComparison.OrdinalIgnoreCase) >= 0 || n.Name.IndexOf("AI Boost", StringComparison.OrdinalIgnoreCase) >= 0));
            bool arrowLakeOrNewer = Regex.IsMatch(cpu, @"Core\(?T?M?\)?\s+Ultra\s+\d\s+(2|3)\d\d", RegexOptions.IgnoreCase);

            string engine = amdNpu != null && xdna2 ? "flm" : intelNpu != null ? "foundry" : "";
            var rows = new List<Dictionary<string, object>>();
            Action<string, string, bool, string> add = (label, value, ok, note) =>
                rows.Add(new Dictionary<string, object> { { "label", label }, { "value", value }, { "ok", ok }, { "note", note } });

            add("Processor", string.IsNullOrEmpty(cpu) ? "unknown" : cpu, engine != "",
                engine == "flm" ? "AMD Ryzen AI with an XDNA 2 NPU" :
                engine == "foundry" ? "Intel Core Ultra with an NPU" :
                amdNpu != null ? "This first-generation Ryzen AI NPU isn't supported by FastFlowLM" :
                "Needs an AMD Ryzen AI 300/400/Max or an Intel Core Ultra processor with an NPU");
            var npu = engine == "flm" ? amdNpu : engine == "foundry" ? intelNpu : npus.FirstOrDefault();
            add("NPU (AI chip)", npu == null ? "none found" : npu.Name, npu != null, npu == null ? "No neural processing unit on this PC" : "");

            bool driverOk = true;
            if (engine == "flm")
            {
                driverOk = Ver(amdNpu.Driver) >= FlmMinDriver;
                add("NPU driver", amdNpu.Driver, driverOk, driverOk ? "" : "Update the AMD NPU driver to " + FlmMinDriver + " or newer (from AMD or your PC maker), then run setup again");
            }
            else if (engine == "foundry")
                add("NPU driver", intelNpu.Driver, true, arrowLakeOrNewer ? "The model runs on the NPU" : "On this Core Ultra generation the model runs on the Intel graphics instead");
            add("Windows", "Windows " + (win11 ? "11" : "10") + " · build " + build, win11 && x64, win11 ? (x64 ? "" : "Needs a 64-bit (x64) PC") : "Needs Windows 11");
            int needRam = 16;
            add("Memory", ram + " GB", ram >= needRam - 1, ram >= needRam - 1 ? "" : "Needs at least " + needRam + " GB of memory");

            string flm = null, foundry = null, winget = null;
            bool engineInstalled = false, modelReady = false;
            var models = new List<string>();
            double needGb = 0;
            if (engine == "flm")
            {
                flm = FlmExe();
                engineInstalled = flm != null;
                if (deep && engineInstalled) models = Models("flm");
                modelReady = models.Contains(FlmModel);
                needGb = models.Count > 0 ? 0 : FlmModelGb + (engineInstalled ? 0 : 0.05);
                add("FastFlowLM", engineInstalled ? "installed" : "not installed", true, engineInstalled ? "" : "Will be downloaded and installed (Windows asks for permission)");
                add("AI model", models.Count > 0 ? models.Count + " installed" : "Qwen3 4B Instruct", true,
                    models.Count > 0 ? "Pick one below" : "About " + FlmModelGb.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture) + " GB download");
            }
            else if (engine == "foundry")
            {
                foundry = FoundryExe();
                winget = WingetExe();
                engineInstalled = foundry != null;
                if (deep && engineInstalled) models = Models("foundry");
                modelReady = models.Any(x => x.StartsWith(FoundryModel, StringComparison.OrdinalIgnoreCase));
                needGb = models.Count > 0 ? 0 : FoundryModelGb + (engineInstalled ? 0 : 0.6);
                add("Microsoft Foundry Local", engineInstalled ? "installed" : "not installed", engineInstalled || winget != null,
                    engineInstalled ? "" : winget != null ? "Will be installed with winget" : "Needs winget (App Installer from the Microsoft Store) to install it");
                add("AI model", models.Count > 0 ? models.Count + " installed" : "Qwen 2.5 1.5B (small, for modest NPUs)", true,
                    models.Count > 0 ? "Pick one below" : "About " + FoundryModelGb.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture) + " GB download");
            }
            double free = FreeGb(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData));
            if (engine != "") add("Free space", free.ToString("0") + " GB", free >= needGb + 1, free >= needGb + 1 ? "" : "Needs about " + Math.Ceiling(needGb + 1) + " GB free");

            bool supported = engine != "" && rows.All(r => (bool)r["ok"]);
            string reason = supported ? "" : engine == "" ? "This PC has no supported AI processor (NPU)." :
                string.Join(" ", rows.Where(r => !(bool)r["ok"]).Select(r => (string)r["note"]));
            return new Dictionary<string, object> {
                { "engine", engine }, { "engineName", engine == "flm" ? "FastFlowLM on the AMD Ryzen AI NPU" : engine == "foundry" ? "Microsoft Foundry Local on Intel " + (arrowLakeOrNewer ? "NPU" : "graphics") : "" },
                { "supported", supported }, { "reason", reason }, { "rows", rows },
                { "installed", engineInstalled }, { "modelReady", modelReady }, { "downloadGb", Math.Round(needGb, 1) },
                { "model", Recommended(engine) }, { "models", models.ToArray() },
                { "recommendedGb", engine == "flm" ? FlmModelGb : FoundryModelGb }, { "cpu", cpu }, { "ram", ram }
            };
        }
    }
}
