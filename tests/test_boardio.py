"""Smoke-test: valideert dat de unittest-runner + het scripts/ import-pad werken,
door een pure functie uit de integriteits-kern te testen."""
import sys
import unittest
from pathlib import Path

# scripts/ importeerbaar maken — robuust ongeacht hoe `discover` draait.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _boardio  # noqa: E402


class ExtractRevTest(unittest.TestCase):
    def test_reads_rev_from_json_bytes(self):
        self.assertEqual(_boardio._extract_rev(b'{"rev": 7}'), 7)

    def test_missing_rev_defaults_to_zero(self):
        self.assertEqual(_boardio._extract_rev(b'{"cards": []}'), 0)

    def test_invalid_json_defaults_to_zero(self):
        self.assertEqual(_boardio._extract_rev(b'not json at all'), 0)


if __name__ == "__main__":
    unittest.main()
