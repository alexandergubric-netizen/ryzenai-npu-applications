"""Verify the Windows process on the other end of a connected loopback socket."""
import ctypes
import http.client
import os
import socket
import struct

WINDOWS = os.name == "nt"

if WINDOWS:
    from ctypes import wintypes as wt


    def _api(library, name, result, *args):
        function = getattr(library, name)
        function.restype = result
        function.argtypes = args
        return function


    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    iphelper = ctypes.WinDLL("iphlpapi", use_last_error=True)
    pointer = ctypes.c_void_p
    dword_ptr = ctypes.POINTER(wt.DWORD)
    tcp_table = _api(iphelper, "GetExtendedTcpTable", wt.DWORD, pointer, dword_ptr, wt.BOOL,
                     wt.ULONG, ctypes.c_int, wt.ULONG)
    open_process = _api(kernel, "OpenProcess", wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
    close = _api(kernel, "CloseHandle", wt.BOOL, wt.HANDLE)
    image_name = _api(kernel, "QueryFullProcessImageNameW", wt.BOOL, wt.HANDLE, wt.DWORD,
                      wt.LPWSTR, dword_ptr)
    open_token = _api(security, "OpenProcessToken", wt.BOOL, wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE))
    token_info = _api(security, "GetTokenInformation", wt.BOOL, wt.HANDLE, ctypes.c_int,
                      pointer, wt.DWORD, dword_ptr)
    equal_sid = _api(security, "EqualSid", wt.BOOL, pointer, pointer)


    def _peer_pid(sock):
        # MIB_TCPTABLE_OWNER_PID begins with a DWORD count followed by six DWORDs per row.
        size = wt.DWORD()
        for _ in range(5):
            buffer = ctypes.create_string_buffer(size.value) if size.value else None
            status = tcp_table(buffer, ctypes.byref(size), False, socket.AF_INET, 5, 0)
            if status == 122:  # ERROR_INSUFFICIENT_BUFFER, also possible if the table grew
                continue
            if status:
                raise ctypes.WinError(status)
            break
        else:
            raise OSError("Could not capture the local TCP connection table.")
        host, port = sock.getpeername()
        local_host, local_port = sock.getsockname()
        loopback = int.from_bytes(socket.inet_aton("127.0.0.1"), "little")
        if host == local_host == "127.0.0.1":
            for index in range(struct.unpack_from("<I", buffer)[0]):
                state, addr, server_port, remote, client_port, pid = struct.unpack_from("<6I", buffer, 4 + index*24)
                if (state, addr, server_port, remote, client_port) == (
                        5, loopback, socket.htons(port), loopback, socket.htons(local_port)) and pid:
                    return pid
        raise OSError("Could not identify the connected local service.")


    def _user(process):
        token = wt.HANDLE()
        if not open_token(process, 8, ctypes.byref(token)):  # TOKEN_QUERY
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            size = wt.DWORD()
            token_info(token, 1, None, 0, ctypes.byref(size))  # TokenUser
            if not size.value:
                raise ctypes.WinError(ctypes.get_last_error())
            data = ctypes.create_string_buffer(size.value)
            if not token_info(token, 1, data, size, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            return data  # owns both the SID_AND_ATTRIBUTES and its pointed-to SID
        finally:
            close(token)


    def verify_peer(sock, executable):
        pid = _peer_pid(sock)
        process = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            path = ctypes.create_unicode_buffer(32768)
            size = wt.DWORD(len(path))
            if not image_name(process, 0, path, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            peer, current = _user(process), _user(wt.HANDLE(-1))
            if (os.path.normcase(path.value) != os.path.normcase(os.path.abspath(executable))
                    or not equal_sid(pointer.from_buffer(peer), pointer.from_buffer(current))
                    or _peer_pid(sock) != pid):
                raise OSError("Unexpected local service identity.")
        finally:
            close(process)
else:
    def verify_peer(sock, executable):
        """macOS: no process-identity check yet; the connection is loopback-only (see MAC.md)."""
        if sock.getpeername()[0] != "127.0.0.1":
            raise OSError("Unexpected local service address.")


class ServiceConnection(http.client.HTTPConnection):
    def __init__(self, port, executable, *, timeout):
        super().__init__("127.0.0.1", port, timeout=timeout)
        self.executable = executable

    def connect(self):
        super().connect()
        try:
            verify_peer(self.sock, self.executable)
        except Exception:
            self.close()
            raise
