"""Builds Washi.exe (launcher\\Washi.cs) with the C# compiler that comes with Windows.

    python make_launcher.py                  # Washi.exe in this folder (to run Washi from source)
    python make_launcher.py --out <file>     # somewhere else (the installer build uses this)

The source-folder copy also gets pythonw.txt, pointing at the Python that runs this script.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSC = [os.path.expandvars(r"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
       os.path.expandvars(r"%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe")]
CREATE_NO_WINDOW = 0x08000000


def build(out):
    csc = next((c for c in CSC if os.path.exists(c)), None)
    if not csc:
        raise RuntimeError("The .NET Framework 4 C# compiler (csc.exe) was not found")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    r = subprocess.run([csc, "/nologo", "/target:winexe", "/optimize+", "/platform:anycpu",
                        f"/win32icon:{os.path.join(HERE, 'washi.ico')}", f"/out:{out}",
                        os.path.join(HERE, "launcher", "Washi.cs")],
                       capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError("csc failed:\n" + (r.stdout or "") + (r.stderr or ""))
    return out


if __name__ == "__main__":
    if "--out" in sys.argv:
        print(build(sys.argv[sys.argv.index("--out") + 1]))
    else:
        exe = build(os.path.join(HERE, "Washi.exe"))
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(pyw):
            with open(os.path.join(HERE, "pythonw.txt"), "w", encoding="utf-8") as f:
                f.write(pyw)
        print(exe)
