"""Karakterisering van port_registry.assign + liveness-registry round-trip."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import port_registry  # noqa: E402


class PortRegistryTest(unittest.TestCase):
    _ENV_KEYS = ("BOARD_REGISTRY", "BOARD_ASSIGNMENTS", "BOARD_ACTIVE")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._saved = {k: os.environ.get(k) for k in self._ENV_KEYS}
        os.environ["BOARD_REGISTRY"] = str(self.tmp / "registry.json")
        os.environ["BOARD_ASSIGNMENTS"] = str(self.tmp / "assignments.json")
        os.environ["BOARD_ACTIVE"] = str(self.tmp / "last-active")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        for k in self._ENV_KEYS:
            if self._saved[k] is not None:
                os.environ[k] = self._saved[k]
            else:
                os.environ.pop(k, None)

    def _board(self, name):
        d = self.tmp / name
        d.mkdir(exist_ok=True)
        return str(d)

    def test_assign_returns_port_in_range(self):
        port = port_registry.assign(self._board("a"))
        self.assertTrue(port_registry.PORT_LO <= port <= port_registry.PORT_HI)

    def test_assign_is_sticky_for_same_board(self):
        a = self._board("a")
        self.assertEqual(port_registry.assign(a), port_registry.assign(a))

    def test_preferred_taken_by_other_board_falls_through(self):
        a = self._board("a")
        self.assertEqual(
            port_registry.assign(a, preferred=port_registry.PORT_LO),
            port_registry.PORT_LO,
        )
        b = self._board("b")
        p_b = port_registry.assign(b, preferred=port_registry.PORT_LO)
        self.assertNotEqual(p_b, port_registry.PORT_LO)
        self.assertTrue(port_registry.PORT_LO <= p_b <= port_registry.PORT_HI)

    def test_dead_dir_is_gced_freeing_its_port(self):
        a = self.tmp / "a"
        a.mkdir()
        self.assertEqual(
            port_registry.assign(str(a), preferred=port_registry.PORT_LO),
            port_registry.PORT_LO,
        )
        shutil.rmtree(a)  # board dir verdwijnt van disk
        b = self._board("b")
        self.assertEqual(
            port_registry.assign(b, preferred=port_registry.PORT_LO),
            port_registry.PORT_LO,  # vrijgekomen poort herbruikt
        )

    def test_write_lookup_remove_roundtrip(self):
        a = self._board("a")
        port_registry.write(a, 7895, os.getpid())
        self.assertEqual(port_registry.lookup(a), 7895)
        port_registry.remove(a)
        self.assertIsNone(port_registry.lookup(a))


if __name__ == "__main__":
    unittest.main()
