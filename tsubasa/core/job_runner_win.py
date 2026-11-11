"""Resource-limited owned processes. Job objects are not filesystem/network isolation."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import threading
import time

K=ctypes.WinDLL("kernel32",use_last_error=True)
N=ctypes.WinDLL("ntdll")
SIZE=ctypes.c_size_t
class IO(ctypes.Structure):
    _fields_=[(n,ctypes.c_ulonglong) for n in ("reads","writes","other","read_bytes","write_bytes","other_bytes")]
class BASIC(ctypes.Structure):
    _fields_=[("process_time",ctypes.c_longlong),("job_time",ctypes.c_longlong),("flags",wintypes.DWORD),
              ("min_working",SIZE),("max_working",SIZE),("active",wintypes.DWORD),("affinity",SIZE),
              ("priority",wintypes.DWORD),("scheduling",wintypes.DWORD)]
class ACCOUNTING(ctypes.Structure):
    _fields_=[(n,ctypes.c_longlong) for n in ("user","kernel","period_user","period_kernel")]+[
        (n,wintypes.DWORD) for n in ("faults","processes","active","terminated")]

class LIMITS(ctypes.Structure):
    _fields_=[("basic",BASIC),("io",IO),("process_memory",SIZE),("job_memory",SIZE),("peak_process",SIZE),("peak_job",SIZE)]
K.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];K.CreateJobObjectW.restype=wintypes.HANDLE
K.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD];K.SetInformationJobObject.restype=wintypes.BOOL
K.QueryInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
K.QueryInformationJobObject.restype=wintypes.BOOL
K.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];K.AssignProcessToJobObject.restype=wintypes.BOOL
K.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT];K.TerminateJobObject.restype=wintypes.BOOL
K.CloseHandle.argtypes=[wintypes.HANDLE];K.CloseHandle.restype=wintypes.BOOL
N.NtResumeProcess.argtypes=[wintypes.HANDLE];N.NtResumeProcess.restype=ctypes.c_long

def run(command,cwd,env,cancel,*,active=1,seconds=10,memory=512*1024*1024,output_limit=16384,
        stdin=subprocess.DEVNULL,stderr=subprocess.STDOUT,cpu_seconds=3):
    job=K.CreateJobObjectW(None,None)
    if not job:raise ctypes.WinError(ctypes.get_last_error())
    process=None
    try:
        limits=LIMITS()
        limits.basic.flags=0x2000|0x8|0x4|0x100|0x200  # kill-on-close, process count, CPU, memory
        limits.basic.active=active
        limits.basic.job_time=cpu_seconds*10000000
        limits.process_memory=memory;limits.job_memory=memory
        if not K.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        process=subprocess.Popen(command,cwd=cwd,env=env,stdin=stdin,
            stdout=subprocess.PIPE,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW|0x4)
        if not K.AssignProcessToJobObject(job,wintypes.HANDLE(int(process._handle))):
            raise ctypes.WinError(ctypes.get_last_error())
        chunks=[];count=0;overflow=threading.Event()
        def read():
            nonlocal count
            while data:=process.stdout.read(1024):
                count+=len(data)
                if count>output_limit:
                    overflow.set();K.TerminateJobObject(job,1);break
                chunks.append(data)
        reader=threading.Thread(target=read,daemon=True);reader.start()
        if N.NtResumeProcess(wintypes.HANDLE(int(process._handle)))<0:
            raise RuntimeError("Could not resume the constrained process.")
        start=time.monotonic();reason=None
        usage=ACCOUNTING()
        while process.poll() is None:
            if not K.QueryInformationJobObject(job,1,ctypes.byref(usage),ctypes.sizeof(usage),None):
                raise ctypes.WinError(ctypes.get_last_error())
            if usage.user + usage.kernel >= limits.basic.job_time:
                reason="CPU limit reached."
                break
            if cancel.wait(.025):reason="Cancelled.";break
            if time.monotonic()-start>seconds:reason="Time limit reached.";break
        if reason:K.TerminateJobObject(job,1)
        process.wait(timeout=5)
        usage=ACCOUNTING()
        if not K.QueryInformationJobObject(job,1,ctypes.byref(usage),ctypes.sizeof(usage),None):
            raise ctypes.WinError(ctypes.get_last_error())
        if not reason and usage.user + usage.kernel >=limits.basic.job_time:reason="CPU limit reached."
        K.TerminateJobObject(job,1)  # Reap any descendant still holding the output pipe.
        reader.join(timeout=5)
        if overflow.is_set():reason="Output limit reached."
        if reader.is_alive():raise RuntimeError("Output reader did not exit.")
        return {"output":b"".join(chunks).decode("utf-8-sig",errors="replace"),
                "exit_code":process.returncode,"cpu_seconds":round((usage.user + usage.kernel)/10000000,3),"limited":reason,"seconds":round(time.monotonic()-start,3)}
    finally:
        if process and process.poll() is None:
            K.TerminateJobObject(job,1)
            process.terminate();process.wait(timeout=5)
        if process and process.stdout:process.stdout.close()
        K.CloseHandle(job)

