"""The overlay's EditGate, driven offscreen with Qt's `qml` runtime (skipped when Qt is missing).

The rest of the Omarchy plugin needs Quickshell and is verified manually; this covers the
draft-validation rules that decide whether Confirm/Replace may run.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).parent / "qml" / "edit_gate_harness.qml"
QML = shutil.which("qml6") or shutil.which("qml", path="/usr/lib/qt6/bin") or shutil.which("qml")


@pytest.fixture(scope="module")
def log() -> list[str]:
    if QML is None:
        pytest.skip("Qt's qml runtime is not installed")
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_FORCE_STDERR_LOGGING": "1"}
    result = subprocess.run(
        [QML, str(HARNESS)], capture_output=True, text=True, timeout=30, env=env, check=False
    )
    lines = [line for line in result.stderr.splitlines() if "RESULT " in line]
    assert lines, result.stderr
    return json.loads(lines[-1].split("RESULT ", 1)[1])


def test_a_rejected_edit_blocks_confirm(log: list[str]) -> None:
    assert log[0] == "blocked 1"


def test_switching_songs_does_not_carry_rejected_fields_over(log: list[str]) -> None:
    assert log[1] == "confirm 2 saved=2 shown=2"


def test_reselecting_the_same_proposal_restores_the_editor_and_its_saved_value(log: list[str]) -> None:
    assert log[2] == "blocked 1"
    assert log[3] == "after reselect shown=1"
    assert log[4] == "confirm 1 saved=1 shown=1"


def test_a_rejection_that_arrives_after_switching_songs_is_ignored(log: list[str]) -> None:
    assert log[5:] == ["confirm 2 saved=2 shown=2"]
