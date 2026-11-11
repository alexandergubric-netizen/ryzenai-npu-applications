"""Open exact paths without following a link or relying on a pathname after open (Windows handles or POSIX fds)."""
import os

if os.name == "nt":
    from core.terminal_paths_win import exact_handle, read_file  # noqa: F401
else:
    from contextlib import contextmanager
    import stat

    @contextmanager
    def exact_handle(path, directory=False):
        flags = os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else 0)
        fd = os.open(str(path), flags)
        try:
            if os.path.realpath(path) != os.path.abspath(path):
                raise ValueError("Project path resolves outside the approved location.")
            yield fd
        finally:
            os.close(fd)

    def read_file(path):
        with exact_handle(path) as fd:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16000:
                raise ValueError("Choose a single-link project file of up to 16,000 bytes.")
            data = os.read(fd, 16001)
            if len(data) > 16000:
                raise ValueError("Project file is too large.")
            return data
