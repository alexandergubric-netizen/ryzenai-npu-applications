"""Open exact Windows paths without following a reparse point or relying on a pathname after open."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import msvcrt
import os
from pathlib import Path
import stat

K=ctypes.WinDLL("kernel32",use_last_error=True)
K.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
K.CreateFileW.restype=wintypes.HANDLE
K.GetFinalPathNameByHandleW.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]
K.GetFinalPathNameByHandleW.restype=wintypes.DWORD
K.CloseHandle.argtypes=[wintypes.HANDLE];K.CloseHandle.restype=wintypes.BOOL
INVALID=ctypes.c_void_p(-1).value

@contextmanager
def exact_handle(path,directory=False):
    flags=0x00200000 | (0x02000000 if directory else 0)
    access=0x80 if directory else 0x80000000
    handle=K.CreateFileW(str(path),access,3 if directory else 1,None,3,flags,None)
    if handle==INVALID:raise ctypes.WinError(ctypes.get_last_error())
    try:
        buf=ctypes.create_unicode_buffer(32768)
        length=K.GetFinalPathNameByHandleW(handle,buf,len(buf),0)
        if not 0<length<len(buf):raise ValueError("Could not verify project path.")
        final=buf.value.removeprefix("\\\\?\\")
        if os.path.normcase(final)!=os.path.normcase(os.path.abspath(path)):
            raise ValueError("Project path resolves outside the approved location.")
        if path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("Linked project paths are unavailable.")
        yield handle
    finally:K.CloseHandle(handle)

def read_file(path):
    with exact_handle(path) as handle:
        # The original handle remains owned by the context and pins this exact file.
        dup=wintypes.HANDLE()
        current=ctypes.c_void_p(-1)
        duplicate=K.DuplicateHandle
        duplicate.argtypes=[wintypes.HANDLE,wintypes.HANDLE,wintypes.HANDLE,ctypes.POINTER(wintypes.HANDLE),wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        if not duplicate(current,handle,current,ctypes.byref(dup),0,False,2):raise ctypes.WinError(ctypes.get_last_error())
        fd=msvcrt.open_osfhandle(dup.value,os.O_RDONLY|os.O_BINARY)
        with os.fdopen(fd,"rb") as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>16000:
                raise ValueError("Choose a single-link project file of up to 16,000 bytes.")
            data=stream.read(16001)
            if len(data)>16000:raise ValueError("Project file is too large.")
            return data

