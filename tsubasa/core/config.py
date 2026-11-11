"""Configuration. No external packages or remote endpoints."""
import os
import shutil
from pathlib import Path

from core.platform import MAC, WINDOWS, data_home

APP_NAME = 'Tsubasa'
VERSION = '0.9.5'
ROOT = Path(__file__).resolve().parents[1]

# The AI engine: FastFlowLM on the Ryzen AI NPU (Windows) or MLX on Apple silicon (macOS).
ENGINE = os.environ.get('TSUBASA_ENGINE') or ('mlx' if MAC else 'flm')

if ENGINE == 'mlx':
    DEFAULT_MODEL = 'mlx-community/Qwen3-8B-4bit'    # chat
    TERMINAL_MODEL = 'mlx-community/Qwen3-4B-4bit'   # Code mode's terminal steps: smaller and faster
else:
    DEFAULT_MODEL = 'qwen-liberty3.5:9b'   # chat and the area modes (falls back to an installed model)
    TERMINAL_MODEL = 'qwen3-it:4b'         # Terminal mode: fast, follows Sensei's command format well
IMAGE_MODEL = 'RealVisXL V5 Lightning' # Images mode, served by a stable-diffusion.cpp sd-server on 52627
FLM_PORT = 52625
GATEWAY_PORT = 52626
MLX_PORT = 52631


def _flm_exe():
    found = shutil.which('flm')
    return Path(found) if found else Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'flm' / 'flm.exe'


FLM_EXE = _flm_exe() if WINDOWS else Path('flm')
DATA_HOME = data_home(APP_NAME)


def image_studio():
    """Folder of the optional image engine (bin/sd-server + models/RealVisXL…): TSUBASA_IMAGE_STUDIO, a folder
    next to the app, or the app's data home. Images mode says how to add it when none is found."""
    names = [os.environ.get('TSUBASA_IMAGE_STUDIO'), ROOT.parent / 'image-studio', DATA_HOME / 'image-studio']
    for name in filter(None, names):
        if (Path(name) / 'bin').is_dir():
            return Path(name)
    return DATA_HOME / 'image-studio'


def pick_model(installed, *wanted):
    """The first wanted model that is installed, else the first installed one (None when there is none)."""
    ids = [m['id'] if isinstance(m, dict) else m for m in installed]
    for w in wanted:
        if w in ids:
            return w
    return ids[0] if ids else None
