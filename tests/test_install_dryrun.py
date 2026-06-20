"""Integratie: install.sh --dry-run schrijft NIETS en rapporteert de footprint.
POSIX-only — install.sh is een bash-script; op Windows overgeslagen."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALL = REPO / "install.sh"
_BASH = shutil.which("bash")
_PY = shutil.which("python3") or shutil.which("python")


@unittest.skipIf(os.name == "nt" or _BASH is None or _PY is None,
                 "needs bash + python on a POSIX host")
class InstallDryRunTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.project = self.home / "proj"
        self.project.mkdir()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def _run(self, *extra):
        env = dict(os.environ)
        env["HOME"] = str(self.home)
        env["CLAUDE_CONFIG_DIR"] = str(self.home / ".claude")
        return subprocess.run(
            [_BASH, str(INSTALL), "--dry-run", "--no-open",
             "--project", str(self.project), *extra],
            cwd=str(REPO), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=60)

    def test_dry_run_exits_zero_and_writes_nothing(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.home / ".claude" / "skills" / "board-steward").exists())
        self.assertFalse((self.home / ".claude" / "settings.json").exists())
        self.assertFalse((self.project / "board").exists())

    def test_dry_run_reports_footprint(self):
        out = self._run().stdout.lower()
        self.assertIn("dry-run", out)
        self.assertIn("hook", out)
        self.assertIn("autostart", out)

    def test_autostart_is_opt_in_by_default(self):
        out = self._run().stdout.lower()
        self.assertIn("skipped", out)  # autostart skipped tenzij --autostart

    def test_autostart_flag_enables_in_report(self):
        out = self._run("--autostart").stdout.lower()
        self.assertIn("login service", out)  # geactiveerd pad rapporteert de service


if __name__ == "__main__":
    unittest.main()
