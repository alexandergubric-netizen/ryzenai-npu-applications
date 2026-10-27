"""Can this PC run Sensei's local AI? FastFlowLM needs Windows 11, an x64 AMD Ryzen AI 300/400/Max processor
(XDNA 2 NPU) and a recent NPU driver. Everything is read from the registry, so the check is instant.

SENSEI_NO_AI_HW=1 pretends the PC is unsupported (to test how the app looks elsewhere)."""
import os
import re
import shutil
import winreg

NPU_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{f01a9d53-3ff6-48d2-9f97-c8a7004be10c}"
FLM_MIN_DRIVER = (32, 0, 203, 311)
FLM_URL = "https://github.com/FastFlowLM/FastFlowLM"
_cache = {}


def _reg(hive, path, name, default=None):
    try:
        with winreg.OpenKey(hive, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


def _npus():
    out = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, NPU_CLASS)
    except OSError:
        return out
    with root:
        for i in range(winreg.QueryInfoKey(root)[0]):
            name = winreg.EnumKey(root, i)
            if name.isdigit():
                sub = NPU_CLASS + "\\" + name
                desc = _reg(winreg.HKEY_LOCAL_MACHINE, sub, "DriverDesc")
                if desc:
                    out.append({"name": desc, "driver": _reg(winreg.HKEY_LOCAL_MACHINE, sub, "DriverVersion", ""),
                                "vendor": _reg(winreg.HKEY_LOCAL_MACHINE, sub, "ProviderName", "")})
    return out


def _ver(text):
    return tuple(int(x) for x in re.findall(r"\d+", text or "")[:4])


def flm_exe():
    for p in (shutil.which("flm"), os.path.expandvars(r"%ProgramFiles%\flm\flm.exe")):
        if p and os.path.exists(p):
            return p
    return None


def check(refresh=False):
    """{supported, reason, cpu, npu, driver, flm} - supported means the hardware can run FastFlowLM."""
    if _cache and not refresh:
        return dict(_cache)
    cpu = (_reg(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                "ProcessorNameString", "") or "").strip()
    build = int(_reg(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuild", "0") or 0)
    arch = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64")
    npus = [d for d in _npus() if re.search(r"npu|ipu|neural", d["name"], re.I)]
    amd = next((d for d in npus if "amd" in (d["vendor"] or "").lower() or "amd" in cpu.lower()), None)
    xdna2 = bool(re.search(r"Ryzen\s+AI\s+(Max\+?\s+)?(PRO\s+)?(\d\s+)?(HX\s+)?(PRO\s+)?[34]\d\d", cpu, re.I)) or \
        bool(re.search(r"Ryzen\s+AI\s+Max", cpu, re.I))
    driver = amd["driver"] if amd else ""
    reason = ""
    if os.environ.get("SENSEI_NO_AI_HW"):
        reason = "Turned off for this test run (SENSEI_NO_AI_HW)"
    elif arch.upper() != "AMD64":
        reason = "Local AI needs a 64-bit AMD processor"
    elif build < 22000:
        reason = "Local AI needs Windows 11"
    elif not (amd and xdna2):
        reason = "Local AI needs an AMD Ryzen AI 300/400 or Ryzen AI Max processor with an NPU"
    elif _ver(driver) < FLM_MIN_DRIVER:
        reason = "Update the AMD NPU driver to 32.0.203.311 or newer to use local AI"
    flm = flm_exe()
    npu = amd["name"] if amd else ""
    if npu and re.search(r"compute accelerator|^npu$|ipu", npu, re.I):   # the driver's generic name
        npu = "Ryzen AI NPU"
    _cache.clear()
    _cache.update({"supported": not reason, "reason": reason, "cpu": cpu, "npu": npu,
                   "driver": driver, "flm": bool(flm), "flm_url": FLM_URL})
    return dict(_cache)
