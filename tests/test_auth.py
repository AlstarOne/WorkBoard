"""Security: een netwerk-bind (0.0.0.0 / LAN-IP) mag nooit ongeauthenticeerd zijn."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import serve  # noqa: E402


class ResolveAuthTokenTest(unittest.TestCase):
    def test_explicit_token_always_wins(self):
        self.assertEqual(
            serve.resolve_auth_token("0.0.0.0", explicit_token="abc"), "abc")
        self.assertEqual(
            serve.resolve_auth_token("127.0.0.1", explicit_token="abc"), "abc")

    def test_loopback_needs_no_token(self):
        for host in ("127.0.0.1", "::1", "localhost"):
            self.assertIsNone(serve.resolve_auth_token(host))

    def test_network_bind_without_token_autogenerates(self):
        for host in ("0.0.0.0", "::", "192.168.1.50"):
            tok = serve.resolve_auth_token(host)
            self.assertIsInstance(tok, str)
            self.assertGreaterEqual(len(tok), 16)

    def test_insecure_flag_keeps_network_bind_open(self):
        self.assertIsNone(
            serve.resolve_auth_token("0.0.0.0", insecure=True))


if __name__ == "__main__":
    unittest.main()
