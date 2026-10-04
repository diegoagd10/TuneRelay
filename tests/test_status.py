import json
import subprocess

from conftest import BIN, TuneRelay


def test_status_counts_songs_waiting_for_review_and_work_in_flight(tr: TuneRelay) -> None:
    reviewed = tr.ready_for_review()
    queued = tr.capture("aaaaaaaaaaa")

    status = tr.cli("status")

    assert status["review"] == 1
    assert status["busy"] is True
    assert status["counts"]["ready_for_review"] == 1
    assert status["counts"]["queued"] == 1
    assert [s["id"] for s in status["review_songs"]] == [reviewed]
    assert [s["id"] for s in status["queue"]] == [queued]


def test_status_is_idle_when_nothing_is_in_flight(tr: TuneRelay) -> None:
    status = tr.cli("status")

    assert (status["review"], status["busy"], status["queue"]) == (0, False, [])
    assert status["max_attempts"] == 3


def test_watch_emits_the_status_now_and_again_whenever_it_changes(tr: TuneRelay) -> None:
    song_id = tr.ready_for_review()
    watch = subprocess.Popen(
        [str(BIN / "tunerelay"), "watch", "--count", "2"], stdout=subprocess.PIPE, env=tr.env, text=True
    )
    assert watch.stdout is not None
    first = json.loads(watch.stdout.readline())
    assert first["review"] == 1

    tr.cli("confirm", str(song_id))

    second = json.loads(watch.stdout.readline())
    assert second["review"] == 0
    assert second["version"] > first["version"]
    assert [s["state"] for s in second["queue"]] == ["in_transit"]
    assert watch.wait(timeout=10) == 0


def test_history_search_and_state_filter(tr: TuneRelay) -> None:
    sent = tr.ready_for_review("aaaaaaaaaaa")
    tr.cli(
        "edit",
        str(sent),
        "title=Rain",
        "artist=Liv Lingive",
        "album_artist=Liv Lingive",
        "album=Rain (Single)",
    )
    tr.cli("confirm", str(sent))
    tr.daemon_once()
    discarded = tr.ready_for_review("bbbbbbbbbbb")
    tr.cli("discard", str(discarded))

    everything = tr.cli("history")["songs"]
    assert [s["id"] for s in everything] == [discarded, sent]
    assert [s["id"] for s in tr.cli("history", "--q", "lingive")["songs"]] == [sent]
    assert [s["id"] for s in tr.cli("history", "--state", "discarded")["songs"]] == [discarded]
    assert tr.cli("history", "--q", "lingive", "--state", "discarded")["songs"] == []
    entry = everything[1]
    assert entry["url"] == "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    assert (entry["title"], entry["artist"], entry["album"]) == ("Rain", "Liv Lingive", "Rain (Single)")
    assert entry["remote_path"] == "Liv Lingive/Rain (Single) (2024)/01 - Rain.m4a"
    assert entry["updated_at"].startswith("20")
