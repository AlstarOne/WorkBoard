"""Karakterisering van card_state.atomic_save: rev-as-CAS lost-update-preventie + backup."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import card_state  # noqa: E402

MINIMAL_BOARD = {
    "rev": 1, "nextNum": 1, "savedAt": "", "savedBy": "claude",
    "columns": [
        {"id": "task", "name": "Task", "kind": "todo", "stackUnder": None},
        {"id": "inprogress", "name": "In Progress", "kind": "active", "stackUnder": None},
        {"id": "done", "name": "Done", "kind": "done", "stackUnder": None},
    ],
    "cards": [],
}


class AtomicSaveCasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.board = self.tmp / "board.json"
        self.board.write_text(json.dumps(MINIMAL_BOARD))
        self._saved_board_no_server = os.environ.get("BOARD_NO_SERVER")
        os.environ["BOARD_NO_SERVER"] = "1"
        card_state._HOLDING_LOCK = True
        self._orig_regen = card_state.REGEN_SCRIPT
        card_state.REGEN_SCRIPT = self.tmp / "nope.py"  # bestaat niet → geen regen-subprocess

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self._saved_board_no_server is not None:
            os.environ["BOARD_NO_SERVER"] = self._saved_board_no_server
        else:
            os.environ.pop("BOARD_NO_SERVER", None)
        card_state._HOLDING_LOCK = False
        card_state.REGEN_SCRIPT = self._orig_regen

    def test_atomic_save_bumps_rev_and_returns_new_rev(self):
        d = card_state.load(self.board)
        new_rev = card_state.atomic_save(self.board, d)
        self.assertEqual(new_rev, 2)
        self.assertEqual(json.loads(self.board.read_text())["rev"], 2)

    def test_assert_base_rev_raises_on_mismatch(self):
        with self.assertRaises(card_state.BoardConflict):
            card_state._assert_base_rev(self.board, 99)

    def test_concurrent_bump_triggers_conflict(self):
        d = card_state.load(self.board)  # base rev 1
        other = json.loads(self.board.read_text())
        other["rev"] = 2  # een andere schrijver bumpt disk achter onze rug
        self.board.write_text(json.dumps(other))
        with self.assertRaises(card_state.BoardConflict):
            card_state.atomic_save(self.board, d)

    def test_current_rev_missing_file_returns_none(self):
        self.assertIsNone(card_state._current_rev(self.tmp / "absent.json"))

    def test_backup_written_on_save(self):
        d = card_state.load(self.board)
        card_state.atomic_save(self.board, d)
        self.assertTrue((self.tmp / ".backups" / "board-2.json").exists())


if __name__ == "__main__":
    unittest.main()
