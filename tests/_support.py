"""Process-wide bootstrap for the ensemble unit-test suite.

Every test module imports this module *before* ``ensemble``.  ``ENSEMBLE_HOME``
is read by ``ensemble.py`` at import time (it drives ``HOME``, the Gemini key
path and, transitively, ``serve.RUNS_DIR``), so pointing it at a throwaway temp
directory here guarantees the suite never reads or writes the developer's real
``~/.ensemble``.

Nothing in this file is itself a test (the filename does not start with
``test_``), so unittest discovery ignores it.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

ENSEMBLE_DIR = Path(__file__).resolve().parent.parent
if str(ENSEMBLE_DIR) not in sys.path:
    # Make ``import ensemble`` / ``import serve`` work no matter where the
    # runner was started from, as long as this file was found by discovery.
    sys.path.insert(0, str(ENSEMBLE_DIR))

# Must be set before ``import ensemble``: HOME is resolved at module import.
TEST_HOME = Path(tempfile.mkdtemp(prefix="ensemble-tests-home-"))
os.environ["ENSEMBLE_HOME"] = str(TEST_HOME)
# Keep any accidental CLI output plain; tests never execute provider CLIs, but
# this also makes the app's colour helpers deterministic.
os.environ.setdefault("NO_COLOR", "1")


def _remove_test_home() -> None:
    shutil.rmtree(TEST_HOME, ignore_errors=True)


atexit.register(_remove_test_home)

import ensemble  # noqa: E402  (deliberately imported after ENSEMBLE_HOME is set)

if ensemble.HOME != TEST_HOME:
    raise RuntimeError(
        "ensemble was imported before tests/_support.py could isolate "
        f"ENSEMBLE_HOME (ensemble.HOME={ensemble.HOME!r}, "
        f"expected {TEST_HOME!r}). Import _support before ensemble in every "
        "test module."
    )
