"""The overlay's ReviewSession (selected song, draft and actions), driven offscreen with Qt.

CLI answers are held and released by the harness, so these cover responses that arrive after
the user has already selected another song.
"""

from pathlib import Path

import pytest

from qml_harness import run_harness


@pytest.fixture(scope="module")
def scenarios() -> list[list[str]]:
    log = run_harness(Path(__file__).parent / "qml" / "review_session_harness.qml")
    groups: list[list[str]] = [[]]
    for entry in log:
        if entry == "---":
            groups.append([])
        else:
            groups[-1].append(entry)
    return groups


def test_a_late_show_for_the_previous_song_never_takes_over_the_form(scenarios: list[list[str]]) -> None:
    assert scenarios[0] == ["late show: selected=5 form=none", "cli confirm 5", "confirmed saved=1 shown=1"]


def test_a_late_proposal_selection_for_the_previous_song_is_dropped(scenarios: list[list[str]]) -> None:
    assert scenarios[1] == [
        "cli select 5 1",
        "late select: selected=3 form=none",
        "cli confirm 3",
        "confirmed saved=1 shown=1",
    ]


def test_a_late_cover_change_for_the_previous_song_is_dropped(scenarios: list[list[str]]) -> None:
    assert scenarios[2] == ["cli cover 7 --thumbnail", "late cover: selected=3 form=none"]


def test_nothing_is_confirmed_before_the_selected_song_has_loaded(scenarios: list[list[str]]) -> None:
    assert scenarios[3] == ["queued before load: 1"]


def test_a_confirm_waiting_on_edits_is_dropped_when_switching_songs(scenarios: list[list[str]]) -> None:
    assert scenarios[4] == ["cli edit 9 track=4", "pending after switch: 0 selected=3 form=3"]


def test_an_edit_while_a_proposal_selection_is_pending_never_hides_what_gets_confirmed(
    scenarios: list[list[str]],
) -> None:
    assert scenarios[5] == [
        "queued while selecting: 1",
        "cli select 11 0",
        "cli confirm 11",
        "confirmed saved=proposal 0 shown=proposal 0",
    ]


def test_a_failed_proposal_selection_reloads_the_saved_draft_before_confirm(
    scenarios: list[list[str]],
) -> None:
    assert scenarios[6] == [
        "cli edit 12 track=4",
        "cli select 12 2",
        "after failure: ready=false queued=1",
        "cli confirm 12",
        "confirmed saved=4 shown=4",
    ]
