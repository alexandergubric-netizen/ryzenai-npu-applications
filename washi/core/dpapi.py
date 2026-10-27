"""Windows DPAPI: encrypt small secrets so only this Windows user (on this PC) can read them back."""
import ctypes
from ctypes import wintypes


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _out(blob):
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def protect(data: bytes) -> bytes:
    src, _keep = _blob(data)
    dst = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), "Washi", None, None, None, 0x1, ctypes.byref(dst)):
        raise OSError("Windows could not protect the data")
    return _out(dst)


def unprotect(data: bytes) -> bytes:
    src, _keep = _blob(data)
    dst = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(dst)):
        raise OSError("Windows could not read the protected data")
    return _out(dst)
