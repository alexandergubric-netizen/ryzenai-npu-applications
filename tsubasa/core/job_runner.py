"""Resource-limited owned processes: Windows job objects, or POSIX process groups with rlimits (macOS)."""
import os

if os.name == "nt":
    from core.job_runner_win import run  # noqa: F401
else:
    from core.job_runner_posix import run  # noqa: F401
