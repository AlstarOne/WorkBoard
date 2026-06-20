"""Karakterisering van hourly_extract_llm: ChunkExtractionError vs lege bucket + split-recovery.
Alle LLM-calls gemockt — er draait nooit een echte `claude -p`."""
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import hourly_extract_llm as hx  # noqa: E402


def _proc(returncode=0, stdout=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


class ExtractChunkTest(unittest.TestCase):
    def _chunk(self):
        return [("12:00", [{"ts": 1}])]

    def test_returns_cards_on_success(self):
        with mock.patch.object(hx, "build_digest", return_value="DIGEST"), \
             mock.patch.object(hx, "subprocess") as msub, \
             mock.patch.object(hx, "parse_card_array", return_value=[{"title": "x"}]):
            msub.SubprocessError = Exception
            msub.run.return_value = _proc(0, '[{"title": "x"}]')
            cards = hx.extract_cards_for_chunk(self._chunk(), Path("."))
        self.assertEqual(cards, [{"title": "x"}])

    def test_nonzero_exit_raises_chunk_error(self):
        with mock.patch.object(hx, "build_digest", return_value="DIGEST"), \
             mock.patch.object(hx, "subprocess") as msub:
            msub.SubprocessError = Exception
            msub.run.return_value = _proc(1, "")
            with self.assertRaises(hx.ChunkExtractionError):
                hx.extract_cards_for_chunk(self._chunk(), Path("."))

    def test_non_json_raises_chunk_error(self):
        with mock.patch.object(hx, "build_digest", return_value="DIGEST"), \
             mock.patch.object(hx, "subprocess") as msub, \
             mock.patch.object(hx, "parse_card_array", return_value=None):
            msub.SubprocessError = Exception
            msub.run.return_value = _proc(0, "not json")
            with self.assertRaises(hx.ChunkExtractionError):
                hx.extract_cards_for_chunk(self._chunk(), Path("."))

    def test_empty_digest_returns_empty_without_subprocess(self):
        with mock.patch.object(hx, "build_digest", return_value=""), \
             mock.patch.object(hx, "subprocess") as msub:
            cards = hx.extract_cards_for_chunk(self._chunk(), Path("."))
        self.assertEqual(cards, [])
        msub.run.assert_not_called()


class RetryLadderTest(unittest.TestCase):
    def test_clean_chunk_returns_without_retry(self):
        buckets = {0: [{"ts": 1}], 1: [{"ts": 2}]}
        with mock.patch.object(hx, "extract_cards_for_chunk",
                               return_value=[{"title": "ok"}]) as m:
            out = hx._extract_chunk_with_retries([0, 1], buckets, Path("."), 30)
        self.assertEqual(out, [{"title": "ok"}])
        self.assertEqual(m.call_count, 1)  # geen retry op een schone chunk

    def test_failed_multibucket_splits_and_recovers(self):
        buckets = {0: [{"ts": 1}], 1: [{"ts": 2}]}
        seen = []

        def side_effect(chunk, project):
            seen.append(chunk)
            if len(chunk) > 1:
                raise hx.ChunkExtractionError("multi")
            return [{"title": "half-%d" % len(seen)}]

        with mock.patch.object(hx, "extract_cards_for_chunk", side_effect=side_effect):
            out = hx._extract_chunk_with_retries([0, 1], buckets, Path("."), 30)
        self.assertEqual(len(out), 2)  # beide helften los hersteld


if __name__ == "__main__":
    unittest.main()
