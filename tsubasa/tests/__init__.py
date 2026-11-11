"""Tsubasa tests. Many tests keep their temporary homes in `.test-runs` (ignored by git and not packed): create it,
so a fresh copy of the project (for example on the Mac) runs the suite as is."""
from pathlib import Path

(Path(__file__).resolve().parents[1] / ".test-runs").mkdir(exist_ok=True)
