"""Make sample files of many kinds and convert each one to every target Morph offers.

python tests/smoke.py [scratch folder] [filter]
"""
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from core import config  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(config.DATA_DIR, "smoke")
ONLY = sys.argv[2] if len(sys.argv) > 2 else ""
SAMPLES = os.path.join(OUT, "samples")
RESULTS = os.path.join(OUT, "results")
for d in (SAMPLES, RESULTS):
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
ORIGINAL = {k: v for k, v in config.get().items() if k in ("output_dir", "beside")}
config.update({"output_dir": RESULTS, "beside": False})

from core.inbox import inbox  # noqa: E402
from core.jobs import jobs  # noqa: E402


def ff(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def make():
    S = lambda n: os.path.join(SAMPLES, n)  # noqa: E731
    ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25", "-f", "lavfi", "-i", "sine=f=440", "-t", "2",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", S("clip.mp4"))
    ff("-f", "lavfi", "-i", "sine=f=330:d=3", "-c:a", "flac", S("tone.flac"))
    ff("-f", "lavfi", "-i", "sine=f=330:d=3", "-c:a", "libmp3lame", S("tone.mp3"))
    ff("-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10", "-t", "1", S("anim.gif"))
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((20, 20, 280, 180), fill=(120, 100, 255, 255))
    im.save(S("logo.png"))
    Image.new("RGB", (640, 480), (200, 120, 60)).save(S("photo.jpg"), quality=90)
    with open(S("shape.svg"), "w") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="120"><rect x="10" y="10" width="180" '
                'height="100" rx="20" fill="#7c6cff"/></svg>')
    md = "# Report\n\nSome **bold** text and a list:\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    with open(S("notes.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(S("plain.txt"), "w", encoding="utf-8") as f:
        f.write("Hello Žilina\nsecond line\n")
    with open(S("page.html"), "w", encoding="utf-8") as f:
        f.write("<html><body><h1>Title</h1><p>Paragraph <b>bold</b></p></body></html>")
    from core.docs import PANDOC
    subprocess.run([PANDOC, S("notes.md"), "-o", S("letter.docx")], check=True)
    import fitz
    doc = fitz.open()
    for i in range(2):
        doc.new_page().insert_text((72, 72), f"Page {i + 1} hello PDF", fontsize=20)
    doc.save(S("doc.pdf"))
    with open(S("table.csv"), "w", encoding="utf-8") as f:
        f.write("name;age;city\nAna;31;Košice\nBob;25;Brno\n")
    import pandas as pd
    with pd.ExcelWriter(S("book.xlsx")) as w:
        pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}).to_excel(w, sheet_name="One", index=False)
        pd.DataFrame({"c": [3]}).to_excel(w, sheet_name="Two", index=False)
    with open(S("config.json"), "w") as f:
        json.dump({"name": "morph", "version": 1, "tags": ["a", "b"], "nested": {"x": 1}}, f)
    with open(S("people.json"), "w") as f:
        json.dump([{"name": "Ana", "age": 31}, {"name": "Bob", "age": 25}], f)
    with open(S("subs.srt"), "w") as f:
        f.write("1\n00:00:01,000 --> 00:00:02,500\nHello there\n\n2\n00:00:03,000 --> 00:00:04,000\nBye\n")
    import zipfile
    with zipfile.ZipFile(S("bundle.zip"), "w") as z:
        z.writestr("a.txt", "aaa")
        z.writestr("dir/b.txt", "bbb")
    shutil.copy(r"C:\Windows\Fonts\arial.ttf", S("arial.ttf"))


def main():
    make()
    fails, ok = [], 0
    t_all = time.time()
    for name in sorted(os.listdir(SAMPLES)):
        if ONLY and ONLY not in name:
            continue
        e = inbox.add(os.path.join(SAMPLES, name))
        tids = [t["id"] for t in e["targets"]]
        print(f"\n{name} [{e['fid']}] facts={e['facts']} picks={e['picks']}\n  -> {len(tids)} targets: {' '.join(tids)}",
              flush=True)
        if e.get("error"):
            print("  ERROR", e["error"])
        inbox.thumbnail(e["id"])
        for tid in tids:
            t0 = time.time()
            job = jobs.submit(e["id"], tid, {"quality": "small"})
            while job["status"] in ("queued", "running"):
                time.sleep(0.05)
            dt = time.time() - t0
            if job["status"] == "done" and job["out_size"]:
                ok += 1
                print(f"   ok  {tid:8} {job['out_size_h']:>9} {dt:5.1f}s  {job['out_name']}", flush=True)
            else:
                fails.append((name, tid, job["error"]))
                print(f"   FAIL {tid:8} {dt:5.1f}s  {job['error']}", flush=True)
    print(f"\n{ok} ok, {len(fails)} failed in {time.time() - t_all:.0f}s")
    for f in fails:
        print("  ", f)


if __name__ == "__main__":
    try:
        main()
    finally:
        config.update(ORIGINAL)
