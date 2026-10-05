"""The TuneRelay window's keyboard map (Keys.js), driven offscreen with Qt."""

from pathlib import Path

from qml_harness import run_harness


def test_navigate_and_edit_mode_keys_map_to_window_commands() -> None:
    assert run_harness(Path(__file__).parent / "qml" / "keys_harness.qml") == [
        "review 0=close",
        "review 1=song-next",
        "review 2=song-next",
        "review 3=song-previous",
        "review 4=proposal-1",
        "review 5=",
        "review 6=edit",
        "review 7=",
        "review 8=discard",
        "review 9=confirm",
        "review 10=confirm",
        "review 11=replace",
        "review 12=",
        "review 13=",
        "review 14=",
        "review 15=tab-history",
        "review 16=",
        "review 17=tab-next",
        "review 18=tab-previous",
        "review 19=help",
        "review 20=page-down",
        "queue 21=line-down",
        "queue 22=",
        "history 23=row-next",
        "history 24=search",
        "history 25=filter",
        "history 26=youtube",
        "history 27=retry",
        "edit esc=leave",
        "edit ctrl+enter=confirm",
        "edit j=",
        "edit enter=",
    ]
