using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text.RegularExpressions;
using System.Threading;

namespace Postura
{
    /// <summary>
    /// The installer's background job: install Postura, then (only if the hardware check passed) the AI engine and
    /// its model. Steps report state/progress for setup.html. An AI failure never undoes Postura itself: the app
    /// then simply runs without the assistant. POSTURA_SETUP_TEST simulates the downloads.
    /// </summary>
    static class AiInstall
    {
        public class Step { public string Key, Label, State = "active", Detail = ""; public int Pct = -1; }

        static readonly object Lock = new object();
        static readonly List<Step> steps = new List<Step>();
        public static bool Running, Done;
        public static string Error = "", AiError = "";
        static bool Test { get { return Setup.TestDir != null; } }

        public static Dictionary<string, object> Progress()
        {
            lock (Lock)
            {
                var list = new List<object>();
                foreach (var s in steps)
                    list.Add(new Dictionary<string, object> { { "key", s.Key }, { "label", s.Label }, { "state", s.State }, { "detail", s.Detail }, { "pct", s.Pct } });
                return new Dictionary<string, object> { { "running", Running }, { "done", Done }, { "error", Error }, { "aiError", AiError }, { "steps", list } };
            }
        }

        static Step Add(string key, string label)
        {
            var s = new Step { Key = key, Label = label };
            lock (Lock) steps.Add(s);
            return s;
        }

        /// <summary>--ai-no-engine (IT): set up the assistant only with an AI engine that is already installed - no
        /// engine download and no administrator prompt.</summary>
        public static bool NoEngineInstall;

        public static void Start(bool desktop, bool startMenu, bool autostart, bool ai, string model = null)
        {
            lock (Lock)
            {
                if (Running) return;
                steps.Clear(); Running = true; Done = false; Error = ""; AiError = "";
            }
            new Thread(() => Run(desktop, startMenu, autostart, ai, model)) { IsBackground = true }.Start();
        }

        static void Run(bool desktop, bool startMenu, bool autostart, bool ai, string model)
        {
            try
            {
                // poka-yoke: the server checks the hardware again; the page's checkbox alone is not trusted
                Dictionary<string, object> hw = ai ? Hardware.Check() : null;
                if (ai && !(bool)hw["supported"]) { ai = false; AiError = "The AI assistant isn't supported on this PC: " + hw["reason"]; }
                string engine = ai ? (string)hw["engine"] : "";
                // poka-yoke: only a model this engine really has, or the recommended one (which is then downloaded)
                var installed = ai ? new List<string>((string[])hw["models"]) : new List<string>();
                if (string.IsNullOrEmpty(model) || !installed.Contains(model)) model = Hardware.Recommended(engine);

                var s = Add("app", "Installing Postura");
                Setup.Install(desktop, startMenu, autostart, "", "");   // AI settings are written only once the engine works
                s.State = "done"; s.Detail = Setup.InstallDir;

                if (engine != "" && NoEngineInstall && !(bool)hw["installed"])
                    throw new AiFailed("The AI engine isn't installed, and --ai-no-engine skips installing it.");
                bool have = installed.Contains(model);
                double gb = engine == "flm" ? Hardware.FlmModelGb + Hardware.FlmModel2Gb : Hardware.FoundryModelGb;
                if (engine != "" && !have && Hardware.FreeGb(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)) < gb + 1)
                    throw new AiFailed("Not enough free disk space to download the AI model (needs about " + Math.Ceiling(gb + 1) + " GB).");
                if (engine == "flm") InstallFlm(hw, have);
                else if (engine == "foundry") InstallFoundry(hw, have);
                if (engine != "") Setup.SaveAi(engine, model);
            }
            catch (AiFailed e)
            {
                AiError = e.Message;
                lock (Lock) foreach (var st in steps) if (st.State == "active") { st.State = "failed"; st.Detail = e.Message; }
            }
            catch (Exception e)
            {
                Error = e.Message;
                Program.Log("setup: " + e);
                lock (Lock) foreach (var st in steps) if (st.State == "active") st.State = "failed";
            }
            finally { Running = false; Done = Error == ""; }
        }

        class AiFailed : Exception { public AiFailed(string m) : base(m) { } }

        // ---------------------------------------------------------------- AMD: FastFlowLM

