"""Run a QML harness offscreen with Qt's `qml` runtime and return the log it prints."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

QML = shutil.which("qml6") or shutil.which("qml", path="/usr/lib/qt6/bin") or shutil.which("qml")


def run_harness(harness: Path) -> list[str]:
    """Skips the test when Qt is not installed; the harness prints one `RESULT <json list>` line."""
    if QML is None:
        pytest.skip("Qt's qml runtime is not installed")
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_FORCE_STDERR_LOGGING": "1"}
    result = subprocess.run(
        [QML, str(harness)], capture_output=True, text=True, timeout=30, env=env, check=False
    )
    lines = [line for line in result.stderr.splitlines() if "RESULT " in line]
    assert lines, result.stderr
    return json.loads(lines[-1].split("RESULT ", 1)[1])
