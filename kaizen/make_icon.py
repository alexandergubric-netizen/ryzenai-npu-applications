"""Builds kaizen.ico and the app-window icon from the chosen design: the kanji 整 ('order') on a dark tile.

Large sizes use the light font weight; 16-48 px use medium so the strokes stay visible on the taskbar.
"""
import os

from PIL import Image

from icon_designs import kanji

SIZES = [16, 24, 32, 48, 64, 128, 256]

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    light, medium = kanji("L"), kanji("M")
    frames = [(medium if s <= 48 else light).resize((s, s), Image.LANCZOS) for s in SIZES]
    # A new file name per design: Windows caches shortcut icons by path, so reusing a name keeps the old picture.
    frames[-1].save(os.path.join(here, "kaizen-sei.ico"), format="ICO", sizes=[(s, s) for s in SIZES],
                    append_images=frames[:-1])
    light.resize((512, 512), Image.LANCZOS).save(os.path.join(here, "kaizen-icon.png"))
    light.resize((192, 192), Image.LANCZOS).save(os.path.join(here, "web", "icon.png"))  # app window / taskbar
    print("icon written")