        static void InstallFlm(Dictionary<string, object> hw, bool haveModel)
        {
            if (!(bool)hw["installed"] || Test)
            {
                var s = Add("engine", "Installing FastFlowLM " + Hardware.FlmVersion + " (runs the AI on the NPU)");
                // a private folder for the download, removed afterwards; the file must match the pinned SHA-256
                string dir = Path.Combine(Path.GetTempPath(), "postura-dl-" + Guid.NewGuid().ToString("N").Substring(0, 8));
                Directory.CreateDirectory(dir);
                try
                {
                    string msi = Path.Combine(dir, "flm-setup.msi");
                    if (Download(Hardware.FlmMsi, msi, s))
                    {
                        s.Pct = -1; s.Detail = "Checking the download…";
                        if (Sha256(msi) != Hardware.FlmMsiSha256)
                            throw new AiFailed("The downloaded FastFlowLM installer doesn't match the expected file, so it was not run. Please try again later.");
                        s.Detail = "Windows will ask for permission — please click Yes.";
                        int rc = RunVisible("msiexec.exe", "/i \"" + msi + "\" /passive /norestart");
                        if (rc != 0 && rc != 3010) throw new AiFailed("FastFlowLM's installer stopped (code " + rc + "). You can install it later from " + Hardware.FlmPage + " and run Postura setup again.");
                    }
                }
                finally { try { Directory.Delete(dir, true); } catch { } }
                s.State = "done"; s.Detail = Test ? "Test mode" : "Installed";
            }
            if (haveModel) { var u = Add("model", "Using the AI model you already have"); u.State = "done"; return; }
            // the default model and the faster one to switch to in Settings
            var models = new[] { Tuple.Create(Hardware.FlmModel, Hardware.FlmModelGb), Tuple.Create(Hardware.FlmModel2, Hardware.FlmModel2Gb) };
            foreach (var mm in models)
            {
                var m = Add(mm.Item1 == Hardware.FlmModel ? "model" : "model2", "Downloading the AI model " + mm.Item1 + " (about " + mm.Item2.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture) + " GB)");
                if (Test) { Simulate(m); m.State = "done"; m.Detail = "Test mode"; continue; }
                string exe = Hardware.FlmExe();
                if (exe == null) throw new AiFailed("FastFlowLM was not found after installing it. Restart Windows and run Postura setup again.");
                if (Hardware.FlmModels(exe).Contains(mm.Item1)) { m.State = "done"; m.Detail = "Already downloaded"; continue; }
                RunWithProgress(exe, "pull " + mm.Item1, m, mm.Item2,
                    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), @"flm\models"));
                if (!Hardware.FlmModels(exe).Contains(mm.Item1)) throw new AiFailed("The model did not finish downloading. Run Postura setup again to retry.");
                m.State = "done"; m.Pct = 100; m.Detail = "Ready on the NPU";
            }
        }

        // ---------------------------------------------------------------- Intel: Foundry Local

        static void InstallFoundry(Dictionary<string, object> hw, bool haveModel)
        {
            if (!(bool)hw["installed"] || Test)
            {
                var s = Add("engine", "Installing Microsoft Foundry Local (runs the AI on Intel NPU / graphics)");
                if (Test) { Simulate(s); }
                else
                {
                    string winget = Hardware.WingetExe();
                    if (winget == null) throw new AiFailed("winget (App Installer) is missing, so Foundry Local can't be installed.");
                    s.Detail = "winget install " + Hardware.FoundryWinget;
                    string o = Hardware.Run(winget, "install --id " + Hardware.FoundryWinget + " -e --silent --accept-package-agreements --accept-source-agreements --disable-interactivity", 15 * 60000);
                    if (Hardware.FoundryExe() == null)
                        throw new AiFailed("Foundry Local could not be installed" + (o.Length > 0 ? ": " + LastLine(o) : "") + ". Your IT department may need to allow it.");
                }
                s.State = "done"; s.Detail = Test ? "Test mode" : "Installed";
            }
            if (haveModel) { var u = Add("model", "Using the AI model you already have"); u.State = "done"; return; }
            var m = Add("model", "Downloading the AI model (Qwen 2.5 1.5B, about " + Hardware.FoundryModelGb + " GB)");
            if (Test) { Simulate(m); m.State = "done"; m.Detail = "Test mode"; return; }
            string exe = Hardware.FoundryExe();
            m.Detail = "Preparing Intel acceleration (first run downloads OpenVINO)…";
            Hardware.Run(exe, "model list", 20 * 60000);     // first run downloads the execution providers
            RunWithProgress(exe, "model download " + Hardware.FoundryModel, m, Hardware.FoundryModelGb, null);
            if (!Hardware.FoundryHasModel(exe)) throw new AiFailed("The model did not finish downloading. Run Postura setup again to retry.");
            m.State = "done"; m.Pct = 100; m.Detail = "Ready";
        }

        // ---------------------------------------------------------------- helpers

        static string LastLine(string o)
        {
            var lines = o.Trim().Split('\n');
            return lines[lines.Length - 1].Trim();
        }

        static string Sha256(string file)
        {
            using (var sha = System.Security.Cryptography.SHA256.Create())
            using (var f = File.OpenRead(file))
                return BitConverter.ToString(sha.ComputeHash(f)).Replace("-", "").ToLowerInvariant();
        }

        static int RunVisible(string exe, string args)
        {
            using (var p = Process.Start(new ProcessStartInfo(exe, args) { UseShellExecute = true }))
            {
                p.WaitForExit();
                return p.ExitCode;
            }
        }

        /// <summary>Run a downloader CLI; progress from "NN%" in its output, or from the folder growing.</summary>
        static void RunWithProgress(string exe, string args, Step s, double expectGb, string folder)
        {
            var psi = new ProcessStartInfo(exe, args) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            long before = folder != null ? DirSize(folder) : 0;
            using (var p = Process.Start(psi))
            {
                DataReceivedEventHandler h = (o, e) =>
                {
                    if (e.Data == null) return;
                    var mm = Regex.Match(e.Data, @"(\d{1,3}(?:\.\d+)?)\s*%");
                    if (mm.Success) s.Pct = Math.Min(99, (int)double.Parse(mm.Groups[1].Value, System.Globalization.CultureInfo.InvariantCulture));
                };
                p.OutputDataReceived += h; p.ErrorDataReceived += h;
                p.BeginOutputReadLine(); p.BeginErrorReadLine();
                var started = DateTime.Now;
                while (!p.WaitForExit(1000))
                {
                    if ((DateTime.Now - started).TotalHours > 3)   // a stuck download must not keep setup open for ever
                    {
                        try { p.Kill(); } catch { }
                        throw new AiFailed("The model download took more than 3 hours and was stopped. Run Postura setup again to retry.");
                    }
                    if (folder != null)
                    {
                        double got = (DirSize(folder) - before) / 1073741824.0;
                        s.Pct = Math.Min(99, (int)(got * 100 / expectGb));
                        s.Detail = got.ToString("0.00") + " of about " + expectGb + " GB";
                    }
                    else if (s.Pct >= 0) s.Detail = s.Pct + "%";
                }
            }
        }

        static long DirSize(string d)
        {
            try
            {
                if (!Directory.Exists(d)) return 0;
                long n = 0;
                foreach (var f in new DirectoryInfo(d).EnumerateFiles("*", SearchOption.AllDirectories)) n += f.Length;
                return n;
            }
            catch { return 0; }
        }

        static void Simulate(Step s)
        {
            for (int i = 0; i <= 20; i++) { s.Pct = i * 5; s.Detail = "Test mode: simulated download " + (i * 5) + "%"; Thread.Sleep(80); }
        }

        /// <summary>Streams a file to disk with progress. Returns false in test mode (nothing downloaded).</summary>
        static bool Download(string url, string dest, Step s)
        {
            if (Test) { Simulate(s); return false; }
            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            try
            {
                var req = (HttpWebRequest)WebRequest.Create(url);
                req.UserAgent = "Postura-Setup/" + Program.Version;
                req.Timeout = 60000;
                using (var r = req.GetResponse())
                using (var input = r.GetResponseStream())
                using (var f = File.Create(dest + ".part"))
                {
                    long total = r.ContentLength, got = 0;
                    var buf = new byte[1 << 16];
                    int n;
                    while ((n = input.Read(buf, 0, buf.Length)) > 0)
                    {
                        f.Write(buf, 0, n);
                        got += n;
                        s.Pct = total > 0 ? (int)(got * 100 / total) : -1;
                        s.Detail = (got / 1048576) + (total > 0 ? " of " + (total / 1048576) + " MB" : " MB");
                    }
                }
                if (File.Exists(dest)) File.Delete(dest);
                File.Move(dest + ".part", dest);
                return true;
            }
            catch (WebException e)
            {
                throw new AiFailed("Couldn't download " + Path.GetFileName(dest) + " (" + e.Message + "). Check the internet connection and run setup again.");
            }
        }
    }
}
