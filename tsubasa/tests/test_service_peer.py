"""Sensitive service requests authenticate their actual TCP peer before sending HTTP."""
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from core.service_peer import ServiceConnection


class ServicePeerTests(unittest.TestCase):
    def test_untrusted_listener_receives_no_bytes(self):
        for mismatch in ("executable", "account"):
            with self.subTest(mismatch=mismatch), socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                executable = Path(sys._base_executable)
                if mismatch == "executable":
                    executable = executable.with_name("other-service.exe")
                else:
                    self.enterContext(patch("core.service_peer.equal_sid", return_value=False))
                connection = ServiceConnection(listener.getsockname()[1], executable, timeout=2)
                try:
                    with self.assertRaisesRegex(OSError, "Unexpected local service identity"):
                        connection.request("POST", "/private", b"private chat or audio")
                    peer, _ = listener.accept()
                    with peer:
                        peer.settimeout(2)
                        self.assertEqual(peer.recv(4096), b"")
                finally:
                    connection.close()
