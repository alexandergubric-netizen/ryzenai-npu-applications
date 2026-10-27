"""Throws many 'do something' requests at the pipeline and reports slow, empty or broken answers.
Usage: python tests/stress.py [--quick]   (prints a summary table; --quick = first 20 only)"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import assistant  # noqa: E402
from core.llm import npu  # noqa: E402
from core.shell import shell  # noqa: E402

REQUESTS = [
    "create a folder called Projects on my desktop", "turn on dark mode", "open notepad", "install vlc",
    "empty the recycle bin", "compress my documents folder into a zip on the desktop", "mute the volume",
    "set the volume to 50%", "turn off wifi", "turn on wifi", "shut down the pc at 11 pm", "restart in 10 minutes",
    "take a screenshot", "set screen brightness to 40%", "kill chrome", "close all edge windows", "open task manager",
    "show hidden files in explorer", "move all screenshots from pictures to a folder called Screenshots",
    "delete files in downloads older than 60 days", "find duplicate photos in pictures", "lock my pc",
    "download https://example.com/file.zip to my downloads", "convert all png files in downloads to jpg",
    "resize image photo.jpg to 50%", "count the words in notes.txt", "backup my documents to D:\\Backup",
    "sort my downloads into folders by type", "change my wallpaper to C:\\pics\\sky.jpg", "turn bluetooth off",
    "list the files in downloads sorted by size", "show the 5 newest files on my desktop", "rename report.docx to final.docx",
    "copy everything from my desktop to D:\\desktop-copy", "open the downloads folder", "open google.com",
    "how much space does my steam folder use", "uninstall spotify", "update windows", "check my disk for errors",
    "find all mp4 files bigger than 1 GB", "show cpu temperature", "stop windows search service", "clear my temp files",
    "show my wifi password", "start a 5 minute timer", "speak hello world", "make a new text file called todo.txt",
    "show the content of todo.txt", "add 'buy milk' to todo.txt", "find which file is using the most space on C",
    "list usb devices", "eject the usb drive E", "set my pc to never sleep", "show my battery health",
    "enable remote desktop", "show the date and time", "change the time zone to Pacific", "copy my ip to clipboard",
    "how many files are in my documents folder",
]

if __name__ == "__main__":
    quick = "--quick" in sys.argv
    shell.start()
    npu.ensure()
    while npu.state == "starting":
        time.sleep(0.5)
    print("NPU:", npu.state, npu.detail)
    rows = []
    for q in REQUESTS[:20] if quick else REQUESTS:
        t = time.time()
        ans, first, statuses = None, None, []
        try:
            for ev in assistant.ask(q):
                if ev["type"] == "token" and first is None:
                    first = time.time() - t
                elif ev["type"] == "status":
                    statuses.append(ev["text"])
                elif ev["type"] == "answer":
                    ans = ev
        except Exception as e:  # noqa: BLE001
            ans = {"code": "", "text": f"EXCEPTION {e}", "check": None, "repairs": 0, "model": "?"}
        took = time.time() - t
        c = ans["check"] or {}
        probs = assistant.problems_of(c) if c else []
        verdict = "EMPTY" if not ans["code"] else ("PROBLEM" if probs else "ok")
        rows.append({"q": q, "s": round(took, 1), "first": first and round(first, 1), "verdict": verdict,
                     "src": ans.get("model"), "repairs": ans["repairs"], "code": ans["code"], "probs": probs,
                     "text": ans["text"][:160]})
        print(f"{verdict:7} {took:5.1f}s first={first and round(first, 1)} {ans.get('model'):8} rep={ans['repairs']} | {q}")
        print("        ", (ans["code"] or ans["text"]).replace("\n", " ⏎ ")[:220])
        for p in probs:
            print("         !", p[:200])
    with open(os.path.join(os.path.dirname(__file__), "stress_result.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    n = len(rows)
    print(f"\n{n} requests: ok {sum(r['verdict'] == 'ok' for r in rows)}, problem {sum(r['verdict'] == 'PROBLEM' for r in rows)}, "
          f"empty {sum(r['verdict'] == 'EMPTY' for r in rows)}, avg {sum(r['s'] for r in rows) / n:.1f}s, "
          f"max {max(r['s'] for r in rows):.1f}s, instant {sum(r['src'] == 'library' for r in rows)}")
