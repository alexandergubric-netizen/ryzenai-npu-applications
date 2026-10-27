"""Shows which library template (if any) answers each request instantly, with the filled-in command.
Usage: python tests/match.py ["request" ...]   (no arguments = the built-in list)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.recipes import library  # noqa: E402

QUERIES = sys.argv[1:] or [
    "create a folder called Projects on my desktop", "turn on dark mode", "open notepad", "install vlc",
    "empty the recycle bin", "compress my documents folder into a zip on the desktop", "mute the volume",
    "set the volume to 50%", "turn off wifi", "turn on wifi", "shut down the pc at 11 pm", "restart in 10 minutes",
    "take a screenshot", "set screen brightness to 40%", "kill chrome", "close all edge windows", "open task manager",
    "show hidden files in explorer", "delete files in downloads older than 60 days", "find duplicate photos in pictures",
    "lock my pc", "download https://example.com/file.zip to my downloads", "convert all png files in downloads to jpg",
    "resize image photo.jpg to 50%", "count the words in notes.txt", "backup my documents to D:\\Backup",
    "sort my downloads into folders by type", "change my wallpaper to C:\\pics\\sky.jpg", "turn bluetooth off",
    "list the files in downloads sorted by size", "show the 5 newest files on my desktop", "rename report.docx to final.docx",
    "copy everything from my desktop to D:\\desktop-copy", "open the downloads folder", "open google.com",
    "uninstall spotify", "update windows", "check my disk for errors", "find all mp4 files bigger than 1 GB",
    "show cpu temperature", "stop windows search service", "clear my temp files", "show my wifi password",
    "start a 5 minute timer", "say hello world", "make a new text file called todo.txt", "show the content of todo.txt",
    "add 'buy milk' to todo.txt", "list usb devices", "eject the usb drive E", "set my pc to never sleep",
    "show my battery health", "show the date and time", "change the time zone to Pacific", "copy my ip to clipboard",
    "how many files are in my documents folder", "what is using my ram", "how much ram does chrome use",
    "which process is using port 3000", "kill the process on port 8080", "ping google.com", "speed test",
    "remind me to call mom in 20 minutes", "volume 30", "louder", "show me all pdf files on my desktop",
    "delete all tmp files in downloads", "move photos from downloads to pictures", "install obsidian",
    "free space on C", "unzip archive.zip", "convert video.mov to mp4", "convert photo.png to jpg",
    "files I changed this week in documents", "open sound settings", "is spotify running", "update all my apps",
    "what's my public ip", "generate a password", "how big is my downloads folder", "zip my desktop folder",
]
hits = 0
for q in QUERIES:
    h = library.exact(q)
    if h:
        hits += 1
        miss = f"  [fill in: {', '.join(h['missing'])}]" if h["missing"] else ""
        print(f"⚡ {q}\n     {h['code'][:170]}{miss}\n     = {h['note_filled'][:120]}")
    else:
        refs = library.search(q, k=1)
        print(f"🤖 {q}   (AI; closest: {refs[0]['q'][0] if refs else '-'})")
print(f"\n{hits}/{len(QUERIES)} answered instantly from the library")
