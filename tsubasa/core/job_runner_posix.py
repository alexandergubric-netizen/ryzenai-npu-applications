"""POSIX counterpart of job_runner_win: the child gets its own process group, CPU and memory rlimits, a wall-clock
limit and an output cap; the whole group is killed at the end. Like the Windows job object, this limits resources;
it is not filesystem or network isolation. Written for macOS; not yet run on a Mac by the author."""
import os
import resource
import signal
import subprocess
import threading
import time


def run(command, cwd, env, cancel, *, active=1, seconds=10, memory=512 * 1024 * 1024, output_limit=16384,
        stdin=subprocess.DEVNULL, stderr=subprocess.STDOUT, cpu_seconds=3):
    def limits():
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        try:   # macOS does not enforce RLIMIT_AS reliably; the wall-clock and CPU limits still apply
            resource.setrlimit(resource.RLIMIT_AS, (memory * 4, memory * 4))
        except (ValueError, OSError):
            pass

    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=stdin, stdout=subprocess.PIPE, stderr=stderr,
                               preexec_fn=limits)

    def kill():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    chunks, count, overflow = [], 0, threading.Event()

    def read():
        nonlocal count
        while data := process.stdout.read(1024):
            count += len(data)
            if count > output_limit:
                overflow.set()
                kill()
                break
            chunks.append(data)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    start, reason = time.monotonic(), None
    try:
        while process.poll() is None:
            if cancel.wait(0.025):
                reason = "Cancelled."
                break
            if time.monotonic() - start > seconds:
                reason = "Time limit reached."
                break
        if reason:
            kill()
        process.wait(timeout=5)
        kill()   # reap any descendant still holding the output pipe
        reader.join(timeout=5)
        if overflow.is_set():
            reason = "Output limit reached."
        elif not reason and process.returncode == -signal.SIGXCPU:
            reason = "CPU limit reached."
        used = resource.getrusage(resource.RUSAGE_CHILDREN)
        return {"output": b"".join(chunks).decode("utf-8-sig", errors="replace"), "exit_code": process.returncode,
                "cpu_seconds": round(used.ru_utime + used.ru_stime, 3), "limited": reason,
                "seconds": round(time.monotonic() - start, 3)}
    finally:
        if process.poll() is None:
            kill()
            process.wait(timeout=5)
        process.stdout.close()
