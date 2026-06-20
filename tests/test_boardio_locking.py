"""Karakterisering van _boardio: backup-snapshots/pruning en cross-process locks."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _boardio  # noqa: E402


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.board = self.tmp / "board.json"
        self.board.write_text('{"rev": 1}')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_backup_creates_snapshot_named_by_rev(self):
        _boardio.write_backup(self.board, b'{"rev": 5}')
        snap = self.tmp / ".backups" / "board-5.json"
        self.assertTrue(snap.exists())
        self.assertEqual(snap.read_bytes(), b'{"rev": 5}')

    def test_prune_keeps_only_newest_N(self):
        for rev in range(1, 13):  # 12 snapshots; keep == 10
            _boardio.write_backup(self.board, json.dumps({"rev": rev}).encode())
        bdir = self.tmp / ".backups"
        revs = sorted(int(p.stem.split("-")[1]) for p in bdir.glob("board-*.json"))
        self.assertEqual(len(revs), _boardio.BACKUP_KEEP)
        self.assertEqual(revs, list(range(3, 13)))  # newest 10 = revs 3..12

    def test_list_backups_newest_first(self):
        for rev in (1, 2, 3):
            _boardio.write_backup(self.board, json.dumps({"rev": rev}).encode())
        revs = [r for r, _ in _boardio.list_backups(self.board)]
        self.assertEqual(revs, [3, 2, 1])


class LockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.board = self.tmp / "board.json"
        self.board.write_text("{}")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_board_lock_acquires_when_free(self):
        with _boardio.board_lock(self.board) as acquired:
            self.assertTrue(acquired)

    def test_board_lock_times_out_when_already_held(self):
        with _boardio.board_lock(self.board) as first:
            self.assertTrue(first)
            with _boardio.board_lock(self.board, timeout=0.2) as second:
                self.assertFalse(second)

    def test_recon_lock_is_non_blocking(self):
        with _boardio.recon_lock(self.board) as first:
            self.assertTrue(first)
            with _boardio.recon_lock(self.board) as second:
                self.assertFalse(second)


if __name__ == "__main__":
    unittest.main()
