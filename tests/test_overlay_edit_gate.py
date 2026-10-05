"""The overlay's EditGate, driven offscreen with Qt's `qml` runtime (skipped when Qt is missing).

The rest of the Omarchy plugin needs Quickshell and is verified manually; this covers the
draft-validation rules that decide whether Confirm/Replace may run.
"""

from pathlib import Path

import pytest

from qml_harness import run_harness


@pytest.fixture(scope="module")
def log() -> list[str]:
    return run_harness(Path(__file__).parent / "qml" / "edit_gate_harness.qml")


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
